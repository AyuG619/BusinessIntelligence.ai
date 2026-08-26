"""Stores 'was this insight useful' feedback. The learning-loop demo."""
import sqlite3
import pathlib
import datetime as dt

ROOT = pathlib.Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "db" / "banking.db"


def record_feedback(insight_ref: str, user_id: str, useful: bool, reason: str = "", db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO feedback (insight_ref, user_id, useful, reason, created_on) "
            "VALUES (?, ?, ?, ?, ?)",
            (insight_ref, user_id, int(useful), reason, dt.datetime.now(dt.timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def feedback_summary(insight_ref: str = None, db_path=DB_PATH) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        if insight_ref:
            rows = conn.execute(
                "SELECT useful, COUNT(*) FROM feedback WHERE insight_ref = ? GROUP BY useful",
                (insight_ref,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT useful, COUNT(*) FROM feedback GROUP BY useful"
            ).fetchall()
        summary = {"useful": 0, "not_useful": 0}
        for useful, count in rows:
            summary["useful" if useful else "not_useful"] = count
        return summary
    finally:
        conn.close()


def recent_feedback(limit: int = 10, db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT insight_ref, user_id, useful, reason, created_on FROM feedback "
            "ORDER BY feedback_id DESC LIMIT ?", (limit,)
        ).fetchall()
        cols = ["insight_ref", "user_id", "useful", "reason", "created_on"]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()
