import boto3
import pandas as pd
from io import BytesIO
import pyarrow.parquet as pq
import pyarrow as pa
import sys

def read_parquet_from_s3(bucket, key):
    """Read Parquet file from S3 and return as pandas DataFrame"""
    s3 = boto3.client('s3')
    response = s3.get_object(Bucket=bucket, Key=key)
    buffer = BytesIO(response['Body'].read())
    table = pq.read_table(buffer)
    return table.to_pandas()

def validate_etl(s3_bucket_name):
    """Validate ETL results in S3"""
    print(f"Validating ETL results in bucket: {s3_bucket_name}")

    s3 = boto3.client('s3')

    # Check if data directory exists
    try:
        response = s3.list_objects_v2(Bucket=s3_bucket_name, Prefix='data/')
        if 'Contents' not in response:
            print("❌ ERROR: No data directory found in S3")
            return False
    except Exception as e:
        print(f"❌ ERROR: Cannot access S3 bucket: {e}")
        return False

    # Check for required Parquet files
    required_prefixes = [
        'data/fact_orders/',
        'data/dim_customers/',
        'data/dim_products/',
        'data/dim_dates/',
        'data/dim_countries/'
    ]

    for prefix in required_prefixes:
        try:
            response = s3.list_objects_v2(Bucket=s3_bucket_name, Prefix=prefix)
            if 'Contents' not in response:
                print(f"❌ ERROR: Missing {prefix}")
                return False
            else:
                parquet_files = [obj['Key'] for obj in response['Contents'] if obj['Key'].endswith('.parquet')]
                if not parquet_files:
                    print(f"❌ ERROR: No Parquet files found in {prefix}")
                    return False
                print(f"✅ Found {len(parquet_files)} Parquet file(s) in {prefix}")
        except Exception as e:
            print(f"❌ ERROR: Cannot check {prefix}: {e}")
            return False

    # Read and validate fact_orders
    try:
        fact_orders_files = s3.list_objects_v2(Bucket=s3_bucket_name, Prefix='data/fact_orders/')['Contents']
        parquet_file = next((obj['Key'] for obj in fact_orders_files if obj['Key'].endswith('.parquet')), None)

        if not parquet_file:
            print("❌ ERROR: No Parquet file found for fact_orders")
            return False

        fact_orders_df = read_parquet_from_s3(s3_bucket_name, parquet_file)

        print(f"✅ fact_orders: {len(fact_orders_df)} records")
        print(f"   Columns: {list(fact_orders_df.columns)}")

        # Validate required columns
        required_columns = ['order_id', 'customer_id', 'product_id', 'order_date_key', 'country_key',
                          'quantity_ordered', 'price_each', 'sales_amount']
        missing_columns = [col for col in required_columns if col not in fact_orders_df.columns]
        if missing_columns:
            print(f"❌ ERROR: Missing columns in fact_orders: {missing_columns}")
            return False

        # Validate sales_amount calculation
        fact_orders_df['calculated_sales'] = fact_orders_df['quantity_ordered'] * fact_orders_df['price_each']
        inconsistent = fact_orders_df[abs(fact_orders_df['sales_amount'] - fact_orders_df['calculated_sales']) > 0.01]
        if len(inconsistent) > 0:
            print(f"❌ ERROR: {len(inconsistent)} records have inconsistent sales_amount")
            return False

        print("✅ sales_amount validation passed")

    except Exception as e:
        print(f"❌ ERROR: Cannot validate fact_orders: {e}")
        return False

    # Read and validate dimensions
    dimensions = {
        'dim_customers': ['customer_id', 'customer_name', 'contact_name', 'city', 'country'],
        'dim_products': ['product_id', 'product_name', 'product_line', 'product_vendor'],
        'dim_dates': ['date_key', 'full_date', 'year', 'quarter', 'month', 'day'],
        'dim_countries': ['country_key', 'country', 'territory']
    }

    for dim_name, required_cols in dimensions.items():
        try:
            dim_files = s3.list_objects_v2(Bucket=s3_bucket_name, Prefix=f'data/{dim_name}/')['Contents']
            parquet_file = next((obj['Key'] for obj in dim_files if obj['Key'].endswith('.parquet')), None)

            if not parquet_file:
                print(f"❌ ERROR: No Parquet file found for {dim_name}")
                return False

            dim_df = read_parquet_from_s3(s3_bucket_name, parquet_file)

            print(f"✅ {dim_name}: {len(dim_df)} records")

            # Check required columns
            missing_cols = [col for col in required_cols if col not in dim_df.columns]
            if missing_cols:
                print(f"❌ ERROR: Missing columns in {dim_name}: {missing_cols}")
                return False

        except Exception as e:
            print(f"❌ ERROR: Cannot validate {dim_name}: {e}")
            return False

    # Validate referential integrity (sample check)
    try:
        # Check if fact_orders customer_ids exist in dim_customers
        dim_customers_df = read_parquet_from_s3(s3_bucket_name,
            next(obj['Key'] for obj in s3.list_objects_v2(Bucket=s3_bucket_name, Prefix='data/dim_customers/')['Contents']
                 if obj['Key'].endswith('.parquet')))

        missing_customers = set(fact_orders_df['customer_id']) - set(dim_customers_df['customer_id'])
        if missing_customers:
            print(f"❌ ERROR: {len(missing_customers)} customer_ids in fact_orders not found in dim_customers")
            return False

        print("✅ Referential integrity check passed (customers)")

    except Exception as e:
        print(f"❌ ERROR: Cannot validate referential integrity: {e}")
        return False

    print("\n🎉 ETL Validation COMPLETED SUCCESSFULLY!")
    print("✅ All required tables exist")
    print("✅ All required columns present")
    print("✅ Sales amount calculations are correct")
    print("✅ Referential integrity maintained")

    return True

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python validate_etl.py <s3_bucket_name>")
        sys.exit(1)

    bucket_name = sys.argv[1]
    success = validate_etl(bucket_name)

    if not success:
        sys.exit(1)