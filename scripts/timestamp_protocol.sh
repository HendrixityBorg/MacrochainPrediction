#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p preregistration/timestamps
openssl ts -query -data preregistration/PROTOCOL_LOCK.json -sha256 -cert \
  -out preregistration/timestamps/PROTOCOL_LOCK.tsq
curl -L --fail --silent --show-error \
  -H 'Content-Type: application/timestamp-query' \
  --data-binary @preregistration/timestamps/PROTOCOL_LOCK.tsq \
  http://timestamp.digicert.com \
  -o preregistration/timestamps/PROTOCOL_LOCK.tsr
openssl ts -reply -in preregistration/timestamps/PROTOCOL_LOCK.tsr -text \
  > preregistration/timestamps/PROTOCOL_LOCK.tsr.txt

