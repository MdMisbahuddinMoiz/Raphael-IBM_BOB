"""D1-B provenance: history of _semantic_inference_to_claims references + PROMPTED_AGENT config history."""
import subprocess

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=".")
    return r.stdout + r.stderr

# 1) commits touching _semantic_inference_to_claims
out = run(["git", "log", "--oneline", "-S", "_semantic_inference_to_claims", "src/arena/conclusion_adapters.py"])
print("=== commits that added/removed _semantic_inference_to_claims ===")
print(out)

# 2) full history of LLMOnlyConclusionAdapter class region: which commits touched the LLMOnly adapter
out2 = run(["git", "log", "--oneline", "--all", "--", "src/arena/conclusion_adapters.py"])
print("\n=== all commits touching conclusion_adapters.py ===")
print(out2)

# 3) PROMPTED_AGENT config history in ablation.py
out3 = run(["git", "log", "--oneline", "-S", "PROMPTED_AGENT", "src/arena/ablation.py"])
print("\n=== commits adding/changing PROMPTED_AGENT in ablation.py ===")
print(out3)