# LLM Evaluation: LLM `gemini-flash-latest`

Months evaluated: 6 (from `realistic_business_sales_data_app_ready.csv`)

| Metric | Result | Goal |
|---|---|---|
| Valid JSON schema | 100% | 100% |
| Unsupported-number rate (hallucination) | 0.0% | 0% |
| Top-driver coverage | 50% | high |
| Top-decline coverage | 89% | high |
| Causal phrases (unsupported causes) | 0 | 0 |
| Recommendations leaking into fact sections | 0 | 0 |

## Per month

         numbers_checked  unsupported_numbers  unsupported_number_rate  driver_coverage  decline_coverage  causal_phrases  reco_leakage  schema_valid    source
period                                                                                                                                                         
2026-04               26                    0                      0.0              0.0               0.7               0             0          True  fallback
2026-05               40                    0                      0.0              1.0               1.0               0             0          True  fallback
2026-06               43                    0                      0.0              0.7               1.0               0             0          True  fallback
2026-07               43                    0                      0.0              1.0               1.0               0             0          True  fallback
2026-08               27                    0                      0.0              0.3               1.0               0             0          True  fallback
2026-09               26                    0                      0.0              0.0               0.7               0             0          True  fallback