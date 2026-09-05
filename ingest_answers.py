"""Ingest Audit Desk exports (data/audit/batch0-answers/<reviewer>.json, git-tracked) and score the reader.

usage: ingest_answers.py            -> prints per-reviewer / per-field / per-book summary
       ingest_answers.py --rows out.jsonl  -> also writes one row per reviewed item (for linking / follow-ups)

Export format (from build_audit_desk.py): {reviewer, exported, answers: {book_slug: {"kind:label": {q1: yes|no,
struck: [ingredient names the reviewer rejected], missing: free text, ts, reviewer}}}}.
Precision of the reader on an item = 1 - struck/listed; "missing" text non-empty flags a recall gap for follow-up.
Later exports by the same reviewer override earlier answers for the same item (newest ts wins) - the git history
of the JSON file is the audit trail.
"""
import glob, json, os, sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
FIELD = {"armstrong": "group theory", "dixon-mortimer": "group theory",
         "silverman-tate": "elliptic curves", "silverman-aec": "elliptic curves",
         "chung-aitsahlia": "stochastic processes", "karatzas-shreve": "stochastic processes"}

def reader_ingredients():
    """proof_id -> list of ingredient names the reader listed (what the reviewer saw as chips)."""
    out = {}
    for f in glob.glob(os.path.join(ROOT, "data/extracted/batch0/_reader_out/*.jsonl")):
        for line in open(f, encoding="utf-8"):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("proof_id"):
                out[r["proof_id"]] = [g.get("name", "") for g in r.get("ingredients", [])]
    return out

def load_answers():
    """(reviewer, book, item) -> newest answer."""
    best = {}
    for f in sorted(glob.glob(os.path.join(ROOT, "data/audit/batch0-answers/*.json"))):
        j = json.load(open(f, encoding="utf-8"))
        who = j.get("reviewer") or os.path.basename(f)[:-5]
        for book, items in (j.get("answers") or {}).items():
            for item, a in items.items():
                k = (who, book, item)
                if k not in best or (a.get("ts") or "") > (best[k].get("ts") or ""):
                    best[k] = a
    return best

def main():
    ings = reader_ingredients()
    answers = load_answers()
    if not answers:
        print("no reviewer exports yet in data/audit/batch0-answers/"); return
    rows = []
    for (who, book, item), a in sorted(answers.items()):
        pid = f"prf:{book}:{item}"
        listed = ings.get(pid, [])
        struck = [s for s in a.get("struck", []) if s in listed]
        rows.append({"reviewer": who, "field": FIELD.get(book, "?"), "book": book, "item": item, "q1": a.get("q1"),
                     "listed": len(listed), "struck": len(struck), "struck_names": struck,
                     "missing": a.get("missing", ""), "ts": a.get("ts")})
    agg = defaultdict(lambda: {"items": 0, "genuine": 0, "listed": 0, "struck": 0, "missing": 0})
    for r in rows:
        for key in (("reviewer", r["reviewer"]), ("field", r["field"]), ("book", r["book"])):
            g = agg[key]; g["items"] += 1; g["genuine"] += r["q1"] == "yes"
            if r["q1"] == "yes":
                g["listed"] += r["listed"]; g["struck"] += r["struck"]; g["missing"] += bool(r["missing"])
    print(f"{'group':40s} {'items':>5s} {'genuine':>8s} {'listed':>7s} {'struck':>7s} {'precision':>9s} {'missing':>8s}")
    for (kind, name), g in sorted(agg.items()):
        prec = f"{1 - g['struck'] / g['listed']:.0%}" if g["listed"] else "-"
        print(f"{kind + ': ' + name:40s} {g['items']:5d} {g['genuine']:8d} {g['listed']:7d} {g['struck']:7d} {prec:>9s} {g['missing']:8d}")
    if "--rows" in sys.argv:
        out = sys.argv[sys.argv.index("--rows") + 1]
        with open(out, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"wrote {len(rows)} rows to {out}")

if __name__ == "__main__":
    main()
