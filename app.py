"""
Healthcare Translation QA Web Interface
Run: python3 app.py
"""

import logging
import os

from flask import Flask, jsonify, render_template, request, send_from_directory
from flask import abort as flask_abort

import db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(BASE_DIR, "translations", "input")
OUTPUT_DIR = os.path.join(BASE_DIR, "translations", "output")

NOTE_MAX_LEN = 5_000

log = logging.getLogger(__name__)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024  # 1 MB request cap


# ── Error handlers ────────────────────────────────────────────────────────────

@app.errorhandler(400)
def bad_request(exc):
    return jsonify({"error": "Bad request"}), 400


@app.errorhandler(404)
def not_found(exc):
    if request.path.startswith("/pdf/") or request.path.startswith("/feedback/"):
        return jsonify({"error": "Not found"}), 404
    return render_template("dashboard.html", documents=[], error="Page not found"), 404


@app.errorhandler(500)
def internal_error(exc):
    log.exception("Unhandled exception on %s %s", request.method, request.path)
    return jsonify({"error": "Internal server error"}), 500


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    try:
        documents = db.get_all_documents()
    except Exception:
        log.exception("Failed to load documents for dashboard")
        documents = []
    return render_template("dashboard.html", documents=documents)


@app.route("/review/<path:doc_name>")
def review(doc_name: str):
    doc_name = os.path.basename(doc_name)
    try:
        all_docs = db.get_all_documents()
        doc_names = {d["doc_name"] for d in all_docs}
    except Exception:
        log.exception("DB error while loading review for %s", doc_name)
        flask_abort(500)

    if doc_name not in doc_names:
        flask_abort(404)

    try:
        feedback = db.get_feedback(doc_name)
    except Exception:
        log.exception("DB error loading feedback for %s", doc_name)
        feedback = []

    return render_template("review.html", doc_name=doc_name, feedback=feedback)


@app.route("/pdf/<side>/<path:doc_name>")
def serve_pdf(side: str, doc_name: str):
    if side not in ("input", "output"):
        flask_abort(400)
    doc_name = os.path.basename(doc_name)
    directory = INPUT_DIR if side == "input" else OUTPUT_DIR
    return send_from_directory(directory, doc_name, mimetype="application/pdf")


@app.route("/feedback", methods=["POST"])
def add_feedback():
    data = request.get_json(force=True, silent=True) or {}
    doc_name = (data.get("doc_name") or "").strip()
    section = (data.get("section") or "").strip()
    note = (data.get("note") or "").strip()

    if not doc_name or not section or not note:
        return jsonify({"error": "doc_name, section, and note are required"}), 400

    if len(note) > NOTE_MAX_LEN:
        return jsonify({"error": f"note must be {NOTE_MAX_LEN} characters or fewer"}), 400

    try:
        new_id = db.add_feedback(doc_name, section, note)
        db.mark_reviewed(doc_name)
    except Exception:
        log.exception("DB error saving feedback for %s", doc_name)
        return jsonify({"error": "Failed to save feedback"}), 500

    log.info("Feedback saved: doc=%s id=%d", doc_name, new_id)
    return jsonify({"status": "ok", "id": new_id}), 201


@app.route("/feedback/<path:doc_name>")
def get_feedback(doc_name: str):
    doc_name = os.path.basename(doc_name)
    try:
        feedback = db.get_feedback(doc_name)
    except Exception:
        log.exception("DB error loading feedback for %s", doc_name)
        return jsonify({"error": "Failed to load feedback"}), 500
    return jsonify({"feedback": feedback})


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    db.init_db()
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug, port=5000)
