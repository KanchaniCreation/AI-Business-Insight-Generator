"""Streamlit web application.   Run:  streamlit run app/app.py

Flow: upload -> column mapping -> cleaning -> KPIs -> charts -> trends -> drivers -> forecast & anomalies
      -> AI insights -> download -> history (SQLite)
"""
from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.column_mapper import FIELD_ORDER, mapping_problems, suggest_mapping
from src.config import CURRENCIES
from src.data_ingestion import load_dataset
from src.database import Database
from src.exceptions import InsightGeneratorError
from src.llm_generator import AIInsightReport, LLMConfig, generate_insights
from src.pipeline import prepare_dataset, run_analysis
from src.report_generator import build_docx, build_markdown
from src.utils import fmt_pct, format_money, set_currency

SAMPLE_PATH = ROOT / "data" / "sales_data.xlsx"
SUPERSTORE_PATH = ROOT / "data" / "superstore_like_sample.csv"

st.set_page_config(page_title="AI Business Insight Generator", page_icon="📊", layout="wide")


def _load_streamlit_secrets() -> None:
    """On Streamlit Cloud keys live in st.secrets; copy them to env vars (never hard-code keys)."""
    try:
        for key in ("LLM_PROVIDER", "LLM_API_KEY", "LLM_MODEL", "LLM_BASE_URL", "LLM_TIMEOUT"):
            if key in st.secrets:
                os.environ.setdefault(key, str(st.secrets[key]))
    except Exception:       # no secrets file locally - that is fine, .env is used instead
        pass


_load_streamlit_secrets()


@st.cache_resource
def _db() -> Database:
    return Database()


# ------------------------------------------------------------------ cached helpers
@st.cache_data(show_spinner=False)
def _load(file_bytes: bytes, name: str) -> pd.DataFrame:
    return load_dataset(io.BytesIO(file_bytes), filename=name)


@st.cache_data(show_spinner=False)
def _prepare(raw: pd.DataFrame, mapping_items: tuple, dayfirst):
    return prepare_dataset(raw, dict(mapping_items), dayfirst)


@st.cache_data(show_spinner=False)
def _analyze(clean_df: pd.DataFrame, period: str, currency: str):
    return run_analysis(clean_df, period, currency=currency)


def _fig_layout(fig: go.Figure, title: str) -> go.Figure:
    fig.update_layout(title=title, margin=dict(l=10, r=10, t=50, b=10), height=380, legend_orientation="h")
    return fig


def _reset_downstream() -> None:
    for k in ("clean", "ai", "dataset_id"):
        st.session_state.pop(k, None)


def _set_raw(raw: pd.DataFrame, source: str, currency: str | None = None) -> None:
    st.session_state.update(raw=raw, source=source, raw_sig=f"{source}-{raw.shape}")
    if currency:
        st.session_state["currency"] = currency
    _reset_downstream()


# ------------------------------------------------------------------ sidebar
st.title("📊 AI Business Insight Generator")
st.caption("Python calculates the facts. The AI only explains them.")

with st.sidebar:
    st.header("1. Data")
    upload = st.file_uploader("Upload Excel / CSV", type=["csv", "xlsx"])
    c1, c2 = st.columns(2)
    use_sample = c1.button("Sample (₹)", disabled=not SAMPLE_PATH.exists(), help="Synthetic Indian retail data")
    use_superstore = c2.button("Superstore-like ($)", disabled=not SUPERSTORE_PATH.exists(),
                               help="Same column style as Kaggle's Superstore: tests column mapping")
    try:
        if upload is not None:
            if st.session_state.get("source") != upload.name or st.session_state.get("upload_size") != upload.size:
                st.session_state["upload_size"] = upload.size
                _set_raw(_load(upload.getvalue(), upload.name), upload.name)
        elif use_sample:
            _set_raw(_load(SAMPLE_PATH.read_bytes(), SAMPLE_PATH.name), SAMPLE_PATH.name, "INR")
        elif use_superstore:
            _set_raw(_load(SUPERSTORE_PATH.read_bytes(), SUPERSTORE_PATH.name), SUPERSTORE_PATH.name, "USD")
    except InsightGeneratorError as exc:
        st.session_state.pop("raw", None)
        st.error(f"❌ {exc}")
    currency = st.selectbox("Currency of the data", list(CURRENCIES), key="currency",
                            format_func=lambda c: f"{c} ({CURRENCIES[c]})")
    save_history = st.checkbox("Save to history (SQLite)", value=True)
    st.divider()
    cfg_preview = LLMConfig.from_env()
    st.caption("AI service: " + ("✅ API key found" if cfg_preview.api_key and cfg_preview.api_key != "your_key_here"
                                 else "⚠️ no API key - rule-based report will be used"))

