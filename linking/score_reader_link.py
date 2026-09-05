#!/usr/bin/env python3
"""score_reader_link.py - reader-link stage 2: decoy control + accepted links -> data/linking/reader_links.jsonl.
Rows carry every surface variant of the resolved name (so build_graph's exact-normalized lookup hits them all)."""
import json, glob, re, sys
from pathlib import Path
from collections import Counter, defaultdict
ROOT = Path(__file__).resolve().parents[1]      # repo root (scripts live one folder down)
D = ROOT / "data/audit/reader-link-v1"
STOP = {"the","a","an","of","for","on","in","is","are","and","to","by","with","at","as","or"}
def toks(s): return {t for t in re.sub(r"[^a-z0-9]+"," ",(s or "").lower()).split() if t not in STOP and len(t)>2}
def norm(s): return " ".join(sorted(toks(s)))
items = {it["item_id"]: it for it in json.loads((D/"items.json").read_text(encoding="utf-8"))}
decoys = json.loads((D/"truth/decoys.json").read_text())
verdicts = {}
for f in glob.glob(str(D/"out/*.txt")):
    for line in open(f, encoding="utf-8"):
        if line.strip():
            try: v = json.loads(line); verdicts[v["item_id"]] = v
            except json.JSONDecodeError: pass
d_tot = d_acc = 0
for did in decoys:
    v = verdicts.get(did)
    if not v: continue
    d_tot += 1
    if v["pick"] != "none":
        d_acc += 1; print(f"DECOY ACCEPTED: {did} '{items[did]['name']}' -> {v['pick']} conf={v['confidence']} ({v['reason']})")
g = json.loads((ROOT/"data/build/graph.json").read_text(encoding="utf-8"))
variants = defaultdict(set)
for d in g["dangling"]:
    if str(d.get("provenance","")).startswith("reader-") and d.get("name"):
        variants[norm(d["name"])].add(d["name"])
rows, dist = [], Counter()
for iid, v in verdicts.items():
    if iid in decoys or iid not in items: continue
    it = items[iid]
    if v["pick"] == "none": dist["none"] += 1; continue
    c = next((c for c in it["candidates"] if c["cid"] == v["pick"]), None)
    if not c: dist["bad-cid"] += 1; continue
    dist["resolved"] += 1
    for nm in variants.get(norm(it["name"]), {it["name"]}):
        rows.append({"relation": "reader-link", "name": nm, "to": c["node"], "to_name": c["name"], "to_kind": c["kind"],
                     "method": "llm-judge", "model": "opus", "confidence": v["confidence"], "reason": v["reason"],
                     "decided_at": "2026-09-03", "decided_by": "reader-link-v1"})
out = ROOT/"data/linking/reader_links.jsonl"
with open(out, "w", encoding="utf-8") as f:
    for r in sorted(rows, key=lambda r: -r["confidence"]): f.write(json.dumps(r, ensure_ascii=False)+"\n")
print(f"verdicts {len(verdicts)}/{len(items)}; decoys falsely accepted {d_acc}/{d_tot}; real items {dict(dist)}; link rows {len(rows)} (>=0.8: {sum(1 for r in rows if r['confidence']>=0.8)})")
import random; random.seed(3)
print("SPOT-CHECK (15 accepts):")
seen=set()
for r in random.sample([r for r in rows if r['confidence']>=0.75], min(15, len(rows))):
    print(f"  [{r['confidence']}] {r['name'][:60]!r} -> {r['to_name'][:60]!r} ({r['to_kind']})")
