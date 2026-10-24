"""Load KEY=value lines from local env files into os.environ (never committed).

Looks for `.env` and `api_key.env` in the repo root. Lines that are not a plain
`NAME=value` (comments, shell snippets) are ignored. Existing environment
variables win over file values.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def load_env(files: tuple[str, ...] = (".env", "api_key.env")) -> list[str]:
    loaded: list[str] = []
    for name in files:
        path = ROOT / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            m = _LINE.match(line)
            if not m or line.lstrip().startswith("#"):
                continue
            key, value = m.group(1), m.group(2).strip().strip('"').strip("'")
            if key not in os.environ and value:
                os.environ[key] = value
                loaded.append(key)
    return loaded
