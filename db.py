import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "translation.db")


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _connect()
    with conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_name      TEXT UNIQUE NOT NULL,
                translated_at DATETIME DEFAULT (datetime('now')),
                status        TEXT NOT NULL DEFAULT 'pending'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_name    TEXT     NOT NULL,
                section     TEXT     NOT NULL,
                note        TEXT     NOT NULL,
                created_at  DATETIME NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (doc_name) REFERENCES documents(doc_name)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_feedback_doc_name ON feedback(doc_name)
        """)
    conn.close()


def register_document(doc_name):
    conn = _connect()
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO documents (doc_name) VALUES (?)",
            (doc_name,)
        )
    conn.close()


def add_feedback(doc_name, section, note):
    conn = _connect()
    with conn:
        cursor = conn.execute(
            "INSERT INTO feedback (doc_name, section, note) VALUES (?, ?, ?)",
            (doc_name, section[:500], note)
        )
        new_id = cursor.lastrowid
    conn.close()
    return new_id


def get_feedback(doc_name):
    conn = _connect()
    rows = conn.execute(
        "SELECT id, section, note, created_at FROM feedback WHERE doc_name = ? ORDER BY created_at ASC",
        (doc_name,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_documents():
    conn = _connect()
    rows = conn.execute("""
        SELECT d.doc_name, d.translated_at, d.status, COUNT(f.id) AS feedback_count
        FROM documents d
        LEFT JOIN feedback f ON d.doc_name = f.doc_name
        GROUP BY d.doc_name
        ORDER BY d.translated_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_reviewed(doc_name):
    conn = _connect()
    with conn:
        conn.execute(
            "UPDATE documents SET status = 'reviewed' WHERE doc_name = ?",
            (doc_name,)
        )
    conn.close()
