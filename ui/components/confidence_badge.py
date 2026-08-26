import streamlit as st

BAND_STYLE = {
    "HIGH": ("🟢", "HIGH"),
    "MEDIUM": ("🟡", "MEDIUM"),
    "LOW": ("🟠", "LOW"),
    "ABSTAIN": ("🔴", "ABSTAIN — human review recommended"),
}


def render_confidence_badge(confidence_result):
    icon, label = BAND_STYLE.get(confidence_result.confidence_band, ("⚪", confidence_result.confidence_band))
    score = confidence_result.confidence_score
    st.markdown(f"### {icon} {label}")
    st.progress(score, text=f"Confidence score · {score:.0%}")
    st.caption(confidence_result.rationale)
