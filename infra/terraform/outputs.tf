output "vpc_id" {
  description = "ID of the VPC."
  value       = module.vpc.vpc_id
}

output "alb_dns_name" {
  description = "Public DNS name of the ALB in front of the API. Point a real domain's CNAME/ALIAS at this once one exists."
  value       = module.ecs.alb_dns_name
}

output "ecs_cluster_name" {
  description = "Name of the ECS cluster running the API and Celery worker services."
  value       = module.ecs.cluster_name
}

output "rds_endpoint" {
  description = "RDS Postgres connection endpoint (host:port)."
  value       = module.rds.db_endpoint
  sensitive   = true
}

output "redis_endpoint" {
  description = "ElastiCache Redis connection URL used as the Celery broker."
  value       = module.redis.redis_url
  sensitive   = true
}

output "ecr_api_repository_url" {
  description = "ECR repository URL to `docker push` the backend API image to."
  value       = module.ecr.api_repository_url
}

output "ecr_worker_repository_url" {
  description = "ECR repository URL to `docker push` the Celery worker image to."
  value       = module.ecr.worker_repository_url
}

output "s3_exports_bucket" {
  description = "S3 bucket name for generated exports (CSV/report downloads)."
  value       = module.s3.exports_bucket_name
}

output "s3_raw_data_bucket" {
  description = "S3 bucket name for raw ingested source artifacts (scraped HTML/PDF/CSV, etc.)."
  value       = module.s3.raw_data_bucket_name
}

output "sqs_task_queue_url" {
  description = "SQS queue URL for bursty/long-running ingestion jobs."
  value       = module.sqs.task_queue_url
}

output "cloudwatch_alarms_topic_arn" {
  description = "SNS topic ARN that CloudWatch alarms publish to."
  value       = module.cloudwatch.alarms_topic_arn
}
