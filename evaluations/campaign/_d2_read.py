"""Read TERMINAL_ANALYSIS_RESULTS and compute sensitivity table for D2."""
import json

d = json.load(open("evaluations/campaign/TERMINAL_ANALYSIS_RESULTS.json"))
print(json.dumps(d, indent=1)[:5000])