"""Step 2c: swap model_id lines to 550B (params already done)."""
from pathlib import Path

p = Path("src/arena/ablation_runner.py")
t = p.read_text()

OLD = 'model_id="deepseek-ai/deepseek-v4-flash-0731",'
NEW = 'model_id="nvidia/nemotron-3-ultra-550b-a55b",'
n = t.count(OLD)
print("deepseek model_id sites:", n)
assert n == 3
t = t.replace(OLD, NEW)
p.write_text(t)
print("OK: 3 model_id sites -> 550B")
print("remaining deepseek:", t.count("deepseek"))
