#!/usr/bin/env python3
"""
THE STUDENT — deep-read pass over the 20 arXiv cs.CR papers captured in the
first session. Full-text extraction (pypdf, in-memory), then the Student's
own extraction primitives over the COMPLETE text (not the 2000-char snippet).

Outputs:
  evaluations/campaign/student_read_session_<ts>.jsonl   (per-paper findings)
  evaluations/campaign/student_read_findings_<ts>.json    (synthesized report)
  prints a readable per-paper findings table
"""
import asyncio
import json
import logging
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
_SRC = _REPO_ROOT + "/src"
for p in (_SRC, _REPO_ROOT):
    while p in sys.path:
        sys.path.remove(p)
sys.path.insert(0, _SRC)
sys.path.insert(0, _REPO_ROOT)

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

from orchestrator.student.scihub import SciHubResearcher


def extract_text_pypdf(self, pdf_data: bytes) -> str:
    import io
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_data))
        parts = []
        for page in reader.pages:
            try:
                t = page.extract_text() or ""
                if t:
                    parts.append(t)
            except Exception:
                continue
        return "\n".join(parts).strip()
    except Exception as e:
        logging.getLogger("student.scihub").warning("pypdf extraction failed: %s", e)
        return ""

SciHubResearcher.extract_text = extract_text_pypdf

CAMPAIGN_DIR = Path(_REPO_ROOT) / "evaluations" / "campaign"
CAMPAIGN_DIR.mkdir(parents=True, exist_ok=True)
TS = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
TEL_LOG = CAMPAIGN_DIR / f"student_read_session_{TS}.jsonl"
FINDINGS_JSON = CAMPAIGN_DIR / f"student_read_findings_{TS}.json"

# The 20 arXiv IDs captured in the first session (from its telemetry)
ARXIV_IDS = [
    "2608.06315v1", "2608.06261v1", "2608.06211v1", "2608.06130v1", "2608.06124v1",
    "2608.06061v1", "2608.05909v1", "2608.05902v1", "2608.05884v1", "2608.05870v1",
    "2608.05836v1", "2608.05831v1", "2608.05790v1", "2608.05754v1", "2608.05737v1",
    "2608.05736v1", "2608.05695v1", "2608.05659v1", "2608.05605v1", "2608.05578v1",
]

# security-domain signal words for thematic synthesis
THEME_WORDS = {
    "llm/agents": ["llm", "large language model", "agent", "prompt injection", "guardrail", "backdoor"],
    "cryptography": ["cryptograph", "encrypt", "signature", "gcm", "nonce", "quantum", "post-quantum", "hash"],
    "formal methods": ["proverif", "tamarin", "formal verification", "theorem", "lean", "proof"],
    "fuzzing": ["fuzz", "greybox", "coverage", "mutation"],
    "hardware/spectre": ["spectre", "meltdown", "speculation", "cpu", "cache side channel"],
    "ai safety": ["safety", "alignment", "unlearnable", "watermark", "copyright"],
    "network/ics": ["water distribution", "scada", "ics", "network anomaly", "baselining"],
    "cloud/zero-trust": ["zero-trust", "keystore", "mcp", "hardware wallet", "cloud"],
    "privacy/labelling": ["differential privacy", "local differential privacy", "privacy"],
}


def synthesize(text: str) -> dict:
    t = text.lower()
    themes = [name for name, kws in THEME_WORDS.items() if any(kw in t for kw in kws)]
    cves = list(dict.fromkeys(re.findall(r"CVE-\d{4}-\d{4,}", text, re.IGNORECASE)))
    # top-10 security-relevant tokens by frequency (stopword-lite)
    tokens = re.findall(r"[a-z][a-z-]{4,}", t)
    stop = {"using", "based", "with", "from", "this", "that", "these", "those", "their",
            "which", "where", "when", "than", "into", "also", "over", "such", "then",
            "paper", "section", "figure", "table", "algorithm", "result", "model", "data",
            "method", "approach", "provide", "propose", "present", "however", "among",
            "across", "during", "within", "after", "before", "about", "between", "other",
            "more", "most", "some", "can", "may", "will", "must", "would", "could", "should"}
    freq = Counter(t for t in tokens if t not in stop and len(t) > 4)
    return {"themes": themes, "cves": cves, "top_terms": freq.most_common(12)}


