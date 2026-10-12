import pandas as pd
import pytest

from src.kpi_calculation import (calculate_kpis, compare_kpis, contribution_pct, dimension_growth,
                                 filter_month, monthly_summary)

# Hand-calculated expectations for the small_clean_df fixture (see tests/conftest.py):
#   Aug: revenue 2000, profit 200 + 500 = 700 (margin 35.0%)
#   Sep: revenue 2400, profit 500 + 400 = 900 (margin 37.5%)


def test_headline_kpis(small_clean_df):
    k = calculate_kpis(small_clean_df)
    assert k["total_revenue"] == 4400
    assert k["total_cost"] == 2800
    assert k["total_profit"] == 1600
    assert k["profit_margin_pct"] == pytest.approx(1600 / 4400 * 100)
    assert k["total_orders"] == 4
    assert k["total_customers"] == 3
    assert k["average_order_value"] == 1100


def test_kpis_on_empty_frame_do_not_crash(small_clean_df):
    k = calculate_kpis(small_clean_df.iloc[0:0])
    assert k["total_revenue"] == 0 and k["profit_margin_pct"] == 0 and k["average_order_value"] == 0


def test_unknown_customers_not_counted(small_clean_df):
    df = small_clean_df.copy()
    df.loc[1, "Customer_ID"] = "UNKNOWN"      # C2 -> UNKNOWN, leaving C1 and C3
    assert calculate_kpis(df)["total_customers"] == 2


def test_compare_kpis_growth(small_clean_df):
    cur, prev = filter_month(small_clean_df, "2026-09"), filter_month(small_clean_df, "2026-08")
    c = compare_kpis(cur, prev)
    assert c["total_revenue"]["growth_pct"] == pytest.approx(20.0)
    assert c["total_profit"]["growth_pct"] == pytest.approx((900 - 700) / 700 * 100)
    assert c["total_orders"]["growth_pct"] == 0
    assert c["total_customers"]["growth_pct"] == 0


def test_margin_change_is_in_percentage_points(small_clean_df):
    cur, prev = filter_month(small_clean_df, "2026-09"), filter_month(small_clean_df, "2026-08")
    m = compare_kpis(cur, prev)["profit_margin_pct"]
    assert m["previous"] == pytest.approx(35.0)
    assert m["current"] == pytest.approx(37.5)
    assert m["change_pp"] == pytest.approx(2.5)


def test_filter_month(small_clean_df):
    assert len(filter_month(small_clean_df, "2026-08")) == 2
    assert len(filter_month(small_clean_df, pd.Period("2026-09", freq="M"))) == 2


def test_dimension_growth_by_region(small_clean_df):
    cur, prev = filter_month(small_clean_df, "2026-09"), filter_month(small_clean_df, "2026-08")
    t = dimension_growth(cur, prev, "Region").set_index("name")
    assert t.loc["North", "growth_pct"] == pytest.approx(50.0)     # 1000 -> 1500
    assert t.loc["West", "growth_pct"] == pytest.approx(-10.0)     # 1000 -> 900
    # total change = +400; North explains +500 of it (125%), West -100 (-25%)
    assert t.loc["North", "contribution_to_change_pct"] == pytest.approx(125.0)
    assert t.loc["West", "contribution_to_change_pct"] == pytest.approx(-25.0)
    assert t["contribution_to_change_pct"].sum() == pytest.approx(100.0)


def test_dimension_growth_handles_new_member(small_clean_df):
    cur, prev = filter_month(small_clean_df, "2026-09").copy(), filter_month(small_clean_df, "2026-08")
    cur.loc[cur.index[0], "Region"] = "East"        # East did not exist last month
    t = dimension_growth(cur, prev, "Region").set_index("name")
    assert t.loc["East", "growth_pct"] is None or pd.isna(t.loc["East", "growth_pct"])


def test_contribution_pct_sums_to_100(small_clean_df):
    c = contribution_pct(small_clean_df, "Region")
    assert c["Contribution_Pct"].sum() == pytest.approx(100.0)


def test_monthly_summary_growth(small_clean_df):
    m = monthly_summary(small_clean_df)
    assert list(m["Revenue"]) == [2000, 2400]
    assert pd.isna(m["Revenue_MoM_Pct"].iloc[0])
    assert m["Revenue_MoM_Pct"].iloc[1] == pytest.approx(20.0)
    assert m["Revenue_YoY_Pct"].isna().all()           # not enough history for YoY
