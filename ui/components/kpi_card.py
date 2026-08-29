import streamlit as st

from ui.components.theme import format_display_date


def render_kpi_card(detection):
    kpi = detection.kpi
    band = detection.materiality_band
    status_class = f"status-{band}" if band in ("high", "medium", "low") else "status-low"

    with st.container(border=True):
        st.markdown(f"**{kpi.label}**")
        val = f"{kpi.actual:,.2f}" if kpi.unit == "currency" else f"{kpi.actual:.1%}"
        st.metric(label=format_display_date(kpi.month), value=val, delta=f"{kpi.change_pct:+.1%} vs baseline")
        st.markdown(f'<span class="status-pill {status_class}">{band.upper()} MATERIALITY</span>', unsafe_allow_html=True)
        st.caption(f"z={detection.z_score} · {'ANOMALOUS' if detection.is_anomalous else 'within range'}")
        if detection.sparse_history:
            st.caption("Sparse history — limited trailing data")
