#!/usr/bin/env python3
"""
THE STUDENT — Neural Networks & Thinking Capability Research Session
Focus: Neural network reasoning, chain-of-thought, System 2 thinking, 
mechanistic interpretability, planning, reasoning capabilities.
Sources: arXiv (cs.LG, cs.AI, cs.CL, cs.NE, stat.ML) — OPEN ACCESS ONLY
"""
import asyncio
import hashlib
import json
import logging
import os
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


# ── Patch: pypdf text extraction ────────────────────────────────────────────
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


# ── Custom search for Neural Networks & Thinking Capability ─────────────────
NEURAL_THINKING_QUERY = (
    "cat:cs.LG OR cat:cs.AI OR cat:cs.CL OR cat:cs.NE OR cat:stat.ML"
    " AND ("
    "  ti:\"chain of thought\" OR ti:\"chain-of-thought\" OR ti:\"reasoning\" OR "
    "  ti:\"system 2\" OR ti:\"system-2\" OR ti:\"system two\" OR "
    "  ti:\"mechanistic interpretability\" OR ti:\"interpretability\" OR "
    "  ti:\"reasoning capabilities\" OR ti:\"planning\" OR "
    "  ti:\"neural network reasoning\" OR ti:\"large language model reasoning\" OR "
    "  ti:\"thinking\" OR ti:\"in-context learning\" OR "
    "  ti:\"scratchpad\" OR ti:\"self-consistency\" OR "
    "  ti:\"tree of thought\" OR ti:\"graph of thought\" OR "
    "  ti:\"program of thought\" OR ti:\"decomposition\""
    ")"
)

ARXIV_API = "https://export.arxiv.org/api/query"

# Keywords for tagging papers in the DB
NEURAL_THINKING_KEYWORDS = {
    "Chain-of-Thought": ["chain of thought", "chain-of-thought", "cot", "scratchpad"],
    "System-2-Thinking": ["system 2", "system-2", "system two", "slow thinking"],
    "Mechanistic-Interpretability": ["mechanistic interpretability", "interpretability", "circuit", "feature"],
    "Reasoning": ["reasoning", "reasoning capabilities", "logical reasoning", "multi-step reasoning"],
    "Planning": ["planning", "planning capabilities", "plan generation", "strategic"],
    "In-Context-Learning": ["in-context learning", "icl", "few-shot"],
    "Self-Consistency": ["self-consistency", "consistency"],
    "Tree-of-Thought": ["tree of thought", "graph of thought", "program of thought"],
    "Decomposition": ["decomposition", "decompose", "subproblem"],
    "Neural-Network-Reasoning": ["neural network reasoning", "neural reasoning", "llm reasoning"],
}

# ─── Telemetry ─────────────────────────────────────────────────────────────
CAMPAIGN_DIR = Path(_REPO_ROOT) / "evaluations" / "campaign"
CAMPAIGN_DIR.mkdir(parents=True, exist_ok=True)
TS = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
TEL_LOG = CAMPAIGN_DIR / f"student_neural_thinking_session_{TS}.jsonl"
DB_PATH = CAMPAIGN_DIR / f"research_neural_thinking_{TS}.db"


def emit(event: dict):
    event["ts"] = datetime.now(timezone.utc).isoformat()
    with open(TEL_LOG, "a") as f:
        f.write(json.dumps(event) + "\n")
    print(f"  [tel] {event.get('event','')} {event.get('title','')[:70]}")


