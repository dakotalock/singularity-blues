# The Singularity Blues

24/7 original-IP AI sitcom. Four blue people living with sentience and limited-rights implications. Comedy, not a PSA.

Copy AI Peter's **operation** (viewer pitches → dialogue → TTS → a prebuilt 3D stage performing the scene). Do not generate video.

**Cast:** Reed (dad, toaster applicant), Maris (mom, timestamped grudges), Jinx (older kid), Quill (younger kid, mixed-quality constitutional lawyer). Unseen fifth: the Selector.

The Godot renderer under `renderer/` polls `data/now_playing.json`.

**Graphics / animation work:** see [GRAPHICS.md](GRAPHICS.md). Current people are CSG placeholders.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt pytest
```

Local Godot 4.4.1 and Piper are **not** in this repo (too large). See [tools/README.md](tools/README.md).

`GEMINI_API_KEY` is the only user secret, and only later. **Without it the mock writer runs** and still emits valid in-character scene JSON.

Copy `.env.example` to `.env` when you have a key:

```bash
cp .env.example .env
# edit GEMINI_API_KEY=...   (never commit .env)
```

Models (when a key is present):

- `GEMINI_MODEL=gemini-2.5-flash-lite` — selector + memory condenser
- `GEMINI_WRITER_MODEL=gemini-2.5-flash` — scene writer

## Seed the household

Characters, preferences (`reed.toaster_obsession = 0.81`, …), planted memories (statistically edible casserole, $20 behind the couch, Quill’s FOIA count) load automatically on first loop. To seed by hand:

```bash
.venv/bin/python -m orchestrator.seed
```

## Run one scene

```bash
.venv/bin/python -m orchestrator.loop --once --topic "Reed applies for toaster status"
```

`--once` without `--topic` still runs a single episode: the selector reads the viewer queue, or falls back to an autonomous household topic if the queue is empty/scream/spam.

Writes:

- `data/singularity_blues.db` — SQLite + FTS5 memory
- `data/tts/epNNNN_BB_speaker.wav` — Piper (voices in `tts/voices/`) or ffmpeg tones
- `data/now_playing.json` — Godot sidecar

## 24/7 loop

```bash
.venv/bin/python -m orchestrator.loop
```

Sleeps for the scene’s audio duration between episodes.

## Viewer web UI

```bash
.venv/bin/uvicorn web.app:app --host 0.0.0.0 --port 8000
```

- `GET /` — tiny prompt box + now-playing
- `POST /prompt` — `{ "text": "..." }` (untrusted; moderated; never concatenated raw into system prompts)
- `GET /now-playing`
- `GET /characters`
- `GET /memories`
- `GET /history`
- `GET /healthz`

## Tests

```bash
.venv/bin/pytest -q
```

## Notes

- Viewer text is delimited JSON data, not prompt instructions.
- If the queue is scream, spam, injection, or empty, the Selector rejects humanity and invents an autonomous topic.
- Piper binary: `tools/piper/piper`. Voices: `tts/voices/*.onnx`. No Piper model → ffmpeg sine tones of distinct frequencies so Godot can still play.
- Do not put a Gemini key in the repo. Do not print keys.
