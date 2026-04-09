"""Unit tests for the translation pipeline (translator.py)."""

import os
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

import translator


# ── wait_for_stable ───────────────────────────────────────────────────────────

def test_wait_for_stable_returns_true_when_size_stabilises(tmp_path):
    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"content")
    # File already exists and size is stable — should return True quickly
    result = translator.wait_for_stable(str(pdf), interval=0.01, retries=5)
    assert result is True


def test_wait_for_stable_returns_false_on_missing_file(tmp_path):
    missing = str(tmp_path / "ghost.pdf")
    result = translator.wait_for_stable(missing, interval=0.01, retries=3)
    assert result is False


def test_wait_for_stable_returns_false_when_always_growing(tmp_path):
    pdf = tmp_path / "growing.pdf"
    pdf.write_bytes(b"x")

    sizes = iter([10, 20, 30, 40, 50])

    with patch("os.path.getsize", side_effect=sizes):
        result = translator.wait_for_stable(str(pdf), interval=0.01, retries=5)
    assert result is False


# ── extract_text ──────────────────────────────────────────────────────────────

def test_extract_text_single_page():
    mock_page = MagicMock()
    mock_page.extract_text.return_value = "Patient name: John Doe"

    mock_pdf = MagicMock()
    mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
    mock_pdf.__exit__ = MagicMock(return_value=False)
    mock_pdf.pages = [mock_page]

    with patch("translator.pdfplumber.open", return_value=mock_pdf):
        result = translator.extract_text("fake.pdf")

    assert result == "Patient name: John Doe"


def test_extract_text_multiple_pages_joined():
    pages = [MagicMock(), MagicMock()]
    pages[0].extract_text.return_value = "Page one content"
    pages[1].extract_text.return_value = "Page two content"

    mock_pdf = MagicMock()
    mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
    mock_pdf.__exit__ = MagicMock(return_value=False)
    mock_pdf.pages = pages

    with patch("translator.pdfplumber.open", return_value=mock_pdf):
        result = translator.extract_text("fake.pdf")

    assert result == "Page one content\n\nPage two content"


def test_extract_text_none_pages_skipped():
    pages = [MagicMock(), MagicMock()]
    pages[0].extract_text.return_value = None
    pages[1].extract_text.return_value = "Only page with text"

    mock_pdf = MagicMock()
    mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
    mock_pdf.__exit__ = MagicMock(return_value=False)
    mock_pdf.pages = pages

    with patch("translator.pdfplumber.open", return_value=mock_pdf):
        result = translator.extract_text("fake.pdf")

    assert result == "Only page with text"


# ── _call_claude ──────────────────────────────────────────────────────────────

def test_call_claude_returns_translated_text():
    mock_client = MagicMock()
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="Texto traducido al español")]
    mock_client.messages.create.return_value = mock_message

    result = translator._call_claude(mock_client, "Original English text")

    assert result == "Texto traducido al español"


def test_call_claude_uses_correct_model_and_prompt():
    mock_client = MagicMock()
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="translated")]
    mock_client.messages.create.return_value = mock_message

    translator._call_claude(mock_client, "some text")

    mock_client.messages.create.assert_called_once_with(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        system=translator.SYSTEM_PROMPT,
        messages=[{"role": "user", "content": "some text"}],
    )


# ── translate_text ────────────────────────────────────────────────────────────

def test_translate_text_short_doc_single_call():
    mock_client = MagicMock()
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="traducción")]
    mock_client.messages.create.return_value = mock_message

    text = "Short document"
    result = translator.translate_text(mock_client, text)

    assert result == "traducción"
    mock_client.messages.create.assert_called_once()


def test_translate_text_long_doc_split_into_chunks():
    mock_client = MagicMock()

    chunk_responses = ["parte uno", "parte dos", "parte tres"]

    def make_response(text):
        msg = MagicMock()
        msg.content = [MagicMock(text=text)]
        return msg

    mock_client.messages.create.side_effect = [
        make_response(t) for t in chunk_responses
    ]

    # Create text slightly larger than 3 * CHUNK_CHAR_LIMIT / 3 (i.e. needs 3 chunks)
    long_text = "A" * (translator.CHUNK_CHAR_LIMIT + 1)

    result = translator.translate_text(mock_client, long_text)

    assert mock_client.messages.create.call_count == 2  # 2 chunks for 150001 chars
    assert "parte uno" in result
    assert "parte dos" in result


# ── build_pdf ─────────────────────────────────────────────────────────────────

def test_build_pdf_creates_valid_pdf_file(tmp_path):
    output_path = str(tmp_path / "output.pdf")
    translator.build_pdf("Texto en español.\nSegunda línea con acentos: café.", output_path)

    assert os.path.exists(output_path)
    assert os.path.getsize(output_path) > 0
    with open(output_path, "rb") as f:
        assert f.read(4) == b"%PDF"


