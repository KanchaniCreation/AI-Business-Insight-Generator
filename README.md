# AI-Powered Automated Business Insight Generator

An end-to-end business analytics platform. Upload **any** sales dataset (Excel/CSV, for example a Kaggle file), and the system maps its columns, cleans the data, stores it in a database, calculates KPIs, trends and growth drivers, forecasts revenue, detects anomalies, and uses an LLM to write the business commentary. The LLM never sees raw data and every number it writes is checked against the analytics.

> **One-line pitch:** Python calculates the facts; the AI only explains them.

## Problem statement
Dashboards show *what* changed ("revenue +7%"), but managers still need someone to explain *why*, which is slow and repetitive. Sending a spreadsheet straight to an LLM is unreliable (bad arithmetic, invented causes) and unsafe (private data leaves the system).

## Objectives
- Build a real analytics pipeline, not a "paste data into ChatGPT" demo.
- Work on any sales dataset through automatic column mapping.
- Let Python compute every number; let the LLM only phrase verified facts, and measure how well it does.
- Provide a web UI, a REST API, persistent history and downloadable reports.

## Features
| Area | What it does |
|---|---|
| Ingestion and mapping | CSV/XLSX loading with friendly errors; automatic + editable column mapping; derives Cost from Profit; date convention detection (day-first vs US month-first); currency selection (INR/USD/EUR/GBP) |
| Cleaning | types, dates, duplicates, invalid values, missing values (repair or drop with reasons), category standardisation, unit-price outliers; every fix is counted and explained |
| KPIs | revenue, cost, profit, margin, orders, quantity, customers, AOV, discount rate, growth, MoM, YoY, contribution % |
| Trends | growth with safe division; increasing / declining / stable; significant changes |
| Driver analysis | ranks regions, categories, sub-categories, products, customer segments, **sales channels and payment methods** by their money contribution to the change |
| Forecast | next 3 months with a 95% range and a **backtest error (MAPE)**; seasonal method when 2+ years exist |
| Anomaly detection | unusual days (robust z-score) and unusual monthly moves per dimension (history z-score) |
| Rule engine | configurable IF/THEN insights: growth, decline, margin, discount pressure, concentration, risks, forecast, anomalies |
| LLM layer | strict prompt, JSON-only output, schema validation, number verification, retries with backoff, rule-based fallback |
| Evaluation | scores AI reports for hallucinated numbers, driver coverage, causal wording |
| App | Streamlit with 8 tabs: data/mapping/cleaning, KPIs, charts, trends, drivers, forecast and anomalies, AI report, history |
| API | FastAPI with upload, analyse, insights and report download; optional API-key auth; SQL analytics endpoints |
| Persistence | SQLite (datasets, sales, runs, reports) |
| Reports | DOCX (with chart), Markdown, JSON |
| Quality | 170+ pytest tests, GitHub Actions CI, Dockerfile |

## Architecture
```
Excel/CSV -> Ingestion -> Column mapping -> Cleaning -> SQLite
  -> KPIs -> Trends -> Drivers -> Forecast -> Anomalies -> Rule-based insights
  -> Structured JSON -> LLM (validated, number-checked, fallback) -> Streamlit / REST API / DOCX
```
Full diagrams (architecture, DFD, ER, UML) are in [`docs/DESIGN.md`](docs/DESIGN.md).

## Tech stack
Python, Pandas, NumPy, Matplotlib, Plotly, Streamlit, FastAPI, SQLite, Pydantic, Requests (REST client), python-docx, python-dotenv, Pytest, Docker, GitHub Actions, Power BI (DAX).

## Quick start
```bash
python -m venv venv
venv\Scripts\activate            # Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
pytest                            # 170+ tests
streamlit run app/app.py          # web app
```
In the app click **Sample (₹)** or **Superstore-like ($)**, then **Run data cleaning**.

### Other ways to run
```bash
uvicorn api.main:app --reload                 # REST API, docs at http://localhost:8000/docs
python scripts/run_pipeline.py                # CLI: reports/ + cleaned CSV
python scripts/run_pipeline.py --input "Sample - Superstore.csv" --currency USD
python scripts/evaluate_llm.py                # LLM quality evaluation
docker compose up --build                     # app on :8501 and API on :8000
```

## Using a real Kaggle dataset
1. Download a sales dataset (for example **Sample - Superstore**) and upload it in the app.
2. Check the **Column mapping** panel: the app auto-detects `Order Date`, `Sub-Category`, `Product Name`, `Segment`, etc., and derives Cost = Sales - Profit when there is no Cost column.
3. Choose the currency (Superstore is USD) and, if the dates look wrong, set the date format (Superstore is month/day/year; auto-detection normally handles it).
4. Run cleaning and read the notes and fix table. Repeated Order IDs are treated as order lines of one order.

Minimum requirements for any file: a **date** column, a **sales/revenue** column and **either Cost or Profit**. Optional columns (region, category, product, segment, channel, payment method...) each unlock an extra driver analysis; columns the app does not know (for example `Unit_Price`) are ignored.

