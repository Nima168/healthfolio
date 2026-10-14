resource "aws_ecr_repository" "api" {
  name = "${var.name}-api"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "keep the last 5 images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 5 }
      action       = { type = "expire" }
    }]
  })
}

# Runs the API and the extraction worker (backend/Dockerfile). The deployment itself (image and
# environment, including secrets) is created in the Lightsail console, so secrets stay out of state.
resource "aws_lightsail_container_service" "api" {
  name  = "${var.name}-api"
  power = var.container_power
  scale = 1

  private_registry_access {
    ecr_image_puller_role {
      is_active = true
    }
  }
}

# Lets the container service pull images from the private ECR repository.
resource "aws_ecr_repository_policy" "lightsail_pull" {
  repository = aws_ecr_repository.api.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "LightsailPull"
      Effect    = "Allow"
      Principal = { AWS = aws_lightsail_container_service.api.private_registry_access[0].ecr_image_puller_role[0].principal_arn }
      Action    = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
    }]
  })
}
