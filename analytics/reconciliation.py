"""Reconcile a separate marketing extract with governed SQLite lead data.

The CSV represents a campaign system at campaign/month/branch grain, while
the lead table is at lead grain. This module only reconciles totals; it does
not replace the governed KPI calculations.
"""
import csv
import datetime as dt
import pathlib
import sqlite3

ROOT = pathlib.Path(__file__).resolve().parent.parent
MARKETING_PATH = ROOT / "data" / "marketing_campaigns.csv"


def reconcile_marketing(branch_id: str, month: str, db_path, marketing_path=MARKETING_PATH) -> dict:
    """Return comparable marketing and CRM totals plus reconciliation status."""
    with open(marketing_path, newline="", encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle)
                if row["branch_id"] == branch_id and row["month"] == month]

    marketing_spend = sum(float(row["spend"]) for row in rows)
    marketing_conversions = sum(int(row["conversions"]) for row in rows)
    with sqlite3.connect(db_path) as conn:
        crm_leads, crm_conversions = conn.execute(
            "SELECT COUNT(*), SUM(CASE WHEN status = 'converted' THEN 1 ELSE 0 END) "
            "FROM leads WHERE branch_id = ? AND strftime('%Y-%m', created_on) = ?",
            (branch_id, month),
        ).fetchone()

    crm_conversions = crm_conversions or 0
    conversion_gap = marketing_conversions - crm_conversions
    return {
        "branch_id": branch_id,
        "month": month,
        "marketing_campaigns": len(rows),
        "marketing_spend": marketing_spend,
        "marketing_conversions": marketing_conversions,
        "crm_leads": crm_leads,
        "crm_conversions": crm_conversions,
        "conversion_gap": conversion_gap,
        "status": "RECONCILED" if conversion_gap == 0 else "REVIEW",
        "source_grains": "marketing campaign/month/branch; CRM lead",
        "marketing_as_of": max((row["as_of"] for row in rows), default=None),
        "reconciled_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }