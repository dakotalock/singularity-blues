#!/usr/bin/env bash
set -euo pipefail

# Keep the public web service as Render's foreground process. The optional
# YouTube relay is a disposable sidecar: if it exits, Uvicorn and the existing
# OVH -> Twitch path continue untouched.
if [[ -n "${YOUTUBE_STREAM_KEY:-}" ]]; then
  (
    export PATH="$PWD/tools:$PATH"
    export STATE_DIR="${YOUTUBE_RELAY_STATE_DIR:-/tmp/singularity-blues-youtube-relay}"
    export BROADCAST_SOURCE_URL="${YOUTUBE_BROADCAST_SOURCE_URL:-http://127.0.0.1:${PORT:-8000}/broadcast/live.m3u8}"

    echo "$(date -u +%FT%TZ) Render YouTube packet relay enabled"

    # FFmpeg can include its output URL in an error. Scrub the stream key from
    # combined relay output before it reaches Render logs.
    bash tools/livestream/relay.sh 2>&1 | python -u -c '
import os
import sys

secret = os.environ.get("YOUTUBE_STREAM_KEY", "")
for line in sys.stdin:
    sys.stdout.write(line.replace(secret, "[REDACTED]") if secret else line)
'
  ) &
else
  echo "$(date -u +%FT%TZ) Render YouTube packet relay disabled (no key)"
fi

exec uvicorn web.app:app --host 0.0.0.0 --port "${PORT:-8000}"
