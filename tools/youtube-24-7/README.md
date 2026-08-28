# 24/7 YouTube helper

> Legacy rollback path. The normal deployment should use the pre-encoded packet
> relay in [`tools/livestream/`](../livestream/README.md), which removes the
> browser, WebGL, capture, and encoder from the small VM.

Kiosk-capture the living-room set (`?broadcast=1` hides Selector chrome) and push it to YouTube Live from an always-on OCI VM. A curl loop pings the site so Render’s free instance does not sleep.

**YouTube Live must already be enabled on the channel** (YouTube Studio → Go live). This script cannot turn that on.

## Install (Ubuntu / OCI)

```bash
sudo apt update
sudo apt install -y ffmpeg chromium-browser xvfb pulseaudio curl
```

## Run

```bash
export YOUTUBE_STREAM_KEY="your-stream-key"   # from YouTube Studio; never commit this
./tools/youtube-24-7/stream.sh
```

Optional env: `STAGE_URL` (default `https://singularity-blues.onrender.com/?broadcast=1`), `KEEPALIVE_URL` (default the same host).

## systemd (optional)

`/etc/systemd/system/singularity-blues-yt.service`:

```ini
[Unit]
Description=Singularity Blues YouTube 24/7
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=/etc/singularity-blues-yt.env
ExecStart=/home/ubuntu/singularity-blues/tools/youtube-24-7/stream.sh
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Put `YOUTUBE_STREAM_KEY=...` in `/etc/singularity-blues-yt.env` (`chmod 600`). Then:

```bash
sudo systemctl enable --now singularity-blues-yt
```
