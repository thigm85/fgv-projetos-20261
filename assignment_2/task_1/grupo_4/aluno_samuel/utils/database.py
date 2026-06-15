from classicmodels_rds.config import load_settings
from classicmodels_rds.mysql_io import connect_with_retries


def get_connection():
    settings = load_settings()
    return connect_with_retries(settings)