from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .config import ROOT, load_config
from .io import canonical_json, read_json, sha256_bytes, sha256_file, write_json
from .locking import verify_lock
from .stopping import break_even_probability


FORBIDDEN_PRESEAL_KEYS = {"policy_response", "real_rate_response", "gold_response", "outcome", "hop_outcomes"}
PRECOMMIT_INVARIANTS = (
    "event_id", "topic", "release_time_utc", "seal_deadline_utc",
    "root_measure", "root_consensus_or_nowcast", "root_scale",
    "expectation_asof_utc", "scale_asof_utc", "pre_event_features",
    "source_records", "outcome_windows", "decision_rule", "tracking_due_utc",
)


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
    _required(record, PRECOMMIT_INVARIANTS, context="live precommit")
    validate_decision_rule(record, config or load_config())
    if record.get("root_actual") not in (None, ""):
        raise ValueError("root_actual must be empty in the pre-release commitment")
    if "root_actual_source" in record:
        raise ValueError("root_actual_source is forbidden before release")
    if any(key in record for key in FORBIDDEN_PRESEAL_KEYS):
        raise ValueError("outcome/downstream fields are forbidden before precommit")
    now = _now()
    release = _time(record["release_time_utc"])
    deadline = _time(record["seal_deadline_utc"])
    if now >= release:
        raise ValueError("macro release has occurred; retrospective precommit refused")
    if deadline <= release:
        raise ValueError("seal deadline must be after the macro release")
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


def seal(input_path: Path, prediction: dict[str, Any], *, root: Path = ROOT) -> dict[str, Any]:
    record = read_json(input_path)
    _required(record, ("event_id", "topic", "release_time_utc", "seal_deadline_utc", "root_actual"), context="live input")
    if any(key in record for key in FORBIDDEN_PRESEAL_KEYS):
        raise ValueError("outcome/downstream fields are forbidden before sealing")
    now = _now()
    deadline = _time(record["seal_deadline_utc"])
    release = _time(record["release_time_utc"])
    if now >= deadline:
        raise ValueError("seal deadline has passed; retrospective demo refused")
    if now < release:
        raise ValueError("macro release has not occurred; root actual cannot be sealed yet")
    if deadline <= release:
        raise ValueError("seal deadline must be after the macro release and before the market outcome window")
    _required(
        record,
        (*PRECOMMIT_INVARIANTS, "root_actual_source"),
        context="live input",
    )
    precommit_path = root / "demo" / "precommitted" / f"{record['event_id']}.json"
    if not precommit_path.exists():
        raise FileNotFoundError("matching pre-release commitment is required")
    precommit_check = verify_precommitted(precommit_path, root=root)
    if not precommit_check["valid"]:
        raise RuntimeError("pre-release commitment failed verification")
    committed = read_json(precommit_path)["input"]
    changed = [key for key in PRECOMMIT_INVARIANTS if canonical_json(record[key]) != canonical_json(committed[key])]
    if changed:
        raise ValueError(f"post-release input changed precommitted fields: {changed}")
    _required(record["root_actual_source"], ("source_id", "url", "retrieved_at_utc", "sha256"), context="root actual source")
    actual_source_time = _time(record["root_actual_source"]["retrieved_at_utc"])
    if actual_source_time < release or actual_source_time >= deadline:
        raise ValueError("root actual source must be captured between release and seal deadline")
    actual_local_path = record["root_actual_source"].get("local_path")
    if actual_local_path:
        actual_target = root / actual_local_path
        if not actual_target.exists() or sha256_file(actual_target) != record["root_actual_source"]["sha256"]:
            raise ValueError("root actual source local hash mismatch")
    lock = verify_lock(root)
    if not lock.get("valid"):
        raise RuntimeError("valid protocol lock required")
    target = root / "demo" / "sealed" / f"{record['event_id']}.json"
    if target.exists():
        raise FileExistsError("sealed record already exists and cannot be overwritten")
    payload = {
        "status": "sealed_outcome_unresolved", "sealed_at_utc": now.isoformat(),
        "protocol_sha256": lock["protocol_sha256"],
        "precommit_sha256": precommit_check["precommit_sha256"],
        "input": record, "prediction": prediction,
    }
    payload["seal_sha256"] = sha256_bytes(canonical_json(payload))
    write_json(target, payload)
    return payload


