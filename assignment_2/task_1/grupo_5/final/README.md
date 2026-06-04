# Assignment 2 — Task 1 — Grupo 5 Final

Entrega da origem incremental para o banco `classicmodels`.

## Estrutura

- `scripts/init_watermark.py`: cria e inicializa a tabela `etl_watermark`.
- `scripts/simulate_new_orders.py`: simula novos pedidos em `orders` e `orderdetails`.
- `scripts/validate_incremental_source.py`: valida watermark, pendências incrementais e integridade.
- `.env.example`: exemplo das variáveis de conexão, sem credenciais reais.

## Configuração

```bash
cd assignment_2/task_1/grupo_5/final
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edite `.env` com os dados do RDS:

```bash
DB_HOST=<endpoint-rds>
DB_PORT=3306
DB_NAME=classicmodels
DB_USER=<usuario>
DB_PASSWORD=<senha>
```

Também é possível exportar as mesmas variáveis diretamente no shell.

## Fluxo de execução

Inicialize o watermark com o histórico já carregado:

```bash
python scripts/init_watermark.py
```

Valide o estado inicial da origem:

```bash
python scripts/validate_incremental_source.py
```

Simule novos pedidos:

```bash
python scripts/simulate_new_orders.py --count 5 --seed 42
```

Valide que existem dados pendentes para o próximo ETL:

```bash
python scripts/validate_incremental_source.py --require-pending
```

## Contrato implementado

A tabela `etl_watermark` é criada com o contrato:

```sql
CREATE TABLE IF NOT EXISTS etl_watermark (
    pipeline_name VARCHAR(64) PRIMARY KEY,
    last_processed_order_date DATE,
    last_run_at DATETIME,
    last_run_status VARCHAR(32)
);
```

O registro inicial usa `pipeline_name = 'classicmodels_sales'` e `last_processed_order_date = MAX(orders.orderDate)`.

O simulador não atualiza `etl_watermark`; essa responsabilidade fica para o ETL incremental.
