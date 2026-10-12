import copy

from src.insight_engine import InsightConfig, detect_insights
from src.pipeline import run_analysis


def _types(insights):
    return {i["type"] for i in insights}


def test_strong_growth_and_drivers_detected(small_clean_df):
    r = run_analysis(small_clean_df)           # revenue +20%
    types = _types(r.insights)
    assert "strong_revenue_growth" in types
    drivers = [i for i in r.insights if i["type"] == "growth_driver" and i["dimension"] == "Region"]
    assert drivers and drivers[0]["name"] == "North"


def test_decline_risk_flagged_for_west(small_clean_df):
    r = run_analysis(small_clean_df)           # West -10%
    risks = [i for i in r.insights if i["type"] == "decline_risk"]
    assert any(i["name"] == "West" for i in risks)


def test_revenue_decline_detected(small_clean_df):
    r = run_analysis(small_clean_df)
    comp = copy.deepcopy(r.comparison)
    comp["total_revenue"].update(current=800.0, previous=1000.0, growth_pct=-20.0)
    types = _types(detect_insights(comp, r.drivers))
    assert "revenue_decline" in types and "strong_revenue_growth" not in types


def test_stable_revenue(small_clean_df):
    r = run_analysis(small_clean_df)
    comp = copy.deepcopy(r.comparison)
    comp["total_revenue"]["growth_pct"] = 1.0
    assert "stable_revenue" in _types(detect_insights(comp, r.drivers))


def test_margin_compression_and_discount_pressure(small_clean_df):
    r = run_analysis(small_clean_df)
    comp = copy.deepcopy(r.comparison)
    comp["profit_margin_pct"]["change_pp"] = -2.0
    comp["effective_discount_pct"]["change_pp"] = 1.5
    types = _types(detect_insights(comp, r.drivers))
    assert {"margin_compression", "discounting_pressure"} <= types


def test_revenue_up_orders_down(small_clean_df):
    r = run_analysis(small_clean_df)
    comp = copy.deepcopy(r.comparison)
    comp["total_orders"]["growth_pct"] = -5.0
    assert "growth_from_order_value" in _types(detect_insights(comp, r.drivers))


def test_thresholds_are_configurable(small_clean_df):
    r = run_analysis(small_clean_df)
    strict = InsightConfig(strong_growth_pct=50.0)
    types = _types(detect_insights(r.comparison, r.drivers, strict))
    assert "moderate_revenue_growth" in types and "strong_revenue_growth" not in types


def test_partial_month_warning(small_clean_df):
    r = run_analysis(small_clean_df)
    assert "data_quality" in _types(detect_insights(r.comparison, r.drivers, is_partial_month=True))


def test_new_member_with_undefined_growth_does_not_crash(small_clean_df):
    df = small_clean_df.copy()
    df.loc[df["Order_ID"] == "B2", "Region"] = "East"      # East has no August revenue
    r = run_analysis(df)
    assert isinstance(r.insights, list)


def test_every_insight_has_required_fields(sample_clean_big):
    clean, _ = sample_clean_big
    for i in run_analysis(clean).insights:
        assert {"type", "severity", "message", "evidence"} <= set(i)
        assert i["severity"] in {"positive", "info", "warning", "negative"}


# ---------------------------------------------------------------- forecast and anomaly rules
def _fc(change, mape=5.0):
    return {"available": True, "metric": "revenue", "method": "linear_trend", "next_month_change_pct": change,
            "backtest_mape_pct": mape,
            "projections": [{"month": "2026-10", "value": 2000.0, "lower": 1800.0, "upper": 2200.0}]}


def test_forecast_decline_is_a_warning(small_clean_df):
    r = run_analysis(small_clean_df)
    ins = detect_insights(r.comparison, r.drivers, forecast=_fc(-12.0))
    assert any(i["type"] == "forecast_decline" and i["severity"] == "warning" for i in ins)


def test_forecast_growth_and_outlook(small_clean_df):
    r = run_analysis(small_clean_df)
    assert "forecast_growth" in _types(detect_insights(r.comparison, r.drivers, forecast=_fc(15.0)))
    assert "forecast_outlook" in _types(detect_insights(r.comparison, r.drivers, forecast=_fc(2.0)))


def test_low_confidence_forecast_is_flagged(small_clean_df):
    r = run_analysis(small_clean_df)
    assert "forecast_low_confidence" in _types(detect_insights(r.comparison, r.drivers, forecast=_fc(2.0, mape=40.0)))


def test_unavailable_forecast_adds_nothing(small_clean_df):
    r = run_analysis(small_clean_df)
    ins = detect_insights(r.comparison, r.drivers, forecast={"available": False, "reason": "x"})
    assert not any(i["type"].startswith("forecast") for i in ins)


def test_anomaly_rules(small_clean_df):
    r = run_analysis(small_clean_df)
    an = {"daily": [{"date": "2026-09-17", "revenue": 900.0, "expected": 300.0, "robust_z": 4.5, "direction": "spike"}],
          "members": [{"dimension": "Region", "name": "North", "mom_pct": 40.0, "typical_mom_pct": 3.0, "z_score": 2.8, "direction": "drop"}]}
    ins = detect_insights(r.comparison, r.drivers, anomalies=an)
    unusual = [i for i in ins if i["type"] == "unusual_movement"]
    assert unusual and unusual[0]["severity"] == "warning"           # a drop is a warning
    assert any(i["type"] == "unusual_day" for i in ins)
