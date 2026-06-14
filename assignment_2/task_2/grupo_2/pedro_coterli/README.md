## Execução da task 1 (origem incremental)

Para configurar e simular a origem incremental, defina as variáveis de ambiente com as credenciais do seu banco RDS:

```bash
export DB_HOST="seu-endpoint-rds.amazonaws.com"
export DB_USER="admin"
export DB_PASS="sua_senha"
export DB_NAME="classicmodels"
```

Em seguida, execute o fluxo sugerido:

1. Inicializar o Watermark:

```bash
python scripts/init_watermark.py
```

2. Validar o estado inicial (deve falhar intencionalmente, pois não há pedidos novos ainda):

```bash
python scripts/validate_incremental_source.py
```

3. Simular novos pedidos:

```bash
python scripts/simulate_new_orders.py --count 5 --seed 42
```

4. Validar a origem (agora deve retornar sucesso):

```bash
python scripts/validate_incremental_source.py
```

**Permissões do EventBridge:**
Devido à restrição do ambiente AWS Academy (LabRole fixa), configuramos o `aws_cloudwatch_event_target` para utilizar a própria `LabRole` (`data.aws_iam_role.lab_role.arn`). O ambiente do Academy já provê as permissões necessárias de `glue:StartJobRun` embutidas nesta role, permitindo a correta invocação do job.

### Evidências da Carga Incremental (Task 2)

Para comprovar o funcionamento correto do pipeline incremental, simulamos a entrada de novos pedidos no banco de dados e disparamos o Job do AWS Glue. Abaixo estão os logs de execução que comprovam que apenas os dados novos (posteriores ao `last_processed_order_date`) foram extraídos, e que a quantidade de registros na tabela fato é perfeitamente coerente com os pedidos gerados.

**1. Log de Simulação de Vendas (Origem):**
```text
--- Resumo da simulação ---
Pedidos criados: 5
IDs dos pedidos: [10431, 10432, 10433, 10434, 10435]
Faixa de datas: 2005-06-14 a 2005-06-28
Linhas criadas em orderdetails: 12

2026-06-13 16:13:10 [INFO] Passo 4/4 - Iniciando validação de dados...
2026-06-13 16:13:11 [INFO]  -> Tabela encontrada: 'dim_customers' (1 arquivo(s))
2026-06-13 16:13:12 [INFO]  -> Tabela encontrada: 'dim_products' (1 arquivo(s))
2026-06-13 16:13:12 [INFO]  -> Tabela encontrada: 'dim_dates' (1 arquivo(s))
2026-06-13 16:13:13 [INFO]  -> Tabela encontrada: 'dim_countries' (1 arquivo(s))
2026-06-13 16:13:14 [INFO]  -> Tabela encontrada: 'fact_orders' (2 arquivo(s))
2026-06-13 16:13:19 [INFO]  -> Tabela fato populada (12 registros).
2026-06-13 16:13:19 [INFO]  -> Integridade OK: Todos os product_id são válidos.
2026-06-13 16:13:19 [INFO]  -> Integridade OK: Todos os customer_id são válidos.
2026-06-13 16:13:19 [INFO]  -> Regra de negócio OK: sales_amount consistente em toda a base.
2026-06-13 16:13:19 [INFO] === ETL CONCLUÍDO COM SUCESSO ===
```

**Conclusão da validação:** Como evidenciado pelos logs acima, o número de linhas novas validadas na tabela fact_orders no S3 corresponde exatamente ao número de itens criados em orderdetails durante a simulação. Isso prova que o filtro incremental pelo watermark processou exclusivamente o delta de dados novos, adicionando as partições de mês/ano corretamente.