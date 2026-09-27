###############################################################################
# Variables — Financial Restatement Pipeline
###############################################################################

variable "project_id" {
  description = "GCP project ID where all resources will be created."
  type        = string
}

variable "region" {
  description = "GCP region for compute resources (Cloud Functions, Scheduler)."
  type        = string
  default     = "us-east4"
}

variable "bq_location" {
  description = "BigQuery dataset location. Multi-region ('US') or single region."
  type        = string
  default     = "US"
}

variable "edgar_user_agent" {
  description = "SEC EDGAR requires a User-Agent header: 'Company Name email@domain.com'."
  type        = string
  default     = "FinancialRestatementPipeline admin@example.com"
}

variable "function_source_path" {
  description = "Local path to the zipped Cloud Function source code."
  type        = string
  default     = "../dist/edgar-ingestion.zip"
}

variable "function_version" {
  description = "Semver tag appended to the Cloud Function archive object name for cache-busting."
  type        = string
  default     = "0.1.0"
}

variable "common_labels" {
  description = "Labels applied to every resource for cost tracking and organization."
  type        = map(string)
  default = {
    project     = "financial-restatement"
    environment = "production"
    managed_by  = "terraform"
  }
}
