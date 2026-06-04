# Task 1 - Source System com AWS RDS

Esta entrega cria o banco MySQL `classicmodels` no Amazon RDS, carrega o dump do dataset e valida as tabelas.

## Seguranca adotada

- RDS privado por padrao (`publicly_accessible = false`).
- Sem regra `0.0.0.0/0` para MySQL.
- Acesso publico so em modo laboratrio, restrito ao seu IP `/32`.
- Storage do RDS criptografado.
- TLS obrigatorio no MySQL via parameter group (`require_secure_transport = ON`).
- Backups por 7 dias e `deletion_protection = true` por padrão.
- Senhas ficam fora do código: use `TF_VAR_db_password`, `terraform.tfvars` local ignorado pelo git ou `.env` local ignorado pelo git.
- `terraform.tfstate`, `.terraform/`, `.env`, caches Python e logs são ignorados.

Essas medidas aplicam defesa em profundidade em quatro camadas. Na camada de rede, o banco não fica exposto publicamente por padrão e o acesso MySQL só é liberado para uma origem explicita quando necessário. Na camada de dados, o armazenamento é criptografado e a comunicacao com o MySQL exige TLS. Na camada de segredos, senhas não ficam no código nem em arquivos versionados. Na camada operacional, backups, proteção contra exclusão acidental e arquivos locais ignorados pelo git reduzem risco de perda de dados e vazamento de informaçõess sensíveis.

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

Para o modo seguro padrão, mantenha:

```hcl
allowed_cidr        = null
publicly_accessible = false
deletion_protection = true
```

Defina a senha:

```powershell
$env:TF_VAR_db_password = "SUA_SENHA_FORTE_COM_12+_CARACTERES"
```


No `terraform.tfvars`, configure somente o seu IP:

```hcl
allowed_cidr        = "SEU_IP_PUBLICO/32"
publicly_accessible = true
deletion_protection = false
```

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

## 3) Preparar Python e conexão

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

## 4) Carregar e validar

```powershell
python .\scripts\01_provision_rds.py
python .\scripts\02_load_data.py
python .\scripts\03_validate.py
```

Resultado esperado:

```text
Validacao concluída com sucesso.
```
