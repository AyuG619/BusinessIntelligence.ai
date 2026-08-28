"""Driver attribution via contribution analysis.

Two modes, both deterministic:

1. Product-driver tree (Scenario A):
   Cross-Sell Revenue change -> which product_code contributed how much,
   and for the top product, which lead-status bucket explains the shortfall.

2. Volume / Mix / Pricing decomposition (Scenario B):
   Revenue change = volume_effect + mix_effect + price_effect
   using a standard price-volume-mix bridge on unit_price * volume_units.

No LLM: this is pure SQL/Pandas arithmetic on revenue_transactions.
"""
import sqlite3
import pathlib
import pandas as pd
from core.models import DetectionResult, AttributionResult, DriverContribution
from core.telemetry import timed_stage

ROOT = pathlib.Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "db" / "banking.db"


def _connect(db_path):
    return sqlite3.connect(db_path)


def attribute_by_product(detection: DetectionResult, db_path=DB_PATH) -> AttributionResult:
    """Scenario A style: decompose a KPI change by product_code, then drill
    the top negative driver into a lead-status sub-breakdown."""
    with timed_stage("attribute"):
        kpi = detection.kpi
        conn = _connect(db_path)
        try:
            months_q = """
                SELECT DISTINCT month FROM revenue_transactions
                WHERE product_category = 'cross_sell' AND month <= ?
                ORDER BY month DESC LIMIT 4
            """
            months = pd.read_sql_query(months_q, conn, params=(kpi.month,))["month"].tolist()
            if not months:
                return AttributionResult(detection=detection, drivers=[])
            current_month = months[0]
            prior_months = months[1:] or [current_month]

            branch_clause = "AND branch_id = ?" if kpi.branch_id else ""
            params_base = (kpi.branch_id,) if kpi.branch_id else ()

            cur_q = f"""
                SELECT product_code, SUM(amount) AS amt FROM revenue_transactions
                WHERE product_category='cross_sell' AND month = ? {branch_clause}
                GROUP BY product_code
            """
            cur = pd.read_sql_query(cur_q, conn, params=(current_month, *params_base))

            prior_q = f"""
                SELECT product_code, SUM(amount)/? AS amt FROM revenue_transactions
                WHERE product_category='cross_sell' AND month IN ({",".join("?" * len(prior_months))}) {branch_clause}
                GROUP BY product_code
            """
            prior = pd.read_sql_query(
                prior_q, conn, params=(len(prior_months), *prior_months, *params_base)
            )

            merged = pd.merge(cur, prior, on="product_code", how="outer",
                               suffixes=("_cur", "_prior")).fillna(0)
            merged["delta"] = merged["amt_cur"] - merged["amt_prior"]
            total_delta = merged["delta"].sum()

            drivers = []
            if abs(total_delta) > 0:
                merged = merged.sort_values("delta")  # most negative first
                for _, row in merged.iterrows():
                    if abs(row["delta"]) < 1:
                        continue
                    contribution_pct = row["delta"] / total_delta if total_delta != 0 else 0
                    sub = []
                    if row["delta"] < 0:
                        sub = _drill_lead_status(conn, row["product_code"], kpi.branch_id)
                    drivers.append(DriverContribution(
                        driver_key=row["product_code"],
                        label=row["product_code"].replace("_", " ").title(),
                        contribution_pct=round(float(contribution_pct), 3),
                        sub_drivers=sub,
                    ))

            drivers.sort(key=lambda d: abs(d.contribution_pct), reverse=True)
            return AttributionResult(detection=detection, drivers=drivers, method="product_contribution")
        finally:
            conn.close()


def _drill_lead_status(conn, product_code: str, branch_id: str = None) -> list:
    branch_clause = "AND branch_id = ?" if branch_id else ""
    params = (product_code, branch_id) if branch_id else (product_code,)
    q = f"""
        SELECT status, COUNT(*) AS n FROM leads
        WHERE product_code = ? {branch_clause}
        GROUP BY status
    """
    df = pd.read_sql_query(q, conn, params=params)
    total = df["n"].sum()
    if total == 0:
        return []
    out = []
    for _, row in df.iterrows():
        out.append(DriverContribution(
            driver_key=f"lead_status_{row['status']}",
            label=f"Leads: {row['status'].title()}",
            contribution_pct=round(float(row["n"] / total), 3),
        ))
    out.sort(key=lambda d: d.contribution_pct, reverse=True)
    return out


def attribute_retention_drivers(detection: DetectionResult, db_path=DB_PATH) -> AttributionResult:
    """Retention-specific attribution.

    Unlike revenue, churn/retention doesn't have a clean SQL decomposition
    into named product drivers from this schema — the honest deterministic
    signal here is *how many* customers churned in the affected cohort.
    The competing causal explanations (engagement vs. pricing) are exactly
    what the evidence/confidence layer is designed to adjudicate between,
    so both are surfaced as hypotheses with an even split, and it is the
    evidence corroboration step (not this function) that should downgrade
    confidence when the evidence contradicts itself. This is intentional —
    see Scenario C.
    """
    with timed_stage("attribute"):
        kpi = detection.kpi
        conn = _connect(db_path)
        try:
            branch_clause = "AND branch_id = ?" if kpi.branch_id else ""
            params = (kpi.month, *( (kpi.branch_id,) if kpi.branch_id else () ))
            q = f"""
                SELECT COUNT(*) FROM customers
                WHERE strftime('%Y-%m', onboarded_on) = ? AND status != 'active' {branch_clause}
            """
            churned_count = conn.execute(q, params).fetchone()[0]

            drivers = []
            if churned_count > 0:
                drivers = [
                    DriverContribution(driver_key="engagement_decline",
                                        label="Engagement Decline", contribution_pct=0.5),
                    DriverContribution(driver_key="pricing_pressure",
                                        label="Competitive Pricing", contribution_pct=0.5),
                ]
            return AttributionResult(detection=detection, drivers=drivers,
                                      method="retention_hypothesis_set")
        finally:
            conn.close()


