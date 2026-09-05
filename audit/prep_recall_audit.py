#!/usr/bin/env python3
"""prep_recall_audit.py - gold-slice recall audit, stage 0 (deterministic prep).

Question: what fraction of a proof's true ingredients did the extraction fleet capture?
Design:
- Sample 30 proofs with proof text across sources (Lebl 15 / ProofWiki 10 / papers 5),
  uniformly over proofs WITH text regardless of how many uses the fleet extracted
  (zero-edge proofs must be in the sample - omission is the question).
- Enumerators (2 independent, blind to fleet output) list every result/definition the
  proof relies on. Human anchor: 5 of the 30 are flagged for Bashar's hand-check.
- Stage 2 (matcher) later compares enumerated ingredients vs fleet uses[] per proof.
Outputs to <outdir>: tasks/enum-<A|B>-<k>.txt prompts (5 proofs each), truth/fleet_uses.json
(what the fleet extracted - NEVER staged where enumerators can read it), sample.json.
"""
import json, os, random, sys, glob
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]      # repo root (scripts live one folder down)
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "audit" / "recall-v1"
(OUT / "tasks").mkdir(parents=True, exist_ok=True)
(OUT / "truth").mkdir(parents=True, exist_ok=True)
random.seed(20260902)

def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]

def load_source(pattern):
    proofs, insts = [], {}
    for pf in glob.glob(str(ROOT / pattern)):
        d = Path(pf).parent
        for r in load_jsonl(d / "instances.jsonl"):
            insts[r["instance_id"]] = r
        for p in load_jsonl(pf):
            if p.get("proof_text") and len(p["proof_text"]) > 120 and p.get("proves") in insts:
                proofs.append(p)
    return proofs, insts

MODE = sys.argv[2] if len(sys.argv) > 2 else "corpus"
sample, fleet = [], {}
if MODE == "batch0":
    # recall-v2: batch-0 textbooks on Nougat text. 5 proofs per book (30), uniformly over proofs with >120 chars.
    # "fleet" truth = the reader's ingredient list from _reader_out_nougat (never staged with the tasks).
    reader = {}
    for f in glob.glob(str(ROOT / "data/extracted/batch0/_reader_out_nougat/*.txt")):
        for r in load_jsonl(f):
            reader[r["proof_id"]] = [{"name": g.get("name"), "kind": g.get("kind"), "how": g.get("how"),
                                      "confidence": g.get("confidence"), "provenance": "reader"} for g in r.get("ingredients", [])]
    quota = {}
    for bf in sorted(glob.glob(str(ROOT / "data/extracted/batch0/*/blocks_nougat.jsonl"))):
        book = Path(bf).parent.name
        proofs = [b for b in load_jsonl(bf) if b.get("proof_text") and len(b["proof_text"]) > 120 and b["kind"] != "exercise"]
        quota[book] = 5
        for b in random.sample(proofs, min(5, len(proofs))):
            pid = f"prf:{book}:{b['kind']}:{b['label']}"
            sample.append({"proof_id": pid, "source": book, "statement_name": f"{b['kind'].title()} {b['label']} ({book})",
                           "statement_text": b["statement_text"], "proof_text": b["proof_text"]})
            fleet[pid] = reader.get(pid, [])
else:
    pools = {
        "lebl": load_source("data/extracted/lebl-ba1/*/proofs.jsonl"),
        "proofwiki": load_source("data/extracted/proofwiki/*/proofs.jsonl"),
        "papers": load_source("data/extracted/papers/*/proofs.jsonl"),
    }
    quota = {"lebl": 15, "proofwiki": 10, "papers": 5}
    for src, (proofs, insts) in pools.items():
        picks = random.sample(proofs, min(quota[src], len(proofs)))
        for p in picks:
            st = insts[p["proves"]]
            uses = [{"target_kind": u.get("target_kind"), "target": u.get("target"), "name": u.get("name") or u.get("raw_label"),
                     "target_name": (insts.get(u.get("target")) or {}).get("local_name") or (insts.get(u.get("target")) or {}).get("local_label"),
                     "provenance": u.get("provenance"), "confidence": u.get("confidence")} for u in p.get("uses", [])]
            sample.append({"proof_id": p["proof_id"], "source": src, "statement_name": st.get("local_name") or st.get("local_label") or st["instance_id"],
                           "statement_text": st.get("statement_text") or "", "proof_text": p["proof_text"]})
            fleet[p["proof_id"]] = uses
random.shuffle(sample)
human = {s["proof_id"] for s in random.sample(sample, 5)}
json.dump({"sample": [{**s, "human_anchor": s["proof_id"] in human} for s in sample]}, open(OUT / "sample.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(fleet, open(OUT / "truth" / "fleet_uses.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

PROMPT = """You are an expert mathematician auditing a proof's INGREDIENTS. For each proof below, list EVERY prior result the proof relies on: named theorems/lemmas/propositions it invokes (explicitly or by an unmistakable implicit appeal such as "by compactness"), and DEFINITIONS whose content the argument actually uses (not mere vocabulary). Do NOT list proof techniques (contradiction, induction as a technique, WLOG) - but DO list a specific principle if invoked as a result (e.g. the well-ordering principle). Be exhaustive; missing an ingredient is worse than including a borderline one, but mark borderline ones with lower confidence.

Output ONE JSON object per proof, one per line, exactly:
{"proof_id": "...", "ingredients": [{"name": "<standard name or short description>", "kind": "theorem|lemma|definition|axiom|principle", "how": "explicit|implicit", "confidence": 0.0-1.0, "evidence": "<short quote from the proof>"}]}

No commentary. Do not consult any files or the web - judge from the text below only.

"""
K = 5
for tag in ("A", "B"):
    order = sample[:] if tag == "A" else sample[::-1]   # different order per enumerator
    for k in range(0, len(order), K):
        chunk = order[k:k+K]
        body = PROMPT
        for s in chunk:
            body += f"\n=== PROOF {s['proof_id']} ===\nSTATEMENT ({s['statement_name']}): {s['statement_text'][:1500]}\nPROOF: {s['proof_text'][:6000]}\n"
        (OUT / "tasks" / f"enum-{tag}-{k//K:02d}.txt").write_text(body, encoding="utf-8")
print(f"sample={len(sample)} (human anchors={len(human)}); tasks={len(list((OUT/'tasks').glob('*.txt')))} -> {OUT}")
print("per-source:", {s: sum(1 for x in sample if x["source"] == s) for s in quota})
print("zero-use proofs in sample:", sum(1 for pid, u in fleet.items() if not u))
