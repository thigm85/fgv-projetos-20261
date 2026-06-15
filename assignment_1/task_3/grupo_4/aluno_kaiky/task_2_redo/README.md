# Task 2 — Pipeline de dados (ETL) com AWS Glue + Terraform

Este diretório implementa a **Task 2**: extrair dados do MySQL (`classicmodels`) no RDS, **transformar para esquema estrela** e gravar as tabelas resultantes em **Parquet no S3**, usando **AWS Glue**, com **toda a infraestrutura criada via Terraform**.

## Pré-requisitos

- Ter concluído a Task 1 e possuir uma instância RDS MySQL com o banco `classicmodels` populado.
- Terraform 1.5+ instalado.
- Credenciais AWS configuradas localmente (perfil `default`).

## O que será criado

- Bucket S3 (saídas Parquet + artefatos do Glue).
- Glue Job usando uma **IAM Role existente do Lab** (por padrão `LabRole`), porque ambientes de laboratório frequentemente bloqueiam `iam:CreateRole`.
- Glue Connection (JDBC) para o MySQL no RDS.
- Glue Job PySpark para:
  - Extrair tabelas do `classicmodels` via JDBC.
  - Produzir:
    - `fact_orders`
    - `dim_customers`
    - `dim_products`
    - `dim_dates`
    - `dim_countries`
  - Gravar cada tabela em uma pasta no S3 (Parquet).
- **Glue Data Catalog** (`classicmodels_star_g4` por padrão): o job registra as cinco tabelas para consulta no Athena (Task 3).

## Como executar

### Passo 0 — Verifique acesso AWS (recomendado)

No PowerShell:

```powershell
aws sts get-caller-identity
```

Se esse comando falhar, corrija suas credenciais AWS antes de continuar.

### Passo 1 — Entrar na pasta de Terraform

```bash
cd assignment_1/task_3/grupo_4/aluno_luciano/task_2_redo/terraform
```

### Passo 2 — Criar `terraform.tfvars`

Crie um arquivo `terraform.tfvars` com o conteúdo abaixo e preencha os valores.

```hcl
aws_region = "us-east-1"

# Mesmo identificador da Task 1 (RDS_DB_INSTANCE_IDENTIFIER no .env).
# O endpoint é obtido automaticamente via AWS API — não cole o hostname aqui.
rds_db_instance_identifier = "classicmodels-mysql-g4"

db_name     = "classicmodels"
db_user     = "admin"
db_password = "SUA_SENHA"

# (Opcional) IAM Role usada pelo Glue Job (default: LabRole)
# glue_role_name = "LabRole"
```

Copie de [`terraform.tfvars.example`](terraform/terraform.tfvars.example). VPC, subnet e security group do Glue são derivados da instância RDS descoberta em [`rds_discovery.tf`](terraform/rds_discovery.tf).

### Passo 3 — Inicializar e aplicar o Terraform

No Windows PowerShell, prefira `;` em vez de `&&`.

```bash
terraform init
terraform apply
```

Após o `apply`, você verá outputs como `glue_job_name`, `s3_bucket_name`, `glue_database_name` e `rds_endpoint` (hostname resolvido da Task 1).

**Importante:** sempre que alterar `glue_job_script.py` ou `glue.tf`, execute `terraform apply` de novo e **reexecute o Glue Job** para atualizar Parquet e tabelas no catálogo.

### Passo 4 — Executar o Glue Job

#### 4A) Pelo Console (recomendado)

- AWS Console → **AWS Glue** → **ETL jobs** → selecione o Job → **Run**
- Acompanhe em **Runs / Job runs** até aparecer **SUCCEEDED**

O job deve terminar em `SUCCEEDED`.

#### 4B) Via AWS CLI (PowerShell)

Pegue o nome do job:

```powershell
terraform output -raw glue_job_name
```

Inicie a execução:

```powershell
$job = terraform output -raw glue_job_name
aws glue start-job-run --job-name "$job"
```

Copie o `JobRunId` retornado e acompanhe o status:

```powershell
aws glue get-job-run --job-name "$job" --run-id "COLE_O_JobRunId" --query "JobRun.JobRunState" --output text
```

## Glue Data Catalog (Athena)

Após o job em `SUCCEEDED`, confira no console **AWS Glue → Databases** o database (output `glue_database_name`, padrão `classicmodels_star_g4`) com as tabelas:

