"""Step 2 (SENTINEL-authorized): swap 3 LLMProviderConfig sites to 550B + transport params."""
from pathlib import Path

p = Path("src/arena/ablation_runner.py")
t = p.read_text()

OLD = 'model_id="deepseek-ai/deepseek-v4-flash-0731",'
NEW = 'model_id="nvidia/nemotron-3-ultra-550b-a55b",'
n_old = t.count(OLD)
print("model_id deepseek-0731 occurrences:", n_old)
assert n_old == 3, f"expected 3 sites, got {n_old}"
t = t.replace(OLD, NEW)

# transport params per SENTINEL freeze: timeout 180s, max_tokens 16384
OLD_T = "                    timeout_seconds=15,\n                    temperature=0.0,\n                    max_tokens=512,"
NEW_T = "                    timeout_seconds=180,\n                    temperature=0.0,\n                    max_tokens=16384,"
n_t = t.count(OLD_T)
print("timeout/max_tokens pattern occurrences:", n_t)
assert n_t == 3, f"expected 3, got {n_t}"
t = t.replace(OLD_T, NEW_T)

p.write_text(t)
print("OK: 3 sites -> 550B, timeout 180, max_tokens 16384")
print("remaining 'deepseek' refs in ablation_runner.py:", t.count("deepseek"))
