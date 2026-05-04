import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

load_dotenv()

DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST')
DB_NAME = 'classicmodels' 
DB_PORT = "3306"

def validate_database():
    # mysql Database
    connection_string = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    engine = create_engine(connection_string)
    
    output_lines = []
    output_lines.append("=== Validation of classicmodels ===\n")

    try:
        with engine.connect() as connection:
            # Getting all tables
            tables_result = connection.execute(text("SHOW TABLES")).fetchall()
            tables = [row[0] for row in tables_result]
            
            output_lines.append(f"Tables found ({len(tables)}): {', '.join(tables)}\n")
            output_lines.append("-" * 40)
            
            # Count and distinct from all tables
            for table in tables:
                total_query = f"SELECT COUNT(*) FROM {table}"
                total_count = connection.execute(text(total_query)).scalar()

                unique_query = f"SELECT COUNT(*) FROM (SELECT DISTINCT * FROM {table}) AS tmp"
                unique_count = connection.execute(text(unique_query)).scalar()
                
                output_lines.append(f"Table: {table}")
                output_lines.append(f"  - Lines: {total_count}")
                output_lines.append(f"  - Uniques:   {unique_count}")
                
                if total_count == unique_count:
                    output_lines.append("  - Status: OK")
                else:
                    output_lines.append("  - Status: X: Duplicates found ")
                
                output_lines.append("-" * 40)
                
    except SQLAlchemyError as e:
        error_msg = f"Error in Database: {e}"
        output_lines.append(error_msg)
        print(error_msg)

    final_output = "\n".join(output_lines)
    print(final_output)
    
    # Saving in a txt
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, "validation.txt")
    
    try:
        with open(file_path, "w", encoding="utf-8") as file:
            file.write(final_output)
    except IOError as e:
        print(f"\nError: {e}")

if __name__ == "__main__":
    validate_database()