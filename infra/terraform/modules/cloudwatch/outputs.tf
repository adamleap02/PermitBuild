output "ecs_log_group_name" {
  value = aws_cloudwatch_log_group.ecs.name
}

output "alarms_topic_arn" {
  value = aws_sns_topic.alarms.arn
}
