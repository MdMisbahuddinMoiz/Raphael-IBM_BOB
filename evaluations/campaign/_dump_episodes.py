import json, os, sys

BASE = "/home/yaser/raphael-2.0-rbsv2r"
RAWDIR = BASE + "/arena/results/raw"
run = sys.argv[1]
d = os.path.join(RAWDIR, run)
p = os.path.join(d, "episodes.jsonl")
print("EPISODES:", p, "exists:", os.path.exists(p))
if not os.path.exists(p):
    sys.exit(0)
with open(p, "r", errors="replace") as fh:
    lines = [l for l in fh if l.strip()]
print("episode_count:", len(lines))
for i, line in enumerate(lines):
    try:
        ev = json.loads(line)
    except Exception as e:
        print(i, "PARSE ERR", e, line[:200])
        continue
    print("\n" + "=" * 25, "episode", i, "=" * 25)
    def short(v, limit=3000):
        s = json.dumps(v, indent=1) if not isinstance(v, str) else v
        return s[:limit] + ("...[trunc]" if len(s) > limit else "")
    for k in ["episode_index", "step", "phase", "event_type", "kind", "observation", "action",
              "model_output", "response", "reasoning", "text", "prompt", "llm_response"]:
        if k in ev:
            print(f"  [{k}]:", short(ev[k]))
    # fallback show structure
    print("  keys:", sorted(ev.keys()))