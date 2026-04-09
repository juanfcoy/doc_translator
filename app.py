"""
Healthcare Translation QA Web Interface
Run: python3 app.py
"""

import os
from flask import Flask, render_template, request, jsonify, send_from_directory, abort

import db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(BASE_DIR, "translations", "input")
OUTPUT_DIR = os.path.join(BASE_DIR, "translations", "output")

app = Flask(__name__)


@app.route("/")
def dashboard():
    documents = db.get_all_documents()
    return render_template("dashboard.html", documents=documents)


@app.route("/review/<path:doc_name>")
def review(doc_name):
    doc_name = os.path.basename(doc_name)
    all_docs = db.get_all_documents()
    doc_names = {d["doc_name"] for d in all_docs}
    if doc_name not in doc_names:
        abort(404)
    feedback = db.get_feedback(doc_name)
    return render_template("review.html", doc_name=doc_name, feedback=feedback)


@app.route("/pdf/<side>/<path:doc_name>")
def serve_pdf(side, doc_name):
    if side not in ("input", "output"):
        abort(400)
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

    new_id = db.add_feedback(doc_name, section, note)
    db.mark_reviewed(doc_name)
    return jsonify({"status": "ok", "id": new_id}), 201


@app.route("/feedback/<path:doc_name>")
def get_feedback(doc_name):
    doc_name = os.path.basename(doc_name)
    feedback = db.get_feedback(doc_name)
    return jsonify({"feedback": feedback})


if __name__ == "__main__":
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    db.init_db()
    app.run(debug=True, port=5000)
