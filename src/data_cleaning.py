"""STEP 3b - Data cleaning pipeline (Pandas).

Entry point:  clean_data(raw_df) -> (clean_df, report)

The pipeline is a sequence of small functions, each doing ONE job. Order matters:

    columns -> types -> dates -> text -> drop unusable rows -> duplicates
            -> repair missing values -> invalid values -> profit -> outliers

`report` is a dictionary that counts every fix, so the user (and the interviewer!)
can see exactly what changed. Nothing is changed silently.
"""
from __future__ import annotations

import re
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

from src.config import (NUMERIC_COLUMNS, OPTIONAL_COLUMNS, REGION_ALIASES,
                        REQUIRED_COLUMNS, STATE_TO_REGION, TEXT_COLUMNS)
from src.exceptions import DataValidationError


# ---------------------------------------------------------------- 1. columns
def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """'order id', 'ORDER-ID', ' Order_ID ' -> 'Order_ID' (case/space insensitive)."""
    canonical = {re.sub(r"[\s\-]+", "_", c.strip().lower()): c for c in REQUIRED_COLUMNS + OPTIONAL_COLUMNS}
    rename = {}
    for col in df.columns:
        key = re.sub(r"[\s\-]+", "_", str(col).strip().lower())
        if key in canonical:
            rename[col] = canonical[key]
    return df.rename(columns=rename)


