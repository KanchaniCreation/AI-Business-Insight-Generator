# Interview Preparation

## A. 2-minute explanation
"I built an **AI-Powered Automated Business Insight Generator**. A manager uploads sales data in Excel or CSV. My Python pipeline cleans it with Pandas, calculates KPIs like revenue, profit, margin, orders and AOV, and compares the latest month with the previous one. The key part is **driver analysis**: it breaks the overall change down by region, product, category and customer segment, ranks each by its rupee contribution, and a rule engine labels growth drivers, risks and anomalies. Only these *verified facts* go to an LLM as a small structured JSON, and the LLM turns them into an executive summary, drivers, risks and recommended actions. A Streamlit app shows KPIs, charts and the AI report with DOCX download, and a Power BI dashboard on the same cleaned data gives interactive slicing. Because the LLM never sees raw data and its numbers are verified against the input, hallucination risk is low, and if the API is down the app still produces a rule-based report. It also forecasts the next three months with a backtested error, flags anomalies, stores everything in SQLite, exposes a FastAPI REST API, works on any dataset through column mapping, and has 170+ pytest tests."

## B. 5-minute explanation (talk track)
1. **Problem (30s):** Managers know *what* changed (revenue +11%) but not *why*; analysts spend hours writing the same commentary every month.
2. **Data (30s):** ~12,000 synthetic order lines over 33 months with deliberately dirty values; 12 core columns; Indian currency formatting.
3. **Cleaning (45s):** standardize columns, parse mixed date formats, convert text numbers, fix casing, drop duplicates/invalid rows, repair Region from State, impute missing Cost with a flag, recompute Profit, flag/remove outliers by IQR. Every fix is counted in a report.
4. **KPIs & trends (45s):** reusable functions; growth = (cur-prev)/prev x100 with zero-safe handling; margin change in percentage points; MoM and YoY; trend direction by linear fit over the last 6 months.
5. **Driver analysis (60s):** total change equals the sum of member changes, so rank members by rupee contribution (not % growth). Example: North +11.2% explains about 73% of the net growth, while West -9.8% is a drag worth investigating.
6. **Rules and JSON (30s):** IF/THEN rules with configurable thresholds produce labelled insights; JSON schema has only aggregates plus pre-formatted display values.
7. **LLM (45s):** strict system prompt, JSON-only output, Pydantic validation, number verification, retries with backoff, fallback report.
8. **App/BI (30s):** Streamlit tabs, error handling, `.env` secrets; Power BI star schema with DAX.
9. **Limitations and next steps (15s):** single-month comparison, synthetic data, no causal inference; next: forecasting, SQL backend, scheduled emails.

## C. Architecture
```
Excel/CSV -> data_ingestion -> data_cleaning -> (EDA)
  -> kpi_calculation -> trend_analysis -> driver_analysis -> insight_engine
  -> schema (structured JSON) -> llm_generator (prompt, REST call, validate, number-check, fallback)
  -> Streamlit app + report_generator (DOCX/MD)         Power BI uses the same cleaned CSV
```
Design principles: **separation of concerns** (each module one job), **pure functions** (DataFrame in, numbers/dicts out, so easy to test), **deterministic facts first, probabilistic language last**, **fail soft** (custom exceptions, friendly messages, fallback).

## D. Questions and answers

### Project-specific
**1. Why did you use Python?** Best ecosystem for data work (Pandas/NumPy), easy API integration, quick to prototype UIs with Streamlit, and the same code is testable and reusable in a pipeline.

**2. Why did you use an LLM?** Calculations are done by code; the LLM only does what it is good at: turning structured numbers into readable business language and prioritising what to say. It saves the manual commentary writing and adapts wording to different data.

**3. Why not send raw data directly to the LLM?** (a) Accuracy: LLMs are unreliable at arithmetic over thousands of rows. (b) Context limits and cost. (c) Privacy: raw customer/order data should not leave the system. (d) Auditability: with a pre-computed fact JSON, every claim is traceable.

**4. How do you prevent hallucinations?** Five layers: only verified facts as input; prompt forbids invented numbers/causes and unsupported causal claims; low temperature; JSON schema validation with a repair retry; programmatic check that every number in the output exists in the input; plus a rule-based fallback. Residual risk: wording can still be slightly off, so the app shows a warning for unsupported numbers.

**5. How do you calculate revenue growth?** `(current - previous) / previous x 100`. If previous is 0 and current is 0, growth is 0; if previous is 0 and current is not, growth is undefined (`None`, labelled "new") rather than infinity.

