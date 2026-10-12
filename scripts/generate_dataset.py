"""STEP 2 - Generate a realistic (and deliberately messy) sales dataset.

Why synthetic data?  Real company data is private. We simulate a retailer with
built-in business stories (North growing, West declining, Laptops booming,
Accessories shrinking, Diwali-season spike) so that our analytics have real
patterns to discover.  We then inject *dirty* data (typos, duplicates, missing
values...) so that the cleaning pipeline has real work to do.

Run:  python scripts/generate_dataset.py
Out:  data/sales_data.xlsx and data/sales_data.csv  (>= 5,000 rows, 33 months)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# product -> (category, unit_price in INR, cost as fraction of price, monthly growth in demand)
PRODUCTS = {
    "Laptop":       ("Electronics", 55000, 0.78, 0.020),
    "Mobile":       ("Electronics", 22000, 0.80, 0.010),
    "Tablet":       ("Electronics", 18000, 0.78, 0.003),
    "Headphones":   ("Electronics", 3500, 0.60, 0.005),
    "Keyboard":     ("Accessories", 1500, 0.55, -0.005),
    "Mouse":        ("Accessories", 800, 0.52, -0.008),
    "Charger":      ("Accessories", 1200, 0.50, -0.003),
    "USB Cable":    ("Accessories", 400, 0.45, -0.006),
    "Air Purifier": ("Home Appliances", 12000, 0.72, 0.008),
    "Microwave":    ("Home Appliances", 9000, 0.74, 0.000),
    "Mixer Grinder": ("Home Appliances", 3500, 0.65, 0.000),
}
PRODUCT_BASE_WEIGHT = {
    "Laptop": 0.10, "Mobile": 0.14, "Tablet": 0.07, "Headphones": 0.10,
    "Keyboard": 0.09, "Mouse": 0.10, "Charger": 0.10, "USB Cable": 0.09,
    "Air Purifier": 0.05, "Microwave": 0.06, "Mixer Grinder": 0.10,
}
REGIONS = {
    # region: (states, base share, monthly growth)
    "North": (["Delhi", "Punjab", "Haryana", "Uttar Pradesh"], 0.28, 0.025),
    "South": (["Karnataka", "Tamil Nadu", "Kerala", "Telangana"], 0.28, 0.008),
    "East":  (["West Bengal", "Odisha", "Bihar", "Assam"], 0.18, 0.004),
    "West":  (["Maharashtra", "Gujarat", "Rajasthan", "Goa"], 0.26, -0.006),
}
SEASONALITY = {1: 0.90, 2: 0.90, 3: 0.95, 4: 0.95, 5: 1.00, 6: 0.95,
               7: 0.95, 8: 1.00, 9: 1.04, 10: 1.25, 11: 1.20, 12: 1.10}
# "Business events" in the final month so the demo shows clear drivers and risks
LAST_MONTH_REGION_SHOCK = {"North": 1.10, "West": 0.93}
LAST_MONTH_PRODUCT_SHOCK = {"Laptop": 1.10, "Mobile": 1.05, "Mouse": 0.90, "Keyboard": 0.92, "Charger": 0.93}
FLASH_SALE_DAY = "2026-09-17"
FLASH_SALE_ORDERS = 45
SEGMENTS = ["Consumer", "Corporate", "Small Business"]


def generate_clean_base(n_rows: int = 12000, seed: int = 42,
                        start: str = "2024-01-01", end: str = "2026-09-30") -> pd.DataFrame:
    """Create a perfectly clean dataset with built-in business trends."""
    rng = np.random.default_rng(seed)
    months = pd.period_range(start, end, freq="M")
    region_names = list(REGIONS)

    # --- 1) decide how many orders fall in each (month, region) cell
    #     (expected counts + 2% noise, so the business story is visible but not perfectly smooth)
    cells, weights = [], []
    for t, m in enumerate(months):
        for r in region_names:
            _, share, g = REGIONS[r]
            w = SEASONALITY[m.month] * share * (1 + g) ** t
            if t == len(months) - 1:           # last month: North surges, West slips
                w *= LAST_MONTH_REGION_SHOCK.get(r, 1.0)
            cells.append((m, r))
            weights.append(w)
    weights = np.array(weights) / np.sum(weights)
    counts = np.maximum(1, np.round(n_rows * weights * (1 + rng.normal(0, 0.02, len(weights))))).astype(int)

    # --- 2) customers: each belongs to one region and one segment
    n_customers = 1500
    cust_region = rng.choice(region_names, size=n_customers, p=[REGIONS[r][1] for r in region_names])
    cust_segment = rng.choice(SEGMENTS, size=n_customers, p=[0.6, 0.25, 0.15])
    cust_ids = np.array([f"C{i:04d}" for i in range(1, n_customers + 1)])
    pool = {r: np.where(cust_region == r)[0] for r in region_names}

    prod_names = list(PRODUCTS)
    rows = []
    for (month, region), k in zip(cells, counts):
        t = months.get_loc(month)
        # product demand drifts over time; quota-based sampling keeps the mix stable
        pw = np.array([PRODUCT_BASE_WEIGHT[p] * (1 + PRODUCTS[p][3]) ** t for p in prod_names])
        if t == len(months) - 1:
            pw = pw * np.array([LAST_MONTH_PRODUCT_SHOCK.get(p, 1.0) for p in prod_names])
        pw = pw / pw.sum()
        alloc = np.floor(k * pw).astype(int)
        if k - alloc.sum() > 0:
            alloc = alloc + rng.multinomial(k - alloc.sum(), pw)
        products = np.repeat(prod_names, alloc)
        rng.shuffle(products)
        for product in products:
            day = int(rng.integers(1, month.days_in_month + 1))
            date = pd.Timestamp(year=month.year, month=month.month, day=day)
            category, price, cost_ratio, _ = PRODUCTS[product]
            qty = 1 + int(rng.poisson(0.35 if price > 10000 else 1.1))
            # West leans on heavy discounting in recent months (margin-pressure story)
            if region == "West" and t >= len(months) - 3:
                disc = rng.choice([0, 0.05, 0.10, 0.15, 0.20], p=[0.15, 0.2, 0.25, 0.25, 0.15])
            else:
                disc = rng.choice([0, 0.05, 0.10, 0.15, 0.20], p=[0.45, 0.25, 0.18, 0.08, 0.04])
            unit_price = price * rng.uniform(0.95, 1.05)
            sales = round(qty * unit_price * (1 - disc), 2)
            cost = round(qty * price * cost_ratio * rng.uniform(0.97, 1.03), 2)
            cust_idx = rng.choice(pool[region])
            rows.append({
                "Date": date, "Order_ID": "", "Customer_ID": cust_ids[cust_idx],
                "Region": region, "State": rng.choice(REGIONS[region][0]),
                "Product_Category": category, "Product": product, "Quantity": qty,
                "Sales": sales, "Cost": cost, "Discount": float(disc),
                "Profit": round(sales - cost, 2), "Customer_Segment": cust_segment[cust_idx],
            })
    df = pd.DataFrame(rows)
    # "Flash sale" event: one day in the last month with an unusual spike of North orders (anomaly demo)
    last = df[(df["Date"].dt.to_period("M") == months[-1]) & (df["Region"] == "North")]
    flash = rng.choice(last.index, size=min(len(last), FLASH_SALE_ORDERS), replace=False)
    df.loc[flash, "Date"] = pd.Timestamp(FLASH_SALE_DAY)
    df = df.sort_values("Date", kind="stable").reset_index(drop=True)
    df["Order_ID"] = [f"ORD-{i + 1:06d}" for i in range(len(df))]
    return add_channel_and_payment(df, seed)


def add_channel_and_payment(df: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Add Sales_Channel and Payment_Method with realistic shifts over time (online and UPI keep growing).

    Uses its OWN random generator, so adding these columns does not change any other number in the dataset.
    """
    rng = np.random.default_rng(seed + 1000)
    t = ((df["Date"].dt.year - df["Date"].dt.year.min()) * 12 + df["Date"].dt.month - df["Date"].dt.month.min()).to_numpy()
    t = t - t.min()
    u = rng.random(len(df))
    p_online = np.clip(0.28 + 0.012 * t, 0, 0.75)
    p_distributor = 0.12
    df["Sales_Channel"] = np.where(u < p_online, "Online", np.where(u < p_online + p_distributor, "Distributor", "Retail Store"))
    v = rng.random(len(df))
    cuts = np.cumsum([np.clip(0.20 + 0.012 * t, 0, 0.6),                      # UPI grows
                      np.full(len(df), 0.22),                                  # Credit Card
                      np.clip(0.25 - 0.006 * t, 0.05, 1),                      # Cash shrinks
                      np.full(len(df), 0.08)], axis=0)                         # Net Banking, rest = Debit Card
    methods = np.array(["UPI", "Credit Card", "Cash", "Net Banking", "Debit Card"])
    df["Payment_Method"] = methods[(v[None, :] >= cuts).sum(axis=0)]
    return df


