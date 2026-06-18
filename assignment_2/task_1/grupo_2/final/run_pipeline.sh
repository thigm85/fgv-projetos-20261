#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════
# Pipeline Task 1 — Fluxo completo de validação
#
# Executa os 4 passos do fluxo sugerido no enunciado:
#   1. init_watermark              → cria/atualiza etl_watermark com baseline
#   2. validate_incremental_source → deve passar (baseline coerente)
#   3. simulate_new_orders         → insere pedidos novos
#   4. validate_incremental_source → deve passar (há dados pendentes)
#
# Uso:
#   bash run_pipeline.sh                    # 5 pedidos, sem seed
#   bash run_pipeline.sh --count 10         # 10 pedidos
#   bash run_pipeline.sh --count 5 --seed 42  # reprodutível
# ═══════════════════════════════════════════════════════════════════════

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Parâmetros passados para o simulador (default: --count 5 --seed 42)
SIM_ARGS="${@:---count 5 --seed 42}"

echo ""
echo "════════════════════════════════════════════════════════"
echo "  Pipeline Task 1 — Fluxo completo"
echo "  Diretório: $SCRIPT_DIR"
echo "  Parâmetros do simulador: $SIM_ARGS"
echo "════════════════════════════════════════════════════════"

# ── Passo 1: Inicializar watermark ────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════"
echo "  PASSO 1 — init_watermark"
echo "════════════════════════════════════════════════════════"
python3 "$SCRIPT_DIR/scripts/init_watermark.py"

# ── Passo 2: Validar baseline ────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════"
echo "  PASSO 2 — validate_incremental_source (baseline)"
echo "════════════════════════════════════════════════════════"
python3 "$SCRIPT_DIR/scripts/validate_incremental_source.py"

# ── Passo 3: Simular novos pedidos ───────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════"
echo "  PASSO 3 — simulate_new_orders $SIM_ARGS"
echo "════════════════════════════════════════════════════════"
python3 "$SCRIPT_DIR/scripts/simulate_new_orders.py" $SIM_ARGS

# ── Passo 4: Validar com dados pendentes ─────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════"
echo "  PASSO 4 — validate_incremental_source (com dados pendentes)"
echo "════════════════════════════════════════════════════════"
python3 "$SCRIPT_DIR/scripts/validate_incremental_source.py"

echo ""
echo "════════════════════════════════════════════════════════"
echo "  ✓ PIPELINE TASK 1 CONCLUÍDO COM SUCESSO"
echo "════════════════════════════════════════════════════════"
echo ""
