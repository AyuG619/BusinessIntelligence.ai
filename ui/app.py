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
def load_dashboard_data(db_path: str, modified_at: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load the dashboard's denormalized view and customer dimension."""
    with sqlite3.connect(db_path) as conn:
        transactions = pd.read_sql_query(
            """SELECT txn_date, month, branch_id, product_code, product_category,
                      customer_id, amount, volume_units, unit_price
               FROM revenue_transactions ORDER BY txn_date""",
            conn,
        )
        customers = pd.read_sql_query(
            "SELECT customer_id, branch_id, segment, status FROM customers", conn
        )
    return transactions, customers


def format_value(value: float, unit: str = "currency") -> str:
    return f"{value:,.0f}" if unit == "currency" else f"{value:.1%}"


def ask_data(question: str, data: pd.DataFrame) -> str:
    """Return a deterministic answer from the currently filtered dataset."""
    if data.empty:
        return "There is no data in the current filter scope. Broaden the filters and try again."
    question = question.lower()
    revenue = data["amount"].sum()
    if "product" in question or "best" in question or "top" in question:
        top = data.groupby("product_code")["amount"].sum().idxmax()
        value = data.groupby("product_code")["amount"].sum().max()
        return f"{top.replace('_', ' ').title()} leads the current scope with {value:,.0f} in revenue."
    if "region" in question or "branch" in question:
        top = data.groupby("branch_id")["amount"].sum().idxmax()
        return f"{top} is the strongest branch in the current scope, contributing {data.loc[data.branch_id == top, 'amount'].sum():,.0f}."
    if "volume" in question or "unit" in question:
        return f"The filtered scope contains {data['volume_units'].sum():,.0f} units across {data['customer_id'].nunique():,} customers."
    return f"The current scope contains {len(data):,} transactions and {revenue:,.0f} in revenue. Ask about products, branches, volume, or customers."


def metric_card(label: str, value: str, delta: str, tone: str = "neutral") -> None:
    st.markdown(
        f'<div class="metric-card"><div class="metric-label">{label}</div>'
        f'<div class="metric-value">{value}</div>'
        f'<div class="metric-delta {tone}">{delta}</div></div>',
        unsafe_allow_html=True,
    )


if "dashboard_question" not in st.session_state:
    st.session_state.dashboard_question = ""

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
st.sidebar.caption(f"{user['role'].replace('_', ' ').title()} · {user['branch_id'] or 'All branches'}")

if not DB_PATH.exists():
    st.error("The dashboard data file is missing. Run the database setup scripts from README.md, then refresh this page.")
    st.stop()

transactions, customers = load_dashboard_data(str(DB_PATH), DB_PATH.stat().st_mtime)
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

st.markdown('<div class="section-label">Ask your data</div>', unsafe_allow_html=True)
question_col, button_col = st.columns([5, 1])
with question_col:
    question = st.text_input("Question", placeholder="Which product is leading this scope?", label_visibility="collapsed", key="dashboard_question")
with button_col:
    ask = st.button("Ask", type="primary", use_container_width=True)
if ask and question:
    st.markdown(f'<div class="insight-callout"><strong>Answer</strong><br>{ask_data(question, filtered)}</div>', unsafe_allow_html=True)

st.caption(f"Showing {len(filtered):,} of {len(transactions):,} transactions · Data updates from local SQLite records")
