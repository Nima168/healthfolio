data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# PostgreSQL is reachable only from Lightsail's network (its VPC is peered with the default VPC:
# `aws lightsail peer-vpc`, done once; see README.md).
resource "aws_security_group" "db" {
  name        = "${var.name}-db"
  description = "Healthfolio database: PostgreSQL from Lightsail only"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "Lightsail peered VPC"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["172.26.0.0/16"]
  }
}

resource "aws_db_subnet_group" "db" {
  name       = "${var.name}-db"
  subnet_ids = data.aws_subnets.default.ids
}

resource "aws_db_instance" "db" {
  identifier     = "${var.name}-db"
  engine         = "postgres"
  engine_version = "16"
  instance_class = var.db_instance_class

  allocated_storage = 20
  storage_type      = "gp3"
  storage_encrypted = true

  db_name  = "healthfolio"
  username = "healthfolio"
  # AWS generates the password and keeps it in Secrets Manager; it never enters Terraform state.
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.db.name
  vpc_security_group_ids = [aws_security_group.db.id]
  publicly_accessible    = false
  multi_az               = false

  backup_retention_period    = 1
  auto_minor_version_upgrade = true
  deletion_protection        = true
  skip_final_snapshot        = false
  final_snapshot_identifier  = "${var.name}-db-final"
}
