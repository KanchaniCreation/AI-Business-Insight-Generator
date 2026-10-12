# Software Requirements Specification (SRS)
**Project:** AI-Powered Automated Business Insight Generator  **Version:** 1.0

## 1. Introduction
### 1.1 Purpose
This document specifies the requirements of a system that converts business sales data into verified analytics and human-readable business insights. It is written for the project guide, evaluators and developers.

### 1.2 Scope
The system ingests Excel/CSV sales data, maps its columns to a standard schema, cleans it, stores it in a database, computes KPIs, trends, growth drivers, forecasts and anomalies, applies rule-based insight detection, and uses an LLM to turn the verified findings into an executive report. It is delivered as a Streamlit web application, a REST API and a command-line tool.

### 1.3 Problem statement
Managers can see *what* changed (for example "revenue +11%") on a dashboard but not *why*. Analysts spend hours writing monthly commentary. Passing a raw spreadsheet to an LLM is unreliable (arithmetic errors, invented causes) and unsafe (private data leaves the system).

### 1.4 Objectives
1. Build a complete analytics pipeline that works on any sales dataset, not one fixed file.
2. Compute every number in Python; allow the LLM only to phrase verified facts.
3. Provide measurable protection against hallucination and a fallback when the AI service fails.
4. Offer a web UI, REST API, persistent history and downloadable reports.

### 1.5 Definitions
| Term | Meaning |
|---|---|
| KPI | Key performance indicator (revenue, profit, margin, orders...) |
| MoM / YoY | Month-over-month / year-over-year growth |
| Driver | A region/product/category that explains a large part of a change |
| Anomaly | A value that is statistically unusual compared with its own history |
| MAPE | Mean absolute percentage error, used to measure forecast accuracy |
| LLM | Large language model accessed through an HTTP API |

## 2. Overall description
### 2.1 Users
| User | Goal |
|---|---|
| Business manager | Understand performance and risks quickly |
| Data analyst | Clean data, explore KPIs, export reports |
| Developer/integrator | Use the REST API from another application |

### 2.2 Operating environment
Python 3.10+, any modern browser, Windows/Linux/macOS. Optional: LLM API key; Docker.

### 2.3 Constraints and assumptions
- Input must contain at least a date, a sales/revenue amount, and either cost or profit.
- One row represents one order line; an order may span several rows.
- The LLM provider is accessed over HTTPS with a user-supplied key.

## 3. Functional requirements
| ID | Requirement | Priority |
|---|---|---|
| FR-01 | Accept .csv and .xlsx uploads and reject empty, corrupt, oversized or unsupported files with a clear message | High |
| FR-02 | Suggest a column mapping automatically (exact and fuzzy alias matching) and let the user edit it | High |
| FR-03 | Derive Cost from Profit (or Profit from Cost), and apply safe defaults for missing optional columns, recording every assumption | High |
| FR-04 | Detect the date convention (day-first / month-first) and allow a manual override | High |
| FR-05 | Clean data: types, dates, duplicates, invalid values, missing values, category standardisation, outliers, with a per-issue report | High |
| FR-06 | Calculate revenue, cost, profit, margin, orders, quantity, customers, AOV, discount rate | High |
| FR-07 | Compare the selected month with the previous month: growth %, margin change in percentage points | High |
| FR-08 | Provide MoM and YoY series and contribution percentages | High |
| FR-09 | Classify trends (increasing, declining, stable, significant change) with safe division | High |
| FR-10 | Rank growth drivers and negative contributors by money contribution for each dimension | High |
| FR-11 | Apply configurable IF/THEN rules to produce labelled insights (growth, decline, margin, discount pressure, concentration, risk, data quality) | High |
| FR-12 | Forecast revenue for the next 3 months with a 95% range and a backtest error | Medium |
| FR-13 | Detect unusual days and unusual monthly movements per dimension | Medium |
| FR-14 | Build a structured JSON payload containing only aggregated facts | High |
| FR-15 | Generate executive summary, drivers, negative contributors, risks and recommended actions with an LLM using only the payload | High |
| FR-16 | Validate the LLM output (JSON schema), verify every number against the payload, retry on failure | High |
| FR-17 | Fall back to a rule-based report if the AI service is unavailable, rate-limited or invalid | High |
| FR-18 | Support multiple currencies (INR, USD, EUR, GBP) | Medium |
| FR-19 | Persist datasets, analysis runs and reports in a database and show history | Medium |
| FR-20 | Expose upload, analyse, insights and report download through a REST API with optional API-key authentication | Medium |
| FR-21 | Export the report as DOCX, Markdown and JSON | High |
| FR-22 | Evaluate AI report quality over many months (hallucination rate, coverage) | Medium |

## 4. Non-functional requirements
| ID | Requirement |
|---|---|
| NFR-01 Reliability | The UI and API must not crash on bad input; domain errors become friendly messages (HTTP 422/404 in the API) |
| NFR-02 Security | API keys come only from environment variables or secret stores; `.env` is git-ignored; raw rows and customer IDs are never sent to the LLM; SQL uses parameters and a column whitelist |
| NFR-03 Accuracy | KPI and growth values are verified by tests against hand-calculated results; SQL aggregates match pandas |
| NFR-04 Performance | A 12,000-row file is cleaned and analysed in a few seconds on a laptop |
| NFR-05 Maintainability | One module per responsibility, pure functions, type hints, 170+ automated tests |
| NFR-06 Usability | Guided flow with auto-detection; each step explains what it changed |
| NFR-07 Portability | Runs on Windows/Linux/macOS; Docker image provided |
| NFR-08 Transparency | Every cleaning fix, mapping assumption and forecast limitation is shown to the user |

## 5. External interfaces
- **User interface:** Streamlit web app (8 tabs). **API:** REST/JSON, OpenAPI docs at `/docs`.
- **LLM interface:** HTTPS POST to a provider endpoint (Anthropic or any OpenAI-compatible API).
- **Database:** SQLite file (`data/insights.db`).
- **Files:** .csv/.xlsx in; .docx/.md/.json out.

## 6. Use cases
| UC | Name | Actor | Main flow |
|---|---|---|---|
| UC-1 | Upload and clean data | Analyst | Upload -> review/adjust column mapping -> run cleaning -> read the fix report |
| UC-2 | View performance | Manager | Pick a month -> read KPIs, charts, trends |
| UC-3 | Understand drivers | Manager | Open Drivers tab -> see top growth drivers and decliners |
| UC-4 | View outlook | Manager | Open Forecast tab -> see projection, range and anomalies |
| UC-5 | Generate AI insights | Manager | Click Generate -> read report -> download DOCX |
| UC-6 | Review history | Analyst | Open History -> reload an old dataset or read a saved report |
| UC-7 | Integrate via API | Developer | POST /datasets -> POST /analyze -> POST /insights -> GET /report |

Alternative flows: invalid file -> error message; mapping incomplete -> button disabled with the reason; API down -> rule-based report with a notice.

## 7. Acceptance criteria
1. A messy file with duplicates, wrong date formats, text numbers and negative values is cleaned and the fix counts are shown.
2. A file with different column names (Kaggle Superstore style, US dates, no Cost column) is analysed correctly after mapping.
3. KPI cards match a hand calculation and the Power BI dashboard.
4. With no API key the app still produces a complete report.
5. In evaluation, AI reports contain 0% unsupported numbers on the sample dataset (rule-based baseline) and any unsupported number produced by an LLM is reported to the user.
