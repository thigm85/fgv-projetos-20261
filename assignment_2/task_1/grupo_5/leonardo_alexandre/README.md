# Assignment 2 — Task 1: Origem incremental e watermark

Solução do **Grupo 5** (Leonardo Alexandre) para o enunciado em `assignment_2/task_1/incremental_source.md`.

Prepara o RDS `classicmodels` (Assignment 1) para cargas incrementais via tabela `etl_watermark` e simulação de novos pedidos.

## Estrutura

```text
grupo_5/leonardo_alexandre/
├── config.py
├── db.py
├── requirements.txt
├── .env.example
├── sql/init_watermark.sql
└── scripts/
    ├── init_watermark.py
    ├── simulate_new_orders.py
    └── validate_incremental_source.py
```

## Pré-requisitos

1. RDS MySQL do Assignment 1 rodando com banco `classicmodels` populado.
2. Credenciais em `.env` (copie de `.env.example`).

Variáveis suportadas:

| Variável | Descrição |
|----------|-----------|
| `DB_HOST` | Endpoint do RDS |
| `DB_PORT` | Porta (default `3306`) |
| `DB_NAME` | Banco (default `classicmodels`) |
| `DB_USER` | Usuário |
| `DB_PASSWORD` | Senha (**não commitar**) |

## Instalação

```bash
cd assignment_2/task_1/grupo_5/leonardo_alexandre
python -m venv .venv
# Windows:
.venv\Scripts\activate
pip install -r requirements.txt
```

## Fluxo sugerido

```bash
# 1. Criar watermark com baseline do Assignment 1
python scripts/init_watermark.py

# 2. Validar origem (baseline coerente, sem pendências)
python scripts/validate_incremental_source.py --require-no-pending

# 3. Simular novos pedidos
python scripts/simulate_new_orders.py --count 5 --seed 42

# 4. Validar origem (há dados pendentes de ETL)
python scripts/validate_incremental_source.py --require-pending
```

## Tabela `etl_watermark`

| Coluna | Descrição |
|--------|-----------|
| `pipeline_name` | PK fixa: `classicmodels_sales` |
| `last_processed_order_date` | Maior `orderDate` já refletida no lake |
| `last_run_at` | UTC da última execução ETL (Task 2) |
| `last_run_status` | `SUCCEEDED`, `FAILED`, `NEVER_RUN` |

O script `simulate_new_orders.py` **não** atualiza o watermark (evita condição de corrida; o Glue faz isso na Task 2).

## Critérios atendidos

1. Tabela `etl_watermark` com contrato do enunciado.
2. Simulação idempotente em estrutura (cada execução pode criar novos pedidos sem corromper o banco).
3. Validação com exit code `0`/`1`.
4. README com variáveis e exemplos (sem senhas).
