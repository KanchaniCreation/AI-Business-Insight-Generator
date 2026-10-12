import pytest

from src.evaluation import evaluate_generator, evaluate_report, summarize
from src.llm_generator import AIInsightReport, generate_fallback_report
from src.pipeline import run_analysis


@pytest.fixture
def payload(small_clean_df):
    return run_analysis(small_clean_df).payload


def test_faithful_report_scores_clean(payload):
    r = AIInsightReport(executive_summary="Revenue grew 20.0% in September 2026, led by North (+50.0%).",
                        key_growth_drivers=["North grew 50.0%."], negative_contributors=["West fell 10.0%."],
                        risks_to_investigate=["Investigate West."], recommended_actions=["Review West pricing."])
    s = evaluate_report(r, payload)
    assert s["unsupported_numbers"] == 0 and s["causal_phrases"] == 0 and s["reco_leakage"] == 0
    assert s["driver_coverage"] > 0 and s["decline_coverage"] > 0


def test_hallucinated_numbers_are_counted(payload):
    r = AIInsightReport(executive_summary="Revenue exploded by 87.3% and costs fell 55.5% this month overall.")
    s = evaluate_report(r, payload)
    assert s["unsupported_numbers"] == 2 and s["unsupported_number_rate"] == 100.0


def test_causal_claims_and_recommendation_leakage_are_flagged(payload):
    r = AIInsightReport(executive_summary="Revenue grew because of a festival, and the team should hire more staff.",
                        recommended_actions=["Hire staff."])
    s = evaluate_report(r, payload)
    assert s["causal_phrases"] == 1 and s["reco_leakage"] == 1


def test_missing_the_main_driver_lowers_coverage(payload):
    r = AIInsightReport(executive_summary="Business performance was good overall this period.")
    assert evaluate_report(r, payload)["driver_coverage"] == 0


def test_generator_failures_are_recorded_not_raised(payload):
    def boom(_):
        raise RuntimeError("API down")
    df = evaluate_generator(boom, {"2026-09": payload})
    assert not df["schema_valid"].iloc[0] and summarize(df)["schema_valid_pct"] == 0


def test_summary_over_fallback_generator(sample_clean_big):
    clean, _ = sample_clean_big
    payloads = {str(m): run_analysis(clean, m).payload for m in sorted(clean["Date"].dt.to_period("M").unique())[-4:]}
    df = evaluate_generator(lambda p: (generate_fallback_report(p), {"source": "fallback"}), payloads)
    s = summarize(df)
    assert s["reports"] == 4 and s["unsupported_number_rate_pct"] == 0 and s["reco_leakage_total"] == 0


def test_summary_counts_where_reports_came_from(payload):
    ok = lambda p: (generate_fallback_report(p), {"source": "llm"})            # noqa: E731
    boom = lambda p: (_ for _ in ()).throw(RuntimeError("503"))                 # noqa: E731
    df = evaluate_generator(ok, {"a": payload, "b": payload})
    df = df.reset_index()
    failed = evaluate_generator(boom, {"c": payload}).reset_index()
    import pandas as pd
    s = summarize(pd.concat([df, failed]).set_index("period"))
    assert (s["from_llm"], s["from_fallback"], s["failed"]) == (2, 0, 1)
