#!/usr/bin/env python3
"""
THE STUDENT — research ingestion session, OPEN-ACCESS ONLY (no sci-hub, no Tor).

Sources: arXiv cs.CR official API (export.arxiv.org). PDFs fetched directly from
arxiv.org — fully licensed open-access content. No paywall bypass, no proxy.

Adaptations living in this script only (src/ untouched):
  1. data_route     -> try_arxiv_direct ONLY (the legal path)
  2. extract_text   -> pypdf fallback (pdftotext binary not installed here)

Telemetry: every step appended to
  evaluations/campaign/student_arxiv_session_<ts>.jsonl
"""
import asyncio
import hashlib
import json
import logging
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
_SRC = _REPO_ROOT + "/src"
for p in (_SRC, _REPO_ROOT):
    while p in sys.path:
        sys.path.remove(p)
sys.path.insert(0, _SRC)
sys.path.insert(0, _REPO_ROOT)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("pypdf").setLevel(logging.WARNING)

from orchestrator.student.scihub import SciHubResearcher


# ── Patch: pypdf text extraction (pdftotext unavailable) ────────────────────
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

# ── Telemetry ───────────────────────────────────────────────────────────────
CAMPAIGN_DIR = Path(_REPO_ROOT) / "evaluations" / "campaign"
CAMPAIGN_DIR.mkdir(parents=True, exist_ok=True)
TS = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
TEL_LOG = CAMPAIGN_DIR / f"student_arxiv_session_{TS}.jsonl"
DB_PATH = CAMPAIGN_DIR / f"research_{TS}.db"


def emit(event: dict):
    event["ts"] = datetime.now(timezone.utc).isoformat()
    with open(TEL_LOG, "a") as f:
        f.write(json.dumps(event) + "\n")
    print(f"  [tel] {event.get('event','')} {event.get('title','')[:70]}")


async def run():
    start = time.time()
    emit({"event": "session_start", "mode": "OPEN_ACCESS", "source": "arxiv_cs.CR",
          "pdf_endpoint": "https://arxiv.org/pdf/", "max_papers": 20,
          "legal": "open-access only, no paywall bypass"})

    researcher = SciHubResearcher(db_path=str(DB_PATH))

    papers = await researcher.fetch_arxiv_papers(max_results=100)
    emit({"event": "arxiv_fetched", "count": len(papers),
          "with_doi": sum(1 for p in papers if p.get("doi"))})

    report = {
        "papers_fetched": len(papers),
        "papers_with_doi": sum(1 for p in papers if p["doi"]),
        "papers_attempted": 0,
        "pdfs_downloaded": 0,
        "pdfs_extracted": 0,
        "writeups_stored": 0,
        "failures": [],
        "paper_details": [],
    }

    for paper in papers[:20]:
        report["papers_attempted"] += 1
        t0 = time.time()

        if not paper.get("arxiv_id"):
            report["failures"].append({"title": paper["title"][:80], "reason": "no arxiv id"})
            emit({"event": "paper_failed", "title": paper["title"][:70], "reason": "no arxiv id"})
            continue

        r0 = time.time()
        pdf_data = await researcher.try_arxiv_direct(paper["arxiv_id"])
        dt = time.time() - r0

        if not pdf_data:
            report["failures"].append({"title": paper["title"][:80], "reason": "arxiv pdf 4xx/5xx"})
            emit({"event": "paper_failed", "title": paper["title"][:70],
                  "arxiv_id": paper["arxiv_id"], "reason": "arxiv pdf unavailable",
                  "elapsed_s": round(dt, 2)})
            continue

        report["pdfs_downloaded"] += 1
        emit({"event": "pdf_ok", "title": paper["title"][:70], "arxiv_id": paper["arxiv_id"],
              "route": "arxiv", "bytes": len(pdf_data), "lookup_s": round(dt, 2)})

        text = researcher.extract_text(pdf_data)
        if not text or len(text) < 50:
            report["failures"].append({"title": paper["title"][:80], "reason": "text extraction empty"})
            emit({"event": "extract_empty", "title": paper["title"][:70], "arxiv_id": paper["arxiv_id"],
                  "text_len": len(text)})
            continue

        report["pdfs_extracted"] += 1
        vuln_classes = researcher.classify_vuln(text)
        techniques = researcher.extract_techniques(text)
        tags = researcher.extract_tags(paper["title"], text, vuln_classes)

        article_id = hashlib.sha256(f"arxiv:{paper['arxiv_id']}".encode()).hexdigest()[:16]
        key_takeaway = researcher._extract_takeaway(text, paper["title"])
        cve_refs = re.findall(r"CVE-\d{4}-\d{4,}", text + paper["title"], re.IGNORECASE)
        chain_steps = researcher._extract_chain(text)

        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                """INSERT OR IGNORE INTO ingested_writeups
                   (id, title, source_url, source_name, vuln_class, target_stack,
                    chain, key_takeaway, tags, cve_refs, raw_summary, full_text, ingested_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (article_id, paper["title"][:500],
                 paper.get("pdf_url", f"https://arxiv.org/abs/{paper.get('arxiv_id','')}"),
                 "arxiv", vuln_classes[0],
                 json.dumps(list(set(re.findall(r"\b(aws|azure|gcp|linux|windows|android|ios|web|cloud|network|mobile|iot)\b",
                                                text, re.IGNORECASE)))),
                 json.dumps(chain_steps), key_takeaway, json.dumps(tags), json.dumps(cve_refs),
                 paper["summary"][:1000] if paper["summary"] else text[:1000],
                 text[:2000], time.time()))
        report["writeups_stored"] += 1
        report["paper_details"].append({"title": paper["title"], "arxiv_id": paper["arxiv_id"],
                                        "vuln_class": vuln_classes[0], "tags": tags, "cves": cve_refs,
                                        "route": "arxiv"})
        emit({"event": "writeup_stored", "title": paper["title"][:70], "arxiv_id": paper["arxiv_id"],
              "vuln_class": vuln_classes[0], "route": "arxiv",
              "paper_s": round(time.time() - t0, 2)})

    report["duration_s"] = round(time.time() - start, 2)
    report["telemetry_file"] = str(TEL_LOG)
    emit({"event": "session_end", "report": report})
    print("\n=== STUDENT SESSION REPORT (ARXIV, OPEN ACCESS) ===")
    print(json.dumps(report, indent=2))
    await researcher._http.aclose()


if __name__ == "__main__":
    asyncio.run(run())