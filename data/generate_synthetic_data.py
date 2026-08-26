"""Generates baseline synthetic data: branches, RMs, customers, product
holdings, leads, and 6 months of revenue transactions with normal variance.

Run BEFORE seed_scenarios.py, which overlays the specific engineered
movements on top of this baseline.
"""
import sqlite3
import random
import datetime as dt
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "db" / "banking.db"

random.seed(42)

BRANCHES = [("BR-01", "Kanpur Central", "North"), ("BR-02", "Lucknow Hazratganj", "North")]
PRODUCTS_CROSS_SELL = ["credit_card", "salary_account", "personal_loan", "platinum_edge"]
PRODUCTS_CORE = ["savings_account", "current_account"]
SEGMENTS = ["mass", "affluent", "platinum"]

MONTHS = []
today = dt.date.today().replace(day=1)
for i in range(6, 0, -1):
    m = (today.replace(day=1) - dt.timedelta(days=1))
    for _ in range(i - 1):
        m = (m.replace(day=1) - dt.timedelta(days=1))
    MONTHS.append(m.strftime("%Y-%m"))
MONTHS = sorted(set(MONTHS))[-6:]
if len(MONTHS) < 6:
    # fallback: build explicitly from today backward
    MONTHS = []
    cursor = today
    for _ in range(6):
        MONTHS.append(cursor.strftime("%Y-%m"))
        cursor = (cursor.replace(day=1) - dt.timedelta(days=1)).replace(day=1)
    MONTHS = sorted(MONTHS)

CURRENT_MONTH = MONTHS[-1]


def month_to_date(month: str, day: int = 15) -> str:
    return f"{month}-{day:02d}"


def generate(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("DELETE FROM revenue_transactions")
    cur.execute("DELETE FROM leads")
    cur.execute("DELETE FROM product_holdings")
    cur.execute("DELETE FROM customers")
    cur.execute("DELETE FROM relationship_managers")
    cur.execute("DELETE FROM branches")
    cur.execute("DELETE FROM kpi_snapshots")

    for b in BRANCHES:
        cur.execute("INSERT INTO branches VALUES (?, ?, ?)", b)

    rm_id_counter = 101
    rms = []
    for branch_id, _, _ in BRANCHES:
        for _ in range(4):
            rm_id = f"RM-{rm_id_counter}"
            rm_name = f"RM {rm_id_counter}"
            cur.execute("INSERT INTO relationship_managers VALUES (?, ?, ?)",
                        (rm_id, rm_name, branch_id))
            rms.append((rm_id, branch_id))
            rm_id_counter += 1

    customers = []
    cust_id_counter = 1001
    for rm_id, branch_id in rms:
        for _ in range(15):
            cust_id = f"CUST-{cust_id_counter}"
            segment = random.choices(SEGMENTS, weights=[0.5, 0.35, 0.15])[0]
            status = random.choices(["active", "churned", "dormant"], weights=[0.82, 0.1, 0.08])[0]
            onboarded = month_to_date(random.choice(MONTHS), random.randint(1, 27))
            income_band = random.choice(["low", "mid", "high"])
            cur.execute(
                "INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (cust_id, f"Customer {cust_id_counter}", rm_id, branch_id, segment, status, onboarded, income_band),
            )
            customers.append((cust_id, rm_id, branch_id, segment))
            cust_id_counter += 1

    # product holdings: give some customers existing products so cross-sell gaps are meaningful
    for cust_id, rm_id, branch_id, segment in customers:
        n_products = random.choices([0, 1, 2], weights=[0.3, 0.5, 0.2])[0]
        owned = random.sample(PRODUCTS_CROSS_SELL + PRODUCTS_CORE, k=n_products) if n_products else []
        for p in owned:
            cur.execute(
                "INSERT INTO product_holdings (customer_id, product_code, opened_on, closed_on) VALUES (?, ?, ?, ?)",
                (cust_id, p, month_to_date(random.choice(MONTHS)), None),
            )

    # leads: mostly baseline, seed_scenarios.py will layer engineered ones on top
    lead_id_counter = 1
    for cust_id, rm_id, branch_id, segment in customers:
        if random.random() < 0.4:
            product_code = random.choice(PRODUCTS_CROSS_SELL)
            status = random.choices(["open", "converted", "lost"], weights=[0.45, 0.4, 0.15])[0]
            created = month_to_date(random.choice(MONTHS), random.randint(1, 20))
            updated = created
            lead_id = f"LEAD-{lead_id_counter:05d}"
            cur.execute(
                "INSERT INTO leads VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (lead_id, cust_id, rm_id, branch_id, product_code, status, created, updated,
                 round(random.uniform(2000, 20000), 2)),
            )
            lead_id_counter += 1

    # revenue transactions: 6 months, normal variance, cross_sell + core + fee
    txn_id_counter = 1
    for month in MONTHS:
        for cust_id, rm_id, branch_id, segment in customers:
            n_txns = random.choices([0, 1, 2], weights=[0.55, 0.35, 0.1])[0]
            for _ in range(n_txns):
                category = random.choices(["cross_sell", "core", "fee"], weights=[0.4, 0.5, 0.1])[0]
                product_code = random.choice(PRODUCTS_CROSS_SELL) if category == "cross_sell" else \
                    random.choice(PRODUCTS_CORE) if category == "core" else "service_fee"
                base_price = {"credit_card": 1200, "salary_account": 300, "personal_loan": 2500,
                               "platinum_edge": 1800, "savings_account": 150, "current_account": 200,
                               "service_fee": 90}[product_code]
                units = random.randint(1, 3)
                unit_price = round(base_price * random.uniform(0.9, 1.1), 2)
                amount = round(unit_price * units, 2)
                txn_date = month_to_date(month, random.randint(1, 27))
                cur.execute(
                    "INSERT INTO revenue_transactions "
                    "(customer_id, branch_id, rm_id, product_code, product_category, txn_date, month, "
                    "amount, volume_units, unit_price) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (cust_id, branch_id, rm_id, product_code, category, txn_date, month,
                     amount, units, unit_price),
                )
                txn_id_counter += 1

    conn.commit()
    conn.close()
    print(f"Generated baseline data for months: {MONTHS} (current={CURRENT_MONTH})")
    print(f"Branches={len(BRANCHES)} RMs={len(rms)} Customers={len(customers)} Transactions~{txn_id_counter-1}")


if __name__ == "__main__":
    generate()
