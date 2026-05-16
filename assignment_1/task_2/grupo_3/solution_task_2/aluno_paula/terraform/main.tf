provider "aws" {
  region = var.region
}

# Identidade atual usada para compor nomes únicos e políticas.
data "aws_caller_identity" "current" {}

locals {
  # Script ETL enviado para o bucket do pipeline.
  glue_script_key = "scripts/glue_etl_star_schema.py"
  # Nome padrão do bucket quando não informado via variável.
  etl_bucket_name = var.etl_bucket_name != "" ? var.etl_bucket_name : "classicmodels-etl-${data.aws_caller_identity.current.account_id}-${var.region}"
  # Reusa role existente em labs restritos, ou cria uma nova quando possível.
  glue_role_arn   = var.existing_glue_role_arn != "" ? var.existing_glue_role_arn : aws_iam_role.glue_role[0].arn
}

resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "classicmodels-vpc"
  }
}

resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "classicmodels-igw"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }

  tags = {
    Name = "classicmodels-public-rt"
  }
}

resource "aws_vpc_endpoint" "s3_gateway" {
  # Necessário para o Glue em VPC acessar S3 sem NAT.
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.public.id]

  tags = {
    Name = "classicmodels-s3-endpoint"
  }
}

resource "aws_subnet" "subnet_a" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = "${var.region}a"
  map_public_ip_on_launch = true

  tags = {
    Name = "classicmodels-subnet-a"
  }
}

resource "aws_subnet" "subnet_b" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.2.0/24"
  availability_zone       = "${var.region}b"
  map_public_ip_on_launch = true

  tags = {
    Name = "classicmodels-subnet-b"
  }
}

resource "aws_route_table_association" "subnet_a_public" {
  subnet_id      = aws_subnet.subnet_a.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "subnet_b_public" {
  subnet_id      = aws_subnet.subnet_b.id
  route_table_id = aws_route_table.public.id
}

resource "aws_db_subnet_group" "default" {
  name       = "rds-subnet-group"
  subnet_ids = [aws_subnet.subnet_a.id, aws_subnet.subnet_b.id]

  tags = {
    Name = "classicmodels-db-subnet-group"
  }
}

resource "aws_security_group" "rds_sg" {
  name   = "classicmodels-rds-sg"
  vpc_id = aws_vpc.main.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "classicmodels-rds-sg"
  }
}

resource "aws_security_group" "glue_sg" {
  name   = "classicmodels-glue-sg"
  vpc_id = aws_vpc.main.id

  ingress {
    # Exigência do Glue em VPC: tráfego interno liberado no próprio SG.
    description = "Required by Glue in VPC: allow all traffic within the same SG"
    from_port   = 0
    to_port     = 65535
    protocol    = "tcp"
    self        = true
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "classicmodels-glue-sg"
  }
}

resource "aws_security_group_rule" "rds_from_glue" {
  # Permite o Glue conectar no MySQL do RDS.
  type                     = "ingress"
  from_port                = 3306
  to_port                  = 3306
  protocol                 = "tcp"
  security_group_id        = aws_security_group.rds_sg.id
  source_security_group_id = aws_security_group.glue_sg.id
  description              = "Glue job access to MySQL"
}

resource "aws_security_group_rule" "rds_from_lab_ip" {
  # Regra opcional para acesso manual ao banco a partir do IP do laboratório.
  count             = var.manage_lab_ip_ingress_rule ? 1 : 0
  type              = "ingress"
  from_port         = 3306
  to_port           = 3306
  protocol          = "tcp"
  security_group_id = aws_security_group.rds_sg.id
  cidr_blocks       = [var.allowed_cidr]
  description       = "Lab access restricted to one trusted /32 IP"
}

resource "aws_db_instance" "mysql" {
  identifier        = var.db_instance_identifier
  engine            = "mysql"
  engine_version    = "8.0"
  instance_class    = var.instance_class
  allocated_storage = 20
  storage_type      = "gp2"

  db_name  = var.db_name
  username = var.db_username
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.default.name
  vpc_security_group_ids = [aws_security_group.rds_sg.id]
  publicly_accessible    = var.publicly_accessible
  deletion_protection    = false

  skip_final_snapshot = true

  tags = {
    Name = "classicmodels-db"
  }
}

