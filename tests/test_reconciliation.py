import sqlite3

from analytics.reconciliation import reconcile_marketing
from feedback.feedback import confidence_adjustment


def test_marketing_reconciliation_reports_cross_source_gap(tmp_path):
    db_path = tmp_path / "reconciliation.db"
    setup = sqlite3.connect(db_path)
    setup.execute("CREATE TABLE leads (branch_id TEXT, status TEXT, created_on TEXT)")
    setup.executemany(
        "INSERT INTO leads VALUES (?, ?, ?)",
        [("BR-01", "converted", "2026-07-05"), ("BR-01", "open", "2026-07-06")],
    )
    setup.commit()
    setup.close()
    result = reconcile_marketing("BR-01", "2026-07", db_path)

    assert result["source_grains"] == "marketing campaign/month/branch; CRM lead"
    assert result["marketing_as_of"] == "2026-08-01"
    assert result["status"] == "REVIEW"
    assert result["conversion_gap"] == 10


def test_feedback_adjustment_requires_sample_and_is_bounded(tmp_path):
    db_path = tmp_path / "feedback.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE feedback (insight_ref TEXT, useful INTEGER)"
    )
    conn.executemany(
        "INSERT INTO feedback VALUES (?, ?)",
        [("cross_sell_revenue|2026-07|BR-01", 1)] * 2
        + [("cross_sell_revenue|2026-06|BR-01", 0)] * 8,
    )
    conn.commit()
    conn.close()

    assert confidence_adjustment("cross_sell_revenue", db_path) == -0.06