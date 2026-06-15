# Assignment 2 — Task 1: Origem incremental e watermark

Esta solução prepara o **sistema de origem** (`classicmodels` no RDS MySQL, reaproveitado
do [Assignment 1](../../../../../assignment_1/)) para cargas **incrementais**:

- Tabela de controle (**watermark**) `etl_watermark` no próprio RDS.
- Script idempotente de inicialização do watermark.
- Simulador de novos pedidos (não depende de dados externos).
- Validador reprodutível de prontidão da origem.

O watermark é baseado na coluna `orders.orderDate` (tipo `DATE`).

## Estrutura

```text
solution_task1/grupo6/joao_vilas/
├── sql/
│   └── init_watermark.sql              # DDL idempotente da etl_watermark + baseline
├── scripts/
│   ├── config.py                       # leitura de configuração via .env
│   ├── db.py                           # conexão MySQL com retry (reuso)
│   ├── init_watermark.py               # 3.1 — cria/inicializa o watermark
│   ├── simulate_new_orders.py          # 3.2 — insere novos pedidos
│   └── validate_incremental_source.py  # 3.3 — valida a origem (exit code determinístico)
├── .env.example
├── pyproject.toml
└── README.md
```

## Contrato da tabela `etl_watermark`

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `pipeline_name` | `VARCHAR(64)` PK | Identificador do pipeline. Fixo: `classicmodels_sales`. |
| `last_processed_order_date` | `DATE` | Maior `orderDate` já refletida no lake analítico. |
| `last_run_at` | `DATETIME` | Timestamp UTC da última execução bem-sucedida do ETL (atualizado na Task 2). |
| `last_run_status` | `VARCHAR(32)` | `NEVER_RUN`, `SUCCEEDED` ou `FAILED`. |

## Pré-requisitos

- Python 3.10+ e [uv](https://docs.astral.sh/uv/).
- Banco `classicmodels` já carregado no RDS (Assignment 1).
- Acesso de rede ao RDS (Security Group liberando o seu IP `/32`).

## Configuração (sem senhas no repositório)

Copie `.env.example` para `.env` e preencha com os dados da sua instância RDS. O `.env`
está no `.gitignore` e **nunca** deve ser commitado.

```powershell
Copy-Item .env.example .env
# edite .env com DB_HOST/DB_PASSWORD reais
```

Alternativamente, derive o host do estado Terraform do Assignment 1:

```powershell
$RdsHost = terraform -chdir=../../../../../assignment_1/task_1/solution_task1/grupo6/joao_vilas/terraform output -raw rds_host

@"
DB_HOST=$RdsHost
DB_PORT=3306
DB_USER=admin
DB_PASSWORD=$env:TF_VAR_db_password
DB_NAME=classicmodels
PIPELINE_NAME=classicmodels_sales
"@ | Set-Content .env
```

| Variável | Default | Descrição |
|----------|---------|-----------|
| `DB_HOST` | — (obrigatório) | Host do RDS MySQL. |
| `DB_PORT` | `3306` | Porta. |
| `DB_USER` | `admin` | Usuário. |
| `DB_PASSWORD` | — (obrigatório) | Senha (somente no `.env` local). |
| `DB_NAME` | `classicmodels` | Banco de origem. |
| `PIPELINE_NAME` | `classicmodels_sales` | Chave do pipeline na `etl_watermark`. |

## Fluxo sugerido (Task 1)

```powershell
uv sync

# 1. cria/atualiza etl_watermark com o baseline do A1
uv run python scripts/init_watermark.py

# 2. valida a origem (deve passar — origem sincronizada, sem pedidos pendentes)
uv run python scripts/validate_incremental_source.py

# 3. simula a chegada de novos pedidos
uv run python scripts/simulate_new_orders.py --count 5 --seed 42

# 4. valida novamente, agora exigindo dados pendentes
uv run python scripts/validate_incremental_source.py --expect-pending
```

Os exit codes são determinísticos: `0` quando todas as checagens passam, `1` caso contrário
— adequado para uso em CI ou em scripts encadeados.

## Detalhes de implementação

- **Idempotência do watermark:** `init_watermark.sql` usa `CREATE TABLE IF NOT EXISTS`,
  um `INSERT ... WHERE NOT EXISTS` (cria o registro só uma vez) e um `UPDATE` que apenas
  faz backfill quando a data está `NULL`. Reexecutar nunca duplica nem retrocede o watermark.
- **Simulação transacional:** `orders` + `orderdetails` são inseridos na mesma transação;
  qualquer erro faz rollback completo. Como `orders.orderNumber` no classicmodels não é
  auto-incremento, o próximo número vem de `MAX(orderNumber) + 1`.
- **Datas estritamente posteriores:** cada pedido novo recebe `orderDate` em dias úteis
  crescentes a partir de `MAX(MAX(orderDate), watermark)`, garantindo que fiquem acima do
  watermark e facilitando os testes de partição da Task 2.
- **`sales_amount` coerente:** `priceEach` vem do `MSRP` do produto e `quantityOrdered` é
  positivo, mantendo `sales_amount = quantity_ordered * price_each` (regra do A1).
- **Separação de responsabilidades:** este script **não** atualiza `etl_watermark`. O
  avanço do watermark é feito pelo job Glue da Task 2, somente após sucesso, evitando
  condição de corrida.

## O que esta tarefa NÃO faz

- Não altera o star schema no S3 (isso é Task 2).
- Não agenda o Glue (isso é Task 2).
- Não commita credenciais nem dumps completos do banco.
