"""STEP 8 - The structured JSON "contract" between Python analytics and the LLM.

Only analysed facts go in here: no raw rows. Every money value comes with a *_display
string (e.g. '₹11,20,000') so the LLM can quote it exactly instead of converting units.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd

from src.utils import format_money

SCHEMA_VERSION = "1.1"


def _r1(x) -> float:
    """round to 1 decimal and turn -0.0 into 0.0 (so reports never show '-0.0')."""
    return round(float(x), 1) + 0.0


def _money(cur, prev, growth) -> Dict:
    return {"current": round(cur, 2), "previous": round(prev, 2),
            "current_display": format_money(cur), "previous_display": format_money(prev),
            "growth_pct": None if growth is None else _r1(growth)}


def _count(cur, prev, growth) -> Dict:
    return {"current": int(cur), "previous": int(prev),
            "growth_pct": None if growth is None else _r1(growth)}


def _member(m: Dict) -> Dict:
    return {"name": m["name"],
            "growth_pct": None if m["growth_pct"] is None else round(m["growth_pct"], 1),
            "revenue_change": round(m["change"], 2), "revenue_change_display": format_money(m["change"]),
            "share_of_net_change_pct": None if m["contribution_to_change_pct"] is None else round(m["contribution_to_change_pct"], 1)}


def _forecast_block(fc: Optional[Dict]) -> Dict:
    if not fc or not fc.get("available"):
        return {"available": False, "reason": (fc or {}).get("reason", "not computed")}
    return {"available": True, "metric": fc["metric"], "method": fc["method"],
            "last_actual_month": fc["last_actual_month"],
            "last_actual_display": format_money(fc["last_actual_value"]),
            "projections": [{"month": p["month"], "value_display": format_money(p["value"]),
                             "lower_display": format_money(p["lower"]), "upper_display": format_money(p["upper"])}
                            for p in fc["projections"]],
            "next_month_change_pct": None if fc["next_month_change_pct"] is None else round(fc["next_month_change_pct"], 1),
            "backtest_mape_pct": None if fc["backtest_mape_pct"] is None else round(fc["backtest_mape_pct"], 1),
            "note": "Statistical projection with a 95% range; not a guarantee."}


def _anomaly_block(an: Optional[Dict]) -> Dict:
    an = an or {"daily": [], "members": []}
    return {"daily": [{"date": a["date"], "revenue_display": format_money(a["revenue"]),
                       "typical_display": format_money(a["expected"]), "direction": a["direction"],
                       "robust_z_score": a["robust_z"]} for a in an["daily"]],
            "members": [{"dimension": a["dimension"], "name": a["name"], "mom_pct": a["mom_pct"],
                         "typical_mom_pct": a["typical_mom_pct"], "z_score": a["z_score"],
                         "direction": a["direction"]} for a in an["members"]]}


def build_payload(current_period: pd.Period, previous_period: pd.Period, comparison: Dict,
                  trends: Dict, drivers: Dict, insights: List[Dict],
                  is_partial_month: bool = False, currency: str = "INR",
                  forecast: Optional[Dict] = None, anomalies: Optional[Dict] = None) -> Dict:
    k = comparison
    payload = {
        "schema_version": SCHEMA_VERSION,
        "period": {"current": str(current_period), "previous": str(previous_period),
                   "label": current_period.strftime("%B %Y"), "is_partial_month": is_partial_month},
        "currency": currency,
        "kpis": {
            "revenue": _money(k["total_revenue"]["current"], k["total_revenue"]["previous"], k["total_revenue"]["growth_pct"]),
            "profit": _money(k["total_profit"]["current"], k["total_profit"]["previous"], k["total_profit"]["growth_pct"]),
            "average_order_value": _money(k["average_order_value"]["current"], k["average_order_value"]["previous"], k["average_order_value"]["growth_pct"]),
            "orders": _count(k["total_orders"]["current"], k["total_orders"]["previous"], k["total_orders"]["growth_pct"]),
            "customers": _count(k["total_customers"]["current"], k["total_customers"]["previous"], k["total_customers"]["growth_pct"]),
            "quantity": _count(k["total_quantity"]["current"], k["total_quantity"]["previous"], k["total_quantity"]["growth_pct"]),
            "profit_margin_pct": {"current": round(k["profit_margin_pct"]["current"], 1),
                                  "previous": round(k["profit_margin_pct"]["previous"], 1),
                                  "change_pp": _r1(k["profit_margin_pct"]["change_pp"])},
            "effective_discount_pct": {"current": round(k["effective_discount_pct"]["current"], 1),
                                       "previous": round(k["effective_discount_pct"]["previous"], 1),
                                       "change_pp": _r1(k["effective_discount_pct"]["change_pp"])},
        },
        "trend": {name: {"direction": t["direction"], "slope_pct_per_month": t["slope_pct_per_month"],
                         "latest_mom_pct": t["latest_mom_pct"], "latest_yoy_pct": t["latest_yoy_pct"]}
                  for name, t in trends.items() if isinstance(t, dict) and "direction" in t},
        "drivers": {
            dim: {"net_revenue_change_display": format_money(info["total_change"]),
                  "top_positive": [_member(m) for m in info["top_positive"]],
                  "top_negative": [_member(m) for m in info["top_negative"]]}
            for dim, info in drivers.items()
        },
        "forecast": _forecast_block(forecast),
        "anomalies": _anomaly_block(anomalies),
        "rule_based_insights": [{"type": i["type"], "severity": i["severity"], "dimension": i["dimension"],
                                 "name": i["name"], "message": i["message"]} for i in insights],
        "allowed_names": sorted({m["name"] for info in drivers.values() for m in info["all_members"]})[:200],
    }
    # convenience shortcuts that mirror the example in the project brief
    reg = drivers.get("Region")
    if reg and reg["top_positive"]:
        payload["top_growth_region"] = {"name": reg["top_positive"][0]["name"], "growth_pct": _member(reg["top_positive"][0])["growth_pct"]}
    prod = drivers.get("Product")
    if prod and prod["top_positive"]:
        payload["top_growth_product"] = {"name": prod["top_positive"][0]["name"], "growth_pct": _member(prod["top_positive"][0])["growth_pct"]}
    payload["negative_contributors"] = [
        {"dimension": d, "name": m["name"], "growth_pct": _member(m)["growth_pct"]}
        for d, info in drivers.items() for m in info["top_negative"]
    ]
    return payload
