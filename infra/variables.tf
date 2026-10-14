variable "region" {
  description = "AWS region for everything except global services."
  type        = string
  default     = "ap-south-1"
}

variable "name" {
  description = "Prefix for resource names."
  type        = string
  default     = "healthfolio"
}

variable "instance_type" {
  description = "API server size (t3.small: 2 vCPU, 2 GB; enough for OCR)."
  type        = string
  default     = "t3.small"
}

variable "db_instance_class" {
  description = "RDS instance size."
  type        = string
  default     = "db.t4g.micro"
}

variable "budget_limit_usd" {
  description = "Monthly cost at which an alert email is sent."
  type        = number
  default     = 20
}

variable "email_backend" {
  description = "\"ses\" sends password-reset emails; \"disabled\" turns password reset off (the page says so)."
  type        = string
  default     = "disabled" # until SES production access is granted (sandbox delivers only to verified addresses)

  validation {
    condition     = contains(["ses", "disabled"], var.email_backend)
    error_message = "email_backend must be \"ses\" or \"disabled\"."
  }
}

variable "sender_email" {
  description = "Address password-reset emails are sent from; verified in SES (set in terraform.tfvars)."
  type        = string
}

variable "alert_email" {
  description = "Where budget alerts are sent (set in terraform.tfvars, which is not committed)."
  type        = string
}
