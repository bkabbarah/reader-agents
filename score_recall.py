#!/usr/bin/env python3
"""score_recall.py - recall audit stage 3: numbers + report.
recall_union     = enumerated ingredients (deduped) captured by the fleet / all enumerated
recall_consensus = same, restricted to ingredients BOTH blind auditors listed (harder to dispute)
precision        = fleet refs judged legitimate / fleet refs
Writes data/audit/recall-v1/RECALL-REPORT.md incl. the 5 human-anchor proofs for Bashar."""
import os, json, glob, math
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).parent
D = ROOT / os.environ.get("RECALL_DIR", "data/audit/recall-v1")   # recall-v2-batch0 via RECALL_DIR
import sys
READER = "--reader" in sys.argv   # score the reader-protocol extraction instead of the original fleet
sample = {s["proof_id"]: s for s in json.loads((D / "sample.json").read_text(encoding="utf-8"))["sample"]}
merged = json.loads((D / "enumerated_merged.json").read_text(encoding="utf-8"))
fleet = json.loads((D / ("truth/reader_uses.json" if READER else "truth/fleet_uses.json")).read_text(encoding="utf-8"))
match = {}
for f in glob.glob(str(D / ("match_out_reader/*.txt" if READER else "match_out/*.txt"))):
    for line in open(f, encoding="utf-8"):
        if line.strip():
            r = json.loads(line); match[r["proof_id"]] = r

def wilson(k, n, z=1.96):
    if n == 0: return (0, 0)
    p = k / n; d = 1 + z*z/n; c = p + z*z/(2*n); h = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))
    return ((c-h)/d, (c+h)/d)

tot = defaultdict(lambda: [0, 0])  # key -> [captured, total]
prec = [0, 0]
per_proof = []
for pid, m in match.items():
    dups = set(m.get("duplicates", {}).keys())
    ents = [x for x in merged[pid] if x["eid"] not in dups]
    cap = m.get("captured", {})
    c_u = sum(1 for x in ents if cap.get(x["eid"]) not in (None, "null", ""))
    cons = [x for x in ents if x["by"] == "AB"]
    c_c = sum(1 for x in cons if cap.get(x["eid"]) not in (None, "null", ""))
    src = sample[pid]["source"]
    for key in ("all", src, "zero-edge" if not fleet.get(pid) else "has-edges"):
        tot[key][0] += c_u; tot[key][1] += len(ents)
    tot["consensus"][0] += c_c; tot["consensus"][1] += len(cons)
    fl = m.get("f_legit", {})
    for j in range(len(fleet.get(pid, []))):
        prec[1] += 1; prec[0] += 1 if fl.get(f"F{j}") is True else 0
    per_proof.append((pid, src, len(ents), c_u, len(fleet.get(pid, [])), sample[pid]["human_anchor"]))

SOURCES = sorted({s["source"] for s in sample.values()})
src_desc = " / ".join(f"{s} {sum(1 for x in sample.values() if x['source'] == s)}" for s in SOURCES)
n_zero = sum(1 for pid in sample if not fleet.get(pid))
title = ("# Extraction recall audit — READER protocol (2026-09-02)\n" if READER
         else f"# Extraction recall audit — {os.path.basename(str(D))}\n")
lines = [title,
         f"{len(sample)} proofs ({src_desc}), incl. {n_zero} the extraction returned zero references for. Two blind Opus auditors enumerated ingredients; a third judge matched enumerations against the extraction output. Ground truth is MODEL-CONSENSUS until the human-anchor proofs below are checked by Bashar. n is small: Wilson 95% intervals given.\n",
         "| metric | captured / total | rate | 95% CI |", "|---|---|---|---|"]
for key in ("all", "consensus", *SOURCES, "has-edges", "zero-edge"):
    k, n = tot[key]; lo, hi = wilson(k, n)
    lines.append(f"| recall ({key}) | {k}/{n} | {k/n:.0%} | {lo:.0%}–{hi:.0%} |" if n else f"| recall ({key}) | 0/0 | – | – |")
k, n = prec; lo, hi = wilson(k, n)
lines.append(f"| precision (fleet refs legit) | {k}/{n} | {k/n:.0%} | {lo:.0%}–{hi:.0%} |")
lines += ["\n## Per proof (enumerated / captured / fleet refs)", "| proof | src | enumerated | captured | fleet refs | human anchor |", "|---|---|---|---|---|---|"]
for pid, src, ne, cu, nf, h in sorted(per_proof, key=lambda r: (r[3]/max(r[2],1))):
    lines.append(f"| {pid} | {src} | {ne} | {cu} | {nf} | {'**YES**' if h else ''} |")
lines += ["\n## Human-anchor proofs (Bashar: ~2 min each — does the enumerated list look right, and is 'captured' fair?)"]
for pid, src, ne, cu, nf, h in per_proof:
    if not h: continue
    m = match[pid]; cap = m.get("captured", {})
    lines.append(f"\n### {pid} — {sample[pid]['statement_name']} ({src})")
    for x in merged[pid]:
        if x["eid"] in m.get("duplicates", {}): continue
        lines.append(f"- [{x['by']}] {x['name']} → {'captured (' + str(cap.get(x['eid'])) + ')' if cap.get(x['eid']) not in (None,'null','') else 'MISSED'}")
    lines.append(f"- fleet refs: {[ (u.get('name') or u.get('target_name') or u.get('target')) for u in fleet.get(pid, [])]}")
(D / ("RECALL-REPORT-reader.md" if READER else "RECALL-REPORT.md")).write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines[:12]))
