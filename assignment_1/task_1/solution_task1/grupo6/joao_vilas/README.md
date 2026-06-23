# Task 1 — Sistema de origem (Engenharia de Dados)

Solução da **Task 1**: provisionar MySQL na AWS (Amazon RDS) com **Terraform** e popular o banco **classicmodels** com scripts Python.

## Estrutura

```text
grupo6/joao_vilas/
├── data/mysqlsampledatabase.sql   # Dump SQL de origem
├── scripts/
│   ├── load_data.py               # Carga no RDS
│   └── validate_data.py           # Validação das tabelas
├── terraform/
│   ├── main.tf                    # RDS e security group
│   ├── outputs.tf                 # Endpoint do banco
│   └── variables.tf               # Senha (variável)
├── README.md
├── pyproject.toml
└── uv.lock
```

## Pré-requisitos

- Python 3.13+ (conforme `pyproject.toml`) e [uv](https://github.com/astral-sh/uv)
- AWS CLI v2
- Terraform

## Ambiente Python (uv)

Na pasta `grupo6/joao_vilas`:

```bash
uv venv
```

Ative o ambiente: Windows PowerShell `.venv\Scripts\activate`; macOS/Linux `source .venv/bin/activate`.

Instale dependências (inclui `pymysql`, conforme `pyproject.toml`):

```bash
uv sync
```

## AWS (Learner Lab)

Credenciais temporárias: no portal do lab, **AWS Details** → **AWS CLI** → **Show**, copie o bloco `[default]`.

Cole em `~/.aws/credentials` (Windows: `C:\Users\<usuario>\.aws\credentials`, sem extensão `.txt`).

Valide:

```bash
aws sts get-caller-identity
```

As credenciais expiram a cada sessão do laboratório.

## Terraform

```bash
cd terraform
terraform init
terraform apply
```

Informe `var.db_password` (mínimo 8 caracteres), confirme com `yes`. Aguarde ~5–10 minutos. Anote o **`rds_endpoint`** no output.

## Carga e validação

```bash
cd ../scripts
```

Em `load_data.py` e `validate_data.py`, ajuste **`HOST`** (endpoint do RDS) e **`PASSWORD`** (mesma do Terraform).

```bash
python load_data.py
python validate_data.py
```

**Validação esperada:** listagem das 8 tabelas com contagens:

| Tabela        | Linhas |
|---------------|--------|
| customers     | 122    |
| employees     | 23     |
| offices       | 7      |
| orderdetails  | 2996   |
| orders        | 326    |
| payments      | 273    |
| productlines  | 7      |
| products      | 110    |

## Destruir o RDS

```bash
cd assignment_1\task_1\solution_task1\grupo6\joao_vilas\terraform
```

```bash
terraform destroy
```