import json
d = json.load(open("evaluations/campaign/TERMINAL_ANALYSIS_RESULTS.json"))
print("NOTES:", d.get("notes", []))
print("KNOWN_GAP:", d.get("known_gap", {}))