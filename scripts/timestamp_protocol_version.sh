#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

protocol_id="$(PYTHONPATH=src .venv/bin/python - <<'PY'
from pathlib import Path
from macro_gold_latent.io import read_json
print(read_json(Path('preregistration/PROTOCOL_LOCK.json'))['protocol_sha256'])
PY
)"
target_dir="preregistration/timestamps/$protocol_id"
if [[ -e "$target_dir/PROTOCOL_LOCK.tsr" ]]; then
  echo "timestamp response already exists; overwrite refused" >&2
  exit 2
fi
mkdir -p "$target_dir"
openssl ts -query -data preregistration/PROTOCOL_LOCK.json -sha256 -cert \
  -out "$target_dir/PROTOCOL_LOCK.tsq"
curl -L --fail --silent --show-error \
  -H 'Content-Type: application/timestamp-query' \
  --data-binary "@$target_dir/PROTOCOL_LOCK.tsq" \
  http://timestamp.digicert.com \
  -o "$target_dir/PROTOCOL_LOCK.tsr"
openssl ts -reply -in "$target_dir/PROTOCOL_LOCK.tsr" -text > "$target_dir/PROTOCOL_LOCK.tsr.txt"

PYTHONPATH=src .venv/bin/python - "$protocol_id" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import sys
from macro_gold_latent.io import sha256_file, write_json

root = Path.cwd()
protocol_id = sys.argv[1]
directory = root / 'preregistration' / 'timestamps' / protocol_id
paths = [
    root / 'preregistration' / 'PROTOCOL_LOCK.json',
    directory / 'PROTOCOL_LOCK.tsq',
    directory / 'PROTOCOL_LOCK.tsr',
    directory / 'PROTOCOL_LOCK.tsr.txt',
]
write_json(directory / 'manifest.json', {
    'protocol_sha256': protocol_id,
    'created_at_utc': datetime.now(timezone.utc).isoformat(),
    'timestamp_authority': 'DigiCert RFC 3161',
    'files': {str(path.relative_to(root)): sha256_file(path) for path in paths},
})
PY
