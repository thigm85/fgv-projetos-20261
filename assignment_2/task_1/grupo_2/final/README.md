# Assignment 2 — Task 1: Origem Incremental e Watermark

**Pipeline:** `classicmodels_sales`  
**Banco OLTP:** MySQL (AWS RDS) — banco `classicmodels`

Solução final consolidada do Grupo 2, combinando os melhores elementos das implementações individuais de cada membro.

---

## Estrutura de Arquivos

```
final/
├── scripts/
│   ├── init_watermark.py              # Cria/inicializa tabela etl_watermark
│   ├── simulate_new_orders.py         # Simula chegada de novos pedidos
│   └── validate_incremental_source.py # Valida que a origem está pronta para ETL
├── db_config.py                       # Helper de conexão com o RDS (3 fallbacks)
├── run_pipeline.sh                    # Fluxo completo de validação (4 passos)
├── .env.example                       # Template de variáveis de ambiente
├── requirements.txt                   # Dependências Python
└── README.md                          # Este arquivo
```

---

## Pré-requisitos

- Python 3.10+
- RDS MySQL ativo com o banco `classicmodels` carregado (Assignment 1)
- Credenciais configuradas (ver seção abaixo)

### Instalação de dependências

```bash
pip install -r requirements.txt
```

---

## Configuração de Credenciais

O `db_config.py` suporta **3 formas de configuração** (em ordem de prioridade):

### 1. AWS Secrets Manager (recomendado para produção)

Defina a variável de ambiente `SECRET_ARN` com o ARN do secret que contém as credenciais do RDS:

```bash
export SECRET_ARN="arn:aws:secretsmanager:us-east-1:123456789:secret:classicmodels-xyz"
export AWS_REGION="us-east-1"
```

O secret deve conter um JSON com as chaves: `host`, `port`, `username`, `password`, `dbname`.

### 2. Variáveis de ambiente (recomendado para dev)

```bash
export DB_HOST="classicmodels-db.xxxxx.us-east-1.rds.amazonaws.com"
export DB_PORT="3306"
export DB_USER="admin"
export DB_PASSWORD="..."
export DB_NAME="classicmodels"
```

> Também aceita os nomes `RDS_HOST`, `RDS_PORT`, `RDS_USER`, `RDS_PASSWORD`, `RDS_DB` para compatibilidade com o Assignment 1.

### 3. Arquivo `.env` (fallback local)

Copie o template e preencha:

```bash
cp .env.example .env
# edite .env com seu editor preferido
```

| Variável      | Descrição                   | Exemplo                                    |
|---------------|-----------------------------|--------------------------------------------|
| `DB_HOST`     | Endpoint do RDS             | `myrds.abcdef.us-east-1.rds.amazonaws.com` |
| `DB_PORT`     | Porta MySQL (default: 3306) | `3306`                                     |
| `DB_USER`     | Usuário do banco            | `admin`                                    |
| `DB_PASSWORD` | Senha                       | `secret`                                   |
| `DB_NAME`     | Nome do banco               | `classicmodels`                            |

> ⚠️ **Não commitar senhas ou o arquivo `.env` no repositório.**

---

## Uso

### 1. Inicializar Watermark

Cria a tabela `etl_watermark` e insere o registro baseline com `MAX(orders.orderDate)`:

```bash
python scripts/init_watermark.py
```

**Idempotente** — pode re-executar sem problemas:
- Se o registro não existir: cria com `MAX(orderDate)` como watermark.
- Se existir com watermark NULL: atualiza.
- Se existir com watermark preenchido: **não sobrescreve** (preserva progresso real de execuções ETL).

### 2. Simular Novos Pedidos

```bash
# 5 pedidos (default), sem seed
python scripts/simulate_new_orders.py

# 10 pedidos com seed para reprodutibilidade
python scripts/simulate_new_orders.py --count 10 --seed 42

# Preview sem inserir (dry-run)
python scripts/simulate_new_orders.py --count 5 --dry-run
```

**Parâmetros:**

| Flag        | Descrição                          | Default |
|-------------|------------------------------------|---------|
| `--count N` | Número de pedidos a criar          | `5`     |
| `--seed S`  | Seed para reprodutibilidade        | `None`  |
| `--dry-run` | Preview sem inserir no banco       | `False` |

