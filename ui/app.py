"""Entry point. Handles the demo login/persona selector, then routes to
pages via the sidebar (Streamlit's native multipage navigation using
ui/pages/*.py).
"""
"""Premium dashboard shell for BusinessIntelligence.ai."""
import pathlib
import sqlite3
import sys

import streamlit as st
from streamlit.errors import StreamlitAPIException

try:
    st.set_page_config(
        page_title="BusinessIntelligence.ai | Command Center",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )
except StreamlitAPIException:
    # Some Streamlit multipage runtimes configure the page before the entry script.
    pass

import pandas as pd
import plotly.express as px

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.security import DEMO_USERS  # noqa: E402
from ui.components.theme import inject_theme  # noqa: E402

DB_PATH = ROOT / "db" / "banking.db"

inject_theme()


@st.cache_data(show_spinner=False)
def load_dashboard_data(db_path: str, modified_at: float, user_id: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load the dashboard's denormalized view and customer dimension."""
    with sqlite3.connect(db_path) as conn:
        user = DEMO_USERS[user_id]
        scope_clause = ""
        params = []
        if user["role"] == "relationship_manager":
            scope_clause = "WHERE r.rm_id = ?"
            params.append(user_id)
        elif user["role"] == "branch_head":
            scope_clause = "WHERE r.branch_id = ?"
            params.append(user["branch_id"])
        transactions = pd.read_sql_query(
            """SELECT txn_date, month, branch_id, rm_id, product_code, product_category,
                      customer_id, amount, volume_units, unit_price
               FROM revenue_transactions r """ + scope_clause + " ORDER BY txn_date",
            conn, params=params,
        )
        customer_scope = ""
        customer_params = []
        if user["role"] == "relationship_manager":
            customer_scope = "WHERE rm_id = ?"
            customer_params.append(user_id)
        elif user["role"] == "branch_head":
            customer_scope = "WHERE branch_id = ?"
            customer_params.append(user["branch_id"])
        customers = pd.read_sql_query(
            "SELECT customer_id, branch_id, segment, status FROM customers " + customer_scope,
            conn, params=customer_params,
        )
    return transactions, customers


def format_value(value: float, unit: str = "currency") -> str:
    return f"{value:,.0f}" if unit == "currency" else f"{value:.1%}"


def metric_card(label: str, value: str, delta: str, tone: str = "neutral") -> None:
    st.markdown(
        f'<div class="metric-card"><div class="metric-label">{label}</div>'
        f'<div class="metric-value">{value}</div>'
        f'<div class="metric-delta {tone}">{delta}</div></div>',
        unsafe_allow_html=True,
    )


st.sidebar.markdown("## BI / INSIGHT")
st.sidebar.caption("Command center · live banking performance")
st.sidebar.markdown("### Navigate")
st.sidebar.page_link("app.py", label="Command center", icon="🏠")
st.sidebar.page_link("pages/1_KPI_Overview.py", label="KPI Overview", icon="📈")
st.sidebar.page_link("pages/2_Insight_Story.py", label="Insight Story", icon="🔎")
st.sidebar.page_link("pages/3_Conversational.py", label="Ask your data", icon="💬")
st.sidebar.page_link("pages/4_Security_Demo.py", label="Security & access", icon="🔐")

st.sidebar.divider()
st.sidebar.markdown("### Workspace")
user_id = st.sidebar.selectbox("User", list(DEMO_USERS), key="dashboard_user")
user = DEMO_USERS[user_id]
st.session_state.user_id = user_id
st.session_state.persona = "executive" if user["role"] == "admin" else user["role"]
st.sidebar.caption(f"{user['role'].replace('_', ' ').title()} · {user['branch_id'] or 'All branches'}")
scope_label = "all branches" if user["role"] == "admin" else (
    "own customers" if user["role"] == "relationship_manager" else "all customers in own branch"
)
st.sidebar.caption(f"Access scope: {scope_label}")

if not DB_PATH.exists():
    st.error("The dashboard data file is missing. Run the database setup scripts from README.md, then refresh this page.")
    st.stop()

transactions, customers = load_dashboard_data(str(DB_PATH), DB_PATH.stat().st_mtime, user_id)
transactions["txn_date"] = pd.to_datetime(transactions["txn_date"])
transactions = transactions.merge(customers[["customer_id", "segment"]], on="customer_id", how="left")

st.sidebar.markdown("### Filters")
date_range = st.sidebar.date_input(
    "Date range",
    value=(transactions["txn_date"].min().date(), transactions["txn_date"].max().date()),
    min_value=transactions["txn_date"].min().date(),
    max_value=transactions["txn_date"].max().date(),
    key="dashboard_dates",
)
regions = st.sidebar.multiselect("Branch", sorted(transactions["branch_id"].unique()), key="dashboard_branches")
products = st.sidebar.multiselect("Product", sorted(transactions["product_code"].unique()), key="dashboard_products")
segments = st.sidebar.multiselect("Segment", sorted(transactions["segment"].dropna().unique()), key="dashboard_segments")

filtered = transactions.copy()
if len(date_range) == 2:
    filtered = filtered[filtered["txn_date"].between(pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1]))]
