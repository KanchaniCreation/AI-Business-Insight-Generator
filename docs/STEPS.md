# Step-by-step guide (Hinglish)

Har step mein: **kya hai → kaunsi file → kaise run karein → expected output → test**.
Pehle setup karo, phir steps ko order mein padho/chalao. Har step ke baad `pytest` chalana mat bhoolna.

## Step 0: Setup (5 min)
```bash
python -m venv venv
venv\Scripts\activate            # Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env           # Mac/Linux: cp .env.example .env   (phir .env mein apni API key daalo)
git init && git add . && git commit -m "Initial project"
pytest                           # expected: 185 passed
```

## Step 1: Project structure
Folder structure README mein hai. `src/` = saara logic, `app/` = Streamlit UI, `tests/` = pytest, `scripts/` = CLI tools.
**Concept:** UI mein logic mat likho. Logic `src/` mein hota hai taaki test ho sake aur UI baad mein badal sake.

## Step 2: Dataset (`scripts/generate_dataset.py`)
- Run: `python scripts/generate_dataset.py` → `data/sales_data.xlsx` (+ csv), ~12,100 rows (Jan 2024 - Sep 2026).
- Isme jaan-boojh ke gandagi daali gayi hai (duplicates, typos, missing values, negative qty, text-numbers, wrong dates) taaki cleaning ka kaam dikhe.
- Built-in business story: North grow kar raha hai, West girta hai, Laptop booming, Accessories shrinking, Oct-Nov festive spike, aur 17 Sep 2026 ko ek "flash sale" din (anomaly demo).
- **Columns:** Date, Order_ID, Customer_ID, Region, State, Product_Category, Product, Quantity, Sales, Cost, Discount, Profit (+ Customer_Segment).
- **Business questions:** konsa region/product profitable hai? margin kyun gir raha hai? discount ka kya asar hai? growth kahan se aa rahi hai?

## Step 3: Ingestion + Cleaning (`src/data_ingestion.py`, `src/data_cleaning.py`)
- Run: `python -c "from src.data_ingestion import load_dataset; from src.data_cleaning import clean_data; d,r=clean_data(load_dataset('data/sales_data.xlsx')); print(r)"`
- Expected: `rows_in ~12149`, `rows_out ~11785`, aur `issues` mein har fix ka count.
- Pipeline order: columns → types → dates → text → critical-missing drop → duplicates → missing repair → invalid values → profit recompute → outliers.
- **Decisions jo interview mein defend karne hain:**
  - Missing `Sales/Date/Quantity` → row drop (guess nahi kar sakte).
  - Missing `Region` → State se repair. Missing `Cost` → product ke typical cost ratio se estimate, `Cost_Imputed=True` flag.
  - `Discount=15` → 0.15 (percent ko fraction banaya).
  - Outlier: IQR×3 se *flag*, IQR×10 se *remove* (extra-zero typos). Bulk orders real ho sakte hain, isliye sab nahi hataye.
  - `Profit` hamesha `Sales - Cost` se recompute (single source of truth).
- Test: `pytest tests/test_data_cleaning.py tests/test_data_ingestion.py`

## Step 4: EDA (`notebooks/EDA.ipynb`)
- Run: `jupyter notebook notebooks/EDA.ipynb` → Restart & Run All. (Notebook already executed hai, charts saved hain.)
- Har chart ek business sawaal answer karta hai, aur uske neeche "kya seekha" likha hai.

## Step 5: KPI engine (`src/kpi_calculation.py`)
- Functions: `calculate_kpis`, `compare_kpis`, `monthly_summary` (MoM + YoY), `contribution_pct`, `dimension_growth`.
- Run: `python -c "..."` ya seedha `scripts/run_pipeline.py`.
- **Concept:** margin ka change **percentage points (pp)** mein hota hai, growth % mein nahi.
- Test: `pytest tests/test_kpi_calculation.py` (expected numbers haath se calculate kiye gaye hain).

