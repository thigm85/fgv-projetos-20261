# Assignment 2 — Task 1: Origem incremental e watermark

Prepara o **sistema de origem** (`classicmodels` no RDS MySQL) para cargas incrementais:
provisiona o RDS, carrega o banco, cria a tabela de controle `etl_watermark`, simula a chegada
de novos pedidos e valida que a origem está pronta para o ETL da Task 2.

**Autocontido**: todo o provisionamento e setup vivem aqui em `assignment_2/task_1/` — não há
dependência da pasta do Assignment 1 para executar (a única referência opcional ao A1 é o dump
SQL já versionado no repo, para não commitar um dump novo).

Esta Task **não** cria star schema no S3 nem agenda o Glue (isso é Task 2).

## Estrutura

```
assignment_2/task_1/
├── infra/                             # Terraform — provisiona SÓ o RDS (sem Glue/S3)
│   ├── main.tf  variables.tf  rds.tf  outputs.tf
│   ├── terraform.tfvars.example       # template de credenciais (sem segredos)
│   └── .gitignore                     # ignora tfstate + terraform.tfvars
├── scripts/
│   ├── db.py                          # helper de conexão (.env + pipeline_info.json + retry)
│   ├── load_classicmodels.py          # carrega o dump no RDS recém-criado
│   ├── init_watermark.py              # cria/inicializa etl_watermark (idempotente)
│   ├── simulate_new_orders.py         # gera pedidos novos no OLTP
│   ├── validate_incremental_source.py # validação com exit code determinístico
│   ├── pipeline.py                    # orquestra load→init→validate→simulate→validate
│   ├── .env                           # senha do RDS (NÃO commitado)
│   └── pipeline_info.json             # gerado pelo terraform apply (NÃO commitado)
├── sql/
│   └── init_watermark.sql             # equivalente SQL puro do init
├── .env.example                       # template sem senha
└── README.md
```

## Pré-requisitos

- Terraform e credenciais AWS (chaves temporárias do AWS Academy/STS).
- Python 3 com `pymysql` e `python-dotenv`.
- Cliente MySQL na máquina **não** é necessário (a carga é via Python).

## Passo a passo (autocontido)

### 1. Provisionar o RDS (Terraform)

```powershell
cd assignment_2\task_1\infra
copy terraform.tfvars.example terraform.tfvars   # depois edite com suas credenciais/senha
terraform init
terraform apply
```

O `apply` cria a instância RDS e **grava `scripts/pipeline_info.json`** automaticamente
(endpoint, porta, usuário, banco). O Security Group libera a porta 3306 apenas para o **seu IP**.

> O RDS leva ~5 min para ficar disponível. Se a primeira conexão falhar, os scripts já têm
> retry com backoff; basta reexecutar.

### 2. Configurar a senha (.env)

```powershell
cd ..\scripts
copy ..\.env.example .env        # depois edite e coloque RDS_ADMIN_PASSWORD = mesma senha do tfvars
```

`.env` e `pipeline_info.json` estão no `.gitignore` — nunca são versionados.

### 3. Rodar o fluxo completo

Opção A — orquestrado (um comando):

```powershell
python pipeline.py --count 5 --seed 42
```

Opção B — passo a passo:

```powershell
python load_classicmodels.py                            # carrega classicmodels
python init_watermark.py                                # cria/inicializa watermark
python validate_incremental_source.py                   # baseline → PASS
python simulate_new_orders.py --count 5 --seed 42       # insere pedidos novos
python validate_incremental_source.py --require-pending # há pendência → PASS
```

### 4. Destruir ao terminar (evita custo)

```powershell
cd ..\infra
terraform destroy
```

## Contrato da tabela `etl_watermark`

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `pipeline_name` | `VARCHAR(64)` PK | `classicmodels_sales` |
| `last_processed_order_date` | `DATE` | Maior `orderDate` já refletida no lake |
| `last_run_at` | `DATETIME` | Timestamp UTC da última execução do ETL (Task 2) |
| `last_run_status` | `VARCHAR(32)` | `SUCCEEDED` / `FAILED` / `NEVER_RUN` |

## Fluxo de validação

```text
1. init_watermark                       → baseline = MAX(orderDate) do histórico carregado
2. validate_incremental_source          → PASS (baseline, sem pendência exigida)
3. simulate_new_orders --count N        → insere N pedidos novos (orderDate > watermark)
4. validate_incremental_source --require-pending → PASS (há dados pendentes de ETL)
```

## Parâmetros

**`load_classicmodels.py`**
- `--sql <caminho>` — caminho do `mysqlsampledatabase.sql` (default: procura em
  `data/` local e depois no dump do A1 já versionado no repo).

**`simulate_new_orders.py`**
- `--count` (default `5`), `--seed` (opcional), `--min-lines`/`--max-lines` (default `1`/`4`).

**`validate_incremental_source.py`**
- `--require-pending` — exige `MAX(orderDate) > last_processed_order_date` (passo 4).
  Sem a flag, basta `>=` (passo 2). Exit code `0` = tudo OK, `1` = falha.

**`pipeline.py`**
- `--skip-load` (banco já carregado), `--count`, `--seed`.

## Notas de design

- **Infra mínima**: `infra/` provisiona apenas o RDS. Glue/S3 ficam para a Task 2.
- **`orders.orderNumber` não é AUTO_INCREMENT** neste dump: o próximo id vem de
  `MAX(orderNumber)+1` dentro da transação (sem `LAST_INSERT_ID()`).
- `simulate_new_orders.py` **não** atualiza `etl_watermark` — isso é responsabilidade do job
  Glue na Task 2 (evita condição de corrida).
- `orderDate` dos pedidos novos usa dias úteis recentes (`> watermark`), facilitando testes de
  partição diária na Task 2.
- `priceEach` deriva do `MSRP`; `sales_amount = quantityOrdered * priceEach` (regra do A1).
- Inserções em transação explícita com `commit`/`rollback`.
- **Segredos**: `terraform.tfvars`, `.env`, `pipeline_info.json` e o dump completo **não** são
  commitados.
