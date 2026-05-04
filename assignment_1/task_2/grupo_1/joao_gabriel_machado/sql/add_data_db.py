import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
import sqlparse

# Load environment variables
load_dotenv()

DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST')
DB_PORT = "3306"

def get_engine():
    connection_string = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/"
    return create_engine(connection_string)

def execute_sql_file(engine, file_path):
    print(f"Reading SQL file from: {file_path}")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            sql_commands = file.read()
    except FileNotFoundError:
        print(f"Error: File not found at {file_path}. Check the relative path.")
        return

    commands = sqlparse.split(sql_commands)

    print("Connecting to the RDS instance and executing commands...")
    try:
        with engine.begin() as connection:
            for command in commands:
                command = command.strip()
                if command:
                    # Execute each valid statement
                    connection.execute(text(command))
        print("Database 'classicmodels' populated successfully")
    except SQLAlchemyError as e:
        print(f"Database error occurred: {e}")

if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sql_file_path = os.path.join(current_dir, "..", "data", "mysqlsampledatabase.sql")
    
    db_engine = get_engine()
    execute_sql_file(db_engine, sql_file_path)