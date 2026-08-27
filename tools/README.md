# Local tools (not in git)

Download these onto the machine that runs the show. Keep them out of the repo.

## Godot 4.4.1

Linux x86_64 from https://github.com/godotengine/godot/releases/tag/4.4.1-stable

```bash
# from repo root
mkdir -p tools
curl -L -o tools/godot.zip \
  https://github.com/godotengine/godot/releases/download/4.4.1-stable/Godot_v4.4.1-stable_linux.x86_64.zip
unzip -o tools/godot.zip -d tools
ln -sf Godot_v4.4.1-stable_linux.x86_64 tools/godot
chmod +x tools/godot tools/Godot_v4.4.1-stable_linux.x86_64
```

Open the stage: `tools/godot --path renderer`

Record a take: `renderer/export_watch.sh --record`

After changing renderer scripts, refresh the deployable Web pack:

```bash
tools/godot --headless --path renderer --export-pack Web ../web/stage/index.pck
python tools/split_web_pck.py
```

Render reconstructs `web/stage/index.pck` from the committed text chunks.

## Piper TTS

rhasspy/piper Linux amd64 release. Voices are rhasspy piper-voices medium English:

| character | voice |
|-----------|--------|
| Reed      | en_US-ryan-medium |
| Maris     | en_US-amy-medium |
| Jinx      | en_GB-alba-medium |
| Quill     | en_US-lessac-medium |

Put the `.onnx` + `.onnx.json` files in `tts/voices/`. JSON configs are in git; the models are not.

Without Piper the orchestrator falls back to ffmpeg sine tones so Godot can still lip-flap.
