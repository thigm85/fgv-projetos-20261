#!/usr/bin/env bash
# Validação end-to-end do pipeline Glue.
# Uso: ./validate.sh [--run-job]
#   sem --run-job: só checa pré-condições (não executa Glue job).
#   com --run-job: executa Glue job e valida outputs.

set -u  # falha se variável não setada
# Não usa -e: queremos rodar TODOS checks e somar falhas.

PROFILE="projetos"
REGION="us-east-1"
TF_DIR="$(cd "$(dirname "$0")/terraform" && pwd)"
ENV_FILE="$(cd "$(dirname "$0")/src" && pwd)/.env"
GLUE_SCRIPT="$(cd "$(dirname "$0")/glue" && pwd)/glue_job_main.py"

RUN_JOB=0
[[ "${1:-}" == "--run-job" ]] && RUN_JOB=1

PASS=0
FAIL=0
ok()   { echo "  ✓ $*"; PASS=$((PASS+1)); }
bad()  { echo "  ✗ $*"; FAIL=$((FAIL+1)); }
step() { echo ""; echo "=== $* ==="; }

# ---------- 1. Terraform state ----------
step "1. Terraform state"
cd "$TF_DIR" || { bad "TF dir não existe: $TF_DIR"; exit 1; }
if terraform plan -detailed-exitcode -input=false >/dev/null 2>&1; then
  ok "terraform plan = no changes"
else
  rc=$?
  if [[ $rc -eq 2 ]]; then
    bad "terraform plan tem mudanças pendentes (roda apply)"
  else
    bad "terraform plan falhou (rc=$rc)"
  fi
fi

ENDPOINT=$(terraform output -raw endpoint 2>/dev/null)
SECRET_ARN=$(terraform output -raw secret_arn 2>/dev/null)
[[ -n "$ENDPOINT" ]]   && ok "RDS endpoint: $ENDPOINT" || bad "sem RDS endpoint"
[[ -n "$SECRET_ARN" ]] && ok "Secret ARN: $SECRET_ARN" || bad "sem secret ARN"

# ---------- 2. .env ----------
step "2. .env"
if [[ -f "$ENV_FILE" ]]; then
  ok ".env existe: $ENV_FILE"
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  [[ -n "${S3_BUCKET:-}" ]]     && ok "S3_BUCKET=$S3_BUCKET"         || bad "S3_BUCKET não definido"
  [[ -n "${GLUE_JOB_NAME:-}" ]] && ok "GLUE_JOB_NAME=$GLUE_JOB_NAME" || bad "GLUE_JOB_NAME não definido"
  [[ -n "${SECRET_ARN:-}" ]]    && ok "SECRET_ARN no .env"           || bad "SECRET_ARN não no .env"
else
  bad ".env não existe — roda terraform apply"
fi

# ---------- 3. Credenciais AWS ----------
step "3. Credenciais AWS"
if aws sts get-caller-identity --profile "$PROFILE" >/dev/null 2>&1; then
  ok "credenciais $PROFILE válidas"
else
  bad "credenciais $PROFILE inválidas/expiradas"
  echo "  → reabre lab AWS Academy, atualiza ~/.aws/credentials"
  exit 1
fi

# ---------- 4. RDS conectividade (do teu IP) ----------
step "4. RDS conectividade"
if command -v mysql >/dev/null; then
  if [[ -z "${MYSQL_PWD:-}" ]]; then
    echo "  ⚠ exporta MYSQL_PWD antes pra testar (ex: export MYSQL_PWD=...)"
  else
    if mysql -h "$ENDPOINT" -u admin --connect-timeout=5 \
         -e "SELECT 1" >/dev/null 2>&1; then
      ok "RDS responde no 3306"
      # Banco populado?
      for t in orders customers products orderdetails; do
        c=$(mysql -h "$ENDPOINT" -u admin -N -B classicmodels \
              -e "SELECT COUNT(*) FROM $t" 2>/dev/null)
        if [[ -n "$c" && "$c" -gt 0 ]]; then
          ok "$t: $c registros"
        else
          bad "$t: vazio ou inexistente"
        fi
      done
    else
      bad "RDS não responde — checa SG / IP / status"
    fi
  fi
else
  echo "  ⚠ mysql client não instalado (skip)"
fi

# ---------- 5. Secret válido ----------
step "5. Secret"
SEC=$(aws secretsmanager get-secret-value --secret-id "$SECRET_ARN" \
        --profile "$PROFILE" --query SecretString --output text 2>/dev/null)
