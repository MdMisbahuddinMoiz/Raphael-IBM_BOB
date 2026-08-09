# Multi-API-Key Rotation — DESIGN ONLY (NOT ACTIVATED)

**Status: DESIGN ARTIFACT — NOT IMPLEMENTED, NOT ACTIVATED**
**RBS-v4 repair item 11** · SENTINEL-mandated: *design only, NOT activated*.
No code in `src/` implements this document. This file specifies a *candidate*
design so that activation is a deliberate, reviewed, separately-authorized
change — never an emergent side-effect of a campaign run.

---

## 1. Problem Statement

The frozen D-6C treatment uses a single NVIDIA API key
(`LLMProviderConfig.api_key`, `api_base=https://integrate.api.nvidia.com/v1`,
see `src/arena/ablation_runner.py` and `scripts/d6c_holdout_runner.py`).

Risks of a single key:

1. **Rate limits / HTTP 429** — a shared key can hit provider rate limits,
   turning into `provider_timeout`/`provider_api_error`, which the D-6C policy
   records as `PROVIDER_CONFOUNDED` rows. Rotation does NOT fix that policy —
   it reduces the *frequency* of provider-side confounds.
2. **Quota exhaustion mid-campaign** — a hard quota stop would abort an
   append-only resumable campaign.
3. **Key-in-code hygiene** — the frozen key currently lives in
   `src/arena/ablation_runner.py:640` and `scripts/d6c_holdout_runner.py`
   (docstring); rotation to an env-var source is a hygiene improvement.

The D-6C / RBS-v4 **reproducibility contract** (`EvaluationProtocol.md`) says
every row must be attributable to a single provider+model+key identity so
that `provider_confounded` classification is meaningful. Rotation must not
break that attribution.

## 2. Constraints (frozen, non-negotiable)

- **Frozen treatment identity**: `provider=nvidia`, `model=deepseek-ai/deepseek-v4-flash`.
  Rotation may rotate the **key only** — never the provider/model.
- **No silent retries**: the D-6C provider-failure policy explicitly forbids
  selective retry/skipping. A rotated key is used for the *next* inference,
  never to retry a failed one, unless a separate SENTINEL mandate changes
  that policy.
- **Attribution**: every `DiagnosticRawRecord` / metrics row must record which
  key (or key index) produced each inference, so post-hoc analysis can detect
  key-vs-result correlations.
- **Determinism**: key selection must be a deterministic function of
  (attempt counter, key list) — e.g., round-robin — so replays reproduce the
  same key assignment given the same attempt sequence. No randomness.

## 3. Design

### 3.1 Configuration surface

Extend `LLMProviderConfig` (in `src/arena/llm_service.py`) with OPTIONAL
fields, defaulting to current behavior (single key, no rotation):

```python
@dataclass
class LLMProviderConfig:
    ...
    # NEW — optional, default OFF
    api_keys: list[str] = field(default_factory=list)   # ordered rotation list
    key_rotation: str = "off"                            # "off" | "round_robin"
```

- If `key_rotation == "off"` (default), behavior is byte-for-byte identical to
  today: `api_key` is used; `api_keys` is ignored.
- If `key_rotation == "round_robin"` and `api_keys` is non-empty, the active
  key for attempt *n* is `api_keys[n % len(api_keys)]`.

### 3.2 Selection point

`call_llm_provider(messages, config)` in `src/arena/llm_service.py:158` is the
single choke point that builds `Authorization: Bearer <key>`. The rotation
resolves the key **inside** `call_llm_provider` so no other call site changes.

Design decision — **resolve in `LLMService.run_inference` instead** (preferred):
`run_inference` already owns per-attempt bookkeeping (`call_count`,
`provider_failures`, `envelope_failures` from repair item 1). It should:

1. Compute `active_key = self._select_key()` before Stage 3.
2. Pass the selected key to `call_llm_provider` via a new optional
   `api_key_override: Optional[str] = None` parameter (default None = use
   `config.api_key`, preserving current behavior).
3. Record `key_index` / `key_hash` in the `DiagnosticRawRecord` and in the
   returned `SemanticInferenceSuccess/Failure` metadata.

### 3.3 Counter semantics

- `call_count` increments per attempt regardless of key (unchanged).
- `provider_failures` increments on `provider_api_error`/`provider_timeout`
  (unchanged — rotation does not reclassify failures).
- NEW counter: `key_rotations` (or `keys_used: set[int]`) on `LLMService`,
  purely informational for the Dev-distribution budget/attribution report.

### 3.4 Attribution fields

Add to the metrics/JSONL row (schema addition, default empty):

```json
"llm": {
  "provider": "nvidia",
  "model_id": "deepseek-ai/deepseek-v4-flash",
  "key_index": 0,
  "key_hash": "sha256:ab12..."
}
```

`key_hash` is a truncated sha256 of the key — never the raw key — so audit
trails never store secrets.

### 3.5 Determinism & replay

`_select_key()` = `attempt_index % len(api_keys)`. Because attempt order is
deterministic (append-only resumable campaign), replays assign identical keys
to identical attempts. No RNG.

## 4. What is explicitly NOT in scope (do not implement)

- ❌ No retry-on-failure logic. D-6C forbids selective retry.
- ❌ No provider/model rotation (frozen identity).
- ❌ No load balancing / adaptive selection (quota-aware steering).
- ❌ No key storage in git. If activated, keys MUST come from environment
  variables (`LLM_API_KEYS`, comma-separated), never committed.
- ❌ No change to the frozen manifest (`rbs_v4_benchmark_frozen-F.json`) or to
  the 3,240-row holdout dataset.
- ❌ No new CLI flags in this design.

## 5. Activation procedure (requires separate authorization)

Activation is a **separate, SENTINEL-authorized change**, not part of this
design artifact. If ever activated:

1. Add `api_keys` + `key_rotation` fields to `LLMProviderConfig`.
2. Implement `_select_key()` + `api_key_override` plumbing in `llm_service.py`.
3. Add `key_index`/`key_hash` attribution to `DiagnosticRawRecord` and the
   JSONL row schema in `scripts/run_rbs_v4_*.py`.
4. Read keys from env, never commit them.
5. Run the full regression gate (currently 191 tests) + a live 2-key smoke
   that verifies key identity appears in telemetry and that
   `original == decrypted`-style invariants hold (no key leaks into evidence).
6. Re-verify the frozen manifest hash — activation must NOT alter it.

## 6. Verification (design-level, runnable today)

Even without implementation, the following are already true and testable:

- `grep -n "api_key" src/arena/llm_service.py` → exactly 2 references
  (the `if config.api_key:` guard at :199 and the header assignment at :200),
  both in `call_llm_provider` — proving a single choke point for rotation.
- `grep -n "api_key" src/arena/ablation_runner.py` → frozen key is a literal
  (lines :645, :856); a future activation would move it to env.
- Token telemetry (repair item 1) already records `provider_failures` so the
  Dev-distribution of provider failures is measurable per key once activated.

## 7. Relationship to other repairs

- Item 1 (token telemetry): rotation builds on `provider_failures` and
  `call_count` counters already present on `LLMService`.
- Item 10 (budget contract): the key-rotation design must respect the frozen
  budget ceilings (ITERATION_BUDGET=5, ACTION_BUDGET=20) — rotation never
  changes the number of attempts, only which key serves an attempt.

---

*Design artifact generated 2026-08-06. NOT ACTIVATED. No source changes were
made for this item; this document is the complete deliverable for repair
item 11.*
