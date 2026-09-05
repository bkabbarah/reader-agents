#!/usr/bin/env python3
"""prep_reader_pass.py - build reader-protocol extraction tasks (the recall fix).
The reader lists every prior result / substantive definition a proof relies on, with an evidence
quote, explicit|implicit, kind, confidence. Output becomes a separately-flagged reference layer
(provenance reader-inferred), never replacing the explicit-ref layer.
usage: prep_reader_pass.py trench   -> data/extracted/trench-ra/reader_tasks/
       prep_reader_pass.py slice    -> data/audit/recall-v1/reader_tasks/  (the 30 audited proofs, for recall re-measure)
"""
import json, os, sys
from pathlib import Path

ROOT = Path(__file__).parent
mode = sys.argv[1]
PROMPT = """You are extracting the INGREDIENTS of mathematical proofs for a dependency graph. For each proof below, list every prior result the proof relies on - named theorems/lemmas/propositions/corollaries it invokes explicitly OR by an unmistakable implicit appeal (e.g. "since the set is compact and f continuous, f is bounded" = the extreme value theorem) - and every DEFINITION or CONCEPT whose content the argument actually uses (uniform convergence, completeness), not mere vocabulary. Exclude proof techniques (contradiction, WLOG, induction-as-technique), restatements of the hypotheses, and background arithmetic/order facts about the reals. Criterion: include it if it is a result or concept that at some point in history did not yet exist. Be exhaustive within that criterion; mark borderline items with lower confidence. Use the standard name of the result when one exists. If the proof defers to another work by citation (e.g. "See [111, I.5.1]" or "[233, Chapter X, Proposition 3]"), list each citation as an ingredient with kind "cited-document", name = the citation text exactly as written, how = "explicit"; a proof that only says "follows from the previous result" lists that result.

Output ONE JSON object per proof, one per line, exactly:
{"proof_id": "...", "ingredients": [{"name": "<standard name or short description>", "kind": "theorem|lemma|corollary|proposition|definition|axiom|principle|cited-document", "how": "explicit|implicit", "confidence": 0.0-1.0, "evidence": "<short quote from the proof>"}]}

No commentary. Do not consult any files or the web - judge from the text below only.

"""
def load_jsonl(p): return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]

if mode == "trench":
    D = ROOT / "data/extracted/trench-ra"
    inst = {r["instance_id"]: r for r in load_jsonl(D / "instances.jsonl")}
    items = [{"proof_id": p["proof_id"], "statement_name": inst[p["proves"]].get("local_name") or inst[p["proves"]]["local_label"],
              "statement_text": inst[p["proves"]]["statement_text"], "proof_text": p["proof_text"]}
             for p in load_jsonl(D / "proofs.jsonl") if not p["proves"].startswith("inst:trench-ra:example")]
    OUT = D / "reader_tasks"
elif mode == "corpus":
    # every proof with text across the original 5-source corpus (Lebl chapters, ProofWiki, papers)
    import glob
    items = []
    for pf in glob.glob(str(ROOT / "data/extracted/lebl-ba1/*/proofs.jsonl")) + \
              glob.glob(str(ROOT / "data/extracted/proofwiki/*/proofs.jsonl")) + \
              glob.glob(str(ROOT / "data/extracted/papers/*/proofs.jsonl")):
        d = Path(pf).parent
        inst = {r["instance_id"]: r for r in load_jsonl(d / "instances.jsonl")}
        for p in load_jsonl(pf):
            if p.get("proof_text") and len(p["proof_text"]) > 80 and p.get("proves") in inst:
                s = inst[p["proves"]]
                items.append({"proof_id": p["proof_id"], "statement_name": s.get("local_name") or s.get("local_label") or s["instance_id"],
                              "statement_text": s.get("statement_text") or "", "proof_text": p["proof_text"]})
    OUT = ROOT / "data/extracted/_reader_corpus/reader_tasks"
elif mode.startswith("batch0"):
    # batch-0 textbooks: PDF-chunked blocks (data/extracted/batch0/<slug>/blocks.jsonl); optional slug filter batch0:<slug>
    import glob
    slug = mode.split(":", 1)[1] if ":" in mode else "*"
    items = []
    # prefer the math-aware (Nougat) blocks when a book has them; fall back to the PDF text-layer blocks
    files = glob.glob(str(ROOT / f"data/extracted/batch0/{slug}/blocks_nougat.jsonl"))
    have = {os.path.dirname(f) for f in files}
    files += [f for f in glob.glob(str(ROOT / f"data/extracted/batch0/{slug}/blocks.jsonl")) if os.path.dirname(f) not in have]
    for bf in files:
        book = Path(bf).parent.name
        for i, b in enumerate(load_jsonl(bf)):
            if b.get("proof_text"):   # no length floor: "See [111, I.5.1]" is a cited-document reference, the cleanest ingredient there is
                items.append({"proof_id": f"prf:{book}:{b['kind']}:{b['label']}", "statement_name": f"{b['kind'].title()} {b['label']} ({book})",
                              "statement_text": b["statement_text"], "proof_text": b["proof_text"]})
    OUT = ROOT / f"data/extracted/batch0/_reader_tasks" / (slug if slug != "*" else "all")
else:
    D = ROOT / "data/audit/recall-v1"
    items = json.loads((D / "sample.json").read_text(encoding="utf-8"))["sample"]
    OUT = D / "reader_tasks"
OUT.mkdir(parents=True, exist_ok=True)
K = 5
for k in range(0, len(items), K):
    body = PROMPT
    for s in items[k:k+K]:
        body += f"\n=== PROOF {s['proof_id']} ===\nSTATEMENT ({s['statement_name']}): {s['statement_text'][:1500]}\nPROOF: {s['proof_text'][:6000]}\n"
    (OUT / f"read-{k//K:03d}.txt").write_text(body, encoding="utf-8")
print(f"{mode}: {len(items)} proofs -> {len(list(OUT.glob('*.txt')))} tasks in {OUT}")
