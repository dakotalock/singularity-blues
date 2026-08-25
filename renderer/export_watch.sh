#!/usr/bin/env bash
# Launch The Singularity Blues living-room stage.
#   ./export_watch.sh              # window if DISPLAY, else xvfb
#   ./export_watch.sh --record     # movie-maker / x11grab -> data/pilot.mp4
# Extra args after -- go to Godot user args (e.g. -- --scene /path.json)
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GODOT="${GODOT:-$ROOT/tools/godot}"
if [[ ! -x "$GODOT" && -x "$ROOT/tools/Godot_v4.4.1-stable_linux.x86_64" ]]; then
  GODOT="$ROOT/tools/Godot_v4.4.1-stable_linux.x86_64"
fi
PROJECT="$ROOT/renderer"
OUT_DIR="$ROOT/data"
mkdir -p "$OUT_DIR"
MP4="$OUT_DIR/pilot.mp4"
AVI="$OUT_DIR/pilot.avi"
HTML="$ROOT/web/watch.html"
VF="scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:black,setsar=1"

RECORD=0
GODOT_ARGS=()
USER_ARGS=()
SEEN_DD=0
for a in "$@"; do
  if [[ "$a" == "--record" ]]; then
    RECORD=1
    continue
  fi
  if [[ "$a" == "--" ]]; then
    SEEN_DD=1
    continue
  fi
  if [[ "$SEEN_DD" == 1 ]]; then
    USER_ARGS+=("$a")
  else
    GODOT_ARGS+=("$a")
  fi
done

if [[ ! -x "$GODOT" ]]; then
  echo "Godot binary not found at $GODOT" >&2
  echo "Fallback: open $HTML in a browser." >&2
  exit 1
fi

# Interactive watch mode must retain WAV playback. Dummy audio belongs only to
# headless/Xvfb capture, where no sound device is expected.
COMMON=(--path "$PROJECT" --rendering-driver opengl3 --resolution 1280x720)
HEADLESS_COMMON=("${COMMON[@]}" --audio-driver Dummy)

run_godot() {
  echo "Launching: $GODOT ${COMMON[*]} $*" >&2
  "$GODOT" "${COMMON[@]}" "$@"
}

encode_mp4() {
  command -v ffmpeg >/dev/null 2>&1 || return 1
  [[ -s "$AVI" ]] || return 1
  rm -f "$MP4"
  ffmpeg -y -i "$AVI" -vf "$VF" -c:v libx264 -pix_fmt yuv420p -crf 20 -preset fast \
    -an -movflags +faststart "$MP4" </dev/null || true
  if [[ -s "$MP4" ]]; then
    echo "Wrote $MP4"
    return 0
  fi
  return 1
}

record_movie() {
  rm -f "$AVI"
  echo "Recording via Godot movie writer -> $AVI" >&2
  local movie_args=(--write-movie "$AVI" --fixed-fps 30 --quit-after 3300 --disable-vsync)
  movie_args+=(-- --quit-after-scene)
  movie_args+=("${USER_ARGS[@]}")
  SINGULARITY_QUIT_AFTER=1 run_godot "${movie_args[@]}" || true
  if [[ -s "$AVI" ]]; then
    encode_mp4 && return 0
    echo "AVI written but mp4 convert failed: $AVI"
    return 0
  fi
  return 1
}

record_x11() {
  if [[ -z "${DISPLAY:-}" ]] || ! command -v ffmpeg >/dev/null 2>&1; then
    return 1
  fi
  echo "Recording via ffmpeg x11grab on DISPLAY=$DISPLAY" >&2
  local log="$OUT_DIR/godot_record.log"
  SINGULARITY_QUIT_AFTER=1 run_godot -- --quit-after-scene "${USER_ARGS[@]}" >"$log" 2>&1 &
  local gpid=$!
  sleep 1.5
  if ! kill -0 "$gpid" 2>/dev/null; then
    echo "Godot exited before x11grab." >&2
    cat "$log" >&2 || true
    return 1
  fi
  rm -f "$MP4"
  ffmpeg -y -f x11grab -video_size 1280x720 -framerate 30 -i "${DISPLAY}.0+0,0" \
    -t 75 -vf "$VF" -c:v libx264 -pix_fmt yuv420p -crf 20 -an "$MP4" </dev/null || true
  wait "$gpid" || true
  if [[ -s "$MP4" ]]; then
    echo "Wrote $MP4"
    return 0
  fi
  return 1
}

fallback_html() {
  echo "Godot could not present a display. Fallback stage: $HTML" >&2
  echo "Open it with: python3 -m http.server -d $ROOT 8765  then browse /web/watch.html" >&2
}

if [[ "$RECORD" == 1 ]]; then
  if [[ -n "${DISPLAY:-}" ]]; then
    if record_movie || record_x11; then
      exit 0
    fi
  fi
  if command -v xvfb-run >/dev/null 2>&1; then
    echo "Trying xvfb-run for movie writer..." >&2
    xvfb-run -a -s "-screen 0 1280x720x24" env SINGULARITY_QUIT_AFTER=1 \
      "$GODOT" "${HEADLESS_COMMON[@]}" --write-movie "$AVI" --fixed-fps 30 --quit-after 3300 --disable-vsync \
      -- --quit-after-scene "${USER_ARGS[@]}" || true
    if [[ -s "$AVI" ]]; then
      encode_mp4 || echo "AVI written: $AVI"
      exit 0
    fi
  fi
  fallback_html
  exit 1
fi

# Interactive / watch mode.
if [[ -n "${DISPLAY:-}" ]]; then
  if [[ ${#USER_ARGS[@]} -gt 0 ]]; then
    run_godot "${GODOT_ARGS[@]}" -- "${USER_ARGS[@]}"
  else
    run_godot "${GODOT_ARGS[@]}"
  fi
  code=$?
  if [[ $code -ne 0 ]]; then
    echo "Godot window failed (exit $code). Trying xvfb-run..." >&2
  else
    exit 0
  fi
fi

if command -v xvfb-run >/dev/null 2>&1; then
  echo "No usable DISPLAY; recording under xvfb-run." >&2
  xvfb-run -a -s "-screen 0 1280x720x24" env SINGULARITY_QUIT_AFTER=1 \
    "$GODOT" "${HEADLESS_COMMON[@]}" --write-movie "$AVI" --fixed-fps 30 --quit-after 3300 --disable-vsync \
    -- --quit-after-scene "${USER_ARGS[@]}" || true
  if [[ -s "$AVI" ]]; then
    encode_mp4 || true
  fi
  if [[ -s "$MP4" || -s "$AVI" || -f "$OUT_DIR/pilot.png" ]]; then
    echo "Artifacts in $OUT_DIR"
    exit 0
  fi
fi

fallback_html
exit 1
