import streamlit as st

STANCE_ICON = {"SUPPORTS": "✅", "CONTRADICTS": "❌", "NEUTRAL": "➖"}


def render_evidence_panel(evidence_items):
    if not evidence_items:
        st.info("No matching evidence found for the top drivers.")
        return
    for e in evidence_items:
        icon = STANCE_ICON.get(e.stance, "➖")
        with st.container(border=True):
            st.markdown(f"{icon} **{e.title}**  ·  _{e.source_type.replace('_', ' ').title()}_")
            st.caption(e.snippet)
            st.caption(f"Stance: {e.stance} · Relevance: {e.relevance:.0%} · "
                       f"Freshness: {e.freshness_status or 'UNKNOWN'} · "
                       f"created: {e.created_on or 'unknown'} · doc_id: {e.doc_id}")