set_currency(currency)
raw = st.session_state.get("raw")

tab_data, tab_kpi, tab_charts, tab_trend, tab_drivers, tab_fc, tab_ai, tab_hist = st.tabs(
    ["1. Data & Cleaning", "2. KPIs", "3. Charts", "4. Trends", "5. Drivers",
     "6. Forecast & Anomalies", "7. AI Insights & Report", "8. History"])

# ------------------------------------------------------------------ tab 1: preview + mapping + cleaning
with tab_data:
    if raw is None:
        st.info("👈 Upload a sales file (Excel/CSV) or pick a sample dataset in the sidebar to start.")
        st.caption("Any sales file works: map your columns below. Minimum: a Date, a Sales/Revenue column and "
                   "either Cost or Profit.")
    else:
        st.subheader(f"Preview: {st.session_state.get('source')}")
        st.caption(f"{len(raw):,} rows x {raw.shape[1]} columns (raw, before cleaning)")
        st.dataframe(raw.head(100), width="stretch")

        # ---- column mapping
        sig = st.session_state["raw_sig"]
        suggested = suggest_mapping(raw)
        problems_auto = mapping_problems(suggested)
        with st.expander("🔗 Column mapping (auto-detected: check and adjust)", expanded=bool(problems_auto)):
            st.caption("Tell the app which of your columns is which. Unmapped optional fields get safe defaults.")
            options = ["(none)"] + [str(c) for c in raw.columns]
            chosen = {}
            cols = st.columns(3)
            for i, field in enumerate(FIELD_ORDER):
                default = suggested.get(field)
                idx = options.index(str(default)) if default is not None else 0
                pick = cols[i % 3].selectbox(field.replace("_", " "), options, index=idx, key=f"map_{sig}_{field}")
                chosen[field] = None if pick == "(none)" else pick
            fmt_choice = st.radio("Date format", ["Auto-detect", "Day first (31/12/2026)", "Month first (12/31/2026)"],
                                  horizontal=True, key=f"datefmt_{sig}")
        dayfirst = {"Auto-detect": None, "Day first (31/12/2026)": True, "Month first (12/31/2026)": False}[fmt_choice]
        problems = mapping_problems(chosen)
        for pr in problems:
            st.warning(f"Mapping incomplete: {pr}.")

        if st.button("🧹 Run data cleaning", type="primary", disabled=bool(problems)):
            try:
                with st.spinner("Mapping columns and cleaning data..."):
                    clean_df, report = _prepare(raw, tuple(chosen.items()), dayfirst)
                st.session_state["clean"] = (clean_df, report)
                st.session_state.pop("ai", None)
                if save_history:
                    try:
                        st.session_state["dataset_id"] = _db().save_dataset(
                            clean_df, str(st.session_state.get("source")), currency, report.get("mapping"), report, report["rows_in"])
                    except Exception:
                        st.caption("History could not be saved (database unavailable); analysis continues normally.")
            except InsightGeneratorError as exc:
                st.error(f"❌ {exc}")

        if "clean" in st.session_state:
            clean_df, report = st.session_state["clean"]
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Rows received", f"{report['rows_in']:,}")
            m2.metric("Rows after cleaning", f"{report['rows_out']:,}")
            m3.metric("Rows removed", f"{report['rows_removed']:,}")
            m4.metric("Date format used", report.get("date_format", "-").split(" ")[0])
            for note in report.get("notes", []):
                st.info(note)
            st.write("**What was fixed**")
            if report["issues"]:
                st.dataframe(pd.DataFrame({"Issue": [k.replace("_", " ") for k in report["issues"]],
                                           "Count": list(report["issues"].values())}), hide_index=True, width="stretch")
            else:
                st.caption("No data-quality issues found.")
            st.download_button("⬇️ Download cleaned CSV", clean_df.to_csv(index=False).encode("utf-8"),
                               "sales_data_clean.csv", "text/csv")