async def run():
    researcher = SciHubResearcher(db_path=str(CAMPAIGN_DIR / f"research_{TS}.db"))
    start = time.time()
    findings = []
    summary = {"papers_read": 0, "total_pdf_bytes": 0, "extract_failures": 0,
               "theme_counts": Counter(), "cve_mentions": Counter(), "per_paper": []}

    for idx, aid in enumerate(ARXIV_IDS, 1):
        t0 = time.time()
        pdf = await researcher.try_arxiv_direct(aid)
        if not pdf:
            ev = {"event": "read_fail", "arxiv_id": aid, "reason": "pdf unavailable"}
            print(f"  [tel] {ev['event']} {aid}")
            summary["extract_failures"] += 1
            continue
        text = researcher.extract_text(pdf)
        if not text or len(text) < 200:
            ev = {"event": "read_fail", "arxiv_id": aid, "reason": "text too short", "text_len": len(text)}
            print(f"  [tel] {ev['event']} {aid} ({len(text)} chars)")
            summary["extract_failures"] += 1
            continue

        summary["papers_read"] += 1
        summary["total_pdf_bytes"] += len(pdf)

        takeaway = researcher._extract_takeaway(text, aid)
        techniques = researcher.extract_techniques(text)
        chains = researcher._extract_chain(text)
        vulns = researcher.classify_vuln(text)
        synth = synthesize(text)

        for theme in synth["themes"]:
            summary["theme_counts"][theme] += 1
        for cve in synth["cves"]:
            summary["cve_mentions"][cve] += 1

        finding = {
            "arxiv_id": aid,
            "pdf_bytes": len(pdf),
            "text_chars": len(text),
            "takeaway": takeaway,
            "techniques": techniques[:8],
            "chain_steps": chains[:5],
            "vuln_classes": vulns[:4],
            "themes": synth["themes"],
            "cves": synth["cves"],
            "top_terms": synth["top_terms"],
            "read_s": round(time.time() - t0, 2),
        }
        findings.append(finding)
        ev = {"event": "read_ok", "arxiv_id": aid, "themes": synth["themes"],
              "cves": synth["cves"], "text_chars": len(text)}
        with open(TEL_LOG, "a") as f:
            f.write(json.dumps(ev, default=str) + "\n")
        print(f"  [tel] {ev['event']} {aid} themes={synth['themes']}")

    summary["duration_s"] = round(time.time() - start, 2)
    summary["theme_counts"] = dict(summary["theme_counts"])
    summary["cve_mentions"] = dict(summary["cve_mentions"])
    summary["per_paper"] = findings
    summary["telemetry_file"] = str(TEL_LOG)

    with open(FINDINGS_JSON, "w") as f:
        json.dump(summary, f, indent=2, default=str)

    print("\n=== READ REPORT ===")
    print(f"papers read: {summary['papers_read']} / {len(ARXIV_IDS)}  failures: {summary['extract_failures']}  total bytes: {summary['total_pdf_bytes']}  duration: {summary['duration_s']}s")
    print(f"themes: {summary['theme_counts']}")
    print(f"cve mentions: {summary['cve_mentions']}")
    for fp in findings:
        print(f"\n--- {fp['arxiv_id']} ---")
        print(f"  takeaway: {fp['takeaway'][:180]}")
        if fp["techniques"]:
            print(f"  techniques: {fp['techniques'][:3]}")
        if fp["cves"]:
            print(f"  cves: {fp['cves']}")
        print(f"  themes: {fp['themes']}  terms: {[t for t,_ in fp['top_terms'][:6]]}")
    await researcher._http.aclose()


if __name__ == "__main__":
    asyncio.run(run())