**6. How do you identify growth drivers?** Compute each region/product/category's revenue change between the two periods, then its share of the net change `change / |total change| x 100`. Rank by rupee change, filter noise members below ~2-3% share, and the rule engine labels members above a contribution threshold as drivers and members declining beyond a threshold as risks.

**7. Why rank by contribution instead of growth %?** A small member can show +80% but add almost no rupees. Business impact is in rupees.

**8. How would you scale this?** Move data to a warehouse/database (PostgreSQL, BigQuery), push aggregations to SQL, process in chunks or with Polars/DuckDB/Spark, cache monthly aggregates, schedule the pipeline (Airflow/cron), put the analytics behind a FastAPI service, and keep the LLM input small (it is already aggregate-only, so LLM cost does not grow with data size).

**9. How would you handle 10 million rows?** Do not load everything into pandas. Use DuckDB/SQL group-bys, read Parquet instead of Excel, `usecols` and category dtypes, chunked cleaning, pre-aggregate to month x region x product, and incrementally update only the latest month. The driver analysis only needs aggregates, so it is cheap once data is grouped.

**10. How would you secure the API?** Keys in environment variables/secret managers, never in code or Git (`.env` in `.gitignore`, `.env.example` committed); least-privilege and spend-limited keys; rotate on leak; HTTPS only; if exposed via an API, add authentication, rate limiting, input validation, and logging that never prints keys or raw data.

**11. What happens if the API is unavailable?** Requests time out, retry with exponential backoff on 429/5xx; on failure the app falls back to the rule-based report and shows a notice. Bad key (401/403) gives a clear config error. The analytics (KPIs, charts, drivers) never depend on the API.

**12. What are the limitations?** Synthetic data; compares one month with the previous (no forecasting or statistical significance tests); drivers show *what* moved, not *why* causally; fixed schema; Customer_Segment optional; thresholds are heuristics; no authentication or multi-user storage; LLM wording quality varies.

**13. What was the hardest bug?** Date parsing: `dayfirst=True` flipped ISO dates (5 March became 3 May), which silently changed monthly totals. I replaced it with explicit format lists (ISO first) and added a regression test comparing CSV vs Excel results.

**14. How is data quality reported?** `clean_data` returns a report with a count for every fix, shown in the UI and the DOCX appendix, so nothing changes silently.

**15. How did you test it?** pytest: cleaning (duplicates, invalid dates, negatives, casing, imputation), KPIs against hand-calculated values, growth and division by zero, driver ranking, rules, JSON schema (no NaN, no raw rows), LLM behaviour with mocked HTTP (retry, rate limit, bad JSON, hallucinated number, fallback), and invalid input handling.

### Python / Pandas
**16. `loc` vs `iloc`?** `loc` is label-based (and boolean masks), `iloc` is integer-position based.

**17. `merge` vs `join` vs `concat`?** `merge` is SQL-style on columns/keys, `join` is merge on the index, `concat` stacks frames along an axis.

**18. How do you find and drop duplicates?** `df.duplicated()`, `df.drop_duplicates(subset=..., keep='first')`. I first removed exact duplicates, then duplicate `Order_ID` (assuming one row per order).

**19. `apply` vs vectorised operations?** Vectorised (column arithmetic, `.str`, `.dt`) runs in optimised C and is much faster; `apply` loops in Python, so use it only when no vectorised option exists.

**20. How do you handle missing values?** Depends on the column: drop if critical and unrecoverable (Sales, Date), derive from other columns (Region from State), impute with a group statistic and flag it (Cost), default with justification (Discount=0). Never blanket `fillna(0)`.

**21. Why `groupby` and what does `transform` do?** `groupby` aggregates per group; `transform` returns a result aligned to the original rows (used for per-product IQR bounds).

**22. How do you detect outliers?** IQR rule: values beyond Q3 + k x IQR. I use k=3 to flag and k=10 to remove (obvious entry errors), per product, because a laptop and a cable have very different normal ranges.

**23. What is a virtual environment?** An isolated Python install per project so dependency versions do not clash; `requirements.txt` makes it reproducible.

### Data analytics / KPIs
**24. Define profit margin and AOV.** Margin = profit / revenue. AOV = revenue / number of orders.

**25. MoM vs YoY?** MoM compares with the previous month (short-term momentum, affected by seasonality); YoY compares with the same month last year (removes seasonality, needs 12+ months).

