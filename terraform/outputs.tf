###############################################################################
# Outputs — Financial Restatement Pipeline
###############################################################################

output "bigquery_dataset_bronze_id" {
  description = "Fully-qualified BigQuery dataset ID for the bronze (raw) layer."
  value       = google_bigquery_dataset.bronze.dataset_id
}

output "bigquery_dataset_silver_id" {
  description = "Fully-qualified BigQuery dataset ID for the silver (cleaned) layer."
  value       = google_bigquery_dataset.silver.dataset_id
}

output "bigquery_dataset_gold_id" {
  description = "Fully-qualified BigQuery dataset ID for the gold (analytics) layer."
  value       = google_bigquery_dataset.gold.dataset_id
}

output "cloud_function_url" {
  description = "HTTPS trigger URL for the EDGAR ingestion Cloud Function."
  value       = google_cloudfunctions2_function.edgar_ingestion.url
}

output "raw_filings_bucket_name" {
  description = "GCS bucket name for raw SEC filing storage."
  value       = google_storage_bucket.raw_filings.name
}

output "pipeline_service_account_email" {
  description = "Email of the pipeline service account (for downstream IAM bindings)."
  value       = google_service_account.pipeline_sa.email
}
