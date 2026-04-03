#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────
# run_all.sh – Regenerate everything from scratch
#
# Usage:  cd Congestion && bash run_all.sh
#
# What it does:
#   1. Runs the ABM simulation  → output/figures/*.png
#   2. Builds the paper (docx)  → output/paper/congestion_paper.docx
#   3. Converts to PDF          → output/paper/congestion_paper.pdf
#
# Prerequisites:
#   Python 3 with: numpy, networkx, pyshp, shapely, matplotlib
#   Node.js with:  docx (run  cd code/paper && npm install  once)
#   LibreOffice    (soffice) for PDF conversion
# ──────────────────────────────────────────────────────────
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
echo "=== Project root: $ROOT ==="

# ── Step 1: Run the simulation ────────────────────────────
echo ""
echo ">>> Step 1/3: Running ABM simulation (akl_sim_v2.py) ..."
python3 "$ROOT/code/simulation/akl_sim_v2.py"
echo "    Figures saved to: $ROOT/output/figures/"

# ── Step 2: Generate paper (docx) ─────────────────────────
echo ""
echo ">>> Step 2/3: Generating Word document (paper_v4.js) ..."
cd "$ROOT/code/paper"
if [ ! -d "node_modules" ]; then
    echo "    Installing Node dependencies ..."
    npm install
fi
node paper_v4.js
echo "    Paper saved to: $ROOT/output/paper/congestion_paper.docx"

# ── Step 3: Convert to PDF ────────────────────────────────
echo ""
echo ">>> Step 3/3: Converting to PDF ..."
cd "$ROOT/output/paper"
soffice --headless --convert-to pdf congestion_paper.docx
echo "    PDF saved to: $ROOT/output/paper/congestion_paper.pdf"

echo ""
echo "=== All done! ==="
echo "    Paper:   output/paper/congestion_paper.docx"
echo "    PDF:     output/paper/congestion_paper.pdf"
echo "    Figures: output/figures/"
