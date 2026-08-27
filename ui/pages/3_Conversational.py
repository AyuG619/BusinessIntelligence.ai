"""Conversational page. Deliberately NOT a new agent: predefined analytical
actions run the deterministic pipeline, and a single LLM call formats the
final answer (or routes free-text questions to the closest predefined action
using simple keyword matching — no separate intent-classification model).
"""
import sys
import pathlib
import streamlit as st

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from analytics.kpi_calculator import latest_kpi_result, KPIS  # noqa: E402
from analytics.detect import detect  # noqa: E402
from analytics.attribute import attribute_by_product, attribute_retention_drivers  # noqa: E402
from evidence.corroborate import build_confidence  # noqa: E402
from recommend.engine import recommend  # noqa: E402
from llm.narrative import generate_narrative, offline_template_narrative  # noqa: E402
from core.models import InsightPackage  # noqa: E402
from core.security import DEMO_USERS  # noqa: E402
from ui.components.theme import inject_theme, page_header, section_label  # noqa: E402

st.set_page_config(page_title="Conversational", layout="wide")
inject_theme()
page_header("Guided analysis", "Ask the signal", "Choose a focused analytical action and let the same governed pipeline build the answer.")

user_id = st.session_state.get("user_id", "BH-01")
persona = st.session_state.get("persona", "branch_head")
user = DEMO_USERS[user_id]
branch_id = user["branch_id"] or "BR-01"

st.markdown('<div class="insight-callout">Guided analysis keeps the numbers deterministic. '
            'The language layer explains validated results; it does not calculate them.</div>', unsafe_allow_html=True)

ACTIONS = ["Analyze KPI", "Drill into drivers", "Show evidence", "Recommend actions", "Ask a question"]
section_label("Set the question")
action = st.radio("Action", ACTIONS, index=4, horizontal=True, label_visibility="collapsed", key="conversation_action")

left, right = st.columns([1.2, 1], gap="large")
with left:
    kpi_key = st.selectbox("KPI", list(KPIS.keys()), format_func=lambda k: KPIS[k]["label"], key="conversation_kpi")
with right:
    free_text = None
    if action == "Ask a question":
        free_text = st.text_input(
            "Your question", placeholder="Why did cross-sell revenue fall?",
            key="conversation_question",
        )

if action == "Ask a question" and free_text:
    # naive keyword match to the closest KPI — not an LLM intent classifier
    if free_text:
        text_lower = free_text.lower()
        for k, cfg in KPIS.items():
            if any(word in text_lower for word in cfg["label"].lower().split()):
                kpi_key = k
                break

run = st.button("Run analysis", type="primary", use_container_width=True)

if run:
    if action == "Ask a question" and not free_text:
        st.warning("Enter a question before running the analysis.")
        st.stop()

    try:
        kpi = latest_kpi_result(kpi_key, branch_id=branch_id)
        detection = detect(kpi)
    except Exception as e:
        st.error(f"Could not compute this KPI — has the data been seeded? {e}")
        st.stop()

    section_label("Result")
    st.subheader(f"{KPIS[kpi_key]['label']} · {kpi.month}")
    st.write(f"Actual: **{kpi.actual:,.2f}**, expected **{kpi.expected:,.2f}** "
             f"({kpi.change_pct:+.1%}), materiality **{detection.materiality_band}**.")

    if action in ("Analyze KPI",):
        st.info("KPI computed deterministically from SQL/Pandas aggregation — see Insight Story "
                 "for the full drill-down.")

    if action in ("Drill into drivers", "Show evidence", "Recommend actions", "Ask a question"):
        if kpi_key == "customer_retention_rate":
            attribution = attribute_retention_drivers(detection)
        else:
            attribution = attribute_by_product(detection)
        for d_ in attribution.drivers[:5]:
            st.markdown(f"- **{d_.label}**: {d_.contribution_pct:+.0%}")

    if action in ("Show evidence", "Recommend actions", "Ask a question"):
        top_product = attribution.drivers[0].driver_key if attribution.drivers else None
        confidence = build_confidence(attribution, branch_id=branch_id, product_code=top_product, user_id=user_id)
        st.markdown(f"**Confidence: {confidence.confidence_band}** — {confidence.rationale}")
        for e in confidence.evidence[:5]:
            st.caption(f"[{e.stance}] {e.title} ({e.source_type})")

    if action in ("Recommend actions", "Ask a question"):
        recommendation = None
        recommendation = recommend(confidence, branch_id=branch_id, product_code=top_product)
        if recommendation:
            st.success(f"**Action:** {recommendation.action}  ·  Owner: {recommendation.owner}")
        else:
            st.warning("No action recommended — confidence too low.")

    if action == "Ask a question" and free_text:
        pkg = InsightPackage(confidence=confidence, recommendation=recommendation, persona=persona)
        result = generate_narrative(pkg)
        text = result["text"]
        if text.startswith("[Offline mode"):
            text = offline_template_narrative(pkg) + "\n\n" + text
        section_label("Answer")
        st.subheader(f"Answer to: {free_text}")
        st.write(text)
