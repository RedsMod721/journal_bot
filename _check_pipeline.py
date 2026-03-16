import json, sqlite3, sys

con = sqlite3.connect("data/db/rpg_life_tracker.db")
con.row_factory = sqlite3.Row

entry_id = sys.argv[1] if len(sys.argv) > 1 else "cac6ce0c-4afd-45bb-9ac9-ecd13e396d8f"
row = con.execute(
    "SELECT result_json FROM processing_jobs WHERE entry_id=? ORDER BY updated_at DESC LIMIT 1",
    (entry_id,)
).fetchone()
if not row:
    print("no job found for", entry_id)
    sys.exit(1)

data = json.loads(row["result_json"])
steps = data.get("step_trace", [])

CRITICAL = ["step_04_ollama_health", "step_06_rag_search", "step_12_insight_plan", "step_16l_persist_insight"]
for s in steps:
    if s["step_name"] not in CRITICAL:
        continue
    out = s.get("output", {})
    print()
    print("[" + s["step_name"] + "]")
    print("  status=" + str(s["status"]) + "  error=" + str(s.get("error_code")))
    if s["step_name"] == "step_06_rag_search":
        print("  hit_count=" + str(out.get("hit_count")) + "  fallback=" + str(out.get("fallback")))
    if "insight" in s["step_name"]:
        print("  generated=" + str(out.get("generated")))
        print("  from_ollama=" + str(out.get("from_ollama")))
        print("  suppression=" + str(out.get("suppression_reason")))
        print("  insight_text=" + str(out.get("insight_text", ""))[:160])
