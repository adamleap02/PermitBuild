output "redis_url" {
  description = "rediss:// connection URL (transit encryption is enabled, hence rediss not redis) for Celery/caching."
  value       = "rediss://${aws_elasticache_replication_group.this.primary_endpoint_address}:6379/0"
}

output "security_group_id" {
  value = aws_security_group.redis.id
}
