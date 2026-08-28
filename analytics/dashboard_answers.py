"""Deterministic answers for the Command Center's scoped transaction data."""
import pandas as pd


def _summary(data: pd.DataFrame, label: str) -> str:
    revenue = data["amount"].sum()
    transactions = len(data)
    customers = data["customer_id"].nunique()
    return f"{label}: revenue {revenue:,.0f}, {transactions:,} transactions, {customers:,} customers"


def answer_question(question: str, data: pd.DataFrame, role: str) -> str:
    """Answer supported questions from already scope-filtered data only."""
    if data.empty:
        return "There is no data in the current filter scope. Broaden the filters and try again."

    normalized = question.strip().lower()
    if "branch" in normalized and any(term in normalized for term in ("compare", "comparison", "performance", "better", "strongest")):
        if role != "admin":
            return "Branch comparison is restricted to Admin. Your role can view only its authorized branch scope."
        rows = [_summary(group, f"{branch}") for branch, group in data.groupby("branch_id")]
        return "Branch comparison: " + "; ".join(rows) + "."

    if ("rm" in normalized or "manager" in normalized) and any(term in normalized for term in ("compare", "comparison", "performance", "better", "strongest")):
        if role not in ("branch_head", "admin"):
            return "RM comparison is restricted to Branch Head or Admin views."
        rows = [_summary(group, f"{rm}") for rm, group in data.groupby("rm_id")]
        return "RM performance comparison: " + "; ".join(rows) + "."

    if any(term in normalized for term in ("product", "best", "top")):
        totals = data.groupby("product_code")["amount"].sum().sort_values(ascending=False)
        top = totals.index[0]
        return f"{top.replace('_', ' ').title()} leads this scope with {totals.iloc[0]:,.0f} in revenue."

    if any(term in normalized for term in ("volume", "unit")):
        return f"This scope contains {data['volume_units'].sum():,.0f} units across {data['customer_id'].nunique():,} customers."

    if any(term in normalized for term in ("customer", "customers")):
        return f"This scope contains {data['customer_id'].nunique():,} distinct customers across {len(data):,} transactions."

    if any(term in normalized for term in ("revenue", "sales", "transaction", "current scope")):
        return _summary(data, "Current scope") + "."

    return ("I can answer product leaders, revenue, volume, customer counts, "
            "or authorized branch/RM comparisons. Ask a specific question about this scope.")