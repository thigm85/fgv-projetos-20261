import os
import sys
import logging

# Padrão de Log
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("DataPipeline")

class CFG:
    DB_USER = 'admin'
    
    # Usando segurança. Para rodar o terraform sem digitar a senha, é preciso rodar no powershell (windows):
    # $env:TF_VAR_db_password ="SENHA_AQUI"
    # $env:DB_PASSWORD ="SENHA_AQUI"

    DB_PASS = os.getenv("DB_PASSWORD")
    if not DB_PASS:
        logger.error("FATAL: Variável de ambiente DB_PASSWORD não encontrada no sistema!")
        sys.exit(1)
        
    DB_NAME = 'classicmodels'
    SQL_PATH = 'assignment_1/task_1/data/mysqlsampledatabase.sql'
    
    @classmethod
    def get_db_host(cls):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        endpoint_file = os.path.join(current_dir, 'rds_endpoint.txt')
        
        try:
            with open(endpoint_file, 'r') as f:
                return f.read().strip()
        except FileNotFoundError:
            logger.error("rds_endpoint.txt não encontrado. Execute o Terraform primeiro.")
            sys.exit(1)

CFG.DB_HOST = CFG.get_db_host()