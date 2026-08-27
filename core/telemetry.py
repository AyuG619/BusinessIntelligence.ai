"""Runtime telemetry: latency, model calls, tokens, estimated cost.

Used as a context manager around each pipeline stage, and directly by
llm/client.py for token/cost logging.
"""
import time
import sqlite3
import datetime as dt
import pathlib
from contextlib import contextmanager

ROOT = pathlib.Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "db" / "banking.db"


def log_event(stage: str, duration_ms: float, model: str = None,
              input_tokens: int = None, output_tokens: int = None,
              est_cost_usd: float = None, db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO telemetry_log "
            "(stage, duration_ms, model, input_tokens, output_tokens, est_cost_usd, created_on) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (stage, duration_ms, model, input_tokens, output_tokens, est_cost_usd,
             dt.datetime.now(dt.timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


@contextmanager
def timed_stage(stage: str, db_path=DB_PATH):
    """Usage: with timed_stage('detect'): ... """
    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        log_event(stage, duration_ms, db_path=db_path)


def recent_events(limit: int = 30, db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT stage, duration_ms, model, input_tokens, output_tokens, est_cost_usd, created_on "
            "FROM telemetry_log ORDER BY telemetry_id DESC LIMIT ?", (limit,)
        ).fetchall()
        cols = ["stage", "duration_ms", "model", "input_tokens", "output_tokens", "est_cost_usd", "created_on"]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


def summary(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT COUNT(*), AVG(duration_ms), SUM(COALESCE(input_tokens,0)), "
            "SUM(COALESCE(output_tokens,0)), SUM(COALESCE(est_cost_usd,0)) FROM telemetry_log"
        ).fetchone()
        model_calls = conn.execute(
            "SELECT COUNT(*) FROM telemetry_log WHERE model IS NOT NULL"
        ).fetchone()[0]
        return {
            "total_calls": row[0] or 0,
            "pipeline_events": row[0] or 0,
            "model_calls": model_calls or 0,
            "avg_duration_ms": round(row[1] or 0, 1),
            "total_input_tokens": row[2] or 0,
            "total_output_tokens": row[3] or 0,
            "total_est_cost_usd": round(row[4] or 0, 4),
        }
    finally:
        conn.close()
