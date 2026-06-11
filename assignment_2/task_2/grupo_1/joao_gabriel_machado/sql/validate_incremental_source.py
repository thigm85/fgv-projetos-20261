import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

load_dotenv()

DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST')
DB_NAME = 'classicmodels'
DB_PORT = "3306"

def validate_incremental():
    connection_string = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    engine = create_engine(connection_string)
    
    output_lines = []
    output_lines.append("=== Incremental Source Validation Report ===\n")

    try:
        with engine.connect() as conn:
            # Check 1 & 2: Watermark table and null values
            watermark_query = text("""
                SELECT pipeline_name, last_processed_order_date, last_run_at, last_run_status 
                FROM etl_watermark 
                WHERE pipeline_name = 'classicmodels_sales'
            """)
            watermark_result = conn.execute(watermark_query).fetchone()

            if not watermark_result:
                msg = "Check 1 FAILED: Record 'classicmodels_sales' not found in etl_watermark."
                output_lines.append(msg)
                print(msg)
                save_report(output_lines)
                sys.exit(1)
            
            pipeline, watermark_date, last_run, status = watermark_result
            output_lines.append("--- Metadata Details ---")
            output_lines.append(f"Pipeline Name: {pipeline}")
            output_lines.append(f"Last Processed Date: {watermark_date}")
            output_lines.append(f"Last Run Timestamp: {last_run}")
            output_lines.append(f"Last Run Status: {status}\n")

            if watermark_date is None:
                msg = "Check 2 FAILED: last_processed_order_date is NULL."
                output_lines.append(msg)
                print(msg)
                save_report(output_lines)
                sys.exit(1)
            
            msg_p12 = f"Check 1 & 2 PASSED: Watermark found with date {watermark_date}."
            output_lines.append(msg_p12)
            print(msg_p12)

            # Check 3: Check for pending data
            max_date_query = text("SELECT MAX(orderDate), COUNT(*) FROM orders")
            max_date_res = conn.execute(max_date_query).fetchone()
            max_date = max_date_res[0]
            total_orders = max_date_res[1]

            pending_count_query = text("SELECT COUNT(*) FROM orders WHERE orderDate > :w_date")
            pending_orders = conn.execute(pending_count_query, {"w_date": watermark_date}).scalar()

            output_lines.append("\n--- Source Volume Details ---")
            output_lines.append(f"Total Orders in DB: {total_orders}")
            output_lines.append(f"Max Order Date in DB: {max_date}")
            output_lines.append(f"Pending Orders for ETL: {pending_orders}\n")

            if max_date is None or max_date <= watermark_date:
                msg = f"Check 3 FAILED: No new orders found. Max date ({max_date}) <= Watermark ({watermark_date})."
                output_lines.append(msg)
                print(msg)
                save_report(output_lines)
                sys.exit(1)
            
            msg_p3 = f"Check 3 PASSED: New data detected up to {max_date} ({pending_orders} pending orders)."
            output_lines.append(msg_p3)
            print(msg_p3)

            # Check 4: Integrity of new orders (no orphaned orders)
            integrity_query = text("""
                SELECT COUNT(o.orderNumber) 
                FROM orders o
                LEFT JOIN orderdetails od ON o.orderNumber = od.orderNumber
                WHERE o.orderDate > :watermark_date AND od.productCode IS NULL
            """)
            orphan_orders = conn.execute(integrity_query, {"watermark_date": watermark_date}).scalar()

            details_count_query = text("""
                SELECT COUNT(od.orderNumber) 
                FROM orderdetails od
                JOIN orders o ON o.orderNumber = od.orderNumber
                WHERE o.orderDate > :watermark_date
            """)
            total_pending_details = conn.execute(details_count_query, {"watermark_date": watermark_date}).scalar()

            output_lines.append("--- Lineage & Integrity Details ---")
            output_lines.append(f"Total rows in orderdetails for pending orders: {total_pending_details}")
            output_lines.append(f"Orphaned new orders (without details): {orphan_orders}\n")

            if orphan_orders > 0:
                msg = f"Check 4 FAILED: Found {orphan_orders} new orders without details."
                output_lines.append(msg)
                print(msg)
                save_report(output_lines)
                sys.exit(1)
            
            msg_p4 = "Check 4 PASSED: All new orders have corresponding details."
            output_lines.append(msg_p4)
            print(msg_p4)
            
            success_msg = "\nValidation SUCCESS: Source is ready for incremental ETL."
            output_lines.append(success_msg)
            print(success_msg)
            
            save_report(output_lines)
            sys.exit(0)

    except SQLAlchemyError as e:
        err_msg = f"Database error: {e}"
        output_lines.append(err_msg)
        print(err_msg)
        save_report(output_lines)
        sys.exit(1)

def save_report(lines):
    final_output = "\n".join(lines)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, "validation_incremental.txt")
    try:
        with open(file_path, "w", encoding="utf-8") as file:
            file.write(final_output)
        print(f"\n[INFO] Incremental validation report saved to: {file_path}")
    except IOError as e:
        print(f"\nError saving report file: {e}")

if __name__ == "__main__":
    validate_incremental()