if [[ -n "$SEC" ]]; then
  for k in username password host port dbname; do
    if echo "$SEC" | grep -q "\"$k\""; then
      ok "secret tem $k"
    else
      bad "secret SEM $k"
    fi
  done
else
  bad "não consegui ler secret"
fi

# ---------- 6. S3 bucket + script Glue ----------
step "6. S3 / Glue script"
if aws s3api head-bucket --bucket "$S3_BUCKET" --profile "$PROFILE" 2>/dev/null; then
  ok "bucket $S3_BUCKET existe"
else
  bad "bucket $S3_BUCKET inacessível"
fi

if aws s3api head-object --bucket "$S3_BUCKET" --key "scripts/glue_job_main.py" \
     --profile "$PROFILE" >/dev/null 2>&1; then
  ok "script no S3"
else
  bad "script ausente no S3"
fi

# ---------- 7. Sintaxe do script ----------
step "7. Sintaxe do script Glue"
if python3 -m py_compile "$GLUE_SCRIPT" 2>/dev/null; then
  ok "script compila"
else
  bad "script tem erro de sintaxe"
fi

# ---------- 8. Glue job config ----------
step "8. Glue job config"
JOB_JSON=$(aws glue get-job --job-name "$GLUE_JOB_NAME" --profile "$PROFILE" 2>/dev/null)
if [[ -n "$JOB_JSON" ]]; then
  ok "job $GLUE_JOB_NAME existe"
  echo "$JOB_JSON" | grep -q "\"Role\":" && ok "role configurada"     || bad "sem role"
  echo "$JOB_JSON" | grep -q "Connections" && ok "connection anexada" || bad "sem connection"
  echo "$JOB_JSON" | grep -q "ScriptLocation" && ok "script location" || bad "sem script"
else
  bad "job não existe"
fi

# ---------- 9. Glue connection ----------
step "9. Glue connection"
CONN_JSON=$(aws glue get-connection --name "classicmodels-jdbc-conn" \
              --profile "$PROFILE" 2>/dev/null)
if [[ -n "$CONN_JSON" ]]; then
  ok "connection existe"
  echo "$CONN_JSON" | grep -q "JDBC_CONNECTION_URL" && ok "JDBC URL set" || bad "sem JDBC URL"
else
  bad "connection não existe"
fi

# ---------- 10. Executa job (opcional) ----------
if [[ $RUN_JOB -eq 1 ]]; then
  step "10. Executando Glue job"
  RUN_ID=$(aws glue start-job-run --job-name "$GLUE_JOB_NAME" \
             --profile "$PROFILE" --query JobRunId --output text 2>/dev/null)
  if [[ -z "$RUN_ID" ]]; then
    bad "falha ao iniciar job"
  else
    ok "job iniciado: $RUN_ID"
    echo "  aguardando (timeout 15min)..."
    for i in {1..90}; do
      STATE=$(aws glue get-job-run --job-name "$GLUE_JOB_NAME" --run-id "$RUN_ID" \
                --profile "$PROFILE" --query 'JobRun.JobRunState' --output text 2>/dev/null)
      printf "  [%02d] %s\n" "$i" "$STATE"
      [[ "$STATE" == "SUCCEEDED" || "$STATE" == "FAILED" || "$STATE" == "STOPPED" || "$STATE" == "TIMEOUT" ]] && break
      sleep 10
    done
    if [[ "$STATE" == "SUCCEEDED" ]]; then
      ok "job SUCCEEDED"
    else
      bad "job terminou em $STATE"
      echo "  logs: aws logs tail /aws-glue/jobs/error --profile $PROFILE"
    fi
  fi

  # ---------- 11. Outputs Parquet ----------
  step "11. Outputs Parquet"
  for t in fact_orders dim_customers dim_products dim_dates dim_countries; do
    n=$(aws s3 ls "s3://$S3_BUCKET/$t/" --recursive --profile "$PROFILE" 2>/dev/null \
          | grep -c '\.parquet$')
    if [[ "$n" -gt 0 ]]; then
      ok "$t: $n parquet(s)"
    else
      bad "$t: nenhum parquet"
    fi
  done
else
  echo ""
  echo "→ checks pré-execução prontos. Pra rodar o job e validar outputs:"
  echo "    $0 --run-job"
fi

# ---------- Resumo ----------
echo ""
echo "================================"
echo "PASS: $PASS  |  FAIL: $FAIL"
echo "================================"
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
