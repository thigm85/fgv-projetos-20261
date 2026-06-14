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