.PHONY: setup run test lint clean

# Default python from virtualenv
VENV = .venv
PYTHON = $(VENV)/bin/python
PIP = $(VENV)/bin/pip
PYTEST = $(VENV)/bin/pytest
UVICORN = $(VENV)/bin/uvicorn

$(VENV)/bin/activate: requirements.txt
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	touch $(VENV)/bin/activate

setup: $(VENV)/bin/activate ## Install dependencies and setup virtual environment

run: setup ## Run the FastAPI application in development mode
	$(UVICORN) app.main:app --reload

test: setup ## Run the test suite
	$(PYTEST) tests/ -v

lint: setup ## Run ruff linter (if installed)
	$(VENV)/bin/ruff check app/ tests/

clean: ## Clean up virtual environment and cache files
	rm -rf $(VENV)
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +

help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'
