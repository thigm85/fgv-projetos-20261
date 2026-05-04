"""
Main script to orchestrate the RDS instance creation, data loading, and validation.
"""

from data_loader import data_loader_pipeline
from data_validation import validate_database
from rds_provider import rds_pipeline

if __name__ == "__main__":
    sql_file_path = "../../data/mysqlsampledatabase.sql"

    endpoint = rds_pipeline()
    data_loader_pipeline(sql_file_path, endpoint)
    validate_database(endpoint)