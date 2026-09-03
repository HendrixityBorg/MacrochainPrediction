from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path else ROOT / "config" / "default.json"
    return json.loads(target.read_text(encoding="utf-8"))


def project_path(*parts: str) -> Path:
    return ROOT.joinpath(*parts)

