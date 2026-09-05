#!/usr/bin/env python3
"""redundancy_check.py - cross-source ingredient agreement (deterministic).
For every canonical node with proofs from >=2 different source docs, compare the
canonical-lifted ingredient sets. Disagreement localizes extractor misses / route
differences. Output: data/audit/REDUNDANCY-REPORT.md
"""
import json
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]      # repo root (scripts live one folder down)
g = json.loads((ROOT / "data/build/graph.json").read_text(encoding="utf-8"))
nodes = {n["id"]: n for n in g["nodes"]}
# proofs per canonical node, keyed by source doc of the proof
uses = defaultdict(lambda: defaultdict(set))  # node -> proof_id -> set(targets)
doc_of = {}
for e in g["edges"]:
    if e.get("target"):
        uses[e["source"]][e["proof"]].add(e["target"])
        doc_of[e["proof"]] = e["proof"].split(":")[1]
rows = []
for nid, proofs in uses.items():
    docs = {doc_of[p] for p in proofs}
    if len(docs) < 2:
        continue
    by_doc = defaultdict(set)
    for p, t in proofs.items():
        by_doc[doc_of[p]] |= t
    dl = sorted(by_doc)
    a, b = by_doc[dl[0]], by_doc[dl[1]]
    j = len(a & b) / len(a | b) if (a | b) else 1.0
    rows.append((nid, dl[0], len(a), dl[1], len(b), len(a & b), j))
rows.sort(key=lambda r: r[-1])
out = ROOT / "data" / "audit" / "REDUNDANCY-REPORT.md"
out.parent.mkdir(parents=True, exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    f.write(f"# Cross-source ingredient redundancy check (2026-09-02)\n\nCanonical nodes with proofs from >=2 sources: **{len(rows)}** (of {len(uses)} nodes with any edges). Jaccard of canonical-lifted ingredient sets; low values = route difference OR extractor miss (needs a look).\n\n")
    f.write("| node | src A | #A | src B | #B | shared | Jaccard |\n|---|---|---|---|---|---|---|\n")
    for nid, da, na, db, nb, sh, j in rows:
        f.write(f"| {nodes.get(nid, {}).get('name', nid)} | {da} | {na} | {db} | {nb} | {sh} | {j:.2f} |\n")
    if rows:
        f.write(f"\nMean Jaccard: {sum(r[-1] for r in rows)/len(rows):.2f}; nodes with zero overlap: {sum(1 for r in rows if r[-1]==0)}\n")
print(f"multi-source nodes: {len(rows)} -> {out}")
