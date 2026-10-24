from __future__ import annotations

from pathlib import Path

import yaml

_PRICING = Path(__file__).with_name("pricing.yaml")
_cache: dict | None = None


def _load() -> dict:
    global _cache
    if _cache is None:
        _cache = yaml.safe_load(_PRICING.read_text(encoding="utf-8")) or {}
    return _cache


def price_for(model: str) -> tuple[float, float]:
    """USD per 1M (input, output) tokens. Longest matching prefix wins; unknown -> (0, 0)."""
    table = _load()
    best = ""
    for key in table:
        if model.startswith(key) and len(key) > len(best):
            best = key
    if not best:
        return 0.0, 0.0
    row = table[best]
    return float(row["input"]), float(row["output"])
