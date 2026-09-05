#!/usr/bin/env python3
"""s2_citations.py - exhaustive forward-citation crawl via the Semantic Scholar Graph API (free, no key).

For each anchor paper (arXiv id), pulls EVERY citing paper (title, year, abstract, arXiv id,
citation count) — unlike a search engine, this is complete coverage of what S2 has indexed.
Writes one JSONL per anchor plus a combined markdown digest: full title list, with papers
matching relevance keyword buckets flagged and grouped first.

  python s2_citations.py -o CITATIONS-2026-08-31   # writes CITATIONS-2026-08-31.jsonl / .md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request

API = "https://api.semanticscholar.org/graph/v1/paper/arXiv:{aid}/citations"
FIELDS = "title,year,abstract,externalIds,citationCount,venue"

ANCHORS = {
    "2104.01112": "NaturalProofs",
    "2606.25363": "TheoremGraph",
    "2605.09012": "Re2Math",
    "2607.16997": "PriorProof",
    "2608.14669": "BeyondCorrectness/AViD",
    "2508.17596": "ConnectedTheorems",
    "1202.3936": "TimeToProof2012",
}

BUCKETS = {
    "temporal": r"\b(tempor|time[- ]slic|time[- ]condition|historical|history|date[ds]?\b|chronolog|snapshot)",
    "retrieval": r"\b(retriev|premise select|reference|search)",
    "ripeness": r"\b(ripe|solvab|forecast|predict\w* (?:discover|solution|proof|solv)|when .* (?:proved|solved))",
    "graph": r"\b(dependency graph|knowledge graph|citation graph|theorem graph)",
}


def fetch_citations(aid: str) -> list[dict]:
    out, offset = [], 0
    while True:
        q = urllib.parse.urlencode({"fields": FIELDS, "limit": 1000, "offset": offset})
        req = urllib.request.Request(f"{API.format(aid=aid)}?{q}",
                                     headers={"User-Agent": "rsireasoner-litreview/1.0"})
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = json.load(r)
                break
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 4:
                    time.sleep(10 * (attempt + 1))
                    continue
                raise
        for row in data.get("data", []):
            p = row.get("citingPaper") or {}
            if p.get("title"):
                out.append(p)
        nxt = data.get("next")
        if nxt is None:
            return out
        offset = nxt
        time.sleep(1.5)  # stay under the unauthenticated rate limit


def buckets_for(p: dict) -> list[str]:
    text = f"{p.get('title') or ''} {p.get('abstract') or ''}".lower()
    return [name for name, pat in BUCKETS.items() if re.search(pat, text)]


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", required=True, help="output basename (writes <out>.jsonl and <out>.md)")
    a = ap.parse_args()

    all_rows, seen = [], set()
    for aid, name in ANCHORS.items():
        try:
            cites = fetch_citations(aid)
        except Exception as e:
            print(f"{name} ({aid}): FAILED {type(e).__name__}: {e}", file=sys.stderr)
            continue
        print(f"{name} ({aid}): {len(cites)} citing papers")
        for p in cites:
            key = p.get("paperId") or p["title"].lower()
            row = {"anchor": name, "anchor_arxiv": aid, "buckets": buckets_for(p),
                   "arxiv": (p.get("externalIds") or {}).get("ArXiv"),
                   "title": p["title"], "year": p.get("year"), "venue": p.get("venue"),
                   "citationCount": p.get("citationCount"), "abstract": p.get("abstract"),
                   "dup": key in seen}
            seen.add(key)
            all_rows.append(row)
        time.sleep(1.5)

    with open(a.out + ".jsonl", "w", encoding="utf-8", newline="\n") as f:
        for row in all_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    flagged = [r for r in all_rows if r["buckets"] and not r["dup"]]
    rest = [r for r in all_rows if not r["buckets"] and not r["dup"]]
    lines = [f"# Forward-citation crawl — {len(all_rows)} rows, {len(seen)} unique papers", ""]
    lines.append(f"## Keyword-flagged ({len(flagged)}) — review abstracts")
    for r in sorted(flagged, key=lambda r: -(r["citationCount"] or 0)):
        aid = f" [arXiv:{r['arxiv']}]" if r["arxiv"] else ""
        lines.append(f"- **{r['title']}** ({r['year']}){aid} — cites {r['anchor']}; "
                     f"buckets: {','.join(r['buckets'])}; cited-by {r['citationCount']}")
    lines.append("")
    lines.append(f"## Everything else ({len(rest)}) — title skim")
    for r in sorted(rest, key=lambda r: (r["anchor"], -(r["citationCount"] or 0))):
        aid = f" [arXiv:{r['arxiv']}]" if r["arxiv"] else ""
        lines.append(f"- {r['title']} ({r['year']}){aid} — cites {r['anchor']}; cited-by {r['citationCount']}")
    with open(a.out + ".md", "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {a.out}.jsonl and {a.out}.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
