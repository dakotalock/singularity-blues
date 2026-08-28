#!/usr/bin/env bash
set -uo pipefail

STATE_DIR="${STATE_DIR:-/var/lib/singularity-blues-relay}"
SOURCE_URL="${BROADCAST_SOURCE_URL:-https://singularity-blues.onrender.com/broadcast/live.m3u8}"
MAX_PROGRESS_AGE="${MAX_PROGRESS_AGE:-45}"
PID_PATH="$STATE_DIR/ffmpeg.pid"
PROGRESS_PATH="$STATE_DIR/ffmpeg.progress"

now="$(date +%s)"
pid="$(cat "$PID_PATH" 2>/dev/null || true)"
progress_age=999999
if [[ -f "$PROGRESS_PATH" ]]; then
  progress_age=$((now - $(stat -c %Y "$PROGRESS_PATH")))
fi

source_ok=false
if curl --fail --silent --max-time 10 -o /dev/null "$SOURCE_URL"; then
  source_ok=true
fi

process_ok=false
cpu="0.0"
rss_kb="0"
if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
  process_ok=true
  read -r cpu rss_kb < <(ps -o %cpu=,rss= -p "$pid" 2>/dev/null || printf '0.0 0\n')
fi

load="$(cut -d' ' -f1-3 /proc/loadavg)"
restarts="$(cat "$STATE_DIR/restarts" 2>/dev/null || printf '0')"
out_time="$(awk -F= '$1=="out_time"{v=$2} END{print v}' "$PROGRESS_PATH" 2>/dev/null)"
fps="$(awk -F= '$1=="fps"{v=$2} END{print v}' "$PROGRESS_PATH" 2>/dev/null)"
dropped="$(awk -F= '$1=="drop_frames"{v=$2} END{print v}' "$PROGRESS_PATH" 2>/dev/null)"
speed="$(awk -F= '$1=="speed"{v=$2} END{print v}' "$PROGRESS_PATH" 2>/dev/null)"

printf 'source_ok=%s process_ok=%s progress_age_sec=%s pid=%s cpu_pct=%s rss_kb=%s load="%s" restarts=%s out_time=%s fps=%s dropped=%s speed=%s webgl_context_losses=0\n' \
  "$source_ok" "$process_ok" "$progress_age" "${pid:-none}" "$cpu" "$rss_kb" \
  "$load" "$restarts" "${out_time:-unknown}" "${fps:-unknown}" \
  "${dropped:-unknown}" "${speed:-unknown}"

if [[ "$process_ok" != true || "$progress_age" -gt "$MAX_PROGRESS_AGE" ]]; then
  exit 1
fi
