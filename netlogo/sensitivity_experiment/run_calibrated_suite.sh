#!/bin/bash
# Re-run the full sensitivity suite on the CALIBRATED model (scale-factor 160 +
# suburban destinations). Concurrency is capped at 3 because the dev machine has
# only 8 GB RAM and BehaviorSpace shares one ~4 GB JVM heap across an experiment's
# parallel runs; 6-way concurrency thrashes GC (~4.5 h/experiment) while 3-way
# runs near-linearly (~2.2 h/experiment, ~11 h total). See LOS_IMPLEMENTATION.md.
#
# Usage:  caffeinate -is bash run_calibrated_suite.sh    # ~11 h, Mac stays awake
#         THREADS=6 caffeinate -is bash run_calibrated_suite.sh   # >=16 GB RAM
# n-sim-days is fixed at 20 in sensitivity_experiment.xml; to shorten the runs,
# edit the <n-sim-days> value there (BehaviorSpace can't override it per-CLI).
set -u
HEADLESS="/Applications/NetLogo 6.4.0/netlogo-headless.sh"
HERE="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
NLDIR="$( dirname "$HERE" )"
XML="$HERE/sensitivity_experiment.xml"
OUT="$NLDIR/../output/tables"
LOG=/tmp/suite_calibrated.log
THREADS="${THREADS:-3}"   # cap concurrency: 8 GB RAM thrashes GC at 6-way
: > "$LOG"

cd "$NLDIR" || exit 1
echo "[$(date '+%F %T')] calibrated suite start (threads=$THREADS)" >> "$LOG"
for EXP in sensitivity-pay sensitivity-elfarol sensitivity-ql-alpha sensitivity-ql-epsilon sensitivity-kfactor; do
  echo "[$(date '+%F %T')] >>> $EXP" >> "$LOG"
  bash "$HEADLESS" --model "$NLDIR/akl_traffic.nlogo" \
    --setup-file "$XML" --experiment "$EXP" \
    --table "$OUT/${EXP}.csv" --threads "$THREADS" >> "$LOG" 2>&1
  echo "[$(date '+%F %T')] <<< $EXP exit $?" >> "$LOG"
done
echo "[$(date '+%F %T')] aggregating" >> "$LOG"
cd "$HERE" || exit 1
python3 aggregate_sensitivity.py >> "$LOG" 2>&1
python3 plot_sensitivity.py >> "$LOG" 2>&1
echo "[$(date '+%F %T')] ALL DONE" >> "$LOG"
