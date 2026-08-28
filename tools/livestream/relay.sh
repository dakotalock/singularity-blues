#!/usr/bin/env bash
set -uo pipefail

# Potato-mode relay: pre-encoded HLS -> RTMP. No Chromium, X11, WebGL,
# scaling, interpolation, decoding, or encoding on the normal path.

SOURCE_URL="${BROADCAST_SOURCE_URL:-https://singularity-blues.onrender.com/broadcast/live.m3u8}"
STATE_DIR="${STATE_DIR:-/var/lib/singularity-blues-relay}"
SOURCE_TIMEOUT="${SOURCE_TIMEOUT:-25}"
FALLBACK_SECONDS="${FALLBACK_SECONDS:-30}"
MAX_BACKOFF="${MAX_BACKOFF:-60}"

mkdir -p "$STATE_DIR"
PROGRESS_PATH="$STATE_DIR/ffmpeg.progress"
PID_PATH="$STATE_DIR/ffmpeg.pid"
RESTART_PATH="$STATE_DIR/restarts"
FALLBACK_PATH="$STATE_DIR/fallback.mp4"

destination="${RTMP_URL:-}"
if [[ -z "$destination" && -n "${TWITCH_STREAM_KEY:-}" ]]; then
  destination="${TWITCH_RTMP_URL:-rtmps://live.twitch.tv/app}/${TWITCH_STREAM_KEY}"
fi
if [[ -z "$destination" && -n "${YOUTUBE_STREAM_KEY:-}" ]]; then
  destination="${YOUTUBE_RTMP_URL:-rtmps://a.rtmp.youtube.com/live2}/${YOUTUBE_STREAM_KEY}"
fi
if [[ -z "$destination" ]]; then
  echo "Set RTMP_URL or a Twitch/YouTube stream key in the protected environment file." >&2
  exit 64
fi

for required in ffmpeg curl; do
  if ! command -v "$required" >/dev/null 2>&1; then
    echo "$required is required." >&2
    exit 69
  fi
done

child_pid=""
cleanup() {
  if [[ -n "$child_pid" ]]; then
    kill "$child_pid" 2>/dev/null || true
    wait "$child_pid" 2>/dev/null || true
  fi
  rm -f "$PID_PATH"
}
terminate() {
  cleanup
  exit 0
}
trap cleanup EXIT
trap terminate INT TERM

restart_count="$(cat "$RESTART_PATH" 2>/dev/null || true)"
[[ "$restart_count" =~ ^[0-9]+$ ]] || restart_count=0

make_fallback() {
  [[ -s "$FALLBACK_PATH" ]] && return 0
  local tmp="$FALLBACK_PATH.tmp.mp4"
  rm -f "$tmp"
  ffmpeg -nostdin -hide_banner -loglevel error -y \
    -f lavfi -i "color=c=0x101722:s=640x360:r=30" \
    -f lavfi -i "anullsrc=r=48000:cl=stereo" \
    -t 6 -c:v libx264 -preset ultrafast -tune stillimage,zerolatency \
    -pix_fmt yuv420p -r 30 -g 60 -keyint_min 60 -sc_threshold 0 \
    -b:v 300k -maxrate 400k -bufsize 600k \
    -c:a aac -b:a 64k -ar 48000 -ac 2 -movflags +faststart -f mp4 "$tmp"
  mv "$tmp" "$FALLBACK_PATH"
}

run_ffmpeg() {
  rm -f "$PROGRESS_PATH"
  ffmpeg -y "$@" &
  child_pid=$!
  printf '%s\n' "$child_pid" > "$PID_PATH"
  wait "$child_pid"
  local status=$?
  child_pid=""
  rm -f "$PID_PATH"
  return "$status"
}

relay_source() {
  echo "$(date -u +%FT%TZ) source available; starting HLS packet copy"
  run_ffmpeg \
    -nostdin -hide_banner -loglevel warning \
    -rw_timeout 20000000 -reconnect 1 -reconnect_streamed 1 \
    -reconnect_at_eof 1 -reconnect_delay_max 10 \
    -fflags +genpts+discardcorrupt -re -i "$SOURCE_URL" \
    -map 0:v:0 -map 0:a:0 -c:v copy -c:a copy \
    -flvflags no_duration_filesize -progress "$PROGRESS_PATH" \
    -f flv "$destination"
}

relay_fallback() {
  make_fallback || return 1
  echo "$(date -u +%FT%TZ) source unavailable; sending ${FALLBACK_SECONDS}s fallback"
  run_ffmpeg \
    -nostdin -hide_banner -loglevel warning \
    -stream_loop -1 -re -i "$FALLBACK_PATH" -t "$FALLBACK_SECONDS" \
    -map 0:v:0 -map 0:a:0 -c:v copy -c:a copy \
    -flvflags no_duration_filesize -progress "$PROGRESS_PATH" \
    -f flv "$destination"
}

backoff=5
while true; do
  restart_count=$((restart_count + 1))
  printf '%s\n' "$restart_count" > "$RESTART_PATH"

  if curl --fail --silent --show-error --max-time "$SOURCE_TIMEOUT" \
      -o /dev/null "$SOURCE_URL"; then
    started="$(date +%s)"
    relay_source || true
    runtime=$(( $(date +%s) - started ))
    if (( runtime >= 120 )); then
      backoff=5
    fi
  else
    if relay_fallback; then
      # The completed fallback maintained ingest for this retry interval.
      # Recheck upstream immediately instead of adding a dead-air sleep.
      backoff=5
      continue
    fi
  fi

  echo "$(date -u +%FT%TZ) relay stopped; retrying in ${backoff}s"
  sleep "$backoff"
  backoff=$((backoff * 2))
  (( backoff > MAX_BACKOFF )) && backoff="$MAX_BACKOFF"
done
