"""STEP 7 - Rule-based insight engine.

Turns NUMBERS into labelled FACTS using explicit, auditable IF/THEN rules.
The LLM later receives these facts - it never has to "discover" anything.
All thresholds live in InsightConfig, so a business user can tune them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from src.utils import fmt_pct, format_money

SEVERITY_ORDER = {"negative": 0, "warning": 1, "info": 2, "positive": 3}


@dataclass
class InsightConfig:
    strong_growth_pct: float = 10.0     # growth >= this is "strong"
    stable_band_pct: float = 2.0        # |growth| <= this is "stable"
    margin_move_pp: float = 1.0         # margin moves >= 1 percentage point are notable
    driver_share_pct: float = 25.0      # member explaining >= 25% of total change = driver
    risk_decline_pct: float = -3.0      # member shrinking by >= 3% = risk
    min_member_share_pct: float = 3.0   # ignore members smaller than 3% of revenue (noise)
    concentration_pct: float = 60.0     # one member explaining >= 60% of the change
    discount_rise_pp: float = 0.5       # effective discount up by >= 0.5 pp
    customer_drop_pct: float = -5.0
    top_n: int = 3
    forecast_drop_pct: float = 5.0           # projected next month >= 5% below last actual = warning
    forecast_low_confidence_mape: float = 25.0  # backtest error above this = low confidence


def _insight(id_: str, type_: str, severity: str, message: str, dimension: Optional[str] = None,
             name: Optional[str] = None, evidence: Optional[Dict] = None) -> Dict:
    return {"id": id_, "type": type_, "severity": severity, "dimension": dimension,
            "name": name, "message": message, "evidence": evidence or {}}


def _r(x, n=1):
    return None if x is None else round(float(x), n)


def detect_insights(comparison: Dict, drivers: Dict, config: Optional[InsightConfig] = None,
                    is_partial_month: bool = False, forecast: Optional[Dict] = None,
                    anomalies: Optional[Dict] = None) -> List[Dict]:
    cfg = config or InsightConfig()
    out: List[Dict] = []
    rev = comparison["total_revenue"]
    g = rev["growth_pct"]

    # ---- Rule 1: revenue direction
    if g is None:
        out.append(_insight("rev_new", "revenue_new", "info", "Revenue growth cannot be computed because the previous period had no revenue."))
    elif g >= cfg.strong_growth_pct:
        out.append(_insight("rev_strong_growth", "strong_revenue_growth", "positive",
                            f"Strong revenue growth: revenue rose {fmt_pct(g, signed=False)} to {format_money(rev['current'])} from {format_money(rev['previous'])}.",
                            evidence={"growth_pct": _r(g), "current": _r(rev["current"], 0), "previous": _r(rev["previous"], 0)}))
    elif g > cfg.stable_band_pct:
        out.append(_insight("rev_moderate_growth", "moderate_revenue_growth", "positive",
                            f"Moderate revenue growth of {fmt_pct(g, signed=False)} to {format_money(rev['current'])}.",
                            evidence={"growth_pct": _r(g)}))
    elif g >= 0:
        out.append(_insight("rev_stable", "stable_revenue", "info",
                            f"Revenue was broadly stable at {format_money(rev['current'])} ({fmt_pct(g)}).", evidence={"growth_pct": _r(g)}))
    else:
        sev = "info" if abs(g) <= cfg.stable_band_pct else "negative"
        out.append(_insight("rev_decline", "revenue_decline", sev,
                            f"Revenue declined {fmt_pct(abs(g), signed=False)} to {format_money(rev['current'])} from {format_money(rev['previous'])}.",
                            evidence={"growth_pct": _r(g)}))

    # ---- Rule 2: margin (percentage points)
    m = comparison["profit_margin_pct"]
    if m["change_pp"] <= -cfg.margin_move_pp:
        out.append(_insight("margin_down", "margin_compression", "warning",
                            f"Profit margin fell {abs(m['change_pp']):.1f} percentage points to {m['current']:.1f}% from {m['previous']:.1f}%.",
                            evidence={"current_pct": _r(m["current"]), "previous_pct": _r(m["previous"]), "change_pp": _r(m["change_pp"])}))
    elif m["change_pp"] >= cfg.margin_move_pp:
        out.append(_insight("margin_up", "margin_expansion", "positive",
                            f"Profit margin improved {m['change_pp']:.1f} percentage points to {m['current']:.1f}% from {m['previous']:.1f}%.",
                            evidence={"current_pct": _r(m["current"]), "previous_pct": _r(m["previous"]), "change_pp": _r(m["change_pp"])}))
    pg = comparison["total_profit"]["growth_pct"]
    if pg is not None and g is not None and pg < g - 3 and pg < cfg.strong_growth_pct:
        out.append(_insight("profit_lag", "profit_lagging_revenue", "warning",
                            f"Profit grew {fmt_pct(pg, signed=False)} versus revenue growth of {fmt_pct(g, signed=False)}: profit is growing slower than revenue.",
                            evidence={"profit_growth_pct": _r(pg), "revenue_growth_pct": _r(g)}))

    # ---- Rule 3: orders vs order value
    og = comparison["total_orders"]["growth_pct"]
    if g is not None and og is not None:
        if g > cfg.stable_band_pct and og <= 0:
            out.append(_insight("rev_up_orders_down", "growth_from_order_value", "warning",
                                f"Revenue rose {fmt_pct(g, signed=False)} while orders fell {fmt_pct(abs(og), signed=False)}: growth came from higher order value, not more orders.",
                                evidence={"revenue_growth_pct": _r(g), "order_growth_pct": _r(og)}))
        elif g < -cfg.stable_band_pct and og >= 0:
            out.append(_insight("rev_down_orders_up", "lower_order_value", "warning",
                                f"Revenue fell {fmt_pct(abs(g), signed=False)} although orders grew {fmt_pct(og, signed=False)}: average order value dropped.",
                                evidence={"revenue_growth_pct": _r(g), "order_growth_pct": _r(og)}))
    cg = comparison["total_customers"]["growth_pct"]
    if cg is not None and cg <= cfg.customer_drop_pct:
        out.append(_insight("cust_drop", "customer_decline", "warning",
                            f"Active customers fell {fmt_pct(abs(cg), signed=False)}.", evidence={"customer_growth_pct": _r(cg)}))

    # ---- Rule 4: discount pressure (co-occurrence, NOT proven cause)
    d = comparison["effective_discount_pct"]
    if d["change_pp"] >= cfg.discount_rise_pp and m["change_pp"] < 0:
        out.append(_insight("discount_pressure", "discounting_pressure", "warning",
                            f"The effective discount rate rose {d['change_pp']:.1f} percentage points to {d['current']:.1f}% while margin fell; discounting coincides with the margin decline.",
                            evidence={"discount_current_pct": _r(d["current"]), "discount_previous_pct": _r(d["previous"]), "margin_change_pp": _r(m["change_pp"])}))

    # ---- Rule 5/6: drivers, risks and concentration per dimension
    for dim, info in drivers.items():
        total_change = info["total_change"]
        for rank, item in enumerate(info["top_positive"][:cfg.top_n]):
            share = item.get("contribution_to_change_pct")
            if total_change > 0 and (rank == 0 or (share is not None and share >= cfg.driver_share_pct)):
                out.append(_insight(f"driver_{dim}_{item['name']}", "growth_driver", "positive",
                                    f"{item['name']} ({dim.replace('_', ' ')}) is a growth driver: revenue {fmt_pct(item['growth_pct'])} "
                                    f"({'+' if item['change'] >= 0 else ''}{format_money(item['change'])}).",
                                    dimension=dim, name=item["name"],
                                    evidence={"growth_pct": _r(item["growth_pct"]), "change": _r(item["change"], 0),
                                              "share_of_change_pct": _r(share)}))
                if share is not None and share >= cfg.concentration_pct and rank == 0 and dim in ("Region", "Product_Category"):
                    out.append(_insight(f"concentration_{dim}", "growth_concentration", "warning",
                                        f"Growth is concentrated: {item['name']} accounts for {share:.0f}% of the net revenue change across {dim.replace('_', ' ')}.",
                                        dimension=dim, name=item["name"], evidence={"share_of_change_pct": _r(share)}))
        for item in info["top_negative"][:cfg.top_n]:
            gp = item["growth_pct"]
            material = max(item["share_of_current_pct"], item["share_of_previous_pct"]) >= cfg.min_member_share_pct
            if material and gp is not None and gp <= cfg.risk_decline_pct:
                out.append(_insight(f"risk_{dim}_{item['name']}", "decline_risk", "negative",
                                    f"{item['name']} ({dim.replace('_', ' ')}) declined {fmt_pct(abs(gp), signed=False)} "
                                    f"({format_money(item['change'])} change) and is flagged for investigation.",
                                    dimension=dim, name=item["name"],
                                    evidence={"growth_pct": _r(gp), "change": _r(item["change"], 0)}))
            elif material and item["change"] < 0:   # small decline: mention as a watch item
                out.append(_insight(f"watch_{dim}_{item['name']}", "minor_decline", "info",
                                    f"{item['name']} ({dim.replace('_', ' ')}) dipped slightly: {fmt_pct(gp)}.",
                                    dimension=dim, name=item["name"], evidence={"growth_pct": _r(gp), "change": _r(item["change"], 0)}))

    # ---- Rule 7: forecast (a statistical projection, never a promise)
    if forecast and forecast.get("available"):
        nxt = forecast["projections"][0]
        chg = forecast["next_month_change_pct"]
        ev = {"month": nxt["month"], "projected": _r(nxt["value"], 0), "lower": _r(nxt["lower"], 0),
              "upper": _r(nxt["upper"], 0), "change_pct": _r(chg), "method": forecast["method"]}
        base = (f"Projected revenue for {nxt['month']} is about {format_money(nxt['value'])} "
                f"(95% range {format_money(nxt['lower'])} to {format_money(nxt['upper'])}), "
                f"{fmt_pct(chg)} versus the last actual month; this is a statistical projection, not a guarantee.")
        if chg is not None and chg <= -cfg.forecast_drop_pct:
            out.append(_insight("forecast_decline", "forecast_decline", "warning", base, evidence=ev))
        elif chg is not None and chg >= cfg.strong_growth_pct:
            out.append(_insight("forecast_growth", "forecast_growth", "positive", base, evidence=ev))
        else:
            out.append(_insight("forecast_stable", "forecast_outlook", "info", base, evidence=ev))
        mape = forecast.get("backtest_mape_pct")
        if mape is not None and mape > cfg.forecast_low_confidence_mape:
            out.append(_insight("forecast_low_confidence", "forecast_low_confidence", "warning",
                                f"Forecast reliability is limited: when tested on the last 3 known months its average error was {mape:.1f}%.",
                                evidence={"backtest_mape_pct": _r(mape)}))

    # ---- Rule 8: anomalies (unusual, so worth checking; not proof of a problem)
    if anomalies:
        for a in anomalies.get("members", [])[:3]:
            sev = "warning" if a["direction"] == "drop" else "info"
            out.append(_insight(f"anomaly_{a['dimension']}_{a['name']}", "unusual_movement", sev,
                                f"{a['name']} ({a['dimension'].replace('_', ' ')}) moved {fmt_pct(a['mom_pct'])} this month versus a typical "
                                f"monthly change of {fmt_pct(a['typical_mom_pct'])}: statistically unusual (z-score {a['z_score']}).",
                                dimension=a["dimension"], name=a["name"], evidence=a))
        for a in anomalies.get("daily", [])[:2]:
            sev = "warning" if a["direction"] == "drop" else "info"
            out.append(_insight(f"daily_{a['date']}", "unusual_day", sev,
                                f"Revenue on {a['date']} was {format_money(a['revenue'])} versus a typical {format_money(a['expected'])} "
                                f"({a['direction']}, robust z-score {a['robust_z']}).", evidence=a))

    # ---- Rule 9: data quality
    if is_partial_month:
        out.append(_insight("partial_month", "data_quality", "warning",
                            "The latest month is incomplete (data ends before the last day), so growth versus the previous full month may be understated."))
    return sorted(out, key=lambda i: SEVERITY_ORDER[i["severity"]])
