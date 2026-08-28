"""Domain-grounded conversational banking analytics workspace."""
import pathlib
import sys

import streamlit as st

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from analytics.attribute import attribute_by_product, attribute_retention_drivers  # noqa: E402
from analytics.detect import detect  # noqa: E402
from analytics.kpi_calculator import (  # noqa: E402
    KPIS,
    compare_kpi_periods,
    latest_kpi_result,
)
from core.models import InsightPackage  # noqa: E402
from core.security import DEMO_USERS  # noqa: E402
from evidence.corroborate import build_confidence  # noqa: E402
from llm.narrative import generate_chat_response  # noqa: E402
from recommend.engine import recommend  # noqa: E402
from ui.components.theme import financial_year_label, inject_theme, page_header, section_label  # noqa: E402

st.set_page_config(page_title="Ask your data", page_icon="💬", layout="wide")
inject_theme()
page_header(
    "Domain assistant",
    "Ask your data",
    "A conversational banking analyst grounded in the current KPI, branch scope, evidence, and confidence model.",
)

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []
if "conversation_kpi" not in st.session_state:
    st.session_state.conversation_kpi = "cross_sell_revenue"

user_id = st.session_state.get("user_id", "BH-01")
persona = st.session_state.get("persona", "branch_head")
user = DEMO_USERS[user_id]
branch_id = user["branch_id"]

section_label("Conversation context")
context_col, action_col = st.columns([4, 1], gap="large")
with context_col:
    kpi_key = st.selectbox(
        "Anchor the conversation to a KPI",
        list(KPIS.keys()),
        index=list(KPIS.keys()).index(st.session_state.conversation_kpi),
        format_func=lambda key: KPIS[key]["label"],
        key="conversation_kpi",
    )
with action_col:
    st.write("")
    if st.button("Clear chat", use_container_width=True):
        st.session_state.chat_messages = []
        st.rerun()

try:
    kpi = latest_kpi_result(kpi_key, branch_id=branch_id)
    detection = detect(kpi)
    if kpi_key == "customer_retention_rate":
        attribution = attribute_retention_drivers(detection)
    else:
        attribution = attribute_by_product(detection)
    top_product = None
    for driver in attribution.drivers[:1]:
        if driver.driver_key in ("credit_card", "salary_account", "personal_loan", "platinum_edge"):
            top_product = driver.driver_key
    confidence = build_confidence(attribution, branch_id=branch_id, product_code=top_product, user_id=user_id)
    recommendation = recommend(confidence, branch_id=branch_id, product_code=top_product, persona=persona)
    comparisons = compare_kpi_periods(kpi_key, branch_id=branch_id)
except Exception as exc:
    st.error(f"Unable to build the banking context. Confirm that the database is seeded. {exc}")
    st.stop()

with st.container(border=True):
    st.markdown(f"**{kpi.label} · {financial_year_label(kpi.month)} · {kpi.month}**")
    metric_cols = st.columns(4)
    metric_cols[0].metric("Actual", f"{kpi.actual:,.2f}")
    metric_cols[1].metric("Baseline", f"{kpi.expected:,.2f}")
    metric_cols[2].metric("Movement", f"{kpi.change_pct:+.1%}")
    metric_cols[3].metric("Confidence", confidence.confidence_band)
    st.caption(f"Scope: {branch_id} · {detection.materiality_band} materiality · {len(confidence.evidence)} evidence items · {attribution.method}")

context = {
    "user": user_id,
    "role": user["role"],
    "persona": persona,
    "branch_scope": branch_id,
    "kpi": {
        "key": kpi.kpi_key,
        "label": kpi.label,
        "period": kpi.month,
        "financial_year": financial_year_label(kpi.month),
        "actual": kpi.actual,
        "baseline": kpi.expected,
        "change_pct": kpi.change_pct,
    },
    "detection": {
        "z_score": detection.z_score,
        "materiality": detection.materiality,
        "materiality_band": detection.materiality_band,
        "persistence_months": detection.persistence_months,
        "sparse_history": detection.sparse_history,
    },
    "drivers": [
        {"key": d.driver_key, "label": d.label, "contribution_pct": d.contribution_pct, "sub_drivers": [s.label for s in d.sub_drivers]}
        for d in attribution.drivers[:5]
    ],
    "evidence": [
        {"title": e.title, "source": e.source_type, "stance": e.stance, "relevance": e.relevance, "freshness": e.freshness_status, "created_on": e.created_on, "snippet": e.snippet}
        for e in confidence.evidence[:8]
    ],
    "confidence": {"score": confidence.confidence_score, "band": confidence.confidence_band, "rationale": confidence.rationale},
    "recommendation": None if recommendation is None else {"action": recommendation.action, "owner": recommendation.owner, "lever": recommendation.lever, "monitoring_kpi": recommendation.monitoring_kpi},
    "comparisons": comparisons,
}

section_label("Chat")
if not st.session_state.chat_messages:
    st.info("Ask about the movement, drivers, evidence, comparison periods, customer impact, or next action. The assistant answers from the governed context above.")

for message in st.session_state.chat_messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

question = st.chat_input("Ask a banking question about this KPI...")
if question:
    st.session_state.chat_messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    package = InsightPackage(
        confidence=confidence,
        recommendation=recommendation,
        persona=persona,
        question=question,
        conversation_history=st.session_state.chat_messages[:-1],
    )
    with st.chat_message("assistant"):
        with st.spinner("Reviewing the banking context..."):
            result = generate_chat_response(package, context)
        answer = result["text"]
        if answer.startswith("[Offline mode"):
            st.warning("Groq was unavailable, so the local deterministic fallback was used.")
        st.markdown(answer)
    st.session_state.chat_messages.append({"role": "assistant", "content": answer})

with st.expander("What the assistant knows"):
    st.write("The assistant can reason over the selected KPI's actual and baseline, materiality and z-score, product or retention drivers, evidence stance and freshness, same-month-last-year and quarter comparisons, confidence, recommendation, branch scope, role, and prior chat messages.")
    st.caption("It must not invent customer facts, override access restrictions, recalculate KPIs, or present low-confidence hypotheses as established causes.")
