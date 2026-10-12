"""STEP 15 - Anomaly detection: find movements that are statistically UNUSUAL.

Two detectors, both explainable with one formula:
  * daily  : robust z-score of a day's revenue against the previous 28 days  (median / MAD, not mean / std,
             so one huge day does not hide the next one)
  * member : z-score of this month's MoM change of a Region/Category/... against that member's own history

An anomaly is a flag to INVESTIGATE, not proof of a problem.
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from src.kpi_calculation import to_period

MAX_MEMBERS = 30     # only low-cardinality dimensions (Region, Category...), not 1,800 product names


def detect_daily_anomalies(df: pd.DataFrame, period, window: int = 28, z_threshold: float = 3.5,
                           max_items: int = 3) -> List[Dict]:
    period = to_period(period)
    daily = df.groupby("Date")["Sales"].sum().sort_index()
    if len(daily) < window // 2 + 5:
        return []
    mad_fn = lambda x: np.median(np.abs(x - np.median(x)))          # noqa: E731
    expected = daily.rolling(window, min_periods=14).median().shift(1)
    mad = daily.rolling(window, min_periods=14).apply(mad_fn, raw=True).shift(1)
    z = 0.6745 * (daily - expected) / mad.where(mad > 0)
    out = []
    for day, value in daily.items():
        if day.to_period("M") != period or pd.isna(z.get(day)) or abs(z[day]) < z_threshold:
            continue
        out.append({"date": day.strftime("%Y-%m-%d"), "revenue": float(value), "expected": float(expected[day]),
                    "robust_z": round(float(z[day]), 1), "direction": "spike" if z[day] > 0 else "drop"})
    return sorted(out, key=lambda r: -abs(r["robust_z"]))[:max_items]


def detect_member_anomalies(df: pd.DataFrame, dimension: str, period, min_history: int = 6,
                            z_threshold: float = 2.0, min_move_pct: float = 5.0) -> List[Dict]:
    period = to_period(period)
    if dimension not in df.columns or not 2 <= df[dimension].nunique() <= MAX_MEMBERS:
        return []
    monthly = (df.assign(Month=df["Date"].dt.to_period("M"))
                 .pivot_table(index="Month", columns=dimension, values="Sales", aggfunc="sum").fillna(0.0))
    monthly = monthly.reindex(pd.period_range(monthly.index.min(), monthly.index.max(), freq="M"), fill_value=0.0)
    if period not in monthly.index:
        return []
    out = []
    for member in monthly.columns:
        s = monthly[member]
        mom = (s.pct_change() * 100).replace([np.inf, -np.inf], np.nan)
        history = mom.loc[:period - 1].dropna()
        if len(history) < min_history or pd.isna(mom.get(period)):
            continue
        std = float(history.std(ddof=1))
        if std <= 0:
            continue
        z = (float(mom[period]) - float(history.mean())) / std
        if abs(z) >= z_threshold and abs(mom[period]) >= min_move_pct:
            out.append({"dimension": dimension, "name": str(member), "mom_pct": round(float(mom[period]), 1),
                        "typical_mom_pct": round(float(history.mean()), 1), "z_score": round(float(z), 1),
                        "direction": "spike" if z > 0 else "drop"})
    return sorted(out, key=lambda r: -abs(r["z_score"]))


def detect_anomalies(df: pd.DataFrame, period, dimensions=("Region", "Product_Category", "Sub_Category",
                                                           "Customer_Segment", "Sales_Channel", "Payment_Method")) -> Dict:
    members: List[Dict] = []
    for d in dimensions:
        members += detect_member_anomalies(df, d, period)
    members = sorted(members, key=lambda r: -abs(r["z_score"]))[:5]
    return {"daily": detect_daily_anomalies(df, period), "members": members}
