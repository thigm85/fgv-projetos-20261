terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.92"
    }
    http = {
      source  = "hashicorp/http"
      version = "~> 3.0"
    }
  }

  required_version = ">= 1.2"
}
