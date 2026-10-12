import pandas as pd
import pytest

from src.column_mapper import MappingError, apply_mapping, mapping_problems, suggest_mapping
from src.pipeline import prepare_dataset, run_analysis


def test_superstore_columns_are_auto_detected(superstore_raw):
    m = suggest_mapping(superstore_raw)
    assert m["Date"] == "Order Date" and m["Order_ID"] == "Order ID"
    assert m["Product_Category"] == "Category" and m["Sub_Category"] == "Sub-Category"
    assert m["Product"] == "Product Name" and m["Customer_Segment"] == "Segment"
    assert m["Cost"] is None and m["Profit"] == "Profit"
    assert mapping_problems(m) == []


def test_row_id_and_ship_date_are_not_mapped(superstore_raw):
    used = set(suggest_mapping(superstore_raw).values())
    assert "Row ID" not in used and "Ship Date" not in used and "Ship Mode" not in used


def test_fuzzy_match_handles_typos():
    df = pd.DataFrame({"Order Dat": ["2026-01-01"], "Revenu": [10], "Profit": [2], "Quantiy": [1]})
    m = suggest_mapping(df)
    assert m["Date"] == "Order Dat" and m["Sales"] == "Revenu" and m["Quantity"] == "Quantiy"


def test_cost_is_derived_from_profit(superstore_raw):
    mapped, notes = apply_mapping(superstore_raw, suggest_mapping(superstore_raw))
    assert (mapped["Cost"] - (mapped["Sales"] - mapped["Profit"])).abs().max() < 1e-6
    assert any("Cost was derived" in n for n in notes)


def test_profit_is_derived_from_cost():
    df = pd.DataFrame({"Date": ["2026-01-01"], "Sales": [100], "Cost": [70]})
    mapped, notes = apply_mapping(df, suggest_mapping(df))
    assert mapped["Profit"].iloc[0] == 30 and any("Profit was derived" in n for n in notes)


def test_missing_optional_columns_get_defaults():
    df = pd.DataFrame({"Date": ["2026-01-01", "2026-01-02"], "Sales": [100, 50], "Profit": [10, 5]})
    mapped, notes = apply_mapping(df, suggest_mapping(df))
    assert list(mapped["Quantity"]) == [1, 1] and list(mapped["Discount"]) == [0.0, 0.0]
    assert mapped["Order_ID"].is_unique and mapped["Region"].eq("Unknown").all()


def test_missing_sales_or_date_is_rejected():
    with pytest.raises(MappingError, match="Sales"):
        apply_mapping(pd.DataFrame({"Date": ["2026-01-01"], "Profit": [1]}), {"Date": "Date", "Profit": "Profit"})
    with pytest.raises(MappingError, match="Cost' or 'Profit"):
        df = pd.DataFrame({"Date": ["2026-01-01"], "Sales": [1]})
        apply_mapping(df, suggest_mapping(df))


def test_wrong_mapping_is_caught():
    df = pd.DataFrame({"Date": ["2026-01-01"], "Name": ["abc"], "Profit": [1]})
    with pytest.raises(MappingError, match="numeric"):
        apply_mapping(df, {"Date": "Date", "Sales": "Name", "Profit": "Profit"})
    df2 = pd.DataFrame({"When": ["hello"], "Sales": [5], "Profit": [1]})
    with pytest.raises(MappingError, match="date"):
        apply_mapping(df2, {"Date": "When", "Sales": "Sales", "Profit": "Profit"})


def test_same_column_cannot_be_used_twice():
    df = pd.DataFrame({"Date": ["2026-01-01"], "Sales": [5], "Profit": [1]})
    with pytest.raises(MappingError, match="more than one"):
        apply_mapping(df, {"Date": "Date", "Sales": "Sales", "Profit": "Sales"})


def test_unknown_mapped_column_is_rejected():
    df = pd.DataFrame({"Date": ["2026-01-01"], "Sales": [5], "Profit": [1]})
    with pytest.raises(MappingError, match="not found"):
        apply_mapping(df, {"Date": "Nope", "Sales": "Sales", "Profit": "Profit"})


def test_superstore_full_pipeline(superstore_raw):
    clean, report = prepare_dataset(superstore_raw)
    assert report["date_format"].startswith("month-first")
    assert clean["Date"].dt.year.between(2014, 2017).all()           # US dates NOT flipped
    assert report["rows_out"] == report["rows_in"]                    # repeated Order IDs are order lines, not duplicates
    assert clean["Order_ID"].duplicated().any() and any("order lines" in n for n in report["notes"])
    result = run_analysis(clean, currency="USD")
    assert result.payload["kpis"]["revenue"]["current_display"].startswith("$")
    assert "Sub_Category" in result.drivers and "Region" in result.drivers


def test_us_dates_give_correct_months(superstore_raw):
    """Regression: '11/8/2016' must be 8 November, not 11 August."""
    clean, _ = prepare_dataset(superstore_raw)
    raw_first = superstore_raw.iloc[0]["Order Date"]
    month, day, year = map(int, raw_first.split("/"))
    assert pd.Timestamp(year=year, month=month, day=day) in set(clean["Date"])


def test_unneeded_columns_are_dropped(superstore_raw):
    clean, _ = prepare_dataset(superstore_raw)
    assert "Ship Mode" not in clean.columns and "Customer Name" not in clean.columns


def test_channel_and_payment_columns_are_detected():
    df = pd.DataFrame({"Date": ["2026-01-01"], "Sales": [10], "Profit": [2], "Payment Mode": ["UPI"], "Channel": ["Online"]})
    m = suggest_mapping(df)
    assert m["Payment_Method"] == "Payment Mode" and m["Sales_Channel"] == "Channel"
    mapped, _ = apply_mapping(df, m)
    assert {"Payment_Method", "Sales_Channel"} <= set(mapped.columns)


def test_unknown_extra_columns_are_still_ignored():
    df = pd.DataFrame({"Date": ["2026-01-01"], "Sales": [10], "Profit": [2], "Unit_Price": [10], "Notes": ["x"]})
    mapped, _ = apply_mapping(df, suggest_mapping(df))
    assert "Unit_Price" not in mapped.columns and "Notes" not in mapped.columns
