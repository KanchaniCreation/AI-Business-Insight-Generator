# MCA project report: chapter plan

Use this as the skeleton of your project report (typical Amity proforma: certificate, declaration, acknowledgement, abstract, then chapters). Each chapter says what to write and where the material already exists in this repository.

| Chapter | Contents | Source in this repo |
|---|---|---|
| Abstract | 150-200 words: problem, approach (pipeline + grounded LLM), results (tests, evaluation) | README "Problem statement" and "Features" |
| 1. Introduction | background, problem, motivation, objectives, scope, organisation of the report | `docs/SRS.md` sections 1.1-1.4 |
| 2. Literature / technology review | business analytics, KPIs, time-series forecasting basics, anomaly detection (z-score, MAD), LLMs and hallucination, prompt engineering, REST, SQLite; comparison with "paste data into ChatGPT" | write yourself; use `docs/INTERVIEW_PREP.md` answers as notes |
| 3. System analysis | existing system limits, proposed system, feasibility (technical, economic, operational), SRS | `docs/SRS.md` |
| 4. System design | architecture, DFD 0/1, ER diagram, UML (use case, class, sequence), module design, database design, API design | `docs/DESIGN.md`, `docs/API.md` |
| 5. Implementation | one section per module: cleaning rules and decisions, KPI formulas, driver ranking (money contribution), forecasting methods, anomaly formulas, insight rules table, prompt design and guardrails, report generation | source files in `src/`, `docs/STEPS.md` |
| 6. Testing | strategy, unit/integration/API tests, test-case table, results | `docs/TEST_CASES.md` |
| 7. Results and evaluation | screenshots (KPIs, drivers, forecast, report), sample report, LLM evaluation table (baseline vs LLM), forecast backtest MAPE, Superstore case study | `reports/`, `docs/LLM_EVALUATION.md` |
| 8. Conclusion and future scope | achievements, limitations, future work (multi-period comparison, ML forecasting, authentication, scheduled reports, PostgreSQL) | README "Limitations" and "Future improvements" |
| References | pandas, Streamlit, FastAPI docs, LLM provider docs, MAD/robust z-score, classical decomposition | |
| Appendix | key code listings, screenshots, user manual (`docs/STEPS.md`), sample JSON payload | `reports/insight_payload_*.json` |

## Formulas to include (with one worked example each)
- Growth % = (current - previous) / previous x 100
- Profit margin = profit / revenue; margin change in percentage points
- Contribution to change = member change / |total change| x 100
- Robust z = 0.6745 x (x - median) / MAD
- MAPE = mean(|actual - forecast| / |actual|) x 100
- Seasonal factor = mean(actual / centred 12-month moving average) per calendar month

## Viva checklist
1. Why not send raw data to the LLM? 2. How do you stop hallucination and how did you measure it? 3. How do you pick growth drivers? 4. What happens when the API fails? 5. How does column mapping make it work on any dataset? 6. How accurate is the forecast and how do you know? 7. How would you scale to 10 million rows? 8. How is the API secured?
