#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess

from macro_gold_latent.demo import verify_precommitted
from macro_gold_latent.io import read_json, sha256_file


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("event_id")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Z0-9_]+", args.event_id):
        raise SystemExit("invalid event_id")
    directory = ROOT / "demo" / "timestamps" / args.event_id
    manifest_path = directory / "manifest.json"
    if not manifest_path.exists():
        print(json.dumps({"valid": False, "reason": "timestamp_manifest_missing"}, indent=2))
        return 1
    manifest = read_json(manifest_path)
    errors: list[str] = []
    for relative, expected in manifest["files"].items():
        path = ROOT / relative
        if not path.exists():
            errors.append(f"missing:{relative}")
        elif sha256_file(path) != expected:
            errors.append(f"hash_mismatch:{relative}")
    precommit_path = ROOT / "demo" / "precommitted" / f"{args.event_id}.json"
    precommit = verify_precommitted(precommit_path)
    if not precommit["valid"]:
        errors.append("precommit_binding_invalid")
    command = [
        "openssl", "ts", "-verify", "-data", f"demo/precommitted/{args.event_id}.json",
        "-in", f"demo/timestamps/{args.event_id}/precommit.tsr",
        "-CAfile", "preregistration/timestamps/digicert_root_g4.cer",
        "-untrusted", "preregistration/timestamps/digicert_tsa_intermediate.pem",
        "-partial_chain",
    ]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0 or "Verification: OK" not in result.stdout + result.stderr:
        errors.append("openssl_verification_failed")
    output = {
        "valid": not errors,
        "event_id": args.event_id,
        "precommit_sha256": precommit.get("precommit_sha256"),
        "manifest_created_at_utc": manifest.get("created_at_utc"),
        "errors": errors,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