# ------------------------------------------------------------------ analysis (after cleaning)
result = None
period = None
if "clean" in st.session_state:
    clean_df, cleaning_report = st.session_state["clean"]
    months = sorted(clean_df["Date"].dt.to_period("M").unique(), reverse=True)
    with st.sidebar:
        st.header("2. Period")
        options_p = [str(m) for m in months[:-1]] or [str(months[0])]
        period = st.selectbox("Analyse month", options_p, help="Compared with the month before it.")
    try:
        result = _analyze(clean_df, period, currency)
    except InsightGeneratorError as exc:
        st.error(f"❌ {exc}")

for tab in (tab_kpi, tab_charts, tab_trend, tab_drivers, tab_fc, tab_ai):
    if result is None:
        with tab:
            st.info("Run **data cleaning** in the first tab to unlock this section.")

if result is not None:
    comp, payload = result.comparison, result.payload
    if result.partial_month:
        st.warning("The selected month is incomplete: growth versus the previous full month may be understated.")

    # -------------------------------------------------------------- tab 2: KPIs
    with tab_kpi:
        st.subheader(f"KPI Dashboard - {payload['period']['label']} vs {result.previous_period.strftime('%B %Y')}")
        a, b, c, d = st.columns(4)
        a.metric("Revenue", format_money(comp["total_revenue"]["current"]), fmt_pct(comp["total_revenue"]["growth_pct"]))
        b.metric("Profit", format_money(comp["total_profit"]["current"]), fmt_pct(comp["total_profit"]["growth_pct"]))
        c.metric("Orders", f"{comp['total_orders']['current']:,}", fmt_pct(comp["total_orders"]["growth_pct"]))
        d.metric("Customers", f"{comp['total_customers']['current']:,}", fmt_pct(comp["total_customers"]["growth_pct"]))
        e, f, g, h = st.columns(4)
        e.metric("Revenue growth", fmt_pct(comp["total_revenue"]["growth_pct"], signed=False))
        f.metric("Profit margin", f"{comp['profit_margin_pct']['current']:.1f}%", f"{comp['profit_margin_pct']['change_pp']:+.1f} pp")
        g.metric("Average order value", format_money(comp["average_order_value"]["current"]), fmt_pct(comp["average_order_value"]["growth_pct"]))
        h.metric("Effective discount", f"{comp['effective_discount_pct']['current']:.1f}%",
                 f"{comp['effective_discount_pct']['change_pp']:+.1f} pp", delta_color="inverse")
        st.caption("Overall (all months): revenue "
                   f"{format_money(result.overall_kpis['total_revenue'])}, profit {format_money(result.overall_kpis['total_profit'])}, "
                   f"{result.overall_kpis['total_orders']:,} orders, {result.overall_kpis['total_customers']:,} customers.")

    # -------------------------------------------------------------- tab 3: charts
    with tab_charts:
        m = result.monthly.copy()
        m["Month"] = m["Month"].astype(str)
        fig = go.Figure()
        fig.add_bar(x=m["Month"], y=m["Revenue"], name="Revenue", marker_color="#4C78A8")
        fig.add_scatter(x=m["Month"], y=m["Profit"], name="Profit", mode="lines+markers", marker_color="#F58518")
        st.plotly_chart(_fig_layout(fig, f"Monthly revenue and profit ({currency})"), width="stretch")
        dims = [d for d in ("Region", "Product_Category", "Sales_Channel") if d in result.drivers]
        for col, dim in zip(st.columns(max(len(dims), 1)), dims):
            members = pd.DataFrame(result.drivers[dim]["all_members"])
            fig = go.Figure()
            fig.add_bar(x=members["name"], y=members["previous"], name=str(result.previous_period), marker_color="#B0B7C3")
            fig.add_bar(x=members["name"], y=members["current"], name=str(result.current_period), marker_color="#4C78A8")
            fig.update_layout(barmode="group")
            col.plotly_chart(_fig_layout(fig, f"{dim.replace('_', ' ')}: revenue by period"), width="stretch")
        if "Product" in result.drivers:
            prod = pd.DataFrame(result.drivers["Product"]["all_members"]).sort_values("current").tail(15)
            fig = go.Figure(go.Bar(x=prod["current"], y=prod["name"], orientation="h", marker_color="#4C78A8"))
            st.plotly_chart(_fig_layout(fig, "Top products: revenue in selected month"), width="stretch")
        fig = go.Figure(go.Scatter(x=m["Month"], y=m["Profit_Margin_Pct"], mode="lines+markers", marker_color="#54A24B"))
        fig.update_yaxes(ticksuffix="%")
        st.plotly_chart(_fig_layout(fig, "Profit margin trend"), width="stretch")

    # -------------------------------------------------------------- tab 4: trends
    with tab_trend:
        st.subheader("Trend analysis")
        rows = []
        for key, label in (("revenue", "Revenue"), ("profit", "Profit"), ("orders", "Orders")):
            t = result.trends[key]
            rows.append({"Metric": label, "Direction (last 6 months)": t["direction"],
                         "Avg slope / month": fmt_pct(t["slope_pct_per_month"]),
                         "Latest MoM": fmt_pct(t["latest_mom_pct"]), "MoM label": t["latest_mom_label"],
                         "Latest YoY": fmt_pct(t["latest_yoy_pct"])})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        m = result.monthly.copy()
        m["Month"] = m["Month"].astype(str)
        fig = go.Figure()
        fig.add_bar(x=m["Month"], y=m["Revenue_MoM_Pct"], name="MoM %", marker_color="#4C78A8")
        fig.add_scatter(x=m["Month"], y=m["Revenue_YoY_Pct"], name="YoY %", mode="lines+markers", marker_color="#F58518")
        fig.update_yaxes(ticksuffix="%")
        st.plotly_chart(_fig_layout(fig, "Revenue growth: month-over-month and year-over-year"), width="stretch")
        st.caption(f"Best revenue month: {result.trends['best_revenue_month']} | Lowest: {result.trends['lowest_revenue_month']}")

    # -------------------------------------------------------------- tab 5: drivers
    with tab_drivers:
        st.subheader(f"Why did revenue change by {fmt_pct(comp['total_revenue']['growth_pct'])}?")
        st.caption("Members ranked by their contribution (in money) to the overall change.")
        dim = st.radio("Dimension", list(result.drivers), horizontal=True, format_func=lambda x: x.replace("_", " "))
        info = result.drivers[dim]
        members = pd.DataFrame(info["all_members"]).sort_values("change").tail(25)
        fig = go.Figure(go.Bar(x=members["change"], y=members["name"], orientation="h",
                               marker_color=["#E45756" if v < 0 else "#54A24B" for v in members["change"]]))
        st.plotly_chart(_fig_layout(fig, f"Revenue change by {dim.replace('_', ' ')} ({currency})"), width="stretch")
        left, right = st.columns(2)

        def _show(col, title, items):
            col.write(f"**{title}**")
            if items:
                col.dataframe(pd.DataFrame([{"Name": i["name"], "Growth": fmt_pct(i["growth_pct"]),
                                             "Revenue change": format_money(i["change"]),
                                             "Share of net change": fmt_pct(i["contribution_to_change_pct"], 0)} for i in items]),
                              hide_index=True, width="stretch")
            else:
                col.caption("None.")
        _show(left, "🟢 Top growth drivers", info["top_positive"])
        _show(right, "🔴 Negative contributors", info["top_negative"])
        with st.expander("Rule-based insights (verified facts sent to the AI)"):
            for i in result.insights:
                st.write({"positive": "🟢", "info": "⚪", "warning": "🟠", "negative": "🔴"}[i["severity"]], i["message"])

    # -------------------------------------------------------------- tab 6: forecast & anomalies
    with tab_fc:
        fc = result.forecast
        st.subheader("Revenue forecast")
        if fc.get("available"):
            hist = result.monthly[result.monthly["Month"] <= result.current_period].copy()
            hist["Month"] = hist["Month"].astype(str)
            proj = pd.DataFrame(fc["projections"])
            fig = go.Figure()
            fig.add_scatter(x=hist["Month"], y=hist["Revenue"], name="Actual", mode="lines+markers", marker_color="#4C78A8")
            fig.add_scatter(x=proj["month"], y=proj["upper"], mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip")
            fig.add_scatter(x=proj["month"], y=proj["lower"], mode="lines", line=dict(width=0), fill="tonexty",
                            fillcolor="rgba(245,133,24,0.2)", name="95% range", hoverinfo="skip")
            fig.add_scatter(x=proj["month"], y=proj["value"], name="Forecast", mode="lines+markers",
                            line=dict(dash="dash"), marker_color="#F58518")
            st.plotly_chart(_fig_layout(fig, f"Revenue: actual and next {fc['horizon']} months ({currency})"), width="stretch")
            k1, k2, k3 = st.columns(3)
            k1.metric(f"Projected {proj['month'].iloc[0]}", format_money(proj["value"].iloc[0]), fmt_pct(fc["next_month_change_pct"]))
            k2.metric("Method", fc["method"].replace("_", " "))
            k3.metric("Backtest error (MAPE)", "n/a" if fc["backtest_mape_pct"] is None else f"{fc['backtest_mape_pct']:.1f}%")
            st.caption("A projection from past patterns, not a guarantee. MAPE = how wrong the method would have been "
                       "on the last 3 known months.")
        else:
            st.info(fc.get("reason", "Forecast not available."))
        st.subheader("Anomalies (unusual movements)")
        an = result.anomalies
        if an["members"]:
            st.write("**Unusual monthly changes**")
            st.dataframe(pd.DataFrame(an["members"]).rename(columns={"mom_pct": "This month MoM %", "typical_mom_pct": "Typical MoM %"}),
                         hide_index=True, width="stretch")
        if an["daily"]:
            st.write("**Unusual days**")
            st.dataframe(pd.DataFrame([{"Date": a["date"], "Revenue": format_money(a["revenue"]), "Typical": format_money(a["expected"]),
                                        "Type": a["direction"], "Robust z": a["robust_z"]} for a in an["daily"]]),
                         hide_index=True, width="stretch")
        if not an["members"] and not an["daily"]:
            st.success("No statistically unusual movements detected in this month.")
        st.caption("Anomalies are signals to investigate, not proof of a problem.")

    # -------------------------------------------------------------- tab 7: AI + report
    with tab_ai:
        st.subheader("AI generated insights")
        st.caption("The AI receives only the structured facts below, never your raw data.")
        with st.expander("View the structured JSON sent to the AI"):
            st.json(payload, expanded=False)
        if st.button("✨ Generate AI Insights", type="primary"):
            with st.spinner("Generating insights..."):
                try:
                    report, meta = generate_insights(payload)
                    st.session_state["ai"] = (period, report, meta)
                    if st.session_state.get("dataset_id"):
                        try:
                            run_id = _db().save_run(st.session_state["dataset_id"], period, payload)
                            _db().save_report(run_id, report.model_dump(), meta)
                        except Exception:
                            pass
                except InsightGeneratorError as exc:
                    st.error(f"❌ {exc}")
                except Exception:  # last line of defence: the app must not crash
                    st.error("Something unexpected went wrong while generating insights. Please try again.")
        ai = st.session_state.get("ai")
        if ai and ai[0] == period:
            _, report, meta = ai
            for w in meta["warnings"]:
                st.warning(w)
            st.caption("Source: " + (f"AI model `{meta['model']}`" if meta["source"] == "llm" else "rule-based engine (fallback)"))
            st.markdown("### Executive Summary")
            st.write(report.executive_summary)
            for title, items in (("Key Growth Drivers", report.key_growth_drivers),
                                 ("Negative Contributors", report.negative_contributors),
                                 ("Risks / Areas to Investigate", report.risks_to_investigate),
                                 ("Recommended Actions (suggestions)", report.recommended_actions)):
                st.markdown(f"### {title}")
                for item in items or ["None identified."]:
                    st.markdown(f"- {item}")
            st.divider()
            st.markdown("### Download report")
            d1, d2, d3 = st.columns(3)
            d1.download_button("⬇️ Word (.docx)", build_docx(payload, report, meta, result.monthly, cleaning_report),
                               f"business_report_{period}.docx",
                               "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            d2.download_button("⬇️ Markdown (.md)", build_markdown(payload, report, meta).encode("utf-8"),
                               f"business_report_{period}.md", "text/markdown")
            d3.download_button("⬇️ Analytics JSON", json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8"),
                               f"insight_payload_{period}.json", "application/json")

# ------------------------------------------------------------------ tab 8: history (database)
with tab_hist:
    st.subheader("Saved datasets and reports")
    try:
        datasets = _db().list_datasets()
    except Exception:
        datasets = []
        st.caption("History is unavailable (database could not be opened).")
    if not datasets:
        st.info("Nothing saved yet. Run data cleaning with **Save to history** ticked.")
    else:
        st.dataframe(pd.DataFrame(datasets), hide_index=True, width="stretch")
        pick = st.selectbox("Open dataset", [d["id"] for d in datasets],
                            format_func=lambda i: next(f"#{d['id']}: {d['name']} ({d['rows_out']:,} rows)" for d in datasets if d["id"] == i))
        runs = _db().list_runs(pick)
        h1, h2 = st.columns(2)
        if h1.button("📂 Load this dataset into the app"):
            meta_ds = _db().get_dataset(pick)
            df_saved = _db().load_sales_df(pick)
            st.session_state.pop("ai", None)
            st.session_state["clean"] = (df_saved, meta_ds["cleaning_report"])
            st.session_state["dataset_id"] = pick
            st.session_state["currency"] = meta_ds["currency"]
            st.session_state["raw"] = st.session_state.get("raw")
            st.rerun()
        if h2.button("🗑️ Delete this dataset"):
            _db().delete_dataset(pick)
            st.rerun()
        if runs:
            st.write("**Saved analysis runs**")
            run_pick = st.selectbox("Run", [r["id"] for r in runs],
                                    format_func=lambda i: next(f"#{r['id']}: {r['period']} ({r['created_at']})" for r in runs if r["id"] == i))
            stored = _db().get_latest_report(run_pick)
            if stored:
                rep = AIInsightReport(**stored["report"])
                st.caption(f"Source: {stored['source']}")
                st.markdown(build_markdown(_db().get_run(run_pick)["payload"], rep, {"source": stored["source"], "model": stored["model"],
                                                                                    "warnings": stored["warnings"]}))
            else:
                st.caption("No AI report saved for this run.")
