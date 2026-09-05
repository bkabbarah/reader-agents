#!/usr/bin/env python3
"""compare_pdf_latex.py - measure PDF chunking against LaTeX-parse ground truth for the same book.
Aligns PDF statement blocks to LaTeX statement instances by normalized-token similarity (LaTeX macros
stripped), then reports statement detection precision/recall, kind agreement, and proof-attachment
agreement. usage: compare_pdf_latex.py <blocks.jsonl> <glob-of-latex-instances> <glob-of-latex-proofs>"""
import json, re, sys, glob
from collections import Counter

def load(p): return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
def strip_tex(s):
    s = re.sub(r"\\(emph|myindex|textbf|textit|label|index)\{([^}]*)\}", r"\2", s or "")
    s = re.sub(r"\\[a-zA-Z]+\*?", " ", s)
    s = re.sub(r"[{}$\\^_&%~]", " ", s)
    return s
import unicodedata
def toks(s):
    # robust to PyMuPDF's dropped spaces and Unicode math-italic glyphs: NFKC-fold, strip everything but
    # letters/digits, compare whitespace-free character 4-grams
    s = unicodedata.normalize("NFKC", strip_tex(s)).lower()
    s = re.sub(r"[^a-z0-9]+", "", s)
    return {s[i:i+4] for i in range(max(len(s) - 3, 0))}
def jac(a, b): return len(a & b) / min(len(a), len(b)) if (a and b) else 0.0   # containment: robust to span-length mismatch

blocks = load(sys.argv[1])
extra = glob.glob("data/prototype/instances.jsonl") if "lebl" in sys.argv[2] else []   # Lebl's prototype chapter lives apart
truth = [r for f in (glob.glob(sys.argv[2]) + extra) for r in load(f) if r.get("kind_as_labeled") in ("theorem","lemma","proposition","corollary","definition")]
proofs_by = {}
for f in glob.glob(sys.argv[3]) + (glob.glob("data/prototype/proofs.jsonl") if "lebl" in sys.argv[3] else []):
    for p in load(f):
        proofs_by.setdefault(p["proves"], []).append(p)
tt = [(r, toks(r.get("statement_text") or "")) for r in truth]
bt = [(b, toks(b["statement_text"])) for b in blocks]
matched_b, matched_t, kind_ok, proof_agree, proof_tot = 0, set(), 0, 0, 0
low = []
for b, bt_ in bt:
    best, bj = None, 0.0
    for i, (r, t_) in enumerate(tt):
        j = jac(bt_, t_)
        if j > bj: best, bj = i, j
    if best is not None and bj >= 0.5:
        matched_b += 1; matched_t.add(best); r = tt[best][0]
        kind_ok += (r["kind_as_labeled"] == b["kind"])
        if r["kind_as_labeled"] != "definition":
            proof_tot += 1
            truth_has = bool(proofs_by.get(r["instance_id"]))
            proof_agree += (truth_has == bool(b["proof_text"]))
    else:
        low.append((b["kind"], b["label"], b["page"], round(bj, 2), b["statement_text"][:70]))
print(f"PDF blocks {len(blocks)} | LaTeX truth statements {len(truth)}")
print(f"statement precision: {matched_b}/{len(blocks)} = {matched_b/len(blocks):.0%}  (PDF blocks matching a truth statement, containment>=0.5)")
print(f"statement recall:    {len(matched_t)}/{len(truth)} = {len(matched_t)/len(truth):.0%}  (truth statements found by the PDF path)")
print(f"kind agreement on matches: {kind_ok}/{matched_b} = {kind_ok/max(matched_b,1):.0%}")
print(f"proof-attachment agreement (theorem-like matches): {proof_agree}/{proof_tot} = {proof_agree/max(proof_tot,1):.0%}")
print("unmatched PDF blocks (first 12):")
for x in low[:12]: print("  ", x)
