#!/usr/bin/env bash
# Backup loop run by the container: backup -> rotate -> status, every BACKUP_INTERVAL seconds.
# A failed backup does not stop the loop: it shows up on the status page instead.
set -uo pipefail

APP_DIR="${APP_DIR:-/app}"
PYTHON="${PYTHON:-python3}"
DEST="${DEST:-/backups}"
STATUS_DIR="${STATUS_DIR:-/status}"
INTERVAL="${BACKUP_INTERVAL:-86400}"
ctl() { "$PYTHON" "$APP_DIR/backupctl.py" "$@"; }

run_cycle() {
    local args=() expect=() f u
    for f in ${SQLITE_FILES:-}; do args+=(--sqlite "$f"); expect+=(--expect "$(basename "${f%.*}")"); done
    for u in ${POSTGRES_URLS:-}; do args+=(--postgres "$u"); expect+=(--expect "${u##*/}"); done
    echo "[$(date -u +%FT%TZ)] backup"
    ctl backup --dest "$DEST" "${args[@]}"
    ctl rotate --dest "$DEST" --keep-daily "${KEEP_DAILY:-7}" --keep-weekly "${KEEP_WEEKLY:-4}"
    ctl status --dest "$DEST" "${expect[@]}" --max-age-hours "${MAX_AGE_HOURS:-26}" \
        --json "$STATUS_DIR/status.json" --html "$STATUS_DIR/index.html"
}

if [[ "${ONESHOT:-0}" == 1 ]]; then
    run_cycle
    exit $?
fi
while true; do
    run_cycle
    sleep "$INTERVAL"
done
