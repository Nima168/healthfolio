locals {
  account_id = data.aws_caller_identity.current.account_id
}

# Uploaded medical documents: private, encrypted, never public.
resource "aws_s3_bucket" "documents" {
  bucket = "${var.name}-documents-${local.account_id}"
}

# The built website; the server copies it in when the web container starts.
resource "aws_s3_bucket" "site" {
  bucket = "${var.name}-site-${local.account_id}"
}

resource "aws_s3_bucket_public_access_block" "private" {
  for_each = { documents = aws_s3_bucket.documents.id, site = aws_s3_bucket.site.id }

  bucket                  = each.value
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "encrypted" {
  for_each = { documents = aws_s3_bucket.documents.id, site = aws_s3_bucket.site.id }

  bucket = each.value
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_ownership_controls" "owner" {
  for_each = { documents = aws_s3_bucket.documents.id, site = aws_s3_bucket.site.id }

  bucket = each.value
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}
