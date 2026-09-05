#!/usr/bin/env python3
"""score_concept.py - concept-resolution stage 2: decoy control + accepted links.
Writes data/linking/concept_links.jsonl (revisable rows) and prints the summary."""
import json, glob
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]      # repo root (scripts live one folder down)
D = ROOT / "data/audit/concept-res-v1"
items = {it["item_id"]: it for it in json.loads((D / "items.json").read_text(encoding="utf-8"))}
decoys = json.loads((D / "truth/decoys.json").read_text())
verdicts = {}
for f in glob.glob(str(D / "out/*.txt")):
    for line in open(f, encoding="utf-8"):
        if line.strip():
            v = json.loads(line); verdicts[v["item_id"]] = v
missing = [i for i in items if i not in verdicts]
d_total = d_acc = 0
for did in decoys:
    v = verdicts.get(did)
    if not v: continue
    d_total += 1
    if v["pick"] != "none":
        d_acc += 1; print(f"DECOY ACCEPTED: {did} '{items[did]['name']}' -> {v['pick']} conf={v['confidence']} ({v['reason']})")
dist = Counter(); rows = []
for iid, v in verdicts.items():
    if iid in decoys: continue
    it = items[iid]
    if v["pick"] == "none":
        dist["none"] += 1; continue
    cand = next((c for c in it["candidates"] if c["cid"] == v["pick"]), None)
    if not cand:
        dist["bad-cid"] += 1; continue
    dist["resolved"] += 1
    rows.append({"relation": "concept-resolution", "name": it["name"], "to": cand["node"], "to_name": cand["name"],
                 "to_kind": cand["kind"], "method": "llm-judge", "model": "opus", "confidence": v["confidence"],
                 "reason": v["reason"], "decided_at": "2026-09-02", "decided_by": "concept-res-v1"})
out = ROOT / "data/linking/concept_links.jsonl"
with open(out, "w", encoding="utf-8") as f:
    for r in sorted(rows, key=lambda r: -r["confidence"]):
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
hi = sum(1 for r in rows if r["confidence"] >= 0.8)
print(f"verdicts {len(verdicts)}/{len(items)} (missing {len(missing)}); decoys falsely accepted {d_acc}/{d_total}")
print(f"real items: {dict(dist)}; accepted links {len(rows)} (>=0.8 conf: {hi}); by target kind: {Counter(r['to_kind'] for r in rows).most_common()}")
print("sample:", [(r['name'], '->', r['to_name'], r['confidence']) for r in rows[:6]])
