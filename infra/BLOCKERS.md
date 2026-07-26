# infra/ - Blockers & things a human needs to decide

Status as of 2026-07-25. This file should be re-checked/updated as items get
resolved - it is not automatically kept in sync.

## 1. Docker is not installed on this machine

`infra/docker-compose.yml` (Postgres+PostGIS, Redis) has been written and is
believed correct, but has **not been run or verified** here because Docker
itself isn't installed.

- Docker Desktop is free for personal use / small business (check current
  Docker Inc. licensing terms for your situation): https://www.docker.com/products/docker-desktop/
- **Windows requirement:** Docker Desktop on Windows uses the WSL2 backend by
  default. Enabling WSL2 (`wsl --install` or turning on the "Windows
  Subsystem for Linux" + "Virtual Machine Platform" optional Windows
  features) typically requires **administrator privileges and a machine
  restart** - this was **not** done automatically as part of this task since
  it needs a human at the keyboard to approve the elevation/restart.
- Until Docker is installed, the backend should default to local SQLite
  (already noted in `infra/docker-compose.yml` and the top-level README) so
  local development isn't blocked on this.
- **Action needed:** a human installs Docker Desktop, enables WSL2 if
  prompted, restarts, then runs `docker compose -f infra/docker-compose.yml --env-file infra/.env up -d`
  to bring up Postgres/Redis and confirm the healthchecks pass.

## 2. Terraform CLI is not installed

`infra/terraform/` has been written (VPC, RDS, ECS Fargate, S3, SQS,
ElastiCache Redis, Secrets Manager, CloudWatch, ECR modules) but **not run**
- `terraform init`/`plan`/`apply` were never executed, and the Terraform CLI
  itself isn't installed here.

- Terraform CLI is free to install: https://developer.hashicorp.com/terraform/install
  (on Windows: `winget install Hashicorp.Terraform`, or download the binary
  directly).
- **Action needed:** once installed, a human runs `terraform init && terraform plan`
  from `infra/terraform/` to review the full set of resources and estimated
  cost - see `infra/terraform/README.md` for the exact command and the list
  of preconditions before ever running `terraform apply`.

## 3. No AWS account / billing set up yet

There is no AWS account tied to this project, and none was created as part
of this task. **Creating an AWS account and attaching a payment method is
explicitly a human/business decision** - not something that should be
automated by an agent - because it establishes a real billing relationship.

- **Action needed:** a human (project owner) creates the AWS account,
  attaches billing, and ideally sets up AWS Budgets/billing alerts *before*
  anyone runs `terraform apply` against it. See `infra/terraform/README.md`
  for the pre-apply checklist.
- Until this exists, `infra/terraform/` remains a design-complete but
  entirely unapplied module set.

## 4. Paid third-party services needed eventually (not now)

These are fine to defer, but will need a paid plan once the product has real
users/scale - flagging now so they aren't a surprise later:

- **Production map tile provider** - a free/dev-tier provider (e.g.
  OpenStreetMap tiles, or a generous free tier from Mapbox/MapTiler/Stadia
  Maps) is fine for development, but any provider's free tier has a request
  volume cap; a paid plan will be needed once the frontend's property-map
  views get real traffic.
- **Email/SMS provider for alerts** (e.g. permit-status alerts, ingestion
  failure notifications) - services like SES/SNS, SendGrid, Twilio, Postmark
  all have free/sandbox tiers suitable for development, but production
  sending (especially SMS, and email at volume, and getting out of any
  "sandbox"/verified-recipients mode) requires a paid plan and often an
  approved sender identity/domain.
- Both of the above are referenced as placeholder entries in
  `infra/terraform/modules/secrets` (`third_party_api_keys` secret) so the
  eventual wiring has a home, but no real provider account or key has been
  created.

## Summary for a human to action, in order

1. Install Docker Desktop (needs admin + restart for WSL2) -> bring up
   `infra/docker-compose.yml` -> confirm healthchecks pass.
2. Install the Terraform CLI -> run `terraform init && terraform plan` in
   `infra/terraform/` (read-only, safe) -> review the resource list and cost.
3. Decide, as a business, whether/when to open an AWS account with billing.
4. Only after 1-3: consider `terraform apply` (never automated).
5. Pick and budget for a production map tile provider and an email/SMS
   provider when getting close to real users.
