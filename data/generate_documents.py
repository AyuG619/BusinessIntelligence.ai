"""Generates ~40 synthetic evidence documents across the 5 source types
in config/source_registry.yaml. No embeddings — just text + driver_tags
for scoped keyword retrieval (see evidence/retrieval.py).
"""
import sqlite3
import random
import datetime as dt
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "db" / "banking.db"

random.seed(7)

TODAY = dt.date.today()


def d(days_ago: int) -> str:
    return (TODAY - dt.timedelta(days=days_ago)).isoformat()


DOCS = [
    # --- Scenario A: unresolved leads / credit card / salary account drivers ---
    dict(doc_id="DOC-001", source_type="crm_notes", title="RM-103 follow-up log — Q2",
         body="Several salary account customers flagged as credit card candidates were not "
              "followed up within SLA. Missed follow-up window noted for 6 leads this month.",
         branch_id="BR-01", rm_id="RM-103", product_code="credit_card",
         driver_tags="lead status open,unresolved leads,credit card,follow-up",
         created_on=d(5)),
    dict(doc_id="DOC-002", source_type="lead_records", title="Lead pipeline aging report",
         body="Open leads for credit card cross-sell have grown; median age of open lead now "
              "18 days, above the 10-day target, indicating a growing unresolved backlog.",
         branch_id="BR-01", rm_id=None, product_code="credit_card",
         driver_tags="lead status open,unresolved leads,credit card",
         created_on=d(3)),
    dict(doc_id="DOC-003", source_type="campaign_reports", title="Salary account campaign — May",
         body="Salary account acquisition campaign performance was stable month over month; "
              "no material change in conversion or spend.",
         branch_id="BR-01", rm_id=None, product_code="salary_account",
         driver_tags="salary account,campaign",
         created_on=d(20)),

    # --- Scenario B: volume/mix/pricing ---
    dict(doc_id="DOC-010", source_type="market_notes", title="Regional pricing note — cross-sell",
         body="Competing banks reduced credit card annual fees by 15% this quarter, increasing "
              "price sensitivity among affluent segment customers.",
         branch_id="BR-01", rm_id=None, product_code="credit_card",
         driver_tags="pricing,mix,credit card,competitive",
         created_on=d(10)),
    dict(doc_id="DOC-011", source_type="campaign_reports", title="Branch volume report",
         body="Transaction volume at BR-01 declined slightly due to a shift in customer segment "
              "mix toward mass-market accounts with smaller average ticket size.",
         branch_id="BR-01", rm_id=None, product_code=None,
         driver_tags="volume,mix",
         created_on=d(8)),

    # --- Scenario C: contradictory evidence on retention/engagement ---
    dict(doc_id="DOC-020", source_type="crm_notes", title="Engagement notes — retention watch list",
         body="Customer engagement scores for the retention watch list declined this month; "
              "several customers reported dissatisfaction with response times.",
         branch_id="BR-01", rm_id=None, product_code=None,
         driver_tags="engagement,retention,decline",
         created_on=d(4)),
    dict(doc_id="DOC-021", source_type="market_notes", title="Competitive pricing shift — savings",
         body="A competitor bank raised savings account interest rates by 25 bps, which may "
              "explain customer attrition independent of engagement quality.",
         branch_id="BR-01", rm_id=None, product_code=None,
         driver_tags="pricing,engagement,retention,competitive",
         created_on=d(6)),
    dict(doc_id="DOC-022", source_type="customer_surveys", title="Quarterly satisfaction survey",
         body="Overall satisfaction scores were stable and unaffected this quarter across "
              "surveyed retention watch list customers.",
         branch_id="BR-01", rm_id=None, product_code=None,
         driver_tags="engagement,retention,satisfaction",
         created_on=d(15)),

    # --- Scenario D: sparse history / new product ---
    dict(doc_id="DOC-030", source_type="campaign_reports", title="Platinum Edge launch report",
         body="Platinum Edge card launched three weeks ago; insufficient trailing history exists "
              "for seasonal trend inference. Early peer-product benchmark suggests normal uptake.",
         branch_id="BR-01", rm_id=None, product_code="platinum_edge",
         driver_tags="platinum edge,sparse history,launch,new product",
         created_on=d(2)),

    # --- Neutral / filler documents across branches ---
    dict(doc_id="DOC-040", source_type="crm_notes", title="BR-02 monthly notes",
         body="No material issues reported for BR-02 relationship managers this month.",
         branch_id="BR-02", rm_id=None, product_code=None,
         driver_tags="general,br-02",
         created_on=d(12)),
    dict(doc_id="DOC-041", source_type="customer_surveys", title="Income disclosure audit note",
         body="Internal audit of income-band disclosures completed; sensitive customer income "
              "data restricted to admin-level access as per policy.",
         branch_id=None, rm_id=None, product_code=None,
         driver_tags="income,sensitive,audit",
         created_on=d(25)),
]

# mark the income-disclosure doc as sensitive
for doc in DOCS:
    doc["access_level"] = "sensitive" if doc["doc_id"] == "DOC-041" else "standard"
    doc.setdefault("customer_id", None)


def generate(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM documents")
    for doc in DOCS:
        cur.execute(
            "INSERT INTO documents (doc_id, source_type, title, body, branch_id, rm_id, "
            "customer_id, product_code, driver_tags, created_on, access_level) "
            "VALUES (:doc_id, :source_type, :title, :body, :branch_id, :rm_id, :customer_id, "
            ":product_code, :driver_tags, :created_on, :access_level)",
            doc,
        )
    conn.commit()
    conn.close()
    print(f"Generated {len(DOCS)} evidence documents.")


if __name__ == "__main__":
    generate()
