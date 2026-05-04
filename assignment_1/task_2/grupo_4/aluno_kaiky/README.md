# Task 2 — Pipeline ETL (AWS Glue → S3 Parquet)

Implementação do job **classicmodels** (OLTP) → **star schema** em Parquet no S3, com **Terraform** para bucket, IAM (escopo ao bucket/prefixos), conexão JDBC ao RDS e definição do Glue Job.

## Layout do código

| Caminho | Função |
|--------|--------|
| `glue_jobs/etl_job.py` | Ponto de entrada Glue: orquestra extract → transform → validações → load |
| `glue_jobs/utils/extract.py` | Leitura MySQL via **Glue connection** (sem usuário/senha no script) |
| `glue_jobs/utils/load.py` | Gravação Parquet por tabela em prefixo S3 |
| `glue_jobs/utils/helpers.py` | Logging e parsing de argumentos Glue |
| `glue_jobs/constants.py` | Nomes de tabelas/colunas e tolerâncias (fonte única para Glue + validação S3) |
| `glue_jobs/transformations/*.py` | Dimensões + `fact_orders` com nomes exigidos pela task |
| `terraform/` | S3, rede (SG Glue, endpoint S3 opcional), `aws_glue_connection`, `aws_glue_job`, artefatos no bucket |
| `scripts/validate_etl_output.py` | Validação pós-job (objetos S3 + amostra `sales_amount`) |
| `requirements.txt` | Dependências locais para `validate_etl_output.py` (boto3, pyarrow) |

## Modelo de saída (nomes exatos)

- **fact_orders**: `order_id`, `customer_id`, `product_id`, `order_date_key`, `country_key`, `quantity_ordered`, `price_each`, `sales_amount`
- **dim_customers**: `customer_id`, `customer_name`, `contact_name`, `city`, `country`
- **dim_products**: `product_id`, `product_name`, `product_line`, `product_vendor`
- **dim_dates**: `date_key`, `full_date`, `year`, `quarter`, `month`, `day`
- **dim_countries**: `country_key`, `country`, `territory`

`product_id` segue o código natural do MySQL (`productCode`, string). `sales_amount` = `quantity_ordered * price_each` (com validação no job).

## Segurança

- **Não** versionar `terraform.tfvars` com senha. No PowerShell: `$env:TF_VAR_glue_db_password="..."`. No Git Bash: `export TF_VAR_glue_db_password='...'`.
- Se o seu usuário AWS **não puder criar IAM Role** (labs), defina `glue_job_role_arn` no `terraform.tfvars` com uma role existente (ex.: `LabRole`). Nesse caso o Terraform **não** anexa a policy inline mínima; a role precisa já permitir Glue + S3 + VPC + logs conforme o lab.
- Quando o Terraform cria a role (`glue_job_role_arn` vazio), a policy inline limita **read/write** a `warehouse/star/*` e **GetObject** em `glue/assets/*`, além de permissões mínimas para logs e ENIs na VPC.
- Credenciais do MySQL ficam na **Glue JDBC connection** (criptografadas pela AWS), não nos argumentos do job.
- O `.gitignore` na raiz deste diretório (`aluno_kaiky/.gitignore`) cobre `venv`, `.env`, estado Terraform e `*.tfvars` locais.

## Pré-requisitos de rede

O Glue precisa alcançar o RDS na VPC: o Terraform usa as subnets do DB subnet group da instância informada em `rds_instance_identifier`. O Terraform cria um **security group dedicado ao Glue** (com **ingress TCP self-referencing** exigido pelo Glue) e adiciona **ingress MySQL** nos security groups do RDS a partir desse SG.

Para o Glue acessar **S3** a partir de subnets privadas, por padrão `create_s3_vpc_endpoint = true` cria um **VPC Gateway Endpoint** para S3 e associa às route tables da VPC. Desative só se sua VPC já tiver NAT ou endpoint S3 equivalente.

## Tutorial de execução (PowerShell, Windows)

### 1) Ir para a pasta do Terraform

```powershell
cd ".\terraform"
```

### 2) Criar arquivo de configuração real

