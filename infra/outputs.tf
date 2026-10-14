output "site_url" {
  description = "The app's address (site and API)."
  value       = "https://${local.site_host}"
}

output "site_bucket" {
  value = aws_s3_bucket.site.bucket
}

output "documents_bucket" {
  value = aws_s3_bucket.documents.bucket
}

output "ecr_repository_url" {
  value = aws_ecr_repository.api.repository_url
}

output "api_instance_id" {
  description = "The API server (connect with Session Manager; no SSH)."
  value       = aws_instance.app.id
}

output "db_endpoint" {
  value = aws_db_instance.db.address
}

output "db_password_secret_arn" {
  description = "Secrets Manager secret holding the database password (read it in the console)."
  value       = aws_db_instance.db.master_user_secret[0].secret_arn
}
