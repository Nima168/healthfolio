terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
  }

  # State lives in its own private, versioned bucket (created once; see README.md).
  backend "s3" {
    bucket  = "healthfolio-tfstate-543175219403"
    key     = "healthfolio/terraform.tfstate"
    region  = "ap-south-1"
    encrypt = true
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "healthfolio"
      ManagedBy = "terraform"
    }
  }
}

# The account the resources are created in (used in bucket names).
data "aws_caller_identity" "current" {}
