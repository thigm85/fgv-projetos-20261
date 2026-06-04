# Assignment 2 - Task 1: Origem incremental e watermark

Solucao do grupo 3 para preparar o RDS `classicmodels` para cargas incrementais.

## Estrutura

```text
final/
|- README.md
|- requirements.txt
|- scripts/
|  |- .env.example
|  |- env_loader.py
|  |- db.py
|  |- init_watermark.py
|  |- simulate_new_orders.py
|  |- validate_incremental_source.py
```

## Pre-requisitos

- RDS do Assignment 1 ativo e carregado com o banco `classicmodels`.
- Python 3.10+.
- Acesso de rede ao endpoint do RDS.

Instale a dependência:

```powershell
cd "assignment_2\task_1\grupo_3\final"
pip install -r requirements.txt
```

## Seguranca e variveis de conexão

Preferir RDS privado. Restrinja `allowed_cidr` ao seu IP `/32`.

Use variáveis de ambiente:

```powershell
$env:DB_HOST = "SEU_ENDPOINT_RDS"
$env:DB_PORT = "3306"
$env:DB_USER = "SEU_USUARIO"
$env:DB_PASSWORD = "SUA_SENHA"
$env:DB_NAME = "classicmodels"
```

Ou crie um `.env` local ignorado pelo git:

```powershell
Copy-Item .\scripts\.env.example .\scripts\.env
```

Edite `scripts\.env` com endpoint, usuario e senha.

As camadas de segurança aplicadas seguem a mesma estratégia da origem criada no Assignment 1. Na camada de rede, o RDS deve ser privado, a regra de entrada deve ficar limitada ao IP em `/32`. Na camada de transporte, os scripts de conexão usam TLS para falar com o MySQL. Na camada de segredos, credenciais ficam em variáveis de ambiente ou em `.env` local ignorado pelo git. Na camada operacional, a simulação incremental não altera o watermark, reduzindo risco de corrida com o ETL.

## Fluxo de execução

Inicializar a tabela `etl_watermark`:

```powershell
python .\scripts\init_watermark.py
```

Validar o baseline:

```powershell
python .\scripts\validate_incremental_source.py
```

Simular novos pedidos:

```powershell
python .\scripts\simulate_new_orders.py --count 5 --seed 42
```

Validar que existem pedidos pendentes de ETL:

```powershell
python .\scripts\validate_incremental_source.py --require-pending
```

## Contrato implementado

- Tabela `etl_watermark` com `pipeline_name`, `last_processed_order_date`, `last_run_at` e `last_run_status`.
- Registro fixo `classicmodels_sales`.
- `last_processed_order_date` inicializado com `MAX(orders.orderDate)`.
- A simulação cria pedidos em `orders` e linhas em `orderdetails` com `orderDate` posterior ao maior valor entre watermark e data maxima atual.
- A simulação nao atualiza `etl_watermark`;
- A validação retorna exit code `0` somente quando as checagens obrigatórias passam.
