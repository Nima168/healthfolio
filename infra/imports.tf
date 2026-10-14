# Resources created with the AWS CLI before this Terraform setup; adopted instead of re-created.
import {
  to = aws_s3_bucket.documents
  id = "healthfolio-documents-543175219403"
}

import {
  to = aws_s3_bucket.site
  id = "healthfolio-site-543175219403"
}

import {
  to = aws_ecr_repository.api
  id = "healthfolio-api"
}

import {
  to = aws_ecr_lifecycle_policy.api
  id = "healthfolio-api"
}

import {
  to = aws_security_group.db
  id = "sg-04cc3caaa9367c33d"
}