**26. Why express margin change in percentage points?** Margin is already a percentage; 35% to 37.5% is +2.5 pp (or +7.1% relative growth, which is confusing).

**27. Revenue grew but profit grew less. What could it mean?** Margin compression: more discounting, higher costs, or a shift toward lower-margin products. The tool flags it and shows discount rate change, but it needs investigation to confirm cause.

**28. Correlation vs causation in your insights?** My discount rule says discounting "coincides with" lower margin; the prompt forbids claiming causes not in the data.

**29. What is the difference between orders, customers and quantity?** Orders = distinct Order_IDs, customers = distinct Customer_IDs, quantity = units sold. Revenue = orders x AOV, so splitting shows if growth is volume or basket-size driven.

### SQL concepts relevant to the project
**30. Write SQL for monthly revenue and MoM growth.**
```sql
WITH m AS (
  SELECT DATE_TRUNC('month', order_date) AS month, SUM(sales) AS revenue
  FROM sales GROUP BY 1)
SELECT month, revenue,
       (revenue - LAG(revenue) OVER (ORDER BY month)) * 100.0
       / NULLIF(LAG(revenue) OVER (ORDER BY month), 0) AS mom_pct
FROM m ORDER BY month;
```
**31. Revenue by region with contribution %?**
```sql
SELECT region, SUM(sales) AS revenue,
       100.0 * SUM(sales) / SUM(SUM(sales)) OVER () AS contribution_pct
FROM sales GROUP BY region ORDER BY revenue DESC;
```
**32. `WHERE` vs `HAVING`?** WHERE filters rows before grouping; HAVING filters groups after aggregation.
**33. Why `NULLIF` in the growth query?** To avoid division by zero (returns NULL instead of an error).
**34. Top 10 products by profit?** `SELECT product, SUM(profit) p FROM sales GROUP BY product ORDER BY p DESC LIMIT 10;`

### Power BI / DAX
**35. Why a star schema?** Dimensions filter a single fact table in one direction: faster, avoids ambiguity, and is required for good time intelligence.
**36. Calculated column vs measure?** A column is computed per row at refresh and stored; a measure is computed at query time in the filter context. Use measures for aggregations.
**37. Explain `CALCULATE`.** It evaluates an expression after modifying the filter context, e.g. `CALCULATE([Total Revenue], DATEADD(DimDate[Date], -1, MONTH))`.
**38. Why `DIVIDE` instead of `/`?** It handles division by zero and returns blank (or an alternative) instead of an error.
**39. What is filter context vs row context?** Filter context is the set of filters from slicers/visual axes on a cell; row context iterates row by row (calculated columns, iterators like `SUMX`).
**40. Why must the date table be marked as a date table?** Time-intelligence functions need a continuous, unique date column.

### APIs / REST / JSON
**41. What is a REST API?** Stateless HTTP-based interface using resources and verbs (GET/POST), usually exchanging JSON; the LLM call is a POST with headers (auth) and a JSON body.
**42. Common status codes you handled?** 200 OK, 401/403 auth, 429 rate limit (retry with backoff), 5xx server error (retry).
**43. Why exponential backoff?** Spreading retries in growing intervals avoids hammering a struggling/rate-limited service.
**44. JSON vs CSV?** JSON supports nesting and typed values, ideal for structured payloads; CSV is flat and tabular.
**45. How do you validate LLM JSON?** Extract the object, `json.loads`, then validate with a Pydantic model (required fields, types); on failure retry once, then fallback.

### LLM / prompt engineering
**46. What does your prompt contain and why?** Role (sets tone), grounding rules (no invention, quote exactly), interpretation guide (growth vs pp vs share-of-change so the model reads fields correctly), fact/recommendation separation, strict output schema, and an instruction to treat input text as data (prompt-injection defence).
**47. Why low temperature?** Reduces randomness and creative drift; better for factual reporting.
**48. What is prompt injection and your defence?** Malicious text in data (e.g., a product named "ignore previous instructions") trying to steer the model. Defences: input is aggregates only, prompt says treat content as data, output is schema-validated and number-checked.
**49. How would you evaluate the LLM output?** Automated: schema validity, unsupported-number rate, mention of unknown entities; manual: fidelity and usefulness on a test set of payloads; track regressions when changing the prompt/model.
**50. Why is the LLM given pre-formatted `*_display` values?** Models often convert units incorrectly (lakh/crore) or round; copying exact strings removes that error class.

