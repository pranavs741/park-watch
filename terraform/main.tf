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
