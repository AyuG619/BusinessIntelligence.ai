"""Create db/banking.db and load schema.sql. Idempotent: safe to re-run."""
import sqlite3
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
SCHEMA_PATH = ROOT / "schema.sql"
DB_PATH = ROOT / "banking.db"


def init_db(db_path: pathlib.Path = DB_PATH, schema_path: pathlib.Path = SCHEMA_PATH) -> None:
    conn = sqlite3.connect(db_path)
    try:
        with open(schema_path, "r") as f:
            conn.executescript(f.read())
        conn.commit()
        print(f"Initialized {db_path} from {schema_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    sys.exit(0)