**O que o simulador faz:**

- Escolhe `customerNumber` e `productCode` **existentes** no banco
- Insere em `orders` com `orderDate` estritamente posterior ao watermark/MAX(orderDate)
- Usa datas em **dias úteis** (seg–sex) para facilitar testes de particionamento na Task 2
- Insere linhas em `orderdetails` com `priceEach` entre `buyPrice` e `MSRP` (regra de negócio)
- Garante `quantityOrdered * priceEach > 0` (consistência com `sales_amount` do A1)
- Varia status entre `In Process` (60%), `Shipped` (30%), `On Hold` (10%)
- Preenche `shippedDate` para pedidos com status `Shipped`
- Usa transações atômicas (orders + orderdetails)
- Usa `SELECT ... FOR UPDATE` para concorrência segura no `orderNumber`
- **NÃO** atualiza `etl_watermark` (responsabilidade do Glue na Task 2)

### 3. Validar Origem Incremental

```bash
python scripts/validate_incremental_source.py
```

**5 checks executados:**

| # | Check              | Critério                                                       |
|---|--------------------|----------------------------------------------------------------|
| 1 | Tabela existe      | `etl_watermark` + registro `classicmodels_sales` presentes     |
| 2 | Watermark não NULL | `last_processed_order_date` tem valor                          |
| 3 | Dados pendentes    | `MAX(orderDate) > watermark` (informativo, não falha se limpo) |
| 4 | Integridade        | Todo `orderNumber` tem linhas em `orderdetails`                |
| 5 | Consistência       | `quantityOrdered > 0` e `priceEach > 0` em `orderdetails`     |

Exit code `0` = todas as checagens passaram. Exit code `1` = falha.

---

## Fluxo Completo (recomendado)

```bash
bash run_pipeline.sh
```

Ou com parâmetros personalizados:

```bash
bash run_pipeline.sh --count 10 --seed 42
```

Executa os 4 passos do fluxo sugerido no enunciado:

```
1. init_watermark              → cria/atualiza etl_watermark com baseline
2. validate_incremental_source → deve passar (baseline coerente)
3. simulate_new_orders         → insere pedidos novos
4. validate_incremental_source → deve passar (há dados pendentes)
```

---

## Tabela `etl_watermark`

| Coluna                      | Tipo            | Descrição                                                         |
|-----------------------------|-----------------|-------------------------------------------------------------------|
| `pipeline_name`             | `VARCHAR(64)` PK| Identificador do pipeline. Valor: `classicmodels_sales`           |
| `last_processed_order_date` | `DATE`          | Maior `orderDate` já refletida no lake analítico                  |
| `last_run_at`               | `DATETIME`      | Timestamp UTC da última execução bem-sucedida do ETL (Task 2)     |
| `last_run_status`           | `VARCHAR(32)`   | `SUCCEEDED`, `FAILED` ou `NEVER_RUN`                             |

---

## O que esta tarefa NÃO faz

- Não altera o star schema no S3 (isso é Task 2)
- Não agenda o Glue (isso é Task 2)
- Não commita credenciais ou dumps completos do banco

---

## Notas de Design

- **Idempotência:** `init_watermark.py` usa `CREATE TABLE IF NOT EXISTS` e `INSERT ... ON DUPLICATE KEY UPDATE` com lógica condicional — preserva progresso real de ETL.
- **Reprodutibilidade:** `simulate_new_orders.py --seed N` garante o mesmo conjunto de pedidos para demos e testes.
- **Integridade:** cada pedido simulado usa `customerNumber` e `productCode` existentes; inserção de `orders` e `orderdetails` ocorre numa mesma transação atômica.
- **Consistência com star schema:** `priceEach` entre `buyPrice` e `MSRP` garante que `quantityOrdered * priceEach` é coerente com `sales_amount`.
- **Datas úteis:** pedidos são agendados em dias úteis (seg–sex) para facilitar testes de particionamento na Task 2.
- **Concorrência:** `SELECT ... FOR UPDATE` evita colisão de `orderNumber` em execuções paralelas.
- **Flexibilidade de credenciais:** 3 fontes (Secrets Manager → env vars → .env file) com fallback automático.

---
