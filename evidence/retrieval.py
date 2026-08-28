"""Scoped, access-controlled evidence retrieval.

Deliberately NOT a vector database. For a demo with ~40 documents, keyword +
scope filtering on SQLite gives the same driver -> evidence -> citation
chain without the sentence-transformers/ChromaDB dependency.
"""
import sqlite3
import pathlib
from core.security import check_branch_access, AccessDenied
from core.telemetry import timed_stage

ROOT = pathlib.Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "db" / "banking.db"


def retrieve_evidence(driver_key: str, branch_id: str = None, product_code: str = None,
                       user_id: str = None, limit: int = 5, db_path=DB_PATH) -> list:
    """Returns a list of dict rows from `documents` matching the driver's
    keyword tags, scoped by branch/product, filtered by the user's access.
    """
    with timed_stage("evidence_retrieval"):
        if user_id and branch_id:
            try:
                check_branch_access(user_id, branch_id, db_path)
            except AccessDenied:
                return []

        conn = sqlite3.connect(db_path)
        try:
            keyword = driver_key.replace("lead_status_", "").replace("_", " ")
            tokens = [t for t in keyword.split() if t]
            token_clauses = " OR ".join(["driver_tags LIKE ?"] * len(tokens)) or "1=0"
            clauses = [f"({token_clauses})"]
            params = [f"%{t}%" for t in tokens]

            if branch_id:
                clauses.append("(branch_id = ? OR branch_id IS NULL)")
                params.append(branch_id)
            if product_code:
                clauses.append("(product_code = ? OR product_code IS NULL)")
                params.append(product_code)

            if user_id:
                # non-admin users never see access_level='sensitive' docs
                from core.security import get_user
                user = get_user(user_id)
                if user["role"] != "admin":
                    clauses.append("access_level != 'sensitive'")
                if user["role"] == "relationship_manager":
                    clauses.append(
                        "((customer_id IS NOT NULL AND EXISTS ("
                        "SELECT 1 FROM customers c WHERE c.customer_id = documents.customer_id "
                        "AND c.rm_id = ?)) OR (customer_id IS NULL AND "
                        "(rm_id = ? OR (rm_id IS NULL AND "
                        "(branch_id = ? OR branch_id IS NULL)))))"
                    )
                    params.extend([user_id, user_id, user["branch_id"]])
                elif user["role"] == "branch_head":
                    clauses.append(
                        "((customer_id IS NOT NULL AND EXISTS ("
                        "SELECT 1 FROM customers c WHERE c.customer_id = documents.customer_id "
                        "AND c.branch_id = ?)) OR (customer_id IS NULL AND "
                        "(branch_id = ? OR branch_id IS NULL)))"
                    )
                    params.extend([user["branch_id"], user["branch_id"]])
            else:
                return []

            q = f"""
                SELECT doc_id, source_type, title, body, driver_tags, created_on, access_level
                FROM documents
                WHERE {" AND ".join(clauses)}
                ORDER BY created_on DESC
                LIMIT ?
            """
            params.append(limit)
            rows = conn.execute(q, params).fetchall()
            cols = ["doc_id", "source_type", "title", "body", "driver_tags", "created_on", "access_level"]
            return [dict(zip(cols, r)) for r in rows]
        finally:
            conn.close()


def retrieve_for_drivers(drivers: list, branch_id: str = None, product_code: str = None,
                          user_id: str = None, db_path=DB_PATH) -> dict:
    """Convenience: retrieve evidence for a whole list of DriverContribution
    objects at once. Returns {driver_key: [doc, ...]}."""
    out = {}
    for d in drivers:
        out[d.driver_key] = retrieve_evidence(
            d.driver_key, branch_id=branch_id, product_code=product_code,
            user_id=user_id, db_path=db_path
        )
    return out
