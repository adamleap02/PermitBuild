variable "name_prefix" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "ecr_api_repository_url" {
  type = string
}

variable "ecr_worker_repository_url" {
  type = string
}

variable "api_image_tag" {
  type = string
}

variable "worker_image_tag" {
  type = string
}

variable "api_cpu" {
  type = number
}

variable "api_memory" {
  type = number
}

variable "api_desired_count" {
  type = number
}

variable "worker_cpu" {
  type = number
}

variable "worker_memory" {
  type = number
}

variable "worker_desired_count" {
  type = number
}

variable "database_secret_arn" {
  description = "Secrets Manager ARN of the composed DATABASE_URL, injected into both tasks as a secret env var."
  type        = string
}

variable "redis_url" {
  description = "Redis connection URL passed as a plain env var (not sensitive enough to warrant a secret, but fine to move to Secrets Manager if desired)."
  type        = string
}

variable "sqs_queue_url" {
  type = string
}

variable "sqs_queue_arn" {
  type = string
}

variable "s3_exports_bucket" {
  type = string
}

variable "log_group_name" {
  type = string
}
