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
    sql_file = os.getenv("SQL_FILE", "data/mysqlsampledatabase.sql")
    
    if not os.path.exists(sql_file):
        print(f"Error: SQL file not found: {sql_file}")
        sys.exit(1)
    
    try:
        conn = mysql.connector.connect(host=host, port=port, user=user, password=password)
        cursor = conn.cursor()
        
        cursor.execute(f"DROP DATABASE IF EXISTS {database}")
        cursor.execute(f"CREATE DATABASE {database}")
        cursor.execute(f"USE {database}")
        
        with open(sql_file, 'r', encoding='utf-8') as f:
            sql_commands = f.read().split(';')
        
        count = 0
        for cmd in sql_commands:
            cmd = cmd.strip()
            if cmd:
                cursor.execute(cmd)
                count += 1
                if count % 10 == 0:
                    print(f"  Executed {count} commands...")
        
        conn.commit()
        print(f"✓ Loaded {count} SQL commands into {database}")
        conn.close()
        
    except Error as e:
        print(f"✗ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()