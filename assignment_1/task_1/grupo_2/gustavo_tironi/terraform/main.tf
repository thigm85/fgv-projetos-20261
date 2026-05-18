terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.4"
    }
  }
}

#==========================
# Credenciais e região
#==========================

provider "aws" {
  region  = "us-east-1"
  profile = "projetos"
}

#==========================
# Variáveis (valores em terraform.tfvars)
#==========================

variable "senha_master" {
  type        = string
  description = "Senha do usuário admin do MySQL. Não use @, / nem aspas (regra do RDS)."
  sensitive   = true
}

variable "meu_ip" {
  type        = string
  description = "Seu IP público para liberar a porta 3306 (só você). Ex: 203.0.113.44 — use curl -s https://checkip.amazonaws.com"
}

#==========================
# VPC e subnets (default da conta)
#==========================

# VPC padrão da região (não cria recurso novo).
data "aws_vpc" "default" {
  default = true
}

# Todas as subnets dessa VPC (RDS exige um grupo com várias AZs).
data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# Nomeia esse conjunto de subnets para o RDS anexar.
resource "aws_db_subnet_group" "lab" {
  name       = "lab-mysql-subnets"
  subnet_ids = data.aws_subnets.default.ids
}

#==========================
# Firewall (security group só com seu IP na 3306)
#==========================

resource "aws_security_group" "mysql" {
  name        = "lab-mysql-sg"
  description = "Libera MySQL (3306) so para o meu IP"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    from_port   = 3306
    to_port     = 3306
    protocol    = "tcp"
    cidr_blocks = ["${var.meu_ip}/32"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

#==========================
# Instância RDS MySQL
#==========================

resource "aws_db_instance" "mysql" {
  identifier = "lab-mysql-classicmodels"

  engine            = "mysql"
  engine_version    = "8.4.7"
  instance_class    = "db.t3.micro"
  allocated_storage = 20
  storage_type      = "gp3"
  # ↑ versão / classe / disco: ajuste livre para lab (console costuma sugerir versão e mais GB).

  username = "admin"
  password = var.senha_master
  # ↑ senha vem do terraform.tfvars (não commitar).

  db_subnet_group_name   = aws_db_subnet_group.lab.name
  vpc_security_group_ids = [aws_security_group.mysql.id]
  # ↑ subnet group + SG definidos acima neste arquivo.

  publicly_accessible = true
  # ↑ laboratório: acesso do seu PC pela internet.

  skip_final_snapshot = true
  # ↑ destroy sem snapshot final (mais simples para lab).
}

#==========================
# Saídas no terminal após apply (terraform output)
#==========================

output "endpoint" {
  description = "Host (copie para o cliente MySQL)"
  value       = aws_db_instance.mysql.address
}

output "porta" {
  value = aws_db_instance.mysql.port
}

output "usuario" {
  value = "admin"
}

#==========================
# Grava ../src/.env (host, porta, usuário, senha)
#==========================

resource "local_file" "rds_env" {
  filename        = "${path.module}/../src/.env"
  file_permission = "0600"
  content         = <<-EOT
MYSQL_HOST=${aws_db_instance.mysql.address}
MYSQL_PORT=${aws_db_instance.mysql.port}
MYSQL_USER=admin
MYSQL_PASSWORD=${var.senha_master}
EOT
}