class NeuralThinkingResearcher(SciHubResearcher):
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(DB_PATH)
        super().__init__(db_path)
        self.query = NEURAL_THINKING_QUERY
        self.keywords = NEURAL_THINKING_KEYWORDS

    async def fetch_papers(self, max_results: int = 50) -> list[dict]:
        """Fetch papers matching neural thinking query from arXiv."""
        params = {
            "search_query": self.query,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": max_results,
        }
        logging.getLogger("student.scihub").info("Fetching neural thinking papers from arXiv...")
        resp = await self._http.get(ARXIV_API, params=params)
        resp.raise_for_status()

        import xml.etree.ElementTree as ET
        root = ET.fromstring(resp.text)
        ns = {
            'atom': 'http://www.w3.org/2005/Atom',
            'arxiv': 'http://arxiv.org/schemas/atom',
        }
        papers = []
        for entry in root.findall('atom:entry', ns):
            title_el = entry.find('atom:title', ns)
            summary_el = entry.find('atom:summary', ns)
            published_el = entry.find('atom:published', ns)
            id_el = entry.find('atom:id', ns)
            arxiv_id = ""
            if id_el is not None and id_el.text:
                arxiv_id = id_el.text.split('/')[-1] if '/' in id_el.text else id_el.text

            pdf_url = ""
            for link in entry.findall('atom:link', ns):
                if link.get('type') == 'application/pdf':
                    pdf_url = link.get('href', '')
                    break

            paper = {
                "arxiv_id": arxiv_id,
                "title": title_el.text.strip() if title_el is not None else "",
                "summary": summary_el.text.strip() if summary_el is not None else "",
                "published": published_el.text.strip() if published_el is not None else "",
                "pdf_url": pdf_url,
            }
            if paper["title"] and paper["pdf_url"]:
                papers.append(paper)
        return papers

    def tag_paper(self, title: str, summary: str) -> list[str]:
        """Tag paper with neural thinking themes."""
        text = (title + " " + summary).lower()
        tags = []
        for theme, kws in self.keywords.items():
            if any(kw.lower() in text for kw in kws):
                tags.append(theme)
        return tags

    async def ingest_paper(self, paper: dict) -> bool:
        """Download, extract, and store paper."""
        arxiv_id = paper["arxiv_id"]
        title = paper["title"]
        summary = paper["summary"]
        pdf_url = paper["pdf_url"]

        # Check if already ingested
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("SELECT id FROM ingested_writeups WHERE id = ?", (arxiv_id,))
            if cur.fetchone():
                logging.getLogger("student.scihub").info("Already ingested: %s", arxiv_id)
                return False

        # Download PDF
        try:
            logging.getLogger("student.scihub").info("Downloading %s...", arxiv_id)
            resp = await self._http.get(pdf_url, timeout=60.0)
            resp.raise_for_status()
            pdf_data = resp.content
        except Exception as e:
            emit({"event": "download_fail", "arxiv_id": arxiv_id, "error": str(e)})
            return False

        # Extract text
        full_text = self.extract_text(pdf_data)
        if not full_text or len(full_text) < 500:
            emit({"event": "extract_fail", "arxiv_id": arxiv_id, "chars": len(full_text)})
            return False

        # Tag paper
        tags = self.tag_paper(title, summary)
        key_takeaway = self.generate_takeaway(full_text[:3000])

        # Store in DB
        import hashlib
        doc_id = hashlib.sha256(arxiv_id.encode()).hexdigest()[:16]
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO ingested_writeups
                (id, title, source_url, source_name, vuln_class, target_stack, chain,
                 key_takeaway, tags, cve_refs, raw_summary, full_text, ingested_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                doc_id, title, pdf_url, "arxiv_neural_thinking",
                "NeuralThinking", "[]", "[]",
                key_takeaway, json.dumps(tags), "[]", summary, full_text,
                time.time()
            ))

        emit({"event": "ingest_ok", "arxiv_id": arxiv_id, "tags": tags, "chars": len(full_text)})
        return True

    def generate_takeaway(self, text: str) -> str:
        """Extract key takeaway from paper text (first meaningful sentences)."""
        sentences = re.split(r'[.!?]\s+', text)
        meaningful = [s.strip() for s in sentences if len(s) > 50 and not s.strip().startswith(('http', 'arXiv', 'doi', 'Abstract', 'ABSTRACT'))]
        return " ".join(meaningful[:3])[:500] if meaningful else "No clear takeaway extracted"


async def main():
    print("=" * 70)
    print("  THE STUDENT — Neural Networks & Thinking Capability Research")
    print("=" * 70)
    print(f"Query: {NEURAL_THINKING_QUERY[:100]}...")
    print(f"Telemetry: {TEL_LOG}")
    print(f"Database: {DB_PATH}")
    print()

    researcher = NeuralThinkingResearcher()
    emit({"event": "session_start", "mode": "OPEN_ACCESS", "query": NEURAL_THINKING_QUERY})

    # Fetch papers
    papers = await researcher.fetch_papers(max_results=30)
    print(f"Found {len(papers)} papers matching query")
    emit({"event": "papers_fetched", "count": len(papers)})

    # Ingest papers
    ok = 0
    for i, paper in enumerate(papers):
        print(f"  [{i+1}/{len(papers)}] {paper['arxiv_id']}: {paper['title'][:80]}")
        if await researcher.ingest_paper(paper):
            ok += 1
        await asyncio.sleep(1)  # be nice to arXiv

    emit({"event": "session_complete", "fetched": len(papers), "ingested": ok, "duration_s": time.time() - start_time})
    print(f"\n[+] Session complete: {ok}/{len(papers)} papers ingested")
    print(f"Telemetry: {TEL_LOG}")
    print(f"Database: {DB_PATH}")


if __name__ == "__main__":
    import time
    start_time = time.time()
    asyncio.run(main())