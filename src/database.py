"""STEP 16 - SQLite persistence: datasets, cleaned sales rows, analysis runs, AI reports.

Why SQLite?  Zero setup (one file), part of Python's standard library, and the SQL is the same you
would write for PostgreSQL/MySQL. Foreign keys + ON DELETE CASCADE keep the data consistent.

Tables (see docs/DESIGN.md for the ER diagram):
    datasets 1--* sales          cleaned order lines of an uploaded dataset
    datasets 1--* analysis_runs  one run = one month analysed (stores the JSON payload)
    analysis_runs 1--* ai_reports generated reports (LLM or fallback)
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, List, Optional

import pandas as pd

from src.exceptions import DataValidationError

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = str(ROOT / "data" / "insights.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    currency      TEXT    NOT NULL DEFAULT 'INR',
    rows_in       INTEGER,
    rows_out      INTEGER,
    mapping_json  TEXT,
    cleaning_json TEXT,
    created_at    TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS sales (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id       INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    order_date       TEXT    NOT NULL,
    order_id         TEXT    NOT NULL,
    customer_id      TEXT,
    region           TEXT,
    state            TEXT,
    product_category TEXT,
    sub_category     TEXT,
    product          TEXT,
    customer_segment TEXT,
    payment_method   TEXT,
    sales_channel    TEXT,
    quantity         INTEGER,
    sales            REAL    NOT NULL,
    cost             REAL,
    discount         REAL,
    profit           REAL
);
CREATE INDEX IF NOT EXISTS idx_sales_dataset_date ON sales(dataset_id, order_date);
CREATE TABLE IF NOT EXISTS analysis_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id   INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    period       TEXT    NOT NULL,
    payload_json TEXT    NOT NULL,
    created_at   TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS ai_reports (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        INTEGER NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    source        TEXT    NOT NULL,
    model         TEXT,
    report_json   TEXT    NOT NULL,
    warnings_json TEXT,
    created_at    TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

# canonical DataFrame column -> SQL column
COLUMN_MAP = {"Date": "order_date", "Order_ID": "order_id", "Customer_ID": "customer_id", "Region": "region",
              "State": "state", "Product_Category": "product_category", "Sub_Category": "sub_category",
              "Product": "product", "Customer_Segment": "customer_segment", "Payment_Method": "payment_method",
              "Sales_Channel": "sales_channel", "Quantity": "quantity",
              "Sales": "sales", "Cost": "cost", "Discount": "discount", "Profit": "profit"}
GROUPABLE = {"Region": "region", "State": "state", "Product_Category": "product_category",
             "Sub_Category": "sub_category", "Product": "product", "Customer_Segment": "customer_segment",
             "Payment_Method": "payment_method", "Sales_Channel": "sales_channel"}
# columns added after the first release: older database files get them automatically (see _migrate)
ADDED_COLUMNS = {"payment_method": "TEXT", "sales_channel": "TEXT"}


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns that an older database file does not have yet (keeps existing history working)."""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(sales)")}
    for name, sql_type in ADDED_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE sales ADD COLUMN {name} {sql_type}")


