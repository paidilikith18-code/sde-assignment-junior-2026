import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "dispatcher.db"


def get_connection():
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=30000")
    return connection


def initialize_database():
    with get_connection() as connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS leads (
                campaign_id TEXT NOT NULL,
                lead_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                phone TEXT NOT NULL,
                customer_name TEXT,
                state TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                next_eligible_at TEXT,
                last_status TEXT,
                last_disposition TEXT,
                PRIMARY KEY (campaign_id, lead_id)
            );

            CREATE TABLE IF NOT EXISTS calls (
                request_id TEXT PRIMARY KEY,
                campaign_id TEXT NOT NULL,
                lead_id TEXT NOT NULL,
                phone TEXT NOT NULL,
                call_sid TEXT UNIQUE,
                state TEXT NOT NULL DEFAULT 'prepared',
                attempt_counted INTEGER NOT NULL DEFAULT 0,
                started_at TEXT,
                ended_at TEXT,
                status TEXT,
                disposition TEXT,
                FOREIGN KEY (campaign_id, lead_id)
                    REFERENCES leads(campaign_id, lead_id)
            );

            CREATE TABLE IF NOT EXISTS dnd_phones (
                phone TEXT PRIMARY KEY
            );
        """)

        # Support databases created before attempt_counted existed.
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(calls)")
        }

        if "attempt_counted" not in columns:
            connection.execute(
                """
                ALTER TABLE calls
                ADD COLUMN attempt_counted INTEGER NOT NULL DEFAULT 0
                """
            )