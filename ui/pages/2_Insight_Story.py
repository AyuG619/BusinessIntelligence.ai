import sys
import pathlib
import streamlit as st

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from analytics.kpi_calculator import (  # noqa: E402
    latest_kpi_result, KPIS, compute_product_revenue_series, latest_product_kpi_result, compare_kpi_periods,
)
from analytics.detect import detect  # noqa: E402
from analytics.attribute import (  # noqa: E402
    attribute_by_product, attribute_volume_mix_price, attribute_retention_drivers,
    attribute_new_product_launch,
)
from evidence.corroborate import build_confidence  # noqa: E402
from recommend.engine import recommend  # noqa: E402
from llm.narrative import generate_narrative, offline_template_narrative  # noqa: E402
from core.models import InsightPackage  # noqa: E402
from core.security import DEMO_USERS  # noqa: E402
from core.telemetry import recent_events, summary as telemetry_summary  # noqa: E402
from feedback.feedback import record_feedback, feedback_summary  # noqa: E402
from ui.components.evidence_panel import render_evidence_panel  # noqa: E402
from ui.components.confidence_badge import render_confidence_badge  # noqa: E402
from ui.components.action_card import render_action_card  # noqa: E402
from ui.components.theme import inject_theme, page_header, section_label, financial_year_label  # noqa: E402

st.set_page_config(page_title="Insight Story", layout="wide")
inject_theme()
page_header("Decision brief", "Insight Story", "Move from a KPI signal to the evidence, confidence, and action behind it.")

user_id = st.session_state.get("user_id", "BH-01")
persona = st.session_state.get("persona", "branch_head")
user = DEMO_USERS[user_id]
branch_id = user["branch_id"] or "BR-01"

NEW_PRODUCT_KEY = "__platinum_edge_launch__"

section_label("Choose a signal")
col_a, col_b = st.columns([1.7, 1], gap="large")
with col_a:
    kpi_options = list(KPIS.keys()) + [NEW_PRODUCT_KEY]

    def _label(k):
        return "🆕 Platinum Edge Revenue (new product launch)" if k == NEW_PRODUCT_KEY else KPIS[k]["label"]

    kpi_key = st.selectbox("Select a KPI to investigate", options=kpi_options, format_func=_label, key="story_kpi")
with col_b:
    attribution_mode = st.radio(
        "Attribution method", ["Product driver tree", "Volume / Mix / Pricing"], horizontal=False, key="story_attribution",
        disabled=(kpi_key in (NEW_PRODUCT_KEY, "customer_retention_rate")),
    )

try:
    if kpi_key == NEW_PRODUCT_KEY:
        series = compute_product_revenue_series("platinum_edge", branch_id=branch_id)
        kpi = latest_product_kpi_result("platinum_edge", "Platinum Edge Revenue", branch_id=branch_id)
        detection = detect(kpi, series_df=series)
    else:
        kpi = latest_kpi_result(kpi_key, branch_id=branch_id)
        detection = detect(kpi)
except Exception as e:
    st.error(f"Could not compute this KPI — has the data been seeded? {e}")
    st.stop()

section_label("01 / What changed")
st.subheader(f"{kpi.label} · {financial_year_label(kpi.month)} · {kpi.month}")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Actual", f"{kpi.actual:,.2f}")
c2.metric("Expected", f"{kpi.expected:,.2f}")
c3.metric("Change", f"{kpi.change_pct:+.1%}")
c4.metric("Materiality", detection.materiality_band.upper())
st.caption(f"z-score {detection.z_score} · anomalous {detection.is_anomalous} · "
            f"sparse history: {detection.sparse_history} · method: {detection.method}")

with st.expander("Baseline, importance, and period comparisons"):
    st.write("Expected is the mean of the latest three completed historical periods before the current period. Importance combines percentage change, configured materiality thresholds, z-score anomaly detection, persistence direction, and sparse-history status.")
    if kpi_key != NEW_PRODUCT_KEY:
        comparison = compare_kpi_periods(kpi_key, branch_id=branch_id)
        comparison_cols = st.columns(3)
        labels = [("Same month last year", "same_month_last_year"), ("Prior-quarter average", "prior_quarter_average"), ("Prior rolling-year average", "rolling_year_average")]
        for col, (label, key) in zip(comparison_cols, labels):
            value = comparison.get(key)
            col.metric(label, "n/a" if value is None else f"{value:,.2f}")
        st.caption("The comparison values use the same branch scope and KPI definition as the headline result.")

section_label("02 / Why it moved")
if kpi_key == NEW_PRODUCT_KEY:
    attribution = attribute_new_product_launch(detection)
    st.caption("Product launched with insufficient trailing history to decompose a trend — "
                "see CONFIDENCE below for how this is handled instead of guessing.")
elif kpi_key == "customer_retention_rate":
    attribution = attribute_retention_drivers(detection)
    st.caption("Retention movement — competing causal hypotheses below; see EVIDENCE and "
                "CONFIDENCE to see which one (if either) is corroborated.")
