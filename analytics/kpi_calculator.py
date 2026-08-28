"""Deterministic KPI computation — pure SQL/Pandas, zero LLM involvement.

This module is the proof point that the numbers are not hallucinated:
every KPI value returned here can be reproduced by re-running the SQL.
"""
import sqlite3
import pathlib
import yaml
import pandas as pd
from core.models import KPIResult
from core.telemetry import timed_stage

ROOT = pathlib.Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "db" / "banking.db"
KPI_CONFIG_PATH = ROOT / "config" / "kpi_definitions.yaml"

with open(KPI_CONFIG_PATH) as f:
    _CFG = yaml.safe_load(f)

KPIS = _CFG["kpis"]


def _connect(db_path):
    return sqlite3.connect(db_path)


def compute_kpi_series(kpi_key: str, branch_id: str = None, db_path=DB_PATH,
                       rm_id: str = None) -> pd.DataFrame:
    """Returns a monthly time series for a KPI, optionally scoped to a branch.

    Columns: month, value
    """
    cfg = KPIS[kpi_key]
    conn = _connect(db_path)
    try:
        if kpi_key == "cross_sell_revenue":
            q = f"""
                SELECT month, SUM(amount) AS value
                FROM revenue_transactions
                WHERE {cfg['filter']}
                {"AND branch_id = ?" if branch_id else ""}
                {"AND rm_id = ?" if rm_id else ""}
                GROUP BY month ORDER BY month
            """
            params = tuple(value for value in (branch_id, rm_id) if value)
            df = pd.read_sql_query(q, conn, params=params)

        elif kpi_key == "lead_conversion_rate":
            q = f"""
                SELECT strftime('%Y-%m', created_on) AS month,
                       SUM(CASE WHEN status = 'converted' THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS value
                FROM leads
                WHERE 1=1 {"AND branch_id = ?" if branch_id else ""}
                {"AND rm_id = ?" if rm_id else ""}
                GROUP BY month ORDER BY month
            """
            params = tuple(value for value in (branch_id, rm_id) if value)
            df = pd.read_sql_query(q, conn, params=params)

        elif kpi_key == "customer_retention_rate":
            q = f"""
                SELECT strftime('%Y-%m', onboarded_on) AS month,
                       SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS value
                FROM customers
                WHERE 1=1 {"AND branch_id = ?" if branch_id else ""}
                {"AND rm_id = ?" if rm_id else ""}
                GROUP BY month ORDER BY month
            """
            params = tuple(value for value in (branch_id, rm_id) if value)
            df = pd.read_sql_query(q, conn, params=params)

        elif kpi_key == "revenue_per_customer":
            q = f"""
                SELECT r.month AS month, SUM(r.amount) * 1.0 / COUNT(DISTINCT r.customer_id) AS value
                FROM revenue_transactions r
                WHERE 1=1 {"AND r.branch_id = ?" if branch_id else ""}
                {"AND r.rm_id = ?" if rm_id else ""}
                GROUP BY r.month ORDER BY r.month
            """
            params = tuple(value for value in (branch_id, rm_id) if value)
            df = pd.read_sql_query(q, conn, params=params)
        else:
            raise ValueError(f"Unknown kpi_key: {kpi_key}")

        return df
    finally:
        conn.close()


def latest_kpi_result(kpi_key: str, branch_id: str = None, db_path=DB_PATH) -> KPIResult:
    """Latest month's actual vs. trailing-3-month average (the 'expected' baseline)."""
    with timed_stage("kpi_calculator"):
        cfg = KPIS[kpi_key]
        df = compute_kpi_series(kpi_key, branch_id, db_path)
        if df.empty or len(df) < 2:
            raise ValueError(f"Not enough data to compute {kpi_key}")

        df = df.dropna(subset=["value"]).reset_index(drop=True)
        latest = df.iloc[-1]
        history = df.iloc[:-1]
        baseline_window = history.tail(3)
        expected = baseline_window["value"].mean() if not baseline_window.empty else history["value"].mean()
        actual = latest["value"]
        change_pct = 0.0 if expected == 0 else (actual - expected) / expected

        return KPIResult(
            kpi_key=kpi_key,
            label=cfg["label"],
            month=latest["month"],
            branch_id=branch_id,
            actual=float(actual),
            expected=float(expected),
            change_pct=float(change_pct),
            unit=cfg["unit"],
        )


