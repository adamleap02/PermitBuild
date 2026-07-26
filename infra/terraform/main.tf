# infra/terraform/main.tf
#
# Root module for the construction-intel production AWS deployment.
#
# *** THIS HAS NOT BEEN APPLIED. NOTHING HERE HAS CREATED ANY REAL AWS RESOURCE. ***
# Read infra/terraform/README.md before running any terraform command against
# real AWS credentials. `terraform init` and `terraform plan` are safe (read-only
# against AWS); `terraform apply` is NOT and will incur real billing.

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Remote state is intentionally NOT configured yet. Until this backend block
  # is uncommented and pointed at a real (versioned, encrypted) S3 bucket +
  # DynamoDB lock table, `terraform` uses local state (terraform.tfstate on
  # disk, already covered by .gitignore). Do not flip this on until an AWS
  # account exists and someone has deliberately decided to start managing real
  # infra - see infra/BLOCKERS.md.
  #
  # backend "s3" {
  #   bucket         = "construction-intel-tfstate"
  #   key            = "prod/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "construction-intel-tflock"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = merge(
      {
        Project     = var.project_name
        Environment = var.environment
        ManagedBy   = "terraform"
      },
      var.tags
    )
  }
}

locals {
  name_prefix = "${var.project_name}-${var.environment}"
}

# --- Networking -------------------------------------------------------------

module "vpc" {
  source = "./modules/vpc"

  name_prefix = local.name_prefix
  vpc_cidr    = var.vpc_cidr
  az_count    = var.az_count
}

# --- Images & secrets (no cross-module cycles: created before compute) ------

module "ecr" {
  source = "./modules/ecr"

  name_prefix = local.name_prefix
}

module "secrets" {
  source = "./modules/secrets"

  name_prefix = local.name_prefix
}

# --- Compute (creates the shared "service" security group RDS/Redis trust) --

module "ecs" {
  source = "./modules/ecs"

  name_prefix = local.name_prefix

  vpc_id             = module.vpc.vpc_id
  public_subnet_ids  = module.vpc.public_subnet_ids
  private_subnet_ids = module.vpc.private_subnet_ids

  ecr_api_repository_url    = module.ecr.api_repository_url
  ecr_worker_repository_url = module.ecr.worker_repository_url
  api_image_tag             = var.api_image_tag
  worker_image_tag          = var.worker_image_tag

  api_cpu              = var.api_cpu
  api_memory           = var.api_memory
  api_desired_count    = var.api_desired_count
  worker_cpu           = var.worker_cpu
  worker_memory        = var.worker_memory
  worker_desired_count = var.worker_desired_count

  database_secret_arn = module.secrets.database_url_secret_arn
  redis_url           = module.redis.redis_url
  sqs_queue_url       = module.sqs.task_queue_url
  sqs_queue_arn       = module.sqs.task_queue_arn
  s3_exports_bucket   = module.s3.exports_bucket_name
  log_group_name      = module.cloudwatch.ecs_log_group_name
}

# --- Data & queue tier --------------------------------------------------------
# (rds/redis reference module.ecs's service security group so only ECS tasks
# can reach them; ecs itself does not depend on rds/redis for its own security
# group creation, so there is no dependency cycle.)

module "rds" {
  source = "./modules/rds"

  name_prefix = local.name_prefix

  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids

  db_name              = var.db_name
  db_username          = var.db_username
  db_instance_class    = var.db_instance_class
  allocated_storage_gb = var.db_allocated_storage_gb

  app_security_group_id  = module.ecs.service_security_group_id
  db_password_secret_id  = module.secrets.db_password_secret_id
  db_password_secret_arn = module.secrets.db_password_secret_arn
}

module "redis" {
  source = "./modules/redis"

  name_prefix = local.name_prefix

  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  node_type          = var.redis_node_type

  app_security_group_id = module.ecs.service_security_group_id
}

module "sqs" {
  source = "./modules/sqs"

  name_prefix = local.name_prefix
}

module "s3" {
  source = "./modules/s3"

  name_prefix = local.name_prefix
}

# --- Observability ------------------------------------------------------------

module "cloudwatch" {
  source = "./modules/cloudwatch"

  name_prefix               = local.name_prefix
  alarm_notification_email  = var.alarm_notification_email
  ecs_cluster_name          = module.ecs.cluster_name
  rds_instance_id           = module.rds.db_instance_id
}
