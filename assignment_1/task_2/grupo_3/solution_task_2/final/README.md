# Task 1 e Task 2 - Pipeline de Dados (RDS + Glue + S3)

Guia completo para executar:
- Task 1: provisionar RDS, carregar `classicmodels` e validar.
- Task 2: rodar ETL no Glue, transformar para star schema e gravar Parquet no S3.

## Estrutura

```text
aluno_x/
|- terraform/
|  |- main.tf
|  |- variables.tf
|  |- outputs.tf
|  |- terraform.tfvars
|- scripts/
|  |- 01_provision_rds.py
|  |- 02_load_data.py
|  |- 03_validate.py
|  |- glue_etl_star_schema.py
|- requirements.txt
```

## Pre-requisitos

- Conda env: `aws-data-pipeline`
- Python 3.10+
- Terraform
- AWS CLI
- Credenciais AWS ativas no laboratorio

## 0) Setup inicial

```powershell
conda activate aws-data-pipeline
cd "projetos-20261\assignment_1\task_2\grupo_3\solution_task_2\aluno_x"
pip install -r requirements.txt
```

Se faltar Terraform:

```powershell
conda install -c conda-forge terraform -y
terraform -version
```

Se faltar AWS CLI:

```powershell
conda install -c conda-forge awscli -y
aws --version
```

Definir regiao:

```powershell
$env:AWS_REGION="us-east-1"
$env:AWS_DEFAULT_REGION="us-east-1"
```

## 1) Task 1 - RDS + carga + validacao

### 1.1 Configurar `terraform.tfvars`

Na pasta `terraform`, use:

```hcl
region                     = "us-east-1"
db_instance_identifier     = "classicmodels-db"
db_name                    = "classicmodels"
db_username                = "x"
db_password                = "SUA_SENHA_FORTE"
instance_class             = "db.t3.micro"
allowed_cidr               = "SEU_IP_PUBLICO/32"
publicly_accessible        = true
existing_glue_role_arn     = "arn:aws:iam::SEU_ACCOUNT_ID:role/LabRole"
manage_lab_ip_ingress_rule = false
```

Notas:
- `db_password` precisa ter 8+ caracteres.
- `allowed_cidr` deve ser `/32`.
- `manage_lab_ip_ingress_rule = false` evita erro de regra duplicada em labs restritos.

### 1.2 Provisionar com Terraform

```powershell
cd terraform
terraform init
terraform validate
terraform plan
terraform apply -auto-approve
```

### 1.3 Exportar variaveis de conexao

```powershell
$env:DB_HOST = terraform output -raw rds_endpoint
$env:DB_PORT = terraform output -raw rds_port
$env:DB_USER = "x"
$env:DB_PASSWORD = "SUA_SENHA_FORTE"
$env:DB_NAME = "classicmodels"
$env:DB_INSTANCE_IDENTIFIER = "classicmodels-db"
```

### 1.4 Executar scripts da Task 1

```powershell
cd ..\scripts
python .\01_provision_rds.py
python .\02_load_data.py
python .\03_validate.py
```

### 1.5 Resultado esperado da Task 1

- Script 01 mostra status `available`.
- Script 02 conclui com sucesso e comandos executados.
- Script 03 conclui com `Validacao concluida com sucesso.`

## 2) Task 2 - Glue ETL para star schema

### 2.1 O que o Terraform cria

- Bucket S3 para ETL.
- Glue Connection para MySQL no RDS.
- Glue Job `classicmodels-etl-star-schema`.
- Security Group para Glue.
- VPC Endpoint S3 (Gateway) para Glue acessar S3 dentro da VPC.

### 2.2 Aplicar mudancas da Task 2

```powershell
cd ..\terraform
terraform apply -auto-approve
```

### 2.3 Iniciar e acompanhar o Glue Job

```powershell
$job = terraform output -raw glue_job_name
aws glue start-job-run --job-name $job --region us-east-1
aws glue get-job-runs --job-name $job --max-results 1 --region us-east-1
```

Repita o `get-job-runs` ate `JobRunState = SUCCEEDED`.

### 2.4 Validar saida no S3

```powershell
$bucket = terraform output -raw etl_bucket_name
aws s3 ls "s3://$bucket/curated/fact_orders/" --recursive --region us-east-1
aws s3 ls "s3://$bucket/curated/dim_customers/" --recursive --region us-east-1
aws s3 ls "s3://$bucket/curated/dim_products/" --recursive --region us-east-1
aws s3 ls "s3://$bucket/curated/dim_dates/" --recursive --region us-east-1
aws s3 ls "s3://$bucket/curated/dim_countries/" --recursive --region us-east-1
```

As tabelas gravadas em Parquet sao:
- `fact_orders`
- `dim_customers`
- `dim_products`
- `dim_dates`
- `dim_countries`

## 3) Onde verificar na interface AWS

- Glue Job:
  - `AWS Glue` > `ETL jobs` > `classicmodels-etl-star-schema` > `Runs`
- Logs:
  - `CloudWatch` > `Log groups` > `/aws-glue/jobs`
- Bucket:
  - `S3` > bucket de output > `curated/...`
- Banco:
  - `RDS` > `Databases` > `classicmodels-db`

## 4) Troubleshooting rapido

- `terraform not recognized`:
  - instalar Terraform no conda.
- `aws not recognized`:
  - instalar AWS CLI no conda.
- `NoRegion`:
  - definir `AWS_REGION`/`AWS_DEFAULT_REGION = us-east-1`.
- `iam:CreateRole` negado:
  - usar `existing_glue_role_arn` com role ja existente.
- `iam:PassRole` negado:
  - role informada nao pode ser passada pelo seu usuario do lab.
- Glue `At least one security group must open all ingress ports`:
  - resolvido no Terraform com regra self no `glue_sg`.
- Glue `Could not find S3 endpoint or NAT gateway`:
  - resolvido no Terraform com `aws_vpc_endpoint` S3.
- `explicit deny ... voc-cancel-cred`:
  - credencial/sessao do laboratorio expirou; reiniciar lab e reconfigurar AWS.

## 5) Limpeza (evitar custo)

```powershell
cd terraform
terraform destroy -auto-approve
```