class Database:
    def __init__(self, path: Optional[str] = None):
        # DB_PATH is read when the object is created (not at import), so tests and Docker can override it
        self.path = str(path or os.getenv("DB_PATH") or DEFAULT_DB_PATH)
        self._ready = False

    # ------------------------------------------------------------ connection
    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            if not self._ready:
                conn.executescript(SCHEMA)
                _migrate(conn)
                self._ready = True
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------ datasets
    def save_dataset(self, df: pd.DataFrame, name: str, currency: str = "INR", mapping: Optional[Dict] = None,
                     cleaning_report: Optional[Dict] = None, rows_in: Optional[int] = None) -> int:
        report = cleaning_report or {}
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO datasets(name, currency, rows_in, rows_out, mapping_json, cleaning_json) VALUES (?,?,?,?,?,?)",
                (name, currency, rows_in if rows_in is not None else report.get("rows_in"), len(df),
                 json.dumps(mapping or report.get("mapping", {})), json.dumps(report, default=str)))
            dataset_id = cur.lastrowid
            records = []
            for r in df.itertuples(index=False):
                d = r._asdict()
                records.append((dataset_id, pd.Timestamp(d["Date"]).strftime("%Y-%m-%d"), str(d["Order_ID"]),
                                d.get("Customer_ID"), d.get("Region"), d.get("State"), d.get("Product_Category"),
                                d.get("Sub_Category"), d.get("Product"), d.get("Customer_Segment"),
                                d.get("Payment_Method"), d.get("Sales_Channel"), int(d["Quantity"]), float(d["Sales"]), float(d["Cost"]), float(d["Discount"]),
                                float(d["Profit"])))
            conn.executemany(
                "INSERT INTO sales(dataset_id, order_date, order_id, customer_id, region, state, product_category,"
                " sub_category, product, customer_segment, payment_method, sales_channel, quantity, sales, cost,"
                " discount, profit) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", records)
        return int(dataset_id)

    def list_datasets(self) -> List[Dict]:
        with self.connect() as conn:
            rows = conn.execute("SELECT id, name, currency, rows_in, rows_out, created_at FROM datasets ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]

    def get_dataset(self, dataset_id: int) -> Dict:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,)).fetchone()
        if row is None:
            raise DataValidationError(f"Dataset {dataset_id} not found.")
        d = dict(row)
        d["mapping"] = json.loads(d.pop("mapping_json") or "{}")
        d["cleaning_report"] = json.loads(d.pop("cleaning_json") or "{}")
        return d

    def load_sales_df(self, dataset_id: int) -> pd.DataFrame:
        """Rebuild the canonical cleaned DataFrame from the sales table."""
        self.get_dataset(dataset_id)                                   # raises if missing
        with self.connect() as conn:
            df = pd.read_sql_query("SELECT * FROM sales WHERE dataset_id = ? ORDER BY order_date, id", conn, params=(dataset_id,))
        inverse = {v: k for k, v in COLUMN_MAP.items()}
        df = df.rename(columns=inverse).drop(columns=["id", "dataset_id"])
        df["Date"] = pd.to_datetime(df["Date"])
        for optional in ("Customer_Segment", "Sub_Category", "Payment_Method", "Sales_Channel"):
            if df[optional].isna().all():
                df = df.drop(columns=[optional])
        return df

    def delete_dataset(self, dataset_id: int) -> None:
        self.get_dataset(dataset_id)
        with self.connect() as conn:
            conn.execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))     # cascades to sales/runs/reports

    # ------------------------------------------------------------ runs & reports
    def save_run(self, dataset_id: int, period: str, payload: Dict) -> int:
        with self.connect() as conn:
            cur = conn.execute("INSERT INTO analysis_runs(dataset_id, period, payload_json) VALUES (?,?,?)",
                               (dataset_id, period, json.dumps(payload, ensure_ascii=False)))
            return int(cur.lastrowid)

    def get_run(self, run_id: int) -> Dict:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM analysis_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise DataValidationError(f"Run {run_id} not found.")
        d = dict(row)
        d["payload"] = json.loads(d.pop("payload_json"))
        return d

    def list_runs(self, dataset_id: Optional[int] = None) -> List[Dict]:
        sql = "SELECT id, dataset_id, period, created_at FROM analysis_runs"
        args: tuple = ()
        if dataset_id is not None:
            sql, args = sql + " WHERE dataset_id = ?", (dataset_id,)
        with self.connect() as conn:
            return [dict(r) for r in conn.execute(sql + " ORDER BY id DESC", args).fetchall()]

    def save_report(self, run_id: int, report: Dict, meta: Dict) -> int:
        with self.connect() as conn:
            cur = conn.execute("INSERT INTO ai_reports(run_id, source, model, report_json, warnings_json) VALUES (?,?,?,?,?)",
                               (run_id, meta.get("source", "unknown"), meta.get("model"), json.dumps(report, ensure_ascii=False),
                                json.dumps(meta.get("warnings", []))))
            return int(cur.lastrowid)

    def get_latest_report(self, run_id: int) -> Optional[Dict]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM ai_reports WHERE run_id = ? ORDER BY id DESC LIMIT 1", (run_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["report"] = json.loads(d.pop("report_json"))
        d["warnings"] = json.loads(d.pop("warnings_json") or "[]")
        return d

    # ------------------------------------------------------------ SQL analytics (parameterised!)
    def sql_monthly_revenue(self, dataset_id: int) -> List[Dict]:
        """Monthly revenue/profit/orders computed INSIDE the database with GROUP BY."""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT substr(order_date, 1, 7) AS month, ROUND(SUM(sales), 2) AS revenue, ROUND(SUM(profit), 2) AS profit,"
                " COUNT(DISTINCT order_id) AS orders FROM sales WHERE dataset_id = ? GROUP BY month ORDER BY month", (dataset_id,)).fetchall()
        return [dict(r) for r in rows]

    def sql_revenue_by(self, dataset_id: int, dimension: str, month: Optional[str] = None) -> List[Dict]:
        """Revenue and contribution % by a dimension. The column name is WHITELISTED (no SQL injection)."""
        if dimension not in GROUPABLE:
            raise DataValidationError(f"Cannot group by '{dimension}'. Choose from: {', '.join(GROUPABLE)}.")
        col = GROUPABLE[dimension]
        sql = (f"SELECT {col} AS name, ROUND(SUM(sales), 2) AS revenue,"
               f" ROUND(100.0 * SUM(sales) / SUM(SUM(sales)) OVER (), 2) AS contribution_pct"
               f" FROM sales WHERE dataset_id = ?")
        args: list = [dataset_id]
        if month:
            sql += " AND substr(order_date, 1, 7) = ?"
            args.append(month)
        with self.connect() as conn:
            return [dict(r) for r in conn.execute(sql + f" GROUP BY {col} ORDER BY revenue DESC", args).fetchall()]