def attribute_new_product_launch(detection: DetectionResult) -> AttributionResult:
    """Scenario D style: a newly launched product has no meaningful driver
    decomposition yet — the honest answer is 'insufficient history', not a
    fabricated breakdown. Returns a single driver so evidence retrieval and
    the recommendation engine have something to key off (matches the
    'sparse_history_new_product' action template and DOC-030's driver_tags).
    """
    drivers = [DriverContribution(
        driver_key="sparse_history_new_product",
        label="New Product — Insufficient History",
        contribution_pct=1.0,
    )]
    return AttributionResult(detection=detection, drivers=drivers, method="new_product_no_decomposition")


def attribute_volume_mix_price(detection: DetectionResult, db_path=DB_PATH) -> AttributionResult:
    """Standard 3-factor volume / mix / price bridge, computed at the
    PRODUCT level (not the branch aggregate).

    Why product-level: with only a single aggregate avg_price = revenue/units,
    "price" and "mix" collapse into the same number — a composition shift
    (more of a cheap product, less of an expensive one) and a genuine
    per-unit price cut are mathematically indistinguishable, and the
    volume+price two-factor split will *always* explain 100% of the delta,
    leaving mix at exactly zero by construction. A true mix effect requires
    knowing each product's own units and price separately:

        volume_effect = (total_cur_units - total_prior_units) * weighted_avg_prior_price
        mix_effect    = total_cur_units * (hypothetical_price - weighted_avg_prior_price)
        price_effect  = sum_i cur_units_i * (cur_price_i - prior_price_i)

    where hypothetical_price is what this period's product mix would have
    cost at last period's per-product prices — i.e. mix_effect isolates the
    revenue impact of selling a different combination of products, holding
    prices fixed. This still reconstructs the total delta exactly (see
    tests/test_attribute.py::test_volume_mix_price_bridge_sums_to_total).
    """
    with timed_stage("attribute"):
        kpi = detection.kpi
        conn = _connect(db_path)
        try:
            branch_clause = "AND branch_id = ?" if kpi.branch_id else ""
            params_branch = (kpi.branch_id,) if kpi.branch_id else ()

            months_q = f"""
                SELECT DISTINCT month FROM revenue_transactions
                WHERE product_category = 'cross_sell' AND month <= ? {branch_clause}
                ORDER BY month DESC LIMIT 2
            """
            months = pd.read_sql_query(
                months_q, conn, params=(kpi.month, *params_branch)
            )["month"].tolist()
            if len(months) < 2:
                return AttributionResult(detection=detection, drivers=[])
            cur_month, prior_month = months[0], months[1]

            def per_product(month):
                q = f"""
                    SELECT product_code, SUM(volume_units) AS units, SUM(amount) AS revenue
                    FROM revenue_transactions
                    WHERE product_category = 'cross_sell' AND month = ? {branch_clause}
                    GROUP BY product_code
                """
                df = pd.read_sql_query(q, conn, params=(month, *params_branch))
                df["price"] = df["revenue"] / df["units"].replace(0, pd.NA)
                return df.set_index("product_code")

            cur = per_product(cur_month)
            prior = per_product(prior_month)

            all_products = set(cur.index) | set(prior.index)
            cur = cur.reindex(all_products, fill_value=0)
            prior = prior.reindex(all_products, fill_value=0)
            # a product with zero prior units has no meaningful "prior price" —
            # treat it as a pure volume/new-product effect by using cur price
            # as its own prior price (contributes 0 to price/mix, all to volume)
            prior_price = prior["price"].where(prior["units"] > 0, cur["price"]).fillna(0)
            cur_price = cur["price"].fillna(0)

            total_cur_units = cur["units"].sum()
            total_prior_units = prior["units"].sum()
            prior_rev = prior["revenue"].sum()
            cur_rev = cur["revenue"].sum()
            total_delta = cur_rev - prior_rev

            weighted_avg_prior_price = (prior_rev / total_prior_units) if total_prior_units else 0

            # hypothetical revenue: this period's product mix, priced at last period's prices
            hypothetical_rev = (cur["units"] * prior_price).sum()
            hypothetical_avg_price = (hypothetical_rev / total_cur_units) if total_cur_units else 0

            volume_effect = (total_cur_units - total_prior_units) * weighted_avg_prior_price
            mix_effect = total_cur_units * (hypothetical_avg_price - weighted_avg_prior_price)
            price_effect = (cur["units"] * (cur_price - prior_price)).sum()

            drivers = []
            if total_delta != 0:
                for key, label, val in [
                    ("volume", "Volume", volume_effect),
                    ("mix", "Mix", mix_effect),
                    ("pricing", "Pricing", price_effect),
                ]:
                    drivers.append(DriverContribution(
                        driver_key=key, label=label,
                        contribution_pct=round(float(val / total_delta), 3),
                    ))
            drivers.sort(key=lambda d: abs(d.contribution_pct), reverse=True)
            return AttributionResult(detection=detection, drivers=drivers, method="volume_mix_price_bridge")
        finally:
            conn.close()
