#!/usr/bin/env python3
"""parse_trench.py - deterministic structural parse of Trench, Introduction to Real Analysis
(corpus/trench-ra/TRENCH_REAL_ANALYSIS.tex, CC BY-NC-SA 3.0) into schema v0.4 instances.
No LLM. Emits: statement_instances (theorem/lemma/corollary/definition + examples as worked-example),
proof_instances (\\proof ... \\bbox attached to the preceding statement) whose uses[] hold ONLY the
explicit \\ref{thmtype:...} references (the NaturalProofs-style layer, provenance explicit-reference).
The reader layer (implicit ingredients) is added separately by the reader pass.
Outputs: data/extracted/trench-ra/{instances.jsonl, proofs.jsonl, source_doc.json, PARSE-REPORT.md}
"""
import json, re, hashlib
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]      # repo root (scripts live one folder down)
SRC = ROOT / "corpus/trench-ra/TRENCH_REAL_ANALYSIS.tex"
OUT = ROOT / "data/extracted/trench-ra"
OUT.mkdir(parents=True, exist_ok=True)
DOC = "trench-ra"
tex = SRC.read_text(encoding="utf-8", errors="replace")

ENV = re.compile(r"\\begin\{(theorem|lemma|corollary|definition|example)\}\s*(?:\[([^\]]*)\])?\s*(?:\\label\{([^}]*)\})?(.*?)\\end\{\1\}", re.S)
# a proof runs from \proof to its \bbox — or, when the \bbox is missing (16 cases), to the next
# statement environment / next \proof, so one unterminated proof cannot swallow its successor
PROOF = re.compile(r"\\proof\b(.*?)(?=\\bbox|\\begin\{(?:theorem|lemma|corollary|definition|example)\}|\\proof\b)", re.S)
REF = re.compile(r"\\ref\{(thmtype|example):([^}]*)\}")
CHAP = re.compile(r"\\setcounter\{chapter\}\{(\d+)\}")
SECT = re.compile(r"\\sectiontitle\{([^}]*)\}")

def pos_map(pattern):
    return [(m.start(), m.group(1)) for m in pattern.finditer(tex)]
chapters, sections = pos_map(CHAP), pos_map(SECT)
def at(pos, table, default=None):
    cur = default
    for p, v in table:
        if p <= pos: cur = v
        else: break
    return cur
def clean(s): return re.sub(r"[ \t]+", " ", s.strip())
HREF = re.compile(r"\\href\{([^}]*)\}\s*\{([^}]*)\}", re.S)
def split_name(name):
    """'\\href{old-mactutor-url}{Archimedean} Property' -> ('Archimedean Property', [fixed url]).
    Trench (2013) links eponyms to MacTutor's old domain, which moved in 2020; rewrite so links resolve."""
    links = []
    def sub(m):
        url = m.group(1).replace("http://www-history.mcs.st-and.ac.uk/Mathematicians/", "https://mathshistory.st-andrews.ac.uk/Biographies/").replace(".html", "/")
        links.append(url); return m.group(2)
    return clean(HREF.sub(sub, name)), links

stmts, proofs, report = [], [], Counter()
label_to_id = {}
for m in ENV.finditer(tex):
    kind, name, label, body = m.group(1), m.group(2), m.group(3), m.group(4)
    if not label:
        lm = re.search(r"\\label\{([^}]*)\}", body)
        label = lm.group(1) if lm else None
    local = label.split(":", 1)[1] if label and ":" in label else (label or "h" + hashlib.sha1(body.encode()).hexdigest()[:8])
    iid = f"inst:{DOC}:{kind}:{local}"
    label_to_id[label] = iid
    role = "worked-example" if kind == "example" else "main"
    name_clean, eponym_links = split_name(name) if name else (None, [])
    if eponym_links: report["eponym_links"] += len(eponym_links)
    stmts.append({
        "meta": {"eponym_links": eponym_links} if eponym_links else None,
        "instance_id": iid, "_pos": m.end(),
        "source": {"doc": DOC, "locator": f"ch{at(m.start(), chapters, '?')} §{at(m.start(), sections, '?')} {kind} {local}",
                   "char_span": [m.start(), m.end()]},
        "kind_as_labeled": kind, "role": role,
        "statement_text": clean(re.sub(r"\\label\{[^}]*\}", "", body)),
        "local_name": name_clean, "local_label": local, "names": None,
        "proof_status": "omitted",
        "extraction": {"method": "rule", "model": None, "prompt_version": "trench-parse-v1", "confidence": 1.0},
        "schema_version": "0.4"})
    report[kind] += 1

