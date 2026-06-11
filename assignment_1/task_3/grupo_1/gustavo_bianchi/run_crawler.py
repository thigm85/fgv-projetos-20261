import boto3
import time
import sys
import logging

logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - [AWS Crawler] %(message)s', 
                    datefmt='%H:%M:%S')

def run_catalog_crawler():
    glue = boto3.client('glue', region_name='us-east-1')
    crawler_name = "classicmodels-s3-crawler"

    try:
        logging.info("Iniciando varredura do S3 para catalogar as tabelas no Athena...")
        glue.start_crawler(Name=crawler_name)
        
        while True:
            response = glue.get_crawler(Name=crawler_name)
            state = response['Crawler']['State']
            
            if state == 'READY': # Quando ele termina, o estado volta para READY
                logging.info("SUCESSO! O Crawler finalizou. Tabelas criadas no AWS Glue Catalog.")
                sys.exit(0)
                
            logging.info(f"Status: {state} (Aguardando conclusão...)")
            time.sleep(15)

    except Exception as e:
        logging.error(f"Erro ao executar o crawler: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_catalog_crawler()