def inject_dirt(df: pd.DataFrame, seed: int = 7) -> pd.DataFrame:
    """Corrupt ~5-8% of the data the way real exports are corrupted."""
    rng = np.random.default_rng(seed)
    df = df.copy().astype({"Date": object, "Sales": object, "Quantity": object, "Discount": object})
    n = len(df)

    def idx(rate):
        return rng.choice(n, size=max(1, int(n * rate)), replace=False)

    # missing values
    for col, rate in [("Region", .010), ("Cost", .010), ("Discount", .010),
                      ("Product_Category", .008), ("Profit", .010), ("Customer_Segment", .010)]:
        df.loc[idx(rate), col] = np.nan
    df.loc[idx(.003), "Sales"] = np.nan       # unrecoverable -> row dropped
    df.loc[idx(.002), "Date"] = np.nan
    # invalid dates (text junk and impossible dates)
    bad = idx(.004)
    df.loc[bad, "Date"] = rng.choice(["31-02-2026", "not available", "2026/13/45", "00-00-0000"], size=len(bad))
    # wrong data types (numbers stored as text with symbols)
    for i in idx(.006):
        v = df.at[i, "Sales"]
        if isinstance(v, (int, float)) and v == v:
            df.at[i, "Sales"] = f"₹{v:,.2f}"
    for i in idx(.004):
        v = df.at[i, "Quantity"]
        if isinstance(v, (int, float)) and v == v:
            df.at[i, "Quantity"] = f"{int(v)} "
    # negative / impossible values
    df.loc[idx(.003), "Quantity"] = -1
    neg = idx(.002)
    df.loc[neg, "Sales"] = [(-abs(x) if isinstance(x, (int, float)) and x == x else x) for x in df.loc[neg, "Sales"]]
    df.loc[idx(.003), "Discount"] = 15        # 15 meant 15%, not 1500%
    # inconsistent text
    r = idx(.03)
    df.loc[r, "Region"] = [str(x).upper() if i % 3 == 0 else (f" {str(x).lower()} " if i % 3 == 1 else str(x)[0])
                           for i, x in enumerate(df.loc[r, "Region"])]
    p = idx(.03)
    df.loc[p, "Product"] = [f" {str(x).lower()}" if i % 2 == 0 else str(x).upper() for i, x in enumerate(df.loc[p, "Product"])]
    c = idx(.02)
    df.loc[c, "Product_Category"] = [str(x).lower() for x in df.loc[c, "Product_Category"]]
    # data-entry outliers (extra zeros)
    for i in idx(.002):
        v = df.at[i, "Sales"]
        if isinstance(v, (int, float)) and v == v and v > 0:
            df.at[i, "Sales"] = v * 100
    # exact duplicate rows
    dups = df.iloc[idx(.015)]
    df = pd.concat([df, dups]).sort_index(kind="stable").reset_index(drop=True)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the sample sales dataset")
    parser.add_argument("--rows", type=int, default=12000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--clean", action="store_true", help="skip dirt injection")
    args = parser.parse_args()

    df = generate_clean_base(args.rows, args.seed)
    if not args.clean:
        df = inject_dirt(df, seed=args.seed + 1)
    out = ROOT / "data"
    out.mkdir(exist_ok=True)
    df.to_excel(out / "sales_data.xlsx", index=False)
    df.to_csv(out / "sales_data.csv", index=False)
    print(f"Created {len(df):,} rows -> {out / 'sales_data.xlsx'}")
    print(df.head())


if __name__ == "__main__":
    main()
