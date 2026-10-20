###############################################################################
# Financial Restatement & Anomaly Detection Pipeline — GCP Infrastructure
# --------------------------------------------------------------------------
# Production-grade Terraform for BigQuery medallion architecture, Cloud
# Functions-based EDGAR ingestion, Cloud Scheduler orchestration, and GCS
# raw-filing storage.  Dev environment uses DuckDB; this config mirrors the
# production deployment target.
###############################################################################

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }

  backend "gcs" {
    bucket = "financial-restatement-tfstate"
    prefix = "terraform/state"
  }
}

# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------
provider "google" {
  project = var.project_id
  region  = var.region
}

# ---------------------------------------------------------------------------
# Data sources
# ---------------------------------------------------------------------------
data "google_project" "current" {}

# ---------------------------------------------------------------------------
# Service Account — single identity for the entire pipeline
# ---------------------------------------------------------------------------
resource "google_service_account" "pipeline_sa" {
  account_id   = "restatement-pipeline-sa"
  display_name = "Financial Restatement Pipeline Service Account"
  description  = "Runs EDGAR ingestion, dbt transforms, anomaly detection"
}

# ---------------------------------------------------------------------------
# GCS — raw filing storage
# ---------------------------------------------------------------------------
resource "google_storage_bucket" "raw_filings" {
  name                        = "${var.project_id}-raw-filings"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  force_destroy               = false

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age = 365
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }

  labels = var.common_labels
}

resource "google_storage_bucket_iam_member" "pipeline_sa_gcs" {
  bucket = google_storage_bucket.raw_filings.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.pipeline_sa.email}"
}

# ---------------------------------------------------------------------------
# BigQuery — medallion architecture (bronze / silver / gold)
# ---------------------------------------------------------------------------
resource "google_bigquery_dataset" "bronze" {
  dataset_id    = "financial_restatement_bronze"
  friendly_name = "Bronze — Raw EDGAR Extracts"
  description   = "Landing zone for raw SEC EDGAR financial facts and filing metadata."
  location      = var.bq_location

  default_table_expiration_ms = null # raw data retained indefinitely

  labels = var.common_labels

  access {
    role          = "OWNER"
    special_group = "projectOwners"
  }

  access {
    role          = "WRITER"
    user_by_email = google_service_account.pipeline_sa.email
  }
}

resource "google_bigquery_dataset" "silver" {
  dataset_id    = "financial_restatement_silver"
  friendly_name = "Silver — Cleaned & Conformed"
  description   = "Cleaned, deduplicated, type-cast financial facts with business keys."
  location      = var.bq_location

  labels = var.common_labels

  access {
    role          = "OWNER"
    special_group = "projectOwners"
  }

  access {
    role          = "WRITER"
    user_by_email = google_service_account.pipeline_sa.email
  }
}

resource "google_bigquery_dataset" "gold" {
  dataset_id    = "financial_restatement_gold"
  friendly_name = "Gold — Analytics & Detection"
  description   = "Restatement flags, anomaly scores, alert-ready aggregates."
  location      = var.bq_location

  labels = var.common_labels

  access {
    role          = "OWNER"
    special_group = "projectOwners"
  }

  access {
    role          = "WRITER"
    user_by_email = google_service_account.pipeline_sa.email
  }

  access {
    role          = "READER"
    special_group = "projectReaders"
  }
}

# ---------------------------------------------------------------------------
# Cloud Function — EDGAR ingestion
# ---------------------------------------------------------------------------
resource "google_storage_bucket" "function_source" {
  name                        = "${var.project_id}-cf-source"
  location                    = var.region
  uniform_bucket_level_access = true
  labels                      = var.common_labels
}

resource "google_storage_bucket_object" "function_archive" {
  name   = "edgar-ingestion-${var.function_version}.zip"
  bucket = google_storage_bucket.function_source.name
  source = var.function_source_path
}

resource "google_cloudfunctions2_function" "edgar_ingestion" {
  name     = "edgar-ingestion"
  location = var.region

  build_config {
    runtime     = "python311"
    entry_point = "ingest_handler"

    source {
      storage_source {
        bucket = google_storage_bucket.function_source.name
        object = google_storage_bucket_object.function_archive.name
      }
    }
  }

  service_config {
    max_instance_count    = 3
    min_instance_count    = 0
    available_memory      = "512Mi"
    timeout_seconds       = 540
    service_account_email = google_service_account.pipeline_sa.email

    environment_variables = {
      RAW_BUCKET       = google_storage_bucket.raw_filings.name
      BQ_DATASET       = google_bigquery_dataset.bronze.dataset_id
      GCP_PROJECT      = var.project_id
      EDGAR_USER_AGENT = var.edgar_user_agent
    }
  }

  labels = var.common_labels
}

# ---------------------------------------------------------------------------
# Cloud Scheduler — daily trigger at 06:00 ET
# ---------------------------------------------------------------------------
resource "google_cloud_scheduler_job" "daily_ingestion" {
  name        = "edgar-daily-ingestion"
  description = "Triggers EDGAR filing ingestion every day at 6 AM Eastern"
  schedule    = "0 6 * * *"
  time_zone   = "America/New_York"
  region      = var.region

  retry_config {
    retry_count          = 3
    min_backoff_duration = "30s"
    max_backoff_duration = "300s"
  }

  http_target {
    http_method = "POST"
    uri         = google_cloudfunctions2_function.edgar_ingestion.url

    oidc_token {
      service_account_email = google_service_account.pipeline_sa.email
      audience              = google_cloudfunctions2_function.edgar_ingestion.url
    }

    body = base64encode(jsonencode({
      mode       = "incremental"
      batch_size = 50
    }))

    headers = {
      "Content-Type" = "application/json"
    }
  }
}

# ---------------------------------------------------------------------------
# IAM — least-privilege bindings
# ---------------------------------------------------------------------------
resource "google_project_iam_member" "pipeline_bq_user" {
  project = var.project_id
  role    = "roles/bigquery.user"
  member  = "serviceAccount:${google_service_account.pipeline_sa.email}"
}

resource "google_project_iam_member" "pipeline_bq_data_editor" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.pipeline_sa.email}"
}

resource "google_project_iam_member" "pipeline_cf_invoker" {
  project = var.project_id
  role    = "roles/cloudfunctions.invoker"
  member  = "serviceAccount:${google_service_account.pipeline_sa.email}"
}

resource "google_project_iam_member" "pipeline_scheduler_admin" {
  project = var.project_id
  role    = "roles/cloudscheduler.admin"
  member  = "serviceAccount:${google_service_account.pipeline_sa.email}"
}

# ---------------------------------------------------------------------------
# Enable required APIs
# ---------------------------------------------------------------------------
resource "google_project_service" "apis" {
  for_each = toset([
    "bigquery.googleapis.com",
    "cloudfunctions.googleapis.com",
    "cloudscheduler.googleapis.com",
    "storage.googleapis.com",
    "cloudbuild.googleapis.com",
    "run.googleapis.com",
  ])

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}
