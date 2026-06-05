# Assignment 2 — Task 1: Origem Incremental e Watermark

Pipeline: **classicmodels_sales**  
Banco OLTP: MySQL (AWS RDS) — banco `classicmodels`

---

## Estrutura de arquivos

```
task_1/
├── scripts/
│   ├── init_watermark.py              # Cria tabela e registro inicial
│   ├── simulate_new_orders.py         # Simula chegada de novos pedidos
│   └── validate_incremental_source.py # Valida a origem antes do ETL
├── .env.example                       # Template de variáveis de ambiente
├── requirements.txt
└── README.md
```

---

## Pré-requisitos

- Python 3.10+
- Acesso à instância RDS com o banco `classicmodels` do Assignment 1
- Liberação de Security Group na porta 3306 para a máquina local

### Instalação de dependências

```bash
pip install -r requirements.txt
```

---

## Configuração de variáveis de ambiente

Copie o template e preencha com suas credenciais:

```bash
cp .env.example .env
# edite .env com seu editor preferido
```

| Variável      | Descrição                                | Exemplo                              |
|---------------|------------------------------------------|--------------------------------------|
| `DB_HOST`     | Endpoint do RDS                          | `myrds.abcdef.us-east-1.rds.amazonaws.com` |
| `DB_PORT`     | Porta MySQL (default: 3306)              | `3306`                               |
| `DB_USER`     | Usuário do banco                         | `admin`                              |
| `DB_PASSWORD` | Senha                                    | `secret`                             |
| `DB_NAME`     | Nome do banco                            | `classicmodels`                      |

> O arquivo `.env` está no `.gitignore`.

---

## Fluxo de execução (Task 1)

Execute os passos na ordem abaixo:

### 1. Inicializar watermark

Cria a tabela `etl_watermark` (se não existir) e insere o registro inicial com
`last_processed_order_date = MAX(orders.orderDate)` do banco histórico.

```bash
python scripts/init_watermark.py
```

---

### 2. Validar origem (antes da simulação)

Verifica que a tabela e o registro existem e que não há pedidos pendentes ainda.

```bash
python scripts/validate_incremental_source.py
```

Saída esperada neste ponto:
- Check 1: tabela existe
- Check 2: registro com data não-nula
- Check 3: sem dados novos (normal — nenhuma simulação rodou ainda)

> O script retorna **exit code 1** se qualquer check falhar.

---

### 3. Simular novos pedidos

Insere pedidos sintéticos com `orderDate` posterior ao watermark atual.

```bash
# 5 pedidos (default)
python scripts/simulate_new_orders.py

# 10 pedidos com semente fixa para reprodutibilidade
python scripts/simulate_new_orders.py --count 10 --seed 42
```

**Argumentos:**

| Argumento | Tipo | Default | Descrição |
|-----------|------|---------|-----------|
| `--count` | int  | `5`     | Número de pedidos a criar |
| `--seed`  | int  | `None`  | Semente aleatória (reprodutibilidade) |

**Exemplo de saída:**
```
============================================================
RESUMO — 5 pedido(s) criado(s)
  IDs: [10426, 10427, 10428, 10429, 10430]
  Faixa de datas: 2005-06-02  →  2005-06-08
  Total de linhas em orderdetails: 11
============================================================
```

> O script **não** atualiza `etl_watermark` — isso é responsabilidade do job Glue (Task 2).

---

### 4. Validar origem (após simulação)

```bash
python scripts/validate_incremental_source.py
```

Saída esperada agora:
- Check 1: tabela existe
- Check 2: registro com data não-nula
- Check 3: `MAX(orderDate) > watermark` — dados pendentes detectados
- Check 4: todos os pedidos novos têm linhas em orderdetails

Exit code **0** = origem pronta para o ETL da Task 2.

---

## Tabela `etl_watermark`

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `pipeline_name` | `VARCHAR(64)` PK | Identificador do pipeline. Valor: `classicmodels_sales` |
| `last_processed_order_date` | `DATE` | Maior `orderDate` já refletida no lake analítico |
| `last_run_at` | `DATETIME` | Timestamp UTC da última execução bem-sucedida do ETL (atualizado na Task 2) |
| `last_run_status` | `VARCHAR(32)` | `SUCCEEDED`, `FAILED` ou `NEVER_RUN` |

---

## Notas de design

- **Idempotência:** `init_watermark.py` usa `CREATE TABLE IF NOT EXISTS` e `INSERT ... ON DUPLICATE KEY UPDATE`, podendo ser executado múltiplas vezes sem corromper dados.
- **Reprodutibilidade:** `simulate_new_orders.py --seed N` garante o mesmo conjunto de pedidos para demos e testes.
- **Integridade:** cada pedido simulado usa `customerNumber` e `productCode` existentes; inserção de `orders` e `orderdetails` ocorre numa mesma transação.
- **Consistência com star schema:** `quantityOrdered * priceEach` equivale ao `sales_amount` calculado no A1.
- **Datas úteis:** pedidos são agendados em dias úteis (seg–sex) para facilitar testes de particionamento na Task 2.
