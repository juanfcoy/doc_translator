"""Unit tests for the Flask web interface (app.py)."""

from unittest.mock import patch

import pytest


# ── Dashboard ─────────────────────────────────────────────────────────────────

def test_dashboard_empty(client):
    with patch("db.get_all_documents", return_value=[]):
        response = client.get("/")
    assert response.status_code == 200
    assert b"No translated documents" in response.data


def test_dashboard_lists_documents(client):
    docs = [
        {
            "doc_name": "report.pdf",
            "translated_at": "2024-01-01 10:00:00",
            "status": "pending",
            "feedback_count": 0,
        }
    ]
    with patch("db.get_all_documents", return_value=docs):
        response = client.get("/")
    assert response.status_code == 200
    assert b"report.pdf" in response.data


def test_dashboard_db_error_returns_empty_list(client):
    with patch("db.get_all_documents", side_effect=Exception("DB down")):
        response = client.get("/")
    assert response.status_code == 200  # gracefully degrades


# ── Review page ───────────────────────────────────────────────────────────────

def test_review_not_found(client):
    with patch("db.get_all_documents", return_value=[]):
        response = client.get("/review/nonexistent.pdf")
    assert response.status_code == 404


def test_review_found(client):
    docs = [
        {
            "doc_name": "report.pdf",
            "translated_at": "2024-01-01",
            "status": "pending",
            "feedback_count": 0,
        }
    ]
    with patch("db.get_all_documents", return_value=docs), patch(
        "db.get_feedback", return_value=[]
    ):
        response = client.get("/review/report.pdf")
    assert response.status_code == 200
    assert b"report.pdf" in response.data


def test_review_path_traversal_blocked(client):
    """Path traversal in doc_name must not expose filesystem paths."""
    with patch("db.get_all_documents", return_value=[]):
        response = client.get("/review/../../etc/passwd")
    assert response.status_code == 404


# ── PDF serving ───────────────────────────────────────────────────────────────

def test_serve_pdf_invalid_side(client):
    response = client.get("/pdf/invalid/report.pdf")
    assert response.status_code == 400


def test_serve_pdf_input_not_found(client, tmp_path):
    with patch("app.INPUT_DIR", str(tmp_path)):
        response = client.get("/pdf/input/missing.pdf")
    assert response.status_code == 404


def test_serve_pdf_output_not_found(client, tmp_path):
    with patch("app.OUTPUT_DIR", str(tmp_path)):
        response = client.get("/pdf/output/missing.pdf")
    assert response.status_code == 404


def test_serve_pdf_input_success(client, tmp_path):
    pdf_file = tmp_path / "report.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 fake content")
    with patch("app.INPUT_DIR", str(tmp_path)):
        response = client.get("/pdf/input/report.pdf")
    assert response.status_code == 200
    assert response.content_type == "application/pdf"


# ── POST /feedback ────────────────────────────────────────────────────────────

def test_add_feedback_success(client):
    with patch("db.add_feedback", return_value=1) as mock_add, patch(
        "db.mark_reviewed"
    ) as mock_mark:
        response = client.post(
            "/feedback",
            json={
                "doc_name": "report.pdf",
                "section": "member deductible",
                "note": "Incorrect translation of deductible",
            },
        )
    assert response.status_code == 201
    data = response.get_json()
    assert data == {"status": "ok", "id": 1}
    mock_add.assert_called_once_with(
        "report.pdf", "member deductible", "Incorrect translation of deductible"
    )
    mock_mark.assert_called_once_with("report.pdf")


def test_add_feedback_missing_doc_name(client):
    response = client.post(
        "/feedback",
        json={"section": "text", "note": "note"},
    )
    assert response.status_code == 400


def test_add_feedback_missing_section(client):
    response = client.post(
        "/feedback",
        json={"doc_name": "report.pdf", "note": "note"},
    )
    assert response.status_code == 400


def test_add_feedback_missing_note(client):
    response = client.post(
        "/feedback",
        json={"doc_name": "report.pdf", "section": "text"},
    )
    assert response.status_code == 400


def test_add_feedback_empty_fields_rejected(client):
    response = client.post(
        "/feedback",
        json={"doc_name": "  ", "section": "  ", "note": "  "},
    )
    assert response.status_code == 400


def test_add_feedback_note_too_long(client):
    response = client.post(
        "/feedback",
        json={"doc_name": "report.pdf", "section": "text", "note": "x" * 5001},
    )
    assert response.status_code == 400
    assert b"5000" in response.data


def test_add_feedback_note_at_max_length(client):
    with patch("db.add_feedback", return_value=1), patch("db.mark_reviewed"):
        response = client.post(
            "/feedback",
            json={"doc_name": "report.pdf", "section": "text", "note": "x" * 5000},
        )
    assert response.status_code == 201


def test_add_feedback_db_error_returns_500(client):
    with patch("db.add_feedback", side_effect=Exception("disk full")):
        response = client.post(
            "/feedback",
            json={"doc_name": "report.pdf", "section": "text", "note": "note"},
        )
    assert response.status_code == 500


def test_add_feedback_no_body(client):
    response = client.post("/feedback", content_type="application/json", data="")
    assert response.status_code == 400


# ── GET /feedback/<doc_name> ──────────────────────────────────────────────────

def test_get_feedback_returns_json(client):
    expected = [
        {"id": 1, "section": "text", "note": "note", "created_at": "2024-01-01 10:00:00"}
    ]
    with patch("db.get_feedback", return_value=expected):
        response = client.get("/feedback/report.pdf")
    assert response.status_code == 200
    assert response.get_json() == {"feedback": expected}


def test_get_feedback_empty(client):
    with patch("db.get_feedback", return_value=[]):
        response = client.get("/feedback/report.pdf")
    assert response.status_code == 200
    assert response.get_json() == {"feedback": []}


def test_get_feedback_db_error_returns_500(client):
    with patch("db.get_feedback", side_effect=Exception("DB error")):
        response = client.get("/feedback/report.pdf")
    assert response.status_code == 500
