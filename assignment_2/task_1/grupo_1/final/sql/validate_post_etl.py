import os
import pandas as pd
import numpy as np

# Configurações do S3
BUCKET_NAME = "fgv-datalake-joao-gabriel-9090"
BASE_S3_PATH = f"s3://{BUCKET_NAME}/data"

def validate_etl():
    output_lines = []
    output_lines.append("=== Validation of ETL (Star Schema) ===\n")
    
    expected_tables = ["fact_orders", "dim_customers", "dim_products", "dim_dates", "dim_countries"]
    dfs = {}
    
    # ---------------------------------------------------------
    # 1. Validação de Existência e Leitura (Critério 4.6 - Parte 2)
    # ---------------------------------------------------------
    output_lines.append("1. Checking S3 Parquet Files:")
    for table in expected_tables:
        s3_path = f"{BASE_S3_PATH}/{table}/"
        try:
            # O Pandas lê automaticamente todos os arquivos parquet da pasta no S3
            df = pd.read_parquet(s3_path)
            dfs[table] = df
            output_lines.append(f"  [OK] {table} loaded successfully with {len(df)} rows.")
        except Exception as e:
            output_lines.append(f"  [ERROR] Failed to load {table}: {e}")

    # ---------------------------------------------------------
    # 2. Validação da Tabela Fato e Métrica (Critério 4.6 - Parte 3 e 4)
    # ---------------------------------------------------------
    if "fact_orders" in dfs:
        output_lines.append("\n2. Validating Business Metrics (fact_orders):")
        fact_df = dfs["fact_orders"]
        
        if fact_df.empty:
            output_lines.append("  [ERROR] fact_orders is empty.")
        else:
            output_lines.append("  [OK] fact_orders contains records.")
            
            # CORREÇÃO AQUI: Converter os tipos Decimal do Parquet para float nativo do Pandas
            fact_df['quantity_ordered'] = fact_df['quantity_ordered'].astype(float)
            fact_df['price_each'] = fact_df['price_each'].astype(float)
            fact_df['sales_amount'] = fact_df['sales_amount'].astype(float)
            
            # Validação da regra: sales_amount = quantity_ordered * price_each
            expected_sales = fact_df['quantity_ordered'] * fact_df['price_each']
            
            # Usamos np.isclose para evitar falsos positivos por conta de arredondamento de float
            inconsistencies = fact_df[~np.isclose(fact_df['sales_amount'], expected_sales, atol=0.01)]
            
            if inconsistencies.empty:
                output_lines.append("  [OK] sales_amount == quantity_ordered * price_each for all records.")
            else:
                output_lines.append(f"  [ERROR] Found {len(inconsistencies)} rows with incorrect sales_amount.")

    # ---------------------------------------------------------
    # 3. Validação de Integridade Referencial (Critério 4.6 - Parte 3)
    # ---------------------------------------------------------
    output_lines.append("\n3. Validating Referential Integrity (Foreign Keys):")
    if "fact_orders" in dfs:
        fact_df = dfs["fact_orders"]
        
        # Mapeamento da Chave Estrangeira (Fato) -> (Nome da Dimensão, Chave Primária)
        fk_mappings = {
            "customer_id": ("dim_customers", "customer_id"),
            "product_id": ("dim_products", "product_id"),
            "order_date_key": ("dim_dates", "date_key"),
            "country_key": ("dim_countries", "country_key")
        }
        
        for fact_col, (dim_name, dim_col) in fk_mappings.items():
            if dim_name in dfs:
                dim_df = dfs[dim_name]
                
                # Coleta valores únicos ignorando nulos (set)
                fact_keys = set(fact_df[fact_col].dropna().unique())
                dim_keys = set(dim_df[dim_col].dropna().unique())
                
                # Se sobrar alguma chave da fato que não existe na dimensão, temos um furo
                missing_keys = fact_keys - dim_keys
                
                if not missing_keys:
                    output_lines.append(f"  [OK] All {fact_col} in fact_orders exist in {dim_name}.")
                else:
                    output_lines.append(f"  [ERROR] Found {len(missing_keys)} {fact_col}(s) in fact_orders missing from {dim_name}.")
            else:
                output_lines.append(f"  [WARNING] Cannot validate {fact_col} because {dim_name} is missing.")

    # ---------------------------------------------------------
    # 4. Saída do Terminal e Escrita no Arquivo .txt
    # ---------------------------------------------------------
    final_output = "\n".join(output_lines)
    print(final_output)
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, "validation_etl.txt")
    
    try:
        with open(file_path, "w", encoding="utf-8") as file:
            file.write(final_output)
        print(f"\n[INFO] Validation report saved to: {file_path}")
    except IOError as e:
        print(f"\nError: {e}")

if __name__ == "__main__":
    validate_etl()