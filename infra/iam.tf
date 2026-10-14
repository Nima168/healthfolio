# The app's identity for S3. Lightsail containers cannot assume IAM roles, so the app uses an access key
# for this user. The key is created by you in the console and entered in the Lightsail deployment:
# it is never stored in Terraform state.
resource "aws_iam_user" "app" {
  name = "${var.name}-app"
}

resource "aws_iam_user_policy" "app_documents" {
  name = "documents-bucket-only"
  user = aws_iam_user.app.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
      Resource = "${aws_s3_bucket.documents.arn}/*"
    }]
  })
}
