#!/usr/bin/env python3
"""prep_recall_match.py - recall audit stage 2 prep: per proof, the union of the two
blind enumerations (with agreement flags) vs what the fleet extracted; a judge decides
which enumerated ingredients the fleet captured and which fleet uses are legitimate.
Yields recall (consensus + union) and precision. Tasks -> data/audit/recall-v1/match_tasks/"""
import os, json, glob, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]      # repo root (scripts live one folder down)
D = ROOT / os.environ.get("RECALL_DIR", "data/audit/recall-v1")   # recall-v2-batch0 via RECALL_DIR
(D / "match_tasks").mkdir(exist_ok=True)
sample = {s["proof_id"]: s for s in json.loads((D / "sample.json").read_text(encoding="utf-8"))["sample"]}
fleet = json.loads((D / "truth/fleet_uses.json").read_text(encoding="utf-8"))
enum = {pid: {"A": [], "B": []} for pid in sample}
for f in glob.glob(str(D / "out/enum-*.txt")):
    tag = Path(f).name.split("-")[1]
    for line in open(f, encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            if r["proof_id"] in enum:
                enum[r["proof_id"]][tag] = r.get("ingredients", [])

def norm(s): return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()

merged = {}
for pid, ab in enum.items():
    items = []
    for tag in ("A", "B"):
        for ing in ab[tag]:
            key = norm(ing["name"])[:60]
            hit = next((x for x in items if x["key"] == key), None)
            if hit: hit["by"].add(tag)
            else: items.append({"key": key, "name": ing["name"], "kind": ing.get("kind"), "how": ing.get("how"), "conf": ing.get("confidence"), "by": {tag}})
    merged[pid] = [{**x, "eid": f"e{i}", "by": "".join(sorted(x["by"]))} for i, x in enumerate(items)]
json.dump(merged, open(D / "enumerated_merged.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

PROMPT = """You are auditing an extraction pipeline. For each proof: list E = ingredients enumerated by independent expert auditors (each tagged by which auditor(s) listed it: A, B, or AB), and list F = what the automated extractor recorded as the proof's ingredient references. Decide, per enumerated ingredient, whether the extractor CAPTURED it (an F entry denotes the same result/definition, even if named differently or recorded as an unresolved name), and per F entry whether it is a LEGITIMATE ingredient of this proof at all.
Note: near-duplicate E entries (same thing named twice by the two auditors) should be marked as duplicates of the earlier eid rather than judged separately.

Output one JSON object per proof, one per line, exactly:
{"proof_id": "...", "captured": {"<eid>": "<F index or null>", ...}, "duplicates": {"<eid>": "<earlier eid>"}, "f_legit": {"<F index>": true|false}, "notes": "<optional short>"}
No commentary. Do not read files or the web.

"""
pids = list(sample)
K = 5
for k in range(0, len(pids), K):
    body = PROMPT
    for pid in pids[k:k+K]:
        s = sample[pid]
        body += f"\n=== PROOF {pid} === ({s['statement_name']})\nSTATEMENT: {s['statement_text'][:800]}\nPROOF (excerpt): {s['proof_text'][:2500]}\nE (enumerated):\n"
        for x in merged[pid]:
            body += f"  {x['eid']} [{x['by']}] ({x['kind']}, {x['how']}) {x['name']}\n"
        body += "F (extractor recorded):\n"
        if not fleet.get(pid):
            body += "  (nothing - extractor recorded zero references)\n"
        for j, u in enumerate(fleet.get(pid, [])):
            body += f"  F{j}: kind={u.get('target_kind') or u.get('kind')} name={u.get('name') or u.get('target_name') or u.get('target')} prov={u.get('provenance')}\n"
    (D / "match_tasks" / f"match-{k//K:02d}.txt").write_text(body, encoding="utf-8")
n_e = sum(len(v) for v in merged.values()); n_ab = sum(1 for v in merged.values() for x in v if x["by"] == "AB")
print(f"proofs {len(merged)}; enumerated ingredients {n_e} (both-auditor consensus {n_ab}); fleet refs {sum(len(v) for v in fleet.values())}; tasks {len(list((D/'match_tasks').glob('*.txt')))}")
