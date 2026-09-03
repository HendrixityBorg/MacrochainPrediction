#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PYTHON="${MACRO_GOLD_PYTHON:-python3}"
if [[ -x .venv/bin/python ]]; then PYTHON=.venv/bin/python; fi
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHON" -m macro_gold_latent.cli run "$@"
