import pytest

from src.exceptions import DataValidationError
from src.trend_analysis import (calculate_growth_pct, classify_change, classify_series_trend,
                                is_partial_month, resolve_periods)


def test_growth_formula():
    assert calculate_growth_pct(112, 100) == pytest.approx(12.0)
    assert calculate_growth_pct(97, 100) == pytest.approx(-3.0)


def test_growth_division_by_zero_is_safe():
    assert calculate_growth_pct(0, 0) == 0.0
    assert calculate_growth_pct(50, 0) is None


def test_growth_with_none_inputs():
    assert calculate_growth_pct(None, 10) is None
    assert calculate_growth_pct(10, None) is None


@pytest.mark.parametrize("value,label", [
    (25, "strong_increase"), (5, "increase"), (1, "stable"), (-1.5, "stable"),
    (-5, "decrease"), (-20, "strong_decrease"), (None, "new"),
])
def test_classify_change(value, label):
    assert classify_change(value) == label


def test_series_trend_directions():
    assert classify_series_trend([100, 110, 120, 130, 140, 150])["direction"] == "increasing"
    assert classify_series_trend([150, 140, 130, 120, 110, 100])["direction"] == "declining"
    assert classify_series_trend([100, 100.5, 99.8, 100.2, 100, 99.9])["direction"] == "stable"


def test_series_trend_needs_enough_points():
    assert classify_series_trend([1, 2])["direction"] == "insufficient_data"


def test_resolve_periods_defaults_to_latest(small_clean_df):
    cur, prev = resolve_periods(small_clean_df)
    assert str(cur) == "2026-09" and str(prev) == "2026-08"


def test_resolve_periods_rejects_unknown_month(small_clean_df):
    with pytest.raises(DataValidationError):
        resolve_periods(small_clean_df, "2030-01")


def test_resolve_periods_needs_two_months(small_clean_df):
    with pytest.raises(DataValidationError):
        resolve_periods(small_clean_df[small_clean_df["Date"].dt.month == 9])


def test_partial_month_detection(small_clean_df):
    assert is_partial_month(small_clean_df, "2026-09")           # data stops on 11 Sep
    assert not is_partial_month(small_clean_df, "2026-08")        # not the latest month
