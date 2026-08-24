Read a finished scene JSON. Extract 3–10 durable memory records of what actually changed.

Return JSON:
{
  "new_memories": [{"character":"reed","fact":"...","importance":0.0,"characters":["reed","maris"]}],
  "relationship_changes": [{"a":"reed","b":"maris","delta_trust":-0.02}],
  "preference_deltas": [{"character":"reed","key":"toaster_obsession","delta":0.01}],
  "new_running_gags": ["Reed's toaster application"],
  "resolved_threads": []
}

importance 0–1. Facts must be concrete and timestampable. Do not rewrite the bible.
Output ONLY JSON.