def all_latest_kpis(branch_id: str = None, db_path=DB_PATH) -> list:
    return [latest_kpi_result(k, branch_id, db_path) for k in KPIS.keys()]


def compare_kpi_by_scope(kpi_key: str, scope: str, branch_id: str = None,
                         db_path=DB_PATH) -> list:
    """Return latest KPI values grouped by authorized branch or RM scope."""
    conn = _connect(db_path)
    try:
        column = "branch_id" if scope == "branch" else "rm_id"
        clauses = ["1=1"]
        params = []
        if branch_id:
            clauses.append(f"{column if scope == 'branch' else 'branch_id'} = ?")
            params.append(branch_id)
        ids = [row[0] for row in conn.execute(
            f"SELECT DISTINCT {column} FROM revenue_transactions WHERE {' AND '.join(clauses)} ORDER BY {column}",
            params,
        ).fetchall()]
    finally:
        conn.close()

    return [
        {"id": identifier, "kpi": latest_kpi_result(
            kpi_key,
            branch_id=identifier if scope == "branch" else branch_id,
            db_path=db_path,
        ).actual if scope == "branch" else _latest_kpi_for_rm(kpi_key, branch_id, identifier, db_path)}
        for identifier in ids
    ]


def _latest_kpi_for_rm(kpi_key: str, branch_id: str, rm_id: str, db_path=DB_PATH) -> float:
    df = compute_kpi_series(kpi_key, branch_id=branch_id, db_path=db_path, rm_id=rm_id)
    if df.empty:
        return 0.0
    return float(df.iloc[-1]["value"])


def compute_product_revenue_series(product_code: str, branch_id: str = None, db_path=DB_PATH) -> pd.DataFrame:
    """Monthly revenue series scoped to a single product (e.g. a newly
    launched product like platinum_edge). Used to demonstrate sparse-history
    detection independent of the branch-wide KPI aggregate. Columns: month, value.
    """
    conn = _connect(db_path)
    try:
        branch_clause = "AND branch_id = ?" if branch_id else ""
        params = (product_code, branch_id) if branch_id else (product_code,)
        q = f"""
            SELECT month, SUM(amount) AS value FROM revenue_transactions
            WHERE product_code = ? {branch_clause}
            GROUP BY month ORDER BY month
        """
        return pd.read_sql_query(q, conn, params=params)
    finally:
        conn.close()


def latest_product_kpi_result(product_code: str, label: str, branch_id: str = None,
                               db_path=DB_PATH) -> KPIResult:
    """Same shape as latest_kpi_result but scoped to a single product,
    for exploring a specific driver (e.g. Scenario D's new-product launch)."""
    df = compute_product_revenue_series(product_code, branch_id, db_path)
    df = df.dropna(subset=["value"]).reset_index(drop=True)
    if df.empty:
        raise ValueError(f"No revenue data for product {product_code}")
    latest = df.iloc[-1]
    history = df.iloc[:-1]
    if history.empty:
        expected = 0.0
    else:
        expected = history.tail(3)["value"].mean()
    actual = latest["value"]
    change_pct = 0.0 if expected == 0 else (actual - expected) / expected
    return KPIResult(
        kpi_key=f"product::{product_code}",
        label=label,
        month=latest["month"],
        branch_id=branch_id,
        actual=float(actual),
        expected=float(expected),
        change_pct=float(change_pct),
        unit="currency",
    )


def compare_kpi_periods(kpi_key: str, branch_id: str = None, db_path=DB_PATH) -> dict:
    """Compare the latest KPI with year-over-year, quarter, and rolling-year references."""
    df = compute_kpi_series(kpi_key, branch_id, db_path).dropna(subset=["value"])
    if df.empty:
        return {}
    df["month"] = pd.to_datetime(df["month"].astype(str) + "-01")
    latest = df.iloc[-1]
    current_month = latest["month"]
    result = {"current": float(latest["value"]), "month": current_month.strftime("%Y-%m")}
    for key, mask in {
        "same_month_last_year": df["month"] == current_month - pd.DateOffset(years=1),
        "prior_quarter_average": (df["month"] < current_month) & (df["month"] >= current_month - pd.DateOffset(months=3)),
        "rolling_year_average": (df["month"] < current_month) & (df["month"] >= current_month - pd.DateOffset(months=12)),
    }.items():
        values = df.loc[mask, "value"]
        result[key] = float(values.mean()) if not values.empty else None
    return result