### Engineering
**51. Why custom exceptions?** The UI can catch a small family (`InsightGeneratorError`) and show friendly messages instead of tracebacks.
**52. Why separate `pipeline.py`?** One orchestrator reused by the CLI, the app and tests, so behaviour cannot drift.
**53. How would you deploy it?** Streamlit Community Cloud (secrets in the dashboard) or Docker on a cloud VM; CI with GitHub Actions running pytest.

## D2. Questions on the MCA-level upgrades
**54. How does column mapping make the project general?** It matches your columns to a standard schema using aliases and fuzzy matching, lets the user correct it, derives missing fields (Cost = Sales - Profit) and records every assumption. The rest of the pipeline only sees the standard names, so it works on any sales file.
**55. How do you know whether dates are day-first or month-first?** If any first number is above 12 the format must be day-first; if any second number is above 12 it must be month-first; if all values are ambiguous we assume day-first, warn the user, and allow an override. Ignoring this silently swaps months (5 March vs 3 May).
**56. Why are repeated Order IDs not duplicates?** One order has several product lines. Only exact duplicate rows are removed; Orders KPI counts distinct Order IDs.
**57. Why judge outliers on unit price?** A bulk order has a large Sales value but a normal unit price. A typo (two extra zeros) shows as a 100x unit price. So unit price separates real bulk orders from errors.
**58. Explain your forecasting method.** With under 24 months: a straight-line fit on the last 12 months. With 24+ months: seasonal factors from sales divided by a centred 12-month moving average, a local trend on the de-seasonalised data, then trend x seasonal factor. Each forecast has a 95% range and a backtest MAPE from hiding the last three known months.
**59. Why not use Prophet or ARIMA?** For a student project I preferred transparent methods I can explain and test; they are validated with a backtest. They can be swapped behind the same function signature later.
**60. What is a robust z-score?** `0.6745 x (x - median) / MAD`. Median and MAD are not distorted by a few extreme days, unlike mean and standard deviation.
**61. How do you avoid false anomaly alarms?** High thresholds (3.5 for days, 2.0 for monthly moves), a minimum move size, enough history, only low-cardinality dimensions, and wording that says "investigate" instead of claiming a problem.
**62. Why SQLite and what would you change for production?** Zero-setup, standard library, same SQL concepts. For production: PostgreSQL, connection pooling, migrations (Alembic), background jobs.
**63. How do you prevent SQL injection?** Parameterised queries for values and a whitelist for column names that cannot be parameterised.
**64. How is the REST API designed?** Resources (datasets, runs, reports), proper status codes (201, 204, 404, 422, 401), JSON errors, an optional API key header compared in constant time, OpenAPI docs generated by FastAPI.
**65. How did you evaluate the LLM?** An evaluation harness scores each generated report against its trusted payload: unsupported-number rate, driver coverage, causal wording, recommendation leakage, schema validity. I run it for a rule-based baseline and for the real model over twelve months.
**66. What are the limits of your evaluation?** Number matching cannot catch a correct number attached to the wrong entity; I report coverage as a proxy and recommend sampling human review.
**67. How do you test an LLM feature without calling the API?** Mock the HTTP layer to simulate success, 429, 5xx, invalid JSON and hallucinated numbers; the logic around the model is deterministic and fully testable.
**68. How would you add authentication to the web app?** Put it behind an authenticating reverse proxy or add a user table with hashed passwords (bcrypt), sessions/JWT, and per-user dataset ownership in the database.

**69. How easy is it to add a new analysis dimension (for example payment method)?** The design is configuration-driven: add the column to the optional-columns list, give the column mapper some aliases, and add it to the driver-dimension list. Cleaning, driver ranking, anomaly detection, report tables and the database then handle it. The database also migrates old files automatically with `ALTER TABLE ... ADD COLUMN`, so saved history keeps working.

## E. Live demo script (3 minutes)
1. Open the app, click **Use sample dataset**, show the raw preview ("see the messy data").
2. Show the **Column mapping** panel, then **Run data cleaning**: fixes table (duplicates, dates, outliers).
3. KPIs tab: revenue +6.7%, margin flat at 19.1%.
4. Drivers tab: North +11.2% explains most of the growth; West -9.8% is flagged.
5. Open "Rule-based insights" expander: "these facts go to the AI, not the raw data".
5b. **Forecast & Anomalies** tab: projection with range, the flash-sale day flagged.
6. **Generate AI Insights**, then download the DOCX. Open **History** to show it was saved.
7. Say: "If the API is down it falls back to the rule-based report. Tests: `pytest` -> 185 passed."
