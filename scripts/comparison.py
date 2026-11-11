"""Comparable facts used by both the website and daily verification."""

import math


def differences(provider: str, model: dict, remote: dict, *, compare_prices: bool = True) -> list[list]:
    """Compare the same billing counters, not merely similarly named fields."""
    pairs = [["context", model.get("context_window"), remote.get("limit", {}).get("context")]]
    pricing = (model.get("pricing") or {}) if compare_prices else {}
    costs = dict(remote.get("cost", {}))
    # OpenRouter's Google write rate is the storage premium alone. RoomKit's
    # disjoint cache-write counter includes ordinary input plus this premium.
    # The originating catalogue documents this normalization; preserve it.
    if provider == "openrouter" and model["id"].startswith("google/"):
        premium, ordinary = costs.get("cache_write"), costs.get("input")
        costs["cache_write"] = premium + ordinary if premium is not None and ordinary is not None else None
    for local, foreign in (("input_per_million", "input"), ("output_per_million", "output"),
                           ("cache_read_per_million", "cache_read"),
                           ("cache_write_per_million", "cache_write")):
        pairs.append([local, pricing.get(local), costs.get(foreign)])
    # Currency conversions and storage premiums can be rounded by the source.
    return [[field, before, after] for field, before, after in pairs
            if before is not None and after is not None
            and not math.isclose(before, after, rel_tol=1e-6, abs_tol=1e-7)]
