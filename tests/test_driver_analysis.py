import pytest

from src.driver_analysis import analyze_drivers
from src.kpi_calculation import filter_month


def test_top_positive_and_negative_regions(small_clean_df):
    cur, prev = filter_month(small_clean_df, "2026-09"), filter_month(small_clean_df, "2026-08")
    d = analyze_drivers(cur, prev, min_share_pct=0)["Region"]
    assert d["top_positive"][0]["name"] == "North"
    assert d["top_positive"][0]["growth_pct"] == pytest.approx(50.0)
    assert d["top_negative"][0]["name"] == "West"
    assert d["top_negative"][0]["growth_pct"] == pytest.approx(-10.0)
    assert d["total_change"] == pytest.approx(400)


def test_missing_dimension_is_skipped(small_clean_df):
    cur, prev = filter_month(small_clean_df, "2026-09"), filter_month(small_clean_df, "2026-08")
    d = analyze_drivers(cur.drop(columns=["Customer_Segment"]), prev.drop(columns=["Customer_Segment"]))
    assert "Customer_Segment" not in d and "Region" in d


def test_ranking_uses_rupee_contribution_not_percentage(small_clean_df):
    """A tiny member with huge % growth must not outrank a big member with more rupee impact."""
    cur, prev = filter_month(small_clean_df, "2026-09").copy(), filter_month(small_clean_df, "2026-08").copy()
    tiny = cur.iloc[[0]].copy(); tiny["Region"] = "East"; tiny["Order_ID"] = "T1"; tiny["Sales"] = 10.0
    import pandas as pd
    cur = pd.concat([cur, tiny])
    d = analyze_drivers(cur, prev, min_share_pct=0)["Region"]
    assert d["top_positive"][0]["name"] == "North"


def test_all_members_present(small_clean_df):
    cur, prev = filter_month(small_clean_df, "2026-09"), filter_month(small_clean_df, "2026-08")
    d = analyze_drivers(cur, prev)["Product"]
    assert {m["name"] for m in d["all_members"]} == {"Laptop", "Mouse"}


def test_new_member_growth_is_none_not_nan(small_clean_df):
    """A member with no previous revenue has undefined growth: must be None (valid JSON), never NaN."""
    cur, prev = filter_month(small_clean_df, "2026-09").copy(), filter_month(small_clean_df, "2026-08")
    cur.loc[cur.index[0], "Region"] = "East"
    members = analyze_drivers(cur, prev, min_share_pct=0)["Region"]["all_members"]
    east = next(m for m in members if m["name"] == "East")
    assert east["growth_pct"] is None


def test_channel_and_payment_drivers(small_clean_df):
    import pandas as pd
    df = small_clean_df.copy()
    df["Sales_Channel"] = ["Online", "Retail Store", "Online", "Retail Store"]       # Aug: 1000/1000, Sep: 1500/900
    df["Payment_Method"] = ["UPI", "Cash", "UPI", "Cash"]
    cur, prev = filter_month(df, "2026-09"), filter_month(df, "2026-08")
    d = analyze_drivers(cur, prev, min_share_pct=0)
    assert d["Sales_Channel"]["top_positive"][0]["name"] == "Online" and d["Sales_Channel"]["top_negative"][0]["name"] == "Retail Store"
    assert d["Payment_Method"]["top_positive"][0]["name"] == "UPI" and d["Payment_Method"]["top_negative"][0]["growth_pct"] == pytest.approx(-10.0)
