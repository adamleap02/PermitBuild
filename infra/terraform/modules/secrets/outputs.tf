output "db_password_secret_id" {
  value = aws_secretsmanager_secret.db_password.id
}

output "db_password_secret_arn" {
  value = aws_secretsmanager_secret.db_password.arn
}

output "database_url_secret_arn" {
  value = aws_secretsmanager_secret.database_url.arn
}

output "third_party_api_keys_secret_arn" {
  value = aws_secretsmanager_secret.third_party_api_keys.arn
}
