#!/usr/bin/env bash
set -euo pipefail

TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${TASK_DIR}/../.." && pwd)"
PYTHON="${PYTHON:-${TASK_DIR}/.venv/bin/python}"
ENV_FILE="${TASK_DIR}/.env"
TASK1_DIR="${REPO_ROOT}/assignment_1/task_1"

if [[ ! -x "${PYTHON}" ]]; then
  PYTHON="python3"
fi

if grep -q "PASTE_YOUR_" "${ENV_FILE}"; then
  echo "Fill AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and AWS_SESSION_TOKEN in ${ENV_FILE} first." >&2
  exit 1
fi

"${PYTHON}" "${TASK1_DIR}/scripts/provision_rds.py" \
  --env-file "${ENV_FILE}"

"${PYTHON}" "${TASK1_DIR}/scripts/load_classicmodels.py" \
  --env-file "${ENV_FILE}" \
  --sql-file "${TASK1_DIR}/data/mysqlsampledatabase.sql"

"${PYTHON}" "${TASK_DIR}/scripts/init_watermark.py"
"${PYTHON}" "${TASK_DIR}/scripts/validate_incremental_source.py"
"${PYTHON}" "${TASK_DIR}/scripts/simulate_new_orders.py" --count "${COUNT:-5}" --seed "${SEED:-42}"
"${PYTHON}" "${TASK_DIR}/scripts/validate_incremental_source.py" --require-pending
