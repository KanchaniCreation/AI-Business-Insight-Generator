"""STEP 4 - KPI engine: small, reusable, testable functions.

Golden rule: every function takes a DataFrame (already cleaned) and returns plain
Python numbers / DataFrames. No printing, no file reading, no globals.
"""
from __future__ import annotations

from typing import Dict, Optional, Union

import numpy as np
import pandas as pd

from src.utils import growth_pct, safe_divide

PeriodLike = Union[str, pd.Period]


# ------------------------------------------------------------ period helpers
def to_period(value: PeriodLike) -> pd.Period:
    return value if isinstance(value, pd.Period) else pd.Period(str(value), freq="M")


def filter_month(df: pd.DataFrame, period: PeriodLike) -> pd.DataFrame:
    """Rows that belong to one calendar month, e.g. filter_month(df, '2026-09')."""
    return df[df["Date"].dt.to_period("M") == to_period(period)]


# ------------------------------------------------------------ core KPIs
def calculate_kpis(df: pd.DataFrame) -> Dict[str, float]:
    """Headline KPIs for any slice of data (whole file, one month, one region...)."""
    revenue = float(df["Sales"].sum())
    cost = float(df["Cost"].sum())
    profit = float(df["Profit"].sum())
    orders = int(df["Order_ID"].nunique())
    # 'UNKNOWN' customers (missing IDs) must not be counted as one fake customer
    customers = int(df.loc[df["Customer_ID"] != "UNKNOWN", "Customer_ID"].nunique())
    gross = float((df["Sales"] / (1 - df["Discount"].clip(upper=0.99))).sum())  # price before discount
    return {
        "total_revenue": revenue,
        "total_cost": cost,
        "total_profit": profit,
        "profit_margin_pct": safe_divide(profit, revenue) * 100,
        "total_orders": orders,
        "total_quantity": int(df["Quantity"].sum()),
        "total_customers": customers,
        "average_order_value": safe_divide(revenue, orders),
        "effective_discount_pct": safe_divide(gross - revenue, gross) * 100,
    }


def compare_kpis(current: pd.DataFrame, previous: pd.DataFrame) -> Dict[str, Dict]:
    """Current vs previous period: each KPI gets current, previous, change, growth_pct."""
    cur, prev = calculate_kpis(current), calculate_kpis(previous)
    result: Dict[str, Dict] = {}
    for key in ["total_revenue", "total_cost", "total_profit", "total_orders",
                "total_quantity", "total_customers", "average_order_value"]:
        result[key] = {
            "current": cur[key], "previous": prev[key],
            "change": cur[key] - prev[key], "growth_pct": growth_pct(cur[key], prev[key]),
        }
    # percentages are compared in percentage POINTS (pp), not growth of a percentage
    for key in ["profit_margin_pct", "effective_discount_pct"]:
        result[key] = {"current": cur[key], "previous": prev[key], "change_pp": cur[key] - prev[key]}
    return result


# ------------------------------------------------------------ monthly view
def monthly_summary(df: pd.DataFrame) -> pd.DataFrame:
    """One row per month with KPIs plus MoM and YoY growth columns."""
    g = df.assign(Month=df["Date"].dt.to_period("M")).groupby("Month")
    out = pd.DataFrame({
        "Revenue": g["Sales"].sum(),
        "Cost": g["Cost"].sum(),
        "Profit": g["Profit"].sum(),
        "Orders": g["Order_ID"].nunique(),
        "Quantity": g["Quantity"].sum(),
        "Customers": g["Customer_ID"].nunique(),
    })
    out["Profit_Margin_Pct"] = [safe_divide(p, r) * 100 for p, r in zip(out["Profit"], out["Revenue"])]
    out["AOV"] = [safe_divide(r, o) for r, o in zip(out["Revenue"], out["Orders"])]
    # reindex to a continuous month range so shift(1) really means "previous month"
    out = out.reindex(pd.period_range(out.index.min(), out.index.max(), freq="M"))
    for col in ["Revenue", "Profit", "Orders", "Customers"]:
        out[f"{col}_MoM_Pct"] = _pct_change(out[col], 1)
        out[f"{col}_YoY_Pct"] = _pct_change(out[col], 12)   # NaN until 12 months of history exist
    out.index.name = "Month"
    return out.reset_index()


def _pct_change(series: pd.Series, lag: int) -> pd.Series:
    prev = series.shift(lag)
    return pd.Series([np.nan if (g := growth_pct(c, p)) is None or pd.isna(c) or pd.isna(p) else g
                      for c, p in zip(series, prev)], index=series.index)


# ------------------------------------------------------------ contribution & growth by dimension
def contribution_pct(df: pd.DataFrame, dimension: str, metric: str = "Sales") -> pd.DataFrame:
    """Share of the total metric that each member of a dimension contributes."""
    totals = df.groupby(dimension)[metric].sum().sort_values(ascending=False)
    total = totals.sum()
    return pd.DataFrame({
        dimension: totals.index, metric: totals.values,
        "Contribution_Pct": [safe_divide(v, total) * 100 for v in totals.values],
    })


def dimension_growth(current: pd.DataFrame, previous: pd.DataFrame,
                     dimension: str, metric: str = "Sales") -> pd.DataFrame:
    """Growth of every Region / Product / Category between two periods.

    Columns
      change                   : current - previous, in the metric's unit (INR)
      growth_pct               : % growth of this member (None if it had 0 before)
      share_of_current_pct     : how big this member is now (% of total)
      contribution_to_change_pct : this member's change / |total change| * 100
                                   (+ve = helped the overall move, -ve = worked against it)
    """
    cur = current.groupby(dimension)[metric].sum()
    prev = previous.groupby(dimension)[metric].sum()
    names = cur.index.union(prev.index)
    cur, prev = cur.reindex(names, fill_value=0.0), prev.reindex(names, fill_value=0.0)
    total_change, total_cur, total_prev = (cur - prev).sum(), cur.sum(), prev.sum()
    rows = []
    for name in names:
        change = float(cur[name] - prev[name])
        rows.append({
            "name": str(name), "current": float(cur[name]), "previous": float(prev[name]),
            "change": change, "growth_pct": growth_pct(float(cur[name]), float(prev[name])),
            "share_of_current_pct": safe_divide(cur[name], total_cur) * 100,
            "share_of_previous_pct": safe_divide(prev[name], total_prev) * 100,
            "contribution_to_change_pct": (change / abs(total_change) * 100) if total_change else None,
        })
    return pd.DataFrame(rows).sort_values("change", ascending=False).reset_index(drop=True)
