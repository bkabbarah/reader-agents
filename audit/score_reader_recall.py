#!/usr/bin/env python3
"""score_reader_recall.py - re-measure recall with the READER extraction on the same 30-proof
audit slice. Converts reader output into the 'fleet uses' shape, then reuses the matching-stage
prep so the same judge protocol compares reader-extracted ingredients vs auditor enumerations.
Step 1 (this script, deterministic): data/audit/recall-v1/reader_out/*.txt -> truth/reader_uses.json
                                     + match_tasks_reader/*.txt
Step 2: run match_tasks_reader on the fleet -> match_out_reader/
Step 3: python score_recall.py --reader   (reads match_out_reader + reader_uses)
"""
import os, json, glob, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]      # repo root (scripts live one folder down)
D = ROOT / os.environ.get("RECALL_DIR", "data/audit/recall-v1")   # recall-v2-batch0 via RECALL_DIR
sample = {s["proof_id"]: s for s in json.loads((D / "sample.json").read_text(encoding="utf-8"))["sample"]}
merged = json.loads((D / "enumerated_merged.json").read_text(encoding="utf-8"))
reader = {}
for f in glob.glob(str(D / "reader_out/*.txt")):
    for line in open(f, encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            if r["proof_id"] in sample:
                reader[r["proof_id"]] = [{"target_kind": "named-unresolved", "target": None, "name": i["name"],
                                          "target_name": None, "provenance": "reader-" + i.get("how", "implicit"),
                                          "confidence": i.get("confidence")} for i in r.get("ingredients", [])]
json.dump(reader, open(D / "truth/reader_uses.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
missing = [p for p in sample if p not in reader]
print(f"reader outputs for {len(reader)}/{len(sample)} proofs (missing {len(missing)}); refs total {sum(len(v) for v in reader.values())}")

PROMPT = open(ROOT / "prep_recall_match.py", encoding="utf-8").read().split('PROMPT = """')[1].split('"""')[0]
(D / "match_tasks_reader").mkdir(exist_ok=True)
pids = list(sample); K = 5
for k in range(0, len(pids), K):
    body = PROMPT
    for pid in pids[k:k+K]:
        s = sample[pid]
        body += f"\n=== PROOF {pid} === ({s['statement_name']})\nSTATEMENT: {s['statement_text'][:800]}\nPROOF (excerpt): {s['proof_text'][:2500]}\nE (enumerated):\n"
        for x in merged[pid]:
            body += f"  {x['eid']} [{x['by']}] ({x['kind']}, {x['how']}) {x['name']}\n"
        body += "F (extractor recorded):\n"
        if not reader.get(pid):
            body += "  (nothing - extractor recorded zero references)\n"
        for j, u in enumerate(reader.get(pid, [])):
            body += f"  F{j}: kind={u['target_kind']} name={u['name']} prov={u['provenance']}\n"
    (D / "match_tasks_reader" / f"match-{k//K:02d}.txt").write_text(body, encoding="utf-8")
print(f"match tasks -> {D/'match_tasks_reader'}")
