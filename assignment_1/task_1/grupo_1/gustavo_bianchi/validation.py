import pymysql
import sys
import os

# Importa config.py
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import CFG

def get_connection():
    return pymysql.connect(
        host=CFG.get_db_host(),
        user=CFG.DB_USER,
        password=CFG.DB_PASS,
        database=CFG.DB_NAME
    )

def validate():
    validation_suite = {
        # Testes de tabelas vazias
        "Completude: Tabela 'orders' populada": ("SELECT COUNT(*) FROM orders;", 0, ">"),
        "Completude: Tabela 'orderdetails' populada": ("SELECT COUNT(*) FROM orderdetails;", 0, ">"),
        
        # Teste de integridade (há registros órfãos?)
        "Integridade: Pedidos sem cliente associado (Orphans)": (
            "SELECT COUNT(*) FROM orders WHERE customerNumber NOT IN (SELECT customerNumber FROM customers);", 
            0, "=="
        ),
        "Integridade: Detalhes de pedido sem pedido correspondente": (
            "SELECT COUNT(*) FROM orderdetails WHERE orderNumber NOT IN (SELECT orderNumber FROM orders);", 
            0, "=="
        ),

        # Teste de regras de negócio (há valores inválidos?)
        "Qualidade: Preços unitários nulos ou negativos": (
            "SELECT COUNT(*) FROM orderdetails WHERE priceEach <= 0 OR priceEach IS NULL;", 
            0, "=="
        ),
        "Qualidade: Quantidades pedidas nulas ou negativas": (
            "SELECT COUNT(*) FROM orderdetails WHERE quantityOrdered <= 0 OR quantityOrdered IS NULL;", 
            0, "=="
        ),
        "Qualidade: Datas de envio anteriores às datas de pedido": (
            "SELECT COUNT(*) FROM orders WHERE shippedDate < orderDate;", 
            0, "=="
        )
    }

    conn = None
    failed_tests = 0

    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        print("Iniciando testes de data quality\n")
        print("-" * 60)

        for test_name, (query, expected_val, operator) in validation_suite.items():
            cursor.execute(query)
            result = cursor.fetchone()[0]
            
            # Avaliação da regra
            passed = False
            if operator == "==": passed = (result == expected_val)
            elif operator == ">": passed = (result > expected_val)

            if passed:
                print(f"[PASS] {test_name}")
            else:
                print(f"[FAIL] {test_name} | Obtido: {result} | Esperado {operator} {expected_val}")
                failed_tests += 1

        print("-" * 60)
    
        if failed_tests > 0:
            print(f"\nStatus: FALHA. {failed_tests} testes nao passaram.")
            sys.exit(1)
        else:
            print("\nStatus: SUCESSO. Integridade do banco validada.")
            sys.exit(0)
            
    except Exception as e:
        print(f"Erro fatal durante a validacao: {e}")
        sys.exit(1)
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    validate()