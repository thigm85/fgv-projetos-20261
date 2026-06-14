import os
import sys
import pymysql

def get_connection():
    return pymysql.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        user=os.environ.get('DB_USER', 'root'),
        password=os.environ.get('DB_PASS', ''),
        database=os.environ.get('DB_NAME', 'classicmodels'),
        cursorclass=pymysql.cursors.DictCursor
    )

def validate():
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            # Verifica se a tabela existe e contém o registro
            cursor.execute("SELECT * FROM etl_watermark WHERE pipeline_name = 'classicmodels_sales';")
            watermark = cursor.fetchone()
            if not watermark:
                print("ERRO: Registro 'classicmodels_sales' não encontrado na tabela etl_watermark.")
                sys.exit(1)
            
            # Verifica se last_processed_order_date não é NULL
            last_processed = watermark['last_processed_order_date']
            if not last_processed:
                print("ERRO: last_processed_order_date está NULL.")
                sys.exit(1)
                
            # Verifica se há dados novos pendentes
            cursor.execute("SELECT MAX(orderDate) as max_date FROM orders;")
            max_order_date = cursor.fetchone()['max_date']
            
            if not max_order_date or max_order_date <= last_processed:
                print(f"ERRO: Não há dados novos pendentes. MAX orderDate ({max_order_date}) <= Watermark ({last_processed}).")
                sys.exit(1)
                
            # Verifica se pedidos novos possuem orderdetails
            cursor.execute("""
                SELECT o.orderNumber 
                FROM orders o
                LEFT JOIN orderdetails od ON o.orderNumber = od.orderNumber
                WHERE o.orderDate > %s AND od.orderNumber IS NULL;
            """, (last_processed,))
            
            pedidos_sem_detalhes = cursor.fetchall()
            if pedidos_sem_detalhes:
                print(f"ERRO: Encontrados pedidos sem detalhes (orderdetails): {pedidos_sem_detalhes}")
                sys.exit(1)
                
            print("SUCESSO: Validação incremental concluída. Origem pronta para ETL.")
            sys.exit(0)
            
    finally:
        connection.close()

if __name__ == "__main__":
    validate()