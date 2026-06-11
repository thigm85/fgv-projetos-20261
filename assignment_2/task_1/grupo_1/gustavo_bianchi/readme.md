# Assignment 2 - Task 1: Origem incremental e watermark

Este diretório contém os scripts responsáveis por preparar o sistema transacional (MySQL no AWS RDS) para extrações de dados incrementais.

# Para rodar:

1. **Faça o pip install do requirements:**
   ```bash
   pip install -r requirements.txt
   ```
2. **Defina a senha do banco no PowerShell:**
   ```powershell
   $env:TF_VAR_db_password="sua_senha_segura"
   ```
3. **Defina a senha para o Python pelo Bash:**
   ```bash
   export TF_VAR_db_password="sua_senha_segura"
   ```
4. **Rode o init_watermark:**
   ```bash
   python init_watermark.py
   ```
5. **Rode o validate_incremental_source:** *(Deve dar sucesso porque não há novos pedidos)*
   ```bash
   python validate_incremental_source.py
   ```
6. **Rode o simulate_new_orders com os valores desejados para count e seed:**
   ```bash
   python simulate_new_orders.py --count 5 --seed 42
   ```
7. **Rode o validate_incremental_source novamente:** *(Deve dar sucesso confirmando que há dados pendentes para o ETL)*
   ```bash
   python validate_incremental_source.py
   ```