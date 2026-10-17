# Deployment from GitHub Actions (.github/workflows/deploy.yml) without AWS keys.
# GitHub proves each run's identity with OIDC; only runs of this repository's "production" environment can
# assume the role, and the role can only push the API image, publish the website, and run the two fixed
# restart commands below (never an arbitrary command on the server).

# The subject GitHub puts in each run's token. This repository uses GitHub's immutable subject format
# (owner@owner-id/name@repository-id), so a renamed or re-created repository cannot reuse the trust.
# Read it with: gh api repos/<owner>/<name>/actions/oidc/customization/sub  (sub_claim_prefix)
variable "github_subject_prefix" {
  description = "OIDC subject prefix of the GitHub repository allowed to deploy."
  type        = string
  default     = "repo:Nima168@108936671/healthfolio@1418697407"
}

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1", "1c58a3a8518e8759bf075b76b750d4f2df264fcd"]
}

resource "aws_iam_role" "github_deploy" {
  name = "${var.name}-github-deploy"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.github.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = "${var.github_subject_prefix}:environment:production"
        }
      }
    }]
  })
}

# Fixed commands GitHub may run on the server (the same steps as a manual release, infra/README.md).
resource "aws_ssm_document" "restart_api" {
  name          = "${var.name}-restart-api"
  document_type = "Command"
  content = jsonencode({
    schemaVersion = "2.2"
    description   = "Restart the API container: pulls the latest image and runs database migrations."
    mainSteps = [{
      action = "aws:runShellScript"
      name   = "restartApi"
      inputs = { runCommand = ["systemctl restart healthfolio", "sleep 45", "systemctl is-active healthfolio"] }
    }]
  })
}

resource "aws_ssm_document" "restart_web" {
  name          = "${var.name}-restart-web"
  document_type = "Command"
  content = jsonencode({
    schemaVersion = "2.2"
    description   = "Restart Caddy, which syncs the website files from S3."
    mainSteps = [{
      action = "aws:runShellScript"
      name   = "restartWeb"
      inputs = { runCommand = ["systemctl restart healthfolio-web", "sleep 15", "systemctl is-active healthfolio-web"] }
    }]
  })
}

resource "aws_iam_role_policy" "github_deploy" {
  name = "healthfolio-github-deploy"
  role = aws_iam_role.github_deploy.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "EcrLogin"
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        # Signed-in pulls of the base image from ECR Public (anonymous pulls from shared GitHub runners hit
        # "429 Too Many Requests – Data limit exceeded"). Read-only: a login token, nothing else.
        Sid      = "PullBaseImageSignedIn"
        Effect   = "Allow"
        Action   = ["ecr-public:GetAuthorizationToken", "sts:GetServiceBearerToken"]
        Resource = "*"
      },
      {
        Sid    = "PushApiImage"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability", "ecr:BatchGetImage", "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:PutImage",
        ]
        Resource = aws_ecr_repository.api.arn
      },
      {
        Sid      = "PublishWebsite"
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = aws_s3_bucket.site.arn
      },
      {
        Sid      = "PublishWebsiteFiles"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = "${aws_s3_bucket.site.arn}/*"
      },
      {
        Sid    = "RunFixedRestartCommands"
        Effect = "Allow"
        Action = "ssm:SendCommand"
        Resource = [
          aws_instance.app.arn,
          aws_ssm_document.restart_api.arn,
          aws_ssm_document.restart_web.arn,
        ]
      },
      {
        Sid      = "ReadCommandResults"
        Effect   = "Allow"
        Action   = "ssm:GetCommandInvocation"
        Resource = "*"
      },
    ]
  })
}

output "github_deploy_role_arn" {
  description = "Set as the AWS_DEPLOY_ROLE_ARN repository variable in GitHub."
  value       = aws_iam_role.github_deploy.arn
}
