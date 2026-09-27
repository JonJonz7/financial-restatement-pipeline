###############################################################################
# Financial Restatement Pipeline — Container Image
# --------------------------------------------------------------------------
# Multi-purpose image for running the pipeline CLI, dbt transforms, and the
# Streamlit dashboard.  Kept lean with python:3.11-slim as the base.
###############################################################################

FROM python:3.11-slim AS base

# Prevent Python from buffering stdout/stderr (important for container logs)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System dependencies (minimal — DuckDB ships its own libs)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        git \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---------------------------------------------------------------------------
# Dependencies — install before copying source for better layer caching
# ---------------------------------------------------------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------------------
# Source code
# ---------------------------------------------------------------------------
COPY ingestion/ ingestion/
COPY detection/ detection/
COPY quality/ quality/
COPY dbt_project/ dbt_project/
COPY dashboard/ dashboard/
COPY dags/ dags/

# ---------------------------------------------------------------------------
# dbt deps (pre-install packages so they're baked into the image)
# ---------------------------------------------------------------------------
RUN cd dbt_project && dbt deps --profiles-dir . --project-dir . || true

# ---------------------------------------------------------------------------
# Healthcheck
# ---------------------------------------------------------------------------
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

EXPOSE 8501

# Default entrypoint: run the Streamlit dashboard
CMD ["streamlit", "run", "dashboard/app.py", \
     "--server.port=8501", \
     "--server.headless=true", \
     "--server.address=0.0.0.0"]
