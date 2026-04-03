#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────
# run_all.sh – Regenerate everything from scratch
#
# Usage:  cd SSC2026 && bash run_all.sh
#
# What it does:
#   1. Runs the ABM simulation  → output/figures/*.png
#
# Prerequisites:
#   Python 3 with: numpy, networkx, pyshp, shapely, matplotlib
# ──────────────────────────────────────────────────────────
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
echo "=== Project root: $ROOT ==="

# ── Step 1: Run the simulation ────────────────────────────
echo ""
echo ">>> Step 1/1: Running ABM simulation (akl_sim_v2.py) ..."
python3 "$ROOT/code/akl_sim_v2.py"
echo "    Figures saved to: $ROOT/output/figures/"

echo ""
echo "=== All done! ==="
echo "    Figures: output/figures/"
