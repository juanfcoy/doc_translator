"""
SQLite persistence layer for the Healthcare Translation QA service.

All public functions are safe to call concurrently from the translator
watcher process and the Flask web process because the database is opened
in WAL mode (set in init_db).
"""

import logging
import sqlite3
import os
from typing import Any

DB_PATH = os.path.join(os.path.dirname(__file__), "translation.db")

log = logging.getLogger(__name__)


def _connect() -> sqlite3.Connection:
    """Open and return a new SQLite connection with row-factory and FK support."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create tables and indexes if they do not already exist. Safe to call repeatedly."""
    conn = _connect()
    try:
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
        log.debug("Database schema initialised at %s", DB_PATH)
    finally:
        conn.close()


def register_document(doc_name: str) -> None:
    """Insert a document record. Silently skips if doc_name already exists."""
    conn = _connect()
    try:
        with conn:
            conn.execute(
                "INSERT OR IGNORE INTO documents (doc_name) VALUES (?)",
                (doc_name,),
            )
    finally:
        conn.close()


def add_feedback(doc_name: str, section: str, note: str) -> int:
    """Insert a feedback row and return its new primary-key ID."""
    conn = _connect()
    try:
        with conn:
            cursor = conn.execute(
                "INSERT INTO feedback (doc_name, section, note) VALUES (?, ?, ?)",
                (doc_name, section[:500], note),
            )
            return cursor.lastrowid  # type: ignore[return-value]
    finally:
        conn.close()


def get_feedback(doc_name: str) -> list[dict[str, Any]]:
    """Return all feedback rows for a document, ordered by creation time."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, section, note, created_at FROM feedback"
            " WHERE doc_name = ? ORDER BY created_at ASC",
            (doc_name,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_all_documents() -> list[dict[str, Any]]:
    """Return all documents with an aggregated feedback count, newest first."""
    conn = _connect()
    try:
        rows = conn.execute("""
            SELECT d.doc_name, d.translated_at, d.status, COUNT(f.id) AS feedback_count
            FROM documents d
            LEFT JOIN feedback f ON d.doc_name = f.doc_name
            GROUP BY d.doc_name
            ORDER BY d.translated_at DESC
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_reviewed(doc_name: str) -> None:
    """Set a document's status to 'reviewed'."""
    conn = _connect()
    try:
        with conn:
            conn.execute(
                "UPDATE documents SET status = 'reviewed' WHERE doc_name = ?",
                (doc_name,),
            )
    finally:
        conn.close()
