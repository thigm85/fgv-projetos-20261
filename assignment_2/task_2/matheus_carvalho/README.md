# Assignment 2 — Task 2: ETL Incremental, Partições e Agendamento

Este diretório contém a implementação completa da **Task 2** do Assignment 2. O pipeline do Assignment 1 foi evoluído para suportar processamento incremental (via watermark), particionamento Hive-style e agendamento automático na AWS.

---

## 📁 Estrutura do Projeto

```
matheus_carvalho/
├── glue/
│   └── etl_job.py          # Script do AWS Glue em PySpark com a lógica incremental
├── terraform/
│   ├── main.tf             # Recursos do EventBridge, Glue Job, Connections e Catalog
│   ├── variables.tf        # Definição das variáveis de entrada
│   ├── versions.tf         # Provedores e versões necessárias (AWS >= 5.0)
│   └── terraform.tfvars.example # Template de exemplo para variáveis
├── run_pipeline_t2.sh      # Script bash interativo para execução e validação completa
└── README.md               # Este arquivo
```

---

## 🛠️ Detalhes Técnicos da Implementação

### 1. Lógica Incremental (PySpark)
O job Glue (`etl_job.py`) executa as seguintes etapas:
- **Leitura do Watermark**: Conecta ao RDS MySQL via JDBC, consulta a tabela `etl_watermark` e recupera o valor `last_processed_order_date` do pipeline `classicmodels_sales`.
- **Carga Incremental**: Filtra a tabela de origem `orders` com a cláusula `orderDate > last_processed_order_date`. Se nenhuma linha nova for encontrada, atualiza apenas o timestamp da execução como `SUCCEEDED` no RDS e encerra a execução rapidamente para economizar recursos.
- **Dimensões**: Reprocessadas e salvas por completo usando o modo `overwrite` (estratégia simples e recomendada para tabelas de dimensões pequenas).
- **Fato Particionada**: A tabela `fact_orders` é salva particionada no formato Hive-style:
  ```
  s3://<bucket>/analytics/fact_orders/order_year=YYYY/order_month=MM/
  ```
- **Dynamic Partition Overwrite**: Para evitar perda de dados históricos nas partições tocadas, o PySpark identifica quais partições `(ano, mês)` contêm registros novos no delta, lê os registros históricos dessas partições no S3, realiza a união (merge) dos dados e remove duplicatas com base nos IDs (`order_id`, `product_id`). Por fim, escreve as partições afetadas usando o modo `dynamic` do Spark.
- **Transação do Watermark**: Se o processamento for bem-sucedido, calcula o `MAX(orderDate)` inserido e executa um `UPDATE` no RDS registrando a data final do lote, a hora UTC e o status `SUCCEEDED`. Se falhar, registra o status `FAILED` sem avançar a data. A atualização de banco é feita diretamente via JDBC Java dentro da JVM do Spark (eliminando a necessidade de pacotes Python externos).

### 2. Infraestrutura (Terraform)
O arquivo `main.tf` define de forma declarativa:
- **EventBridge Cron Rule**: Cria uma regra cron configurada para disparar toda segunda-feira às 12:00 UTC: `cron(0 12 ? * MON *)`.
- **EventBridge Target**: Dispara o Glue Job criado. Utiliza a role existente `LabRole` para ter permissões de invocação (`glue:StartJobRun`).
- **Glue Connection**: Conexão JDBC utilizando as propriedades extraídas automaticamente da instância RDS ativa (`classicmodels-db`) via Data Source Terraform.
- **Catalog Database e Tables**: Define o banco de dados `classicmodels_analytics` e as tabelas catalogadas, declarando explicitamente as chaves de partição (`order_year` e `order_month` como `int`) para que o Athena reconheça a partição nativamente.

---

## 🚀 Como Executar e Validar (Passo a Passo)

### Pré-requisitos
- Ter o RDS populado e as credenciais atualizadas no terminal.
- Certificar-se de ter o AWS CLI configurado e logado.

### Executando tudo via Script de Validação Interativa
Criamos o script `run_pipeline_t2.sh` que faz todo o trabalho de forma sequencial e controlada. **Ele não roda nada escondido**, exibindo o log de cada etapa:

1. **Execute o script de testes na pasta atual:**
   ```bash
   ./run_pipeline_t2.sh
   ```

2. **O que o script faz por baixo dos panos:**
   - **Terraform Init & Apply**: Inicializa e cria o Bucket S3, Glue Connection, Glue Job, regras do EventBridge e o Catálogo do Glue.
   - **Watermark Init**: Configura o watermark no RDS com o baseline histórico (`2005-05-31`).
   - **Glue Run 1 (Carga de Histórico)**: Inicia o Job Glue via AWS CLI e aguarda a finalização (deve demorar cerca de 2-3 minutos). Valida que o watermark no banco não mudou (pois processou o histórico até a data máxima atual).
   - **Simulação de Vendas**: Roda o simulador da Task 1 inserindo 5 novos pedidos em datas futuras (ex: maio de 2026).
   - **Glue Run 2 (Carga Incremental)**: Executa o Job Glue novamente. O Job detecta apenas os 5 pedidos novos.
   - **Validação de Resultados**: 
     - Verifica se o watermark no RDS avançou para a data do último pedido simulado (`2026-05-15`).
     - Lista o bucket S3 exibindo a nova estrutura de partições (`order_year=2026/order_month=05`).

---

## 🛠️ Comandos Manuais (Alternativa)
Se preferir rodar cada comando manualmente:

```bash
# 1. Configurar infraestrutura
cd terraform
terraform init
terraform apply -auto-approve
cd ..

# 2. Inicializar Watermark no RDS (A partir da pasta da Task 1)
cd ../task_1/grupo_2/final
python3 scripts/init_watermark.py

# 3. Disparar primeiro Job Glue (Carga Histórica)
aws glue start-job-run --job-name "classicmodels-incremental-etl-job"

# 4. Verificar status do run
aws glue get-job-run --job-name "classicmodels-incremental-etl-job" --run-id <RUN_ID>

# 5. Simular novas compras (Task 1)
python3 scripts/simulate_new_orders.py --count 5 --seed 42

# 6. Disparar segundo Job Glue (Incremental)
aws glue start-job-run --job-name "classicmodels-incremental-etl-job"

# 7. Verificar se watermark avançou no MySQL do RDS
# (Acesse o MySQL e rode: SELECT * FROM etl_watermark;)
```
