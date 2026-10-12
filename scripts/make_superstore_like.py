"""Create a file that LOOKS like Kaggle's "Sample - Superstore" dataset, to test column mapping.

Same column names (Row ID, Order ID, Order Date, Ship Mode, Segment, Category, Sub-Category,
Product Name ...), US-style dates (month/day/year), NO Cost column, USD amounts, several
rows per Order ID, and latin-1 encoding - the things that usually break naive pipelines.
Not real Kaggle data; use the real file for the actual demo.

Run:  python scripts/make_superstore_like.py   ->  data/superstore_like_sample.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

CATALOG = {  # (category, sub-category): [(product name, unit price, margin)]
    ("Technology", "Phones"): [("Apple iPhone 13", 850, 0.12), ("Samsung Galaxy S21", 700, 0.10), ("Nokia Smart Phone", 300, 0.18)],
    ("Technology", "Accessories"): [("Logitech Wireless Mouse", 40, 0.30), ("Kingston 32GB USB Drive", 18, 0.28)],
    ("Technology", "Copiers"): [("Canon Imaging Copier", 2400, 0.35)],
    ("Furniture", "Chairs"): [("Ergonomic Office Chair", 260, 0.08), ("Executive Leather Chair", 420, 0.05)],
    ("Furniture", "Tables"): [("Conference Table 8ft", 780, -0.06), ("Round Meeting Table", 520, -0.04)],
    ("Furniture", "Bookcases"): [("Oak Bookcase 5-Shelf", 330, 0.04)],
    ("Office Supplies", "Paper"): [("Xerox Copy Paper 500", 24, 0.45), ("Recycled Notepads", 9, 0.42)],
    ("Office Supplies", "Binders"): [("Avery Heavy-Duty Binder", 14, 0.38), ("Cardinal Ring Binder", 8, 0.35)],
    ("Office Supplies", "Storage"): [("Fellowes Storage Box", 36, 0.20)],
}
REGION_STATES = {"West": ["California", "Washington", "Oregon"], "East": ["New York", "Pennsylvania", "Ohio"],
                 "Central": ["Texas", "Illinois", "Michigan"], "South": ["Florida", "Georgia", "Virginia"]}
SEGMENTS = ["Consumer", "Corporate", "Home Office"]


def build(n_orders: int = 2600, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    months = pd.period_range("2014-01", "2017-12", freq="M")
    season = {1: .6, 2: .6, 3: .9, 4: .8, 5: .85, 6: .9, 7: .85, 8: .9, 9: 1.3, 10: 1.0, 11: 1.6, 12: 1.7}
    weights = np.array([season[m.month] * (1 + 0.05) ** i for i, m in enumerate(months)])
    weights = weights / weights.sum()
    products = [(c, s, *p) for (c, s), items in CATALOG.items() for p in items]
    customers = [f"{a}{b}-{n}" for a, b, n in zip(rng.choice(list("ABCDEFGHJKLMNPRS"), 700),
                                                    rng.choice(list("ABCDEFGHJKLMNPRS"), 700),
                                                    rng.integers(10000, 99999, 700))]
    segment_of = {c: SEGMENTS[i % 3] for i, c in enumerate(customers)}      # deterministic
    product_id = {p[2]: f"{p[0][:3].upper()}-{p[1][:2].upper()}-{10000 + 37 * i}" for i, p in enumerate(products)}
    rows, row_id = [], 1
    for i in range(n_orders):
        month = months[int(rng.choice(len(months), p=weights))]
        date = pd.Timestamp(year=month.year, month=month.month, day=int(rng.integers(1, month.days_in_month + 1)))
        region = rng.choice(list(REGION_STATES), p=[0.32, 0.29, 0.23, 0.16])
        cust = customers[int(rng.integers(0, len(customers)))]
        seg = segment_of[cust]
        for _ in range(int(rng.integers(1, 5))):                 # 1-4 lines per order
            cat, sub, name, price, margin = products[int(rng.integers(0, len(products)))]
            qty = int(rng.integers(1, 8))
            disc = float(rng.choice([0, 0, 0, 0.1, 0.2, 0.3, 0.5, 0.7], p=[.3, .2, .1, .1, .1, .1, .06, .04]))
            sales = round(price * qty * (1 - disc) * rng.uniform(0.95, 1.05), 4)
            profit = round(sales * (margin - disc * 0.55) + rng.normal(0, sales * 0.03), 4)
            rows.append({
                "Row ID": row_id, "Order ID": f"US-{date.year}-{100000 + i}", "Order Date": f"{date.month}/{date.day}/{date.year}",
                "Ship Date": f"{(date + pd.Timedelta(days=4)).month}/{(date + pd.Timedelta(days=4)).day}/{(date + pd.Timedelta(days=4)).year}",
                "Ship Mode": rng.choice(["Standard Class", "Second Class", "First Class", "Same Day"]),
                "Customer ID": cust, "Customer Name": "Café Customer " + cust[-3:], "Segment": seg,
                "Country": "United States", "City": "Springfield", "State": rng.choice(REGION_STATES[region]),
                "Postal Code": int(rng.integers(10000, 99999)), "Region": region,
                "Product ID": product_id[name],
                "Category": cat, "Sub-Category": sub, "Product Name": name,
                "Sales": sales, "Quantity": qty, "Discount": disc, "Profit": profit,
            })
            row_id += 1
    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = build()
    out = ROOT / "data" / "superstore_like_sample.csv"
    df.to_csv(out, index=False, encoding="latin-1")   # real Superstore is not UTF-8 either
    print(f"Created {len(df):,} rows -> {out}")
