# Graphics brief (for Sol)

First running version. Procedural CSG stand-ins. Make the graphics and canned animations actually look like a sitcom without changing the show's architecture.

## Do not change

- Do **not** generate video (no Runway, no frame diffusion). Godot **performs** a scene JSON + WAV.
- Original IP. Four **blue** people. Not Smurfs. Not hue-shifted Simpsons.
- Cast: **Reed** (dad), **Maris** (mom), **Jinx** (older kid), **Quill** (younger kid). Quill is not named Sol.
- Contract: orchestrator writes `data/now_playing.json`; Godot polls it. Schema: `prompts/scene.schema.json`.
- 1280×720, 30 fps, **GL Compatibility** renderer (the host machine is not a GPU box).
- Lip-flap from WAV amplitude (`WavLoader.gd`). Keep that, just make the mouth read better.
- Writer / memory / TTS / FastAPI are out of scope unless a renderer contract change is required.

## Current look (placeholder)

- Characters are CSG capsules / spheres / cylinders with four distinct blues and silhouettes (`renderer/scripts/Character.gd`).
- Living room is hardcoded CSG furniture (`renderer/scripts/LivingRoom.gd`).
- Camera is a sitcom three-shot with a few canned moves (`renderer/scripts/CameraDirector.gd`).
- Body acting is canned: idle, talking, gesture_small, arms_crossed, shrug, pointing, sitting, walking, shocked, crying, screaming, enter, leave.
- Names float as Label3D.

## What better looks like

Replace CSG people with actual character meshes (Blender → Godot). Keep them **all blue**, household, distinct at a glance (Reed slumped/wide, Maris composed, Jinx sharp, Quill small/upright).

Upgrade canned anims so talking / shrug / scream / walk read from the cheap seats. Idle should breathe. Sit/stand on the couch should not clip.

Living room: a real set. Couch, coffee table, TV, kitchen pass-through, a toaster somewhere Reed can yearn at. Warm sitcom lighting, not a gray void.

Camera: still sitcom-hardcoded, not cinematic chaos. Coverage that can hold a four-hander.

## Files to touch

```
renderer/project.godot
renderer/scenes/Main.tscn
renderer/scripts/Character.gd
renderer/scripts/LivingRoom.gd
renderer/scripts/CameraDirector.gd
renderer/scripts/ScenePlayer.gd
renderer/scripts/Main.gd
renderer/scripts/WavLoader.gd
renderer/export_watch.sh
renderer/assets/seed_scene.json
```

Add `renderer/assets/` meshes, materials, animations as needed. Keep the `now_playing.json` poll loop in `Main.gd` / `ScenePlayer.gd`.

## How to preview

```bash
# after tools/README.md downloads
tools/godot --path renderer --quit-after 1   # import
tools/godot --path renderer                  # window
# or
renderer/export_watch.sh
```

A mock scene lives at `renderer/assets/seed_scene.json` if the orchestrator has not written `data/now_playing.json` yet.
