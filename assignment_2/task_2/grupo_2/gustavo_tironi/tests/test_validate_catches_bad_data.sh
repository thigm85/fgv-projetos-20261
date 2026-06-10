#!/bin/bash
# Prova que validate_incremental_source detecta dado quebrado no RDS.
#
# Fluxo:
#   1. validate antes (deve passar — RDS limpo)
#   2. injeta orders SEM orderdetails (via Python, bypassa Lambda)
#   3. validate depois (deve FALHAR — orphan detectado)
#   4. cleanup: remove pedido injetado
#   5. validate final (deve passar de novo)

set -e
cd "$(dirname "$0")/.."

echo "============================================"
echo "PASSO 1 — validate ANTES (estado limpo)"
echo "============================================"
python src/validate_incremental_source.py && echo "  → validate=0 (esperado)" || echo "  → validate=1 (INESPERADO antes da injeção)"

echo
echo "============================================"
echo "PASSO 2 — injetando pedido sem orderdetails (bypassa gate)"
echo "============================================"
python scripts/_inject_bad_order.py inject

echo
echo "============================================"
echo "PASSO 3 — validate DEPOIS (deve detectar orphan)"
echo "============================================"
if python src/validate_incremental_source.py; then
    echo "  → validate=0 (FAIL: deveria ter detectado dado quebrado)"
    EXIT_CODE=1
else
    echo "  → validate=1 (OK: gate de pós-validação funcionou)"
    EXIT_CODE=0
fi

echo
echo "============================================"
echo "PASSO 4 — cleanup do pedido injetado"
echo "============================================"
python scripts/_inject_bad_order.py cleanup

echo
echo "============================================"
echo "PASSO 5 — validate FINAL (deve passar de novo)"
echo "============================================"
python src/validate_incremental_source.py && echo "  → validate=0 (estado limpo restaurado)" || echo "  → validate=1 (cleanup falhou)"

echo
if [ $EXIT_CODE -eq 0 ]; then
    echo "RESULTADO: validate detectou dado quebrado ✓"
else
    echo "RESULTADO: FALHOU — validate não detectou"
fi
exit $EXIT_CODE