## Step 6: Trend analysis (`src/trend_analysis.py`)
- `growth_pct = (current - previous) / previous × 100`, zero-division safe (previous=0 → `None`, matlab "new").
- `classify_change`: stable (±2%), increase/decrease, strong (±10%).
- `classify_series_trend`: last 6 months pe straight-line fit → increasing / declining / stable.
- Test: `pytest tests/test_trend_analysis.py`

## Step 7: Driver analysis (`src/driver_analysis.py`)  ← sabse important
- Overall change = har member ke change ka sum. Isliye har Region/Product ko **rupee contribution** se rank karte hain.
- **Interview point:** chhota region 80% grow kare to bhi bade region ke 8% se kam matter karta hai. Isliye % se nahi, rupees se rank.
- `contribution_to_change_pct = member change / |total change| × 100` (+ve = madad ki, −ve = ulta kaam kiya; 100% se zyada ho sakta hai jab doosre offset karein).
- Test: `pytest tests/test_driver_analysis.py`

## Step 8: Rule-based insights (`src/insight_engine.py`)
- IF/THEN rules, thresholds `InsightConfig` mein (strong growth 10%, risk decline −3%, driver share 25% ...).
- Rules: revenue direction, margin compression, profit lagging, orders vs AOV, discount pressure, growth concentration, decline risk, partial-month warning.
- Discount rule sirf bolta hai "coincides with" (saath hua), "caused" nahi, kyunki correlation ≠ causation.
- Test: `pytest tests/test_insight_engine.py`

## Step 9: Structured JSON (`src/schema.py`)
- Sirf analysed facts, raw rows nahi. Paise ke saath `*_display` string (`₹92,10,087`) taaki LLM units convert na kare.
- Dekhne ke liye: `reports/insight_payload_2026-09.json`.

## Step 10: LLM + prompt (`src/llm_generator.py`)
- Provider `.env` se: `LLM_PROVIDER=anthropic` ya `openai` (OpenAI-compatible endpoints ke liye `LLM_BASE_URL`).
- 5 hallucination layers: (1) sirf facts input, (2) strict prompt, (3) JSON + Pydantic validation (+1 repair retry), (4) number-check: AI ke har number ko payload se match karta hai, (5) API fail ho to rule-based fallback report.
- Retry: 429/5xx pe exponential backoff. 401/403 pe turant clear error.
- Prompt ke sections aur unke reasons `SYSTEM_PROMPT` ke andar comments/headings mein hain (GROUNDING RULES, HOW TO READ THE DATA, FACTS vs RECOMMENDATIONS, OUTPUT FORMAT).
- Bina key ke bhi app chalti hai (fallback).
- Test: `pytest tests/test_llm_generator.py` (HTTP mock kiya hai, asli API call nahi hoti).

## Step 11: Report (`src/report_generator.py`)
- DOCX (chart ke saath) + Markdown. Sections: Executive Summary, KPI, Trend, Drivers, Negatives, Risks, Actions, Data-quality appendix.

## Step 12: Streamlit app (`app/app.py`)
```bash
streamlit run app/app.py
```
Sidebar: "Sample" button ya apni file upload → Tab 1 mein **Run data cleaning** → baaki tabs unlock → Tab 6 mein **Generate AI Insights** → download.
Error handling: empty/invalid file, missing columns, API fail sab friendly message dete hain, crash nahi.

## Step 13: Power BI (`powerbi/`)
`powerbi/README.md` follow karo. DAX copy-paste `dax_measures.dax` se. Validation table ke numbers se match karna.

## Step 14: GitHub + deploy
```bash
git remote add origin <your-repo-url>
git push -u origin main
```
- `.env` kabhi commit nahi hota (`.gitignore` mein hai). Commit se pehle `git status` check karo.
- Streamlit Community Cloud: repo connect karo, main file `app/app.py`, **Secrets** mein `LLM_API_KEY="..."` daalo (app `st.secrets` ko env var mein copy karta hai).
- README mein screenshots daalo (`docs/screenshots/`).

## Step 15: Interview prep
`docs/INTERVIEW_PREP.md` padho. Live demo script us file ke end mein hai.


