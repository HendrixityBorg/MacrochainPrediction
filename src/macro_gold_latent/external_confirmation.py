from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import ROOT
from .io import read_csv, read_json, sha256_file
from .locking import verify_lock


PREDICTION_FIELDS = {
    "event_id", "predicted_at_utc", "label_unlock_not_before_utc",
    "chain_probability", "ci_lower", "ci_upper",
    "p_1", "p_2", "p_3", "n_1", "n_2", "n_3",
}
LABEL_FIELDS = {"event_id", "outcome", "label_available_at_utc"}


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must contain a timezone")
    return parsed.astimezone(timezone.utc)


def _number(value: str, *, low: float, high: float, name: str) -> float:
    number = float(value)
    if not low <= number <= high:
        raise ValueError(f"{name} outside [{low}, {high}]")
    return number


def audit_bundle(bundle: Path, *, root: Path = ROOT, unlocked: bool = False) -> dict[str, Any]:
    """Fail-closed audit for a genuinely new external confirmation batch.

    The function never constructs labels.  Before unlock it rejects a labels
    file; after unlock it verifies that every prediction predates the declared
    label availability time.
    """
    errors: list[str] = []
    manifest_path = bundle / "manifest.json"
    prediction_path = bundle / "predictions.csv"
    label_path = bundle / "labels.csv"
    if not manifest_path.exists() or not prediction_path.exists():
        return {"eligible": False, "errors": ["manifest_or_predictions_missing"], "events": 0}
    manifest = read_json(manifest_path)
    for field in (
        "batch_id", "topic", "created_at_utc", "protocol_sha256",
        "model_run_sha256", "custodian_attestation_reference",
        "prediction_file_sha256", "minimum_events",
    ):
        if manifest.get(field) in (None, "", [], {}):
            errors.append(f"manifest_missing:{field}")
    lock = verify_lock(root)
    if not lock.get("valid") or manifest.get("protocol_sha256") != lock.get("protocol_sha256"):
        errors.append("protocol_binding_invalid")
    model_path = root / "reports" / "model_run.json"
    if not model_path.exists() or manifest.get("model_run_sha256") != sha256_file(model_path):
        errors.append("model_binding_invalid")
    if manifest.get("prediction_file_sha256") != sha256_file(prediction_path):
        errors.append("prediction_file_hash_mismatch")
    predictions = read_csv(prediction_path)
    fields = set(predictions[0]) if predictions else set()
    if fields != PREDICTION_FIELDS:
        errors.append(f"prediction_schema_mismatch:{sorted(fields)}")
    ids: list[str] = []
    unlock_by_id: dict[str, datetime] = {}
    for index, row in enumerate(predictions, 1):
        try:
            event_id = row["event_id"]
            ids.append(event_id)
            predicted = _time(row["predicted_at_utc"])
            unlock = _time(row["label_unlock_not_before_utc"])
            unlock_by_id[event_id] = unlock
            if predicted >= unlock:
                raise ValueError("prediction is not earlier than label unlock")
            probability = _number(row["chain_probability"], low=0.0, high=1.0, name="chain_probability")
            lower = _number(row["ci_lower"], low=0.0, high=1.0, name="ci_lower")
            upper = _number(row["ci_upper"], low=0.0, high=1.0, name="ci_upper")
            if not lower <= probability <= upper:
                raise ValueError("probability is outside CI")
            for hop in range(1, 4):
                _number(row[f"p_{hop}"], low=0.0, high=1.0, name=f"p_{hop}")
                if float(row[f"n_{hop}"]) <= 0:
                    raise ValueError(f"n_{hop} is not positive")
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"prediction_row_{index}:{exc}")
    if len(ids) != len(set(ids)):
        errors.append("duplicate_event_ids")
    minimum = int(manifest.get("minimum_events", 50) or 50)
    if minimum < 50 or len(ids) < minimum:
        errors.append(f"insufficient_events:{len(ids)}/{max(minimum, 50)}")
    existing_path = root / "data" / "frozen" / "events.csv"
    existing_ids = {row["event_id"] for row in read_csv(existing_path)} if existing_path.exists() else set()
    overlap = sorted(existing_ids & set(ids))
    if overlap:
        errors.append(f"overlaps_existing_confirmation:{len(overlap)}")

    labels_checked = 0
    if not unlocked and label_path.exists():
        errors.append("labels_present_before_declared_unlock")
    if unlocked:
        if not label_path.exists():
            errors.append("labels_missing_after_unlock")
        else:
            labels = read_csv(label_path)
            label_fields = set(labels[0]) if labels else set()
            if label_fields != LABEL_FIELDS:
                errors.append(f"label_schema_mismatch:{sorted(label_fields)}")
            label_ids: list[str] = []
            for index, row in enumerate(labels, 1):
                try:
                    event_id = row["event_id"]
                    label_ids.append(event_id)
                    if row["outcome"] not in {"0", "1"}:
                        raise ValueError("outcome must be 0 or 1")
                    available = _time(row["label_available_at_utc"])
                    if event_id not in unlock_by_id or available < unlock_by_id[event_id]:
                        raise ValueError("label availability violates prediction unlock boundary")
                except (KeyError, TypeError, ValueError) as exc:
                    errors.append(f"label_row_{index}:{exc}")
            if set(label_ids) != set(ids) or len(label_ids) != len(set(label_ids)):
                errors.append("label_prediction_event_set_mismatch")
            labels_checked = len(labels)
    return {
        "eligible": not errors,
        "mode": "post_unlock" if unlocked else "pre_unlock",
        "batch_id": manifest.get("batch_id"),
        "events": len(ids),
        "labels_checked": labels_checked,
        "overlap_with_existing": len(overlap),
        "errors": errors,
        "evidence_boundary": "predictions must precede per-event label unlock; existing confirmation event IDs are forbidden",
    }

