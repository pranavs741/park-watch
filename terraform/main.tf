terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_compute_resource_policy" "parkwatch_hours" {
  name   = "parkwatch-hours"
  region = var.region

  instance_schedule_policy {
    time_zone = var.time_zone

    vm_start_schedule {
      schedule = var.start_schedule
    }

    vm_stop_schedule {
      schedule = var.stop_schedule
    }
  }
}

resource "google_compute_resource_policy_attachment" "parkwatch_hours" {
  name     = google_compute_resource_policy.parkwatch_hours.name
  instance = var.instance_name
  zone     = var.zone
}

data "google_compute_instance" "parkwatch" {
  count = var.gcs_bucket_name == null ? 0 : 1
  name  = var.instance_name
  zone  = var.zone
}

resource "google_storage_bucket" "parkwatch_images" {
  count                       = var.gcs_bucket_name == null ? 0 : 1
  name                        = var.gcs_bucket_name
  location                    = var.region
  project                     = var.project_id
  uniform_bucket_level_access = true

  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "Delete"
    }
  }
}

resource "google_storage_bucket_iam_member" "parkwatch_uploader" {
  count  = var.gcs_bucket_name == null ? 0 : 1
  bucket = google_storage_bucket.parkwatch_images[0].name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${data.google_compute_instance.parkwatch[0].service_account[0].email}"
}