elif attribution_mode == "Product driver tree":
    attribution = attribute_by_product(detection)
else:
    attribution = attribute_volume_mix_price(detection)

if not attribution.drivers:
    st.info("No decomposable drivers found for this KPI/period.")
else:
    for d_ in attribution.drivers[:5]:
        st.markdown(f'<div class="insight-callout"><strong>{d_.label}</strong> '
                f'&nbsp; {d_.contribution_pct:+.0%} of the movement</div>', unsafe_allow_html=True)
        if d_.sub_drivers:
            for sd in d_.sub_drivers:
                st.markdown(f"　　↳ {sd.label}: {sd.contribution_pct:.0%}")

section_label("03 / Evidence")
top_product = "platinum_edge" if kpi_key == NEW_PRODUCT_KEY else None
if top_product is None:
    for d_ in attribution.drivers[:1]:
        top_product = d_.driver_key if d_.driver_key in (
            "credit_card", "salary_account", "personal_loan", "platinum_edge") else None

confidence = build_confidence(attribution, branch_id=branch_id, product_code=top_product, user_id=user_id)
render_evidence_panel(confidence.evidence)

section_label("04 / Confidence")
render_confidence_badge(confidence)

section_label("05 / Recommended response")
recommendation = recommend(confidence, branch_id=branch_id, product_code=top_product)
render_action_card(recommendation)

section_label("06 / Executive narrative")
st.subheader("The short version")
pkg = InsightPackage(confidence=confidence, recommendation=recommendation, persona=persona)
llm_result = generate_narrative(pkg)
narrative_text = llm_result["text"]
if narrative_text.startswith("[Offline mode"):
    narrative_text = offline_template_narrative(pkg) + "\n\n" + narrative_text
st.write(narrative_text)

with st.expander("Method and model telemetry"):
    st.markdown(
        f"""
| Stage | Method | LLM involved? |
|---|---|---|
| KPI calculation | SQL/Pandas aggregation | No |
| Detection | Baseline z-score + materiality | No |
| Attribution | {attribution.method} | No |
| Evidence retrieval | Scoped SQLite keyword match | No |
| Evidence classification | Stance classification | **Yes** (falls back to keyword heuristic offline) |
| Confidence scoring | Rule-based combination | No |
| Recommendation eligibility | Rule-based (confidence band gate) | No |
| Narrative | Persona-adapted natural language | **Yes** |
"""
    )
    st.caption(f"Narrative call — model: {llm_result['model']}, latency: {llm_result['latency_ms']}ms, "
                f"tokens: {llm_result['input_tokens']}/{llm_result['output_tokens']}, "
                f"est. cost: ${llm_result['est_cost_usd']}")
    tsum = telemetry_summary()
    st.caption(f"Session totals — model calls: {tsum['model_calls']}, pipeline events: {tsum['pipeline_events']}, "
                f"avg latency: {tsum['avg_duration_ms']}ms, "
                f"tokens: {tsum['total_input_tokens']}/{tsum['total_output_tokens']}, "
                f"est. cost: ${tsum['total_est_cost_usd']}")

with st.expander("KPI contract and lineage"):
    if kpi_key == NEW_PRODUCT_KEY:
        st.caption("Product-scoped Platinum Edge revenue uses the same revenue_transactions source at product grain.")
    else:
        kpi_cfg = KPIS[kpi_key]
        st.markdown(f"**Source:** `{kpi_cfg['table']}`  \n"
                    f"**Lineage:** {kpi_cfg.get('lineage', 'Defined in analytics/kpi_calculator.py')}  \n"
                    f"**Drivers:** {', '.join(kpi_cfg.get('drivers', []))}  \n"
                    f"**Refresh cadence:** {kpi_cfg.get('refresh_cadence', 'Not specified')}  \n"
                    f"**Access:** {kpi_cfg.get('access_scope', 'RBAC policy applies')}")

section_label("Feedback loop")
st.subheader("Was this brief useful?")
insight_ref = f"{kpi_key}|{kpi.month}|{branch_id}"
fb_col1, fb_col2, fb_col3 = st.columns([1, 1, 4])
if fb_col1.button("👍 Yes"):
    record_feedback(insight_ref, user_id, True)
    st.success("Thanks — feedback recorded.")
if fb_col2.button("👎 No"):
    st.session_state["show_reason"] = True
if st.session_state.get("show_reason"):
    reason = fb_col3.text_input("What was wrong?", key="fb_reason")
    if st.button("Submit feedback"):
        record_feedback(insight_ref, user_id, False, reason)
        st.session_state["show_reason"] = False
        st.success("Thanks — feedback recorded.")

fb_summary = feedback_summary(insight_ref)
st.caption(f"This insight: 👍 {fb_summary['useful']}  ·  👎 {fb_summary['not_useful']}")
