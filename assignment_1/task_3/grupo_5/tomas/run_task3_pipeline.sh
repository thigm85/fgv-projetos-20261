#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"
RDS_ENV_FILE="${SCRIPT_DIR}/.rds.generated.env"
TERRAFORM_DIR="${SCRIPT_DIR}/terraform"
TASK1_DIR="${REPO_ROOT}/assignment_1/task_1"
TASK3_REQUIREMENTS="${SCRIPT_DIR}/requirements_task3.txt"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing .env file."
  echo "Create it with:"
  echo "  cp ${SCRIPT_DIR}/.env.example ${SCRIPT_DIR}/.env"
  echo "Then fill it with your AWS Academy values and MySQL password."
  exit 1
fi

set -a
source "${ENV_FILE}"
set +a

required_vars=(
  AWS_ACCESS_KEY_ID
  AWS_SECRET_ACCESS_KEY
  AWS_SESSION_TOKEN
  AWS_REGION
  PROJECT_NAME
  RDS_INSTANCE_ID
  DB_PORT
  DB_NAME
  DB_USER
  DB_PASSWORD
  RDS_INSTANCE_CLASS
  RDS_ALLOCATED_STORAGE
  RDS_PUBLICLY_ACCESSIBLE
  GLUE_ROLE_NAME
)

for var_name in "${required_vars[@]}"; do
  if [[ -z "${!var_name:-}" ]]; then
    echo "Missing required value in .env: ${var_name}"
    exit 1
  fi
done

for command_name in terraform python; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Missing required command: ${command_name}"
    exit 1
  fi
done

if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  echo "No external virtual environment is active."
  echo "Activate your repo venv first, for example:"
  echo "  source .venv/bin/activate"
  exit 1
fi

PYTHON_BIN="$(command -v python)"
echo "Using Python: ${PYTHON_BIN}"

if command -v brew >/dev/null 2>&1 && brew --prefix expat >/dev/null 2>&1; then
  EXPAT_LIB="$(brew --prefix expat)/lib"
  export DYLD_LIBRARY_PATH="${EXPAT_LIB}:${DYLD_LIBRARY_PATH:-}"
  export DYLD_FALLBACK_LIBRARY_PATH="${EXPAT_LIB}:${DYLD_FALLBACK_LIBRARY_PATH:-}"
fi

missing_modules="$(${PYTHON_BIN} - <<'PYCHECK'
import importlib.util

missing = [
    module
    for module in ("boto3", "pymysql", "awswrangler", "pandas", "seaborn", "matplotlib", "ipywidgets", "ipykernel")
    if importlib.util.find_spec(module) is None
]
print(" ".join(missing))
PYCHECK
)"

if [[ -n "${missing_modules}" ]]; then
  echo "Installing missing Python dependencies in active virtual environment: ${missing_modules}"
  if ! "${PYTHON_BIN}" -m pip install -r "${TASK1_DIR}/requirements.txt" -r "${TASK3_REQUIREMENTS}"; then
    echo "pip failed in the active virtual environment."
    echo "Your Homebrew Python/libexpat install is broken. Try:"
    echo "  brew reinstall expat python@3.12"
    echo "Then recreate your external venv and rerun."
    exit 1
  fi
else
  echo "Python dependencies already installed in active virtual environment."
fi

echo "Checking AWS credentials..."
AWS_ACCOUNT_ID="$("${PYTHON_BIN}" - <<'PY'
import boto3

print(boto3.client("sts").get_caller_identity()["Account"])
PY
)"
GLUE_ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/${GLUE_ROLE_NAME}"

cat > "${RDS_ENV_FILE}" <<EOF
AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
AWS_SESSION_TOKEN=${AWS_SESSION_TOKEN}
AWS_REGION=${AWS_REGION}
AWS_DEFAULT_REGION=${AWS_REGION}
RDS_DB_INSTANCE_IDENTIFIER=${RDS_INSTANCE_ID}
RDS_DB_NAME=${DB_NAME}
RDS_MASTER_USERNAME=${DB_USER}
RDS_MASTER_PASSWORD=${DB_PASSWORD}
MYSQL_PORT=${DB_PORT}
RDS_INSTANCE_CLASS=${RDS_INSTANCE_CLASS}
RDS_ALLOCATED_STORAGE=${RDS_ALLOCATED_STORAGE}
RDS_PUBLICLY_ACCESSIBLE=${RDS_PUBLICLY_ACCESSIBLE}
EOF

