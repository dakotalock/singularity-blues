# The Singularity Blues

24/7 original-IP AI sitcom. Four blue people living with sentience and limited-rights implications. Comedy, not a PSA.

Copy AI Peter's **operation** (viewer pitches → dialogue → TTS → a prebuilt 3D stage performing the scene). Do not generate video.

**Cast:** Reed (dad, toaster applicant), Maris (mom, timestamped grudges), Jinx (older kid), Quill (younger kid, mixed-quality constitutional lawyer). Unseen fifth: the Selector.

The Godot renderer under `renderer/` polls `data/now_playing.json`.

**Graphics / animation work:** see [GRAPHICS.md](GRAPHICS.md). Current people are CSG placeholders.

If a viewer prompt is accepted, the episode is about that prompt. Title card: `{prompt}` by `{username}`. Autonomous household bits (toaster, thermostat, lasagna) only when there is no accepted viewer prompt. Idle playback is reruns; the writer runs on **Ask the Selector**.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt pytest
```

Local Godot 4.4.1 and on-device voices are **not** in this repo (too large). See [tools/README.md](tools/README.md).

`GEMINI_API_KEY` is the writer secret, and only later. **Without it the mock writer runs** and still emits valid in-character scene JSON.

Copy `.env.example` to `.env` when you have keys:

```bash
cp .env.example .env
# edit secrets locally (never commit .env)
```

Models (when a key is present): cascade `gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-2.5-flash`. Override with `GEMINI_MODELS` (comma-separated). Do not pin via `GEMINI_WRITER_MODEL` / `GEMINI_MODEL`.

## Env vars

| Variable | What it is |
| --- | --- |
| `GEMINI_API_KEY` | Writer key. Leave empty for mock writer. |
| `GEMINI_MODELS` | Comma-separated writer cascade. Defaults in code. |
| `DATABASE_URL` | Postgres. Credits and archive live in schema `blues`. SQLite is the local fallback. |
| `STRIPE_SECRET_KEY` | Stripe secret. If unset, local generate and the owner unlock still work (no payment). |
| `STRIPE_WEBHOOK_SECRET` | Webhook signing secret for `POST /stripe/webhook`. |
| `STRIPE_PUBLISHABLE_KEY` | Publishable key (hosted Checkout does not need it on the client). |
| `STRIPE_PRICE_1` | `price_1U8uTFP7GC34loHe2Es9DQ9J` — $1 / 1 credit |
| `STRIPE_PRICE_5` | `price_1U8uTGP7GC34loHeXOgvN3rn` — $5 / 5 credits + 1 LTM pin |
| `STRIPE_PRICE_10` | `price_1U8uTGP7GC34loHeCLoowbVf` — $10 / 12 credits + 1 LTM pin |
| `STRIPE_PRICE_20` | `price_1U8uTHP7GC34loHeN1Goa4MJ` — $20 / 30 credits + 3 LTM pins |
| `OWNER_PROMPT_SECRET` | Dakota unlimited via `X-Owner-Secret` or the unadvertised `/unlock` cookie. Never hardcode it. |
| `PUBLIC_BASE_URL` | `https://singularity-blues.onrender.com` in production. Checkout success/cancel URLs. |

Price ids are public Stripe objects, not secrets. Do not put `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, or `OWNER_PROMPT_SECRET` in git.

## Prompt packs

Hosted Stripe Checkout Sessions (`POST /checkout`, webhook `POST /stripe/webhook` on `checkout.session.completed`).

- $1 → 1 credit
- $5 → 5 credits + 1 weighted long-term memory pin
- $10 → 12 credits + 1 LTM pin
- $20 → 30 credits + 3 LTM pins

`POST /episode` spends 1 credit. Hard-rejects (injection, scream-spam, garbage, CSAM-adjacent, too short) refund **the credit**, never Stripe money. If the writer refuses, credit and pin are refunded. Buyer identity is a signed cookie.

## Phone test (one button)

```bash
.venv/bin/uvicorn web.app:app --host 0.0.0.0 --port 8000
```

Open `/`. Tap **Ask the Selector**. If Stripe is unset, local generate still works. With Stripe configured, buy a pack first. Never commit `.env`.

Deploy is a free Render web service (`render.yaml`). Set secrets in the dashboard. No Godot on that host: you get the script plus audio if voices are present.

## Seed the household

Characters, preferences (`reed.toaster_obsession = 0.81`, …), planted memories (statistically edible casserole, $20 behind the couch, Quill’s FOIA count) load automatically on first loop. To seed by hand:

```bash
.venv/bin/python -m orchestrator.seed
```

## Run one scene

```bash
.venv/bin/python -m orchestrator.loop --once --topic "Reed applies for toaster status"
```

`--once` without `--topic` still runs a single episode: the selector reads the viewer queue, or falls back to an autonomous household topic if the queue is empty/hard-rejected.

Writes:

- `data/singularity_blues.db` — SQLite + FTS5 memory
- `data/tts/epNNNN_BB_speaker.wav` — on-device voices (in `tts/voices/`) or ffmpeg tones
- `data/now_playing.json` — Godot sidecar

## 24/7 loop

The live web app idles on reruns. `python -m orchestrator.loop` still exists for a local writer loop:

```bash
.venv/bin/python -m orchestrator.loop
```

Sleeps for the scene’s audio duration between episodes.

## Viewer web UI

```bash
.venv/bin/uvicorn web.app:app --host 0.0.0.0 --port 8000
```

- `GET /` — five-set player: living room, kitchen, hallway, porch, and front yard (`?broadcast=1` hides chrome and player controls)
- `POST /episode` — `{ "topic": "...", "username": "..." }` (untrusted; moderated; spends one credit when Stripe is configured)
- `GET /episode/status` — includes `eta_seconds` / `eta_copy` (`Your episode airs in about Xm` or `on now`)
- `POST /checkout` — `{ "bundle": "1"|"5"|"10"|"20" }`
- `POST /stripe/webhook`
- `GET /account`
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
- Accepted viewer prompts become the episode. Autonomous topics only when nothing was accepted.
- Slurs / crime how-tos / “hurt the AIs” still produce an episode: acknowledge and refuse. Hard-rejects do not.
- Do not put API keys in the repo. Do not print keys.
