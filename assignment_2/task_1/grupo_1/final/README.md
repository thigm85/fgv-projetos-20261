## Task 1 - Simulação de Ambiente Incremental e Watermark

### Variáveis de Ambiente Necessárias
Crie um arquivo `.env` na raiz da pasta `sql/` (ou do diretório onde for executar os scripts) contendo as credenciais de acesso ao RDS provisionado no Assignment 1:

DB_HOST=endereço-do-seu-rds.us-east-1.rds.amazonaws.com
DB_USER=admin
DB_PASSWORD=sua_senha_segura
DB_PORT=3306
DB_NAME=classicmodels

*(Nota: O arquivo `.env` deve ser incluído no `.gitignore` e nunca committado)*

### Fluxo de Execução

1. **Inicializar o controle de metadados (Watermark):**
   Cria a tabela de controle e registra a data máxima dos pedidos históricos como a linha de base para futuras extrações.
   ```bash
   python scripts/init_watermark.py

2. Validar ausência de dados pendentes:
    Apenas para garantir que o watermark foi alinhado com a carga existente. O comando deve falhar (exit code 1) relatando "Não há dados novos para processar".

    ```bash
    python scripts/validate_incremental_source.py

3. Simular novos pedidos na Origem:
    Gera novos registros nas tabelas orders e orderdetails respeitando a integridade referencial e empurrando as datas para além da linha de base atual.

    ```bash
    python scripts/simulate_new_orders.py --count 10

4. Validar pendência e integridade:
    Confirma que os dados foram gerados corretamente e que a origem está pronta para o extrator Glue JDBC. O código de saída deve ser 0 (Sucesso).

    ```bash
    python scripts/validate_incremental_source.py