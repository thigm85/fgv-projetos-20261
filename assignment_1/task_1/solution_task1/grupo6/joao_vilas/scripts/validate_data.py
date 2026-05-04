import pymysql

HOST = "classicmodels-rds-lab.chihawye3zpo.us-east-1.rds.amazonaws.com" 
USER = "admin"
PASSWORD = "password"
DB_NAME = "classicmodels" 

print(f"Conectando ao banco '{DB_NAME}' para validação...\n")

try:
    conexao = pymysql.connect(
        host=HOST,
        user=USER,
        password=PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor
    )

    with conexao.cursor() as cursor:
        # Pegar a lista de todas as tabelas no banco
        cursor.execute("SHOW TABLES;")
        tabelas = [list(row.values())[0] for row in cursor.fetchall()]
        
        print(f"Encontradas {len(tabelas)} tabelas. Contando os registros de cada uma:\n")

        print(f"{'NOME DA TABELA'.ljust(20)} | {'QTD DE LINHAS'}")        
        # Contar quantas linhas cada tabela tem
        for tabela in tabelas:
            cursor.execute(f"SELECT COUNT(*) as total FROM {tabela};")
            resultado = cursor.fetchone()
            print(f"{tabela.ljust(20)} | {resultado['total']}")
            
        print("Validação concluída com sucesso! Sistema de origem está pronto.")

except Exception as e:
    print(f"Ocorreu um erro: {e}")
finally:
    if 'conexao' in locals() and conexao.open:
        conexao.close()