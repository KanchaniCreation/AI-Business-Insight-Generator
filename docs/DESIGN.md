# System Design

Diagrams use [Mermaid](https://mermaid.js.org/). They render automatically on GitHub; in VS Code install the extension "Markdown Preview Mermaid Support"; to export PNG/SVG for your report paste the code into https://mermaid.live.

## 1. Architecture
```mermaid
flowchart LR
    U[User] --> UI[Streamlit app]
    D[Developer] --> API[FastAPI REST API]
    UI --> CORE
    API --> CORE
    subgraph CORE[Analytics core - src/]
        ING[Ingestion] --> MAP[Column mapper] --> CLN[Cleaning] --> KPI[KPI engine]
        KPI --> TRD[Trend analysis] --> DRV[Driver analysis]
        DRV --> FC[Forecast] --> ANO[Anomaly detection]
        ANO --> RULE[Rule-based insights] --> JSON[Structured JSON]
    end
    CORE --> DB[(SQLite)]
    JSON --> LLM[LLM generator<br/>prompt, validation, number check]
    LLM -->|API| EXT[LLM provider]
    LLM -->|failure| FB[Rule-based fallback]
    LLM --> REP[Report generator<br/>DOCX / MD / JSON]
```

## 2. Data flow diagrams
### DFD level 0 (context)
```mermaid
flowchart LR
    USER([Business user]) -- "sales file, month, currency" --> SYS((AI Business<br/>Insight Generator))
    SYS -- "KPIs, charts, forecast, report" --> USER
    SYS -- "structured facts (no raw data)" --> LLMX([LLM provider])
    LLMX -- "business language insights" --> SYS
    DEV([Developer]) -- "REST requests" --> SYS
    SYS -- "JSON responses, files" --> DEV
```

### DFD level 1
```mermaid
flowchart TD
    A([User]) -- "file" --> P1[1. Ingest and map columns]
    P1 -- "canonical table" --> P2[2. Clean data]
    P2 -- "clean rows + fix report" --> DS[(D1 datasets and sales)]
    DS -- "clean rows" --> P3[3. Compute KPIs, trends, drivers]
    P3 -- "metrics" --> P4[4. Forecast and detect anomalies]
    P4 -- "metrics + forecast" --> P5[5. Apply insight rules]
    P5 -- "facts JSON" --> RUNS[(D2 analysis runs)]
    RUNS -- "facts JSON" --> P6[6. Generate AI insights]
    P6 -- "prompt" --> L([LLM provider])
    L -- "JSON text" --> P6
    P6 -- "validated report" --> REPS[(D3 ai reports)]
    REPS --> P7[7. Build report files]
    P7 -- "DOCX / MD / JSON" --> A
```

## 3. Entity-relationship diagram
```mermaid
erDiagram
    DATASETS ||--o{ SALES : contains
    DATASETS ||--o{ ANALYSIS_RUNS : has
    ANALYSIS_RUNS ||--o{ AI_REPORTS : produces
    DATASETS {
        int id PK
        text name
        text currency
        int rows_in
        int rows_out
        text mapping_json
        text cleaning_json
        text created_at
    }
    SALES {
        int id PK
        int dataset_id FK
        text order_date
        text order_id
        text customer_id
        text region
        text state
        text product_category
        text sub_category
        text product
        text customer_segment
        text payment_method
        text sales_channel
        int quantity
        real sales
        real cost
        real discount
        real profit
    }
    ANALYSIS_RUNS {
        int id PK
        int dataset_id FK
        text period
        text payload_json
        text created_at
    }
    AI_REPORTS {
        int id PK
        int run_id FK
        text source
        text model
        text report_json
        text warnings_json
        text created_at
    }
```
Indexes: `sales(dataset_id, order_date)`. Deleting a dataset cascades to its sales rows, runs and reports.

## 4. UML use case diagram
```mermaid
flowchart LR
    M([Manager]) --- UC2(View KPIs and charts)
    M --- UC3(Understand drivers)
    M --- UC4(View forecast and anomalies)
    M --- UC5(Generate AI insights)
    M --- UC8(Download report)
    A([Analyst]) --- UC1(Upload, map and clean data)
    A --- UC6(Review history)
    A --- UC9(Evaluate AI quality)
    DV([Developer]) --- UC7(Use REST API)
    UC5 -. includes .-> UC11(Apply insight rules)
    UC5 -. extends .-> UC12(Fallback report)
    UC5 --- LP([LLM provider])
```

## 5. UML class diagram
```mermaid
classDiagram
    class Database {
        +save_dataset(df, name, currency, mapping, report) int
        +load_sales_df(dataset_id) DataFrame
        +save_run(dataset_id, period, payload) int
        +save_report(run_id, report, meta) int
        +sql_monthly_revenue(dataset_id) list
        +sql_revenue_by(dataset_id, dimension, month) list
    }
    class AnalysisResult {
        +current_period
        +comparison
        +monthly
        +drivers
        +forecast
        +anomalies
        +insights
        +payload
    }
    class InsightConfig {
        +strong_growth_pct
        +risk_decline_pct
        +driver_share_pct
        +forecast_drop_pct
    }
    class LLMConfig {
        +provider
        +api_key
        +model
        +from_env() LLMConfig
        +validate()
    }
    class AIInsightReport {
        +executive_summary
        +key_growth_drivers
        +negative_contributors
        +risks_to_investigate
        +recommended_actions
    }
    class InsightGeneratorError
    class DataValidationError
    class LLMError
    InsightGeneratorError <|-- DataValidationError
    InsightGeneratorError <|-- LLMError
    DataValidationError <|-- MappingError
    LLMError <|-- LLMConfigError
    LLMError <|-- LLMRateLimitError
    LLMError <|-- LLMResponseError
    class Pipeline {
        +prepare_dataset(raw, mapping) tuple
        +run_analysis(df, period, currency) AnalysisResult
    }
    Pipeline --> AnalysisResult
    Pipeline --> InsightConfig
    Pipeline ..> Database : saved by app and API
    class LLMGenerator {
        +generate_insights(payload, config) tuple
    }
    LLMGenerator --> LLMConfig
    LLMGenerator --> AIInsightReport
    LLMGenerator ..> AnalysisResult : consumes payload
```

## 6. Sequence diagram: generate AI insights (API view)
```mermaid
sequenceDiagram
    actor C as Client
    participant A as FastAPI
    participant D as Database
    participant P as Pipeline
    participant G as LLM generator
    participant L as LLM provider
    C->>A: POST /datasets (file)
    A->>P: prepare_dataset (map + clean)
    A->>D: save_dataset
    A-->>C: dataset_id, fix report
    C->>A: POST /datasets/{id}/analyze
    A->>D: load_sales_df
    A->>P: run_analysis
    A->>D: save_run (payload JSON)
    A-->>C: run_id, payload
    C->>A: POST /runs/{id}/insights
    A->>G: generate_insights(payload)
    G->>L: prompt + payload (aggregates only)
    alt API ok and valid JSON
        L-->>G: JSON text
        G->>G: validate schema, verify numbers
    else failure (429, 5xx, timeout, bad JSON)
        G->>G: retry with backoff, then rule-based fallback
    end
    G-->>A: report, meta
    A->>D: save_report
    A-->>C: report
    C->>A: GET /runs/{id}/report?format=docx
    A-->>C: DOCX file
```

## 7. Module design (src/)
| Module | Responsibility |
|---|---|
| `data_ingestion` | Safe file loading and validation |
| `column_mapper` | Alias/fuzzy column matching, derived columns, mapping checks |
| `data_cleaning` | Types, dates (convention detection), duplicates, invalid values, imputation, outliers |
| `kpi_calculation` | KPIs, comparisons, monthly MoM/YoY, contribution, dimension growth |
| `trend_analysis` | Growth, change/trend classification, period selection |
| `driver_analysis` | Rank contributors by money contribution |
| `forecasting` | Linear and seasonal trend forecast, 95% range, backtest MAPE |
| `anomaly_detection` | Robust z-score (daily) and history z-score (members) |
| `insight_engine` | Configurable IF/THEN rules |
| `schema` | JSON contract between analytics and LLM |
| `llm_generator` | Prompt, REST call, retries, validation, number check, fallback |
| `evaluation` | Hallucination and coverage metrics |
| `report_generator` | DOCX and Markdown reports |
| `database` | SQLite persistence and SQL analytics |
| `pipeline` | Orchestration used by app, API and CLI |

## 8. Key design decisions
1. **Facts first, language last:** all numbers are computed deterministically; the LLM only phrases them.
2. **Money contribution, not percentage, ranks drivers:** a tiny region with +80% can matter less than a large region with +8%.
3. **Order lines, not unique orders:** repeated Order IDs are valid lines of one order, so only exact duplicates are removed.
4. **Unit-price outliers:** judged on price per unit so legitimate bulk orders survive.
5. **Fail soft:** custom exceptions, friendly messages, retry with backoff, rule-based fallback.
6. **Explicit assumptions:** every default, derivation and imputation is written to a notes list shown to the user.

## 9. Deployment
```mermaid
flowchart LR
    B[Browser] --> S[Streamlit container :8501]
    C[API client] --> F[FastAPI container :8000]
    S --> V[(volume: data/insights.db)]
    F --> V
    S --> X[LLM provider over HTTPS]
    F --> X
```
