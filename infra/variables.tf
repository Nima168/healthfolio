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

variable "container_power" {
  description = "Lightsail container size (micro: 0.25 vCPU, 1 GB)."
  type        = string
  default     = "micro"
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

variable "alert_email" {
  description = "Where budget alerts are sent (set in terraform.tfvars, which is not committed)."
  type        = string
}
