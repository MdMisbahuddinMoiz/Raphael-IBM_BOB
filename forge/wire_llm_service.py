"""SENTINEL Option A: wire LLMService into _run_llm_only().

Mirrors the verified _run_raphael integration (lines 843-853 / 960-978 /
1105-1131) per SENTINEL Rule 44 constraint: copy the proven path, do not
invent new logic.

Three insertions:
  A. Create self._llm_service (LLMService + PROMPTED_AGENT_SYSTEM_PROMPT)
     right after `self._llm = TracedLLM(...)` in _run_llm_only.
  B. Semantic inference + model_inference evidence creation at the top of
     each iteration (after `iteration += 1`), mirroring 2a-LLM placement.
  C. Telemetry: provider_failures from LLMService into metrics at end of
     _run_llm_only (RunMetrics.provider_failures field exists, unused).
"""
import sys

PATH = "src/arena/ablation_runner.py"

with open(PATH, "r", encoding="utf-8", newline="") as f:
    src = f.read()

orig = src
report = []

# ── Insertion A: LLMService creation ─────────────────────────────
anchor_a = "        self._llm = TracedLLM(self.tracer, self.config)\n        \n        # Create ArenaRunner with fresh state (same interface as Raphael)"
assert anchor_a in src, "anchor A not found"
insert_a = """        self._llm = TracedLLM(self.tracer, self.config)
        
        # LLMService for semantic inference (L-028 Option A — mirrors _run_raphael).
        # PROMPTED_AGENT gets the PROMPTED_AGENT_SYSTEM_PROMPT envelope.
        if self.config.llm_enabled:
            if self._llm_config_override is not None:
                llm_config = self._llm_config_override
            else:
                llm_config = LLMProviderConfig(
                    model_id="deepseek-ai/deepseek-v4-flash",
                    provider="nvidia",
                    api_base="https://integrate.api.nvidia.com/v1",
                    api_key="nvapi-REDACTED",
                    timeout_seconds=15,
                    temperature=0.0,
                    max_tokens=512,
                )
            self._llm_service = LLMService(
                config=llm_config,
                tracer=self.tracer,
                system_prompt=PROMPTED_AGENT_SYSTEM_PROMPT if self.config.config_id == "PROMPTED_AGENT" else None,
            )
        else:
            self._llm_service = None
        
        # Create ArenaRunner with fresh state (same interface as Raphael)"""
src = src.replace(anchor_a, insert_a, 1)
report.append("[A] LLMService creation inserted (mirrors _run_raphael 843-853)")

# ── Insertion B: semantic inference at top of each iteration ────
anchor_b = """        while iteration < max_iterations:
            iteration += 1
            
            # LLM proposes action based on current evidence"""
assert anchor_b in src, "anchor B not found"
insert_b = """        while iteration < max_iterations:
            iteration += 1
            
            # Semantic inference on current evidence (L-028 Option A —
            # mirrors _run_raphael 2a-LLM block). Produces model_inference
            # evidence that the L-028 parsers consume.
            if self.config.llm_enabled and self._llm_service:
                _llm_ev = runner.evidence_graph.get_all_evidence()
                if len(_llm_ev) >= 3:
                    _diverse_items = select_diverse_evidence(_llm_ev)
                    if _diverse_items:
                        _llm_evidence_ids = tuple(
                            eid for item in _diverse_items for eid in item.get('evidence_ids', [])
                        )
                        if _llm_evidence_ids:
                            _llm_text = build_evidence_context(_diverse_items)
                            _llm_result = self._llm_service.run_inference(
                                observation_text=_llm_text,
                                source_evidence_ids=_llm_evidence_ids,
                                run_id=self.run_id,
                            )
                            if isinstance(_llm_result, SemanticInferenceSuccess):
                                si_evidence = Evidence.create(
                                    raw_content=json.dumps({
                                        "claim": _llm_result.claim,
                                        "category": _llm_result.category.value,
                                        "confidence": _llm_result.confidence,
                                        "structured_conclusion": getattr(_llm_result, 'structured_conclusion', {}) or {}
                                    }),
                                    trust_level=TrustLevel.MODEL_INFERENCE,
                                    source_detail=f"LLM semantic inference (category: {_llm_result.category.value})",
                                    target=_llm_result.category.value,
                                    evidence_type="model_inference",
                                    description=f"LLM semantic inference: {_llm_result.claim[:100]}",
                                    structured_content={
                                        "claim": _llm_result.claim,
                                        "category": _llm_result.category.value,
                                        "confidence": _llm_result.confidence,
                                        "structured_conclusion": getattr(_llm_result, 'structured_conclusion', {}) or {}
                                    },
                                    collected_by="llm_service",
                                )
                                runner.evidence_graph.add_evidence(si_evidence)
                                self._pending_si_evidence_ids.append(si_evidence.evidence_id)
            
            # LLM proposes action based on current evidence"""
src = src.replace(anchor_b, insert_b, 1)
report.append("[B] semantic inference + evidence creation inserted (mirrors 960-978 / 1105-1131)")

# ── Insertion C: telemetry at end of _run_llm_only ──────────────
anchor_c = """        if iteration >= max_iterations:
            decision_outcome = "STOP_OBJECTIVE_REACHED"
        self.metrics.decision_outcome = decision_outcome
    
    def _run_scripted(self):"""
assert anchor_c in src, "anchor C not found"
insert_c = """        if iteration >= max_iterations:
            decision_outcome = "STOP_OBJECTIVE_REACHED"
        self.metrics.decision_outcome = decision_outcome
        
        # LLMService telemetry (L-028 Option A — provider status for PROMPTED_AGENT)
        if getattr(self, '_llm_service', None):
            self.metrics.provider_failures = self._llm_service.provider_failures
            self.metrics.llm_calls += self._llm_service.call_count
    
    def _run_scripted(self):"""
src = src.replace(anchor_c, insert_c, 1)
report.append("[C] LLMService telemetry wired (provider_failures, llm_calls)")

changed = src != orig
report.append(f"changed: {changed} (size {len(orig)} -> {len(src)})")

with open(PATH, "w", encoding="utf-8", newline="\n") as f:
    f.write(src)

print("\n".join(report))

# Compile check
import py_compile
py_compile.compile(PATH, doraise=True)
print("COMPILE OK")
