import pandas as pd
import pytest

from src.data_cleaning import canonicalize_text, clean_data, parse_dates, to_numeric_clean
from src.exceptions import DataValidationError
from tests.conftest import make_row


def _raw(rows):
    return pd.DataFrame(rows)


def test_missing_required_column_raises():
    df = _raw([make_row("2026-01-01", "A1")]).drop(columns=["Sales"])
    with pytest.raises(DataValidationError, match="Sales"):
        clean_data(df)


def test_empty_dataframe_raises():
    with pytest.raises(DataValidationError):
        clean_data(pd.DataFrame())


def test_column_names_are_standardised():
    df = _raw([make_row("2026-01-01", "A1")]).rename(columns={"Order_ID": " order id ", "Sales": "SALES"})
    clean, _ = clean_data(df)
    assert "Order_ID" in clean.columns and "Sales" in clean.columns


def test_exact_duplicates_removed():
    row = make_row("2026-01-01", "A1")
    clean, rep = clean_data(_raw([row, dict(row), make_row("2026-01-02", "A2")]))
    assert len(clean) == 2 and rep["issues"]["exact_duplicates_removed"] == 1


def test_invalid_dates_dropped():
    rows = [make_row("2026-01-01", "A1"), make_row("31-02-2026", "A2"), make_row("garbage", "A3")]
    clean, rep = clean_data(_raw(rows))
    assert list(clean["Order_ID"]) == ["A1"]
    assert rep["issues"]["invalid_dates_removed"] == 2


def test_negative_and_zero_values_removed():
    rows = [make_row("2026-01-01", "A1"), make_row("2026-01-02", "A2", qty=-1),
            make_row("2026-01-03", "A3", sales=-50), make_row("2026-01-04", "A4", qty=0)]
    clean, _ = clean_data(_raw(rows))
    assert list(clean["Order_ID"]) == ["A1"]


def test_text_numbers_with_currency_symbols_are_converted():
    s = to_numeric_clean(pd.Series(["₹1,23,456.50", " 12 ", "abc", None]))
    assert s.iloc[0] == 123456.5 and s.iloc[1] == 12
    assert pd.isna(s.iloc[2]) and pd.isna(s.iloc[3])


def test_categorical_values_standardised():
    s = canonicalize_text(pd.Series(["North", " north ", "NORTH", "N", "South"]), {"n": "north", "s": "south"})
    assert set(s) == {"North", "South"}


def test_product_casing_keeps_usb_cable_intact():
    s = canonicalize_text(pd.Series(["USB Cable", "usb cable", "USB Cable", " USB CABLE"]))
    assert set(s) == {"USB Cable"}


def test_missing_region_repaired_from_state():
    row = make_row("2026-01-01", "A1", state="Gujarat")
    row["Region"] = None
    clean, rep = clean_data(_raw([row, make_row("2026-01-02", "A2")]))
    assert clean.loc[clean["Order_ID"] == "A1", "Region"].iloc[0] == "West"


def test_missing_cost_is_imputed_and_flagged():
    rows = [make_row("2026-01-01", f"A{i}", sales=1000, cost=800) for i in range(5)]
    rows[0]["Cost"] = None
    clean, rep = clean_data(_raw(rows))
    flagged = clean[clean["Cost_Imputed"]]
    assert len(flagged) == 1 and flagged["Cost"].iloc[0] == pytest.approx(800)


def test_discount_given_as_percent_is_converted():
    clean, _ = clean_data(_raw([make_row("2026-01-01", "A1", discount=15)]))
    assert clean["Discount"].iloc[0] == pytest.approx(0.15)


def test_profit_is_recomputed():
    row = make_row("2026-01-01", "A1", sales=1000, cost=800)
    row["Profit"] = 999999
    clean, _ = clean_data(_raw([row]))
    assert clean["Profit"].iloc[0] == 200


def test_extreme_outlier_removed_but_normal_kept():
    rows = [make_row("2026-01-01", f"A{i}", sales=1000 + i, cost=800) for i in range(30)]
    rows.append(make_row("2026-01-02", "BAD", sales=1_000_000, cost=800))
    clean, rep = clean_data(_raw(rows))
    assert "BAD" not in set(clean["Order_ID"]) and len(clean) == 30


def test_full_sample_pipeline_has_no_missing_values(sample_clean_big):
    clean, rep = sample_clean_big
    assert clean.isna().sum().sum() == 0
    assert rep["rows_out"] < rep["rows_in"]
    assert (clean["Quantity"] > 0).all() and (clean["Sales"] > 0).all()
    assert set(clean["Region"]) <= {"North", "South", "East", "West"}


