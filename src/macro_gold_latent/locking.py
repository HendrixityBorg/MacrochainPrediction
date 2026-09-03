from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any

from .config import ROOT
from .io import canonical_json, read_json, sha256_file, write_json


LOCK_INPUTS = [
    "config/default.json",
    "preregistration/CONFIRMATION_PROTOCOL.zh-CN.md",
    "preregistration/S_GRADE_MATRIX.json",
    "src/macro_gold_latent/data.py",
    "src/macro_gold_latent/latent.py",
    "src/macro_gold_latent/model.py",
    "src/macro_gold_latent/stopping.py",
    "src/macro_gold_latent/evaluate.py",
    "src/macro_gold_latent/oracle.py",
    "src/macro_gold_latent/gates.py",
]


def protocol_digest(root: Path = ROOT) -> tuple[str, list[dict[str, str]]]:
    files = []
    for relative in LOCK_INPUTS:
        path = root / relative
        if not path.exists():
            raise FileNotFoundError(f"protocol input missing: {relative}")
        files.append({"path": relative, "sha256": sha256_file(path)})
    digest = hashlib.sha256(canonical_json(files)).hexdigest()
    return digest, files


def freeze(root: Path = ROOT) -> dict[str, Any]:
    target = root / "preregistration" / "PROTOCOL_LOCK.json"
    digest, files = protocol_digest(root)
    if target.exists():
        existing = read_json(target)
        if existing.get("protocol_sha256") != digest:
            raise RuntimeError("protocol is already frozen and current inputs differ; create a new version instead")
        return existing
    payload = {
        "status": "frozen_before_confirmation_label_generation",
        "protocol_sha256": digest,
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "files": files,
        "external_timestamp": None,
        "warning": "Local timestamp proves immutability within this artifact, not third-party custody. Add RFC3161/Git attestation before submission.",
    }
    write_json(target, payload)
    return payload


def freeze_amendment(
    amendment_file: str, root: Path = ROOT, *, requires_independent_acceptance: bool | None = None,
) -> dict[str, Any]:
    amendment_path = root / amendment_file
    if not amendment_path.exists():
        raise FileNotFoundError(amendment_file)
    target = root / "preregistration" / "PROTOCOL_LOCK.json"
    if not target.exists():
        raise RuntimeError("base protocol lock missing")
    previous = read_json(target)
    history = root / "preregistration" / "lock_history"
    archive = history / f"PROTOCOL_LOCK.{previous.get('protocol_sha256', 'missing')}.json"
    if archive.exists() and read_json(archive) != previous:
        raise RuntimeError("protocol lock history archive is inconsistent")
    if not archive.exists():
        write_json(archive, previous)
    digest, files = protocol_digest(root)
    if previous.get("protocol_sha256") == digest:
        raise RuntimeError("amendment requested but locked inputs did not change")
    chain = list(previous.get("amendment_chain", []))
    if not chain and previous.get("amendment_file"):
        chain.append({
            "amendment_file": previous["amendment_file"],
            "amendment_sha256": previous.get("amendment_sha256"),
            "frozen_at_utc": previous.get("frozen_at_utc"),
        })
    chain.append({
        "amendment_file": amendment_file,
        "amendment_sha256": sha256_file(amendment_path),
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
    })
    payload = {
        "status": "frozen_protocol_amendment_chain",
        "protocol_sha256": digest,
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "previous_protocol_sha256": previous.get("protocol_sha256"),
        "previous_frozen_at_utc": previous.get("frozen_at_utc"),
        "base_protocol_sha256": previous.get("base_protocol_sha256", previous.get("previous_protocol_sha256", previous.get("protocol_sha256"))),
        "amendment_file": amendment_file,
        "amendment_sha256": sha256_file(amendment_path),
        "amendment_chain": chain,
        "files": files,
        "external_timestamp": None,
        "requires_independent_acceptance": (
            bool(previous.get("requires_independent_acceptance", False))
            if requires_independent_acceptance is None else bool(requires_independent_acceptance)
        ),
        "warning": "This is a chained amendment. Historical model/label changes remain immutable and disclosed; no participant-defined external signature is required. Live-demo amendments must be frozen before the live outcome.",
    }
    write_json(target, payload)
    return payload


def verify_lock(root: Path = ROOT) -> dict[str, Any]:
    target = root / "preregistration" / "PROTOCOL_LOCK.json"
    if not target.exists():
        return {"valid": False, "reason": "protocol_lock_missing"}
    existing = read_json(target)
    digest, files = protocol_digest(root)
    return {
        "valid": existing.get("protocol_sha256") == digest,
        "reason": "ok" if existing.get("protocol_sha256") == digest else "locked_inputs_changed",
        "protocol_sha256": existing.get("protocol_sha256"),
        "current_sha256": digest,
        "files": files,
        "frozen_at_utc": existing.get("frozen_at_utc"),
    }
