#!/usr/bin/env bash
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"
RDS_ENV_FILE="${SCRIPT_DIR}/.rds.generated.env"
TERRAFORM_DIR="${SCRIPT_DIR}/terraform"
TASK1_DIR="${REPO_ROOT}/assignment_1/task_1"
TASK3_REQUIREMENTS="${SCRIPT_DIR}/requirements_task3.txt"

RUN_CRAWLER="${RUN_CRAWLER:-true}"
LOAD_SOURCE_DATA="${LOAD_SOURCE_DATA:-true}"
AUTO_INSTALL_DEPS="${AUTO_INSTALL_DEPS:-true}"
REQUIRE_ACTIVE_VENV="${REQUIRE_ACTIVE_VENV:-true}"
GLUE_POLL_INTERVAL="${GLUE_POLL_INTERVAL:-20}"
GLUE_TIMEOUT_SECONDS="${GLUE_TIMEOUT_SECONDS:-3600}"
CRAWLER_POLL_INTERVAL="${CRAWLER_POLL_INTERVAL:-20}"
CRAWLER_TIMEOUT_SECONDS="${CRAWLER_TIMEOUT_SECONDS:-1800}"
RDS_WAIT_TIMEOUT="${RDS_WAIT_TIMEOUT:-3600}"
TERRAFORM_APPLY_RETRIES="${TERRAFORM_APPLY_RETRIES:-2}"
TERRAFORM_RETRY_DELAY_SECONDS="${TERRAFORM_RETRY_DELAY_SECONDS:-20}"

on_error() {
  local line="$1"
  local cmd="$2"
  local rc="$3"
  echo "[task3][error] line=${line} rc=${rc} command=${cmd}" >&2
}
trap 'on_error "${LINENO}" "${BASH_COMMAND}" "$?"' ERR

log() {
  echo "[task3] $*"
}

normalize_bool() {
  local value
  value="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  case "${value}" in
    true|1|yes|y|on) echo "true" ;;
    false|0|no|n|off) echo "false" ;;
    *)
      echo "[task3][error] Invalid boolean value: $1" >&2
      exit 1
      ;;
  esac
}

require_commands() {
  for command_name in "$@"; do
    if ! command -v "${command_name}" >/dev/null 2>&1; then
      echo "[task3][error] Missing required command: ${command_name}" >&2
      exit 1
    fi
  done
}

retry_terraform_apply() {
  local attempts=1
  while true; do
    if terraform apply -auto-approve -input=false; then
      return 0
    fi

    if [[ "${attempts}" -ge "${TERRAFORM_APPLY_RETRIES}" ]]; then
      echo "[task3][error] terraform apply failed after ${attempts} attempt(s)." >&2
      return 1
    fi

    attempts=$((attempts + 1))
    log "terraform apply failed; retrying in ${TERRAFORM_RETRY_DELAY_SECONDS}s (attempt ${attempts}/${TERRAFORM_APPLY_RETRIES})..."
    sleep "${TERRAFORM_RETRY_DELAY_SECONDS}"
  done
}

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing .env file."
  echo "Create it with:"
  echo "  cp ${SCRIPT_DIR}/.env.example ${SCRIPT_DIR}/.env"
  echo "Then fill it with your AWS Academy values and MySQL password."
  exit 1
fi

RUN_CRAWLER="$(normalize_bool "${RUN_CRAWLER}")"
LOAD_SOURCE_DATA="$(normalize_bool "${LOAD_SOURCE_DATA}")"
AUTO_INSTALL_DEPS="$(normalize_bool "${AUTO_INSTALL_DEPS}")"
REQUIRE_ACTIVE_VENV="$(normalize_bool "${REQUIRE_ACTIVE_VENV}")"

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
    echo "[task3][error] Missing required value in .env: ${var_name}" >&2
    exit 1
  fi
done

require_commands terraform python

if [[ "${REQUIRE_ACTIVE_VENV}" == "true" ]] && [[ -z "${VIRTUAL_ENV:-}" ]]; then
  echo "No external virtual environment is active."
  echo "Activate your repo venv first, for example:"
  echo "  source .venv/bin/activate"
  exit 1
fi

PYTHON_BIN="$(command -v python)"
log "Using Python: ${PYTHON_BIN}"

if command -v brew >/dev/null 2>&1 && brew --prefix expat >/dev/null 2>&1; then
  EXPAT_LIB="$(brew --prefix expat)/lib"
  export DYLD_LIBRARY_PATH="${EXPAT_LIB}:${DYLD_LIBRARY_PATH:-}"
  export DYLD_FALLBACK_LIBRARY_PATH="${EXPAT_LIB}:${DYLD_FALLBACK_LIBRARY_PATH:-}"
fi

if [[ "${AUTO_INSTALL_DEPS}" == "true" ]]; then
  missing_modules="$(${PYTHON_BIN} - <<'PYCHECK'
import importlib.util