def test_parse_dates_handles_day_first_and_iso():
    s = parse_dates(pd.Series(["2026-03-05", "05-03-2026", "05/03/2026", "2026-03-05 00:00:00", "nonsense"]))
    assert all(s.iloc[i] == pd.Timestamp("2026-03-05") for i in range(4))   # ISO is NOT flipped
    assert pd.isna(s.iloc[4])


def test_parse_dates_accepts_excel_datetime_objects():
    s = parse_dates(pd.Series([pd.Timestamp("2026-03-05"), "31-02-2026", None]))
    assert s.iloc[0] == pd.Timestamp("2026-03-05") and s.iloc[1:].isna().all()


def test_csv_and_excel_paths_give_identical_results(sample_raw_df, tmp_path):
    """Regression test: a date-format bug once made CSV uploads silently wrong."""
    from src.data_ingestion import load_dataset
    sample_raw_df.to_csv(tmp_path / "s.csv", index=False)
    sample_raw_df.to_excel(tmp_path / "s.xlsx", index=False)
    a, _ = clean_data(load_dataset(tmp_path / "s.csv"))
    b, _ = clean_data(load_dataset(tmp_path / "s.xlsx"))
    assert a.groupby(a["Date"].dt.to_period("M"))["Sales"].sum().round(2).equals(
        b.groupby(b["Date"].dt.to_period("M"))["Sales"].sum().round(2))


# ---------------------------------------------------------------- real-world robustness (e.g. Kaggle files)
def test_repeated_order_ids_are_kept_as_order_lines():
    rows = [make_row("2026-01-01", "A1", product="Mouse", sales=100), make_row("2026-01-01", "A1", product="Laptop", sales=900)]
    clean, rep = clean_data(_raw(rows))
    assert len(clean) == 2 and any("order lines" in n for n in rep["notes"])


def test_legitimate_bulk_order_is_not_removed_as_outlier():
    """A big order (quantity 50) has a large Sales value but a NORMAL unit price: it must survive."""
    rows = [make_row("2026-01-01", f"A{i}", sales=100, cost=60, qty=1) for i in range(20)]
    rows.append(make_row("2026-01-02", "BULK", sales=5000, cost=3000, qty=50))
    clean, _ = clean_data(_raw(rows))
    assert "BULK" in set(clean["Order_ID"])


def test_unit_price_typo_is_removed():
    rows = [make_row("2026-01-01", f"A{i}", sales=100, cost=60, qty=1) for i in range(20)]
    rows.append(make_row("2026-01-02", "TYPO", sales=10000, cost=60, qty=1))      # 100x too big
    clean, _ = clean_data(_raw(rows))
    assert "TYPO" not in set(clean["Order_ID"])


def test_us_date_convention_detected():
    rows = [make_row("12/25/2026", "A1"), make_row("1/5/2026", "A2")]
    clean, rep = clean_data(_raw(rows))
    assert rep["date_format"].startswith("month-first")
    assert set(clean["Date"]) == {pd.Timestamp("2026-12-25"), pd.Timestamp("2026-01-05")}


def test_ambiguous_dates_add_a_note_and_can_be_overridden():
    rows = [make_row("05/03/2026", "A1"), make_row("04/02/2026", "A2")]
    clean, rep = clean_data(_raw(rows))
    assert any("ambiguous" in n for n in rep["notes"]) and pd.Timestamp("2026-03-05") in set(clean["Date"])
    clean2, _ = clean_data(_raw(rows), dayfirst=False)
    assert pd.Timestamp("2026-05-03") in set(clean2["Date"])


def test_optional_columns_are_cleaned_too():
    row = make_row("2026-01-01", "A1")
    row["Sub_Category"] = " chairs "
    clean, _ = clean_data(_raw([row, dict(row, Order_ID="A2", Sub_Category="CHAIRS")]))
    assert clean["Sub_Category"].nunique() == 1


def test_iso_dates_are_labelled_iso_not_ambiguous():
    clean, rep = clean_data(_raw([make_row("2026-03-05", "A1"), make_row("2026-04-06", "A2")]))
    assert rep["date_format"].startswith("ISO") and not any("ambiguous" in n for n in rep["notes"])


def test_channel_and_payment_are_standardised_and_missing_become_unknown():
    rows = [dict(make_row("2026-01-01", f"A{i}"), Sales_Channel=ch, Payment_Method=pm)
            for i, (ch, pm) in enumerate([("Online", "UPI"), (" online ", "upi"), ("ONLINE", "Cash"), ("Retail Store", None)])]
    clean, _ = clean_data(_raw(rows))
    assert set(clean["Sales_Channel"]) == {"Online", "Retail Store"}
    assert set(clean["Payment_Method"]) == {"UPI", "Cash", "Unknown"}
