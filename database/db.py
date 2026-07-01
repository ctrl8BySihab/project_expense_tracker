import sqlite3
from pathlib import Path

from werkzeug.security import generate_password_hash

DB_PATH = Path(__file__).parent / "expense_tracker.db"


def get_db():
    """Return a SQLite connection with Row factory and FK enforcement on."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create tables if they don't exist. Idempotent — safe on every startup."""
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL CHECK(amount > 0),
            category TEXT NOT NULL,
            description TEXT,
            expense_date DATE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    conn.commit()
    conn.close()


def seed_db():
    """Insert a demo user and sample expenses, if not already present."""
    conn = get_db()
    existing = conn.execute(
        "SELECT id FROM users WHERE email = ?", ("demo@spendly.dev",)
    ).fetchone()

    if existing is None:
        cur = conn.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
            ("demo_user", "demo@spendly.dev", generate_password_hash("demopassword123")),
        )
        user_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, description, expense_date) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (user_id, 450.00, "Food", "Lunch with friends", "2026-06-20"),
                (user_id, 1200.00, "Bills", "Electricity bill", "2026-06-25"),
                (user_id, 300.00, "Travel", None, "2026-06-28"),
            ],
        )
        conn.commit()

    conn.close()
