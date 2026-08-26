import sys
import pathlib
import sqlite3
import streamlit as st

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
DB_PATH = ROOT / "db" / "banking.db"

from core.security import (  # noqa: E402
    DEMO_USERS, ROLES, check_customer_access, check_branch_access,
    check_sensitive_field_access, AccessDenied, recent_audit_events,
)
from ui.components.theme import inject_theme, page_header, section_label  # noqa: E402

st.set_page_config(page_title="Security Demo", layout="wide")
inject_theme()
page_header("Governance lab", "Security & access", "See how role-based permissions protect customer data and leave an auditable trail.")

user_id = st.session_state.get("user_id", "RM-103")
user = DEMO_USERS[user_id]
role = ROLES[user["role"]]

section_label("Current identity")
st.subheader(f"{user_id} · {role['label']}")
c1, c2 = st.columns(2)
with c1:
    st.markdown(f"**Role:** {role['label']}")
    st.markdown(f"**Branch:** {user['branch_id'] or 'All (admin)'}")
    st.markdown("**Allowed:**")
    for a in role["can_view"]:
        st.markdown(f"✅ {a.replace('_', ' ')}")
with c2:
    st.markdown("**Restricted:**")
    for d_ in role["denied"]:
        st.markdown(f"❌ {d_.replace('_', ' ')}")
    if not role["denied"]:
        st.caption("No restrictions for this role.")

section_label("Test permissions")
st.subheader("Try a controlled access request")

conn = sqlite3.connect(DB_PATH)
other_customers = conn.execute(
    "SELECT customer_id, rm_id, branch_id FROM customers WHERE rm_id != ? LIMIT 5",
    (user_id,) if user["role"] == "relationship_manager" else ("__none__",),
).fetchall()
own_customers = conn.execute(
    "SELECT customer_id FROM customers WHERE rm_id = ? LIMIT 5", (user_id,)
).fetchall()
conn.close()

colx, coly = st.columns(2)
with colx:
    st.markdown("**Try: view your own customer**")
    if own_customers:
        target = st.selectbox("Own customer", [c[0] for c in own_customers], key="own")
        if st.button("Attempt access", key="btn_own"):
            try:
                check_customer_access(user_id, target)
                st.success(f"✅ ACCESS ALLOWED — {user_id} may view {target}.")
            except AccessDenied as e:
                st.error(f"❌ ACCESS DENIED — {e}")
    else:
        st.caption("No customers owned by this user.")

with coly:
    st.markdown("**Try: view RM-108's customer (or another RM's, if not you)**")
    if other_customers:
        target2 = st.selectbox("Other RM's customer", [c[0] for c in other_customers], key="other")
        if st.button("Attempt access", key="btn_other"):
            try:
                check_customer_access(user_id, target2)
                st.success(f"✅ ACCESS ALLOWED — {user_id} may view {target2}.")
            except AccessDenied as e:
                st.error(f"❌ ACCESS DENIED — Reason: {e}\n\nAudit event recorded.")
    else:
        st.caption("This role can already see all customers.")

st.markdown("**Try: view sensitive income data**")
if st.button("Attempt sensitive field access"):
    try:
        check_sensitive_field_access(user_id, "income_band")
        st.success("✅ ACCESS ALLOWED — sensitive income data visible to this role.")
    except AccessDenied as e:
        st.error(f"❌ ACCESS DENIED — {e}\n\nAudit event recorded.")

st.markdown("**Try: view another branch's aggregate**")
other_branch = "BR-02" if user["branch_id"] != "BR-02" else "BR-01"
if st.button(f"Attempt access to {other_branch} aggregate"):
    try:
        check_branch_access(user_id, other_branch)
        st.success(f"✅ ACCESS ALLOWED — {user_id} may view {other_branch} aggregate.")
    except AccessDenied as e:
        st.error(f"❌ ACCESS DENIED — {e}\n\nAudit event recorded.")

section_label("Audit trail")
st.subheader("Recent access decisions")
events = recent_audit_events(limit=15)
if events:
    st.dataframe(events, use_container_width=True)
else:
    st.caption("No audit events yet — try an access attempt above.")
