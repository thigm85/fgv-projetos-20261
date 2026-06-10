#!/bin/bash
# Executa bateria de testes da Task 1:
#   1. validate_incremental_source antes
#   2. simulate direto RDS
#   3. simulate via Lambda
#   4. test_lambda_rejections (5 cenários de rejeição)
#   5. validate_incremental_source depois
#
# Passo 6 (injeção manual de dado quebrado no RDS) está documentado
# no README — não roda aqui pois envolve credenciais do Secrets Manager.

set -e
cd "$(dirname "$0")/.."

echo "============================================"
echo "PASSO 1 — validate (estado inicial)"
echo "============================================"
python src/validate_incremental_source.py || echo "  → validate retornou erro (esperado se watermark = MAX(orderDate))"

echo
echo "============================================"
echo "PASSO 2 — simulate direto no RDS"
echo "============================================"
python simulator/simulate_new_orders.py --count 3 --seed 42

echo
echo "============================================"
echo "PASSO 3 — simulate via Lambda gateway"
echo "============================================"
python simulator/simulate_new_orders.py --count 3 --seed 99 --via-lambda

echo
echo "============================================"
echo "PASSO 4 — testes de rejeição da Lambda"
echo "============================================"
python simulator/test_lambda_rejections.py

echo
echo "============================================"
echo "PASSO 5 — validate (estado final)"
echo "============================================"
python src/validate_incremental_source.py

echo
echo "TODOS OS PASSOS CONCLUÍDOS"
echo
echo "Para testar bloqueio do validate, ver README seção 'Injeção manual'."
