"""Overlays the 5 engineered demo scenarios on top of the baseline data
produced by generate_synthetic_data.py. Run generate_synthetic_data.py and
generate_documents.py first.

Scenario A — Cross-Sell Revenue down, traced to credit_card -> unresolved leads
Scenario B — Branch revenue down via volume/mix/pricing bridge
Scenario C — Retention down with contradictory evidence (handled via documents)
Scenario D — Platinum Edge: only current-month data exists (sparse history)
Scenario E — Security: uses existing RM-103 vs RM-108 customer ownership (no data change needed)
"""
import sqlite3
import random
import pathlib
import datetime as dt

ROOT = pathlib.Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "db" / "banking.db"

random.seed(99)


def get_months(conn):
    rows = conn.execute("SELECT DISTINCT month FROM revenue_transactions ORDER BY month").fetchall()
    return [r[0] for r in rows]


def scenario_a_credit_card_shortfall(conn):
    """Scenario A: suppress current-month credit_card revenue at BR-01 and
    open a batch of unresolved (status='open') credit_card leads."""
    months = get_months(conn)
    current = months[-1]
    conn.execute(
        "UPDATE revenue_transactions SET amount = amount * 0.55, unit_price = unit_price * 0.55 "
        "WHERE month = ? AND branch_id = 'BR-01' AND product_code = 'credit_card'",
        (current,),
    )
    # ensure a clear batch of unresolved leads exists for BR-01 credit_card
    cust_ids = [r[0] for r in conn.execute(
        "SELECT customer_id FROM customers WHERE branch_id='BR-01' AND rm_id='RM-103' LIMIT 10"
    ).fetchall()]
    lead_id_start = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0] + 1
    for i, cust_id in enumerate(cust_ids):
        lead_id = f"LEAD-SCEN-A-{i:03d}"
        conn.execute(
            "INSERT OR REPLACE INTO leads VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?)",
            (lead_id, cust_id, "RM-103", "BR-01", "credit_card",
             f"{current}-05", f"{current}-05", round(random.uniform(3000, 15000), 2)),
        )


def scenario_b_volume_mix_price(conn):
    """Scenario B: engineer three *independent* effects so the bridge in
    analytics/attribute.attribute_volume_mix_price produces a real 3-way
    split instead of one effect swamping the others:

    1. VOLUME effect  — fewer total units sold this month (same products, same prices)
    2. PRICE effect   — a flat discount applied per-unit across the board
    3. MIX effect     — some higher-priced product_code transactions (personal_loan)
                        are reclassified as a lower-priced product (salary_account),
                        changing the average price via composition, not per-unit pricing

    A uniform "amount *= k" scale-down (the old approach) collapses mix to ~0%
    because it never changes the *composition* of what's being sold — only
    volume and price move, so mix has nothing to explain.
    """
    months = get_months(conn)
    current = months[-1]

    # 1) Volume effect: ~15% fewer units, same unit_price, same product mix
    conn.execute(
        "UPDATE revenue_transactions "
        "SET volume_units = MAX(1, CAST(volume_units * 0.85 AS INT)) "
        "WHERE month = ? AND branch_id = 'BR-01' AND product_code != 'platinum_edge'",
        (current,),
    )

    # 2) Price effect: ~5% flat discount per unit
    conn.execute(
        "UPDATE revenue_transactions "
        "SET unit_price = unit_price * 0.95 "
        "WHERE month = ? AND branch_id = 'BR-01' AND product_code != 'platinum_edge'",
        (current,),
    )

    # Recompute amount to reflect the volume + price changes before the mix shift
    conn.execute(
        "UPDATE revenue_transactions SET amount = volume_units * unit_price "
        "WHERE month = ? AND branch_id = 'BR-01' AND product_code != 'platinum_edge'",
        (current,),
    )

    # 3) Mix effect: reclassify ~40% of this month's personal_loan (high-price)
    # transactions as salary_account (low-price) — same customers/volumes,
    # different composition, which is exactly what a "mix shift" is.
    salary_avg_price_row = conn.execute(
        "SELECT AVG(unit_price) FROM revenue_transactions "
        "WHERE product_code = 'salary_account' AND branch_id = 'BR-01' AND month = ?",
        (current,),
    ).fetchone()
    salary_avg_price = salary_avg_price_row[0] or 300.0

    loan_txns = conn.execute(
        "SELECT txn_id, volume_units FROM revenue_transactions "
        "WHERE month = ? AND branch_id = 'BR-01' AND product_code = 'personal_loan'",
        (current,),
    ).fetchall()
    n_to_shift = max(1, int(len(loan_txns) * 0.4))

    for txn_id, units in loan_txns[:n_to_shift]:
        new_amount = round(salary_avg_price * units, 2)
        conn.execute(
            "UPDATE revenue_transactions SET product_code = 'salary_account', "
            "unit_price = ?, amount = ? WHERE txn_id = ?",
            (round(salary_avg_price, 2), new_amount, txn_id),
        )


