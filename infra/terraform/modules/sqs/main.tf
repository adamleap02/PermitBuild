# modules/sqs - task queue for ingestion jobs.
#
# ElastiCache Redis (modules/redis) is the primary Celery broker + result
# backend for this deployment. This SQS queue is provided as an
# alternative/supplementary queue for specific long-running or bursty
# ingestion jobs (e.g. large bulk permit-file backfills, jurisdiction
# connector reruns) where SQS's durability, native retry/backoff, and
# decoupling from the Redis broker are preferable. The backend can pick
# either broker per task/queue via Celery's routing config.

resource "aws_sqs_queue" "dlq" {
  name                      = "${var.name_prefix}-tasks-dlq"
  message_retention_seconds = 1209600 # 14 days
}

resource "aws_sqs_queue" "tasks" {
  name                       = "${var.name_prefix}-tasks"
  visibility_timeout_seconds = 300
  message_retention_seconds  = 345600 # 4 days

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 5
  })
}
