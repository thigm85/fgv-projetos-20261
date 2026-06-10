#!/usr/bin/env python3
import os
import sys
import pymysql
import pymysql.cursors

def load_rds_config(filename: str = "rds_connection.env") -> dict:
    current_dir = os.path.abspath(os.path.dirname(__file__))
    while current_dir:
        filepath = os.path.join(current_dir, filename)
        if os.path.isfile(filepath):
            env = {}
            with open(filepath) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, val = line.partition("=")
                        env[key.strip()] = val.strip()
            return env
        parent_dir = os.path.dirname(current_dir)
        if parent_dir == current_dir:
            break
        current_dir = parent_dir
    return {}

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Inicializa a tabela de watermark no RDS.")
    parser.add_argument("--reset", action="store_true", help="Força o reset do watermark para o baseline histórico original.")
    args = parser.parse_args()

    print("=== Inicializando Tabela de Watermark (etl_watermark) ===")
    cfg = load_rds_config()
    
    if not cfg.get("RDS_HOST"):
        print("[ERRO] Configurações do RDS não encontradas no rds_connection.env.", file=sys.stderr)
        sys.exit(1)
        
    try:
        conn = pymysql.connect(
            host=cfg.get("RDS_HOST"),
            port=int(cfg.get("RDS_PORT", 3306)),
            user=cfg.get("RDS_USER"),
            password=cfg.get("RDS_PASSWORD"),
            database=cfg.get("RDS_DB"),
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor
        )
    except Exception as e:
        print(f"[ERRO] Não foi possível conectar ao RDS: {e}", file=sys.stderr)
        sys.exit(1)
        
    try:
        with conn.cursor() as cur:
            # 1. Cria a tabela etl_watermark se não existir
            print("[INFO] Criando tabela etl_watermark se não existir...")
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS etl_watermark (
                pipeline_name VARCHAR(64) PRIMARY KEY,
                last_processed_order_date DATE,
                last_run_at DATETIME,
                last_run_status VARCHAR(32)
            );
            """
            cur.execute(create_table_sql)
            
            # 2. Verifica se a linha classicmodels_sales já existe
            cur.execute("SELECT COUNT(*) as count FROM etl_watermark WHERE pipeline_name = 'classicmodels_sales'")
            row_exists = cur.fetchone()["count"] > 0
            
            if not row_exists:
                # 3. Inicializa com o MAX(orders.orderDate) atual
                print("[INFO] Registro 'classicmodels_sales' ausente. Obtendo MAX(orderDate) da tabela orders...")
                cur.execute("SELECT MAX(orderDate) as max_date FROM orders WHERE comments IS NULL OR comments NOT LIKE '%%Simulated%%'")
                max_date = cur.fetchone()["max_date"]
                
                if max_date is None:
                    cur.execute("SELECT MAX(orderDate) as max_date FROM orders")
                    max_date = cur.fetchone()["max_date"]

                if max_date is None:
                    print("[AVISO] Tabela 'orders' está vazia ou sem datas. Usando data atual como fallback.")
                    from datetime import date
                    max_date = date.today()
                    
                print(f"[INFO] MAX(orderDate) encontrado: {max_date}. Inserindo watermark inicial...")
                insert_sql = """
                INSERT INTO etl_watermark (pipeline_name, last_processed_order_date, last_run_at, last_run_status)
                VALUES (%s, %s, NULL, 'NEVER_RUN')
                """
                cur.execute(insert_sql, ('classicmodels_sales', max_date))
                conn.commit()
                print(f"[OK] Watermark inicializado com pipeline_name = 'classicmodels_sales' e last_processed_order_date = {max_date}")
            elif args.reset:
                # Força o reset para o baseline original
                print("[INFO] Forçando reset do watermark para o baseline histórico (filtrando pedidos simulados)...")
                cur.execute("SELECT MAX(orderDate) as max_date FROM orders WHERE comments IS NULL OR comments NOT LIKE '%%Simulated%%'")
                max_date = cur.fetchone()["max_date"]
                
                if max_date is None:
                    cur.execute("SELECT MAX(orderDate) as max_date FROM orders")
                    max_date = cur.fetchone()["max_date"]
                
                if max_date is None:
                    from datetime import date
                    max_date = date(2005, 5, 31)

                update_sql = """
                UPDATE etl_watermark
                SET last_processed_order_date = %s, last_run_at = NULL, last_run_status = 'NEVER_RUN'
                WHERE pipeline_name = 'classicmodels_sales'
                """
                cur.execute(update_sql, (max_date,))
                conn.commit()
                print(f"[OK] Watermark resetado com sucesso para {max_date}")
            else:
                # Já existe, mantemos idempotência
                cur.execute("SELECT last_processed_order_date, last_run_at, last_run_status FROM etl_watermark WHERE pipeline_name = 'classicmodels_sales'")
                current_wm = cur.fetchone()
                print(f"[OK] Tabela já inicializada. Watermark atual: {current_wm}")
                
    except Exception as e:
        conn.rollback()
        print(f"[ERRO] Falha durante inicialização: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
