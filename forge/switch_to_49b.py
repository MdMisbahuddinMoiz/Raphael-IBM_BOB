"""Update model config to 49B (gate-passing model) for holdout launch."""
from pathlib import Path

# Ablation runner - 3 sites
p = Path("src/arena/ablation_runner.py")
t = p.read_text()
OLD_MODEL = 'model_id="nvidia/nemotron-3-ultra-550b-a55b",'
NEW_MODEL = 'model_id="nvidia/llama-3.3-nemotron-super-49b-v1",'
n = t.count(OLD_MODEL)
print(f"ablation_runner 550B sites: {n}")
assert n == 3
t = t.replace(OLD_MODEL, NEW_MODEL)
p.write_text(t)

# Semantic inference default
p = Path("src/arena/semantic_inference.py")
t = p.read_text()
OLD_DEF = 'model_id: str = "nvidia/nemotron-3-ultra-550b-a55b"'
NEW_DEF = 'model_id: str = "nvidia/llama-3.3-nemotron-super-49b-v1"'
n = t.count(OLD_DEF)
print(f"semantic_inference default 550B: {n}")
assert n == 1
t = t.replace(OLD_DEF, NEW_DEF)
p.write_text(t)

# Verify
for pth, pat in [
    ("src/arena/ablation_runner.py", 'model_id="nvidia/llama-3.3-nemotron-super-49b-v1"'),
    ("src/arena/semantic_inference.py", 'model_id: str = "nvidia/llama-3.3-nemotron-super-49b-v1"'),
]:
    t = Path(pth).read_text()
    n = t.count(pat)
    print(f"{pth}: {n} occurrences of 49B model_id")

print("OK: instrument updated to 49B (gate-passing model)")