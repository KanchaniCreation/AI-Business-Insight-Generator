"""STEP 18 - Measure LLM report quality instead of just hoping it is good.

For every analysed month we have a trusted payload (the "ground truth"). A report is scored on:
  unsupported_number_rate : % of metric numbers in the text that do not exist in the payload  (hallucination)
  driver_coverage         : share of top growth drivers (Region/Category/Product) the report mentions
  decline_coverage        : share of top decliners the report mentions
  causal_phrases          : count of causal wording ("because", "due to"...) - the prompt forbids unsupported causes
  reco_leakage            : "should/recommend" wording inside FACT sections (facts vs recommendations mixing)
  schema_valid            : output parsed and matched the required JSON schema
Used by scripts/evaluate_llm.py and the unit tests.
"""
from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd

from src.llm_generator import (AIInsightReport, extract_metric_numbers, find_unsupported_numbers, report_text)

CAUSAL = re.compile(r"\b(because|due to|caused by|as a result of|owing to|thanks to|resulting from|on account of)\b", re.I)
RECO = re.compile(r"\b(should|recommend(?:ed|s)?|must|ought to|need to)\b", re.I)


def _coverage(names: List[str], text: str) -> Optional[float]:
    if not names:
        return None
    low = text.lower()
    return sum(1 for n in names if n.lower() in low) / len(names)


def evaluate_report(report: AIInsightReport, payload: Dict) -> Dict:
    text = report_text(report)
    numbers = extract_metric_numbers(text)
    unsupported = find_unsupported_numbers(report, payload)
    drivers = payload.get("drivers", {})
    top_pos = [d["top_positive"][0]["name"] for k, d in drivers.items()
               if k in ("Region", "Product_Category", "Product") and d["top_positive"]]
    top_neg = [d["top_negative"][0]["name"] for k, d in drivers.items()
               if k in ("Region", "Product_Category", "Product") and d["top_negative"]]
    fact_text = " ".join([report.executive_summary] + report.key_growth_drivers + report.negative_contributors
                         + report.risks_to_investigate)
    return {
        "numbers_checked": len(numbers),
        "unsupported_numbers": len(unsupported),
        "unsupported_number_rate": (len(unsupported) / len(numbers) * 100) if numbers else 0.0,
        "driver_coverage": _coverage(top_pos, text),
        "decline_coverage": _coverage(top_neg, text),
        "causal_phrases": len(CAUSAL.findall(text)),
        "reco_leakage": len(RECO.findall(fact_text)),
        "schema_valid": True,
    }


def evaluate_generator(generate: Callable[[Dict], Tuple[AIInsightReport, Dict]], payloads: Dict[str, Dict]) -> pd.DataFrame:
    """Run a generator over many payloads (key = period label) and score each result."""
    rows = []
    for label, payload in payloads.items():
        try:
            report, meta = generate(payload)
            row = evaluate_report(report, payload)
            row["source"] = meta.get("source", "unknown")
        except Exception as exc:                    # a failed generation is itself a data point
            row = {"schema_valid": False, "source": "error", "error": str(exc)[:80]}
        row["period"] = label
        rows.append(row)
    return pd.DataFrame(rows).set_index("period")


def summarize(df: pd.DataFrame) -> Dict:
    ok = df[df["schema_valid"]]
    total_numbers = ok["numbers_checked"].sum() if len(ok) else 0
    sources = df["source"] if "source" in df.columns else pd.Series(dtype=str)
    return {
        "reports": int(len(df)),
        "from_llm": int((sources == "llm").sum()),
        "from_fallback": int((sources == "fallback").sum()),
        "failed": int((sources == "error").sum()),
        "schema_valid_pct": float(df["schema_valid"].mean() * 100),
        "unsupported_number_rate_pct": float(ok["unsupported_numbers"].sum() / total_numbers * 100) if total_numbers else 0.0,
        "avg_driver_coverage_pct": float(ok["driver_coverage"].mean() * 100) if len(ok) else 0.0,
        "avg_decline_coverage_pct": float(ok["decline_coverage"].mean() * 100) if len(ok) else 0.0,
        "causal_phrases_total": int(ok["causal_phrases"].sum()) if len(ok) else 0,
        "reco_leakage_total": int(ok["reco_leakage"].sum()) if len(ok) else 0,
    }
