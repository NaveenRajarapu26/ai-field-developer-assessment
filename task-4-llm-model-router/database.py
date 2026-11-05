
import sqlite3
from contextlib import closing
from pathlib import Path


# SQLite database stored on disk
DB_PATH = Path(__file__).parent / "rate_limits.db"


def get_connection():
    """Create a connection to SQLite."""

    connection = sqlite3.connect(
        DB_PATH,
        timeout=10
    )

    connection.row_factory = sqlite3.Row

    return connection


def initialize_database():
    """Create the token usage table if needed."""

    with closing(get_connection()) as connection:

        connection.execute("""
            CREATE TABLE IF NOT EXISTS token_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_key TEXT NOT NULL,
                tokens INTEGER NOT NULL CHECK(tokens > 0),
                timestamp REAL NOT NULL
            )
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_tenant_timestamp
            ON token_usage (tenant_key, timestamp)
        """)

        connection.commit()


if __name__ == "__main__":
    initialize_database()
    print("SQLite database initialized successfully!")
