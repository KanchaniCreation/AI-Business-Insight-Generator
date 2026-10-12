# Test cases and results

**Automated:** 185 pytest tests, all passing (`pytest`). **Manual:** a short checklist for the UI (fill in the Result column during your demo or viva).

## A. Automated tests by module
| Test file | Tests | What it proves |
|---|---|---|
| `test_data_ingestion.py` | 6 | empty file, wrong extension, fake Excel, header-only CSV, missing path rejected with clear errors |
| `test_data_cleaning.py` | 26 | duplicates, invalid/US/ambiguous dates, negatives, currency text, casing, imputation, outliers, order lines, optional columns |
| `test_column_mapper.py` | 15 | auto-detect Superstore columns, fuzzy typos, derived Cost/Profit, defaults, wrong or duplicate mapping rejected, US dates not flipped |
| `test_kpi_calculation.py` | 10 | hand-calculated KPIs, empty frame, growth, margin in percentage points, contribution sums to 100% |
| `test_trend_analysis.py` | 16 | growth formula, division by zero, classification, series trend, period selection, partial month |
| `test_driver_analysis.py` | 6 | top positive/negative drivers, ranking by money not percent, NaN never leaks |
| `test_insight_engine.py` | 15 | every rule, thresholds configurable, forecast and anomaly rules |
| `test_forecasting.py` | 8 | trend extrapolation, seasonal peak learning, range validity, too little history, gaps, backtest |
| `test_anomaly_detection.py` | 9 | spike/drop detection, noise ignored, short history, high-cardinality skipped |
| `test_pipeline_and_schema.py` | 9 | JSON serialisable, no NaN, no raw rows, currency applied, short history |
| `test_llm_generator.py` | 28 | JSON parsing, retries, 429, 401, network failure, bad JSON repair, fallback, hallucinated number warning, key from env |
| `test_evaluation.py` | 6 | faithful report scores clean, hallucination/causal/leakage detected |
| `test_database.py` | 12 | round trip, SQL equals pandas, SQL-injection whitelist, cascade delete, missing ids, new columns, automatic migration of old database files |
| `test_api.py` | 12 | full upload-analyze-insights-report flow, bad uploads, mapping, currency, API key |
| `test_utils.py` | 5 | Indian grouping, currency switch, safe divide, growth |
| `test_app_smoke.py` | 2 | the real Streamlit script runs end to end on both sample datasets without exceptions |

## B. Selected test cases (for the project report)
| ID | Module | Input | Expected result | Status |
|---|---|---|---|---|
| TC-01 | Ingestion | empty .csv | "The uploaded file is empty." | Pass |
| TC-02 | Ingestion | text file renamed .xlsx | "Could not read the file..." | Pass |
| TC-03 | Mapping | Superstore-style columns | Date=Order Date, Product=Product Name, Cost derived from Profit | Pass |
| TC-04 | Mapping | no Sales column | MappingError naming the missing field | Pass |
| TC-05 | Cleaning | `31-02-2026`, `garbage` dates | rows removed, count reported | Pass |
| TC-06 | Cleaning | `12/25/2026` and `1/5/2026` | month-first detected; 25 Dec and 5 Jan | Pass |
| TC-07 | Cleaning | quantity -1 or 0 | row removed | Pass |
| TC-08 | Cleaning | quantity 50 with normal unit price | row kept (legitimate bulk order) | Pass |
| TC-09 | Cleaning | sales typed 100x too large | row removed as outlier | Pass |
| TC-10 | KPI | two-month fixture | revenue growth +20%, margin +2.5 pp | Pass |
| TC-11 | Growth | previous = 0 | `None` (undefined), no crash | Pass |
| TC-12 | Drivers | North 1000->1500, West 1000->900 | North top driver (+50%), West top decliner (-10%) | Pass |
| TC-13 | Forecast | < 6 months of data | "At least 6 months..." message, no crash | Pass |
| TC-14 | Anomaly | one day with 8x revenue | flagged as spike | Pass |
| TC-15 | LLM | API returns 429 three times | rule-based fallback and a notice | Pass |
| TC-16 | LLM | model returns text instead of JSON | one repair retry, then fallback | Pass |
| TC-17 | LLM | answer contains 87.3% not in input | warning listing the number | Pass |
| TC-18 | API | wrong/missing X-API-Key when API_KEY set | HTTP 401 | Pass |
| TC-19 | Database | delete dataset | runs and reports deleted (cascade) | Pass |
| TC-20 | Database | group by `region; DROP TABLE sales;--` | rejected, no SQL executed | Pass |

## C. Manual UI checklist
| ID | Steps | Expected | Result |
|---|---|---|---|
| M-01 | Start app, click **Sample (₹)** | preview of raw data appears | |
| M-02 | Click **Run data cleaning** | row counts and fix table appear | |
| M-03 | Click **Superstore-like ($)** and run cleaning | mapping auto-filled, notes mention derived Cost, `$` amounts | |
| M-04 | Clear the Sales mapping | warning appears and cleaning button is disabled | |
| M-05 | Change "Analyse month" | KPIs and drivers update | |
| M-06 | Open **Forecast & Anomalies** | forecast chart with range band; anomaly tables | |
| M-07 | Click **Generate AI Insights** without a key | fallback notice and complete report | |
| M-08 | Download DOCX | opens in Word with tables and chart | |
| M-09 | Open **History** | saved dataset and run listed; load and delete work | |
| M-10 | Upload an empty file | red error message, app keeps working | |
