"""STEP 6 - Driver analysis: WHY did revenue move?

Idea: total change = sum of every member's change. So we rank each Region / Product /
Category by its rupee contribution to the overall change. A tiny region growing 80%
can matter less than a big region growing 8% - ranking by contribution captures that.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

import pandas as pd

from src.config import DRIVER_DIMENSIONS
from src.kpi_calculation import dimension_growth


def _clean(record: Dict) -> Dict:
    """Round floats and turn NaN into None (pandas silently turns None into NaN; NaN is not valid JSON)."""
    out = {}
    for k, v in record.items():
        if isinstance(v, float):
            out[k] = None if math.isnan(v) else round(v, 2)
        else:
            out[k] = v
    return out


def analyze_dimension(current: pd.DataFrame, previous: pd.DataFrame, dimension: str,
                      top_n: int = 3, min_share_pct: float = 2.0, metric: str = "Sales") -> Dict:
    table = dimension_growth(current, previous, dimension, metric)
    # ignore tiny members (noise): they must be >= min_share_pct of either period
    material = table[(table["share_of_current_pct"] >= min_share_pct) | (table["share_of_previous_pct"] >= min_share_pct)]
    positive = material[material["change"] > 0].sort_values("change", ascending=False).head(top_n)
    negative = material[material["change"] < 0].sort_values("change", ascending=True).head(top_n)
    rated = material[material["growth_pct"].notna()]
    fastest = rated.sort_values("growth_pct", ascending=False).head(1)
    return {
        "dimension": dimension,
        "total_change": round(float(table["change"].sum()), 2),
        "top_positive": [_clean(r) for r in positive.to_dict("records")],
        "top_negative": [_clean(r) for r in negative.to_dict("records")],
        "fastest_growing": _clean(fastest.iloc[0].to_dict()) if len(fastest) else None,
        "all_members": [_clean(r) for r in table.to_dict("records")],
    }


def analyze_drivers(current: pd.DataFrame, previous: pd.DataFrame,
                    dimensions: Optional[List[str]] = None, top_n: int = 3,
                    min_share_pct: float = 2.0) -> Dict[str, Dict]:
    """Run driver analysis for every available dimension (skips missing columns)."""
    dims = dimensions or DRIVER_DIMENSIONS
    out = {}
    for d in dims:
        if d not in current.columns or d not in previous.columns:
            continue
        members = set(current[d].unique()) | set(previous[d].unique())
        if len(members - {"Unknown", "UNKNOWN"}) < 2:      # nothing to compare (column absent or constant)
            continue
        out[d] = analyze_dimension(current, previous, d, top_n, min_share_pct)
    return out
