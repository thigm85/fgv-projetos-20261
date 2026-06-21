## Task 1 — Sistema de Origem (RDS MySQL)

Esta pasta contém scripts Python para:

- **Provisionamento do RDS** (MySQL)
- **Carga do banco `classicmodels`** a partir do arquivo SQL de exemplo
- **Validação** (tabelas e contagem básica de registros)

### Pré-requisitos

- Python 3.10+
- Credenciais AWS configuradas localmente (ex.: `aws configure`)
- Permissões para criar/consultar RDS, e (se necessário) criar Security Group/Subnet Group
- Acesso de rede do seu computador ao endpoint do RDS (ex.: `PubliclyAccessible=true` + Security Group liberando 3306 para o seu IP)

### Instalação

No diretório desta pasta:

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### Variáveis de ambiente (AWS)

Você pode usar o profile padrão do AWS CLI, ou definir:

- `AWS_PROFILE` (opcional)
- `AWS_REGION` (ou `AWS_DEFAULT_REGION`)

### 1) Provisionar o RDS

Exemplo (ajuste `--vpc-security-group-ids` e `--db-subnet-group-name` conforme seu ambiente):

```bash
python 01_provision_rds.py `
  --db-instance-identifier classicmodels-larissa `
  --master-username admin `
  --master-password "SUA_SENHA" `
  --db-instance-class db.t3.micro `
  --allocated-storage 20 `
  --publicly-accessible true `
  --vpc-security-group-ids sg-0051c6c38d967aae2 `
  --db-subnet-group-name vpc-0173df1e1018a44c3 `
  --region us-east-1
```

Ao final, o script imprime o **endpoint** e a **porta**.

### 2) Carregar o SQL (criar + popular `classicmodels`)

```bash
python 02_load_classicmodels.py `
  --host classicmodels-larissa.cns0qka4oeu3.us-east-1.rds.amazonaws.com `
  --port 3306 `
  --user admin `
  --password "SUA_SENHA" `
  --sql-path ..\..\data\mysqlsampledatabase.sql
```

### 3) Validar tabelas/dados

```bash
python 03_validate_classicmodels.py `
  --host classicmodels-larissa.cns0qka4oeu3.us-east-1.rds.amazonaws.com `
  --port 3306 `
  --user admin `
  --password "SUA_SENHA"
```

### Observações

- O arquivo SQL usado é o fornecido no repositório: `assignment_1/task_1/data/mysqlsampledatabase.sql`.
- A validação aqui é propositalmente simples: checa a lista de tabelas esperadas e faz contagens básicas em algumas tabelas.