echo "Creating or reusing RDS instance: ${RDS_INSTANCE_ID}"
"${PYTHON_BIN}" "${TASK1_DIR}/scripts/provision_rds.py" --env-file "${RDS_ENV_FILE}"

echo "Loading classicmodels data into RDS..."
"${PYTHON_BIN}" "${TASK1_DIR}/scripts/load_classicmodels.py" \
  --env-file "${RDS_ENV_FILE}" \
  --sql-file "${TASK1_DIR}/data/mysqlsampledatabase.sql"

echo "Discovering RDS network values for Glue..."
NETWORK_VALUES="$("${PYTHON_BIN}" - <<'PY'
import json
import os

import boto3

rds = boto3.client("rds", region_name=os.environ["AWS_REGION"])
instance = rds.describe_db_instances(
    DBInstanceIdentifier=os.environ["RDS_INSTANCE_ID"]
)["DBInstances"][0]

print(json.dumps({
    "db_host": instance["Endpoint"]["Address"],
    "db_security_group_id": instance["VpcSecurityGroups"][0]["VpcSecurityGroupId"],
    "vpc_id": instance["DBSubnetGroup"]["VpcId"],
    "subnet_id": instance["DBSubnetGroup"]["Subnets"][0]["SubnetIdentifier"],
}))
PY
)"
export NETWORK_VALUES

DB_HOST="$("${PYTHON_BIN}" -c 'import json, os; print(json.loads(os.environ["NETWORK_VALUES"])["db_host"])')"
DB_SECURITY_GROUP_ID="$("${PYTHON_BIN}" -c 'import json, os; print(json.loads(os.environ["NETWORK_VALUES"])["db_security_group_id"])')"
VPC_ID="$("${PYTHON_BIN}" -c 'import json, os; print(json.loads(os.environ["NETWORK_VALUES"])["vpc_id"])')"
SUBNET_ID="$("${PYTHON_BIN}" -c 'import json, os; print(json.loads(os.environ["NETWORK_VALUES"])["subnet_id"])')"

cd "${TERRAFORM_DIR}"

cat > terraform.tfvars <<EOF
aws_region           = "${AWS_REGION}"
project_name         = "${PROJECT_NAME}"
db_host              = "${DB_HOST}"
db_port              = ${DB_PORT}
db_name              = "${DB_NAME}"
db_user              = "${DB_USER}"
db_password          = "${DB_PASSWORD}"
db_security_group_id = "${DB_SECURITY_GROUP_ID}"
vpc_id               = "${VPC_ID}"
subnet_id            = "${SUBNET_ID}"
glue_role_arn        = "${GLUE_ROLE_ARN}"
EOF

echo "Initializing Terraform..."
terraform init

echo "Applying Terraform..."
terraform apply -auto-approve

echo "Saving Terraform outputs..."
terraform output -json > outputs.json

GLUE_JOB_NAME="$(terraform output -raw glue_job_name)"
S3_BUCKET_NAME="$(terraform output -raw s3_bucket_name)"
export GLUE_JOB_NAME

echo "Starting Glue job: ${GLUE_JOB_NAME}"
JOB_RUN_ID="$("${PYTHON_BIN}" - <<'PY'
import os

import boto3

glue = boto3.client("glue", region_name=os.environ["AWS_REGION"])
print(glue.start_job_run(JobName=os.environ["GLUE_JOB_NAME"])["JobRunId"])
PY
)"
export JOB_RUN_ID

echo "Glue run id: ${JOB_RUN_ID}"
echo "Waiting for Glue job to finish..."

while true; do
  STATUS="$("${PYTHON_BIN}" - <<'PY'
import os

import boto3

glue = boto3.client("glue", region_name=os.environ["AWS_REGION"])
response = glue.get_job_run(
    JobName=os.environ["GLUE_JOB_NAME"],
    RunId=os.environ["JOB_RUN_ID"],
)
print(response["JobRun"]["JobRunState"])
PY
)"

  echo "Current Glue status: ${STATUS}"

  case "${STATUS}" in
    SUCCEEDED)
      echo "Glue job succeeded."
      break
      ;;
    FAILED|STOPPED|TIMEOUT|ERROR)
      echo "Glue job ended with status: ${STATUS}"
      exit 1
      ;;
    *)
      sleep 20
      ;;
  esac
done

echo
echo "Pipeline finished."
echo "S3 bucket: ${S3_BUCKET_NAME}"
echo "Curated path: s3://${S3_BUCKET_NAME}/curated/"
echo
echo "Next: open task3_dashboard.ipynb from this folder and run all cells."
echo "It will read terraform/outputs.json automatically."