required = (
    "boto3",
    "pymysql",
    "awswrangler",
    "pandas",
    "seaborn",
    "matplotlib",
    "ipywidgets",
    "ipykernel",
)
missing = [module for module in required if importlib.util.find_spec(module) is None]
print(" ".join(missing))
PYCHECK
)"

  if [[ -n "${missing_modules}" ]]; then
    log "Installing missing Python dependencies: ${missing_modules}"
    "${PYTHON_BIN}" -m pip install -r "${TASK1_DIR}/requirements.txt" -r "${TASK3_REQUIREMENTS}"
  else
    log "Python dependencies already installed."
  fi
else
  log "Skipping dependency auto-install (AUTO_INSTALL_DEPS=false)."
fi

log "Checking AWS credentials..."
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
chmod 600 "${RDS_ENV_FILE}"

log "Creating or reusing RDS instance: ${RDS_INSTANCE_ID}"
"${PYTHON_BIN}" "${TASK1_DIR}/scripts/provision_rds.py" \
  --env-file "${RDS_ENV_FILE}" \
  --wait-timeout "${RDS_WAIT_TIMEOUT}"

if [[ "${LOAD_SOURCE_DATA}" == "true" ]]; then
  log "Loading classicmodels data into RDS..."
  "${PYTHON_BIN}" "${TASK1_DIR}/scripts/load_classicmodels.py" \
    --env-file "${RDS_ENV_FILE}" \
    --sql-file "${TASK1_DIR}/data/mysqlsampledatabase.sql"
else
  log "Skipping source data load (LOAD_SOURCE_DATA=false)."
fi

log "Discovering RDS network values for Glue..."
NETWORK_VALUES="$("${PYTHON_BIN}" - <<'PY'
import json
import os

import boto3

region = os.environ["AWS_REGION"]
rds = boto3.client("rds", region_name=region)
ec2 = boto3.client("ec2", region_name=region)
instance = rds.describe_db_instances(
    DBInstanceIdentifier=os.environ["RDS_INSTANCE_ID"]
)["DBInstances"][0]

subnets = instance["DBSubnetGroup"]["Subnets"]
selected_subnet = subnets[0]["SubnetIdentifier"]
for subnet in subnets:
    sid = subnet["SubnetIdentifier"]
    try:
        response = ec2.describe_subnets(SubnetIds=[sid])
        state = response["Subnets"][0]["State"]
        if state == "available":
            selected_subnet = sid
            break
    except Exception:
        continue

print(json.dumps({
    "db_host": instance["Endpoint"]["Address"],
    "db_security_group_id": instance["VpcSecurityGroups"][0]["VpcSecurityGroupId"],
    "vpc_id": instance["DBSubnetGroup"]["VpcId"],
    "subnet_id": selected_subnet,
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
chmod 600 terraform.tfvars

log "Initializing Terraform..."
terraform init -input=false

log "Applying Terraform..."
retry_terraform_apply

log "Saving Terraform outputs..."
terraform output -json > outputs.json
chmod 600 outputs.json

GLUE_JOB_NAME="$(terraform output -raw glue_job_name)"
GLUE_CRAWLER_NAME="$(terraform output -raw glue_crawler_name)"
GLUE_CATALOG_DATABASE_NAME="$(terraform output -raw glue_catalog_database_name)"
S3_BUCKET_NAME="$(terraform output -raw s3_bucket_name)"

log "Starting and monitoring Glue job: ${GLUE_JOB_NAME}"
"${PYTHON_BIN}" "${SCRIPT_DIR}/scripts/run_glue_job.py" \
  --job-name "${GLUE_JOB_NAME}" \
  --region "${AWS_REGION}" \
  --poll-interval "${GLUE_POLL_INTERVAL}" \
  --timeout-seconds "${GLUE_TIMEOUT_SECONDS}"

if [[ "${RUN_CRAWLER}" == "true" ]]; then
  log "Running Glue crawler: ${GLUE_CRAWLER_NAME}"
  "${PYTHON_BIN}" "${SCRIPT_DIR}/scripts/run_glue_crawler.py" \
    --crawler-name "${GLUE_CRAWLER_NAME}" \
    --region "${AWS_REGION}" \
    --poll-interval "${CRAWLER_POLL_INTERVAL}" \
    --timeout-seconds "${CRAWLER_TIMEOUT_SECONDS}"
else
  log "Skipping Glue crawler execution (RUN_CRAWLER=false)."
fi

echo
echo "Pipeline finished."
echo "S3 bucket: ${S3_BUCKET_NAME}"
echo "Curated path: s3://${S3_BUCKET_NAME}/curated/"
echo "Glue catalog database: ${GLUE_CATALOG_DATABASE_NAME}"
echo "Glue crawler: ${GLUE_CRAWLER_NAME}"
echo
echo "Next: open task3_dashboard.ipynb from this folder and run all cells."
echo "It will read terraform/outputs.json automatically."
