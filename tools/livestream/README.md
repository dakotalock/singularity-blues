# Pre-encoded 24/7 livestream

This is the cheap appliance path. The relay VM never opens the website. It
reads a rolling HLS playlist containing Twitch-ready H.264/AAC and remuxes the
packets into RTMP/FLV with `-c:v copy -c:a copy`.

The old Chromium/Xvfb capture is intentionally preserved under
`tools/youtube-24-7/` as the rollback path.

## Audited data path

The normal site is not a video player. FastAPI redirects `/` to `/stage/`,
where a Godot Web export paints a WebGL canvas. `ScenePlayer.gd` polls
`/now-playing`, downloads each beat's WAV separately, and plays it through a
Godot `AudioStreamPlayer`. There is no HTML video, MediaSource, WebRTC,
HLS/DASH, MP4, or encoded stream underneath the canvas to bypass.

The legacy relay launches Xvfb and Chromium at 1280x720, captures X11 and
PulseAudio, and runs this real-time video path:

```text
x11grab -> libx264 veryfast 2500k -> AAC 128k -> RTMP
```

That makes Chromium/WebGL/compositing plus x264 the CPU bottleneck. FFmpeg can
repeat frames at 30 FPS, but the measured source on the two-core VM supplies
only 3-5 genuinely new frames per second.

Episodes are a better seam. Before playback, the backend already has the full
scene, set, camera, dialogue, animations, WAV paths, and durations. The new TV
renderer uses that future state to render faster or slower than real time into
six-second fragments:

```text
scene packet + Piper WAVs
  -> cheap 640x360 semantic TV renderer (Render worker thread)
  -> 30 FPS H.264 + 48 kHz stereo AAC MPEG-TS fragments
  -> Cloudflare R2 episode cache
  -> 30-180 second rolling HLS playlist
  -> potato VM FFmpeg stream copy
  -> Twitch RTMP
```

This TV representation deliberately uses inexpensive 2D sets and characters.
The public Godot/WebGL show, its interactivity, memory, voices, animation logic,
and viewer GPU rendering are unchanged.

## Render and R2 setup

The Render blueprint enables the renderer and declares the R2 variables. Set
these secret values in the existing Render service:

```dotenv
R2_ACCOUNT_ID=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET=...
R2_PUBLIC_BASE_URL=https://media.your-domain.example
```

`R2_PUBLIC_BASE_URL` must publicly serve the configured bucket at its root.
The renderer writes `broadcast/<asset-id>/seg-NNN.ts` and `asset.json`. R2 is
important: it lets each scene upload once and keeps continuous segment traffic
off Render. Without a public R2 URL, the feature still works through FastAPI,
but Render proxies all video bytes.

After deploying, wait for the fallback and first rerun to encode:

```bash
curl -fsS https://singularity-blues.onrender.com/broadcast/healthz
curl -fsS https://singularity-blues.onrender.com/broadcast/live.m3u8
ffprobe -v error \
  -show_entries stream=codec_name,codec_type,width,height,r_frame_rate,sample_rate,channels \
  https://singularity-blues.onrender.com/broadcast/live.m3u8
```

Healthy output has H.264 at 640x360/30 and AAC at 48000 Hz stereo. The health
JSON reports asset count, render queue, buffer depth, last wall/media time,
render speed, failures, FFmpeg availability, and R2 state.

Reference two-core-affinity smoke test (not a promise about Render hardware): a
12.0-second semantic episode encoded in 0.943 seconds (12.72x), with the Python
process peaking at about 30 MB RSS. Real-time `-c copy` playback took 11.55
seconds and consumed only 0.08 user + 0.01 system CPU seconds. Production caps
the background renderer at 2.5x and runs its encoder at nice level 10 so prompts
and Piper retain CPU priority. Confirm production figures through the health
endpoint and VM commands below before retiring the legacy path.

## Install the relay VM

These commands assume this repo lives at `/opt/singularity-blues`:

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg curl git
sudo git clone https://github.com/dakotalock/singularity-blues.git /opt/singularity-blues

sudo install -m 0644 \
  /opt/singularity-blues/tools/livestream/singularity-blues-relay.service \
  /etc/systemd/system/singularity-blues-relay.service
sudo install -m 0644 \
  /opt/singularity-blues/tools/livestream/singularity-blues-relay-watchdog.service \
  /etc/systemd/system/singularity-blues-relay-watchdog.service
sudo install -m 0644 \
  /opt/singularity-blues/tools/livestream/singularity-blues-relay-watchdog.timer \
  /etc/systemd/system/singularity-blues-relay-watchdog.timer
sudo install -m 0600 \
  /opt/singularity-blues/tools/livestream/relay.env.example \
  /etc/singularity-blues-relay.env
sudoedit /etc/singularity-blues-relay.env

sudo systemctl daemon-reload
sudo systemctl enable --now singularity-blues-relay.service
sudo systemctl enable --now singularity-blues-relay-watchdog.timer
```

Put the Twitch key only in `/etc/singularity-blues-relay.env`. Do not commit it
or paste it into service logs.

## Add YouTube without touching Twitch

The YouTube relay is a second instance of the same packet-copy path. It reads
the same pre-encoded HLS feed, keeps separate state and health supervision, and
does not modify or restart the existing Twitch relay. One destination can
reconnect without interrupting the other.

Create a reusable YouTube stream in YouTube Studio and copy its stream key into
the protected YouTube-only environment file. Never commit or log that key.

```bash
cd /opt/singularity-blues
sudo git pull --ff-only origin main

