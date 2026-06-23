#!/usr/bin/env python3
"""
Task 3 Validation Script
Validates that the Athena queries can execute successfully against the Glue tables
"""

import sys
import boto3
from botocore.exceptions import ClientError

def validate_glue_database(database_name, region):
    """Check if the Glue database exists and contains required tables"""
    try:
        glue_client = boto3.client('glue', region_name=region)
        
        # Check database exists
        try:
            db_response = glue_client.get_database(Name=database_name)
            print(f"✓ Database '{database_name}' found")
        except ClientError as e:
            print(f"✗ Database '{database_name}' not found: {e}")
            return False
        
        # Check required tables
        required_tables = [
            'fact_orders',
            'dim_customers',
            'dim_products',
            'dim_dates',
            'dim_countries'
        ]
        
        try:
            tables_response = glue_client.get_tables(DatabaseName=database_name)
            existing_tables = [t['Name'] for t in tables_response.get('TableList', [])]
            
            print(f"\n✓ Found {len(existing_tables)} tables in database:")
            for table in sorted(existing_tables):
                marker = "  ✓" if table in required_tables else "  •"
                print(f"{marker} {table}")
            
            missing = [t for t in required_tables if t not in existing_tables]
            if missing:
                print(f"\n✗ Missing required tables: {', '.join(missing)}")
                return False
            
            print(f"\n✓ All required tables present")
            return True
            
        except ClientError as e:
            print(f"✗ Error listing tables: {e}")
            return False
            
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False

def validate_athena_output(bucket_name, region):
    """Check if S3 bucket for Athena output exists and is accessible"""
    try:
        s3_client = boto3.client('s3', region_name=region)
        
        try:
            s3_client.head_bucket(Bucket=bucket_name)
            print(f"✓ Athena output bucket '{bucket_name}' exists and is accessible")
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                print(f"✗ Athena output bucket '{bucket_name}' not found")
            elif e.response['Error']['Code'] == '403':
                print(f"✗ Access denied to bucket '{bucket_name}'")
            else:
                print(f"✗ Error accessing bucket: {e}")
            return False
            
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False

def validate_config_file():
    """Check if configuration file exists and is readable"""
    try:
        import config
        required_attrs = ['GLUE_DATABASE', 'S3_OUTPUT', 'AWS_REGION']
        
        missing = [attr for attr in required_attrs if not hasattr(config, attr)]
        if missing:
            print(f"✗ Missing config attributes: {', '.join(missing)}")
            return False
        
        print(f"✓ Configuration file (config.py) is valid")
        print(f"  - GLUE_DATABASE: {config.GLUE_DATABASE}")
        print(f"  - AWS_REGION: {config.AWS_REGION}")
        print(f"  - S3_OUTPUT: {config.S3_OUTPUT}")
        return True
        
    except ImportError:
        print("⚠️  config.py not found. Skipping configuration validation.")
        print("    Run 'terraform apply' to generate config.py")
        return True  # Not a critical error, can be generated

def main():
    print("=" * 60)
    print("Task 3: Validation")
    print("=" * 60)
    
    print("\n1. Checking configuration file...")
    config_ok = validate_config_file()
    
    if not config_ok:
        print("\n✗ Configuration validation failed")
        sys.exit(1)
    
    # Load config if available
    try:
        from config import GLUE_DATABASE, AWS_REGION, ATHENA_OUTPUT_BUCKET
    except ImportError:
        print("\n✗ Cannot load configuration. Run 'terraform apply' first.")
        sys.exit(1)
    
    print("\n2. Validating Glue Catalog database and tables...")
    glue_ok = validate_glue_database(GLUE_DATABASE, AWS_REGION)
    
    if not glue_ok:
        print("\n⚠️  Glue database validation failed.")
        print("    Ensure Task 2 ETL completed successfully.")
        sys.exit(1)
    
    print("\n3. Validating Athena S3 output bucket...")
    s3_ok = validate_athena_output(ATHENA_OUTPUT_BUCKET, AWS_REGION)
    
    if not s3_ok:
        print("\n✗ S3 output bucket validation failed")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("✓ All validations passed!")
    print("=" * 60)
    print("\nYou can now run the Jupyter notebook:")
    print("  jupyter lab transformer.ipynb")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
