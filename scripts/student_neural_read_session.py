#!/usr/bin/env python3
"""
THE STUDENT — deep-read pass over neural thinking papers (Neural Networks & Thinking Capability)
Full-text extraction (pypdf, in-memory), then extraction primitives over COMPLETE text.
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
TEL_LOG = CAMPAIGN_DIR / f"student_neural_read_session_{TS}.jsonl"
FINDINGS_JSON = CAMPAIGN_DIR / f"student_neural_read_findings_{TS}.json"

# Neural thinking theme words
NEURAL_THEME_WORDS = {
    "chain-of-thought": ["chain of thought", "chain-of-thought", "cot", "scratchpad", "intermediate reasoning"],
    "system-2-thinking": ["system 2", "system-2", "system two", "slow thinking", "deliberative"],
    "mechanistic-interpretability": ["mechanistic interpretability", "interpretability", "circuit", "feature", "activation", "neuron"],
    "reasoning": ["reasoning", "reasoning capabilities", "logical reasoning", "multi-step reasoning", "deductive", "inductive"],
    "planning": ["planning", "planning capabilities", "plan generation", "strategic planning", "plan"],
    "in-context-learning": ["in-context learning", "icl", "few-shot", "few shot", "context window"],
    "self-consistency": ["self-consistency", "consistency", "majority vote"],
    "tree-of-thought": ["tree of thought", "graph of thought", "program of thought", "tree search", "beam search"],
    "decomposition": ["decomposition", "decompose", "subproblem", "sub-problem", "divide and conquer"],
    "neural-network-reasoning": ["neural network reasoning", "neural reasoning", "llm reasoning", "language model reasoning"],
    "mechanistic": ["mechanistic", "circuit", "feature", "superposition", "polysemantic"],
    "activation-analysis": ["activation", "activation space", "activation analysis", "probing", "linear probe"],
    "faithfulness": ["faithfulness", "faithful", "explanation", "explainability"],
    "emergent-abilities": ["emergent", "emergence", "phase transition", "scaling laws"],
    "alignment": ["alignment", "aligned", "rlhf", "rlhf", "dpo", "preference"],
    "generalization": ["generalization", "generalise", "generalize", "out-of-distribution", "o.o.d"],
    "robustness": ["robustness", "robust", "adversarial", "adversarial robustness"],
    "efficiency": ["efficiency", "efficient", "compression", "quantization", "distillation", "pruning"],
}


def synthesize(text: str) -> dict:
    t = text.lower()
    themes = [name for name, kws in NEURAL_THEME_WORDS.items() if any(kw in t for kw in kws)]
    cves = list(dict.fromkeys(re.findall(r"CVE-\d{4}-\d{4,}", text, re.IGNORECASE)))
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
    # Find the latest neural thinking database
    db_files = sorted(CAMPAIGN_DIR.glob("research_neural_thinking_*.db"))
    if not db_files:
        print("No neural thinking research database found!")
        return
    DB_PATH = db_files[-1]
    print(f"Using database: {DB_PATH}")

    researcher = SciHubResearcher(db_path=str(DB_PATH))
    start = time.time()
    findings = []
    summary = {"papers_read": 0, "total_pdf_bytes": 0, "extract_failures": 0,
               "theme_counts": Counter(), "cve_mentions": Counter(), "per_paper": []}

    # Get all arXiv IDs from the database
    import sqlite3
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("SELECT id, title FROM ingested_writeups")
        rows = cur.fetchall()

    ARXIV_IDS = [row[0] for row in rows]
    print(f"Found {len(ARXIV_IDS)} papers in database")

    for idx, aid in enumerate(ARXIV_IDS, 1):
        t0 = time.time()
        # Get the full text from DB
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.execute("SELECT full_text, title, source_url FROM ingested_writeups WHERE id = ?", (aid,))
            row = cur.fetchone()
            if not row:
                print(f"  [tel] read_fail {aid} (not in DB)")
                summary["extract_failures"] += 1
                continue
            text, title, pdf_url = row

        if not text or len(text) < 200:
            print(f"  [tel] read_fail {aid} (text too short: {len(text)} chars)")
            summary["extract_failures"] += 1
            continue

        summary["papers_read"] += 1
        summary["total_pdf_bytes"] += len(text.encode())

        # Use existing extraction methods from SciHubResearcher
        takeaway = researcher._extract_takeaway(text, aid) if hasattr(researcher, '_extract_takeaway') else text[:500]
        techniques = researcher.extract_techniques(text) if hasattr(researcher, 'extract_techniques') else []
        chains = researcher._extract_chain(text) if hasattr(researcher, '_extract_chain') else []
        vulns = researcher.classify_vuln(text) if hasattr(researcher, 'classify_vuln') else []
        synth = synthesize(text)

        for theme in synth["themes"]:
            summary["theme_counts"][theme] += 1
        for cve in synth["cves"]:
            summary["cve_mentions"][cve] += 1

        finding = {
            "arxiv_id": aid,
            "pdf_bytes": len(text.encode()),
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

    print("\n=== NEURAL THINKING READ REPORT ===")
    print(f"papers read: {summary['papers_read']} / {len(ARXIV_IDS)}  failures: {summary['extract_failures']}  total bytes: {summary['total_pdf_bytes']}  duration: {summary['duration_s']}s")
    print(f"themes: {summary['theme_counts']}")
    print(f"cve mentions: {summary['cve_mentions']}")
    for fp in findings:
        print(f"\n--- {fp['arxiv_id']} ---")
        print(f"  takeaway: {fp['takeaway'][:200]}")
        print(f"  themes: {fp['themes']}")
        print(f"  top_terms: {fp['top_terms'][:8]}")


if __name__ == "__main__":
    import time
    start = time.time()
    asyncio.run(run())