"""
Healthcare PDF Translation Pipeline
Watches /translations/input for new PDFs, translates English -> Spanish via
the Claude API, and writes reconstructed PDFs to /translations/output.

Usage:
    export ANTHROPIC_API_KEY=sk-...
    python3 translator.py
"""

import os
import sys
import time
import logging

import pdfplumber
import anthropic
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

import db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(BASE_DIR, "translations", "input")
OUTPUT_DIR = os.path.join(BASE_DIR, "translations", "output")

CHUNK_CHAR_LIMIT = 150_000  # split docs larger than this

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a precise healthcare document translator. "
    "Translate the following English healthcare document to Spanish. "
    "Preserve all medical terminology, member names, dates, policy numbers, "
    "and formatting exactly. Do not add, remove, or interpret any information. "
    "Translate only."
)


def wait_for_stable(path: str, interval: float = 0.5, retries: int = 12) -> bool:
    """Return True once the file size stops changing (write complete)."""
    prev_size = -1
    for _ in range(retries):
        try:
            size = os.path.getsize(path)
        except OSError:
            time.sleep(interval)
            continue
        if size == prev_size and size > 0:
            return True
        prev_size = size
        time.sleep(interval)
    return False


def extract_text(pdf_path: str) -> str:
    """Extract plain text from all pages of a PDF."""
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return "\n\n".join(pages)


def translate_text(client: anthropic.Anthropic, text: str) -> str:
    """Send text to Claude for translation, chunking if necessary."""
    if len(text) <= CHUNK_CHAR_LIMIT:
        return _call_claude(client, text)

    log.warning("Document exceeds %d chars — translating in chunks.", CHUNK_CHAR_LIMIT)
    chunks = [text[i:i + CHUNK_CHAR_LIMIT] for i in range(0, len(text), CHUNK_CHAR_LIMIT)]
    translated_chunks = [_call_claude(client, chunk) for chunk in chunks]
    return "\n\n".join(translated_chunks)


def _call_claude(client: anthropic.Anthropic, text: str) -> str:
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": text}],
    )
    return message.content[0].text


def build_pdf(translated_text: str, output_path: str) -> None:
    """Reconstruct a formatted PDF from translated plain text."""
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=inch,
        rightMargin=inch,
        topMargin=inch,
        bottomMargin=inch,
    )
    styles = getSampleStyleSheet()
    body_style = ParagraphStyle(
        "HealthcareBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        spaceAfter=4,
    )
    story = []
    for line in translated_text.splitlines():
        stripped = line.strip()
        if stripped:
            story.append(Paragraph(stripped, body_style))
        else:
            story.append(Spacer(1, 6))
    if not story:
        story.append(Paragraph("(no content)", body_style))
    doc.build(story)


def translate_document(pdf_path: str) -> None:
    """Full pipeline: extract -> translate -> rebuild PDF -> register."""
    doc_name = os.path.basename(pdf_path)
    output_path = os.path.join(OUTPUT_DIR, doc_name)

    if os.path.exists(output_path):
        log.info("Already translated, skipping: %s", doc_name)
        return

    log.info("Waiting for file to be fully written: %s", doc_name)
    if not wait_for_stable(pdf_path):
        log.warning("File did not stabilise in time, skipping: %s", doc_name)
        return

    log.info("Extracting text from: %s", doc_name)
    try:
        text = extract_text(pdf_path)
    except Exception as exc:
        log.error("Text extraction failed for %s: %s", doc_name, exc)
        return

    if not text.strip():
        log.warning("No extractable text in %s — skipping.", doc_name)
        return

    log.info("Translating %d characters via Claude API…", len(text))
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    try:
        translated = translate_text(client, text)
    except Exception as exc:
        log.error("Translation failed for %s: %s", doc_name, exc)
        return

    log.info("Building translated PDF: %s", output_path)
    try:
        build_pdf(translated, output_path)
    except Exception as exc:
        log.error("PDF build failed for %s: %s", doc_name, exc)
        return

    db.register_document(doc_name)
    log.info("Done: %s -> %s", doc_name, output_path)


class PDFHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and event.src_path.lower().endswith(".pdf"):
            translate_document(event.src_path)

    def on_moved(self, event):
        # Handle files moved/dropped into the watch folder
        if not event.is_directory and event.dest_path.lower().endswith(".pdf"):
            translate_document(event.dest_path)


def main():
    # Validate API key at startup — fail fast with a clear message
    if "ANTHROPIC_API_KEY" not in os.environ:
        sys.exit("ERROR: ANTHROPIC_API_KEY environment variable is not set.")

    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    db.init_db()

    # Process any PDFs already in the input folder at startup
    for fname in os.listdir(INPUT_DIR):
        if fname.lower().endswith(".pdf"):
            translate_document(os.path.join(INPUT_DIR, fname))

    observer = Observer()
    observer.schedule(PDFHandler(), path=INPUT_DIR, recursive=False)
    observer.start()
    log.info("Watching %s for new PDF files. Press Ctrl+C to stop.", INPUT_DIR)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()
        log.info("Translator stopped.")


if __name__ == "__main__":
    main()
