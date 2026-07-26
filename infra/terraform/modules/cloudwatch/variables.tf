variable "name_prefix" {
  type = string
}

variable "alarm_notification_email" {
  description = "Email to subscribe to the alarms SNS topic. Empty string skips the subscription."
  type        = string
  default     = ""
}

variable "ecs_cluster_name" {
  type = string
}

variable "rds_instance_id" {
  type = string
}
