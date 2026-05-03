# Task 2 - AWS RDS Pipeline (Terraform + Python)

Este projeto provisiona um MySQL no Amazon RDS, carrega o dataset `classicmodels` e valida qualidade dos dados.

Implementa as correcoes de aula de idempotencia, seguranca, configuracao, robustez de carga, validacao objetiva e observabilidade.

## Estrutura

```text
aluno_paula/
|- terraform/
|  |- main.tf
|  |- variables.tf
|  |- outputs.tf
|- scripts/
|  |- 01_provision_rds.py
|  |- 02_load_data.py
|  |- 03_validate.py
|- requirements.txt
```

## Pre-requisitos

- Conda environment: `aws-data-pipeline`
- Python 3.10+
- Terraform no PATH
- AWS CLI configurado (`aws configure`)
- Permissoes IAM para VPC, Security Group, Subnet Group e RDS

## 1) Preparar ambiente

No PowerShell:

```powershell
conda activate aws-data-pipeline
cd "C:\Users\paula\OneDrive - Fundacao Getulio Vargas - FGV\Documentos\7 periodo\Projetos em CD\fgv-projetos-20261\assignment_1\task_2\grupo_3\solution_task_2\aluno_paula"
pip install -r requirements.txt
```

Se `terraform` nao for reconhecido:

```powershell
conda activate aws-data-pipeline
conda install -c conda-forge terraform -y
terraform -version
```

## 2) Provisionar infraestrutura (Terraform)

Entrar na pasta Terraform:

```powershell
cd terraform
```

Criar `terraform.tfvars` com valores reais:

```hcl
region                 = "us-east-1"
db_instance_identifier = "classicmodels-db"
db_name                = "classicmodels"
db_username            = "paula"
db_password            = "SUA_SENHA_FORTE"
instance_class         = "db.t3.micro"
allowed_cidr           = "SEU_IP_PUBLICO/32"
publicly_accessible    = true
```

Observacoes:
- `db_password` precisa ter ao menos 8 caracteres.
- `allowed_cidr` deve ser `/32` (ex.: `179.218.10.130/32`).
- `0.0.0.0/0` e bloqueado por validacao no `variables.tf`.

Executar:

```powershell
terraform init
terraform validate
terraform plan
terraform apply -auto-approve
```

## 3) Exportar variaveis para scripts

Ainda na pasta `terraform`:

```powershell
$env:DB_HOST = terraform output -raw rds_endpoint
$env:DB_PORT = terraform output -raw rds_port
$env:DB_USER = "paula"
$env:DB_PASSWORD = "SUA_SENHA_FORTE"
$env:DB_NAME = "classicmodels"
$env:AWS_REGION = "us-east-1"
$env:DB_INSTANCE_IDENTIFIER = "classicmodels-db"
```

Nota:
- Os scripts aceitam `DB_HOST` com ou sem `:3306`.

## 4) Executar pipeline Python

Ir para scripts:

```powershell
cd ..\scripts
```

### 4.1 Verificar RDS

```powershell
python .\01_provision_rds.py
```

Comportamento:
- verifica se instancia existe;
- mostra status/endpoint/porta;
- aguarda estado `available` com timeout explicito quando necessario;
- suporta `DRY_RUN=1`.

### 4.2 Carregar dados

```powershell
python .\02_load_data.py
```

Comportamento:
- localiza SQL com fallback;
- conecta com retry (`MYSQL_CONNECT_RETRIES`, `MYSQL_CONNECT_DELAY_SECONDS`);
- executa em transacao;
- `rollback` em erro;
- logs por etapa e `DRY_RUN=1`.

### 4.3 Validar qualidade

```powershell
python .\03_validate.py
```

Comportamento:
- valida tabelas esperadas;
- valida minimo de linhas por tabela critica;
- valida integridade referencial basica (FK checks);
- retorna `exit code` 0/1 de forma deterministica.

## 5) Troubleshooting

- `terraform not recognized`:
  - instalar com `conda install -c conda-forge terraform -y`.
- `MasterUserPassword ... shorter than 8 characters`:
  - usar senha com 8+ caracteres em `db_password`.
- `Unknown MySQL server host '...:3306'`:
  - resolvido no codigo; hoje o script separa host/porta automaticamente.
- `Arquivo SQL nao encontrado`:
  - resolvido no codigo; busca em `assignment_1/task_1/data/mysqlsampledatabase.sql`.
- `Table 'classicmodels.orders' doesn't exist`:
  - indica que a carga ainda nao foi feita com sucesso; execute `02_load_data.py` antes de `03_validate.py`.

## 6) Seguranca aplicada

- Sem hardcode de credenciais nos scripts.
- Leitura centralizada de variaveis de ambiente.
- Regra SG restrita para CIDR `/32`.
- Bloqueio explicito de `0.0.0.0/0` no Terraform.

## 7) Limpeza de recursos

Para evitar custos:

```powershell
cd ..\terraform
terraform destroy -auto-approve
```