def validate_required_columns(df: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise DataValidationError(
            f"Missing required column(s): {', '.join(missing)}. "
            f"Required columns are: {', '.join(REQUIRED_COLUMNS)}."
        )


# ---------------------------------------------------------------- 2. types
def to_numeric_clean(series: pd.Series) -> pd.Series:
    """'₹1,23,456.50 ' -> 123456.5 ; unparseable text -> NaN (counted later)."""
    text = series.astype("string").str.replace(r"[₹$,\s]", "", regex=True)
    # float64 (not nullable Float64) so NaN comparisons are plain False, never <NA>
    return pd.to_numeric(text, errors="coerce").astype("float64")


ISO_FORMATS = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y/%m/%d"]
DAY_FIRST_FORMATS = ["%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%y", "%d/%m/%y"]
MONTH_FIRST_FORMATS = ["%m-%d-%Y", "%m/%d/%Y", "%m.%d.%Y", "%m-%d-%y", "%m/%d/%y"]
NAMED_MONTH_FORMATS = ["%d-%b-%Y", "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y"]


def detect_dayfirst(series: pd.Series) -> Optional[bool]:
    """Decide whether 05/03/2026 means 5 March (day-first) or May 3 (month-first).

    Look at the values: if any first number is > 12 (e.g. 25/03/2026) the format must be
    day-first; if any second number is > 12 (e.g. 03/25/2026) it must be month-first.
    Returns None when every value is ambiguous (all numbers <= 12).
    """
    parts = series.dropna().astype(str).str.strip().str.extract(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.]\d{2,4}")
    a, b = pd.to_numeric(parts[0], errors="coerce"), pd.to_numeric(parts[1], errors="coerce")
    first_big, second_big = int((a > 12).sum()), int((b > 12).sum())
    if first_big and not second_big:
        return True
    if second_big and not first_big:
        return False
    return None


def parse_dates(series: pd.Series, dayfirst: Optional[bool] = None) -> pd.Series:
    """Parse mixed date formats. Impossible dates ('31-02-2026') and junk become NaT.

    Why explicit formats instead of pd.to_datetime(dayfirst=True)?  dayfirst=True also
    flips ISO dates ('2026-03-05' would become 5 May!). We try unambiguous ISO first,
    then the detected convention (day-first = Indian/UK, month-first = US/Kaggle Superstore).
    dayfirst=None -> auto-detect, and if still ambiguous assume day-first.
    """
    text = series.astype("string").str.strip()
    if dayfirst is None:
        dayfirst = detect_dayfirst(text)
    if dayfirst is None:
        dayfirst = True
    order = ISO_FORMATS + (DAY_FIRST_FORMATS if dayfirst else MONTH_FIRST_FORMATS) + NAMED_MONTH_FORMATS
    result = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    for fmt in order:
        todo = result.isna() & text.notna()
        if not todo.any():
            break
        result[todo] = pd.to_datetime(text[todo], format=fmt, errors="coerce").astype("datetime64[ns]")
    result = result.dt.normalize()
    # sanity window: protects against 1900/2200 typos
    return result.where((result.dt.year >= 2000) & (result.dt.year <= 2100))


# ---------------------------------------------------------------- 3. text
def canonicalize_text(series: pd.Series, aliases: dict | None = None) -> pd.Series:
    """Make ' north ', 'NORTH', 'North' all become the most common spelling ('North').

    Trick: group by the lower-case key and pick the most frequent original spelling.
    This keeps 'USB Cable' correct (a plain .title() would give 'Usb Cable').
    """
    s = series.astype("string").str.strip().str.replace(r"\s+", " ", regex=True)
    s = s.where(s.str.lower() != "nan", pd.NA)
    key = s.str.lower()
    if aliases:
        key = key.replace(aliases)
    # most frequent *properly cased* spelling within each key group
    chosen = {}
    for k, grp in s.groupby(key):
        counts = grp.value_counts()
        chosen[k] = counts.idxmax()
    mapped = key.map(chosen)
    return mapped.astype("string")


# ---------------------------------------------------------------- main pipeline
def clean_data(raw: pd.DataFrame, dayfirst: Optional[bool] = None) -> Tuple[pd.DataFrame, Dict]:
    """Run the full cleaning pipeline. Returns (clean_df, report).

    dayfirst: None = auto-detect the date convention, True = 31/12/2026, False = 12/31/2026.
    """
    if raw is None or raw.empty:
        raise DataValidationError("No data to clean.")

    df = standardize_columns(raw.copy())
    validate_required_columns(df)
    keep = [c for c in REQUIRED_COLUMNS + OPTIONAL_COLUMNS if c in df.columns]
    df = df[keep]

    report: Dict = {"rows_in": int(len(df)), "issues": {}, "notes": []}
    issues = report["issues"]
    notes = report["notes"]

    # drop fully empty rows
    before = len(df)
    df = df.dropna(how="all")
    issues["empty_rows_removed"] = before - len(df)

    # ---- types
    for col in NUMERIC_COLUMNS:
        original_non_null = df[col].notna()
        df[col] = to_numeric_clean(df[col])
        issues[f"unparseable_{col.lower()}"] = int((original_non_null & df[col].isna()).sum())
    issues["text_numbers_converted"] = 0  # informational; conversion happens silently above

    raw_dates = df["Date"].copy()
    detected = detect_dayfirst(raw_dates.astype("string")) if dayfirst is None else dayfirst
    report["date_format"] = {True: "day-first (31/12/2026)", False: "month-first (12/31/2026)",
                             None: "ambiguous (assumed day-first)"}[detected]
    iso_share = raw_dates.astype("string").str.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}").fillna(False).mean()
    if detected is None and iso_share > 0.5:           # 2026-12-31 can only mean year-month-day: not ambiguous
        report["date_format"] = "ISO (2026-12-31)"
    if detected is None and raw_dates.astype("string").str.contains(r"^\d{1,2}[/\-.]\d{1,2}[/\-.]", regex=True, na=False).any():
        notes.append("Date format is ambiguous (all day/month numbers <= 12); day-first was assumed. "
                     "If your dates are US style (month/day/year), re-run with the month-first option.")
    df["Date"] = parse_dates(df["Date"], dayfirst=detected)
    issues["invalid_dates_removed"] = int((raw_dates.notna() & df["Date"].isna()).sum())

    # ---- text standardisation
    changed = 0
    for col in [c for c in TEXT_COLUMNS if c in df.columns]:
        before_vals = df[col].astype("string")
        df[col] = canonicalize_text(df[col], REGION_ALIASES if col == "Region" else None)
        changed += int((before_vals.notna() & (before_vals != df[col])).sum())
    df["Order_ID"] = df["Order_ID"].astype("string").str.strip()
    df["Customer_ID"] = df["Customer_ID"].astype("string").str.strip()
    issues["text_values_standardized"] = changed

    # ---- drop rows missing something we cannot guess
    critical = df["Date"].isna() | df["Order_ID"].isna() | df["Sales"].isna() | df["Quantity"].isna()
    issues["rows_missing_critical_fields"] = int(critical.sum())
    df = df[~critical]

    # ---- duplicates
    before = len(df)
    df = df.drop_duplicates()
    issues["exact_duplicates_removed"] = before - len(df)
    # Repeated Order_IDs are legitimate (one order can have several product lines), so we only
    # remove EXACT duplicate rows above. We just tell the user how the data is structured.
    repeated = int(df["Order_ID"].duplicated(keep=False).sum())
    if repeated:
        notes.append(f"{repeated:,} rows share an Order_ID with another row; they are treated as separate order lines "
                     "of the same order (Orders KPI counts distinct Order_IDs).")

    # ---- repair missing values
    # Region from State
    miss_region = df["Region"].isna()
    df.loc[miss_region, "Region"] = df.loc[miss_region, "State"].map(STATE_TO_REGION)
    issues["region_repaired_from_state"] = int(miss_region.sum() - df["Region"].isna().sum())
    issues["region_set_unknown"] = int(df["Region"].isna().sum())
    df["Region"] = df["Region"].fillna("Unknown")

    # Category from Product (most common category for that product)
    prod_to_cat = (df.dropna(subset=["Product_Category", "Product"])
                     .groupby("Product")["Product_Category"].agg(lambda s: s.value_counts().idxmax()))
    miss_cat = df["Product_Category"].isna()
    df.loc[miss_cat, "Product_Category"] = df.loc[miss_cat, "Product"].map(prod_to_cat)
    issues["category_repaired_from_product"] = int(miss_cat.sum() - df["Product_Category"].isna().sum())
    df["Product_Category"] = df["Product_Category"].fillna("Unknown")
    df["Product"] = df["Product"].fillna("Unknown")
    df["State"] = df["State"].fillna("Unknown")
    df["Customer_ID"] = df["Customer_ID"].fillna("UNKNOWN")
    for col in OPTIONAL_COLUMNS:
        if col in df.columns:
            df[col] = df[col].fillna("Unknown")

    # Discount: missing -> 0 ; 15 -> 0.15 ; nonsense -> row removed below
    issues["discount_missing_filled"] = int(df["Discount"].isna().sum())
    df["Discount"] = df["Discount"].fillna(0.0)
    pct_style = (df["Discount"] > 1) & (df["Discount"] <= 100)
    issues["discount_percent_converted"] = int(pct_style.sum())
    df.loc[pct_style, "Discount"] = df.loc[pct_style, "Discount"] / 100

    # ---- invalid values (after repairs so we only drop truly broken rows)
    bad_qty = df["Quantity"] <= 0
    bad_sales = df["Sales"] <= 0
    bad_cost = df["Cost"] < 0
    bad_disc = (df["Discount"] < 0) | (df["Discount"] > 1)
    issues["invalid_quantity_removed"] = int(bad_qty.sum())
    issues["invalid_sales_removed"] = int((bad_sales & ~bad_qty).sum())
    issues["invalid_cost_removed"] = int((bad_cost & ~bad_qty & ~bad_sales).sum())
    issues["invalid_discount_removed"] = int((bad_disc & ~bad_qty & ~bad_sales & ~bad_cost).sum())
    df = df[~(bad_qty | bad_sales | bad_cost | bad_disc)].copy()
    df["Quantity"] = df["Quantity"].round().astype(int)

    # Cost: missing -> product's typical cost/sales ratio x Sales (flagged for transparency)
    ratio = (df["Cost"] / df["Sales"]).where(df["Cost"].notna())
    prod_ratio = ratio.groupby(df["Product"]).median()
    global_ratio = ratio.median() if ratio.notna().any() else 0.7
    miss_cost = df["Cost"].isna()
    est = df["Product"].map(prod_ratio).fillna(global_ratio) * df["Sales"]
    df["Cost"] = df["Cost"].fillna(est)
    df["Cost_Imputed"] = miss_cost
    issues["cost_imputed"] = int(miss_cost.sum())

    # Profit: always Sales - Cost (single source of truth)
    recomputed = (df["Sales"] - df["Cost"]).round(2)
    mismatch = df["Profit"].isna() | ((df["Profit"] - recomputed).abs() > 1.0)
    issues["profit_recalculated"] = int(mismatch.sum())
    df["Profit"] = recomputed

    # ---- outliers: judged on the UNIT price (before discount), so legitimate bulk orders are safe.
    # A Sales value typed with two extra zeros shows up as a 100x unit price.
    # Flag = beyond Q3 + 3xIQR ; Remove = beyond Q3 + 10xIQR. Products with < 8 rows are not judged.
    gross_unit = df["Sales"] / df["Quantity"].clip(lower=1) / (1 - df["Discount"].clip(upper=0.95))
    grp = gross_unit.groupby(df["Product"])
    enough = grp.transform("size") >= 8
    q1, q3 = grp.transform(lambda x: x.quantile(0.25)), grp.transform(lambda x: x.quantile(0.75))
    iqr = (q3 - q1).clip(lower=0.05 * grp.transform("median"))
    df["Is_Outlier"] = enough & (gross_unit > q3 + 3 * iqr)
    extreme = enough & (gross_unit > q3 + 10 * iqr)
    issues["outliers_flagged"] = int(df["Is_Outlier"].sum())
    issues["extreme_outliers_removed"] = int(extreme.sum())
    df = df[~extreme]

    df = df.sort_values(["Date", "Order_ID"]).reset_index(drop=True)
    for col in ["Region", "State", "Product_Category", "Product", "Order_ID", "Customer_ID"]:
        df[col] = df[col].astype(str)
    for col in OPTIONAL_COLUMNS:
        if col in df.columns:
            df[col] = df[col].astype(str)

    report["rows_out"] = int(len(df))
    report["rows_removed"] = report["rows_in"] - report["rows_out"]
    report["issues"] = {k: v for k, v in issues.items() if v}
    return df, report
