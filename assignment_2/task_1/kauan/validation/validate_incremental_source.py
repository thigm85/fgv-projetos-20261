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
    print("=== Validando Origem Incremental ===")
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

    failures = 0

    try:
        with conn.cursor() as cur:
            # 1. Verificar se a tabela etl_watermark existe
            cur.execute("""
                SELECT COUNT(*) as count FROM information_schema.tables 
                WHERE table_schema = %s AND table_name = 'etl_watermark'
            """, (cfg.get("RDS_DB"),))
            if cur.fetchone()["count"] > 0:
                print("[OK] Tabela etl_watermark encontrada no banco de dados.")
            else:
                print("[FALHA] Tabela etl_watermark não existe no banco de dados.")
                failures += 1

            # 2. Verificar se o registro classicmodels_sales existe e se last_processed_order_date não é NULL
            watermark_date = None
            if failures == 0:
                cur.execute("SELECT last_processed_order_date, last_run_status FROM etl_watermark WHERE pipeline_name = 'classicmodels_sales'")
                row = cur.fetchone()
                if row:
                    watermark_date = row["last_processed_order_date"]
                    status = row["last_run_status"]
                    if watermark_date is not None:
                        print(f"[OK] Registro 'classicmodels_sales' encontrado. Watermark: {watermark_date}, Status: {status}")
                        if status == 'FAILED':
                            print("[AVISO] A última execução do ETL falhou (status: FAILED)!")
                    else:
                        print("[FALHA] last_processed_order_date está nulo para 'classicmodels_sales'.")
                        failures += 1
                else:
                    print("[FALHA] Registro 'classicmodels_sales' não encontrado na tabela etl_watermark.")
                    failures += 1

            # 3. Comparar MAX(orders.orderDate) com last_processed_order_date
            if watermark_date is not None:
                cur.execute("SELECT MAX(orderDate) as max_date FROM orders")
                max_order_date = cur.fetchone()["max_date"]
                
                if max_order_date is None:
                    print("[FALHA] Não foi possível obter o MAX(orderDate) da tabela orders (tabela vazia?).")
                    failures += 1
                elif max_order_date < watermark_date:
                    print(f"[FALHA] Data máxima em orders ({max_order_date}) é anterior ao watermark ({watermark_date})!")
                    failures += 1
                elif max_order_date > watermark_date:
                    print(f"[OK] Há dados novos pendentes de ETL: MAX(orderDate) {max_order_date} > watermark {watermark_date}")
                else:
                    print(f"[OK] Base de dados coerente. Nenhum dado pendente: MAX(orderDate) {max_order_date} == watermark {watermark_date}")

            # 4. Integridade mínima: verificar se pedidos simulados (com data posterior ao watermark) possuem linhas em orderdetails
            if watermark_date is not None:
                query_orphans = """
                    SELECT o.orderNumber
                    FROM orders o
                    LEFT JOIN orderdetails od ON o.orderNumber = od.orderNumber
                    WHERE o.orderDate > %s AND od.orderNumber IS NULL
                """
                cur.execute(query_orphans, (watermark_date,))
                orphans = cur.fetchall()
                if not orphans:
                    print("[OK] Todos os pedidos simulados (com data posterior ao watermark) possuem itens na tabela orderdetails.")
                else:
                    orphan_ids = [r["orderNumber"] for r in orphans]
                    print(f"[FALHA] Encontrados {len(orphan_ids)} pedidos novos/simulados sem itens em orderdetails: {orphan_ids}")
                    failures += 1

    except Exception as e:
        print(f"[ERRO] Falha ao executar verificações: {e}", file=sys.stderr)
        failures += 1
    finally:
        conn.close()

    if failures == 0:
        print("\n[SUCESSO] Todas as validações da origem passaram!")
        sys.exit(0)
    else:
        print(f"\n[ERRO] {failures} validação(ões) falharam.")
        sys.exit(1)

if __name__ == "__main__":
    main()
