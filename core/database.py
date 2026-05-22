import sqlite3
import os
from datetime import datetime

DATABASE_DIR = "./data"
DATABASE_PATH = os.path.join(DATABASE_DIR, "Hevva.db")

def init_db():
    os.makedirs(DATABASE_DIR, exist_ok=True)
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processed_activities (
                object_id INTEGER PRIMARY KEY,
                processed_at TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS strava_tokens (
                id INTEGER PRIMARY KEY DEFAULT 1,
                access_token TEXT NOT NULL,
                refresh_token TEXT NOT NULL,
                expires_at INTEGER NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.commit()


def set_config(key: str, value: str):
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO app_config (key, value) VALUES (?, ?)", (key, value)
        )
        conn.commit()


def get_config(key: str) -> str | None:
    with sqlite3.connect(DATABASE_PATH) as conn:
        row = conn.execute("SELECT value FROM app_config WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

def record_processed_activity(object_id: int):
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO processed_activities (object_id, processed_at) VALUES (?, ?)",
                       (object_id, datetime.utcnow().isoformat()))
        conn.commit()

def is_activity_processed(object_id: int) -> bool:
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM processed_activities WHERE object_id = ?", (object_id,))
        return cursor.fetchone() is not None

def update_strava_tokens(access_token: str, refresh_token: str, expires_at: int):
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO strava_tokens (id, access_token, refresh_token, expires_at)
            VALUES (1, ?, ?, ?)
        """, (access_token, refresh_token, expires_at))
        conn.commit()

def get_strava_tokens():
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT access_token, refresh_token, expires_at FROM strava_tokens WHERE id = 1")
        return cursor.fetchone()


init_db()
