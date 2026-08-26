import streamlit as st


def render_action_card(recommendation):
    if recommendation is None:
        st.warning("No action recommended — confidence too low or no driver identified.")
        return
    st.markdown('<div class="action-callout">', unsafe_allow_html=True)
    st.markdown(f"**Next best action**  \n{recommendation.action}")
    st.markdown('</div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.caption(f"Lever: {recommendation.lever}  ·  Owner: {recommendation.owner}")
        if recommendation.monitoring_kpi:
            st.caption(f"Monitoring KPI: {recommendation.monitoring_kpi.replace('_', ' ').title()}")