sudo install -m 0644 \
  tools/livestream/singularity-blues-youtube-relay.service \
  /etc/systemd/system/singularity-blues-youtube-relay.service
sudo install -m 0644 \
  tools/livestream/singularity-blues-youtube-relay-watchdog.service \
  /etc/systemd/system/singularity-blues-youtube-relay-watchdog.service
sudo install -m 0644 \
  tools/livestream/singularity-blues-youtube-relay-watchdog.timer \
  /etc/systemd/system/singularity-blues-youtube-relay-watchdog.timer
sudo install -m 0600 \
  tools/livestream/youtube-relay.env.example \
  /etc/singularity-blues-youtube-relay.env
sudoedit /etc/singularity-blues-youtube-relay.env

sudo systemctl daemon-reload
sudo systemctl enable --now singularity-blues-youtube-relay.service
sudo systemctl enable --now singularity-blues-youtube-relay-watchdog.timer
```

Verify both independent outputs while they are live:

```bash
sudo systemctl status singularity-blues-relay.service
sudo systemctl status singularity-blues-youtube-relay.service
sudo env STATE_DIR=/var/lib/singularity-blues-relay \
  /opt/singularity-blues/tools/livestream/healthcheck.sh
sudo env STATE_DIR=/var/lib/singularity-blues-youtube-relay \
  /opt/singularity-blues/tools/livestream/healthcheck.sh
```

To roll back only YouTube, leave Twitch running and disable the new units:

```bash
sudo systemctl disable --now singularity-blues-youtube-relay-watchdog.timer
sudo systemctl disable --now singularity-blues-youtube-relay.service
```

### Render-side fallback when the VM login is unavailable

The existing Render web service can host the YouTube packet-copy relay without
changing the OVH Twitch relay. Set `YOUTUBE_STREAM_KEY` as a secret in Render
and use `bash tools/livestream/render-start.sh` as the service start command.
Never put the key in `render.yaml`, GitHub, screenshots, or logs.

The wrapper keeps Uvicorn as Render's foreground process and starts the relay
only when the secret is non-empty. It reads the local rolling HLS playlist,
copies H.264/AAC into YouTube RTMPS, stores disposable state under `/tmp`, and
scrubs the key from relay logs. If the sidecar fails, the public site and the
independent OVH-to-Twitch relay continue running.

Verify in Render logs:

```text
Render YouTube packet relay enabled
source available; starting HLS packet copy
```

Then wait for the preview in YouTube Live Control Room before making the stream
public. To disable this route, remove `YOUTUBE_STREAM_KEY` and restore the
original Uvicorn start command; no OVH change is required.

## Test packet copy before going live

Backend-only local test:

```bash
export BROADCAST_VIDEO_ENABLED=1
.venv/bin/uvicorn web.app:app --host 127.0.0.1 --port 8000
curl -fsS http://127.0.0.1:8000/broadcast/healthz
ffmpeg -t 30 -re -i http://127.0.0.1:8000/broadcast/live.m3u8 \
  -map 0:v:0 -map 0:a:0 -c:v copy -c:a copy -f flv /tmp/sb-copy-test.flv
ffprobe -v error -show_streams /tmp/sb-copy-test.flv
```

On the relay VM:

```bash
sudo systemctl status singularity-blues-relay.service
sudo journalctl -u singularity-blues-relay.service -f
sudo /opt/singularity-blues/tools/livestream/healthcheck.sh
curl -fsS https://singularity-blues.onrender.com/broadcast/healthz
```

For a before/after observation window:

```bash
pidstat -h -r -u -p ALL 10 12
free -h
uptime
sudo journalctl -u singularity-blues-relay.service --since '30 minutes ago' \
  | grep -c 'source available'
```

The relay health line includes its FFmpeg CPU/RSS, load average, progress age,
output time, reported FPS, drops, speed, and restart count. WebGL context losses
are permanently zero because the relay has no WebGL process. Twitch Inspector
is still the final authority for ingest FPS, bitrate stability, and disconnects.

## Failure behavior

- The backend keeps a bounded rolling playlist and a disk cap. Episode segments
  in R2 are the persistent rerun cache, not disposable relay state.
- A missing/stale HLS source makes FFmpeg exit. The relay sends a tiny local
  pre-encoded fallback loop for 30 seconds, then retries with capped exponential
  backoff.
- The watchdog kills a stuck FFmpeg when its progress file is stale. The relay
  wrapper reconnects; systemd restarts the wrapper if it exits.
- New episodes are rendered before random reruns. Existing completed R2 assets
  keep the live buffer supplied while a new episode is rendering.
- Broadcast renderer failure does not fail the public website or a paid prompt.

## Rollback

Stop the packet relay and return to the untouched legacy capture service/script:

```bash
sudo systemctl disable --now singularity-blues-relay-watchdog.timer
sudo systemctl disable --now singularity-blues-relay.service
cd /opt/singularity-blues
git checkout PREVIOUS_GOOD_COMMIT
```

Then restart the former Chromium capture unit, or run
`tools/youtube-24-7/stream.sh` with its original environment. No public-player
state or episode data migration is required.
