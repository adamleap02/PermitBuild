variable "name_prefix" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "node_type" {
  type = string
}

variable "app_security_group_id" {
  description = "Security group ID of the ECS services allowed to reach this cache on 6379."
  type        = string
}
