# Copyright (c) Brand.Me, Inc. All rights reserved.
#
# Brand.Me Infrastructure - Main Terraform Configuration
# =======================================================

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }

  backend "gcs" {
    bucket = "brandme-terraform-state"
    prefix = "terraform/state"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ==========================================
# Variables
# ==========================================

variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP Region"
  type        = string
  default     = "us-east1"
}

variable "environment" {
  description = "Environment (dev/staging/prod)"
  type        = string
}

# ==========================================
# VPC Network
# ==========================================

resource "google_compute_network" "vpc" {
  name                    = "brandme-vpc-${var.environment}"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "subnet" {
  name          = "brandme-subnet-${var.environment}"
  ip_cidr_range = "10.0.0.0/24"
  region        = var.region
  network       = google_compute_network.vpc.id

  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = "10.1.0.0/16"
  }

  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = "10.2.0.0/16"
  }
}

# ==========================================
# GKE Cluster
# ==========================================

resource "google_container_cluster" "primary" {
  name     = "brandme-cluster-${var.environment}"
  location = var.region

  # We can't create a cluster with no node pool defined, but we want to only use
  # separately managed node pools. So we create the smallest possible default
  # node pool and immediately delete it.
  remove_default_node_pool = true
  initial_node_count       = 1

  network    = google_compute_network.vpc.name
  subnetwork = google_compute_subnetwork.subnet.name

  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  addons_config {
    http_load_balancing {
      disabled = false
    }
    horizontal_pod_autoscaling {
      disabled = false
    }
  }

  release_channel {
    channel = "REGULAR"
  }
}

resource "google_container_node_pool" "primary_nodes" {
  name       = "brandme-node-pool"
  location   = var.region
  cluster    = google_container_cluster.primary.name
  node_count = 3

  node_config {
    machine_type = "e2-standard-4"
    disk_size_gb = 100

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]

    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    labels = {
      environment = var.environment
      managed_by  = "terraform"
    }
  }

  autoscaling {
    min_node_count = 3
    max_node_count = 10
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }
}

# ==========================================
# Cloud SQL (PostgreSQL)
# ==========================================

resource "google_sql_database_instance" "postgres" {
  name             = "brandme-postgres-${var.environment}"
  database_version = "POSTGRES_15"
  region           = var.region

  settings {
    tier = "db-custom-2-7680"

    backup_configuration {
      enabled                        = true
      start_time                     = "03:00"
      point_in_time_recovery_enabled = true
      backup_retention_settings {
        retained_backups = 30
      }
    }

    ip_configuration {
      ipv4_enabled    = true
      private_network = google_compute_network.vpc.id
      require_ssl     = true
    }

    database_flags {
      name  = "max_connections"
      value = "100"
    }
  }

  deletion_protection = var.environment == "prod" ? true : false
}

resource "google_sql_database" "brandme_db" {
  name     = "brandme"
  instance = google_sql_database_instance.postgres.name
}

resource "google_sql_user" "brandme_user" {
  name     = "brandme"
  instance = google_sql_database_instance.postgres.name
  password = var.db_password # Should be from Secret Manager
}

# ==========================================
# Cloud Storage Bucket
# ==========================================

resource "google_storage_bucket" "passport_blobs" {
  name          = "brandme-passport-blobs-${var.environment}"
  location      = var.region
  force_destroy = var.environment != "prod"

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }

  lifecycle_rule {
    condition {
      age = 365
    }
    action {
      type          = "SetStorageClass"
      storage_class = "COLDLINE"
    }
  }
}

# ==========================================
# Service Accounts & IAM
# ==========================================

resource "google_service_account" "brandme_workload" {
  account_id   = "brandme-workload-${var.environment}"
  display_name = "Brand.Me Workload Identity Service Account"
}

resource "google_project_iam_member" "workload_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.brandme_workload.email}"
}

resource "google_storage_bucket_iam_member" "workload_storage" {
  bucket = google_storage_bucket.passport_blobs.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.brandme_workload.email}"
}

# ==========================================
# Outputs
# ==========================================

output "gke_cluster_name" {
  value       = google_container_cluster.primary.name
  description = "GKE Cluster Name"
}

output "gke_cluster_endpoint" {
  value       = google_container_cluster.primary.endpoint
  description = "GKE Cluster Endpoint"
  sensitive   = true
}

output "cloudsql_connection_name" {
  value       = google_sql_database_instance.postgres.connection_name
  description = "Cloud SQL Connection Name"
}

output "gcs_bucket_name" {
  value       = google_storage_bucket.passport_blobs.name
  description = "GCS Bucket Name"
}

output "workload_identity_sa" {
  value       = google_service_account.brandme_workload.email
  description = "Workload Identity Service Account Email"
}
