"""One function that runs the whole analytics pipeline (used by the CLI, the app and tests)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd

from src.column_mapper import apply_mapping, suggest_mapping
from src.data_cleaning import clean_data
from src.driver_analysis import analyze_drivers
from src.anomaly_detection import detect_anomalies
from src.forecasting import forecast_monthly
from src.insight_engine import InsightConfig, detect_insights
from src.kpi_calculation import calculate_kpis, compare_kpis, filter_month, monthly_summary
from src.schema import build_payload
from src.trend_analysis import analyze_trends, is_partial_month, resolve_periods
from src.utils import set_currency


def prepare_dataset(raw: pd.DataFrame, mapping: Optional[Dict] = None, dayfirst: Optional[bool] = None):
    """raw file -> (clean_df, report). Applies column mapping, then the cleaning pipeline.

    mapping: {canonical_field: source_column}; None = auto-detect.
    The report holds the cleaning counts, the mapping used and human-readable notes.
    """
    mapping = mapping if mapping is not None else suggest_mapping(raw)
    mapped, notes = apply_mapping(raw, mapping)
    clean, report = clean_data(mapped, dayfirst=dayfirst)
    report["notes"] = notes + report.get("notes", [])
    report["mapping"] = {k: v for k, v in mapping.items() if v}
    return clean, report


@dataclass
class AnalysisResult:
    current_period: pd.Period
    previous_period: pd.Period
    overall_kpis: Dict
    comparison: Dict
    monthly: pd.DataFrame
    trends: Dict
    drivers: Dict
    insights: List[Dict]
    payload: Dict
    partial_month: bool
    forecast: Dict
    anomalies: Dict
    currency: str = "INR"


def run_analysis(clean_df: pd.DataFrame, period=None, config: Optional[InsightConfig] = None,
                 currency: str = "INR", forecast_horizon: int = 3) -> AnalysisResult:
    """clean data -> KPIs -> trends -> drivers -> forecast -> anomalies -> rule-based insights -> structured payload."""
    currency = set_currency(currency)
    current, previous = resolve_periods(clean_df, period)
    cur_df, prev_df = filter_month(clean_df, current), filter_month(clean_df, previous)
    comparison = compare_kpis(cur_df, prev_df)
    monthly = monthly_summary(clean_df)
    upto = monthly[monthly["Month"] <= current]
    trends = analyze_trends(upto)
    drivers = analyze_drivers(cur_df, prev_df)
    partial = is_partial_month(clean_df, current)
    # an incomplete final month would look like a crash, so it is excluded from forecasting
    forecast = forecast_monthly(upto, "Revenue", forecast_horizon, exclude_last_month=partial)
    anomalies = detect_anomalies(clean_df[clean_df["Date"].dt.to_period("M") <= current], current)
    insights = detect_insights(comparison, drivers, config, partial, forecast, anomalies)
    payload = build_payload(current, previous, comparison, trends, drivers, insights, partial, currency,
                            forecast, anomalies)
    return AnalysisResult(current, previous, calculate_kpis(clean_df), comparison, monthly, trends,
                          drivers, insights, payload, partial, forecast, anomalies, currency)
