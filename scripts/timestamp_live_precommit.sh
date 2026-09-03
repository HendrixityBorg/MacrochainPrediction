#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

event_id="${1:-}"
if [[ ! "$event_id" =~ ^[A-Z0-9_]+$ ]]; then
  echo "usage: $0 EVENT_ID (uppercase letters, digits and underscores only)" >&2
  exit 2
fi

source_file="demo/precommitted/${event_id}.json"
target_dir="demo/timestamps/${event_id}"
if [[ ! -f "$source_file" ]]; then
  echo "missing precommit: $source_file" >&2
  exit 2
fi
mkdir -p "$target_dir"
if [[ -e "$target_dir/precommit.tsr" ]]; then
  echo "timestamp response already exists; overwrite refused" >&2
  exit 2
fi

openssl ts -query -data "$source_file" -sha256 -cert -out "$target_dir/precommit.tsq"
curl -L --fail --silent --show-error \
  -H 'Content-Type: application/timestamp-query' \
  --data-binary "@$target_dir/precommit.tsq" \
  http://timestamp.digicert.com \
  -o "$target_dir/precommit.tsr"
openssl ts -reply -in "$target_dir/precommit.tsr" -text > "$target_dir/precommit.tsr.txt"

PYTHONPATH=src .venv/bin/python - "$event_id" <<'PY'
from datetime import datetime, timezone
import sys
from pathlib import Path

from macro_gold_latent.io import sha256_file, write_json

event_id = sys.argv[1]
root = Path.cwd()
directory = root / "demo" / "timestamps" / event_id
paths = [
    root / "demo" / "precommitted" / f"{event_id}.json",
    directory / "precommit.tsq",
    directory / "precommit.tsr",
    directory / "precommit.tsr.txt",
]
write_json(directory / "manifest.json", {
    "event_id": event_id,
    "created_at_utc": datetime.now(timezone.utc).isoformat(),
    "timestamp_authority": "DigiCert RFC 3161",
    "files": {str(path.relative_to(root)): sha256_file(path) for path in paths},
})
PY