def prepare_seal_input(
    *, event_id: str, root_actual: float, actual_source_path: Path,
    actual_source_url: str, output_path: Path, root: Path = ROOT,
) -> dict[str, Any]:
    """Build the only permitted post-release input without manual JSON copying."""
    precommit_path = root / "demo" / "precommitted" / f"{event_id}.json"
    if not precommit_path.exists():
        raise FileNotFoundError("matching pre-release commitment is required")
    check = verify_precommitted(precommit_path, root=root)
    if not check["valid"]:
        raise RuntimeError("pre-release commitment failed verification")
    payload = read_json(precommit_path)
    record = copy.deepcopy(payload["input"])
    now = _now()
    release = _time(record["release_time_utc"])
    deadline = _time(record["seal_deadline_utc"])
    if now < release or now >= deadline:
        raise ValueError("seal input can only be prepared inside the committed release window")
    source = actual_source_path.resolve()
    project = root.resolve()
    try:
        relative_source = source.relative_to(project)
    except ValueError as exc:
        raise ValueError("root actual source must be stored inside the project") from exc
    if not source.is_file():
        raise FileNotFoundError("root actual source snapshot is missing")
    source_modified = datetime.fromtimestamp(source.stat().st_mtime, tz=timezone.utc)
    if source_modified < release or source_modified >= deadline:
        raise ValueError("root actual source file must be created inside the committed release window")
    if output_path.exists():
        raise FileExistsError("prepared seal input already exists and cannot be overwritten")
    record["root_actual"] = float(root_actual)
    record["root_actual_source"] = {
        "source_id": "bls_employment_situation_first_release_actual",
        "url": actual_source_url,
        "retrieved_at_utc": now.isoformat(),
        "local_path": str(relative_source),
        "sha256": sha256_file(source),
    }
    write_json(output_path, record)
    return {
        "event_id": event_id,
        "output_path": str(output_path),
        "root_actual": float(root_actual),
        "root_z": (float(root_actual) - float(record["root_consensus_or_nowcast"])) / float(record["root_scale"]),
        "actual_source_sha256": record["root_actual_source"]["sha256"],
        "precommit_sha256": check["precommit_sha256"],
    }


def verify_sealed(path: Path, *, root: Path = ROOT) -> dict[str, Any]:
    payload = read_json(path)
    expected = payload.get("seal_sha256")
    content = dict(payload)
    content.pop("seal_sha256", None)
    record = payload.get("input", {})
    event_id = record.get("event_id")
    precommit_path = root / "demo" / "precommitted" / f"{event_id}.json"
    precommit = verify_precommitted(precommit_path, root=root) if precommit_path.exists() else {"valid": False}
    timeline_valid = False
    try:
        sealed = _time(payload["sealed_at_utc"])
        timeline_valid = _time(record["release_time_utc"]) <= sealed < _time(record["seal_deadline_utc"])
    except (KeyError, TypeError, ValueError):
        pass
    valid = bool(
        expected == sha256_bytes(canonical_json(content))
        and precommit.get("valid")
        and payload.get("precommit_sha256") == precommit.get("precommit_sha256")
        and timeline_valid
    )
    return {
        "valid": valid, "path": str(path), "seal_sha256": expected,
        "precommit_sha256": payload.get("precommit_sha256"),
        "precommit_valid": precommit.get("valid", False),
        "timeline_valid": timeline_valid,
        "status": payload.get("status"), "event_id": event_id,
    }


def live_demo_status(*, root: Path = ROOT) -> dict[str, Any]:
    withdrawal_directory = root / "demo" / "withdrawals"
    withdrawal_files = sorted(withdrawal_directory.glob("*.json")) if withdrawal_directory.exists() else []
    withdrawals = {
        item.get("event_id") for item in (read_json(path) for path in withdrawal_files)
        if item.get("status") == "WITHDRAWN_NOT_USED_FOR_SUBMISSION"
    }
    precommit_directory = root / "demo" / "precommitted"
    precommit_files = sorted(precommit_directory.glob("*.json")) if precommit_directory.exists() else []
    precommit_checks = [verify_precommitted(path, root=root) for path in precommit_files]
    directory = root / "demo" / "sealed"
    files = sorted(directory.glob("*.json")) if directory.exists() else []
    checks = [verify_sealed(path, root=root) for path in files]
    for item in precommit_checks + checks:
        item["eligible_for_submission"] = item.get("event_id") not in withdrawals
    valid = [
        item for item in checks
        if item["valid"] and item["status"] == "sealed_outcome_unresolved" and item["eligible_for_submission"]
    ]
    return {
        "valid_pre_release_commitments": sum(item["valid"] and item["eligible_for_submission"] for item in precommit_checks),
        "all_valid_pre_release_commitments_including_withdrawn": sum(item["valid"] for item in precommit_checks),
        "withdrawn_event_ids": sorted(item for item in withdrawals if item),
        "precommit_records": precommit_checks,
        "valid_prospective_seals": len(valid), "records": checks, "passes": len(valid) >= 1,
    }
