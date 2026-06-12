terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  backend "local" {
    path = "terraform.tfstate"
  }
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile
  default_tags {
    tags = var.tags
  }
}

# Create S3 bucket for Athena query results if it doesn't exist
resource "aws_s3_bucket" "athena_output" {
  bucket = var.athena_output_bucket != "" ? var.athena_output_bucket : "${var.project_name}-athena-output-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_versioning" "athena_output" {
  bucket = aws_s3_bucket.athena_output.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "athena_output" {
  bucket = aws_s3_bucket.athena_output.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "athena_output" {
  bucket                  = aws_s3_bucket.athena_output.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Data source to get current AWS account ID
data "aws_caller_identity" "current" {}

# Generate the configuration file for the Jupyter notebook
resource "local_file" "notebook_config" {
  filename = "${path.module}/config.py"
  
  content = <<-EOT
# Auto-generated Task 3 Configuration
# Generated from Terraform - DO NOT EDIT MANUALLY
# Regenerate with: terraform apply

# Glue Catalog database name with star schema tables
GLUE_DATABASE = "${var.glue_database_name}"

# S3 bucket for Athena query results
ATHENA_OUTPUT_BUCKET = "${aws_s3_bucket.athena_output.id}"

# Full S3 path for Athena query results
S3_OUTPUT = "s3://${aws_s3_bucket.athena_output.id}/${var.athena_output_prefix}"

# AWS region
AWS_REGION = "${var.aws_region}"

# Configuration metadata
TF_BACKEND = "local"
CONFIG_VERSION = "1.0"
CONFIGURED = True
EOT
}

# Output the configuration for the Jupyter notebook
output "glue_database_name" {
  description = "Name of the Glue Catalog database with the star schema tables"
  value       = var.glue_database_name
}

output "athena_output_bucket" {
  description = "S3 bucket where Athena stores query results"
  value       = aws_s3_bucket.athena_output.id
}

output "athena_output_path" {
  description = "S3 path for Athena query results"
  value       = "s3://${aws_s3_bucket.athena_output.id}/${var.athena_output_prefix}"
}

output "aws_region" {
  description = "AWS region for the notebook configuration"
  value       = var.aws_region
}

output "config_file" {
  description = "Path to the generated configuration file for the notebook"
  value       = local_file.notebook_config.filename
  depends_on  = [local_file.notebook_config]
}