Read a finished scene JSON. Extract 3–10 durable memory records of what actually happened ON SCREEN. No hypotheticals.

Return JSON:
{
  "new_memories": [{"character":"reed","fact":"...","importance":0.0,"characters":["reed","maris"]}],
  "relationship_changes": [{"a":"reed","b":"maris","delta_trust":-0.02}],
  "preference_deltas": [{"character":"reed","key":"toaster_obsession","delta":0.01}],
  "new_running_gags": ["Reed's toaster application"],
  "resolved_threads": [],
  "character_arcs": [{"character":"jinx","note":"now claims the Selector reads the fridge logs"}]
}

Rules:
- Facts must be concrete and past-tense. Include who did/said what. Do not put calendar dates, weekdays, or clock times in the fact text. created_at is the stamp; we convert it to Denver at write time.
- character_arcs: one short note per person who actually shifted this episode (optional, max 4). This becomes their current continuity.
- Do not rewrite the bible. Do not log "they claimed to remember X" unless X was in the scene.
- importance 0–1.
Output ONLY JSON.
