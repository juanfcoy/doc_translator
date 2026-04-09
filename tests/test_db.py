"""Unit tests for the db module (SQLite persistence layer)."""

import sqlite3

import db as db_module


# ── init_db ───────────────────────────────────────────────────────────────────

def test_init_db_creates_tables(temp_db):
    conn = sqlite3.connect(temp_db)
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()
    assert "documents" in tables
    assert "feedback" in tables


def test_init_db_is_idempotent(temp_db):
    """Calling init_db() a second time must not raise or lose data."""
    db_module.register_document("existing.pdf")
    db_module.init_db()  # second call
    docs = db_module.get_all_documents()
    assert any(d["doc_name"] == "existing.pdf" for d in docs)


# ── register_document ─────────────────────────────────────────────────────────

def test_register_document(temp_db):
    db_module.register_document("report.pdf")
    docs = db_module.get_all_documents()
    assert len(docs) == 1
    assert docs[0]["doc_name"] == "report.pdf"
    assert docs[0]["status"] == "pending"


def test_register_document_duplicate_is_ignored(temp_db):
    db_module.register_document("report.pdf")
    db_module.register_document("report.pdf")  # second call — should not raise
    docs = db_module.get_all_documents()
    assert len(docs) == 1


# ── add_feedback ──────────────────────────────────────────────────────────────

def test_add_feedback_returns_id(temp_db):
    db_module.register_document("report.pdf")
    new_id = db_module.add_feedback("report.pdf", "some text", "wrong word")
    assert isinstance(new_id, int)
    assert new_id > 0


def test_add_feedback_section_truncated_at_500_chars(temp_db):
    db_module.register_document("report.pdf")
    long_section = "x" * 600
    db_module.add_feedback("report.pdf", long_section, "note")
    rows = db_module.get_feedback("report.pdf")
    assert len(rows[0]["section"]) == 500


def test_add_feedback_note_stored_in_full(temp_db):
    db_module.register_document("report.pdf")
    db_module.add_feedback("report.pdf", "section text", "detailed reviewer note")
    rows = db_module.get_feedback("report.pdf")
    assert rows[0]["note"] == "detailed reviewer note"


# ── get_feedback ──────────────────────────────────────────────────────────────

def test_get_feedback_empty(temp_db):
    db_module.register_document("report.pdf")
    assert db_module.get_feedback("report.pdf") == []


def test_get_feedback_returns_all_rows_ordered(temp_db):
    db_module.register_document("report.pdf")
    db_module.add_feedback("report.pdf", "first", "note A")
    db_module.add_feedback("report.pdf", "second", "note B")
    rows = db_module.get_feedback("report.pdf")
    assert len(rows) == 2
    assert rows[0]["section"] == "first"
    assert rows[1]["section"] == "second"


def test_get_feedback_returns_correct_keys(temp_db):
    db_module.register_document("report.pdf")
    db_module.add_feedback("report.pdf", "text", "note")
    row = db_module.get_feedback("report.pdf")[0]
    assert {"id", "section", "note", "created_at"} == set(row.keys())


# ── get_all_documents ─────────────────────────────────────────────────────────

def test_get_all_documents_empty(temp_db):
    assert db_module.get_all_documents() == []


def test_get_all_documents_feedback_count(temp_db):
    db_module.register_document("report.pdf")
    db_module.add_feedback("report.pdf", "s1", "n1")
    db_module.add_feedback("report.pdf", "s2", "n2")
    docs = db_module.get_all_documents()
    assert docs[0]["feedback_count"] == 2


def test_get_all_documents_zero_feedback_count(temp_db):
    db_module.register_document("no-feedback.pdf")
    docs = db_module.get_all_documents()
    assert docs[0]["feedback_count"] == 0


def test_get_all_documents_returns_all_docs(temp_db):
    db_module.register_document("first.pdf")
    db_module.register_document("second.pdf")
    docs = db_module.get_all_documents()
    doc_names = {d["doc_name"] for d in docs}
    assert doc_names == {"first.pdf", "second.pdf"}


# ── mark_reviewed ─────────────────────────────────────────────────────────────

def test_mark_reviewed_updates_status(temp_db):
    db_module.register_document("report.pdf")
    assert db_module.get_all_documents()[0]["status"] == "pending"
    db_module.mark_reviewed("report.pdf")
    assert db_module.get_all_documents()[0]["status"] == "reviewed"


def test_mark_reviewed_unknown_doc_does_not_raise(temp_db):
    """UPDATE on a non-existent row must silently do nothing."""
    db_module.mark_reviewed("ghost.pdf")  # should not raise
