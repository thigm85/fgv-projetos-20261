# Assignment 2 — Task 1: Origem incremental e watermark

## 1 — Introdução

No [Assignment 1](../../assignment_1/), você construiu um pipeline batch que carrega o histórico completo do banco `classicmodels` (MySQL no RDS) para um esquema estrela no S3. Na prática, o negócio continua vendendo: novos pedidos entram no OLTP todos os dias.

Nesta tarefa você prepara o **sistema de origem** para cargas incrementais:

- Metadados de controle (**watermark**) no próprio RDS.
- Scripts para **simular** a chegada de novos pedidos (sem depender de dados externos).
- Validação reprodutível de que a origem está pronta para o ETL da Task 2.

O contexto de negócio permanece o da loja de modelos clássicos ([MySQL Sample Database](https://www.mysqltutorial.org/mysql-sample-database.aspx)).

## 2 — Contexto e premissas

- Você reutiliza a instância RDS e o banco `classicmodels` do Assignment 1.
- O ETL da Task 2 continuará extraindo via **Glue JDBC**; esta tarefa **não** exporta CSV para o S3 como etapa principal.
- O watermark deste laboratório é baseado na data do pedido: coluna `orders.orderDate` (tipo `DATE` ou `DATETIME` conforme seu dump).

## 3 — Task 1: Metadados e simulação incremental

### 3.1 — Tabela de watermark

Crie no banco `classicmodels` uma tabela de controle com o contrato mínimo abaixo (nomes fixos para avaliação):

**Tabela:** `etl_watermark`

| Coluna | Tipo sugerido | Descrição |
|--------|---------------|-----------|
| `pipeline_name` | `VARCHAR(64)` PK | Identificador do pipeline. Use **`classicmodels_sales`**. |
| `last_processed_order_date` | `DATE` | Maior `orderDate` já refletida no lake analítico. |
| `last_run_at` | `DATETIME` | Timestamp UTC da última execução bem-sucedida do ETL (atualizado na Task 2). |
| `last_run_status` | `VARCHAR(32)` | Ex.: `SUCCEEDED`, `FAILED`, `NEVER_RUN`. |

**3.1.1.** Forneça um script SQL ou Python idempotente (`scripts/init_watermark.py` ou `sql/init_watermark.sql`) que:

1. Cria a tabela se não existir.
2. Insere o registro inicial `pipeline_name = 'classicmodels_sales'` se ausente.
3. Inicializa `last_processed_order_date` com o `MAX(orders.orderDate)` **atual** do banco (carga histórica já refletida após o A1).

### 3.2 — Simulação de novos pedidos

Implemente `scripts/simulate_new_orders.py` (ou nome equivalente documentado no README) que:

**3.2.1.** Aceita parâmetros configuráveis (argumentos CLI ou variáveis de ambiente), no mínimo:

- `--count` (número de pedidos a criar; default sugerido: `5`)
- `--seed` (opcional, para reprodutibilidade de demos)

**3.2.2.** Para cada pedido simulado:

1. Escolhe um `customerNumber` e `productCode` **existentes** no banco.
2. Insere uma linha em `orders` com `orderDate` **estritamente posterior** ao watermark atual (ou à data máxima existente, o que for maior).
3. Insere pelo menos uma linha em `orderdetails` coerente (`quantityOrdered`, `priceEach`, `orderLineNumber`).
4. Garante que `quantityOrdered * priceEach` é consistente com a regra de negócio usada no A1 para `sales_amount`.

**3.2.3.** Não atualiza `etl_watermark` neste script — a atualização do watermark é responsabilidade do job Glue na Task 2 (evita condição de corrida).

**3.2.4.** Imprime resumo ao final: IDs dos pedidos criados, faixa de datas, contagem de linhas em `orderdetails`.

### 3.3 — Validação da origem

Implemente `scripts/validate_incremental_source.py` que verifica:

1. A tabela `etl_watermark` existe e contém o registro `classicmodels_sales`.
2. `last_processed_order_date` não é `NULL` após inicialização.
3. Após executar a simulação, `MAX(orders.orderDate) > last_processed_order_date` (ou seja, há dados novos pendentes de ETL).
4. Integridade mínima: pedidos simulados possuem linhas em `orderdetails`.

O script deve retornar **código de saída 0** apenas se todas as checagens passarem.

## 4 — Fluxo sugerido (Task 1)

```text
1. init_watermark     → cria/atualiza etl_watermark com baseline do A1
2. validate_incremental_source → deve passar (sem pedidos pendentes OU baseline coerente)
3. simulate_new_orders --count N → insere pedidos novos
4. validate_incremental_source → deve passar com “há dados pendentes”
```

Documente esse fluxo no `README.md` do grupo.

## 5 — Critérios mínimos de conclusão da Task 1

1. Tabela `etl_watermark` criada com o contrato especificado.
2. Script de simulação idempotente em estrutura (reexecução não corrompe o banco; pode criar novos pedidos a cada run).
3. Script de validação com exit code determinístico.
4. README com variáveis de conexão (sem senhas commitadas) e exemplos de comando.

## 6 — O que não fazer nesta tarefa

- Não alterar o star schema no S3 (isso é Task 2).
- Não agendar o Glue (isso é Task 2).
- Não commitar credenciais ou dumps completos do banco.

## 7 — Dicas

- Use transações ao inserir `orders` + `orderdetails`.
- Se o `orderNumber` for auto-increment, use `LAST_INSERT_ID()` ou equivalente.
- Mantenha `orderDate` em dias úteis recentes para facilitar testes de partição na Task 2.
