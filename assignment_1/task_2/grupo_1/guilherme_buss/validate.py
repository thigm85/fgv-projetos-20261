#!/usr/bin/env python3
import sys
import os
import mysql.connector
from mysql.connector import Error

def main():
    host = os.getenv("RDS_HOST", "localhost")
    port = int(os.getenv("RDS_PORT", 3306))
    user = os.getenv("RDS_USER", "admin")
    password = os.getenv("RDS_PASSWORD")
    database = os.getenv("RDS_DATABASE", "classicmodels")
    
    tables = ["customers", "products", "productlines", "orders", "orderdetails", "payments", "employees", "offices"]
    
    try:
        conn = mysql.connector.connect(host=host, port=port, user=user, password=password, database=database)
        cursor = conn.cursor()
        
        print(f"\nValidating {database}...")
        all_valid = True
        
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            status = "✓" if count > 0 else "✗"
            print(f"{status} {table}: {count} rows")
            if count == 0:
                all_valid = False
        
        cursor.execute("SELECT COUNT(*) FROM orders WHERE customerNumber NOT IN (SELECT customerNumber FROM customers)")
        orphan = cursor.fetchone()[0]
        if orphan == 0:
            print("✓ Orders referential integrity OK")
        else:
            print(f"✗ {orphan} orphan orders")
            all_valid = False
        
        conn.close()
        
        if all_valid:
            print("✓ ALL VALIDATIONS PASSED\n")
            return 0
        else:
            print("✗ VALIDATION FAILED\n")
            return 1
            
    except Error as e:
        print(f"✗ Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())