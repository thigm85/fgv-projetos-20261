# Task 2 - Grupo 2 / Sillas

Implementacao simples e reexecutavel da task 2 usando:
- Terraform para provisionar RDS, S3, IAM e AWS Glue.
- Python local para carregar o banco `classicmodels`, iniciar o job e validar a saida.
- Glue PySpark para transformar os dados no esquema estrela e gravar Parquet no S3.

## Estrutura

- `terraform/`: infraestrutura AWS
- `glue/etl_job.py`: job ETL do AWS Glue
- `scripts/load_classicmodels.py`: carga do banco de origem
- `scripts/run_pipeline.py`: orquestrador de ponta a ponta com dry-run
- `scripts/run_glue_job.py`: dispara e acompanha o Glue Job
- `scripts/validate_pipeline.py`: valida status do job, arquivos Parquet e regras de qualidade

## Pre-requisitos

- AWS credentials configuradas localmente
- Terraform instalado
- `uv` instalado
- Um arquivo `.env` criado a partir de `.env.example`
- Um arquivo `terraform/terraform.tfvars` criado a partir de `terraform/terraform.tfvars.example`

Se `allowed_cidr` ficar vazio no `terraform.tfvars`, o Terraform tenta descobrir seu IP publico automaticamente e usa `<ip>/32`.
Os scripts locais tambem tentam completar `DB_HOST`, `GLUE_JOB_NAME` e `S3_BUCKET_NAME` a partir de `terraform output` quando essas variaveis estiverem vazias no `.env`.
Por padrao, o Glue usa a role existente `LabRole`, que neste laboratorio ja aceita `glue.amazonaws.com`. Se quiser sobrescrever isso, use `existing_glue_role_arn` ou `existing_glue_role_name`. So use `create_glue_role = true` se sua conta realmente puder criar IAM Role.

## Ordem de execucao

```bash
cd assignment_1/task_2/grupo_2/final
uv sync
uv run python scripts/run_pipeline.py --dry-run
uv run python scripts/run_pipeline.py
```

## Execucao manual alternativa

```bash
cd assignment_1/task_2/grupo_2/final
uv sync
terraform -chdir=terraform init
terraform -chdir=terraform apply
uv run python scripts/load_classicmodels.py
uv run python scripts/run_glue_job.py
uv run python scripts/validate_pipeline.py
```

## Outputs esperados

- `fact_orders`
- `dim_customers`
- `dim_products`
- `dim_dates`
- `dim_countries`

Todos sao gravados em `s3://<bucket>/analytics/<tabela>/` em formato Parquet.
