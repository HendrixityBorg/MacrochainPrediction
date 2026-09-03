#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PYTHON="${MACRO_GOLD_PYTHON:-python3}"
if [[ -x .venv/bin/python ]]; then PYTHON=.venv/bin/python; fi
PYTHONPATH=src "$PYTHON" -m unittest discover -s tests -v

