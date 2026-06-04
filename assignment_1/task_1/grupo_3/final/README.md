# Task 1 - Source System com AWS RDS

Esta entrega cria o banco MySQL `classicmodels` no Amazon RDS, carrega o dump do dataset e valida as tabelas.

## Seguranca adotada

- RDS privado por padrao (`publicly_accessible = false`).
- Sem regra `0.0.0.0/0` para MySQL.
- Acesso publico so em modo laboratorio, restrito ao seu IP `/32`.
- Storage do RDS criptografado.
- TLS obrigatorio no MySQL via parameter group (`require_secure_transport = ON`).
- Backups por 7 dias e `deletion_protection = true` por padrao.
- Senhas ficam fora do codigo: use `TF_VAR_db_password`, `terraform.tfvars` local ignorado pelo git ou `.env` local ignorado pelo git.
- `terraform.tfstate`, `.terraform/`, `.env`, caches Python e logs sao ignorados.

## Estrutura

```text
final/
|- terraform/
|  |- main.tf
|  |- variables.tf
|  |- outputs.tf
|  |- terraform.tfvars.example
|- scripts/
|  |- .env.example
|  |- env_loader.py
|  |- 01_provision_rds.py
|  |- 02_load_data.py
|  |- 03_validate.py
|- requirements.txt
```

## 1) Preparar Terraform

```powershell
cd assignment_1\task_1\grupo_3\final\terraform
Copy-Item terraform.tfvars.example terraform.tfvars
```

Para o modo seguro padrao, mantenha:

```hcl
allowed_cidr        = null
publicly_accessible = false
deletion_protection = true
```

Defina a senha sem commitar:

```powershell
$env:TF_VAR_db_password = "SUA_SENHA_FORTE_COM_12+_CARACTERES"
```

Se precisar conectar do seu notebook no laboratorio, use modo publico restrito:

```powershell
Invoke-RestMethod https://checkip.amazonaws.com
```

No `terraform.tfvars`, configure somente o seu IP:

```hcl
allowed_cidr        = "SEU_IP_PUBLICO/32"
publicly_accessible = true
deletion_protection = false
```

Nunca use `allowed_cidr = "0.0.0.0/0"`.

## 2) Provisionar RDS

```powershell
terraform init
terraform validate
terraform plan
terraform apply
```

Para destruir depois, se `deletion_protection = true`, altere para `false` e aplique antes do destroy:

```powershell
terraform apply
terraform destroy
```

## 3) Preparar Python e conexao

```powershell
cd ..
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Crie um `.env` local a partir do exemplo:

```powershell
Copy-Item .\scripts\.env.example .\scripts\.env
```

Edite `scripts\.env`:

```text
AWS_REGION=us-east-1
DB_INSTANCE_IDENTIFIER=classicmodels-db
DB_HOST=ENDPOINT_DO_RDS_SEM_:3306
DB_PORT=3306
DB_USER=admin
DB_PASSWORD=SUA_SENHA
DB_NAME=classicmodels
```

`scripts\.env` e ignorado pelo git. Nao commite esse arquivo.

## 4) Carregar e validar

```powershell
python .\scripts\01_provision_rds.py
python .\scripts\02_load_data.py
python .\scripts\03_validate.py
```

Resultado esperado:

```text
Validacao concluida com sucesso.
```
