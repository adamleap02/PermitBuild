# modules/redis - ElastiCache Redis, used as the primary Celery broker/result
# backend and general-purpose cache.

resource "aws_elasticache_subnet_group" "this" {
  name       = "${var.name_prefix}-redis-subnets"
  subnet_ids = var.private_subnet_ids
}

resource "aws_security_group" "redis" {
  name        = "${var.name_prefix}-redis-sg"
  description = "Allow Redis access from the ECS app services only"
  vpc_id      = var.vpc_id

  ingress {
    description     = "Redis from ECS services"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [var.app_security_group_id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.name_prefix}-redis-sg"
  }
}

resource "aws_elasticache_replication_group" "this" {
  replication_group_id = "${var.name_prefix}-redis"
  description           = "Redis for Celery broker/result backend and general caching"
  engine                = "redis"
  engine_version        = "7.1"
  node_type             = var.node_type

  num_cache_clusters         = 1 # single node to start; raise + enable automatic_failover_enabled for HA (adds cost)
  port                       = 6379
  automatic_failover_enabled = false

  subnet_group_name  = aws_elasticache_subnet_group.this.name
  security_group_ids = [aws_security_group.redis.id]

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true

  tags = {
    Name = "${var.name_prefix}-redis"
  }
}
