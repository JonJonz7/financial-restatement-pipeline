###############################################################################
# Financial Restatement Pipeline — Developer Makefile
#
#   make setup      one-time: virtualenv, dependencies, dbt packages
#   make demo       full pipeline on the bundled sample data (no network)
#   make pipeline   full pipeline on live SEC EDGAR data (needs EDGAR_USER_AGENT)
###############################################################################

.DEFAULT_GOAL := help
.PHONY: help setup ingest replay demo transform quality detect pipeline test \
        lint format dashboard docker-up docker-down clean sample-data

VENV       := $(CURDIR)/.venv
PYTHON     := $(VENV)/bin/python
PIP        := $(VENV)/bin/pip
DBT        := $(VENV)/bin/dbt
STREAMLIT  := $(VENV)/bin/streamlit
PYTEST     := $(VENV)/bin/pytest
RUFF       := $(VENV)/bin/ruff

# One warehouse path for Python and dbt (dbt reads it via env_var in profiles.yml)
export WAREHOUSE_DB_PATH ?= $(CURDIR)/warehouse.duckdb
DBT_ARGS   := --profiles-dir . --project-dir .
PY_DIRS    := ingestion detection quality dags tests scripts dashboard

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup: ## Create venv, install deps, install dbt packages
	python3.11 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	cd dbt_project && $(DBT) deps $(DBT_ARGS)
	@echo "\n--- Setup complete. Try: make demo ---"

ingest: ## Pull live SEC EDGAR filings + prices into bronze
	$(PYTHON) -m ingestion.pipeline

replay: ## Rebuild bronze from the landing zone (no network)
	$(PYTHON) -m ingestion.pipeline --replay

transform: ## dbt build: seeds, models and all tests (staging -> intermediate -> marts)
	cd dbt_project && $(DBT) build $(DBT_ARGS)

quality: ## Data contracts + Great Expectations suite (fail on any breach)
	$(PYTHON) -m quality.check_contracts
	$(PYTHON) -m quality.run_expectations

detect: ## Score anomalies into gold.alerts + reports/alerts.md
	$(PYTHON) -m detection.run

pipeline: ingest quality transform detect ## Full live run
	@echo "\n--- Pipeline complete: see reports/alerts.md ---"

demo: ## Full run on bundled sample data, in demo.duckdb (no network)
	rm -f $(CURDIR)/demo.duckdb
	$(MAKE) --no-print-directory _demo WAREHOUSE_DB_PATH=$(CURDIR)/demo.duckdb

_demo:
	$(PYTHON) -m ingestion.demo
	$(PYTHON) -m quality.check_contracts
	$(PYTHON) -m quality.run_expectations
	cd dbt_project && $(DBT) build $(DBT_ARGS)
	$(PYTHON) -m detection.run --report reports/demo_alerts.md

sample-data: ## Regenerate data/sample/ (fictional companies)
	$(PYTHON) scripts/make_sample_data.py

test: ## Unit + integration tests
	$(PYTEST) tests/ -v --tb=short

lint: ## Lint and check formatting
	$(RUFF) check $(PY_DIRS)
	$(RUFF) format --check $(PY_DIRS)

format: ## Auto-fix lint and formatting
	$(RUFF) check --fix $(PY_DIRS)
	$(RUFF) format $(PY_DIRS)

dashboard: ## Streamlit dashboard on localhost:8501
	$(STREAMLIT) run dashboard/app.py --server.port=8501

docker-up: ## Start Airflow + dashboard via docker compose
	docker compose up -d --build
	@echo "\nAirflow UI: http://localhost:8080  (admin/admin)"
	@echo "Dashboard:  http://localhost:8501"

docker-down: ## Stop docker compose services
	docker compose down

clean: ## Remove warehouses, dbt artifacts and caches (keeps .venv and data/landing)
	rm -f warehouse.duckdb demo.duckdb *.duckdb.wal
	rm -rf dbt_project/target dbt_project/logs
	rm -rf .pytest_cache .ruff_cache test-results.xml
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
