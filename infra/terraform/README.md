# Terraform - construction-intel production AWS deployment

## READ THIS FIRST

**This Terraform code has NOT been applied. No AWS resources described here
exist. Nothing has been created, and no money has been spent.**

**Running `terraform apply` on this module WILL create real, billable AWS
resources** - an RDS Postgres instance, an ElastiCache Redis cluster, a NAT
gateway, an Application Load Balancer, ECS Fargate tasks, etc. Several of
these (NAT gateway, ALB, RDS, ElastiCache) cost money **per hour they exist**,
regardless of traffic. Do not run `apply` casually or "just to see what
happens."

**Do not run `apply` until all of the following are true:**

1. A real AWS account exists with billing/payment set up (this is a human /
   business decision - see `infra/BLOCKERS.md` - and is explicitly **not**
   something an agent or script should do on your behalf).
2. AWS Budgets / billing alerts are configured on that account so unexpected
   spend gets caught immediately.
3. A human has run `terraform plan` (see below), read the full list of
   resources it intends to create, and understood the resulting cost.
4. The `backend "s3" {}` remote-state block in `main.tf` has been uncommented
   and pointed at a real (versioned, encrypted) S3 bucket + DynamoDB lock
   table - otherwise state lives only in a local `terraform.tfstate` file,
   which is fragile and not shareable across a team.

## The one command a human should run first

```bash
cd infra/terraform
terraform init
terraform plan -out=tfplan
```

`terraform plan` is **read-only** against AWS (it only needs credentials to
look up things like available AZs) and will print the full list of resources
that *would* be created, without creating anything. Review that output -
resource types, counts, and estimated monthly cost (cross-reference against
the [AWS Pricing Calculator](https://calculator.aws/)) - before anyone runs
`terraform apply tfplan`.

Do **not** run `terraform apply` (with or without `tfplan`) as part of any
automated agent workflow. Applying this configuration is a deliberate,
reviewed, human decision.

## What this describes

A production-style deployment of the construction-intel platform on AWS:

| Concern | Resource | Module |
|---|---|---|
| Network | VPC, public + private subnets across `az_count` AZs, 1 NAT gateway, route tables | `modules/vpc` |
| Database | RDS Postgres (PostGIS-capable engine; extension enabled via a one-time `CREATE EXTENSION postgis;` migration, not by Terraform) | `modules/rds` |
| Cache / broker | ElastiCache Redis (Celery broker + result backend, cache) | `modules/redis` |
| Task queue | SQS queue + DLQ, for bursty/long-running ingestion jobs as an alternative/supplement to the Redis broker | `modules/sqs` |
| Compute | ECS Fargate cluster running the FastAPI `api` service (behind an ALB) and the Celery `worker` service | `modules/ecs` |
| Object storage | S3 buckets: generated exports, raw ingested source artifacts | `modules/s3` |
| Images | ECR repositories for the `api` and `worker` images | `modules/ecr` |
| Secrets | Secrets Manager: generated DB master password, composed `DATABASE_URL`, placeholder for third-party API keys | `modules/secrets` |
| Observability | CloudWatch log group for ECS, CPU/storage alarms on ECS + RDS, SNS topic (+ optional email subscription) | `modules/cloudwatch` |

### Why ECS Fargate and not EKS

ECS Fargate is used for the API and worker services because it has **no
cluster/control-plane cost and no node management** - a good fit for a small,
early-stage team. If the team later standardizes on Kubernetes (e.g. for
portability, existing Helm charts, or a multi-cloud requirement), swap
`modules/ecs` for an EKS module (`aws_eks_cluster` + a managed node group or
Fargate profile) and translate the two task definitions into a Deployment
(api) and a Deployment or CronJob (worker). Budget for the EKS control plane
charge (currently ~$0.10/hr = ~$73/mo) plus node costs on top of that - this
is why EKS was not chosen as the default here.

### Cost awareness (rough order of magnitude, us-east-1, single small
environment, NOT a quote - check current AWS pricing before relying on this)

- NAT gateway: ~$0.045/hr + data processing, i.e. running 24/7 whether or not
  it's used.
- ALB: ~$0.0225/hr + LCU usage.
- RDS `db.t4g.micro`: Free-Tier eligible for a *new* AWS account's first 12
  months (750 hrs/mo + 20GB storage); billed normally after that or on an
  existing account.
- ElastiCache `cache.t4g.micro`: similar small-instance pricing; verify
  current Free-Tier terms.
- ECS Fargate tasks: billed per vCPU-second + GB-second while running; the
  default `api_desired_count = 1` / `worker_desired_count = 1` keep this
  minimal but non-zero.
- S3, ECR, Secrets Manager, CloudWatch: usage-based, generally cheap at low
  volume but not exactly zero.

**Net: leaving this applied 24/7 costs real money even with zero users.**
Destroy (`terraform destroy`, also a deliberate human action) or scale
resources down (e.g. `desired_count = 0`) if this environment isn't in
active use.

## Structure

```
infra/terraform/
  main.tf          root module wiring - calls every module below
  variables.tf     root input variables (sane defaults, all overridable via
                    a *.tfvars file that is NOT committed)
  outputs.tf        root outputs (ALB DNS name, RDS/Redis endpoints, etc.)
  README.md        this file
  modules/
    vpc/            VPC, subnets, NAT, routing
    rds/            RDS Postgres + PostGIS-capable engine
    redis/          ElastiCache Redis replication group
    sqs/             SQS task queue + DLQ
    ecs/            ECS Fargate cluster, ALB, task defs/services for api+worker
    s3/              Exports + raw-data buckets
    ecr/             Container image repositories
    secrets/         Secrets Manager entries
    cloudwatch/      Log group, alarms, SNS topic
```

## Not yet wired up (intentionally left as follow-up work, not blockers to
scaffolding)

- Remote state backend (commented out in `main.tf` - needs a real AWS
  account + a bootstrap bucket/table created once, likely by hand or via a
  tiny separate bootstrap Terraform config).
- A real domain name + ACM certificate + HTTPS listener on the ALB (currently
  HTTP-only on port 80 - fine for `plan`-time review, not for real traffic).
- CI/CD wiring that builds+pushes images to the ECR repos and updates the ECS
  task definitions on deploy (this repo's `.github/workflows/ci.yml` only
  lints/tests; it does not deploy anything).
- Fine-grained IAM policy scoping (the worker task role currently allows SQS
  actions on `"*"` as a placeholder - narrow this to the specific queue ARN
  from `module.sqs.task_queue_arn` before any real deployment).
