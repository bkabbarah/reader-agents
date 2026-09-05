#!/usr/bin/env python3
"""build_evaluator_packet.py - per-book review packet for the expert evaluators (batch 0).
For each extracted statement: the statement, the proof excerpt, and the reader-found ingredients with
their evidence quotes; three questions per item (real statement? ingredients right? what's missing?).
Answers come back as a simple CSV (item id, q1, q2 strikes, q3 free text). Static HTML, artifact-ready.
usage: build_evaluator_packet.py <book-slug> <out.html> [--policy strict|all]
"""
import json, sys, html, glob, random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]      # repo root (scripts live one folder down)
slug, out = sys.argv[1], Path(sys.argv[2])
policy = sys.argv[sys.argv.index("--policy") + 1] if "--policy" in sys.argv else "all"
STRICT_KINDS = {"theorem", "lemma", "corollary", "proposition", "principle"}
blocks = [json.loads(l) for l in open(ROOT / f"data/extracted/batch0/{slug}/blocks.jsonl", encoding="utf-8")]
reader = {}
for f in glob.glob(str(ROOT / "data/extracted/batch0/_reader_out/*.txt")):
    for line in open(f, encoding="utf-8"):
        if line.strip():
            try:
                r = json.loads(line); reader[r["proof_id"]] = r.get("ingredients", [])
            except json.JSONDecodeError:
                pass
TITLES = {"armstrong": "Armstrong, Groups and Symmetry", "dixon-mortimer": "Dixon & Mortimer, Permutation Groups",
          "silverman-tate": "Silverman & Tate, Rational Points on Elliptic Curves", "silverman-aec": "Silverman, The Arithmetic of Elliptic Curves (2nd ed.)",
          "chung-aitsahlia": "Chung & AitSahlia, Elementary Probability Theory (4th ed.)", "karatzas-shreve": "Karatzas & Shreve, Brownian Motion and Stochastic Calculus (2nd ed.)"}
items = []
for b in blocks:
    pid = f"prf:{slug}:{b['kind']}:{b['label']}"
    ings = reader.get(pid, [])
    if policy == "strict":
        ings = [i for i in ings if (i.get("confidence") or 0) >= 0.75 and i.get("kind") in STRICT_KINDS]
    items.append((b, ings))
random.seed(7); order = list(range(len(items))); random.shuffle(order)
esc = html.escape
rows = []
for n, idx in enumerate(order, 1):
    b, ings = items[idx]
    iid = f"{slug}:{b['kind']}:{b['label']}"
    ing_html = "".join(
        f'<li><span class="conf">{i.get("confidence", "")}</span> <b>{esc(i["name"])}</b> <span class="k">{esc(i.get("kind") or "")} · {esc(i.get("how") or "")}</span>'
        f'<div class="ev">“{esc((i.get("evidence") or "")[:160])}”</div></li>' for i in ings) or '<li class="none">(no ingredients found by the reader)</li>'
    proof = esc((b["proof_text"] or "")[:900]) + (" …" if b["proof_text"] and len(b["proof_text"]) > 900 else "")
    rows.append(f'''<section class="item" id="{esc(iid)}">
  <div class="head"><span class="n">#{n}</span> <b>{esc(b["kind"].title())} {esc(b["label"])}</b> <span class="k">p. {b["page"]} · id {esc(iid)}</span></div>
  <div class="stmt">{esc(b["statement_text"][:1200])}</div>
  {"<details><summary>proof excerpt</summary><div class='proof'>" + proof + "</div></details>" if b["proof_text"] else "<div class='k'>no proof captured</div>"}
  <div class="q"><b>Q1</b> Is this a genuine statement of the book (not a fragment / running header / exercise)?</div>
  <div class="q"><b>Q2</b> Ingredients the reader says this proof relies on — strike any that are wrong:</div>
  <ul class="ings">{ing_html}</ul>
  <div class="q"><b>Q3</b> What does the proof rely on that is <i>missing</i> above? (one line; “nothing” is a valid answer)</div>
</section>''')
page = f'''<title>Review Packet · {esc(TITLES.get(slug, slug))}</title>
<style>
:root{{--bg:#FAF8F4;--card:#fff;--line:#E4E0D6;--ink:#22242C;--muted:#6A6E7C;--faint:#9A9EAC;--gold:#8A6210;--mint:#116B4E;--violet:#6743A8;--sans:'IBM Plex Sans',system-ui,sans-serif;--mono:ui-monospace,Menlo,monospace}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#0E1220;--card:#171C2E;--line:#272E48;--ink:#E8E4D8;--muted:#989DB0;--faint:#6A7086;--gold:#E0AF52;--mint:#4FD6A5;--violet:#B18FE8}}}}
:root[data-theme="dark"]{{--bg:#0E1220;--card:#171C2E;--line:#272E48;--ink:#E8E4D8;--muted:#989DB0;--faint:#6A7086;--gold:#E0AF52;--mint:#4FD6A5;--violet:#B18FE8}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:15px;line-height:1.5}}
.wrap{{max-width:860px;margin:0 auto;padding:30px 20px 80px}}
h1{{font-size:26px;margin:4px 0}} .sub{{color:var(--muted);max-width:75ch}}
.how{{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--gold);border-radius:10px;padding:12px 16px;margin:16px 0}}
.item{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 18px;margin:14px 0}}
.head{{margin-bottom:6px}} .n{{font-family:var(--mono);color:var(--faint);margin-right:6px}} .k{{color:var(--faint);font-size:12px;font-family:var(--mono)}}
.stmt{{margin:6px 0 8px;white-space:pre-wrap}} .proof{{white-space:pre-wrap;font-size:13.5px;color:var(--muted);margin-top:6px}}
details summary{{cursor:pointer;color:var(--gold);font-size:13px}}
.q{{margin-top:10px;font-size:14px}} .ings{{margin:4px 0 0;padding-left:20px}} .ings li{{margin:4px 0}} .ings .none{{color:var(--faint);list-style:none;margin-left:-20px}}
.conf{{font-family:var(--mono);font-size:11px;color:var(--violet);margin-right:4px}} .ev{{font-size:12.5px;color:var(--muted)}}
</style>
<div class="wrap">
<div class="k">History-of-Mathematics Graph · expert review packet · batch 0</div>
<h1>{esc(TITLES.get(slug, slug))}</h1>
<div class="sub">{len(items)} statements extracted automatically from the book, in random order. Per item, three quick judgments. Ingredients were found by a reader model (confidence shown; ≥0.75 is the strict cut); a wrong ingredient or a missing one is exactly what we need to hear.</div>
<div class="how"><b>How to answer</b> — reply with one line per item you have an opinion on, e.g. <code>#12 Q1 no (fragment) · Q2 strike "ordered field axioms" · Q3 missing: orbit-stabilizer theorem</code>. Items you skip count as "looks fine". Stop whenever you like; partial is useful.</div>
{"".join(rows)}
</div>'''
out.write_text(page, encoding="utf-8")
print(f"{slug}: {len(items)} items ({sum(1 for _, i in items if i)} with reader ingredients) -> {out}")
