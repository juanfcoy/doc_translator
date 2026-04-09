# Healthcare Document Translation Service

A Python-based pipeline that automatically translates English healthcare PDFs to Spanish using the Claude API, with a web-based QA interface for reviewers to annotate translations.

## Overview

1. **Translator** — watches `translations/input/` for new PDFs, extracts text with pdfplumber, sends it to Claude for translation, and writes a reconstructed Spanish PDF to `translations/output/`.
2. **QA Interface** — a Flask web app where reviewers view the original and translated PDFs side by side, highlight sections, and log feedback notes to a SQLite database.

## Requirements

- Python 3.11+
- An Anthropic API key

## Setup

```bash
# Install runtime dependencies
pip install -r requirements.txt

# Set your API key
export ANTHROPIC_API_KEY=sk-ant-...
```

## Running

Start each component in a separate terminal:

```bash
# Terminal 1 — translation watcher
python3 translator.py

# Terminal 2 — QA web interface
python3 app.py
```

Then open [http://localhost:5000](http://localhost:5000) in your browser.

Drop any PDF into `translations/input/` and the translator will detect it, translate it, and register it in the dashboard automatically.

## Project Structure

```
doc_translator/
├── translator.py          # File watcher + Claude translation pipeline
├── app.py                 # Flask QA web interface
├── db.py                  # SQLite persistence layer
├── requirements.txt       # Runtime dependencies
├── requirements-dev.txt   # Dev/test dependencies
├── pyproject.toml         # Tool config (black, ruff, mypy, pytest)
├── Makefile               # Developer convenience targets
├── .pre-commit-config.yaml
├── .github/
│   └── workflows/
│       └── ci.yml         # GitHub Actions CI pipeline
├── templates/
│   ├── base.html
│   ├── dashboard.html     # Document list with status and feedback counts
│   └── review.html        # Side-by-side PDF review and annotation UI
├── static/
│   ├── css/styles.css
│   └── js/review.js       # PDF.js rendering + text selection + feedback POST
├── tests/
│   ├── conftest.py
│   ├── test_db.py
│   ├── test_app.py
│   └── test_translator.py
└── translations/
    ├── input/             # Drop PDFs here to translate
    └── output/            # Translated PDFs appear here
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key for the Claude translation model |
| `FLASK_DEBUG` | No | Set to `1` to enable Flask debug mode (default: off) |

## Development

```bash
# Install dev dependencies
make install-dev

# Run tests
make test

# Run tests with coverage report
make test-cov

# Lint
make lint

# Format code
make format

# Type check
make typecheck

# Set up pre-commit hooks
pre-commit install
```

## CI

GitHub Actions runs on every push and pull request:

1. Format check (`black`)
2. Lint (`ruff`)
3. Type check (`mypy`)
4. Tests with ≥80% coverage requirement

## Notes

- The translated PDF is plain-text layout — `pdfplumber` extracts text only, not visual layout coordinates. The original PDF on the left pane of the review UI serves as the layout reference.
- Documents larger than 150,000 characters are split into chunks, translated separately, and rejoined.
- The SQLite database (`translation.db`) is created automatically on first run.
- Feedback notes are capped at 5,000 characters; selected text excerpts stored as the "section" field are capped at 500 characters.