```powershell
copy .\terraform.tfvars.example .\terraform.tfvars
```

Abra `terraform.tfvars` e preencha os valores reais:
- `aws_region`
- `project_name`
- `rds_instance_identifier`
- `rds_database`
- `glue_db_username`
- `glue_job_role_arn` (labs sem `iam:CreateRole`: ARN da role existente, ex. `LabRole`)
- `create_s3_vpc_endpoint` (default `true`; endpoint S3 na VPC)
- `glue_mysql_jdbc_suffix` (opcional; default inclui timeouts e `useSSL=false` para labs)
- `glue_max_concurrent_runs` (opcional; default 3 — reduz `ConcurrentRunsExceededException` em lab)

### 3) Definir senha do MySQL sem versionar no Git

```powershell
$env:TF_VAR_glue_db_password="SUA_SENHA_MYSQL"
```

### 4) Provisionar infraestrutura

```powershell
terraform init
terraform apply
```

O `archive_file` gera `build/glue_modules.zip` (tudo em `glue_jobs/` exceto `etl_job.py`). O script principal sobe como `glue/assets/etl_job.py` e o job usa `--extra-py-files` para os módulos.

### 5) Rodar o Glue Job sem copiar outputs manualmente

```powershell
$REGION = "us-east-1"
$JOB_NAME = terraform output -raw glue_job_name
aws glue start-job-run --region $REGION --job-name "$JOB_NAME"
```

Para acompanhar o último run:

```powershell
aws glue get-job-runs --region $REGION --job-name "$JOB_NAME" --max-results 1
```

Aguarde `JobRunState` = `SUCCEEDED`.

### 6) Validar saída Parquet no S3

```powershell
$REGION = "us-east-1"
$BUCKET = terraform output -raw s3_bucket_name
pip install -r "..\requirements.txt"
python "..\scripts\validate_etl_output.py" --bucket "$BUCKET" --prefix "warehouse/star" --region $REGION
```

Se o script terminar com `All validations passed`, a carga da task está validada.

No próprio job Spark há validações de integridade referencial e de `sales_amount` antes do `commit`.

## Troubleshooting (Glue → MySQL)

Se o job falhar com **`Communications link failure`** no `getDynamicFrame`, normalmente é **rede JDBC** ou **MySQL 8 / SSL / plugin de auth** (não é bug do Spark em si):

- Rode `terraform apply` com a versão atual: a conexão Glue prefere **subnet na mesma AZ do RDS** e a URL JDBC usa `glue_mysql_jdbc_suffix` (default inclui `allowPublicKeyRetrieval=true` para `caching_sha2_password`, timeouts e `useSSL=false` em lab).
- Se a AWS não atualizar a connection “no lugar”, force recriação: `terraform apply -replace="aws_glue_connection.mysql[0]"` (com `TF_VAR_glue_db_password` exportado).
- Confirme usuário/senha (`glue_db_username` + `TF_VAR_glue_db_password`) e que o usuário aceita conexão da VPC (`'%'` ou host correto).
- Se o RDS exigir TLS, troque `glue_mysql_jdbc_suffix` para a variante `useSSL=true` comentada em `terraform.tfvars.example`.
- Veja logs no CloudWatch (`/aws-glue/jobs/...`) e valide SG/NACL entre subnet do Glue e RDS.

### `ConcurrentRunsExceededException`

O job tem limite de runs simultâneos (`glue_max_concurrent_runs`, default **3** no Terraform atual). Se ainda aparecer o erro:

- Liste runs **não terminados** (ex.: `RUNNING`, `STARTING`, `STOPPING`, `WAITING`) e pare os que estiverem ativos.
- Ou aguarde ~1–2 minutos após `batch-stop-job-run` (estado `STOPPING` pode continuar contando no limite).
- Ajuste `glue_max_concurrent_runs` no `terraform.tfvars` e rode `terraform apply`.

## Conexão JDBC

A URL usa o catálogo `classicmodels`; o extract usa apenas o **nome da tabela** em `dbtable` (`customers`, `orders`, …), como recomendado quando o JDBC já aponta para o database.
