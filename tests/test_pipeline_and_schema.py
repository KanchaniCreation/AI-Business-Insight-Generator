import json
import math

from src.pipeline import run_analysis


def _walk(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)
    else:
        yield obj


def test_payload_is_json_serialisable_and_has_no_nan(sample_clean_big):
    clean, _ = sample_clean_big
    payload = run_analysis(clean).payload
    json.dumps(payload)                                    # must not raise
    assert not any(isinstance(v, float) and math.isnan(v) for v in _walk(payload))


def test_payload_contains_only_aggregates(sample_clean_big):
    clean, _ = sample_clean_big
    text = json.dumps(run_analysis(clean).payload)
    assert "ORD-" not in text and "Customer_ID" not in text      # no raw rows / identifiers


def test_payload_structure(sample_clean_big):
    clean, _ = sample_clean_big
    p = run_analysis(clean).payload
    assert {"schema_version", "period", "kpis", "trend", "drivers", "rule_based_insights",
            "top_growth_region", "negative_contributors", "allowed_names"} <= set(p)
    assert p["kpis"]["revenue"]["current_display"].startswith("₹")


def test_hand_checked_payload(small_clean_df):
    p = run_analysis(small_clean_df).payload
    assert p["kpis"]["revenue"]["growth_pct"] == 20.0
    assert p["top_growth_region"] == {"name": "North", "growth_pct": 50.0}
    assert p["negative_contributors"][0]["name"] == "West"
    assert p["period"]["label"] == "September 2026"


def test_payload_has_forecast_and_anomalies(sample_clean_big):
    clean, _ = sample_clean_big
    p = run_analysis(clean).payload
    assert "available" in p["forecast"] and set(p["anomalies"]) == {"daily", "members"}
    json.dumps(p)


def test_short_history_pipeline_still_works(small_clean_df):
    p = run_analysis(small_clean_df).payload
    assert p["forecast"]["available"] is False and "reason" in p["forecast"]


def test_currency_is_applied_everywhere(small_clean_df):
    p = run_analysis(small_clean_df, currency="USD").payload
    assert p["currency"] == "USD" and p["kpis"]["revenue"]["current_display"] == "$2,400"
    assert "$" in " ".join(i["message"] for i in run_analysis(small_clean_df, currency="USD").insights)
    assert run_analysis(small_clean_df, currency="INR").payload["kpis"]["revenue"]["current_display"] == "₹2,400"


def test_sample_data_has_channel_and_payment_drivers(sample_clean_big):
    clean, _ = sample_clean_big
    res = run_analysis(clean)
    assert {"Sales_Channel", "Payment_Method"} <= set(res.drivers)
    assert "Sales_Channel" in res.payload["drivers"] and "Payment_Method" in res.payload["drivers"]


def test_report_shows_channel_and_payment_tables(sample_clean_big):
    from src.llm_generator import generate_fallback_report
    from src.report_generator import build_markdown
    clean, _ = sample_clean_big
    payload = run_analysis(clean).payload
    md = build_markdown(payload, generate_fallback_report(payload))
    assert "**By Sales Channel**" in md and "**By Payment Method**" in md
