#!/usr/bin/env bash
# Daily ETL cron — run at 02:00 UTC
# Add to crontab: 0 2 * * * /path/to/daily_cron.sh >> /var/log/heatmap_cron.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DATA_SOURCE="${HEATMAP_DATA_SOURCE:-/data/kindergarten_daily.csv}"
LOG_DIR="${HEATMAP_LOG_DIR:-$PROJECT_ROOT/logs}"
MAX_RETRIES=3
RETRY_WAIT=60   # seconds

mkdir -p "$LOG_DIR"
LOGFILE="$LOG_DIR/pipeline_$(date +%Y%m%d).log"

log() { echo "[$(date -u +%FT%TZ)] $*" | tee -a "$LOGFILE"; }

run_pipeline() {
  cd "$PROJECT_ROOT"
  python -c "
from heatmap.backend.etl.pipeline import run_pipeline
import json, sys
result = run_pipeline('$DATA_SOURCE', source_type='csv', push_cdn=True)
print(json.dumps(result, indent=2))
sys.exit(0 if not result['errors'] else 1)
" 2>&1 | tee -a "$LOGFILE"
  return ${PIPESTATUS[0]}
}

log "=== Jordan Heatmap Daily ETL START ==="

for attempt in $(seq 1 $MAX_RETRIES); do
  log "Attempt $attempt / $MAX_RETRIES"
  if run_pipeline; then
    log "Pipeline succeeded on attempt $attempt"
    log "=== DONE ==="
    exit 0
  fi
  log "Pipeline failed on attempt $attempt"
  if [ "$attempt" -lt "$MAX_RETRIES" ]; then
    log "Waiting ${RETRY_WAIT}s before retry..."
    sleep "$RETRY_WAIT"
    RETRY_WAIT=$((RETRY_WAIT * 2))  # exponential backoff
  fi
done

log "Pipeline failed after $MAX_RETRIES attempts"
log "=== FAILED ==="
exit 1
