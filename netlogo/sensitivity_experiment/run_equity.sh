#!/bin/bash
# Run the equity-by-quintile experiment (equity_experiment.xml) headless.
#
# Usage:
#   export NETLOGO=~/NetLogo-6.4.0-64
#   bash run_equity.sh
#
# Writes output/tables/equity-quintile.csv, then plot with:
#   python3 plot_equity.py
#
# Requires NetLogo 6.x (tested with 6.4.0 headless, Java 11+). Runs from the
# netlogo/ folder so the model's relative "Data/..." paths resolve.

set -e
NETLOGO="${NETLOGO:?Set NETLOGO to your NetLogo install dir, e.g. export NETLOGO=~/NetLogo-6.4.0-64}"
HEADLESS="$NETLOGO/netlogo-headless.sh"
HERE="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
NETLOGO_DIR="$( dirname "$HERE" )"          # the netlogo/ folder (model + Data live here)
MODEL="$NETLOGO_DIR/akl_traffic.nlogo"
XML="$HERE/equity_experiment.xml"
OUT="$NETLOGO_DIR/../output/tables"
mkdir -p "$OUT"

cd "$NETLOGO_DIR"   # so Data/... resolves
echo ">>> running equity-quintile"
bash "$HEADLESS" --model "$MODEL" \
  --setup-file "$XML" --experiment equity-quintile \
  --table "$OUT/equity-quintile.csv" --threads "$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 2)"
echo "Done. Table in $OUT/equity-quintile.csv. Now run: python3 $HERE/plot_equity.py"