---
# Upgrade steps (MCA level)

## Step 16: Column mapping (`src/column_mapper.py`)
- **Problem:** Kaggle files ke column names alag hote hain (`Order Date`, `Sub-Category`, `Product Name`) aur kabhi Cost column hota hi nahi.
- `suggest_mapping()` pehle exact alias match karta hai, phir fuzzy match (typos). `apply_mapping()` canonical table banata hai aur har assumption `notes` mein likhta hai (jaise "Cost = Sales - Profit").
- Minimum: Date + Sales + (Cost ya Profit). Galat mapping (jaise text column ko Sales banana) pe clear error.
- App mein "Column mapping" panel hai jahan tum selectbox se badal sakti ho. CLI: `--map "Date=Order Date"`.
- Test: `pytest tests/test_column_mapper.py`

## Step 17: Date convention + order lines + unit-price outliers (cleaning upgrade)
- `5/3/2026` ka matlab 5 March ya May 3? `detect_dayfirst()` values dekhta hai (agar koi pehla number >12 hai to day-first, dusra >12 to month-first). Superstore US style hai (month/day/year).
- Repeated Order ID ko duplicate nahi maante (ek order mein kai product lines hote hain); sirf exact duplicate rows hatate hain.
- Outlier ab **per-unit price** pe dekhte hain, taaki bulk order (quantity 50) galti se na hate, par 100x typo hate.
- Test: `pytest tests/test_data_cleaning.py`

## Step 18: Forecasting (`src/forecasting.py`)
- Do methods: `linear_trend` (24 mahine se kam) aur `seasonal_trend` (2+ saal: centred moving average se seasonal factor).
- Har forecast ke saath 95% range aur **backtest MAPE** (last 3 mahine chhupa ke forecast karke error naapte hain).
- Test: `pytest tests/test_forecasting.py`

## Step 19: Anomaly detection (`src/anomaly_detection.py`)
- Daily: robust z = 0.6745 x (x - median) / MAD, pichhle 28 din ke against.
- Member: Region/Category ka is mahine ka MoM% apni history ke against z-score.
- Anomaly = "check karo", "problem hai" nahi.
- Test: `pytest tests/test_anomaly_detection.py`

## Step 20: Database + REST API (`src/database.py`, `api/main.py`)
```bash
uvicorn api.main:app --reload     # http://localhost:8000/docs
```
- SQLite tables: datasets, sales, analysis_runs, ai_reports (ER diagram `docs/DESIGN.md` mein).
- `/datasets/{id}/monthly` aur `/breakdown` SQL (GROUP BY, window function) se result dete hain; column name whitelist se SQL injection band.
- Optional security: `API_KEY` env var set karo to `X-API-Key` header chahiye.
- Test: `pytest tests/test_database.py tests/test_api.py`

## Step 21: LLM evaluation (`src/evaluation.py`)
```bash
python scripts/evaluate_llm.py --max-months 12
```
Bina key ke fallback ko score karta hai (baseline); key ke saath asli LLM ko. Output `reports/llm_evaluation.md`. Dono tables report mein side-by-side daalo.

## Step 22: Docs, Docker, CI
- `docs/SRS.md`, `docs/DESIGN.md` (DFD, ER, UML Mermaid mein), `docs/TEST_CASES.md`, `docs/REPORT_OUTLINE.md` (report ke chapters).
- Mermaid diagrams ki PNG chahiye to code https://mermaid.live pe paste karke export karo.
- `docker compose up --build` (Docker installed ho to), `.github/workflows/ci.yml` GitHub pe push karte hi tests chalata hai.

## Kaggle dataset pe test karne ka tarika
1. Kaggle se "Sample - Superstore" download karo, app mein upload karo.
2. Mapping panel check karo (sab auto-detect hona chahiye), currency USD rakho.
3. Cleaning chalao; notes padho ("Cost derived", "order lines").
4. Koi mapping/date galat lage to panel mein badlo ya `--month-first` use karo.
5. Kuch toote to error ka text bhej do, fix kar denge.
