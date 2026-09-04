from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any

from .config import ROOT, load_config
from .io import canonical_json, read_json, sha256_bytes, sha256_file, write_json
from .locking import verify_lock
from .stopping import break_even_probability


FORBIDDEN_PRESEAL_KEYS = {"policy_response", "real_rate_response", "gold_response", "outcome", "hop_outcomes"}
PRECOMMIT_INVARIANTS = (
    "event_id", "topic", "release_time_utc",
    "root_measure", "root_consensus_or_nowcast", "root_scale",
    "expectation_asof_utc", "scale_asof_utc", "pre_event_features",
    "source_records", "outcome_windows", "decision_rule", "tracking_due_utc",
)

CURRENT_DEMO_STATUSES = {
    "current_macro_demo_outcomes_unresolved",
    "current_macro_demo_outcomes_partially_resolved",
    "current_macro_demo_outcomes_resolved",
}


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _required(record: dict[str, Any], names: tuple[str, ...], *, context: str) -> None:
    missing = [key for key in names if record.get(key) in (None, "", [], {})]
    if missing:
        raise ValueError(f"{context} missing fields: {missing}")


def _timeline_field(record: dict[str, Any]) -> str:
    """Return the point before which a current-event prediction must be recorded."""
    if record.get("downstream_outcome_available_after_utc"):
        return "downstream_outcome_available_after_utc"
    raise ValueError("live precommit requires downstream_outcome_available_after_utc")


def _verify_local_sources(record: dict[str, Any], root: Path) -> None:
    for source in record["source_records"]:
        _required(source, ("source_id", "url", "retrieved_at_utc", "sha256"), context="source record")
        if _time(source["retrieved_at_utc"]) >= _time(record["release_time_utc"]):
            raise ValueError(f"source {source['source_id']} was not captured before release")
        local_path = source.get("local_path")
        if local_path:
            target = root / local_path
            if not target.exists() or sha256_file(target) != source["sha256"]:
                raise ValueError(f"source {source['source_id']} local hash mismatch")


def validate_decision_rule(record: dict[str, Any], config: dict[str, Any]) -> None:
    """Refuse a live record whose written rule differs from executable settings."""
    rule = record.get("decision_rule")
    if not isinstance(rule, dict):
        raise ValueError("live decision_rule must be an object")
    expected_threshold = break_even_probability(config)
    committed_threshold = float(rule.get("break_even_probability", float("nan")))
    if abs(committed_threshold - expected_threshold) > 1e-12:
        raise ValueError(
            "decision_rule break_even_probability differs from executable payoff formula: "
            f"committed={committed_threshold}, executable={expected_threshold}"
        )
    expected_width = float(config["stopping"]["maximum_interval_width"])
    committed_width = float(rule.get("maximum_ci_width", float("nan")))
    if abs(committed_width - expected_width) > 1e-12:
        raise ValueError(
            "decision_rule maximum_ci_width differs from executable stopping setting: "
            f"committed={committed_width}, executable={expected_width}"
        )


