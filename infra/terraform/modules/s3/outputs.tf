output "exports_bucket_name" {
  value = aws_s3_bucket.exports.bucket
}

output "exports_bucket_arn" {
  value = aws_s3_bucket.exports.arn
}

output "raw_data_bucket_name" {
  value = aws_s3_bucket.raw_data.bucket
}

output "raw_data_bucket_arn" {
  value = aws_s3_bucket.raw_data.arn
}
