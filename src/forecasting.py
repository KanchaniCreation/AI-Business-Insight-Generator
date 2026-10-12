"""STEP 14 - Forecasting: project the next few months of revenue/profit.

Two transparent methods (no black box, easy to explain in a viva):
  * linear_trend    : straight-line fit on the last 12 months   (used when < 24 months of history)
  * seasonal_trend  : linear trend x calendar-month seasonal factor (used with >= 24 months = 2 full cycles)

Every forecast comes with a 95% range and a BACKTEST error (MAPE): we hide the last 3 known months,
forecast them, and measure how wrong we would have been. If it is large, the report says so.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

MIN_POINTS = 6
SEASONAL_MIN_POINTS = 24
TREND_WINDOW = 12


def _trend_with_interval(y: np.ndarray, horizon: int):
    n = len(y)
    t = np.arange(n)
    slope, intercept = np.polyfit(t, y, 1)
    resid = y - (intercept + slope * t)
    s = float(np.sqrt((resid ** 2).sum() / max(n - 2, 1)))
    tf = np.arange(n, n + horizon)
    point = intercept + slope * tf
    spread = ((t - t.mean()) ** 2).sum()
    width = 1.96 * s * np.sqrt(1 + 1 / n + (tf - t.mean()) ** 2 / spread)
    return point, width


def forecast_values(values: List[float], last_period: pd.Period, horizon: int = 3) -> Optional[Dict]:
    """Forecast `horizon` months after `last_period`. Returns None if there is too little history."""
    y_all = np.asarray([v for v in values], dtype=float)
    if len(y_all) < MIN_POINTS or np.isnan(y_all).any():
        return None
    future_periods = [last_period + i for i in range(1, horizon + 1)]

    if len(y_all) >= SEASONAL_MIN_POINTS:
        n = len(y_all)
        months = np.array([(last_period - (n - 1 - i)).month for i in range(n)])
        # classical decomposition: compare each month with a centred 12-month moving average
        w = np.array([0.5] + [1.0] * 11 + [0.5]) / 12
        cma = np.convolve(y_all, w, mode="valid")            # centred on indices 6 .. n-7
        ratio = y_all[6:n - 6] / np.where(cma > 0, cma, np.nan)
        r_months = months[6:n - 6]
        factor = {m: float(np.nanmean(ratio[r_months == m])) if (r_months == m).any() else 1.0 for m in range(1, 13)}
        mean_factor = float(np.mean(list(factor.values())))
        factor = {m: f / mean_factor for m, f in factor.items()}
        seas = np.array([factor[m] for m in months])
        deseason = y_all / seas
        # LOCAL trend: last 12 de-seasonalised points (growth rates change over multi-year history)
        d12 = deseason[-TREND_WINDOW:]
        tt = np.arange(len(d12))
        slope, intercept = np.polyfit(tt, d12, 1)
        fitted = (intercept + slope * tt) * seas[-TREND_WINDOW:]
        sigma = float(np.sqrt(((y_all[-TREND_WINDOW:] - fitted) ** 2).sum() / max(len(d12) - 2, 1)))
        tf = np.arange(len(d12), len(d12) + horizon)
        point = (intercept + slope * tf) * np.array([factor[p.month] for p in future_periods])
        return _pack("seasonal_trend", future_periods, point, np.full(horizon, 1.96 * sigma))

    y = y_all[-TREND_WINDOW:]
    point, width = _trend_with_interval(y, horizon)
    return _pack("linear_trend", future_periods, point, width)


def _pack(method: str, periods, point, width) -> Dict:
    return {"method": method, "projections": [
        {"month": str(p), "value": float(max(v, 0.0)), "lower": float(max(v - w, 0.0)), "upper": float(max(v + w, 0.0))}
        for p, v, w in zip(periods, point, width)]}


def backtest_mape(values: List[float], last_period: pd.Period, horizon: int = 3) -> Optional[float]:
    """Mean absolute % error when forecasting the last `horizon` known months from the earlier ones."""
    y = list(values)
    if len(y) - horizon < MIN_POINTS:
        return None
    res = forecast_values(y[:-horizon], last_period - horizon, horizon)
    if res is None:
        return None
    actual = np.asarray(y[-horizon:], dtype=float)
    pred = np.asarray([p["value"] for p in res["projections"]])
    mask = actual != 0
    return float(np.mean(np.abs(actual[mask] - pred[mask]) / np.abs(actual[mask])) * 100) if mask.any() else None


def forecast_monthly(monthly: pd.DataFrame, metric: str = "Revenue", horizon: int = 3,
                     exclude_last_month: bool = False) -> Dict:
    """Forecast from the monthly_summary table. `exclude_last_month` drops an incomplete final month."""
    data = monthly.iloc[:-1] if exclude_last_month else monthly
    values = data[metric].tolist()
    if len(values) < MIN_POINTS:
        return {"available": False, "metric": metric.lower(),
                "reason": f"At least {MIN_POINTS} months of history are needed to forecast (found {len(values)})."}
    last_period = data["Month"].iloc[-1]
    res = forecast_values(values, last_period, horizon)
    if res is None:
        return {"available": False, "metric": metric.lower(), "reason": "History contains gaps; cannot forecast."}
    latest = float(values[-1])
    first = res["projections"][0]["value"]
    return {"available": True, "metric": metric.lower(), "method": res["method"], "horizon": horizon,
            "history_months": len(values), "last_actual_month": str(last_period), "last_actual_value": latest,
            "projections": res["projections"],
            "next_month_change_pct": None if latest == 0 else (first - latest) / latest * 100,
            "backtest_mape_pct": backtest_mape(values, last_period, min(3, horizon))}
