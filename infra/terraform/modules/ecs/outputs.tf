output "cluster_name" {
  value = aws_ecs_cluster.this.name
}

output "service_security_group_id" {
  description = "Security group shared by the api and worker ECS tasks - used by rds/redis modules to scope their ingress rules."
  value       = aws_security_group.service.id
}

output "alb_dns_name" {
  value = aws_lb.api.dns_name
}
