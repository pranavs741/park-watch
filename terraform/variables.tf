variable "project_id" {
  description = "GCP project containing the Park Watch VM."
  type        = string
}

variable "region" {
  description = "GCP region containing the VM and resource policy."
  type        = string
  default     = "us-west2"
}

variable "zone" {
  description = "Zone containing the Park Watch VM, for example us-west2-a."
  type        = string
}

variable "instance_name" {
  description = "Name of the Compute Engine VM to schedule."
  type        = string
}

variable "time_zone" {
  description = "IANA time zone used by the VM schedules."
  type        = string
  default     = "America/Los_Angeles"
}

variable "start_schedule" {
  description = "Unix cron expression for starting the VM."
  type        = string
  default     = "30 7 * * *"
}

variable "stop_schedule" {
  description = "Unix cron expression for stopping the VM."
  type        = string
  default     = "0 17 * * *"
}