if regions:
    filtered = filtered[filtered["branch_id"].isin(regions)]
if products:
    filtered = filtered[filtered["product_code"].isin(products)]
if segments:
    filtered = filtered[filtered["segment"].isin(segments)]

st.markdown('<div class="eyebrow">Command center / live scope</div>', unsafe_allow_html=True)
header_col, action_col = st.columns([4, 1])
with header_col:
    st.title("Performance, in focus.")
    st.markdown('<p class="dashboard-subtitle">A calm view of the signals, movements, and opportunities behind your banking book.</p>', unsafe_allow_html=True)
with action_col:
    st.write("")
    st.download_button("Download CSV", filtered.to_csv(index=False), "bi-filtered-transactions.csv", "text/csv", use_container_width=True)

with st.expander("About this dashboard"):
    st.write("Use the sidebar to narrow the live transaction dataset by time, branch, product, and customer segment. Every value and chart below updates from that scope. Open Insight Story when a signal needs explanation.")

if filtered.empty:
    st.warning("No records match the current filters. Broaden the date range or remove a filter to continue.")
    st.stop()

revenue = filtered["amount"].sum()
prior_month = filtered[filtered["txn_date"] < filtered["txn_date"].max().replace(day=1)]
prior_revenue = prior_month["amount"].sum()
delta = (revenue - prior_revenue) / prior_revenue if prior_revenue else 0
metrics = st.columns(4, gap="medium")
for col, args in zip(metrics, [
    ("Revenue", format_value(revenue), f"{delta:+.1%} vs prior scope", "positive" if delta >= 0 else "negative"),
    ("Transactions", f"{len(filtered):,}", f"{filtered['volume_units'].sum():,.0f} units", "neutral"),
    ("Customers reached", f"{filtered['customer_id'].nunique():,}", f"{filtered['branch_id'].nunique()} branches", "neutral"),
    ("Avg. transaction", format_value(filtered["amount"].mean()), "per transaction", "neutral"),
]):
    with col:
        metric_card(*args)

st.markdown('<div class="section-label">Performance overview</div>', unsafe_allow_html=True)
trend_tab, product_tab, table_tab = st.tabs(["Revenue trend", "Product mix", "Transaction detail"])
with trend_tab:
    trend = filtered.groupby("txn_date", as_index=False)["amount"].sum()
    fig = px.area(trend, x="txn_date", y="amount", template="plotly_dark")
    fig.update_traces(line_color="#ffffff", fillcolor="rgba(255,255,255,.08)")
    fig.update_layout(height=340, margin=dict(l=0, r=0, t=20, b=0), paper_bgcolor="#000000", plot_bgcolor="#000000", font_color="#ffffff", xaxis_title=None, yaxis_title=None)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
with product_tab:
    product_mix = filtered.groupby("product_code", as_index=False)["amount"].sum().sort_values("amount", ascending=True)
    fig = px.bar(product_mix, x="amount", y="product_code", orientation="h", template="plotly_dark")
    fig.update_traces(marker_color="#ffffff")
    fig.update_layout(height=340, margin=dict(l=0, r=0, t=20, b=0), paper_bgcolor="#000000", plot_bgcolor="#000000", font_color="#ffffff", xaxis_title=None, yaxis_title=None)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
with table_tab:
    st.dataframe(filtered.sort_values("txn_date", ascending=False).head(100), use_container_width=True, hide_index=True)

st.caption(f"Showing {len(filtered):,} of {len(transactions):,} transactions · Data updates from local SQLite records")
