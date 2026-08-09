"""Fixup: replace the 3 hardcoded-key creation blocks (two-phase verify+apply).

Phase 1: count all targets. Phase 2: apply only if all counts exact.
"""
import sys
from pathlib import Path

AR = Path("/home/yaser/raphael-2.0-rbsv2r/src/arena/ablation_runner.py")
text = AR.read_text(encoding="utf-8")

BLOCK_16 = '''                model_id="deepseek-ai/deepseek-v4-flash",
                provider="nvidia",
                api_base="https://integrate.api.nvidia.com/v1",
                api_key="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",'''
BLOCK_20 = '''                    model_id="deepseek-ai/deepseek-v4-flash",
                    provider="nvidia",
                    api_base="https://integrate.api.nvidia.com/v1",
                    api_key="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",'''
NEW_BLOCK_16 = '''                model_id="deepseek-ai/deepseek-v4-flash-0731",
                provider="nvidia",
                api_base="https://integrate.api.nvidia.com/v1",
                api_key=_resolve_nvidia_api_key(),'''
NEW_BLOCK_20 = '''                    model_id="deepseek-ai/deepseek-v4-flash-0731",
                    provider="nvidia",
                    api_base="https://integrate.api.nvidia.com/v1",
                    api_key=_resolve_nvidia_api_key(),'''

c16 = text.count(BLOCK_16)
c20 = text.count(BLOCK_20)
print(f"phase1: block16={c16} (expect 1), block20={c20} (expect 2)")
if c16 != 1 or c20 != 2:
    print("ABORT: counts not as expected; no writes.")
    sys.exit(1)
if "deepseek-ai/deepseek-v4-flash-0731" in text and "_resolve_nvidia_api_key()" in text:
    print("ABORT: appears already applied; no writes.")
    sys.exit(1)

text = text.replace(BLOCK_16, NEW_BLOCK_16)
text = text.replace(BLOCK_20, NEW_BLOCK_20)
AR.write_text(text, encoding="utf-8")
print("phase2: all 3 blocks replaced.")

# verify
text = AR.read_text(encoding="utf-8")
assert "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" not in text
assert text.count("deepseek-ai/deepseek-v4-flash-0731") == 3
assert text.count("_resolve_nvidia_api_key()") == 3
print("verify: hardcoded key gone; 3x -0731; 3x resolver. OK")
