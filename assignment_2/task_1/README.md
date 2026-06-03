# Assignment 2 - Task 1: Origem incremental e watermark

Esta entrega prepara o banco MySQL `classicmodels` do Assignment 1 para cargas incrementais. O foco e a origem transacional: criar o controle de watermark no RDS, simular novos pedidos e validar que existem dados pendentes para a Task 2.

## Arquivos

- `scripts/db_config.py`: leitura centralizada de conexao, sem credenciais hardcoded.
- `scripts/init_watermark.py`: cria `etl_watermark` e inicializa o baseline com `MAX(orders.orderDate)`.
- `scripts/simulate_new_orders.py`: insere novos pedidos e detalhes em transacao, com suporte a `--dry-run`.
- `scripts/validate_incremental_source.py`: valida contrato, baseline, pendencias, tabelas obrigatorias e integridade minima.
- `.env.example`: exemplo de variaveis, sem senha real.

## Configuracao

Instale a dependencia Python:

```powershell
conda activate aws-data-pipeline
pip install -r assignment_2/task_1/requirements.txt
```

Defina as variaveis de conexao antes de executar os scripts:

```powershell
$env:CLASSICMODELS_DB_HOST="your-rds-endpoint.amazonaws.com"
$env:CLASSICMODELS_DB_PORT="3306"
$env:CLASSICMODELS_DB_USER="admin"
$env:CLASSICMODELS_DB_PASSWORD="sua-senha"
$env:CLASSICMODELS_DB_NAME="classicmodels"
$env:CLASSICMODELS_DB_CONNECT_RETRIES="3"
$env:CLASSICMODELS_DB_CONNECT_RETRY_DELAY="2"
```

Os mesmos valores tambem podem ser passados por CLI com `--host`, `--port`, `--user`, `--password`, `--database`, `--connect-retries` e `--connect-retry-delay`.

## Fluxo de execucao

Inicialize a tabela de watermark:

```powershell
python assignment_2/task_1/scripts/init_watermark.py
```

Valide o baseline. Antes da simulacao, pode nao existir pedido pendente:

```powershell
python assignment_2/task_1/scripts/validate_incremental_source.py
```

Simule novos pedidos. O script nao altera `etl_watermark`; isso fica para o Glue na Task 2.

```powershell
python assignment_2/task_1/scripts/simulate_new_orders.py --count 5 --seed 42
```

Para testar o plano sem gravar no banco, use `--dry-run`. A transacao e revertida ao final:

```powershell
python assignment_2/task_1/scripts/simulate_new_orders.py --count 5 --seed 42 --dry-run
```

Valide exigindo dados pendentes:

```powershell
python assignment_2/task_1/scripts/validate_incremental_source.py --require-pending
```

## Contrato do watermark

A tabela criada no banco `classicmodels` e:

```sql
CREATE TABLE IF NOT EXISTS etl_watermark (
    pipeline_name VARCHAR(64) NOT NULL PRIMARY KEY,
    last_processed_order_date DATE NOT NULL,
    last_run_at DATETIME NULL,
    last_run_status VARCHAR(32) NOT NULL
);
```

O registro inicial usa `pipeline_name = 'classicmodels_sales'`, `last_processed_order_date = MAX(orders.orderDate)`, `last_run_at = NULL` e `last_run_status = 'NEVER_RUN'`.

## Observacoes de engenharia

- Reexecucao de `init_watermark.py` e idempotente: cria a tabela se necessario e nao retrocede watermark existente.
- `simulate_new_orders.py` usa `MAX(orderNumber) + 1`, porque o dump do Assignment 1 nao define `orderNumber` como auto-increment. A maior linha de `orders` e bloqueada com `FOR UPDATE` durante a transacao para reduzir risco de conflito.
- Cada pedido simulado escolhe `customerNumber` e `productCode` existentes, grava pelo menos uma linha em `orderdetails` e preserva a regra `sales_amount = quantityOrdered * priceEach`.
- `validate_incremental_source.py` retorna exit code `0` apenas quando as checagens passam; com `--require-pending`, tambem exige `MAX(orders.orderDate) > last_processed_order_date`.
- Todos os scripts aceitam `--verbose` para logs mais detalhados e usam retry de conexao para lidar com instabilidade comum apos provisionamento do RDS.
- A exposicao da porta 3306 nao e tratada nesta task, mas a execucao pressupoe security group restrito ao IP atual (`/32`) ou acesso privado, conforme recomendado no A1.