resource "aws_s3_bucket" "etl" {
  # Bucket de script, temporários e datasets curados em Parquet.
  bucket = local.etl_bucket_name

  tags = {
    Name = local.etl_bucket_name
  }
}

resource "aws_s3_bucket_versioning" "etl" {
  bucket = aws_s3_bucket.etl.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "etl" {
  bucket = aws_s3_bucket.etl.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_object" "glue_script" {
  # Publica o script do Glue no S3 para execução do job.
  bucket = aws_s3_bucket.etl.id
  key    = local.glue_script_key
  source = "${path.module}/../scripts/glue_etl_star_schema.py"
  etag   = filemd5("${path.module}/../scripts/glue_etl_star_schema.py")
}

resource "aws_iam_role" "glue_role" {
  # Em alguns labs não há permissão de IAM; por isso este recurso é condicional.
  count = var.existing_glue_role_arn == "" ? 1 : 0
  name = "classicmodels-glue-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "glue.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "glue_service_role" {
  count      = var.existing_glue_role_arn == "" ? 1 : 0
  role       = aws_iam_role.glue_role[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

resource "aws_iam_role_policy" "glue_inline" {
  count = var.existing_glue_role_arn == "" ? 1 : 0
  name = "classicmodels-glue-inline-policy"
  role = aws_iam_role.glue_role[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.etl.arn,
          "${aws_s3_bucket.etl.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = [
          "arn:aws:logs:${var.region}:${data.aws_caller_identity.current.account_id}:log-group:/aws-glue/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:CreateNetworkInterface",
          "ec2:DeleteNetworkInterface",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DescribeSubnets",
          "ec2:DescribeSecurityGroups",
          "ec2:DescribeRouteTables",
          "ec2:DescribeVpcEndpoints",
          "ec2:DescribeVpcAttribute",
          "ec2:DescribeVpcs"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_glue_connection" "rds_mysql" {
  # Conexão JDBC entre Glue e RDS dentro da VPC.
  name = var.glue_connection_name

  connection_properties = {
    JDBC_CONNECTION_URL = "jdbc:mysql://${aws_db_instance.mysql.address}:${aws_db_instance.mysql.port}/${var.db_name}"
    USERNAME            = var.db_username
    PASSWORD            = var.db_password
  }

  physical_connection_requirements {
    availability_zone      = aws_subnet.subnet_a.availability_zone
    security_group_id_list = [aws_security_group.glue_sg.id]
    subnet_id              = aws_subnet.subnet_a.id
  }
}

resource "aws_glue_job" "classicmodels_etl" {
  # Job responsável por extrair, transformar (star schema) e carregar no S3.
  name              = var.glue_job_name
  role_arn          = local.glue_role_arn
  glue_version      = "4.0"
  worker_type       = "G.1X"
  number_of_workers = var.glue_workers
  timeout           = 20

  command {
    script_location = "s3://${aws_s3_bucket.etl.id}/${aws_s3_object.glue_script.key}"
    python_version  = "3"
  }

  connections = [aws_glue_connection.rds_mysql.name]

  default_arguments = {
    # Parâmetros consumidos pelo script glue_etl_star_schema.py
    "--job-language"                     = "python"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--db_name"                          = var.db_name
    "--rds_host"                         = aws_db_instance.mysql.address
    "--rds_port"                         = tostring(aws_db_instance.mysql.port)
    "--rds_user"                         = var.db_username
    "--rds_password"                     = var.db_password
    "--output_path"                      = "s3://${aws_s3_bucket.etl.id}/curated"
    "--TempDir"                          = "s3://${aws_s3_bucket.etl.id}/tmp"
  }

  depends_on = [
    aws_s3_object.glue_script,
    aws_glue_connection.rds_mysql
  ]
}
