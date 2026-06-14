terraform {
  required_version = ">= 1.3.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    http = {
      source  = "hashicorp/http"
      version = "~> 3.0"
    }
  }
}

provider "aws" {
  region = var.region
}

# --- Data Sources globais ---

data "aws_caller_identity" "current" {}

# IP Público local para restringir o acesso no SG
data "http" "myip" {
  url = "https://api.ipify.org"
}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnet" "glue_subnet" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
  filter {
    name   = "defaultForAz"
    values = ["true"]
  }
  filter {
    name   = "availabilityZone"
    values = ["${var.region}a"]
  }
}
