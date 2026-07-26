# modules/rds - RDS Postgres instance for the application database.
#
# PostGIS note: RDS Postgres ships the PostGIS extension binaries already, but
# the extension itself must still be enabled per-database with:
#   CREATE EXTENSION IF NOT EXISTS postgis;
# This is NOT done by Terraform - it should be the first Alembic migration the
# backend runs against a fresh database (same migration works against the
# local docker-compose postgis/postgis Postgres too, since that image also
# ships the extension pre-installed but not auto-enabled per database).

data "aws_secretsmanager_secret_version" "db_password" {
  secret_id = var.db_password_secret_id
}

resource "aws_db_subnet_group" "this" {
  name       = "${var.name_prefix}-db-subnets"
  subnet_ids = var.private_subnet_ids
}

resource "aws_security_group" "rds" {
  name        = "${var.name_prefix}-rds-sg"
  description = "Allow Postgres access from the ECS app services only"
  vpc_id      = var.vpc_id

  ingress {
    description     = "Postgres from ECS services"
    from_port       = 5432
    to_port         = 5432
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
    Name = "${var.name_prefix}-rds-sg"
  }
}

resource "aws_db_instance" "this" {
  identifier     = "${var.name_prefix}-postgres"
  engine         = "postgres"
  engine_version = "16.4"
  instance_class = var.db_instance_class

  allocated_storage     = var.allocated_storage_gb
  max_allocated_storage = var.allocated_storage_gb * 5 # allow autoscaling storage up to 5x before manual intervention
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = var.db_name
  username = var.db_username
  password = data.aws_secretsmanager_secret_version.db_password.secret_string

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false

  multi_az                     = false # set true for HA in a real production launch - roughly doubles RDS cost
  backup_retention_period      = 7
  deletion_protection          = true
  skip_final_snapshot          = false
  final_snapshot_identifier    = "${var.name_prefix}-postgres-final"
  auto_minor_version_upgrade   = true
  performance_insights_enabled = true

  tags = {
    Name = "${var.name_prefix}-postgres"
  }
}
