###############################################################################
# Financial Restatement Pipeline — Developer Makefile
###############################################################################

.DEFAULT_GOAL := help
.PHONY: help setup ingest transform detect pipeline test quality \
        dashboard docker-up docker-down clean lint format

VENV       := .venv
PYTHON     := $(VENV)/bin/python
PIP        := $(VENV)/bin/pip
DBT        := $(VENV)/bin/dbt
STREAMLIT  := $(VENV)/bin/streamlit
PYTEST     := $(VENV)/bin/pytest
RUFF       := $(VENV)/bin/ruff
DUCKDB_PATH := warehouse.duckdb

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------
help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
setup: ## Create venv, install deps, init DuckDB, install dbt packages
	python3.11 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	$(PYTHON) -c "import duckdb; con = duckdb.connect('$(DUCKDB_PATH)'); \
		con.execute('CREATE SCHEMA IF NOT EXISTS bronze'); \
		con.execute('CREATE SCHEMA IF NOT EXISTS silver'); \
		con.execute('CREATE SCHEMA IF NOT EXISTS gold'); \
		con.close(); print('DuckDB initialized: $(DUCKDB_PATH)')"
	cd dbt_project && $(DBT) deps --profiles-dir . --project-dir .
	@echo "\n--- Setup complete. Activate with: source $(VENV)/bin/activate ---"

# ---------------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------------
ingest: ## Run EDGAR ingestion for all watched companies
	$(PYTHON) -m ingestion.pipeline

transform: ## Run dbt (staging -> intermediate -> marts)
	cd dbt_project && $(DBT) run --profiles-dir . --project-dir .

detect: ## Run restatement detection + anomaly scoring
	$(PYTHON) -m detection.restatement_detector
	$(PYTHON) -m detection.anomaly_scorer

pipeline: ingest transform detect ## Run full pipeline (ingest + transform + detect)
	@echo "\n--- Full pipeline complete ---"

# ---------------------------------------------------------------------------
# Testing & Quality
# ---------------------------------------------------------------------------
test: ## Run pytest + dbt test
	$(PYTEST) tests/ -v --tb=short
	cd dbt_project && $(DBT) test --profiles-dir . --project-dir .

quality: ## Run Great Expectations checkpoint
	cd quality/great_expectations && \
		$(PYTHON) -m great_expectations checkpoint run filing_checkpoint

lint: ## Lint source code with ruff
	$(RUFF) check ingestion/ detection/ dags/ tests/

format: ## Auto-format source code with ruff
	$(RUFF) format ingestion/ detection/ dags/ tests/

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
dashboard: ## Start Streamlit dashboard on port 8501
	$(STREAMLIT) run dashboard/app.py --server.port=8501

# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------
docker-up: ## Start all services via docker-compose
	docker compose up -d --build
	@echo "\nAirflow UI: http://localhost:8080  (admin/admin)"
	@echo "Dashboard:  http://localhost:8501"

docker-down: ## Stop all services
	docker compose down

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
clean: ## Remove generated files, caches, venv
	rm -f $(DUCKDB_PATH)
	rm -rf $(VENV)
	rm -rf dbt_project/target dbt_project/dbt_packages dbt_project/logs
	rm -rf quality/great_expectations/uncommitted
	rm -rf __pycache__ */__pycache__ */*/__pycache__
	rm -rf .pytest_cache tests/.pytest_cache
	rm -rf .ruff_cache
	rm -f test-results.xml
	@echo "Cleaned."