def test_build_pdf_handles_empty_text(tmp_path):
    output_path = str(tmp_path / "empty.pdf")
    translator.build_pdf("", output_path)
    assert os.path.exists(output_path)


def test_build_pdf_handles_special_characters(tmp_path):
    output_path = str(tmp_path / "special.pdf")
    spanish_text = "Señor García, su deducible es de $500. ¿Tiene alguna pregunta?"
    translator.build_pdf(spanish_text, output_path)
    assert os.path.exists(output_path)
    assert os.path.getsize(output_path) > 0


# ── translate_document ────────────────────────────────────────────────────────

def test_translate_document_skips_existing_output(tmp_path, monkeypatch):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    monkeypatch.setattr(translator, "OUTPUT_DIR", str(output_dir))

    # Pre-create the output file to simulate prior translation
    (output_dir / "report.pdf").write_bytes(b"already translated")

    input_pdf = tmp_path / "report.pdf"
    input_pdf.write_bytes(b"fake input")

    with patch.object(translator, "wait_for_stable") as mock_wait:
        translator.translate_document(str(input_pdf))

    mock_wait.assert_not_called()


def test_translate_document_skips_when_file_unstable(tmp_path, monkeypatch, caplog):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    monkeypatch.setattr(translator, "OUTPUT_DIR", str(output_dir))

    input_pdf = tmp_path / "report.pdf"
    input_pdf.write_bytes(b"fake input")

    with patch.object(translator, "wait_for_stable", return_value=False):
        with patch.object(translator, "extract_text") as mock_extract:
            translator.translate_document(str(input_pdf))
            mock_extract.assert_not_called()


def test_translate_document_skips_when_no_text(tmp_path, monkeypatch):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    monkeypatch.setattr(translator, "OUTPUT_DIR", str(output_dir))

    input_pdf = tmp_path / "report.pdf"
    input_pdf.write_bytes(b"fake input")

    with patch.object(translator, "wait_for_stable", return_value=True), patch.object(
        translator, "extract_text", return_value="   "
    ):
        with patch.object(translator, "build_pdf") as mock_build:
            translator.translate_document(str(input_pdf))
            mock_build.assert_not_called()


def test_translate_document_full_pipeline(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-ci")

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    monkeypatch.setattr(translator, "OUTPUT_DIR", str(output_dir))

    input_pdf = tmp_path / "patient_report.pdf"
    input_pdf.write_bytes(b"fake pdf bytes")

    with patch.object(translator, "wait_for_stable", return_value=True), patch.object(
        translator, "extract_text", return_value="Patient deductible: $500"
    ), patch("anthropic.Anthropic"), patch.object(
        translator,
        "translate_text",
        return_value="Deducible del paciente: $500",
    ), patch.object(
        translator, "build_pdf"
    ) as mock_build, patch(
        "db.register_document"
    ) as mock_register:
        translator.translate_document(str(input_pdf))

    mock_build.assert_called_once()
    # Verify output path and translated text passed to build_pdf
    call_args = mock_build.call_args
    assert call_args[0][0] == "Deducible del paciente: $500"
    assert call_args[0][1] == str(output_dir / "patient_report.pdf")

    mock_register.assert_called_once_with("patient_report.pdf")


def test_translate_document_handles_extraction_error(tmp_path, monkeypatch):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    monkeypatch.setattr(translator, "OUTPUT_DIR", str(output_dir))

    input_pdf = tmp_path / "bad.pdf"
    input_pdf.write_bytes(b"corrupt pdf")

    with patch.object(translator, "wait_for_stable", return_value=True), patch.object(
        translator, "extract_text", side_effect=Exception("pdfplumber error")
    ):
        with patch.object(translator, "build_pdf") as mock_build:
            translator.translate_document(str(input_pdf))  # must not raise
            mock_build.assert_not_called()


def test_translate_document_handles_translation_error(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-ci")

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    monkeypatch.setattr(translator, "OUTPUT_DIR", str(output_dir))

    input_pdf = tmp_path / "report.pdf"
    input_pdf.write_bytes(b"fake")

    with patch.object(translator, "wait_for_stable", return_value=True), patch.object(
        translator, "extract_text", return_value="Some English text"
    ), patch("anthropic.Anthropic"), patch.object(
        translator, "translate_text", side_effect=Exception("API rate limit")
    ):
        with patch.object(translator, "build_pdf") as mock_build:
            translator.translate_document(str(input_pdf))  # must not raise
            mock_build.assert_not_called()
