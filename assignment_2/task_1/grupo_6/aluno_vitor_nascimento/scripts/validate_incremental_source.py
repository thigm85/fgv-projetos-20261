import logging
import os
import sys

import mysql.connector
from dotenv import find_dotenv, load_dotenv

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Search and load .env
dotenv_path = find_dotenv()
if not dotenv_path:
    for path in [".env", "src/.env", "../src/.env", "../../src/.env"]:
        if os.path.exists(path):
            dotenv_path = path
            break

if dotenv_path:
    load_dotenv(dotenv_path)
else:
    load_dotenv()


def validate_source():
    db_host = os.getenv("DB_HOST")
    db_user = os.getenv("DB_USER")
    db_pass = os.getenv("DB_PASS")
    db_name = os.getenv("DB_NAME")

    if not all([db_host, db_user, db_pass, db_name]):
        logger.error("Erro: Variáveis de conexão ao banco de dados incompletas no .env")
        sys.exit(1)

    logger.info("Iniciando validação da origem incremental...")
    success = True
    conn = None

    try:
        conn = mysql.connector.connect(
            host=db_host,
            user=db_user,
            password=db_pass,
            database=db_name,
            use_pure=True,
        )
        cursor = conn.cursor()

        # 1. Verificar se a tabela etl_watermark existe e contém o registro 'classicmodels_sales'
        pipeline_name = "classicmodels_sales"
        logger.info("Checagem 1/4: Verificando tabela 'etl_watermark'...")
        try:
            cursor.execute(
                "SELECT last_processed_order_date FROM etl_watermark WHERE pipeline_name = %s",
                (pipeline_name,),
            )
            row = cursor.fetchone()
            if row:
                logger.info(
                    f"[OK] Registro '{pipeline_name}' encontrado em 'etl_watermark'."
                )
                watermark_date = row[0]
            else:
                logger.error(
                    f"[FALHA] Registro para '{pipeline_name}' não encontrado na tabela 'etl_watermark'."
                )
                success = False
                watermark_date = None
        except mysql.connector.Error as err:
            logger.error(
                f"[FALHA] Tabela 'etl_watermark' não existe ou não pôde ser consultada: {err}"
            )
            success = False
            watermark_date = None

        # 2. Verificar se last_processed_order_date não é NULL
        logger.info("Checagem 2/4: Verificando se o watermark não é nulo...")
        if watermark_date is not None:
            logger.info(f"[OK] last_processed_order_date é: {watermark_date}")
        else:
            logger.error("[FALHA] last_processed_order_date está NULL.")
            success = False

        # 3. Verificar relação entre MAX(orderDate) e watermark
        logger.info(
            "Checagem 3/4: Verificando MAX(orders.orderDate) em relação ao watermark..."
        )
        cursor.execute("SELECT MAX(orderDate) FROM orders")
        max_order_date = cursor.fetchone()[0]

        if max_order_date is None:
            logger.error(
                "[FALHA] Não foi possível ler a data máxima de pedidos (orders está vazia)."
            )
            success = False
        elif watermark_date is not None:
            if max_order_date > watermark_date:
                logger.info(
                    f"[OK] MAX(orders.orderDate) ({max_order_date}) > watermark ({watermark_date}) -> HÁ DADOS NOVOS PENDENTES DE ETL."
                )
            elif max_order_date == watermark_date:
                logger.info(
                    f"[OK] MAX(orders.orderDate) ({max_order_date}) == watermark ({watermark_date}) -> Sem pedidos pendentes (baseline coerente)."
                )
            else:
                logger.error(
                    f"[FALHA] MAX(orders.orderDate) ({max_order_date}) < watermark ({watermark_date}) -> Inconsistência encontrada."
                )
                success = False

        # 4. Integridade mínima: verificar se pedidos simulados (posteriores ao watermark) possuem linhas em orderdetails
        logger.info("Checagem 4/4: Verificando integridade dos pedidos novos...")
        if watermark_date is not None:
            # Buscar pedidos simulados
            cursor.execute(
                "SELECT orderNumber, orderDate FROM orders WHERE orderDate > %s",
                (watermark_date,),
            )
            simulated_orders = cursor.fetchall()

            if simulated_orders:
                logger.info(
                    f"Detectados {len(simulated_orders)} pedidos posteriores ao watermark. Validando detalhes..."
                )

                # Query para contar quantos desses novos pedidos não possuem detalhes
                query_orphans = """
                SELECT COUNT(*) FROM orders o
                LEFT JOIN orderdetails d ON o.orderNumber = d.orderNumber
                WHERE o.orderDate > %s AND d.orderNumber IS NULL
                """
                cursor.execute(query_orphans, (watermark_date,))
                orphans_count = cursor.fetchone()[0]

                if orphans_count == 0:
                    logger.info(
                        f"[OK] Todos os {len(simulated_orders)} pedidos novos possuem registros correspondentes em 'orderdetails'."
                    )
                else:
                    logger.error(
                        f"[FALHA] Detectados {orphans_count} pedidos novos sem detalhes em 'orderdetails'."
                    )
                    success = False
            else:
                logger.info(
                    "[OK] Nenhum pedido novo detectado para validar detalhes (trivialmente válido)."
                )

    except Exception as e:
        logger.error(f"Erro fatal durante a validação da origem: {e}")
        success = False
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

    if success:
        logger.info("VALIDAÇÃO DA ORIGEM INCREMENTAL CONCLUÍDA COM SUCESSO.")
        sys.exit(0)
    else:
        logger.error("VALIDAÇÃO DA ORIGEM INCREMENTAL REPROVADA.")
        sys.exit(1)


if __name__ == "__main__":
    validate_source()