def scenario_c_retention_conflict(conn):
    """Scenario C: mark most of the *current onboarding cohort's* BR-01
    customers as churned/dormant. customer_retention_rate is computed as an
    onboarding-cohort active-ratio (see analytics/kpi_calculator.py), so the
    movement must land in the current month's cohort specifically, not just
    anywhere in the branch. Contradictory evidence already seeded via
    generate_documents.py (DOC-020 'engagement declined' vs DOC-021/022
    'stable/pricing-driven')."""
    months = get_months(conn)
    current = months[-1]
    cust_ids = [r[0] for r in conn.execute(
        "SELECT customer_id FROM customers WHERE branch_id='BR-01' AND onboarded_on LIKE ? ORDER BY customer_id",
        (f"{current}%",),
    ).fetchall()]
    # churn most (not all) of this cohort so the movement is a clear drop, not to zero
    n_to_churn = max(1, int(len(cust_ids) * 0.7))
    for cust_id in cust_ids[:n_to_churn]:
        conn.execute("UPDATE customers SET status='churned' WHERE customer_id=?", (cust_id,))


def scenario_d_sparse_platinum_edge(conn):
    """Scenario D: platinum_edge only has transactions in the current month
    (simulating a product launched 3 weeks ago) -> detect.py should flag
    sparse_history=True when this KPI/product is queried in isolation.

    Kept deliberately small in absolute terms so it doesn't swamp the
    overall Cross-Sell Revenue aggregate used by Scenario A/B — this
    scenario is meant to be explored via the product-scoped series
    (see analytics/kpi_calculator.compute_product_revenue_series), not
    the branch-wide KPI total.
    """
    # Remove ALL platinum_edge history (any month) so it starts clean,
    # then add a small, controlled current-month-only footprint.
    conn.execute("DELETE FROM revenue_transactions WHERE product_code='platinum_edge'")
    months = get_months(conn)
    current = months[-1]
    rows = conn.execute(
        "SELECT customer_id, rm_id, branch_id FROM customers WHERE branch_id='BR-01' LIMIT 3"
    ).fetchall()
    for cust_id, rm_id, branch_id in rows:
        conn.execute(
            "INSERT INTO revenue_transactions "
            "(customer_id, branch_id, rm_id, product_code, product_category, txn_date, month, "
            "amount, volume_units, unit_price) VALUES (?, ?, ?, 'platinum_edge', 'cross_sell', ?, ?, ?, ?, ?)",
            (cust_id, branch_id, rm_id, f"{current}-18", current, 900.0, 1, 900.0),
        )


def scenario_e_security_note(conn):
    """Scenario E needs no data change — RM-103 and RM-108 already own
    disjoint customer sets from generate_synthetic_data.py. This function
    just verifies that precondition."""
    rm103 = conn.execute("SELECT COUNT(*) FROM customers WHERE rm_id='RM-103'").fetchone()[0]
    rm108 = conn.execute("SELECT COUNT(*) FROM customers WHERE rm_id='RM-108'").fetchone()[0]
    if rm103 == 0 or rm108 == 0:
        print("WARNING: RM-103 or RM-108 has no customers — check branch/RM seeding.")


def seed(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    try:
        scenario_a_credit_card_shortfall(conn)
        scenario_b_volume_mix_price(conn)
        scenario_c_retention_conflict(conn)
        scenario_d_sparse_platinum_edge(conn)
        scenario_e_security_note(conn)
        conn.commit()
        print("Seeded 5 scenarios (A-E) on top of baseline data.")
    finally:
        conn.close()


if __name__ == "__main__":
    seed()
