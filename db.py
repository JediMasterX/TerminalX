import sqlite3
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def init_db():
    conn = sqlite3.connect("app.db")
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        hashed_password TEXT NOT NULL,
        is_admin INTEGER NOT NULL DEFAULT 0
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS hosts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        host TEXT NOT NULL,
        username TEXT NOT NULL,
        password TEXT NOT NULL,
        folder TEXT NOT NULL DEFAULT '',
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)
    # Enforce case-insensitive uniqueness for usernames where possible
    try:
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS users_username_nocase ON users(lower(trim(username)))"
        )
    except Exception:
        # Ignore if SQLite version doesn't support expression indexes or data conflicts
        pass
    # Seed hard-coded admin if missing
    cursor.execute("SELECT id FROM users WHERE lower(trim(username)) = lower(trim(?))", ("admin",))
    if not cursor.fetchone():
        hashed = pwd_context.hash("adminpassword")
        cursor.execute(
            "INSERT INTO users (username, hashed_password, is_admin) VALUES (?, ?, ?)",
            ("admin", hashed, 1)
        )
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect("app.db")
    conn.row_factory = sqlite3.Row
    return conn
