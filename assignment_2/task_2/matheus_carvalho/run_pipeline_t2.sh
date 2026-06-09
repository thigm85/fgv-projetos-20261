#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════
# Script de Validação Interativa — Task 2 (ETL Incremental)
#
# Este script guia você na execução e validação da Task 2 de ponta a ponta:
#   1. Inicializa e aplica o Terraform (cria o Glue Job, agendamento, etc)
#   2. Inicializa o Watermark no RDS
#   3. Executa a primeira run do Glue Job (Full load/Histórico)
#   4. Simula a chegada de novos pedidos (Task 1)
#   5. Executa a segunda run do Glue Job (Incremental)
#   6. Valida se o watermark avançou e as partições foram criadas no S3
# ═══════════════════════════════════════════════════════════════════════

set -e

# Cores para o terminal
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Caminhos
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TF_DIR="$SCRIPT_DIR/terraform"
T1_DIR="$(cd "$SCRIPT_DIR/../../task_1/grupo_2/final" && pwd)"

echo -e "${BLUE}════════════════════════════════════════════════════════"
echo -e "  INICIANDO AGENTE DE VALIDAÇÃO INTERATIVA — TASK 2"
echo -e "  Diretório Task 2: $SCRIPT_DIR"
echo -e "  Diretório Task 1: $T1_DIR"
echo -e "════════════════════════════════════════════════════════${NC}"

# Função para aguardar o Glue Job finalizar
wait_for_glue_job() {
    local job_name=$1
    local run_id=$2
    echo -e "${YELLOW}Aguardando o Glue Job '$job_name' finalizar (Run ID: $run_id)...${NC}"
    
    while true; do
        status=$(aws glue get-job-run --job-name "$job_name" --run-id "$run_id" --query "JobRun.JobRunState" --output text)
        echo -e "  Status atual: ${YELLOW}$status${NC}"
        
        if [ "$status" = "SUCCEEDED" ]; then
            echo -e "${GREEN}✓ Job finalizado com sucesso!${NC}"
            break
        elif [ "$status" = "FAILED" ] || [ "$status" = "STOPPED" ] || [ "$status" = "TIMEOUT" ]; then
            echo -e "${RED}✗ O Job falhou com status: $status${NC}"
            exit 1
        fi
        sleep 15
    done
}

# ── Passo 1: Terraform ────────────────────────────────────────────────
echo -e "\n${BLUE}PASSO 1: Aplicando a Infraestrutura via Terraform...${NC}"
cd "$TF_DIR"

if [ ! -f "terraform.tfvars" ]; then
    echo -e "${YELLOW}Criando terraform.tfvars com valores padrão...${NC}"
    cp terraform.tfvars.example terraform.tfvars
fi

terraform init
terraform apply -auto-approve

# Captura variáveis do Terraform
JOB_NAME=$(terraform output -raw glue_job_name)
BUCKET_NAME=$(terraform output -raw analytics_bucket_name)

echo -e "${GREEN}✓ Terraform aplicado com sucesso!${NC}"
echo -e "  Glue Job Name: ${GREEN}$JOB_NAME${NC}"
echo -e "  S3 Bucket Name: ${GREEN}$BUCKET_NAME${NC}"

# ── Passo 2: Inicialização do Watermark ──────────────────────────────
echo -e "\n${BLUE}PASSO 2: Inicializando o Watermark no RDS (Task 1)...${NC}"
cd "$T1_DIR"

if [ ! -f ".env" ]; then
    echo -e "${YELLOW}Copiando arquivo .env da carga do A1 para a pasta Task 1...${NC}"
    cp ../../../../assignment_1/task_1/grupo_2/final/rds_connection.env .env
fi

python3 scripts/init_watermark.py

# ── Passo 3: Execução 1 do Glue (Carga de Histórico) ─────────────────
echo -e "\n${BLUE}PASSO 3: Iniciando a primeira execução do Glue (Full load histórico)...${NC}"
RUN_ID=$(aws glue start-job-run --job-name "$JOB_NAME" --query "JobRunId" --output text)
wait_for_glue_job "$JOB_NAME" "$RUN_ID"

echo -e "\n${BLUE}Verificando Watermark após a primeira execução...${NC}"
python3 scripts/validate_incremental_source.py

# ── Passo 4: Simulação de Novos Pedidos ──────────────────────────────
echo -e "\n${BLUE}PASSO 4: Simulando a chegada de 5 novos pedidos...${NC}"
python3 scripts/simulate_new_orders.py --count 5 --seed 42

echo -e "\n${BLUE}Verificando Watermark (deve apontar dados pendentes)...${NC}"
python3 scripts/validate_incremental_source.py

# ── Passo 5: Execução 2 do Glue (Carga Incremental) ─────────────────
echo -e "\n${BLUE}PASSO 5: Iniciando a segunda execução do Glue (Carga Incremental)...${NC}"
RUN_ID2=$(aws glue start-job-run --job-name "$JOB_NAME" --query "JobRunId" --output text)
wait_for_glue_job "$JOB_NAME" "$RUN_ID2"

# ── Passo 6: Validação Final ──────────────────────────────────────────
echo -e "\n${BLUE}PASSO 6: Validação de Watermark e Partições S3...${NC}"

echo -e "\n${YELLOW}1. Estado do Watermark no RDS (deve ter avançado para 2026-05-15):${NC}"
python3 -c "
import sys; sys.path.insert(0, '$T1_DIR'); import db_config
conn = db_config.get_connection(autocommit=True)
cur = conn.cursor()
cur.execute('SELECT last_processed_order_date, last_run_status, last_run_at FROM etl_watermark')
row = cur.fetchone()
print(f'  Watermark Date: {row[0]}')
print(f'  Status:         {row[1]}')
print(f'  Last Run At:    {row[2]}')
conn.close()
"

echo -e "\n${YELLOW}2. Estrutura de Partições gerada no S3 para fact_orders:${NC}"
aws s3 ls "s3://$BUCKET_NAME/analytics/fact_orders/" --recursive | grep ".parquet" | head -n 20

echo -e "\n${BLUE}════════════════════════════════════════════════════════"
echo -e "  ✓ VALIDAÇÃO DA TASK 2 CONCLUÍDA COM SUCESSO!"
echo -e "════════════════════════════════════════════════════════${NC}"
