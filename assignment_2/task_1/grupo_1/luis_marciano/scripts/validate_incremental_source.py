import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

def get_engine():
    user = os.getenv('DB_USER')
    password = os.getenv('DB_PASSWORD')
    host = os.getenv('DB_HOST')
    return create_engine(f"mysql+pymysql://{user}:{password}@{host}:3306/classicmodels")

def validate_source():
    engine = get_engine()
    errors = []

    try:
        with engine.connect() as conn:
            # 1 e 2. Checagem do Watermark e de nulidade
            watermark_res = conn.execute(text(
                "SELECT last_processed_order_date FROM etl_watermark WHERE pipeline_name = 'classicmodels_sales'"
            )).fetchone()
            
            if not watermark_res:
                errors.append("[FALHA] Registro 'classicmodels_sales' não encontrado na tabela etl_watermark.")
                last_processed = None
            else:
                last_processed = watermark_res[0]
                if last_processed is None:
                    errors.append("[FALHA] last_processed_order_date está NULL.")
                else:
                    print(f"[OK] Watermark lido com sucesso. Data base: {last_processed}")

            # 3. Checagem de Novos Dados (Pendências para o ETL)
            if last_processed:
                max_order_date_res = conn.execute(text("SELECT MAX(orderDate) FROM orders")).fetchone()
                max_date = max_order_date_res[0]
                
                if max_date is None or max_date <= last_processed:
                    errors.append(f"[FALHA] Não há dados novos para processar. MAX(orderDate) = {max_date}, Watermark = {last_processed}")
                else:
                    print(f"[OK] Dados incrementais detectados. Nova data máxima na origem: {max_date}")

            # 4. Integridade Mínima (Pedidos sem detalhes)
            if last_processed:
                orphans = conn.execute(text("""
                    SELECT o.orderNumber 
                    FROM orders o
                    LEFT JOIN orderdetails od ON o.orderNumber = od.orderNumber
                    WHERE o.orderDate > :watermark AND od.orderNumber IS NULL
                """), {"watermark": last_processed}).fetchall()
                
                if orphans:
                    orphan_ids = [row[0] for row in orphans]
                    errors.append(f"[FALHA] Integridade violada: {len(orphan_ids)} novos pedidos sem orderdetails. IDs: {orphan_ids}")
                else:
                    print("[OK] Todos os pedidos pendentes de extração possuem linhas de detalhe atreladas.")

    except Exception as e:
        errors.append(f"[ERRO CRÍTICO] Falha ao conectar ou consultar o banco: {e}")

    if errors:
        print("\n=== Resultado da Validação: FALHA ===")
        for err in errors:
            print(err)
        sys.exit(1)
    else:
        print("\n=== Resultado da Validação: SUCESSO ===")
        print("A origem está apta e contém dados prontos para o fluxo incremental.")
        sys.exit(0)

if __name__ == "__main__":
    validate_source()