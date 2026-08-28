"""Role-based access control + audit logging.

Deterministic. The LLM never makes access decisions — this module does,
and every check is written to audit_log regardless of outcome.
"""
import sqlite3
import datetime as dt
import pathlib
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
POLICY_PATH = ROOT / "config" / "security_policies.yaml"
DB_PATH = ROOT / "db" / "banking.db"

with open(POLICY_PATH) as f:
    _POLICY = yaml.safe_load(f)

ROLES = _POLICY["roles"]
DEMO_USERS = {u["user_id"]: u for u in _POLICY["demo_users"]}
SENSITIVE_FIELDS = {"income_band"}


class AccessDenied(Exception):
    pass


def _log(conn, user_id: str, action: str, resource: str, result: str, reason: str = ""):
    conn.execute(
        "INSERT INTO audit_log (user_id, action, resource, result, reason, created_on) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, action, resource, result, reason, dt.datetime.now(dt.timezone.utc).isoformat()),
    )
    conn.commit()


def get_user(user_id: str) -> dict:
    if user_id not in DEMO_USERS:
        raise AccessDenied(f"Unknown user_id: {user_id}")
    return DEMO_USERS[user_id]


def check_customer_access(user_id: str, target_customer_id: str, db_path=DB_PATH) -> bool:
    """Returns True/raises AccessDenied. Always audits."""
    user = get_user(user_id)
    role = ROLES[user["role"]]
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT rm_id, branch_id FROM customers WHERE customer_id = ?",
            (target_customer_id,),
        ).fetchone()
        if row is None:
            _log(conn, user_id, "view_customer", target_customer_id, "DENIED", "customer not found")
            raise AccessDenied("Customer not found")
        owning_rm, owning_branch = row

        allowed, reason = False, ""
        if role["scope"] == "global":
            allowed, reason = True, "admin global scope"
        elif role["scope"] == "own_branch":
            allowed = owning_branch == user["branch_id"]
            reason = "branch match" if allowed else "customer outside branch head's branch"
        elif role["scope"] == "own_customers":
            allowed = owning_rm == user_id
            reason = "RM owns customer" if allowed else f"customer belongs to {owning_rm}, not {user_id}"

        _log(conn, user_id, "view_customer", target_customer_id, "ALLOWED" if allowed else "DENIED", reason)
        if not allowed:
            raise AccessDenied(reason)
        return True
    finally:
        conn.close()


def check_branch_access(user_id: str, target_branch_id: str, db_path=DB_PATH) -> bool:
    user = get_user(user_id)
    role = ROLES[user["role"]]
    conn = sqlite3.connect(db_path)
    try:
        allowed, reason = False, ""
        if role["scope"] == "global":
            allowed, reason = True, "admin global scope"
        elif role["scope"] in ("own_branch", "own_customers"):
            allowed = user["branch_id"] == target_branch_id
            reason = "branch match" if allowed else "user not attached to this branch"
        _log(conn, user_id, "view_branch_aggregate", target_branch_id,
             "ALLOWED" if allowed else "DENIED", reason)
        if not allowed:
            raise AccessDenied(reason)
        return True
    finally:
        conn.close()


def check_sensitive_field_access(user_id: str, field_name: str, db_path=DB_PATH) -> bool:
    user = get_user(user_id)
    role = ROLES[user["role"]]
    conn = sqlite3.connect(db_path)
    try:
        known_field = field_name in SENSITIVE_FIELDS
        allowed = known_field and "sensitive_income_data" not in role.get("denied", [])
        reason = "" if known_field else "field is not registered as sensitive"
        if not allowed and known_field:
            reason = "role does not include sensitive_income_data"
        _log(conn, user_id, f"view_field:{field_name}", field_name,
             "ALLOWED" if allowed else "DENIED",
             reason)
    finally:
        conn.close()
    if not allowed:
        raise AccessDenied("Sensitive field access denied or field is not registered")
    return True


def recent_audit_events(limit: int = 20, db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT user_id, action, resource, result, reason, created_on "
            "FROM audit_log ORDER BY audit_id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [
            dict(zip(["user_id", "action", "resource", "result", "reason", "created_on"], r))
            for r in rows
        ]
    finally:
        conn.close()
