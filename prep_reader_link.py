#!/usr/bin/env python3
"""prep_reader_link.py - judged linking of reader-layer ingredient names to in-corpus statements (stage 0).
Takes every reader-layer named-unresolved reference in the built graph (deduped by normalized name,
technique words excluded), proposes up to 6 in-corpus candidates by token overlap over names+text, adds
20 blind decoys, and writes judge tasks. Same protocol as concept-res-v1 (0/20 decoys accepted there).
Outputs: data/audit/reader-link-v1/{items.json, truth/decoys.json, tasks/*.txt}
"""
import json, random, re, sys
from pathlib import Path
from collections import Counter, defaultdict

ROOT = Path(__file__).parent
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "audit" / "reader-link-v1"
(OUT / "tasks").mkdir(parents=True, exist_ok=True); (OUT / "truth").mkdir(exist_ok=True)
random.seed(20260903)
STOP = {"the", "a", "an", "of", "for", "on", "in", "is", "are", "and", "to", "by", "with", "at", "as", "or"}
TECH = re.compile(r"\b(contradiction|wlog|without loss of generality|induction)\b", re.I)

def toks(s): return {t for t in re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).split() if t not in STOP and len(t) > 2}
def norm(s): return " ".join(sorted(toks(s)))

g = json.loads((ROOT / "data/build/graph.json").read_text(encoding="utf-8"))
nodes = {n["id"]: n for n in g["nodes"] if n.get("name")}
node_toks = {nid: toks(n["name"]) | toks((n.get("text") or "")[:240]) for nid, n in nodes.items()}

by_name = defaultdict(list)
for d in g["dangling"]:
    if not str(d.get("provenance", "")).startswith("reader-") or not d.get("name"):
        continue
    if TECH.search(d["name"]) or d.get("kind") == "technique":
        continue
    by_name[norm(d["name"])].append(d)
items = []
for key, refs in by_name.items():
    name = max((r["name"] for r in refs), key=len)
    nt = toks(name)
    scored = sorted(((len(nt & node_toks[nid]) / max(len(nt), 1), nid) for nid in nodes if nt & node_toks[nid]), reverse=True)[:6]
    if not scored or scored[0][0] < 0.34:
        continue
    items.append({"item_id": f"RL-{len(items):04d}", "name": name, "kind": refs[0].get("kind"), "n_refs": len(refs),
                  "sources": sorted({r["source"] for r in refs})[:5],
                  "candidates": [{"cid": f"c{j}", "node": nid, "name": nodes[nid]["name"], "kind": nodes[nid].get("kind"),
                                  "text": (nodes[nid].get("text") or "")[:220]} for j, (_, nid) in enumerate(scored)]})
n_real = len(items)
decoys = {}
all_nodes = list(nodes)
for j in range(20):
    base = random.choice(items[:n_real])
    cands = random.sample([n for n in all_nodes if n not in {c["node"] for c in base["candidates"]}], 5)
    did = f"RL-D{j:03d}"
    items.append({**base, "item_id": did, "candidates": [{"cid": f"c{k}", "node": nid, "name": nodes[nid]["name"], "kind": nodes[nid].get("kind"),
                                                          "text": (nodes[nid].get("text") or "")[:220]} for k, nid in enumerate(cands)]})
    decoys[did] = {"decoy": True, "true_item": base["item_id"]}
random.shuffle(items)
json.dump(items, open(OUT / "items.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(decoys, open(OUT / "truth/decoys.json", "w"), indent=1)

PROMPT = """You are resolving ingredient references in a mathematics dependency graph. Each item is a result or concept NAME that a proof relies on (found by a reader), not yet linked to a statement. You are given candidate in-corpus statements. Pick the candidate that IS that result/concept (same mathematical object, possibly worded differently or a standard special case presented as the named result), or "none" if no candidate is it. Be strict: sharing words is not a match; a theorem ABOUT a concept is not the concept's definition; a corollary is not the theorem.

Output one JSON object per item, one per line, exactly:
{"item_id": "...", "pick": "<cid or none>", "confidence": 0.0-1.0, "reason": "<one short sentence>"}
No commentary. Do not read any files or the web.

"""
K = 25
for k in range(0, len(items), K):
    body = PROMPT
    for it in items[k:k+K]:
        body += f"\n=== ITEM {it['item_id']} === name: \"{it['name']}\" (kind: {it.get('kind')})\n"
        for c in it["candidates"]:
            body += f"  [{c['cid']}] ({c['kind']}) {c['name']} :: {c['text']}\n"
    (OUT / "tasks" / f"rl-{k//K:03d}.txt").write_text(body, encoding="utf-8")
kinds = Counter(it.get("kind") for it in items[:n_real])
print(f"reader names: {len(by_name)} distinct; with candidates: {n_real}; +20 decoys; tasks: {len(list((OUT/'tasks').glob('*.txt')))}; kinds: {dict(kinds)}")
