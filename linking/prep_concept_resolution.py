#!/usr/bin/env python3
"""prep_concept_resolution.py - finding #37 cleanup, stage 0.
- Tiny stoplist: pure proof-technique tokens are never ingredients (deterministic).
- Every other named-unresolved dangling ref gets up to 6 in-corpus candidate targets by
  token overlap (definitions + results), plus a 'none of these' option; judges pick.
- 20 decoys (dangling name paired with random unrelated candidates only) measure false-accept.
Outputs: <outdir>/tasks/res-<k>.txt (25 items each), truth/decoys.json, items.json, stoplisted.json
"""
import json, random, re, sys
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]      # repo root (scripts live one folder down)
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "audit" / "concept-res-v1"
(OUT / "tasks").mkdir(parents=True, exist_ok=True)
(OUT / "truth").mkdir(parents=True, exist_ok=True)
random.seed(20260902)

STOPLIST = {"contradiction", "proof by contradiction", "wlog", "without loss of generality", "assume", "suppose",
            "induction on n", "strong induction", "direct computation", "the same argument", "similarly"}
STOP = {"the", "a", "an", "of", "for", "on", "in", "is", "are", "and", "to", "by", "with"}

def toks(s):
    return {t for t in re.sub(r"[^a-z0-9]+", " ", s.lower()).split() if t not in STOP and len(t) > 2}

g = json.loads((ROOT / "data/build/graph.json").read_text(encoding="utf-8"))
nodes = {n["id"]: n for n in g["nodes"] if n.get("name")}
node_toks = {nid: toks(n["name"]) | toks((n.get("text") or "")[:200]) for nid, n in nodes.items()}

items, stoplisted = [], []
seen = set()
for d in g["dangling"]:
    if d.get("target_kind") != "named-unresolved" or not d.get("name"):
        continue
    name = d["name"].strip()
    key = name.lower()
    if key in STOPLIST:
        stoplisted.append(d); continue
    if key in seen:
        continue
    seen.add(key)
    nt = toks(name)
    scored = sorted(((len(nt & node_toks[nid]) / max(len(nt), 1), nid) for nid in nodes if nt & node_toks[nid]), reverse=True)[:6]
    if not scored:
        continue
    items.append({"item_id": f"CR-{len(items):04d}", "name": name, "example_source": d.get("source"),
                  "candidates": [{"cid": f"c{j}", "node": nid, "name": nodes[nid]["name"], "kind": nodes[nid].get("kind"),
                                  "text": (nodes[nid].get("text") or "")[:220]} for j, (_, nid) in enumerate(scored)]})

decoys = {}
all_nodes = list(nodes)
for j in range(20):
    base = random.choice(items)
    cands = random.sample([n for n in all_nodes if n not in {c["node"] for c in base["candidates"]}], 5)
    did = f"CR-D{j:03d}"
    items.append({"item_id": did, "name": base["name"], "example_source": base["example_source"],
                  "candidates": [{"cid": f"c{k}", "node": nid, "name": nodes[nid]["name"], "kind": nodes[nid].get("kind"),
                                  "text": (nodes[nid].get("text") or "")[:220]} for k, nid in enumerate(cands)]})
    decoys[did] = {"decoy": True, "true_item": base["item_id"]}
random.shuffle(items)
json.dump(items, open(OUT / "items.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(decoys, open(OUT / "truth" / "decoys.json", "w"), indent=1)
json.dump(stoplisted, open(OUT / "stoplisted.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

PROMPT = """You are resolving dangling references in a mathematics dependency graph. Each item is a NAME mentioned in a proof (as an ingredient) that was not linked to anything. You are given candidate in-corpus statements. Pick the candidate that IS the referenced result/definition (same mathematical object, possibly worded differently), or "none" if no candidate is it. Be strict: a candidate that is merely related, or shares a word, is NOT a match. Concept words like "continuous" should match the DEFINITION of continuity if present, not a theorem about continuity.

Output one JSON object per item, one per line, exactly:
{"item_id": "...", "pick": "<cid or none>", "confidence": 0.0-1.0, "reason": "<one short sentence>"}
No commentary. Do not read any files or the web.

"""
K = 25
for k in range(0, len(items), K):
    body = PROMPT
    for it in items[k:k+K]:
        body += f"\n=== ITEM {it['item_id']} === name: \"{it['name']}\"\n"
        for c in it["candidates"]:
            body += f"  [{c['cid']}] ({c['kind']}) {c['name']} :: {c['text']}\n"
    (OUT / "tasks" / f"res-{k//K:02d}.txt").write_text(body, encoding="utf-8")
print(f"items={len(items)} (incl 20 decoys), stoplisted={len(stoplisted)}, tasks={len(list((OUT/'tasks').glob('*.txt')))} -> {OUT}")
