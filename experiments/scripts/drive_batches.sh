#!/bin/bash
# Batch driver used for the Experiment A runs (v3 and v5/M3 were run this way).
# Runs one stage in batches of N calls until it ends for a reason other than the batch budget;
# on a subscription usage limit or repeated api_error it waits 15 minutes and resumes. Only the
# final line of each batch is logged, so arm-level outcomes are not seen during the run (§8a).
#
#   scripts/drive_batches.sh config/experiment_A_v5.frozen.yaml m3 30 progress.txt
set -u
CONFIG=$1; STAGE=$2; N=${3:-30}; P=${4:-progress.txt}
cd "$(dirname "$0")/.."
R=".venv/bin/python -m harness.runner_A --config $CONFIG"
waits=0
while true; do
  out=$($R "$STAGE" --max-calls "$N" 2>&1 | tail -1)
  case "$out" in
    *"batch budget"*) echo "$(date +%H:%M) batch" >> "$P" ;;
    *"usage limit"*|*"consecutive api_error"*)
      waits=$((waits+1)); echo "$(date +%H:%M) PAUSE $waits: $out" >> "$P"
      [ $waits -gt 40 ] && { echo "$(date +%H:%M) GIVING UP after $waits pauses" >> "$P"; exit 0; }
      sleep 900 ;;
    *) echo "$(date +%H:%M) END: $out" >> "$P"; exit 0 ;;
  esac
done
