# Task 1 - Source System with AWS RDS (Terraform + Python)

Este projeto implementa o Task 1 do laboratorio: criar o sistema de origem em MySQL no Amazon RDS, carregar o dataset `classicmodels` e validar as tabelas.

## Estrutura

```text
aluno_paula/
|- terraform/
|  |- main.tf
|  |- variables.tf
|  |- outputs.tf
|  |- terraform.tfvars.example
|- scripts/
|  |- 01_provision_rds.py
|  |- 02_load_data.py
|  |- 03_validate.py
|- requirements.txt
```

## Pre-requisitos

- Python 3.10+
- Terraform 1.5+
- AWS CLI configurado (`aws configure`)
- Permissao IAM para VPC, Security Group e RDS

## 1) Provisionar infraestrutura (Terraform)

Se o comando `terraform` nao existir no PowerShell, use o binario local:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\bin" | Out-Null
Invoke-WebRequest -Uri "https://releases.hashicorp.com/terraform/1.9.8/terraform_1.9.8_windows_amd64.zip" -OutFile "$env:TEMP\terraform.zip"
Expand-Archive -Path "$env:TEMP\terraform.zip" -DestinationPath "$env:USERPROFILE\bin" -Force
& "$env:USERPROFILE\bin\terraform.exe" --version
```

No PowerShell, partindo da raiz do repositorio:

```powershell
cd assignment_1\task_1\grupo_3\aluno_paula\terraform
Copy-Item terraform.tfvars.example terraform.tfvars
```

Edite `terraform.tfvars` e troque `db_password` para uma senha forte.

Depois execute:

```powershell
& "$env:USERPROFILE\bin\terraform.exe" init
& "$env:USERPROFILE\bin\terraform.exe" validate
& "$env:USERPROFILE\bin\terraform.exe" plan
& "$env:USERPROFILE\bin\terraform.exe" apply
```

Obter valores para os scripts:

```powershell
& "$env:USERPROFILE\bin\terraform.exe" output
```

## Como validar no console AWS (etapa 1)

No Console AWS, regiao `us-east-1`:

1. `RDS > Databases > classicmodels-db`
2. Verifique:
   - `Status = Available`
   - Engine MySQL
   - Endpoint preenchido
3. `Connectivity & security`:
   - Security group associado
   - DB subnet group com 2 subnets em AZs diferentes
4. `VPC > Your VPCs`:
   - VPC `classicmodels-vpc` criada
5. `VPC > Subnets`:
   - `classicmodels-subnet-a` e `classicmodels-subnet-b`

## 2) Preparar ambiente Python

Volte para a pasta `aluno_paula`:

```powershell
cd ..
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 3) Verificar instancia RDS (script 01)

Defina variaveis de ambiente (use os valores do `terraform output`):

```powershell
$env:AWS_REGION="us-east-1"
$env:DB_INSTANCE_IDENTIFIER="classicmodels-db"
$env:DB_HOST="classicmodels-db.czgogsk8eoie.us-east-1.rds.amazonaws.com"
$env:DB_USER="paula_admin"
$env:DB_PASSWORD="<sua-senha>"
```

Importante: em `DB_HOST`, nao colocar `:3306`.

Execute:

```powershell
python .\scripts\01_provision_rds.py
```

Resultado esperado:
- Mostra instancia, status, endpoint e porta.
- Status ideal: `available`.

## Como validar no console AWS (etapa 3)

1. `RDS > Databases > classicmodels-db`
2. Confirmar `Status = Available`
3. Confirmar endpoint igual ao usado em `DB_HOST`

## 4) Carga de dados (script 02)

Execute:

```powershell
python .\scripts\02_load_data.py
```

Resultado esperado:
- Mensagem `Dados carregados com sucesso`
- Quantidade de comandos SQL executados

## Como validar no console AWS (etapa 4)

1. `RDS > Databases > classicmodels-db`
2. Instancia continua em `Available`
3. Sem eventos recentes de erro em `Logs & events`

## 5) Validacao de tabelas e contagens (script 03)

Execute:

```powershell
python .\scripts\03_validate.py
```

Resultado esperado:
- Lista as 8 tabelas:
  - `customers`
  - `employees`
  - `offices`
  - `orderdetails`
  - `orders`
  - `payments`
  - `productlines`
  - `products`
- Mostra contagem de linhas por tabela
- Finaliza com `Validacao concluida com sucesso`

## Como validar no console AWS (etapa 5)

No console do RDS:

1. `RDS > Databases > classicmodels-db > Connectivity & security`
2. Copie o endpoint e confirme que e o mesmo do script
3. Evidencia funcional principal desta etapa:
   - Saida do script `03_validate.py` sem erros

## Limpeza de recursos (evitar custos)

Quando terminar o laboratorio:

```powershell
cd .\terraform
terraform destroy
```

## Observacoes de seguranca

- Nao commitar `terraform.tfvars` com senha real.
- Em ambiente produtivo, substituir senha em variavel por AWS Secrets Manager.
- Em ambiente produtivo, restringir `allowed_cidr` para seu IP (`x.x.x.x/32`).


