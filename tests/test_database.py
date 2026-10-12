import pandas as pd
import pytest

from src.database import Database
from src.exceptions import DataValidationError
from src.pipeline import run_analysis


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "t.db"))


def test_round_trip_preserves_data(db, small_clean_df):
    did = db.save_dataset(small_clean_df, "demo.csv", "INR", {"Date": "Date"}, {"rows_in": 4, "issues": {}, "notes": []})
    loaded = db.load_sales_df(did)
    assert len(loaded) == 4 and loaded["Sales"].sum() == small_clean_df["Sales"].sum()
    assert set(loaded["Region"]) == {"North", "West"} and pd.api.types.is_datetime64_any_dtype(loaded["Date"])


def test_analysis_on_loaded_data_matches_original(db, small_clean_df):
    did = db.save_dataset(small_clean_df, "demo.csv")
    a, b = run_analysis(small_clean_df).payload["kpis"], run_analysis(db.load_sales_df(did)).payload["kpis"]
    assert a["revenue"] == b["revenue"] and a["orders"] == b["orders"]


def test_sql_monthly_revenue_matches_pandas(db, sample_clean_big):
    clean, _ = sample_clean_big
    did = db.save_dataset(clean, "sample")
    sql = {r["month"]: r["revenue"] for r in db.sql_monthly_revenue(did)}
    pdm = clean.groupby(clean["Date"].dt.strftime("%Y-%m"))["Sales"].sum().round(2)
    assert len(sql) == len(pdm) and all(abs(sql[m] - pdm[m]) < 0.05 for m in pdm.index)


def test_sql_breakdown_contribution_sums_to_100(db, small_clean_df):
    did = db.save_dataset(small_clean_df, "demo")
    rows = db.sql_revenue_by(did, "Region", "2026-09")
    assert abs(sum(r["contribution_pct"] for r in rows) - 100) < 0.1 and rows[0]["name"] == "North"


def test_group_by_is_whitelisted_against_sql_injection(db, small_clean_df):
    did = db.save_dataset(small_clean_df, "demo")
    with pytest.raises(DataValidationError):
        db.sql_revenue_by(did, "region; DROP TABLE sales;--")


def test_runs_and_reports_are_stored(db, small_clean_df):
    did = db.save_dataset(small_clean_df, "demo")
    run_id = db.save_run(did, "2026-09", {"hello": "world"})
    assert db.get_run(run_id)["payload"] == {"hello": "world"} and db.list_runs(did)[0]["id"] == run_id
    assert db.get_latest_report(run_id) is None
    db.save_report(run_id, {"executive_summary": "x" * 20}, {"source": "fallback", "warnings": ["w"]})
    stored = db.get_latest_report(run_id)
    assert stored["source"] == "fallback" and stored["warnings"] == ["w"]


def test_deleting_dataset_cascades(db, small_clean_df):
    did = db.save_dataset(small_clean_df, "demo")
    run_id = db.save_run(did, "2026-09", {})
    db.delete_dataset(did)
    with pytest.raises(DataValidationError):
        db.get_run(run_id)
    assert db.list_datasets() == []


def test_missing_ids_raise_clear_errors(db):
    for call in (lambda: db.get_dataset(5), lambda: db.get_run(5), lambda: db.load_sales_df(5)):
        with pytest.raises(DataValidationError, match="not found"):
            call()


def test_optional_columns_survive_round_trip(db, small_clean_df):
    did = db.save_dataset(small_clean_df.drop(columns=["Customer_Segment"]), "demo")
    assert "Customer_Segment" not in db.load_sales_df(did).columns


def test_db_path_is_read_from_environment_at_creation(tmp_path, monkeypatch, small_clean_df):
    target = tmp_path / "custom.db"
    monkeypatch.setenv("DB_PATH", str(target))
    Database().save_dataset(small_clean_df, "demo")
    assert target.exists()


def test_channel_and_payment_survive_round_trip(db, small_clean_df):
    df = small_clean_df.copy()
    df["Sales_Channel"], df["Payment_Method"] = "Online", "UPI"
    loaded = db.load_sales_df(db.save_dataset(df, "demo"))
    assert set(loaded["Sales_Channel"]) == {"Online"} and set(loaded["Payment_Method"]) == {"UPI"}
    rows = db.sql_revenue_by(db.save_dataset(df, "again"), "Sales_Channel")
    assert rows[0]["name"] == "Online" and rows[0]["contribution_pct"] == 100


def test_old_database_file_is_migrated_automatically(tmp_path, small_clean_df):
    """A database created by the first release (no channel/payment columns) must keep working."""
    import sqlite3
    path = str(tmp_path / "old.db")
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE datasets (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, currency TEXT NOT NULL DEFAULT 'INR',
            rows_in INTEGER, rows_out INTEGER, mapping_json TEXT, cleaning_json TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE sales (id INTEGER PRIMARY KEY AUTOINCREMENT, dataset_id INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
            order_date TEXT NOT NULL, order_id TEXT NOT NULL, customer_id TEXT, region TEXT, state TEXT, product_category TEXT,
            sub_category TEXT, product TEXT, customer_segment TEXT, quantity INTEGER, sales REAL NOT NULL, cost REAL, discount REAL, profit REAL);
        INSERT INTO datasets(name) VALUES ('legacy');
        INSERT INTO sales(dataset_id, order_date, order_id, region, quantity, sales, cost, discount, profit)
            VALUES (1, '2026-01-05', 'X1', 'North', 1, 100, 60, 0, 40);
    """)
    conn.commit(); conn.close()
    old = Database(path)
    legacy = old.load_sales_df(1)                                         # old row still loads
    assert len(legacy) == 1 and "Sales_Channel" not in legacy.columns
    df = small_clean_df.copy()
    df["Sales_Channel"], df["Payment_Method"] = "Online", "UPI"
    new_id = old.save_dataset(df, "new")                                  # and new data with the new columns saves fine
    assert set(old.load_sales_df(new_id)["Sales_Channel"]) == {"Online"}
