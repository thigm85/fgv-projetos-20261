from __future__ import annotations

import sys

from config import load_config, load_db_credentials


def main() -> int:
    config = load_config()
    creds = load_db_credentials()

    print(f"AWS_REGION={config.aws_region}")
    print(f"PROJECT_PREFIX={config.project_prefix}")
    print(f"DB_SECRET_ID={config.db_secret_id}")
    print(f"GLUE_DATABASE={config.glue_database}")
    print(f"ATHENA_WORKGROUP={config.athena_workgroup}")
    print(f"ATHENA_OUTPUT_S3={config.athena_output_s3}")
    print(f"ETL_BUCKET={config.etl_bucket}")
    print()
    print("# valores resolvidos a partir do Secrets Manager (apenas para verificacao):")
    print(f"# rds_host={creds.host}")
    print(f"# rds_port={creds.port}")
    print(f"# rds_user={creds.username}")
    print(f"# rds_db={creds.dbname}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
