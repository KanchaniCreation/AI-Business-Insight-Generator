"""STEP 5 - Trend analysis: compare periods and classify direction/strength."""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.exceptions import DataValidationError
from src.kpi_calculation import to_period
from src.utils import growth_pct

# Public, well-named alias: growth = ((current - previous) / previous) * 100
calculate_growth_pct = growth_pct


def classify_change(growth: Optional[float], stable_band_pct: float = 2.0,
                    strong_pct: float = 10.0) -> str:
    """Label one period-over-period change.

    |g| <= 2%  -> stable ; 2-10% -> increase/decrease ; >= 10% -> strong_*
    None (previous was 0) -> 'new' (growth cannot be computed from zero).
    """
    if growth is None:
        return "new"
    if abs(growth) <= stable_band_pct:
        return "stable"
    if growth > 0:
        return "strong_increase" if growth >= strong_pct else "increase"
    return "strong_decrease" if growth <= -strong_pct else "decrease"


def classify_series_trend(values, window: int = 6, flat_slope_pct: float = 1.0) -> Dict:
    """Direction of a time series using a straight-line fit over the last `window` points.

    slope_pct_per_month = (slope of the fitted line) / (average value) * 100.
    A slope within +/-1% of the average per month counts as 'stable'.
    """
    vals = np.array([v for v in list(values)[-window:] if v is not None and not pd.isna(v)], dtype=float)
    if len(vals) < 3 or vals.mean() == 0:
        return {"direction": "insufficient_data", "slope_pct_per_month": None, "months_used": len(vals)}
    slope = np.polyfit(np.arange(len(vals)), vals, 1)[0]
    slope_pct = float(slope / vals.mean() * 100)
    direction = "stable" if abs(slope_pct) <= flat_slope_pct else ("increasing" if slope_pct > 0 else "declining")
    return {"direction": direction, "slope_pct_per_month": round(slope_pct, 2), "months_used": int(len(vals))}


def detect_significant_changes(monthly: pd.DataFrame, column: str = "Revenue_MoM_Pct",
                               threshold_pct: float = 10.0) -> List[Dict]:
    """Months where the MoM move was at least +/- threshold."""
    hits = monthly[monthly[column].abs() >= threshold_pct]
    return [{"month": str(r["Month"]), "mom_pct": round(float(r[column]), 1)} for _, r in hits.iterrows()]


def analyze_trends(monthly: pd.DataFrame, window: int = 6) -> Dict:
    """Trend summary for revenue, profit and orders (uses the monthly_summary table)."""
    result: Dict = {}
    for metric in ["Revenue", "Profit", "Orders"]:
        info = classify_series_trend(monthly[metric].tolist(), window=window)
        last = monthly.iloc[-1]
        mom = last[f"{metric}_MoM_Pct"]
        yoy = last[f"{metric}_YoY_Pct"]
        info.update({
            "latest_mom_pct": None if pd.isna(mom) else round(float(mom), 1),
            "latest_mom_label": classify_change(None if pd.isna(mom) else float(mom)),
            "latest_yoy_pct": None if pd.isna(yoy) else round(float(yoy), 1),
        })
        result[metric.lower()] = info
    best = monthly.loc[monthly["Revenue"].idxmax()]
    worst = monthly.loc[monthly["Revenue"].idxmin()]
    result["best_revenue_month"] = str(best["Month"])
    result["lowest_revenue_month"] = str(worst["Month"])
    result["significant_revenue_changes"] = detect_significant_changes(monthly)[-3:]
    return result


# ------------------------------------------------------------ choosing periods
def resolve_periods(df: pd.DataFrame, period=None) -> Tuple[pd.Period, pd.Period]:
    """Return (current_month, previous_month). Default = latest month in the data."""
    months = df["Date"].dt.to_period("M").unique()
    if len(months) < 2:
        raise DataValidationError("At least two months of data are needed to compare periods.")
    current = to_period(period) if period is not None else max(months)
    if current not in set(months):
        raise DataValidationError(f"No data found for {current}.")
    previous = current - 1
    if previous not in set(months):
        raise DataValidationError(f"No data for the previous month ({previous}); cannot compare.")
    return current, previous


def is_partial_month(df: pd.DataFrame, period) -> bool:
    """True if the LAST month in the data stops before its final day (incomplete month)."""
    period = to_period(period)
    in_month = df[df["Date"].dt.to_period("M") == period]["Date"]
    latest_overall = df["Date"].dt.to_period("M").max()
    if period != latest_overall or in_month.empty:
        return False
    return in_month.max().day < period.days_in_month
