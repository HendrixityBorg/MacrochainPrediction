#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import subprocess

from macro_gold_latent.io import read_json, sha256_file


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    lock = read_json(ROOT / "preregistration/PROTOCOL_LOCK.json")
    version_directory = ROOT / "preregistration" / "timestamps" / lock["protocol_sha256"]
    manifest_path = version_directory / "manifest.json"
    legacy = False
    if not manifest_path.exists():
        manifest_path = ROOT / "preregistration/timestamps/manifest.json"
        legacy = True
    if not manifest_path.exists():
        print(json.dumps({"valid": False, "reason": "timestamp_manifest_missing"}, indent=2))
        return 1
    manifest = read_json(manifest_path)
    errors = []
    for relative, expected in manifest["files"].items():
        path = ROOT / relative
        if not path.exists():
            errors.append(f"missing:{relative}")
        elif sha256_file(path) != expected:
            errors.append(f"hash_mismatch:{relative}")
    response_path = "preregistration/timestamps/PROTOCOL_LOCK.tsr" if legacy else str(
        (version_directory / "PROTOCOL_LOCK.tsr").relative_to(ROOT)
    )
    command = [
        "openssl", "ts", "-verify", "-data", "preregistration/PROTOCOL_LOCK.json",
        "-in", response_path,
        "-CAfile", "preregistration/timestamps/digicert_root_g4.cer",
        "-untrusted", "preregistration/timestamps/digicert_tsa_intermediate.pem", "-partial_chain",
    ]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0 or "Verification: OK" not in result.stdout + result.stderr:
        errors.append("openssl_verification_failed")
    output = {
        "valid": not errors,
        "protocol_sha256": lock["protocol_sha256"],
        "timestamp_utc": manifest.get("timestamp_utc", manifest.get("created_at_utc")),
        "errors": errors,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