def precommit(
    input_path: Path, *, root: Path = ROOT, config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Commit all information knowable before the macro release.

    The release value is deliberately excluded.  This prevents a forecast,
    scale, window or trading rule from being selected after seeing the actual.
    """
    record = read_json(input_path)
    timeline_field = _timeline_field(record)
    invariants = (*PRECOMMIT_INVARIANTS, timeline_field)
    _required(record, invariants, context="live precommit")
    validate_decision_rule(record, config or load_config())
    if record.get("root_actual") not in (None, ""):
        raise ValueError("root_actual must be empty in the pre-release commitment")
    if "root_actual_source" in record:
        raise ValueError("root_actual_source is forbidden before release")
    if any(key in record for key in FORBIDDEN_PRESEAL_KEYS):
        raise ValueError("outcome/downstream fields are forbidden before precommit")
    now = _now()
    release = _time(record["release_time_utc"])
    deadline = _time(record[timeline_field])
    if now >= release:
        raise ValueError("macro release has occurred; retrospective precommit refused")
    if deadline <= release:
        raise ValueError("downstream outcome availability must be after the macro release")
    if _time(record["expectation_asof_utc"]) >= release or _time(record["scale_asof_utc"]) >= release:
        raise ValueError("expectation and scale must be fixed before the macro release")
    if float(record["root_scale"]) <= 0:
        raise ValueError("root_scale must be positive")
    _verify_local_sources(record, root)
    lock = verify_lock(root)
    if not lock.get("valid"):
        raise RuntimeError("valid protocol lock required")
    model_path = root / "reports" / "model_run.json"
    dataset_path = root / "data" / "frozen" / "events.csv"
    if not model_path.exists() or not dataset_path.exists():
        raise FileNotFoundError("model report and frozen dataset are required before precommit")
    target = root / "demo" / "precommitted" / f"{record['event_id']}.json"
    if target.exists():
        raise FileExistsError("precommitted record already exists and cannot be overwritten")
    payload = {
        "status": "precommitted_awaiting_release",
        "precommitted_at_utc": now.isoformat(),
        "protocol_sha256": lock["protocol_sha256"],
        "model_run_sha256": sha256_file(model_path),
        "frozen_dataset_sha256": sha256_file(dataset_path),
        "input": record,
    }
    payload["precommit_sha256"] = sha256_bytes(canonical_json(payload))
    write_json(target, payload)
    return payload


def verify_precommitted(path: Path, *, root: Path = ROOT) -> dict[str, Any]:
    payload = read_json(path)
    expected = payload.get("precommit_sha256")
    content = dict(payload)
    content.pop("precommit_sha256", None)
    hash_valid = expected == sha256_bytes(canonical_json(content))
    lock = verify_lock(root)
    model_path = root / "reports" / "model_run.json"
    dataset_path = root / "data" / "frozen" / "events.csv"
    bindings_valid = bool(
        lock.get("valid")
        and payload.get("protocol_sha256") == lock.get("protocol_sha256")
        and model_path.exists()
        and payload.get("model_run_sha256") == sha256_file(model_path)
        and dataset_path.exists()
        and payload.get("frozen_dataset_sha256") == sha256_file(dataset_path)
    )
    source_bindings_valid = True
    timeline_valid = False
    try:
        _verify_local_sources(payload["input"], root)
        timeline_valid = bool(
            _time(payload["precommitted_at_utc"]) < _time(payload["input"]["release_time_utc"])
            and _time(payload["input"]["expectation_asof_utc"]) < _time(payload["input"]["release_time_utc"])
            and _time(payload["input"]["scale_asof_utc"]) < _time(payload["input"]["release_time_utc"])
        )
    except (KeyError, TypeError, ValueError, FileNotFoundError):
        source_bindings_valid = False
    return {
        "valid": hash_valid and bindings_valid and source_bindings_valid and timeline_valid,
        "hash_valid": hash_valid,
        "bindings_valid": bindings_valid,
        "source_bindings_valid": source_bindings_valid,
        "timeline_valid": timeline_valid,
        "path": str(path),
        "precommit_sha256": expected,
        "status": payload.get("status"),
        "event_id": payload.get("input", {}).get("event_id"),
    }


def _git_blob(root: Path, oid: str) -> bytes:
    """Read immutable evidence from repository history without using its working-tree copy."""
    result = subprocess.run(
        ["git", "cat-file", "blob", oid], cwd=root, check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return result.stdout


def _git_commit_time(root: Path, commit: str) -> datetime:
    result = subprocess.run(
        ["git", "show", "-s", "--format=%cI", commit], cwd=root, check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    return _time(result.stdout.strip())


def _prediction_matches_prior_record(prediction: dict[str, Any], diagnostic: dict[str, Any]) -> bool:
    """Match the decision-relevant values that were already present in the cited commit."""
    scalar_pairs = (
        (prediction.get("intrinsic_probability"), diagnostic.get("intrinsic_probability")),
        (prediction.get("interruption_probability"), diagnostic.get("interruption_probability")),
        (prediction.get("chain_probability"), diagnostic.get("chain_probability")),
        (prediction.get("ci_lower"), (diagnostic.get("ci90") or [None, None])[0]),
        (prediction.get("ci_upper"), (diagnostic.get("ci90") or [None, None])[1]),
        (prediction.get("ci_width"), diagnostic.get("ci_width")),
    )
    try:
        scalars_match = all(abs(float(left) - float(right)) <= 1e-12 for left, right in scalar_pairs)
        vectors_match = all(
            len(prediction.get(key, [])) == len(diagnostic.get(key, []))
            and all(abs(float(left) - float(right)) <= 1e-12 for left, right in zip(prediction[key], diagnostic[key]))
            for key in ("p_i", "n_i")
        )
        predicted_stop = prediction["execution_stop"]
        recorded_stop = diagnostic["execution_stop"]
        stop_matches = (
            int(predicted_stop["hop"]) == int(recorded_stop["hop"])
            and predicted_stop["state"] == recorded_stop["state"]
            and predicted_stop["reason"] == recorded_stop["reason"]
        )
    except (KeyError, TypeError, ValueError):
        return False
    return scalars_match and vectors_match and stop_matches


def _recorded_prediction(document: dict[str, Any]) -> dict[str, Any]:
    """Find the prediction payload in either the compact snapshot or an older Git blob."""
    direct = document.get("recorded_prediction")
    if isinstance(direct, dict):
        return direct
    for value in document.values():
        if isinstance(value, dict) and {"p_i", "n_i", "chain_probability"}.issubset(value):
            return value
    raise ValueError("prediction evidence does not contain a recorded prediction")


def verify_current_demo(path: Path, *, root: Path = ROOT) -> dict[str, Any]:
    """Verify the order: commitment, released input, prediction, downstream labels."""
    payload = read_json(path)
    event_id = payload.get("event_id") or payload.get("input", {}).get("event_id")
    expected = payload.get("current_demo_sha256")
    content = dict(payload)
    content.pop("current_demo_sha256", None)
    hash_valid = expected == sha256_bytes(canonical_json(content))
    status_valid = payload.get("status") in CURRENT_DEMO_STATUSES
    forbidden_outcomes_absent = not any(
        key in payload or key in payload.get("input", {}) for key in FORBIDDEN_PRESEAL_KEYS
    )

    precommit_path = root / "demo" / "precommitted" / f"{event_id}.json"
    precommit = verify_precommitted(precommit_path, root=root) if precommit_path.exists() else {"valid": False}
    committed_payload = read_json(precommit_path) if precommit_path.exists() else {}
    precommit_binding_valid = bool(
        precommit.get("valid")
        and payload.get("precommit_sha256") == precommit.get("precommit_sha256")
    )
    artifact_bindings_valid = bool(
        precommit_binding_valid
        and payload.get("protocol_sha256") == committed_payload.get("protocol_sha256")
        and payload.get("model_run_sha256") == committed_payload.get("model_run_sha256")
        and payload.get("frozen_dataset_sha256") == committed_payload.get("frozen_dataset_sha256")
    )

    timeline_valid = False
    git_evidence_valid = False
    evidence_snapshot_valid = False
    actual_source_valid = False
    prediction_matches = False
    cited_commit_time = None
    try:
        release = _time(payload["release_time_utc"])
        recorded = _time(payload["prediction_recorded_at_utc"])
        downstream = _time(payload["downstream_outcome_available_after_utc"])
        source_retrieved = _time(payload["input"]["root_actual_source"]["retrieved_at_utc"])
        timeline_valid = release <= source_retrieved <= recorded < downstream

        actual_source = payload["input"]["root_actual_source"]
        actual_source_path = root / actual_source["local_path"]
        actual_source_valid = bool(
            actual_source_path.is_file()
            and sha256_file(actual_source_path) == actual_source["sha256"]
        )

        evidence = payload["prediction_evidence"]
        commit = evidence["git_commit"]
        snapshot_path = root / evidence["distributed_snapshot_path"]
        snapshot_bytes = snapshot_path.read_bytes()
        snapshot = json.loads(snapshot_bytes.decode("utf-8"))
        snapshot_prediction = _recorded_prediction(snapshot)
        prediction_matches = _prediction_matches_prior_record(payload["prediction"], snapshot_prediction)
        evidence_snapshot_valid = bool(
            sha256_bytes(snapshot_bytes) == evidence["distributed_snapshot_sha256"]
            and snapshot.get("event_id") == event_id
            and prediction_matches
        )
        try:
            prior_bytes = _git_blob(root, evidence["git_blob_oid"])
            cited_commit_time_value = _git_commit_time(root, commit)
            cited_commit_time = cited_commit_time_value.isoformat()
            prior = json.loads(prior_bytes.decode("utf-8"))
            git_evidence_valid = bool(
                sha256_bytes(prior_bytes) == evidence["sha256_at_commit"]
                and cited_commit_time_value == recorded
                and prior.get("event_id") == event_id
                and _prediction_matches_prior_record(payload["prediction"], _recorded_prediction(prior))
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Source archives and shallow clones may omit the older Git blob.
            # The compact distributed snapshot keeps the numeric check portable.
            cited_commit_time_value = _time(evidence["commit_time_utc"])
            cited_commit_time = cited_commit_time_value.isoformat()
    except (
        KeyError, TypeError, ValueError, json.JSONDecodeError,
        subprocess.CalledProcessError, UnicodeDecodeError, OSError,
    ):
        pass

    valid = bool(
        hash_valid and status_valid and forbidden_outcomes_absent
        and artifact_bindings_valid and timeline_valid
        and actual_source_valid and evidence_snapshot_valid and prediction_matches
    )
    return {
        "valid": valid,
        "path": str(path),
        "event_id": event_id,
        "status": payload.get("status"),
        "hash_valid": hash_valid,
        "precommit_valid": precommit.get("valid", False),
        "precommit_binding_valid": precommit_binding_valid,
        "artifact_bindings_valid": artifact_bindings_valid,
        "timeline_valid": timeline_valid,
        "actual_source_valid": actual_source_valid,
        "git_evidence_valid": git_evidence_valid,
        "evidence_snapshot_valid": evidence_snapshot_valid,
        "prediction_matches_prior_commit": prediction_matches,
        "forbidden_outcomes_absent": forbidden_outcomes_absent,
        "prediction_recorded_at_utc": payload.get("prediction_recorded_at_utc"),
        "downstream_outcome_available_after_utc": payload.get("downstream_outcome_available_after_utc"),
        "cited_commit_time_utc": cited_commit_time,
        "current_demo_sha256": expected,
    }


def live_demo_status(*, root: Path = ROOT) -> dict[str, Any]:
    precommit_directory = root / "demo" / "precommitted"
    precommit_files = sorted(precommit_directory.glob("*.json")) if precommit_directory.exists() else []
    precommit_checks = [verify_precommitted(path, root=root) for path in precommit_files]
    current_directory = root / "demo" / "current"
    current_files = sorted(current_directory.glob("*.json")) if current_directory.exists() else []
    current_checks = [verify_current_demo(path, root=root) for path in current_files]
    for item in precommit_checks + current_checks:
        item["eligible_for_submission"] = True
    valid_current = [
        item for item in current_checks
        if item["valid"] and item["status"] in CURRENT_DEMO_STATUSES
    ]
    return {
        "valid_pre_release_commitments": sum(item["valid"] for item in precommit_checks),
        "precommit_records": precommit_checks,
        "valid_current_macro_records": len(valid_current),
        "records": current_checks,
        "passes": len(valid_current) >= 1,
        "timeline_policy": "prediction is recorded after the macro release and before downstream outcomes become available",
    }
