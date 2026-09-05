# Fusion pass step 0 (deterministic, free): candidate generation
# harvest dated names x NaturalProofs titles x current canonicals -> tiered match queues
import json, re, sys, unicodedata
from pathlib import Path
from collections import defaultdict

ROOT = Path(r"C:\Users\kabba\Desktop\rsireasoner")
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "linking" / "fusion_candidates.jsonl"

STOP = {"the", "a", "an", "of", "for", "on", "in", "s"}
KINDW = {"theorem", "theorems", "lemma", "conjecture", "law", "formula", "identity",
         "inequality", "principle", "rule", "test", "criterion", "paradox", "problem"}

def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("\u2013", "-").replace("\u2014", "-").replace("'", "")
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    toks = [t for t in s.split() if t not in STOP]
    return " ".join(toks)

def core(name: str) -> str:  # also drop kind words: "bolzano weierstrass theorem" -> "bolzano weierstrass"
    return " ".join(t for t in norm(name).split() if t not in KINDW)

def load_jsonl(p):
    with open(p, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

harvest = load_jsonl(ROOT / "data/dates/harvest/consolidated/instances.jsonl")
events = load_jsonl(ROOT / "data/dates/harvest/consolidated/events.jsonl")
np_inst = load_jsonl(ROOT / "data/extracted/naturalproofs/instances.jsonl")
graph = json.loads((ROOT / "data/build/graph.json").read_text(encoding="utf-8"))

# events keyed by slug; harvest instance ids are inst:wikipedia:<slug>
dated_ids = {f"inst:wikipedia:{e['slug']}" for e in events if e.get("events")}

h_by_norm, h_by_core = defaultdict(list), defaultdict(list)
n_dated = 0
for h in harvest:
    nm = h.get("local_name") or ""
    if not nm:
        continue
    if h["instance_id"] in dated_ids:
        n_dated += 1
    h_by_norm[norm(nm)].append(h["instance_id"])
    h_by_core[core(nm)].append(h["instance_id"])

def match(name):
    n, c = norm(name), core(name)
    if n and n in h_by_norm:
        return "exact", h_by_norm[n]
    if c and c in h_by_core:
        return "core", h_by_core[c]
    return None, None

rows, tiers = [], defaultdict(int)
np_titles = {i["instance_id"]: i.get("local_name") or "" for i in np_inst}
for iid, title in np_titles.items():
    tier, targets = match(title)
    if tier:
        tiers[f"np-{tier}"] += 1
        for t in targets:
            rows.append({"relation": "harvest-date-link", "from": iid, "to": t,
                         "tier": tier, "np_title": title, "dated": t in dated_ids})

canon_hits = 0
for node in graph.get("nodes", []):
    nm = node.get("ename") or node.get("preferred_name") or ""
    if not nm:
        continue
    tier, targets = match(nm)
    if tier:
        canon_hits += 1
        for t in targets:
            rows.append({"relation": "harvest-date-link", "from": node.get("id") or node.get("canonical_id"),
                         "tier": tier, "to": t, "canon_name": nm, "dated": t in dated_ids})

dated_rows = sum(1 for r in rows if r["dated"])
print(f"harvest named: {len(h_by_norm)} distinct norms ({n_dated} dated instances)")
print(f"NP titles matched: exact={tiers['np-exact']} core={tiers['np-core']} of {len(np_titles)}")
print(f"canonical nodes matched: {canon_hits} of {len(graph.get('nodes', []))}")
print(f"candidate rows: {len(rows)} ({dated_rows} pointing at a DATED harvest result)")

with open(OUT, "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"wrote {OUT}")
