.PHONY: help install install-dev lint format format-check typecheck test test-cov clean run-translator run-web

help:
	@echo "Available targets:"
	@echo "  install         Install runtime dependencies"
	@echo "  install-dev     Install runtime + dev dependencies"
	@echo "  lint            Run ruff linter"
	@echo "  format          Auto-format code with black"
	@echo "  format-check    Check formatting without modifying files"
	@echo "  typecheck       Run mypy type checker"
	@echo "  test            Run test suite"
	@echo "  test-cov        Run tests with HTML + terminal coverage report"
	@echo "  clean           Remove build/cache artifacts"
	@echo "  run-translator  Start the PDF translation watcher"
	@echo "  run-web         Start the Flask QA web interface"

install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements.txt -r requirements-dev.txt

lint:
	ruff check .

format:
	black .

format-check:
	black --check .

typecheck:
	mypy app.py db.py translator.py

test:
	pytest

test-cov:
	pytest --cov=. --cov-report=term-missing --cov-report=html
	@echo ""
	@echo "HTML coverage report: htmlcov/index.html"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -type f -name "*.pyc" -delete 2>/dev/null; true
	rm -rf .pytest_cache .coverage htmlcov .mypy_cache

run-translator:
	python3 translator.py

run-web:
	python3 app.py
