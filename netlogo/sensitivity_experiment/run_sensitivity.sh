#!/bin/bash
# Run the behavioural-parameter sensitivity analysis for the SSC2026 model.
#
# Usage:
#   export NETLOGO=~/NetLogo-6.4.0-64
#   bash run_sensitivity.sh
#
# Requires NetLogo 6.x (tested with 6.4.0 headless, Java 11+). The gis, nw, csv
# and table extensions ship with NetLogo. The script runs from the netlogo/
# folder so the model's relative "Data/..." paths resolve.

set -e
NETLOGO="${NETLOGO:?Set NETLOGO to your NetLogo install dir, e.g. export NETLOGO=~/NetLogo-6.4.0-64}"
HEADLESS="$NETLOGO/netlogo-headless.sh"
HERE="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
NETLOGO_DIR="$( dirname "$HERE" )"          # the netlogo/ folder (model + Data live here)
MODEL="$NETLOGO_DIR/akl_traffic.nlogo"
XML="$HERE/sensitivity_experiment.xml"
OUT="$NETLOGO_DIR/../output/tables"
mkdir -p "$OUT"

cd "$NETLOGO_DIR"   # so Data/... resolves
for EXP in sensitivity-pay sensitivity-elfarol sensitivity-ql-alpha sensitivity-ql-epsilon; do
  echo ">>> running $EXP"
  bash "$HEADLESS" --model "$MODEL" \
    --setup-file "$XML" --experiment "$EXP" \
    --table "$OUT/${EXP}.csv" --threads "$(nproc 2>/dev/null || echo 2)"
done
echo "Done. Tables in $OUT. Now run: python3 $HERE/aggregate_sensitivity.py"
