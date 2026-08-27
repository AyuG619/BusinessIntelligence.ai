import sys
import pathlib
import streamlit as st

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from analytics.kpi_calculator import all_latest_kpis  # noqa: E402
from analytics.detect import detect_all  # noqa: E402
from ui.components.kpi_card import render_kpi_card  # noqa: E402
from core.security import DEMO_USERS  # noqa: E402
from ui.components.theme import inject_theme, page_header, section_label  # noqa: E402

st.set_page_config(page_title="KPI Overview", layout="wide")
inject_theme()
page_header("Executive monitor", "KPI Overview", "A live read of the signals shaping branch performance this period.")

user_id = st.session_state.get("user_id", "BH-01")
user = DEMO_USERS[user_id]
branch_id = user["branch_id"]  # None for admin -> all branches

if branch_id is None:
    st.caption("Administrator view · choose a branch to inspect")
    branch_id = st.selectbox("Branch", ["BR-01", "BR-02"], key="overview_branch")
else:
    st.caption(f"Scope: {branch_id} · current period")

try:
    kpis = all_latest_kpis(branch_id=branch_id)
    detections = detect_all(kpis)
except Exception as e:
    st.error(f"Could not compute KPIs — has the data been seeded? Run the setup scripts in README.md.\n\n{e}")
    st.stop()

section_label("Current signal")
cols = st.columns(len(detections), gap="medium")
for col, det in zip(cols, detections):
    with col:
        render_kpi_card(det)

section_label("Attention queue")
st.subheader("What needs a closer look?")
st.caption("Signal count is dynamic: every KPI registered in config/kpi_definitions.yaml appears here.")
alerts = sorted(detections, key=lambda d: d.materiality, reverse=True)
alerts = [a for a in alerts if a.materiality_band in ("high", "medium")]
overview_tab, alerts_tab, data_tab = st.tabs(["Signal overview", "Attention queue", "Data note"])
with overview_tab:
    st.caption("Headline KPIs are computed live for the selected scope.")
with alerts_tab:
    if not alerts:
        st.info("No high/medium materiality movements this period.")
    else:
        for a in alerts:
            st.markdown(f'<div class="action-callout"><strong>{a.kpi.label}</strong> '
                    f' moved {a.kpi.change_pct:+.1%} · {a.materiality_band.upper()} materiality'
                    f'{" · sparse history" if a.sparse_history else ""}<br>'
                    f'<span style="color:#ffffff">Open Insight Story to trace the movement.</span></div>',
                    unsafe_allow_html=True)
            st.write("")
with data_tab:
    st.caption("All headline values are computed live from transaction, lead, and customer records. No precomputed snapshot is used for this view.")
