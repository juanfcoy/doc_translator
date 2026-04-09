"""Shared pytest fixtures."""

import pytest

import db as db_module
from app import app as flask_app


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    """Redirect db.DB_PATH to a fresh temporary database for each test."""
    db_file = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_file)
    db_module.init_db()
    return db_file


@pytest.fixture()
def client():
    """Flask test client with TESTING mode enabled."""
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as test_client:
        yield test_client
