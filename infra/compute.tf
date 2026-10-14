# One small server runs the API and the extraction worker (backend/Dockerfile) in Docker.
# It accepts connections only from inside the VPC: CloudFront reaches it privately (VPC origin, cdn.tf).
# It keeps a public IP for outbound traffic only (Groq API, ECR, Secrets Manager, SSM).

data "aws_ssm_parameter" "al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

resource "aws_security_group" "app" {
  name        = "${var.name}-app"
  description = "Healthfolio API: port 8000 from inside the VPC only (CloudFront VPC origin)"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "CloudFront VPC origin (its network interface is inside the VPC)"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.default.cidr_block]
  }

  egress {
    description = "Outbound: Groq, ECR, AWS APIs, the database"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Non-secret settings, read by the server at start. The two secrets (/healthfolio/groq_api_key and
# /healthfolio/jwt_secret) are created by you as SecureString parameters, never by Terraform.
resource "aws_ssm_parameter" "site_url" {
  name  = "/${var.name}/site_url"
  type  = "String"
  value = "https://${aws_cloudfront_distribution.site.domain_name}"
}

resource "aws_instance" "app" {
  ami                  = data.aws_ssm_parameter.al2023.value
  instance_type        = var.instance_type
  subnet_id            = data.aws_subnets.default.ids[0]
  iam_instance_profile = aws_iam_instance_profile.app.name

  vpc_security_group_ids      = [aws_security_group.app.id]
  associate_public_ip_address = true # outbound only; no inbound rule allows the internet

  metadata_options {
    http_tokens                 = "required" # IMDSv2 only
    http_put_response_hop_limit = 2          # lets the Docker container use the instance role
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = 20
    encrypted   = true
  }

  user_data = templatefile("${path.module}/server-setup.sh", {
    region        = var.region
    name          = var.name
    image         = "${aws_ecr_repository.api.repository_url}:latest"
    db_host       = aws_db_instance.db.address
    db_secret_arn = aws_db_instance.db.master_user_secret[0].secret_arn
    bucket        = aws_s3_bucket.documents.bucket
  })
  user_data_replace_on_change = true

  lifecycle {
    ignore_changes = [ami] # a newer Amazon Linux image should not replace the running server
  }

  tags = {
    Name = "${var.name}-api"
  }
}
