"""Fix telemetry clobber for L-028 Option A wiring.

run() finalize (line ~735) does `self.metrics.llm_calls = self._llm.call_count`
which OVERWRITES the LLMService count added in _run_llm_only. Fix:
  1. In insertion A: set self._llm_service_llm_only = True (scoped flag).
  2. In insertion C: drop the llm_calls += (keep provider_failures).
  3. In run() finalize: add scoped merge for llm_only path only —
     FULL_RAPHAEL telemetry semantics untouched.
"""
import sys

PATH = "src/arena/ablation_runner.py"

with open(PATH, "r", encoding="utf-8", newline="") as f:
    src = f.read()

report = []

# 1. Scoped flag after LLMService creation in _run_llm_only
anchor_flag = """            self._llm_service = LLMService(
                config=llm_config,
                tracer=self.tracer,
                system_prompt=PROMPTED_AGENT_SYSTEM_PROMPT if self.config.config_id == "PROMPTED_AGENT" else None,
            )
        else:
            self._llm_service = None"""
assert anchor_flag in src, "flag anchor not found"
src = src.replace(anchor_flag, anchor_flag + "\n        self._llm_service_llm_only = bool(self._llm_service)", 1)
report.append("[1] scoped flag self._llm_service_llm_only added")

# 2. Fix insertion C: keep provider_failures only (llm_calls handled in finalize)
anchor_c = """        # LLMService telemetry (L-028 Option A — provider status for PROMPTED_AGENT)
        if getattr(self, '_llm_service', None):
            self.metrics.provider_failures = self._llm_service.provider_failures
            self.metrics.llm_calls += self._llm_service.call_count"""
assert anchor_c in src, "insertion C anchor not found"
src = src.replace(anchor_c, """        # LLMService telemetry (L-028 Option A — provider status for PROMPTED_AGENT)
        # NOTE: llm_calls merge happens in run() finalize (avoids clobber).
        if getattr(self, '_llm_service', None):
            self.metrics.provider_failures = self._llm_service.provider_failures""", 1)
report.append("[2] insertion C: dropped llm_calls += (moved to finalize)")

# 3. Finalize merge, scoped to llm_only path
anchor_fin = """        # Populate resource metrics from LLM tracker
        if self._llm:
            self.metrics.llm_calls = self._llm.call_count
            self.metrics.input_tokens = self._llm.input_tokens
            self.metrics.output_tokens = self._llm.output_tokens"""
assert anchor_fin in src, "finalize anchor not found"
src = src.replace(anchor_fin, anchor_fin + """

        # L-028 Option A: include LLMService semantic-inference calls in
        # telemetry for the LLM-only path (PROMPTED_AGENT / LLM_ONLY).
        # Scoped by flag: FULL_RAPHAEL telemetry semantics are untouched.
        if getattr(self, '_llm_service_llm_only', False) and getattr(self, '_llm_service', None):
            self.metrics.llm_calls += self._llm_service.call_count""", 1)
report.append("[3] finalize merge added (scoped to llm_only path)")

with open(PATH, "w", encoding="utf-8", newline="\n") as f:
    f.write(src)

print("\n".join(report))

import py_compile
py_compile.compile(PATH, doraise=True)
print("COMPILE OK")
