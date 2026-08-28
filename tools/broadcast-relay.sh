#!/usr/bin/env bash
# Dumb relay: copy already-encoded HLS/TS from Render to Twitch or YouTube.
# No Chromium, no x11grab, no libx264. Stream key stays in a file, never echoed.
set -euo pipefail

SRC="${BROADCAST_URL:-https://singularity-blues.onrender.com/broadcast/live.m3u8}"
KEY_FILE="${STREAM_KEY_FILE:-/root/twitch-stream.key}"
DEST="${RTMP_BASE:-rtmp://live.twitch.tv/app}"

if [[ ! -s "$KEY_FILE" ]]; then
  echo "missing stream key file" >&2
  exit 1
fi
KEY=$(tr -d '[:space:]' < "$KEY_FILE")

# If upstream HLS stalls, ffmpeg exits; systemd Restart=always picks it up.
# -c copy is the whole point: the potato does not encode.
exec ffmpeg -hide_banner -loglevel warning -nostats \
  -reconnect 1 -reconnect_streamed 1 -reconnect_on_network_error 1 \
  -reconnect_delay_max 4 -rw_timeout 15000000 \
  -i "$SRC" \
  -c copy -bsf:a aac_adtstoasc \
  -f flv "${DEST}/${KEY}"
