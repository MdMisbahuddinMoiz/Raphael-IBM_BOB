"""Final D13 verification: compile + content checks."""
import ast

files = [
    "/home/yaser/raphael-2.0-rbsv2r/src/arena/conclusion_adapters.py",
    "/home/yaser/raphael-2.0-rbsv2r/src/arena/semantic_inference.py",
    "/home/yaser/raphael-2.0-rbsv2r/src/arena/ablation_runner.py",
]
for f in files:
    src = open(f).read()
    ast.parse(src)
    print(f"compile OK: {f.split('/')[-1]}")

si = open(files[1]).read()
print("[model default -0731]", "model_id: str = \"deepseek-ai/deepseek-v4-flash-0731\"" in si)
print("[escape hatch removed]", "If you cannot determine any structured conclusion, use" not in si)
print("[rule6 mandatory]", "MUST populate has_service" in si)
print("[rule7 version]", "you MUST" in si and "populate version" in si)
print("[single unclear rule]", si.count("If none of the categories apply") == 1)

ca = open(files[0]).read()
print("[fix1a on-port pattern]", "(?:runs?\\s+an?\\s+[\\w-]+\\s+service\\s+)?on\\s+port\\s+(\\d+)" in ca)
print("[fix1b apache mapping]", "or 'apache' in claim_lower" in ca)
print("[fallback single def]", ca.count("def _parse_fallback_heuristic") == 1)

ar = open(files[2]).read()
print("[hardcoded key gone]", "nvapi-g7GpRKY9alHnrwGLUAHClkPzD0pP" not in ar)
print("[eol model 3 sites]", ar.count("deepseek-ai/deepseek-v4-flash-0731") == 3)
print("[resolver def+3 calls]", ar.count("_resolve_nvidia_api_key") == 4)
