import sys
import warnings
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
warnings.filterwarnings("ignore")


def make_row(date, order, region="North", product="Laptop", category="Electronics", qty=1,
             sales=1000.0, cost=800.0, discount=0.0, customer="C1", state="Delhi", segment="Consumer"):
    return {"Date": date, "Order_ID": order, "Customer_ID": customer, "Region": region, "State": state,
            "Product_Category": category, "Product": product, "Quantity": qty, "Sales": sales,
            "Cost": cost, "Discount": discount, "Profit": sales - cost, "Customer_Segment": segment}


@pytest.fixture
def small_clean_df():
    """Two months with hand-picked numbers so every expected result is easy to verify by hand.
    Aug: North 1000 + West 1000 = 2000.   Sep: North 1500 + West 900 = 2400 (+20%)."""
    rows = [
        make_row("2026-08-10", "A1", "North", "Laptop", "Electronics", sales=1000, cost=800, customer="C1"),
        make_row("2026-08-11", "A2", "West", "Mouse", "Accessories", sales=1000, cost=500, customer="C2", state="Gujarat"),
        make_row("2026-09-10", "B1", "North", "Laptop", "Electronics", sales=1500, cost=1000, customer="C1"),
        make_row("2026-09-11", "B2", "West", "Mouse", "Accessories", sales=900, cost=500, customer="C3", state="Gujarat"),
    ]
    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"])
    return df


@pytest.fixture(scope="session")
def sample_raw_df():
    from generate_dataset import generate_clean_base, inject_dirt
    return inject_dirt(generate_clean_base(n_rows=1500, seed=42), seed=7)


@pytest.fixture(scope="session")
def sample_clean_big(sample_raw_df):
    from src.data_cleaning import clean_data
    return clean_data(sample_raw_df)


@pytest.fixture(scope="session")
def superstore_raw():
    """A file shaped like Kaggle's Superstore: US dates, no Cost column, several lines per order."""
    from make_superstore_like import build
    return build(n_orders=900, seed=3)


def months_df(values, start="2024-01"):
    """Monthly summary-like frame for forecasting tests."""
    idx = pd.period_range(start, periods=len(values), freq="M")
    return pd.DataFrame({"Month": idx, "Revenue": values})
