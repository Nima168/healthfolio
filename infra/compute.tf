# One small server runs two containers on a private Docker network:
# - Caddy: HTTPS (Let's Encrypt, renewed automatically), the website files, and /api/* to the app;
# - the API and extraction worker (backend/Dockerfile), reachable only by Caddy.
# The address is https://<elastic-ip-with-dashes>.sslip.io (free wildcard DNS; no domain needed).

data "aws_ssm_parameter" "al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

resource "aws_security_group" "app" {
  name_prefix = "${var.name}-app-"
  description = "Healthfolio server: HTTPS (and HTTP for certificate checks and redirects)"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTP: Lets Encrypt checks, redirect to HTTPS"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Outbound: Groq, ECR, AWS APIs, the database"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  lifecycle {
    create_before_destroy = true # replaced safely while the server and database still use it
  }
}

# Non-secret settings, read by the server at start. The two secrets (/healthfolio/groq_api_key and
# /healthfolio/jwt_secret) are created by you as SecureString parameters, never by Terraform.
resource "aws_ssm_parameter" "site_url" {
  name  = "/${var.name}/site_url"
  type  = "String"
  value = "https://${local.site_host}"
}

# A fixed public address: the site's hostname (and its certificate) stays the same across restarts.
resource "aws_eip" "app" {
  domain   = "vpc"
  instance = aws_instance.app.id
}

locals {
  site_host = "${replace(aws_eip.app.public_ip, ".", "-")}.sslip.io"
}

resource "aws_instance" "app" {
  ami                  = data.aws_ssm_parameter.al2023.value
  instance_type        = var.instance_type
  subnet_id            = data.aws_subnets.default.ids[0]
  iam_instance_profile = aws_iam_instance_profile.app.name

  vpc_security_group_ids      = [aws_security_group.app.id]
  associate_public_ip_address = true

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
    site_bucket   = aws_s3_bucket.site.bucket
  })
  user_data_replace_on_change = true

  lifecycle {
    ignore_changes = [ami] # a newer Amazon Linux image should not replace the running server
  }

  tags = {
    Name = "${var.name}-api"
  }
}