# attach each \proof...\bbox to the nearest preceding statement (if no other statement starts in between)
starts = sorted((s["_pos"], i) for i, s in enumerate(stmts))
for pm in PROOF.finditer(tex):
    prev = None
    for p, i in starts:
        if p <= pm.start(): prev = i
        else: break
    if prev is None: report["orphan_proofs"] += 1; continue
    nxt = next((p for p, _ in starts if p > stmts[prev]["_pos"]), None)
    if nxt is not None and nxt < pm.start():
        report["orphan_proofs"] += 1; continue
    s = stmts[prev]
    if s["proof_status"] == "proof-env": report["extra_proofs"] += 1
    s["proof_status"] = "proof-env"
    body = pm.group(1)
    uses = []
    for r in REF.finditer(body):
        lab = f"{r.group(1)}:{r.group(2)}"
        tgt = label_to_id.get(lab)
        uses.append({"target_kind": "resolved-instance" if tgt else "resolved-label", "target": tgt,
                     "raw_label": lab, "provenance": "explicit-reference", "confidence": 0.97})
    k = sum(1 for p in proofs if p["proves"] == s["instance_id"])
    proofs.append({"proof_id": f"prf:{DOC}:{s['local_label']}" + (f"-{k}" if k else ""), "proves": s["instance_id"],
                   "source": {"doc": DOC, "char_span": [pm.start(), pm.end()]},
                   "proof_text": clean(body), "presentation": "proof-env", "uses": uses,
                   "extraction": {"method": "rule", "prompt_version": "trench-parse-v1", "confidence": 1.0}, "schema_version": "0.4"})
for s in stmts: s.pop("_pos")
with open(OUT / "instances.jsonl", "w", encoding="utf-8") as f:
    for s in stmts: f.write(json.dumps(s, ensure_ascii=False) + "\n")
with open(OUT / "proofs.jsonl", "w", encoding="utf-8") as f:
    for p in proofs: f.write(json.dumps(p, ensure_ascii=False) + "\n")
json.dump({"doc_slug": DOC, "title": "Introduction to Real Analysis", "authors": ["William F. Trench"], "doc_kind": "textbook",
           "published": {"min": 2013, "max": 2013}, "license": "CC BY-NC-SA 3.0", "license_verified": True,
           "acquisition": "manual download by Bashar 2026-09-02, digitalcommons.trinity.edu/mono/7", "raw_stored_at": "corpus/trench-ra/"},
          open(OUT / "source_doc.json", "w", encoding="utf-8"), indent=1)
n_uses = sum(len(p["uses"]) for p in proofs); n_res = sum(1 for p in proofs for u in p["uses"] if u["target"])
main_proofs = [p for p in proofs if not p["proves"].startswith(f"inst:{DOC}:example")]
ps = Counter(s["proof_status"] for s in stmts if s["kind_as_labeled"] in ("theorem", "lemma", "corollary"))
rep = f"""# Trench parse report (trench-parse-v1, deterministic) — 2026-09-02
statements: {dict(report)}
proofs attached: {len(proofs)} (to theorem-like: {len(main_proofs)}); explicit \\ref uses: {n_uses} ({n_res} resolved in-book) = {n_uses/max(len(proofs),1):.2f} per proof (NaturalProofs reported 1.6 for this book)
theorem-like proof_status: {dict(ps)}
"""
(OUT / "PARSE-REPORT.md").write_text(rep, encoding="utf-8")
print(rep)
