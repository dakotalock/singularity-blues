#!/usr/bin/env bash
set -euo pipefail

# 24/7 capture of the living-room set → YouTube Live.
# Stream key comes from the environment only. Never echo it.

STAGE_URL="${STAGE_URL:-https://singularity-blues.onrender.com/?broadcast=1}"
KEEPALIVE_URL="${KEEPALIVE_URL:-https://singularity-blues.onrender.com/}"
WIDTH="${WIDTH:-1280}"
HEIGHT="${HEIGHT:-720}"
FPS="${FPS:-30}"
DISPLAY_NUM="${DISPLAY_NUM:-:99}"

if [[ -z "${YOUTUBE_STREAM_KEY:-}" ]]; then
  echo "YOUTUBE_STREAM_KEY is not set. Export it first (YouTube Studio stream key)." >&2
  exit 1
fi

if command -v chromium-browser >/dev/null 2>&1; then
  CHROME_BIN=chromium-browser
elif command -v chromium >/dev/null 2>&1; then
  CHROME_BIN=chromium
else
  echo "chromium-browser (or chromium) is not installed." >&2
  exit 1
fi

cleanup() {
  [[ -n "${KEEP_PID:-}" ]] && kill "$KEEP_PID" 2>/dev/null || true
  [[ -n "${CHROME_PID:-}" ]] && kill "$CHROME_PID" 2>/dev/null || true
  [[ -n "${XVFB_PID:-}" ]] && kill "$XVFB_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

Xvfb "$DISPLAY_NUM" -screen 0 "${WIDTH}x${HEIGHT}x24" -nolisten tcp >/dev/null 2>&1 &
XVFB_PID=$!
export DISPLAY="$DISPLAY_NUM"
sleep 1

if ! pactl info >/dev/null 2>&1; then
  pulseaudio --start --exit-idle-time=-1 >/dev/null 2>&1 || true
fi

# Keep Render's free instance awake.
(
  while true; do
    curl -fsS -o /dev/null -m 20 "$KEEPALIVE_URL" || true
    sleep 240
  done
) &
KEEP_PID=$!

"$CHROME_BIN" \
  --kiosk \
  --no-first-run \
  --disable-translate \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --autoplay-policy=no-user-gesture-required \
  --window-size="${WIDTH},${HEIGHT}" \
  --window-position=0,0 \
  --user-data-dir="${HOME}/.cache/singularity-blues-kiosk" \
  "$STAGE_URL" >/dev/null 2>&1 &
CHROME_PID=$!

sleep 5

# x11grab + pulse → YouTube RTMP. Do not print the destination (it contains the key).
ffmpeg -hide_banner -loglevel error -nostats \
  -f x11grab -draw_mouse 0 -video_size "${WIDTH}x${HEIGHT}" -framerate "$FPS" -i "${DISPLAY_NUM}.0" \
  -f pulse -i default \
  -c:v libx264 -preset veryfast -tune zerolatency -pix_fmt yuv420p -r "$FPS" -g $((FPS * 2)) -b:v 2500k \
  -c:a aac -b:a 128k -ar 44100 -ac 2 \
  -f flv "rtmp://a.rtmp.youtube.com/live2/${YOUTUBE_STREAM_KEY}"
