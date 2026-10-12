"""Run the whole pipeline from the command line (handy for demos, cron jobs and debugging).

    python scripts/run_pipeline.py                          # latest month in data/sales_data.xlsx
    python scripts/run_pipeline.py --input my.csv --period 2026-08
    python scripts/run_pipeline.py --input "Sample - Superstore.csv" --currency USD
    python scripts/run_pipeline.py --input my.csv --map "Date=Order Date" --map "Sales=Revenue" --month-first
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data_ingestion import load_dataset
from src.exceptions import InsightGeneratorError
from src.llm_generator import generate_insights
from src.column_mapper import suggest_mapping
from src.pipeline import prepare_dataset, run_analysis
from src.report_generator import build_docx, build_markdown


def main() -> int:
    ap = argparse.ArgumentParser(description="AI Business Insight Generator - CLI")
    ap.add_argument("--input", default=str(ROOT / "data" / "sales_data.xlsx"))
    ap.add_argument("--period", default=None, help="month to analyse, e.g. 2026-09 (default: latest)")
    ap.add_argument("--out", default=str(ROOT / "reports"))
    ap.add_argument("--currency", default="INR", choices=["INR", "USD", "EUR", "GBP"])
    ap.add_argument("--map", action="append", default=[], metavar="FIELD=COLUMN",
                    help="override the auto column mapping, e.g. --map \"Date=Order Date\" (repeatable)")
    ap.add_argument("--month-first", action="store_true", help="dates are month/day/year (US style)")
    ap.add_argument("--day-first", action="store_true", help="dates are day/month/year")
    ap.add_argument("--save-db", action="store_true", help="also store the dataset and run in the SQLite history")
    args = ap.parse_args()

    try:
        raw = load_dataset(args.input)
        mapping = suggest_mapping(raw)
        for item in args.map:
            field, _, column = item.partition("=")
            mapping[field.strip()] = column.strip() or None
        dayfirst = True if args.day_first else (False if args.month_first else None)
        clean, cleaning = prepare_dataset(raw, mapping, dayfirst)
        print(f"[1/4] Loaded {cleaning['rows_in']:,} rows, kept {cleaning['rows_out']:,} after cleaning "
              f"(dates: {cleaning['date_format']})")
        for note in cleaning["notes"]:
            print("      note:", note)
        result = run_analysis(clean, args.period, currency=args.currency)
        print(f"[2/4] Analysed {result.current_period} vs {result.previous_period}: "
              f"{len(result.insights)} rule-based insights")
        report, meta = generate_insights(result.payload)
        print(f"[3/4] Insights source: {meta['source']}")
        for w in meta["warnings"]:
            print("      note:", w)
    except InsightGeneratorError as exc:
        print(f"ERROR: {exc}")
        return 1

    if args.save_db:
        from src.database import Database
        db = Database()
        dataset_id = db.save_dataset(clean, Path(args.input).name, args.currency, cleaning["mapping"], cleaning, cleaning["rows_in"])
        run_id = db.save_run(dataset_id, str(result.current_period), result.payload)
        db.save_report(run_id, report.model_dump(), meta)
        print(f"      saved to database: dataset #{dataset_id}, run #{run_id}")

    out = Path(args.out)
    out.mkdir(exist_ok=True)
    tag = str(result.current_period)
    (out / f"business_report_{tag}.docx").write_bytes(build_docx(result.payload, report, meta, result.monthly, cleaning))
    (out / f"business_report_{tag}.md").write_text(build_markdown(result.payload, report, meta), encoding="utf-8")
    (out / f"insight_payload_{tag}.json").write_text(json.dumps(result.payload, indent=2, ensure_ascii=False), encoding="utf-8")
    clean_path = ROOT / "data" / f"{Path(args.input).stem}_clean.csv"      # e.g. data/sales_data_clean.csv (Power BI input)
    clean.to_csv(clean_path, index=False)
    print(f"[4/4] Reports written to {out}; cleaned data saved to {clean_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
