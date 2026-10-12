"""Column mapping: make the project work on ANY sales file (e.g. Kaggle datasets).

Real files rarely use our names (Order_ID, Sales...). Superstore calls them
'Order ID', 'Order Date', 'Category', 'Sub-Category', 'Segment' and has no Cost column.

Flow:  suggest_mapping(df)  ->  user can edit it in the UI  ->  apply_mapping(df, mapping)
The result has our canonical column names, so the rest of the pipeline never changes.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

import pandas as pd

from src.data_cleaning import parse_dates, to_numeric_clean
from src.exceptions import DataValidationError

# canonical field -> accepted aliases (normalised: lower-case, no punctuation). Earlier = higher priority.
CANONICAL_ALIASES: Dict[str, List[str]] = {
    "Date": ["date", "order date", "orderdate", "invoice date", "invoicedate", "transaction date", "sale date",
             "sales date", "purchase date", "order day", "datetime", "timestamp", "day"],
    "Sales": ["sales", "revenue", "sales amount", "total sales", "net sales", "amount", "total amount", "total price",
              "line total", "turnover", "order value", "gross sales"],
    "Order_ID": ["order id", "orderid", "order no", "order number", "order", "invoice no", "invoice number",
                 "invoiceno", "invoice", "transaction id", "bill no", "bill number"],
    "Customer_ID": ["customer id", "customerid", "cust id", "client id", "customer no", "customer number",
                    "user id", "customer code", "customer"],
    "Region": ["region", "sales region", "zone", "area", "territory"],
    "State": ["state", "province", "state province", "state name"],
    "Product_Category": ["category", "product category", "item category", "department", "product line",
                         "product type", "product group"],
    "Sub_Category": ["sub category", "subcategory", "sub cat", "product sub category"],
    "Product": ["product", "product name", "item name", "item", "description", "sku", "product description",
                "product id", "productid"],
    "Quantity": ["quantity", "qty", "units", "units sold", "quantity ordered", "order quantity", "unit sold"],
    "Cost": ["cost", "total cost", "cogs", "cost price", "cost of goods sold"],
    "Discount": ["discount", "discount %", "discount pct", "discount rate", "discount percent", "disc"],
    "Profit": ["profit", "net profit", "gross profit", "profit amount", "total profit"],
    "Customer_Segment": ["segment", "customer segment", "customer type", "client segment", "customer category"],
    "Payment_Method": ["payment method", "payment mode", "payment type", "mode of payment", "pay mode", "payment"],
    "Sales_Channel": ["sales channel", "channel", "order channel", "sales mode", "order source", "store type", "platform"],
}
FIELD_ORDER = ["Date", "Sales", "Order_ID", "Customer_ID", "Region", "State", "Product_Category", "Sub_Category",
               "Product", "Quantity", "Cost", "Discount", "Profit", "Customer_Segment", "Sales_Channel", "Payment_Method"]
REQUIRED_FIELDS = ["Date", "Sales"]          # plus: Cost OR Profit
FINAL_ORDER = ["Date", "Order_ID", "Customer_ID", "Region", "State", "Product_Category", "Product",
               "Quantity", "Sales", "Cost", "Discount", "Profit", "Customer_Segment", "Sub_Category", "Sales_Channel", "Payment_Method"]
FUZZY_CUTOFF = 0.86


class MappingError(DataValidationError):
    """The column mapping is incomplete or does not fit the data."""


def _norm(name) -> str:
    s = re.sub(r"[_\-/\\]+", " ", str(name).strip().lower())
    s = re.sub(r"[^a-z0-9% ]+", "", s)
    return re.sub(r"\s+", " ", s).strip()


def suggest_mapping(df: pd.DataFrame) -> Dict[str, Optional[str]]:
    """Guess which source column feeds each canonical field (None = not found)."""
    norm = {col: _norm(col) for col in df.columns}
    used: set = set()
    mapping: Dict[str, Optional[str]] = {f: None for f in FIELD_ORDER}
    # pass 1: exact (normalised) alias match, in alias-priority order
    for field in FIELD_ORDER:
        for alias in CANONICAL_ALIASES[field]:
            hit = next((c for c, n in norm.items() if n == _norm(alias) and c not in used), None)
            if hit is not None:
                mapping[field] = hit
                used.add(hit)
                break
    # pass 2: fuzzy match (typos such as 'Quantiy', 'Custmer ID') for fields still unmapped
    for field in FIELD_ORDER:
        if mapping[field] is not None:
            continue
        best, best_score = None, 0.0
        for col, n in norm.items():
            if col in used:
                continue
            for alias in CANONICAL_ALIASES[field]:
                score = SequenceMatcher(None, n, _norm(alias)).ratio()
                if score > best_score:
                    best, best_score = col, score
        if best is not None and best_score >= FUZZY_CUTOFF:
            mapping[field] = best
            used.add(best)
    return mapping


def mapping_problems(mapping: Dict[str, Optional[str]]) -> List[str]:
    """Human-readable list of what is still missing (empty list = mapping is usable)."""
    m = {k: v for k, v in mapping.items() if v}
    problems = [f"'{f}' column is required" for f in REQUIRED_FIELDS if f not in m]
    if "Cost" not in m and "Profit" not in m:
        problems.append("either 'Cost' or 'Profit' column is required (needed for profit and margin)")
    return problems


def apply_mapping(df: pd.DataFrame, mapping: Dict[str, Optional[str]]) -> Tuple[pd.DataFrame, List[str]]:
    """Build the canonical DataFrame. Returns (canonical_df, notes explaining every assumption)."""
    notes: List[str] = []
    m = {k: v for k, v in mapping.items() if v and k in FIELD_ORDER}
    problems = mapping_problems(m)
    if problems:
        raise MappingError("Cannot map the dataset: " + "; ".join(problems) + ".")
    unknown = [c for c in m.values() if c not in df.columns]
    if unknown:
        raise MappingError(f"Mapped column(s) not found in the file: {', '.join(map(str, unknown))}.")
    if len(set(m.values())) != len(m):
        raise MappingError("The same source column is mapped to more than one field.")

    out = pd.DataFrame({canon: df[src] for canon, src in m.items()})

    # sanity checks so a wrong mapping fails loudly instead of producing nonsense
    sales_ok = to_numeric_clean(out["Sales"]).notna().mean()
    if sales_ok < 0.5:
        raise MappingError(f"Column '{m['Sales']}' does not look numeric, so it cannot be Sales/Revenue.")
    date_ok = parse_dates(out["Date"]).notna().mean()
    if date_ok < 0.5:
        raise MappingError(f"Column '{m['Date']}' does not look like a date column.")

    if "Cost" not in out:
        out["Cost"] = to_numeric_clean(out["Sales"]) - to_numeric_clean(out["Profit"])
        notes.append(f"No Cost column: Cost was derived as Sales - Profit (from '{m['Profit']}').")
    if "Profit" not in out:
        out["Profit"] = to_numeric_clean(out["Sales"]) - to_numeric_clean(out["Cost"])
        notes.append(f"No Profit column: Profit was derived as Sales - Cost (from '{m['Cost']}').")
    if "Order_ID" not in out:
        out["Order_ID"] = [f"ROW-{i + 1}" for i in range(len(out))]
        notes.append("No Order ID column: every row is treated as one order.")
    if "Quantity" not in out:
        out["Quantity"] = 1
        notes.append("No Quantity column: quantity was set to 1 per row.")
    if "Discount" not in out:
        out["Discount"] = 0.0
        notes.append("No Discount column: discount was assumed to be 0.")
    for col, default in {"Customer_ID": "UNKNOWN", "Region": "Unknown", "State": "Unknown",
                         "Product_Category": "Unknown", "Product": "Unknown"}.items():
        if col not in out:
            out[col] = default
            notes.append(f"No {col.replace('_', ' ')} column: analysis by {col.replace('_', ' ')} is unavailable.")
    cols = [c for c in FINAL_ORDER if c in out.columns]
    return out[cols].reset_index(drop=True), notes
