import numpy as np
import pandas as pd

from src.anomaly_detection import detect_anomalies, detect_daily_anomalies, detect_member_anomalies


def _daily_df(spike_day=None, days=60):
    rng = np.random.default_rng(1)
    rows = []
    for i, d in enumerate(pd.date_range("2026-01-01", periods=days)):
        amount = 1000 * rng.uniform(.9, 1.1) * (8 if d == pd.Timestamp(spike_day) else 1) if spike_day else 1000 * rng.uniform(.9, 1.1)
        rows.append({"Date": d, "Sales": amount, "Region": "North", "Order_ID": f"O{i}"})
    return pd.DataFrame(rows)


def test_daily_spike_is_detected():
    out = detect_daily_anomalies(_daily_df("2026-02-20"), "2026-02")
    assert out and out[0]["date"] == "2026-02-20" and out[0]["direction"] == "spike" and out[0]["robust_z"] > 3.5


def test_normal_noise_is_not_flagged():
    assert detect_daily_anomalies(_daily_df(None), "2026-02") == []


def test_short_history_returns_empty():
    assert detect_daily_anomalies(_daily_df(None, days=10), "2026-01") == []


def _member_df(last_north):
    rows = []
    rng = np.random.default_rng(2)
    for i, m in enumerate(pd.period_range("2025-01", "2026-03", freq="M")):
        for region, base in (("North", 1000), ("South", 800)):
            val = base * (1 + rng.normal(0, 0.03))
            if region == "North" and m == pd.Period("2026-03", "M"):
                val = last_north
            rows.append({"Date": m.to_timestamp() + pd.Timedelta(days=5), "Sales": val, "Region": region})
    return pd.DataFrame(rows)


def test_member_spike_detected_and_stable_member_ignored():
    out = detect_member_anomalies(_member_df(1700), "Region", "2026-03")
    assert [a["name"] for a in out] == ["North"] and out[0]["direction"] == "spike" and out[0]["mom_pct"] > 50


def test_member_drop_detected():
    out = detect_member_anomalies(_member_df(400), "Region", "2026-03")
    assert out and out[0]["direction"] == "drop"


def test_no_anomaly_when_nothing_unusual():
    assert detect_member_anomalies(_member_df(1000), "Region", "2026-03") == []


def test_high_cardinality_dimension_is_skipped(sample_clean_big):
    clean, _ = sample_clean_big
    assert detect_member_anomalies(clean.assign(Product=clean["Order_ID"]), "Product", "2026-09") == []


def test_missing_dimension_and_unknown_period():
    df = _member_df(1000)
    assert detect_member_anomalies(df, "Nope", "2026-03") == []
    assert detect_member_anomalies(df, "Region", "2030-01") == []


def test_detect_anomalies_structure(sample_clean_big):
    clean, _ = sample_clean_big
    out = detect_anomalies(clean, "2026-09")
    assert set(out) == {"daily", "members"} and isinstance(out["members"], list)
