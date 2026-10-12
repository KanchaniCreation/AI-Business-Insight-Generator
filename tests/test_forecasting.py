import numpy as np
import pandas as pd
import pytest

from src.forecasting import backtest_mape, forecast_monthly, forecast_values
from tests.conftest import months_df


def test_linear_trend_extrapolates():
    values = [100 + 10 * i for i in range(12)]                       # perfect line: 100..210
    res = forecast_values(values, pd.Period("2024-12", "M"), 3)
    assert res["method"] == "linear_trend"
    assert [round(p["value"]) for p in res["projections"]] == [220, 230, 240]
    assert [p["month"] for p in res["projections"]] == ["2025-01", "2025-02", "2025-03"]


def test_seasonal_method_learns_a_december_peak():
    rng = np.random.default_rng(0)
    season = np.array([.9, .9, .95, 1, 1, 1, 1, 1, 1.05, 1.1, 1.2, 1.6])
    values = [(1000 + 20 * i) * season[i % 12] * rng.uniform(.98, 1.02) for i in range(36)]
    res = forecast_values(values, pd.Period("2026-12", "M"), 3)
    assert res["method"] == "seasonal_trend"
    jan, feb, mar = [p["value"] for p in res["projections"]]
    assert jan < 1700 and 1500 < jan and mar > 1500                  # roughly (1000+20*36) * 0.9 = 1548
    assert backtest_mape(values, pd.Period("2026-12", "M")) < 8


def test_range_contains_point_and_is_non_negative():
    res = forecast_values([50, 40, 30, 20, 10, 5, 2, 1], pd.Period("2024-08", "M"), 3)
    for p in res["projections"]:
        assert 0 <= p["lower"] <= p["value"] <= p["upper"]


def test_too_little_history_is_reported_not_crashed():
    fc = forecast_monthly(months_df([1, 2, 3]))
    assert fc["available"] is False and "6 months" in fc["reason"]


def test_gaps_in_history_are_rejected():
    fc = forecast_monthly(months_df([1, 2, np.nan, 4, 5, 6, 7]))
    assert fc["available"] is False


def test_forecast_monthly_structure():
    fc = forecast_monthly(months_df([100, 110, 120, 130, 140, 150, 160, 170, 180]), horizon=2)
    assert fc["available"] and len(fc["projections"]) == 2 and fc["last_actual_month"] == "2024-09"
    assert fc["next_month_change_pct"] == pytest.approx((fc["projections"][0]["value"] - 180) / 180 * 100)
    assert fc["backtest_mape_pct"] is not None


def test_incomplete_last_month_can_be_excluded():
    values = [100, 110, 120, 130, 140, 150, 160, 20]                  # last month only partly recorded
    fc = forecast_monthly(months_df(values), exclude_last_month=True)
    assert fc["last_actual_month"] == "2024-07" and fc["projections"][0]["value"] > 150


def test_backtest_needs_enough_history():
    assert backtest_mape([1, 2, 3, 4, 5, 6], pd.Period("2024-06", "M")) is None
