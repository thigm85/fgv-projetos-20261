"""
Script to create an RDS instance in AWS.
"""

import boto3
import os
import logging
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(os.path.basename(__file__))


def load_config():
    logger.info("Loading configuration from environment variables...")

    config = {
        "region": os.getenv("AWS_REGION", "us-east-1"),
        "db_id": os.getenv("DB_INSTANCE_ID"),
        "db_class": os.getenv("DB_INSTANCE_CLASS"),
        "engine": os.getenv("DB_ENGINE"),
        "engine_version": os.getenv("DB_ENGINE_VERSION"),
        "username": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "storage": int(os.getenv("DB_STORAGE", "20")),
        "public": os.getenv("DB_PUBLIC", "false").lower() == "true",
        "backup_retention": int(os.getenv("DB_BACKUP_RETENTION", "0")),
        "tags": [
            {"Key": "project", "Value": os.getenv("PROJECT_NAME", "default")}
        ],
    }

    logger.info(f"Configuration loaded (db_id={config['db_id']}, engine={config['engine']})")
    return config


def create_rds_instance(config):
    logger.info(f"Creating RDS instance: {config['db_id']}")

    rds = boto3.client("rds", region_name=config["region"])
    db_id = config["db_id"]

    try:
        response = rds.create_db_instance(
            DBInstanceIdentifier=db_id,
            DBInstanceClass=config["db_class"],
            Engine=config["engine"],
            EngineVersion=config["engine_version"],
            MasterUsername=config["username"],
            MasterUserPassword=config["password"],
            AllocatedStorage=config["storage"],
            PubliclyAccessible=config["public"],
            BackupRetentionPeriod=config["backup_retention"],
            Tags=config["tags"],
        )

        logger.info("RDS creation request sent successfully.")
        return True

    except ClientError:
        logger.exception("Error creating RDS instance")
        return None


def wait_for_instance(config):
    logger.info("Waiting for RDS instance to become available...")

    rds = boto3.client("rds", region_name=config["region"])
    db_id = config["db_id"]

    waiter = rds.get_waiter("db_instance_available")
    waiter.wait(DBInstanceIdentifier=db_id)

    logger.info("RDS instance is now available!")


def get_endpoint(config):
    logger.info("Fetching RDS endpoint...")

    rds = boto3.client("rds", region_name=config["region"])
    db_id = config["db_id"]

    response = rds.describe_db_instances(DBInstanceIdentifier=db_id)
    endpoint = response["DBInstances"][0]["Endpoint"]["Address"]

    logger.info(f"Endpoint retrieved: {endpoint}")
    return endpoint


def rds_pipeline():
    try:
        logger.info("Starting RDS pipeline...")

        config = load_config()

        created = create_rds_instance(config)
        if not created:
            logger.error("RDS creation failed. Exiting pipeline.")
            return

        wait_for_instance(config)

        endpoint = get_endpoint(config)
        if endpoint:
            logger.info(f"RDS instance is available at: {endpoint}")

        return endpoint

    except Exception:
        logger.exception("Unexpected error in pipeline")


if __name__ == "__main__":
    endpoint = rds_pipeline()