variable "name_prefix" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "db_name" {
  type = string
}

variable "db_username" {
  type = string
}

variable "db_instance_class" {
  type = string
}

variable "allocated_storage_gb" {
  type = number
}

variable "app_security_group_id" {
  description = "Security group ID of the ECS services allowed to reach this database on 5432."
  type        = string
}

variable "db_password_secret_id" {
  description = "Secrets Manager secret ID holding the generated master password."
  type        = string
}

variable "db_password_secret_arn" {
  description = "Secrets Manager secret ARN holding the generated master password (unused directly here, kept for callers that need it)."
  type        = string
  default     = ""
}
