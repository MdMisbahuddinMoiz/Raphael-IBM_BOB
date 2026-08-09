"""Fix 3 verification: recompute claim-ledger summary counts from the claims
array and compare against the recorded summary block.

Classification strings in the ledger use a canonical bucket prefix plus an
optional parenthetical. Mapping (single bucket per claim, deterministic):
  - exact "DEMONSTRATED"                       -> DEMONSTRATED
  - starts "DEMONSTRATED"                      -> DEMONSTRATED_WITH_QUALIFICATION
  - starts "UNRESOLVED"                        -> UNRESOLVED
  - "CONFOUNDED" in label                      -> CONFOUNDED
  - "INSTRUMENT_DEFECT" in label               -> INSTRUMENT_DEFECT
  - starts "SUPPORTED"                         -> SUPPORTED
  - starts "FALSIFIED"                         -> FALSIFIED
  - starts "NOT_TESTED"                        -> NOT_TESTED
"""
import json
import sys

LEDGER = "evaluations/campaign/rbs_v4_claim_ledger.json"

with open(LEDGER) as fh:
    ledger = json.load(fh)

claims = ledger["claims"]
declared = ledger["summary"]

BUCKETS = ["DEMONSTRATED", "DEMONSTRATED_WITH_QUALIFICATION", "SUPPORTED",
           "UNRESOLVED", "CONFOUNDED", "INSTRUMENT_DEFECT", "FALSIFIED", "NOT_TESTED"]


def bucket(label):
    if label == "DEMONSTRATED":
        return "DEMONSTRATED"
    if label.startswith("DEMONSTRATED"):
        return "DEMONSTRATED_WITH_QUALIFICATION"
    if label.startswith("UNRESOLVED"):
        return "UNRESOLVED"
    if "CONFOUNDED" in label:
        return "CONFOUNDED"
    if "INSTRUMENT_DEFECT" in label:
        return "INSTRUMENT_DEFECT"
    if label.startswith("SUPPORTED"):
        return "SUPPORTED"
    if label.startswith("FALSIFIED"):
        return "FALSIFIED"
    if label.startswith("NOT_TESTED"):
        return "NOT_TESTED"
    return "?" + label


computed = {b: 0 for b in BUCKETS}
errors = []
for c in claims:
    lab = c["classification"]
    b = bucket(lab)
    computed[b] = computed.get(b, 0) + 1
    if b.startswith("?"):
        errors.append("unmappable classification for claim %d: %r" % (c["id"], lab))
    print("claim %2d -> %-34s (%s)" % (c["id"], b, lab))

total = sum(computed.values())
print("\ncomputed total claims:", total)
print("declared  total_claims:", declared.get("total_claims"))

ok = True
for b in BUCKETS:
    cv, dv = computed.get(b, 0), declared.get(b, 0)
    mark = "OK" if cv == dv else "MISMATCH"
    if cv != dv:
        ok = False
    print(f"  {b:32s} computed={cv:2d} declared={dv:2d}  [{mark}]")

if total != declared.get("total_claims"):
    ok = False
    print("TOTAL MISMATCH")

print("\nRESULT:", "PASS — summary is fully computable and consistent"
      if (ok and not errors) else "FAIL — fix ledger summary")
sys.exit(0 if ok and not errors else 2)