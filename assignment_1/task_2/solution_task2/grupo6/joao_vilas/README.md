# Task 2 — Pipeline ETL ClassicModels com AWS Glue

Esta solução implementa um pipeline de dados:

RDS MySQL `classicmodels` → AWS Glue → Star Schema → S3 Parquet.

## Componentes provisionados via Terraform

- RDS MySQL com o banco de origem.
- Security Group do RDS com acesso local restrito por IP `/32`.
- Bucket S3 para dados transformados.
- S3 Gateway VPC Endpoint.
- Security Group do Glue.
- Regra permitindo acesso MySQL ao RDS somente a partir do Security Group do Glue.
- Glue Connection JDBC.
- Glue Job Spark.
- Upload do script ETL para o S3.

No AWS Learner Lab, o Glue Job usa a role existente `LabRole`.

## Modelo estrela gerado

O Glue Job gera as seguintes tabelas em Parquet:

- `fact_orders`
- `dim_customers`
- `dim_products`
- `dim_dates`
- `dim_countries`

## Colunas principais

`fact_orders`:

- `order_id`
- `customer_id`
- `product_id`
- `order_date_key`
- `country_key`
- `quantity_ordered`
- `price_each`
- `sales_amount`

`dim_customers`:

- `customer_id`
- `customer_name`
- `contact_name`
- `city`
- `country`

`dim_products`:

- `product_id`
- `product_name`
- `product_line`
- `product_vendor`

`dim_dates`:

- `date_key`
- `full_date`
- `year`
- `quarter`
- `month`
- `day`

`dim_countries`:

- `country_key`
- `country`
- `territory`

## Execução

Na raiz do projeto:

```powershell
aws sts get-caller-identity

$env:AWS_REGION = "us-east-1"
$env:AWS_DEFAULT_REGION = "us-east-1"
$env:TF_VAR_aws_region = "us-east-1"
$env:TF_VAR_db_password = "ClassicModels2026Lab!"

$MyIp = (Invoke-RestMethod "https://checkip.amazonaws.com").Trim()
$env:TF_VAR_allowed_mysql_cidr = "$MyIp/32"

terraform -chdir=terraform init
terraform -chdir=terraform fmt -recursive
terraform -chdir=terraform validate
terraform -chdir=terraform plan -out=tfplan
terraform -chdir=terraform apply tfplan
```

## Gerar .env:

```powershell
$RdsHost = terraform -chdir=terraform output -raw rds_host
$RdsPort = terraform -chdir=terraform output -raw rds_port

@"
DB_HOST=$RdsHost
DB_PORT=$RdsPort
DB_USER=admin
DB_PASSWORD=$env:TF_VAR_db_password
DB_NAME=classicmodels
MYSQL_SQL_PATH=data/mysqlsampledatabase.sql
MYSQL_CONNECT_RETRIES=10
MYSQL_CONNECT_DELAY_SECONDS=10
"@ | Set-Content .env
```

## Carregar e validar o banco

```powershell
uv sync
uv run python scripts/load_data.py --dry-run
uv run python scripts/load_data.py
uv run python scripts/validate_data.py
```

## Executar Glue Job

```powershell
$JOB_NAME = terraform -chdir=terraform output -raw glue_job_name

$RUN_ID = aws glue start-job-run `
  --job-name $JOB_NAME `
  --query "JobRunId" `
  --output text

$RUN_ID
```

## Validar Parquets

```powershell
$BUCKET = terraform -chdir=terraform output -raw etl_bucket_name

aws s3 ls "s3://$BUCKET/curated/classicmodels/fact_orders/" --recursive
aws s3 ls "s3://$BUCKET/curated/classicmodels/dim_customers/" --recursive
aws s3 ls "s3://$BUCKET/curated/classicmodels/dim_products/" --recursive
aws s3 ls "s3://$BUCKET/curated/classicmodels/dim_dates/" --recursive
aws s3 ls "s3://$BUCKET/curated/classicmodels/dim_countries/" --recursive
```

## Finalizar serviços

```powershell
terraform -chdir=terraform output
```

Esse comando deve mostrar recursos como:

```text
rds_host
etl_bucket_name
glue_connection_name
glue_job_name
```

Se você tiver um `RUN_ID` salvo da execução do Glue Job, confira o status:

```powershell
$JOB_NAME = terraform -chdir=terraform output -raw glue_job_name

aws glue get-job-runs `
  --job-name $JOB_NAME `
  --max-results 5 `
  --query "JobRuns[].{RunId:Id,State:JobRunState,StartedOn:StartedOn}" `
  --output table
```

Se algum job estiver com status `RUNNING`, pare a execução usando o `RunId` exibido:

```powershell
aws glue batch-stop-job-run `
  --job-name $JOB_NAME `
  --job-run-ids "COLE_AQUI_O_RUN_ID"
```

Depois confira novamente:

```powershell
aws glue get-job-runs `
  --job-name $JOB_NAME `
  --max-results 5 `
  --query "JobRuns[].{RunId:Id,State:JobRunState}" `
  --output table
```

### Destruir todos os recursos criados pelo Terraform

Na raiz do projeto:

```powershell
terraform -chdir=terraform plan -destroy -out=destroy.tfplan
```

Revise o plano. Ele deve indicar destruição de recursos como:

```text
aws_db_instance.classicmodels_db
aws_security_group.rds_sg
aws_security_group.glue_sg
aws_security_group_rule.rds_from_glue
aws_s3_bucket.etl_bucket
aws_s3_bucket_public_access_block.etl_bucket
aws_s3_bucket_server_side_encryption_configuration.etl_bucket
aws_s3_object.glue_script
aws_glue_connection.classicmodels_mysql
aws_glue_job.classicmodels_etl
aws_vpc_endpoint.s3
```

Se o plano estiver correto, aplique:

```powershell
terraform -chdir=terraform apply destroy.tfplan
```