## Environment variables
```bash
copy .env.example .env             # Mac/Linux: cp .env.example .env
```
```
LLM_PROVIDER=anthropic             # or openai (any OpenAI-compatible endpoint, set LLM_BASE_URL)
LLM_API_KEY=your_key_here
LLM_MODEL=claude-sonnet-5-5
API_KEY=                           # optional: protects the REST API (header X-API-Key)
DB_PATH=                           # optional: SQLite file location
```
Never commit `.env`. Without a key everything works and the report comes from the rule-based engine.

## Dataset
Two sample files are included:
- `data/sales_data.xlsx` (about 12,100 rows, Jan 2024 - Sep 2026): synthetic Indian retail data with built-in business stories and deliberately injected dirty values (duplicates, typos, wrong dates, text numbers, negative quantities, missing values), plus one "flash sale" day as an anomaly. Regenerate with `python scripts/generate_dataset.py`.
- `data/superstore_like_sample.csv`: a file shaped like Kaggle's Superstore (US dates, no Cost column, several lines per order, USD) to demonstrate column mapping. Regenerate with `python scripts/make_superstore_like.py`.

| Column | Meaning | Used for |
|---|---|---|
| Date | order date | trends, MoM/YoY, forecast |
| Order_ID | order identifier | order counts |
| Customer_ID | customer | customer counts |
| Region / State | geography | regional drivers |
| Product_Category / Sub_Category / Product | what was sold | product drivers |
| Quantity | units | volume, unit-price outlier check |
| Sales | revenue after discount | revenue KPIs |
| Cost | cost of goods | profit and margin |
| Discount | fraction (0.10 = 10%) | discount impact |
| Profit | Sales - Cost | profitability |
| Customer_Segment | e.g. Consumer, Corporate | segment drivers |
| Sales_Channel (optional) | e.g. Online, Retail Store, Distributor | channel drivers and mix shifts |
| Payment_Method (optional) | e.g. UPI, Cash, Credit Card | payment-mix drivers |

## Example output (sample dataset, September 2026, rule-based baseline)
> **Revenue** rose 6.7% to ₹1,03,95,191 from ₹97,38,780. **North** (+11.2%, +₹4,81,108) and **Home Appliances** (+21.7%) are growth drivers; **West** declined 9.8% and **Small Business** customers declined 23.2%, both flagged for investigation. Growth is concentrated: North explains 73% of the net change.
>
> **Forecast:** October 2026 projected at about ₹1,20,89,174 (95% range ₹1,13,84,904 to ₹1,27,93,445); backtest error 4.8%.
>
> **Anomaly:** 17 Sep 2026 revenue of ₹10,26,023 versus a typical ₹3,15,526 (robust z-score 4.5).

With an API key the LLM rewrites these verified facts as fluent executive prose. Full examples: `reports/`.

## LLM safety and evaluation
Five layers: only verified facts as input; a strict prompt; JSON validation with one repair retry; automatic check that every number in the answer exists in the input; rule-based fallback on failure. Quality is measured with `scripts/evaluate_llm.py` (see [`docs/LLM_EVALUATION.md`](docs/LLM_EVALUATION.md)); the rule-based baseline scores 0% unsupported numbers.

## Power BI dashboard
See [`powerbi/README.md`](powerbi/README.md): data model, layout and [DAX measures](powerbi/dax_measures.dax). It reads `data/sales_data_clean.csv` (created by `scripts/run_pipeline.py`).

## Project structure
```
data/        sample datasets (raw, cleaned)          notebooks/  EDA.ipynb
src/         ingestion, column_mapper, cleaning, kpi_calculation, trend_analysis, driver_analysis,
             forecasting, anomaly_detection, insight_engine, schema, llm_generator, evaluation,
             report_generator, database, pipeline
app/app.py   Streamlit UI                            api/main.py FastAPI REST API
scripts/     dataset generators, CLI runner, LLM evaluation
powerbi/     guide + DAX                             tests/      pytest suite (170+)
docs/        SRS, DESIGN (DFD/ER/UML), API, TEST_CASES, REPORT_OUTLINE, LLM_EVALUATION, STEPS, INTERVIEW_PREP
Dockerfile, docker-compose.yml, .github/workflows/ci.yml
```

## Screenshots
Add images to `docs/screenshots/` and reference them here:
`![KPI dashboard](docs/screenshots/kpi.png)` `![Drivers](docs/screenshots/drivers.png)` `![Forecast](docs/screenshots/forecast.png)`

## Security notes
API keys only from environment variables or secret stores; `.env` is git-ignored; the LLM receives aggregates only (no customer IDs or raw rows); SQL uses parameters and a column whitelist; optional API-key authentication for the REST API; errors never print secrets.

## Limitations
- Compares a month with the previous month; no significance testing.
- Drivers and anomalies show where change happened, not proven causes.
- Forecasts are trend/seasonality projections; with under 24 months only a linear trend is used.
- Number checking cannot catch a correct number attached to the wrong entity.
- Single-user SQLite; no login in the web app.

## Future improvements
PostgreSQL and background jobs for very large data, multi-period comparison, ML forecasting (Prophet/ARIMA), user accounts, scheduled email reports, "ask your data" chat grounded on the payload, cloud deployment.
