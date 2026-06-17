set -eux

SUDO_USER=ec2-user
NOTEBOOK_DIR=/home/${SUDO_USER}/SageMaker/task3
mkdir -p "${NOTEBOOK_DIR}"

ETL_BUCKET="__ETL_BUCKET__"
NOTEBOOK_KEY="__NOTEBOOK_KEY__"
GLUE_DATABASE="__GLUE_DATABASE__"
ATHENA_WORKGROUP="__ATHENA_WORKGROUP__"
ATHENA_OUTPUT_S3="__ATHENA_OUTPUT_S3__"
DB_SECRET_ID="__DB_SECRET_ID__"
AWS_REGION_VAR="__AWS_REGION__"

aws s3 cp "s3://${ETL_BUCKET}/${NOTEBOOK_KEY}" "${NOTEBOOK_DIR}/classicmodels_dashboard.ipynb" --region "${AWS_REGION_VAR}"

ENV_FILE=/home/${SUDO_USER}/SageMaker/task3/.env
cat > "${ENV_FILE}" <<EOF
AWS_REGION=${AWS_REGION_VAR}
GLUE_DATABASE=${GLUE_DATABASE}
ATHENA_WORKGROUP=${ATHENA_WORKGROUP}
ATHENA_OUTPUT_S3=${ATHENA_OUTPUT_S3}
DB_SECRET_ID=${DB_SECRET_ID}
ETL_BUCKET=${ETL_BUCKET}
EOF

chown -R ${SUDO_USER}:${SUDO_USER} /home/${SUDO_USER}/SageMaker/task3

sudo -u ${SUDO_USER} -i bash -c "
source /home/${SUDO_USER}/anaconda3/bin/activate python3
pip install --quiet --upgrade 'awswrangler>=3.9.0' 'ipywidgets>=8.1.2' 'seaborn>=0.13.2'
jupyter nbextension enable --py --sys-prefix widgetsnbextension || true
source /home/${SUDO_USER}/anaconda3/bin/deactivate
"

echo 'SageMaker on-start: notebook sincronizado e dependencias garantidas.'