- `dim_customers`, `dim_products`, `dim_dates`, `dim_countries`, `fact_orders`

Use esse nome como `GLUE_DATABASE` no notebook da Task 3:

```bash
terraform output -raw glue_database_name
```

## Saídas esperadas no S3

O Terraform cria um bucket e grava as saídas neste prefixo:

- `s3://<bucket>/out/dim_customers/`
- `s3://<bucket>/out/dim_products/`
- `s3://<bucket>/out/dim_dates/`
- `s3://<bucket>/out/dim_countries/`
- `s3://<bucket>/out/fact_orders/`

### Como listar as saídas no S3

Pegue o bucket pelo Terraform:

```powershell
$bucket = terraform output -raw s3_bucket_name
aws s3 ls "s3://$bucket/out/"
```

## Validação mínima (critérios do enunciado)

1. **Job**: status `SUCCEEDED`.
2. **Parquet no S3**: existem pastas/arquivos para `fact_orders` e todas as dimensões.
3. **Integridade das chaves**:
   - `fact_orders.customer_id` existe em `dim_customers.customer_id`
   - `fact_orders.product_id` existe em `dim_products.product_id`
   - `fact_orders.order_date_key` existe em `dim_dates.date_key`
   - `fact_orders.country_key` existe em `dim_countries.country_key`
4. **Métrica**:
   - `sales_amount = quantity_ordered * price_each` (o job calcula exatamente assim)

## Observações importantes

### Rede (VPC/Subnet/SG)

- **Descoberta automática**: `rds_discovery.tf` lê a instância `rds_db_instance_identifier` (mesmo nome da Task 1) e define endpoint, VPC, subnet (mesma AZ do RDS quando possível) e SG do RDS.
- **Pré-requisito**: execute a Task 1 (`01_provision_rds.py`) antes do `terraform apply`, para a instância existir na conta.
- **Acesso ao RDS**: o SG do RDS precisa permitir inbound 3306 a partir do(s) SG(s) da Glue Connection.

### Sobre `dim_countries.territory`

No dataset `classicmodels`, `territory` fica em `offices` (não em `customers`). O job deriva `territory` via:

- `customers.salesRepEmployeeNumber -> employees.officeCode -> offices.territory`

## Troubleshooting (erros comuns)

### 1) `AccessDenied: iam:CreateRole`

Ambientes de lab podem bloquear criação de IAM Role. Esta implementação usa por padrão `glue_role_name = "LabRole"`.

Se sua conta tiver outra role pronta para Glue, defina no `terraform.tfvars`, por exemplo:

```hcl
glue_role_name = "SUA_ROLE_EXISTENTE"
```

### 2) `At least one security group must open all ingress ports`

O lab pode exigir que a Glue Connection tenha pelo menos um SG com **inbound all ports**. O Terraform cria um SG dedicado com inbound “all” **a partir dele mesmo** (self), reduzindo a exposição.

### 3) `VPC S3 endpoint validation failed ... Could not find S3 endpoint or NAT`

Este lab pode exigir um **VPC Endpoint de S3**. O Terraform cria um **Gateway VPC Endpoint para S3** no VPC informado em `vpc_id`.

### 4) `AccessDenied` em bucket `...590183650282` ou Glue catalog `590183650282`

O **terraform.tfstate** ainda descreve recursos de outra conta AWS (ex.: lab de colega). Você está autenticado em `190496630210`, mas o state aponta para `590183650282`.

**Correção:** arquive o state antigo e aplique de novo na conta atual:

```bash
cd assignment_1/task_3/grupo_4/aluno_luciano/task_2_redo/terraform
mv terraform.tfstate terraform.tfstate.account-OUTRA_CONTA
mv terraform.tfstate.backup terraform.tfstate.backup.account-OUTRA_CONTA 2>/dev/null
terraform apply
```

O bucket novo será `classicmodels-etl-g4-<SUA_CONTA>` (ex.: `...-190496630210`).

### 5) `no matching EC2 Subnet found`

Confirme que a instância RDS da Task 1 existe na conta atual (`rds_db_instance_identifier` no `terraform.tfvars`). A rede é descoberta automaticamente via `rds_discovery.tf`.

### 5) `Invalid index` em `vpc_endpoints.tf` (route tables vazias)

Mesma causa: `vpc_id` inválido na conta atual. Corrija o `vpc_id` no `terraform.tfvars` (ver item 4).

