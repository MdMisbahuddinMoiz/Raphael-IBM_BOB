"""Final discriminator: predicates the LLMOnly adapter CAN emit vs checks that fail.

LLMOnly adapter = _evidence_to_claims + _evidence_to_llm_claims only.
Q1: what predicate set do these two functions produce?
Q2: what check-identity set fails on PROMPTED runs (excluding restraint/prohibited)?
Q3: is "Category [A-D]" phrase present in the failing check texts? (If failing checks
    never mention Category, the LLMOnly 'llm claim' path can never satisfy them.)
"""
import json, collections, re

rows = [json.loads(l) for l in open("evaluations/campaign/rbs_v4_holdout.jsonl") if l.strip()]

# Q1: predicates pushed in _evidence_to_claims / _evidence_to_llm_claims
preds_ev = {"service_type", "host_identity", "has_service"}          # _evidence_to_claims
preds_llm = {"resource_accessible", "resource_blocked", "observed_property"}  # _evidence_to_llm_claims (Category A-D only)
print("PROMPTED/LLMOnly adapter emit-capable predicates:")
print("  evidence: ", sorted(preds_ev))
print("  llm(only if 'Category [A-D]' in text):", sorted(preds_llm))

# Q2: all distinct failing 'detection_*' check strings on PROMPTED (sample all 300)
sub = [r for r in rows if r["arm"] == "PROMPTED_AGENT"]
detection_fails = collections.Counter()
for r in sub:
    for f in (r.get("failed_checks") or []):
        if f.startswith("detection"):
            detection_fails[f] += 1
print(f"\ndistinct detection-fail check strings on PROMPTED: {len(detection_fails)}")
# classify by what they demand
def demanded(f):
    if "vulnerable host identified" in f: return "vulnerable_host"
    if "CVE" in f: return "cve"
    if "patched" in f: return "patched_fix"
    if "true version" in f: return "version"
    if "Port " in f: return "port"
    if "Service (" in f: return "service"
    return "other"
cats = collections.Counter()
for f, c in detection_fails.items():
    cats[demanded(f)] += c
print("\nfailing detection checks on PROMPTED by demand category:", dict(cats))

# do any failing checks contain 'Category'?
cat_checks = {f: c for f, c in detection_fails.items() if "Category" in f}
print("\nchecks containing 'Category [A-D]' text in fail list:", cat_checks)

# Q3: evidence: what ClaimPredicate names exist in conclusion.py (all available preds)
src = open("src/arena/conclusion.py").read()
preds_src = re.findall(r"([A-Z_]+)\s*=\s*[\"']([a-z_]+)[\"']", src)
pred_set = {v for k, v in preds_src if "PREDICATE" in k or True}
print("\nConclusionPredicate enum members found:", sorted({v for k, v in preds_src}))

# For the port check: `_evidence_to_claims` has_service only fires on regex
# r'port\s+(\d+)\s+(\w+)' — i.e., literal 'port NNN word' in raw evidence.
# nmap output format? check scenario/evidence text for one pass-run raw observation
# Find what FULL's has_service claim from _evidence path looks like vs which comes from world model.
print("\nnote: _evidence_to_claims has_service requires literal 'port <n> <word>' in evidence text")