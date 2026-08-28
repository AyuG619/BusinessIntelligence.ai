import pathlib
import sys
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.security import (  # noqa: E402
    check_customer_access, check_branch_access, AccessDenied, get_user,
)

DB_PATH = ROOT / "db" / "banking.db"


@pytest.mark.skipif(not DB_PATH.exists(), reason="db/banking.db not initialized — run setup scripts first")
def test_rm_cannot_access_other_rm_customer():
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT customer_id FROM customers WHERE rm_id = 'RM-108' LIMIT 1").fetchone()
    conn.close()
    if row is None:
        pytest.skip("No RM-108 customers seeded")
    other_customer = row[0]
    with pytest.raises(AccessDenied):
        check_customer_access("RM-103", other_customer)


@pytest.mark.skipif(not DB_PATH.exists(), reason="db/banking.db not initialized — run setup scripts first")
def test_rm_can_access_own_customer():
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT customer_id FROM customers WHERE rm_id = 'RM-103' LIMIT 1").fetchone()
    conn.close()
    if row is None:
        pytest.skip("No RM-103 customers seeded")
    own_customer = row[0]
    assert check_customer_access("RM-103", own_customer) is True


def test_unknown_user_raises():
    with pytest.raises(AccessDenied):
        get_user("NOT-A-REAL-USER")


@pytest.mark.skipif(not DB_PATH.exists(), reason="db/banking.db not initialized — run setup scripts first")
def test_unknown_sensitive_field_is_denied():
    with pytest.raises(AccessDenied):
        from core.security import check_sensitive_field_access
        check_sensitive_field_access("ADMIN-01", "ssn")


@pytest.mark.skipif(not DB_PATH.exists(), reason="db/banking.db not initialized — run setup scripts first")
def test_branch_head_cannot_access_other_branch():
    with pytest.raises(AccessDenied):
        check_branch_access("BH-01", "BR-02")
