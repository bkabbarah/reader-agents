#!/usr/bin/env python3
"""build_audit_desk.py - the reviewer platform: one page, all batch-0 books, grouped by field.
Reviewer enters a name, picks a field and a book, audits item by item (genuine? / strike wrong
ingredients / what's missing), progress and answers persist in the browser (localStorage), and
"Export answers" yields a JSON block to paste back to us. No runtime capabilities: works for anyone
with the link (external evaluators included). usage: build_audit_desk.py <out.html>"""
import json, sys, glob, os, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]      # repo root (scripts live one folder down)
out = Path(sys.argv[1])
FIELDS = [
    ("Group theory", [("armstrong", "Armstrong — Groups and Symmetry (1988)"), ("dixon-mortimer", "Dixon & Mortimer — Permutation Groups (1st ed., 1996)")]),
    ("Elliptic curves", [("silverman-tate", "Silverman & Tate — Rational Points on Elliptic Curves (1st ed., 1992)"), ("silverman-aec", "Silverman — The Arithmetic of Elliptic Curves (2nd ed., 2009)")]),
    ("Stochastic processes", [("chung-aitsahlia", "Chung & AitSahlia — Elementary Probability Theory (4th ed., 2003)"), ("karatzas-shreve", "Karatzas & Shreve — Brownian Motion and Stochastic Calculus (2nd ed., 1991)")]),
]
reader = {}
READER_OUT = ROOT / ("data/extracted/batch0/_reader_out_nougat" if (ROOT / "data/extracted/batch0/_reader_out_nougat").exists()
                     else "data/extracted/batch0/_reader_out")           # Nougat-text reader run when present, else old run
for f in glob.glob(str(READER_OUT / "*.txt")):
    for line in open(f, encoding="utf-8"):
        if line.strip():
            try:
                r = json.loads(line); reader[r["proof_id"]] = r.get("ingredients", [])
            except json.JSONDecodeError:
                pass

MATH_SPAN = re.compile(r"(\\\(.*?\\\)|\\\[.*?\\\]|\$\$.*?\$\$|\$[^$\n]*\$)", re.S)   # capturing: split() keeps the spans

def safe_tex(s, limit=None):
    """Cut a string without splitting a math span, then close any math delimiter the reader left open,
    so MathJax never sees a half formula (Tim: 'a few LaTeX expressions in Q2 aren't compiling')."""
    s = (s or "").strip()
    if limit and len(s) > limit:
        cut = limit
        for m in MATH_SPAN.finditer(s):                 # never cut inside a span: back up to its start
            if m.start() < cut < m.end():
                cut = m.start()
                break
        s = s[:cut].rstrip() + "…"
    n_open, n_close = s.count("\\("), s.count("\\)")
    if n_open > n_close:
        s += "\\)" * (n_open - n_close)
    elif n_close > n_open:                                    # quote started mid-formula: drop the stray closers
        for _ in range(n_close - n_open):
            s = s.replace("\\)", "", 1)
    d_open, d_close = s.count("\\["), s.count("\\]")
    if d_open > d_close:
        s += "\\]" * (d_open - d_close)
    elif d_close > d_open:
        for _ in range(d_close - d_open):
            s = s.replace("\\]", "", 1)
    if s.count("$") % 2:
        s += "$"
    return wrap_bare_tex(s)

BARE = re.compile(r"[\\^_{}]")                                 # a token that only makes sense as LaTeX (has \ ^ _ { })
VARLIKE = re.compile(r"^[A-Za-z](?:[,.;:)]|')?$|^[=<>+\-]$|^\(?[A-Za-z]$")  # H  K,  =  (G

def wrap_bare_tex(s):
    r"""The reader often quotes math without delimiters ("xy^{-1}\in H\cap K"). Outside existing math spans,
    wrap maximal runs of LaTeX-looking tokens, absorbing adjacent single-letter variables, in \( \)."""
    out = []
    for i, part in enumerate(MATH_SPAN.split(s)):
        if i % 2 == 1 or not BARE.search(part):
            out.append(part); continue
        toks = part.split(" ")
        is_tex = [bool(BARE.search(t)) for t in toks]
        # absorb single-letter neighbours (H, K, =) that touch a LaTeX token
        changed = True
        while changed:
            changed = False
            for j, t in enumerate(toks):
                if not is_tex[j] and VARLIKE.match(t) and ((j > 0 and is_tex[j-1]) or (j+1 < len(toks) and is_tex[j+1])):
                    is_tex[j] = True; changed = True
        buf, run = [], []
        for t, m in zip(toks, is_tex):
            if m:
                run.append(t)
            else:
                if run:
                    buf.append("\\(" + " ".join(run) + "\\)"); run = []
                buf.append(t)
        if run:
            buf.append("\\(" + " ".join(run) + "\\)")
        out.append(" ".join(buf))
    return "".join(out)

CITE = re.compile(r"(?i)\b(theorem|lemma|proposition|corollary|definition|prop\.|thm\.|cor\.|lem\.)\s*\(?([IVXLC]*\.?\d+(?:\.\d+)*[A-Za-z]?)\)?|\((\d+\.\d+[A-Za-z]?)\)")

GENERIC = {"theorem", "lemma", "proposition", "corollary", "definition", "claim", "for", "with", "curves", "curve", "rational",
           "point", "points", "order", "two", "the", "of", "and", "on", "over", "in", "to", "a", "an"}

def _fold(t):
    import unicodedata
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower().replace("'", "").replace(chr(8217), "")

def name_keys(it):
    """Distinctive words of a NAMED result ("Nagell-Lutz Theorem" -> {nagell, lutz}; "Siegel's Lemma" -> {siegel}).
    Synthesized labels (p68-the3) and generic ones (Theorem) give nothing."""
    label = it["label"].split("#")[0]
    src = (it.get("name") or "") + " " + ("" if re.match(r"^p\d+-", label) else label)
    keys = []
    for w in re.findall(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'’\-]{3,}", src):
        for part in re.split(r"[\-]", _fold(w.replace("'s", "").replace("’s", ""))):
            if part and part not in GENERIC and part not in keys:
                keys.append(part)
    return keys

def book_edges(items):
    """Intra-book 'uses' edges from explicit citations in ingredient names/evidence (deterministic; the cross-book
    linking pass is a separate fleet stage): (1) numbered labels ("Proposition 3.14", "(5.1)", "Theorem 1.4A"),
    (2) named results ("by the Nagell-Lutz Theorem", "Siegel's Lemma"), (3) chapter-local "Lemma 2" in books that
    number lemmas per chapter (Silverman-Tate), resolved to the nearest earlier item with that label within 60 pages."""
    by_label = {}
    for j, it in enumerate(items):
        by_label.setdefault(it["label"].split("#")[0].upper(), j)
    named = [(j, name_keys(it)) for j, it in enumerate(items)]
    named = [(j, k) for j, k in named if k]
    edges = {}
    for j, it in enumerate(items):
        chap = it["label"].rsplit(".", 1)[0] if it["label"].count(".") >= 1 else ""
        found = []
        text = " ".join(((g.get("name") or "") + " " + (g.get("ev") or "")) for g in it["ings"])
        folded = _fold(text)
        for m in CITE.finditer(text):                                       # (1) numbered
            lab = (m.group(2) or m.group(3) or "").upper().strip(".")
            for cand in (lab, f"{chap}.{lab}" if chap else lab, f"{chap.split('.')[0]}.{lab}" if chap else lab):
                k = by_label.get(cand)
                if k is not None and k != j and k not in found:
                    found.append(k); break
        for k, keys in named:                                               # (2) named results, cited as a phrase
            if k == j or k in found:
                continue
            phrase = " ".join(keys)                                         # keys keep the name's word order
            if len(keys) >= 2:
                hit = re.search(r"\b" + r"[\s\-]+".join(map(re.escape, keys)) + r"\b", folded)
            else:                                                           # "bezout" alone is not enough: "Bezout's theorem", "theorem of Bezout"
                w = re.escape(keys[0])
                hit = re.search(r"\b" + w + r"(?:s)?[\s\-]+(?:theorem|lemma|proposition|corollary|inequality|formula|criterion|identity)\b|"
                                r"\b(?:theorem|lemma|proposition|corollary|inequality|formula|criterion|identity)\s+of\s+" + w + r"\b", folded)
            if hit:
                found.append(k)
        for m in re.finditer(r"\b(Lemma|Proposition|Theorem|Corollary)\s+(\d{1,2})\b(?![.\d])", text):   # (3) chapter-local
            lab = m.group(2)
            cands = [k for k, x in enumerate(items) if x["label"].split("#")[0] == f"{m.group(1)} {lab}"
                     and 0 <= it["page"] - x["page"] <= 60 and k != j]
            if cands:
                k = max(cands, key=lambda k: items[k]["page"])                 # nearest earlier one
                if k not in found:
                    found.append(k)
        if found:
            edges[j] = found
    return edges

books = {}
for field, bl in FIELDS:
    for slug, title in bl:
        items = []
        bf = ROOT / f"data/extracted/batch0/{slug}/blocks_nougat.jsonl"       # math-aware OCR blocks when available
        if not bf.exists():
            bf = ROOT / f"data/extracted/batch0/{slug}/blocks.jsonl"
        for b in (json.loads(l) for l in open(bf, encoding="utf-8")):
            if b["kind"] == "exercise":                                          # problems/exercises: no proof to audit
                continue
            pid = f"prf:{slug}:{b['kind']}:{b['label']}"
            items.append({"id": f"{b['kind']}:{b['label']}", "kind": b["kind"], "label": b["label"], "page": b["page"],
                          "name": b.get("name"), "proof_status": b.get("proof_status"), "proof_page": b.get("proof_page"), "partial": bool(b.get("page_partial")),
                          "statement": b["statement_text"][:6000], "proof": (b["proof_text"] or "")[:12000],
                          "ings": [{"name": safe_tex(i["name"]), "kind": i.get("kind"), "how": i.get("how"), "conf": i.get("confidence"),
                                    "ev": safe_tex(i.get("evidence"), 220)} for i in (reader.get(pid, []) if b.get("proof_text") else [])]})
        edges = book_edges(items)
        for j, it in enumerate(items):
            it["uses"] = edges.get(j, [])
        books[slug] = {"title": title, "field": field, "items": items,
                       "n_edges": sum(len(v) for v in edges.values())}
viewers_path = ROOT / "data/audit/source_viewers.json"          # per-book "source pages" artifacts (build_source_pages.py)
viewers = json.loads(viewers_path.read_text(encoding="utf-8")) if viewers_path.exists() else {}
for slug, url in viewers.items():
    if slug in books:
        books[slug]["source_url"] = url
data = {"fields": [{"name": f, "books": [s for s, _ in bl]} for f, bl in FIELDS], "books": books}
payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")

html = r'''<meta charset="utf-8"><title>Audit Desk</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{--bg:#FAF8F4;--card:#FFFFFF;--line:#E4E0D6;--ink:#22242C;--muted:#6A6E7C;--faint:#9A9EAC;--gold:#8A6210;--gold-bg:#F6EDD8;--mint:#116B4E;--mint-bg:#DDF2E9;--violet:#6743A8;--violet-bg:#ECE4F8;--warn:#8A3B12;--warn-bg:#F9E7DC;--sky:#1F5FBF;--sky-bg:#DCE8FA;
--sans:'IBM Plex Sans',system-ui,sans-serif;--mono:'IBM Plex Mono',ui-monospace,monospace;--disp:'Fraunces',Georgia,serif}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#0E1220;--card:#171C2E;--line:#272E48;--ink:#E8E4D8;--muted:#989DB0;--faint:#6A7086;--gold:#E0AF52;--gold-bg:#2C2410;--mint:#4FD6A5;--mint-bg:#0E2B21;--violet:#B18FE8;--violet-bg:#251B3A;--warn:#F09A6E;--warn-bg:#331E10;--sky:#7FB2FF;--sky-bg:#14243D}}
:root[data-theme="dark"]{--bg:#0E1220;--card:#171C2E;--line:#272E48;--ink:#E8E4D8;--muted:#989DB0;--faint:#6A7086;--gold:#E0AF52;--gold-bg:#2C2410;--mint:#4FD6A5;--mint-bg:#0E2B21;--violet:#B18FE8;--violet-bg:#251B3A;--warn:#F09A6E;--warn-bg:#331E10;--sky:#7FB2FF;--sky-bg:#14243D}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:15px;line-height:1.5}
.wrap{max-width:900px;margin:0 auto;padding:26px 20px 90px}
.eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:var(--faint)}
h1{font-family:var(--disp);font-weight:600;font-size:30px;margin:4px 0 2px} h2{font-family:var(--disp);font-weight:600;font-size:20px;margin:22px 0 8px}
.sub{color:var(--muted);max-width:70ch;margin-bottom:14px}
input[type=text],textarea{font:inherit;color:var(--ink);background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 10px;width:100%}
button{font:inherit;cursor:pointer;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:8px;padding:7px 12px}
button.primary{background:var(--gold);border-color:var(--gold);color:#fff} button.on{background:var(--mint-bg);border-color:var(--mint);color:var(--mint)} button.bad{background:var(--warn-bg);border-color:var(--warn);color:var(--warn)}
button:focus-visible,input:focus-visible,textarea:focus-visible{outline:2px solid var(--violet);outline-offset:2px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}
.fieldcard{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.fieldcard h3{margin:0 0 6px;font-family:var(--disp);font-size:18px;font-weight:600}
.bookbtn{display:block;width:100%;text-align:left;margin:6px 0;padding:9px 12px}
.bookbtn .prog{font-family:var(--mono);font-size:11px;color:var(--faint);display:block;margin-top:2px}
.bar{height:6px;background:var(--line);border-radius:99px;overflow:hidden;margin:6px 0 14px} .bar i{display:block;height:100%;background:var(--mint)}
.top{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}
.item{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:12px 0}
.k{font-family:var(--mono);font-size:11.5px;color:var(--faint)}
.stmt{white-space:pre-wrap;margin:8px 0 10px;font-size:15px}
details summary{cursor:pointer;color:var(--gold);font-size:13px} .proof{white-space:pre-wrap;font-size:13.5px;color:var(--muted);margin-top:6px}
.q{margin-top:14px;font-weight:600;font-size:14px} .q .hint{font-weight:400;color:var(--muted)}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}
.chip{border:1px solid var(--line);background:var(--bg);border-radius:10px;padding:7px 10px;cursor:pointer;max-width:100%;text-align:left}
.chip .c{font-family:var(--mono);font-size:10.5px;color:var(--violet);margin-right:4px} .chip .kk{font-family:var(--mono);font-size:10.5px;color:var(--faint);margin-left:4px}
.chip .ev{display:block;font-size:12px;color:var(--muted);margin-top:2px} .chip.struck{background:var(--warn-bg);border-color:var(--warn);text-decoration:line-through;opacity:.85}
.nav{display:flex;gap:8px;flex-wrap:wrap;margin-top:16px;align-items:center} .nav .sp{flex:1}
.pg{display:inline-block;font-family:var(--sans);font-weight:600;font-size:15px;color:var(--gold);background:var(--gold-bg);border:1px solid var(--gold);border-radius:8px;padding:2px 10px;vertical-align:middle}
.wrap{max-width:1280px}
.two{display:grid;grid-template-columns:1fr;gap:18px;align-items:start}
@media (min-width:1000px){.two{grid-template-columns:minmax(0,1.1fr) minmax(0,1fr)} .src{position:sticky;top:12px;max-height:calc(100vh - 24px);overflow:auto;padding-right:6px}}
.src,.qs{min-width:0}
.graphs{display:grid;grid-template-columns:1fr;gap:14px;margin:12px 0}
@media (min-width:1000px){.graphs{grid-template-columns:3fr 2fr}}
.gcard{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;min-width:0}
.gcard .gh{display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap}
.gcard h4{margin:0;font-family:var(--disp);font-weight:600;font-size:15px}
.legend{display:flex;gap:12px;flex-wrap:wrap;font-family:var(--mono);font-size:10.5px;color:var(--muted);align-items:center}
.legend i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px;vertical-align:-1px}
.gcard svg{width:100%;height:auto;display:block;margin-top:6px} .gcard svg text{font-family:var(--mono);font-size:10px;fill:var(--muted)}
.gcard .band{fill:var(--bg);stroke:var(--line)} .gcard .nd{fill:var(--line);cursor:pointer} .gcard .nd.done{fill:var(--mint)}
.gcard .nd.up{fill:var(--violet)} .gcard .nd.down{fill:var(--sky)} .gcard .nd.cur{fill:var(--gold);stroke:var(--ink);stroke-width:1.5}
.gcard .ed{stroke:var(--line);stroke-width:1;fill:none;opacity:.8} .gcard .ed.up{stroke:var(--violet);stroke-width:1.8;opacity:1} .gcard .ed.down{stroke:var(--sky);stroke-width:1.8;opacity:1}
.gcard .pill{cursor:pointer} .gcard .pill rect{fill:var(--bg)} .gcard .pill.up rect{stroke:var(--violet)} .gcard .pill.down rect{stroke:var(--sky)} .gcard .pill text.t{fill:var(--ink);font-family:var(--sans);font-size:11.5px;font-weight:500}
.gcard .curbox rect{fill:var(--gold-bg);stroke:var(--gold);stroke-width:1.6} .gcard .curbox text{fill:var(--gold);font-family:var(--sans);font-weight:600;font-size:12px}
.gcard .flag rect{fill:var(--gold-bg);stroke:var(--gold)} .gcard .flag text{fill:var(--gold);font-weight:600}
.pill{display:inline-block;font-family:var(--mono);font-size:10.5px;padding:2px 8px;border-radius:99px;background:var(--mint-bg);color:var(--mint)}
.list{display:flex;flex-wrap:wrap;gap:4px;margin:8px 0 0} .list button{padding:2px 7px;font-size:11px;font-family:var(--mono)} .list button.done{background:var(--mint-bg);border-color:var(--mint);color:var(--mint)} .list button.cur{outline:2px solid var(--violet)}
.toast{position:fixed;bottom:16px;left:50%;transform:translateX(-50%);background:var(--ink);color:var(--bg);padding:8px 14px;border-radius:10px;font-size:13px;opacity:0;transition:opacity .2s} .toast.show{opacity:1}
.foot{color:var(--faint);font-size:12px;margin-top:26px;font-family:var(--mono)}
mjx-container{color:inherit} mjx-container svg{vertical-align:-0.2em}
</style>
<script>
  window.MathJax = { tex: { inlineMath: [['$','$'], ['\\(','\\)']], displayMath: [['$$','$$'], ['\\[','\\]']], processEscapes: true,
                            macros: { R: '\\mathbb{R}', N: '\\mathbb{N}', Z: '\\mathbb{Z}', Q: '\\mathbb{Q}', C: '\\mathbb{C}' } },
                     options: { skipHtmlTags: ['script','noscript','style','textarea','input'] }, svg: { fontCache: 'global' } };
</script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/mathjax/3.2.2/es5/tex-svg.js"></script>
<div class="wrap" id="app"></div>
<div class="toast" id="toast"></div>
<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const KEY = 'audit-desk-v1';
let S = {name:'', answers:{}, pos:{}};
try { const s = localStorage.getItem(KEY); if (s) S = Object.assign(S, JSON.parse(s)); } catch (e) {}
function save(){ try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (e) {} }
const $ = s => document.querySelector(s), esc = s => (s||'').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function toast(m){ const t=$('#toast'); t.textContent=m; t.classList.add('show'); setTimeout(()=>t.classList.remove('show'),1400); }
let view = {screen:'home', book:null, i:0};
function ansFor(book){ return S.answers[book] = S.answers[book] || {}; }
function done(book){ return Object.keys(ansFor(book)).length; }

function home(){
  const app = $('#app');
  app.innerHTML = `<div class="eyebrow">History-of-Mathematics Graph · expert audit</div><h1>Audit Desk</h1>
  <div class="sub">Two minutes per item: is the statement real, which listed ingredients are wrong, what's missing. Your progress stays in this browser; export whenever you like — partial is useful.</div>
  <label class="k" for="nm">Your name</label><input id="nm" type="text" placeholder="e.g. David" value="${esc(S.name)}">
  <h2>Choose a book</h2><div class="grid">` + D.fields.map(f => `<div class="fieldcard"><h3>${esc(f.name)}</h3>` + f.books.map(b => {
    const bk = D.books[b], n = bk.items.length, d = done(b);
    return `<button class="bookbtn" data-book="${b}"><b>${esc(bk.title)}</b><span class="prog">${d}/${n} reviewed</span></button>`; }).join('') + `</div>`).join('') + `</div>
  <h2>Export</h2><div class="sub">When you're done (or done for now), copy this and paste it into the Slack channel.</div>
  <button id="exp">Show my answers</button> <button id="cp">Copy to clipboard</button><textarea id="out" rows="6" style="margin-top:8px;display:none;font-family:var(--mono);font-size:12px"></textarea>
  <h2>Restore</h2><div class="sub">New browser or device? Paste a previous export here to pick up where you left off (it merges with anything already here).</div>
  <textarea id="imp" rows="3" placeholder="paste exported JSON" style="font-family:var(--mono);font-size:12px"></textarea><div style="margin-top:6px"><button id="impbtn">Import</button></div>
  <div class="foot">Statements and proofs were read from the scanned pages by a math-aware OCR model; ingredients were listed by a reader model from that text. The number on each ingredient is the reader's own confidence. If something looks cut off or wrong in the text itself, say so in Q3.</div>`;
  $('#nm').addEventListener('input', e => { S.name = e.target.value; save(); });
  app.querySelectorAll('.bookbtn').forEach(b => b.addEventListener('click', () => { if (!S.name.trim()) { toast('Please enter your name first'); $('#nm').focus(); return; } view = {screen:'book', book:b.dataset.book, i:S.pos[b.dataset.book]||0}; render(); }));
  const exportText = () => JSON.stringify({reviewer:S.name, exported:new Date().toISOString(), answers:S.answers}, null, 1);
  $('#exp').addEventListener('click', () => { const o=$('#out'); o.style.display='block'; o.value=exportText(); });
  $('#impbtn').addEventListener('click', () => { try { const j = JSON.parse($('#imp').value); if (j.reviewer && !S.name) S.name = j.reviewer; for (const b in (j.answers||{})) { S.answers[b] = Object.assign(S.answers[b]||{}, j.answers[b]); } save(); toast('Imported'); render(); } catch(e) { toast('Could not parse that JSON'); } });
  $('#cp').addEventListener('click', async () => { try { await navigator.clipboard.writeText(exportText()); toast('Copied'); } catch(e){ const o=$('#out'); o.style.display='block'; o.value=exportText(); o.select(); toast('Select and copy'); } });
}

function book(){
  const b = view.book, bk = D.books[b], items = bk.items, n = items.length;
  view.i = Math.max(0, Math.min(view.i, n-1)); const it = items[view.i];
  const A = ansFor(b); const cur = A[it.id] || {q1:null, struck:[], missing:''};
  const showName = !!(it.name && it.label.toLowerCase().indexOf(it.name.toLowerCase()) < 0);   // name not already the label
  const app = $('#app');
  app.innerHTML = `<div class="top"><div><div class="eyebrow">${esc(bk.field)}</div><h1 style="font-size:22px">${esc(bk.title)}</h1></div><div><button id="back">← Books</button></div></div>
  <div class="k">${done(b)}/${n} reviewed · reviewer ${esc(S.name)}</div><div class="bar"><i style="width:${(100*done(b)/n).toFixed(1)}%"></i></div>
  <div class="item two"><div class="src">
    <div class="k">item ${view.i+1} of ${n} · <span class="pg">page ${it.page}${it.proof_page&&it.proof_page!==it.page?` (proof p. ${it.proof_page})`:``}</span> · <b style="color:var(--ink)">${esc(displayLabel(it, false)).replace(' (unnumbered)', ' <span class="k">(unnumbered in the book)</span>')}${/#\d+$/.test(it.label)?` <span class="k">(occurrence ${it.label.match(/#(\d+)$/)[1]})</span>`:''}</b>${showName?` (${esc(it.name)})`:''}${bk.source_url?` · <a href="${bk.source_url}#p${it.page}" target="_blank" rel="noopener">source page</a>${it.proof_page&&it.proof_page!==it.page?` · <a href="${bk.source_url}#p${it.proof_page}" target="_blank" rel="noopener">proof p. ${it.proof_page}</a>`:''}`:''}</div>
    ${it.partial?`<div class="k" style="color:var(--warn)">OCR of this page is incomplete (the scan was only partly read) — if the text below looks cut off, answer from your copy of the book.</div>`:``}<div class="stmt">${esc(it.statement)}</div>
    ${it.proof ? `<details${cur.q1?'':' open'}><summary>proof excerpt${it.proof_status==='proof-implicit'?' (no “Proof” marker in the book — this is the prose that follows the statement and may be discussion rather than a proof)':''}</summary><div class="proof">${esc(it.proof)}</div></details>` : `<div class="k">${it.proof_status==='deferred-or-omitted'?'the book defers or omits this proof':'no proof captured for this statement'}</div>`}
  </div><div class="qs">
    <div class="q" style="margin-top:0">Q1 · Is this a genuine statement of the book? <span class="hint">(not a fragment, running header, or exercise)</span></div>
    <div class="nav" style="margin-top:6px"><button id="q1y" class="${cur.q1==='yes'?'on':''}">Yes, genuine</button><button id="q1n" class="${cur.q1==='no'?'bad':''}">No — fragment / not a statement</button></div>
    <div class="q">Q2 · Ingredients the reader says this proof relies on <span class="hint">— click any that are wrong to strike them</span></div>
    <div class="chips" id="chips">${it.ings.length ? it.ings.map((g,j) => `<button class="chip ${cur.struck.includes(g.name)?'struck':''}" data-j="${j}"><span class="c">${g.conf??''}</span>${esc(g.name)}<span class="kk">${esc(g.kind||'')}·${esc(g.how||'')}</span><span class="ev">“${esc(g.ev)}”</span></button>`).join('') : '<span class="k">(no ingredients found)</span>'}</div>
    <div class="q">Q3 · What does the proof rely on that is missing above? <span class="hint">(one line; "nothing" is fine)</span></div>
    <input id="miss" type="text" value="${esc(cur.missing)}" placeholder="e.g. orbit–stabilizer theorem; definition of a normal subgroup">
    <div class="nav"><button id="prev">← Prev</button><button id="skip">Skip</button><span class="sp"></span><span class="k">Enter = save & next</span><button id="savenext" class="primary">Save & next →</button></div>
  </div></div>
  <div class="graphs">
    <div class="gcard"><div class="gh"><h4>Book map · reading order →</h4><div class="legend"><span><i style="background:var(--gold)"></i>this item</span><span><i style="background:var(--violet)"></i>its proof uses</span><span><i style="background:var(--sky)"></i>used by later proofs</span><span><i style="background:var(--mint)"></i>reviewed</span><span>arrow points at the result being used</span></div></div>${bookMap(items, view.i, A)}<div class="k">${n} items · ${bk.n_edges} in-book citations found by label · faint arcs are everyone else's · click to jump</div></div>
    <div class="gcard"><div class="gh"><h4>${esc(shortLabel(it))} in context</h4><div class="legend"><span>earlier ←</span><span>→ later</span></div></div>${neighbourhood(items, view.i)}</div>
  </div>
  <div class="k">jump to item</div><div class="list">${items.map((x,j) => `<button data-i="${j}" class="${A[x.id]?'done':''} ${j===view.i?'cur':''}" title="${esc(x.kind+' '+x.label)}">${j+1}</button>`).join('')}</div>`;
  const state = {q1:cur.q1, struck:new Set(cur.struck)};
  $('#q1y').onclick = () => { state.q1='yes'; $('#q1y').classList.add('on'); $('#q1n').classList.remove('bad'); };
  $('#q1n').onclick = () => { state.q1='no'; $('#q1n').classList.add('bad'); $('#q1y').classList.remove('on'); };
  app.querySelectorAll('.chip').forEach(c => c.onclick = () => { const nm = it.ings[+c.dataset.j].name; if (state.struck.has(nm)) { state.struck.delete(nm); c.classList.remove('struck'); } else { state.struck.add(nm); c.classList.add('struck'); } });
  const commit = () => { A[it.id] = {q1:state.q1, struck:[...state.struck], missing:$('#miss').value.trim(), ts:new Date().toISOString(), reviewer:S.name}; S.pos[b] = Math.min(view.i+1, n-1); save(); };
  const go = (i) => { view.i = i; render(); };
  $('#savenext').onclick = () => { if (!state.q1) { toast('Answer Q1 first'); return; } commit(); toast('Saved'); go(Math.min(view.i+1, n-1)); };
  $('#skip').onclick = () => { S.pos[b] = Math.min(view.i+1, n-1); save(); go(Math.min(view.i+1, n-1)); };
  $('#prev').onclick = () => go(Math.max(view.i-1, 0));
  $('#back').onclick = () => { view = {screen:'home'}; render(); };
  $('#miss').addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); $('#savenext').click(); } });
  app.querySelectorAll('.list button').forEach(x => x.onclick = () => go(+x.dataset.i));
  app.querySelectorAll('[data-g]').forEach(x => x.onclick = () => go(+x.dataset.g));
  window.scrollTo({top:0});
}

function usedBy(items, i){ const r=[]; items.forEach((x,j) => { if ((x.uses||[]).includes(i)) r.push(j); }); return r; }
function kindAbbr(k){ return ({theorem:'Thm',lemma:'Lem',proposition:'Prop',corollary:'Cor',definition:'Def',claim:'Claim'})[k] || k; }
function isNumbered(l){ return /^[IVXLC]*\.?\d+(\.\d+)*[A-Za-z]?(#\d+)?$/.test(l); }
function displayLabel(x, abbr){                                   // "Thm 1.3.13" · "Nagell-Lutz Theorem" · "Thm (Gauss)" · "Thm (unnumbered)"
  const K = abbr ? kindAbbr(x.kind) : x.kind[0].toUpperCase()+x.kind.slice(1), base = x.label.replace(/#\d+$/,'');
  if (/^p\d+-/.test(base) || new RegExp('^'+x.kind+'$','i').test(base)) return K+' (unnumbered)';
  if (isNumbered(base)) return K+' '+base;
  if (new RegExp(x.kind,'i').test(base)) return base;               // "Descent Theorem", "Siegel's Lemma"
  return K+' ('+base+')';                                           // "Theorem (Gauss)"
}
function shortLabel(x){ return displayLabel(x, true); }
function chapterOf(x){ const m = x.label.match(/^([IVXLC]+|\d+)\./); return m ? m[1] : null; }
function bookMap(items, cur, A){
  const n = items.length, W = 760, left = 16, right = 16, base = 150, span = W-left-right, step = span/Math.max(n,1);
  const X = j => left + step*(j+0.5), dense = step < 7;
  const uses = new Set(items[cur].uses||[]), by = new Set(usedBy(items, cur));
  const arc = (a, b, cls) => { const x1=X(a), x2=X(b), h = Math.min(120, 18 + Math.abs(x2-x1)*0.35); return `<path class="ed ${cls}" d="M${x1},${base-4} C${x1},${base-4-h} ${x2},${base-4-h} ${x2},${base-4}"${cls?' marker-end="url(#arr-'+cls+')"':''}/>`; };
  let faint='', hi='';
  items.forEach((x,j) => (x.uses||[]).forEach(k => { if (j===cur) hi += arc(j,k,'up'); else if (k===cur) hi += arc(j,k,'down'); else faint += arc(j,k,''); }));
  // chapter bands under the baseline
  let bands='', prev=null, startJ=0;
  const flush = (endJ) => { if (prev===null) return; const x1 = X(startJ)-step/2+1, x2 = X(endJ)+step/2-1; if (x2-x1 > 2) bands += `<rect class="band" x="${x1.toFixed(1)}" y="${base+8}" width="${(x2-x1).toFixed(1)}" height="16" rx="4"/>${x2-x1>34?`<text x="${((x1+x2)/2).toFixed(1)}" y="${base+20}" text-anchor="middle">${esc('ch. '+prev)}</text>`:''}`; };
  items.forEach((x,j) => { const c = chapterOf(x); if (c!==prev){ flush(j-1); prev=c; startJ=j; } }); flush(n-1);
  const nodes = items.map((x,j) => { const cls = j===cur?'cur':uses.has(j)?'up':by.has(j)?'down':A[x.id]?'done':''; const t = `<title>${esc(shortLabel(x))} · p. ${x.page}</title>`;
    if (j===cur) return `<circle class="nd cur" cx="${X(j).toFixed(1)}" cy="${base}" r="6.5" data-g="${j}">${t}</circle>`;
    return dense ? `<rect class="nd ${cls}" x="${(X(j)-1).toFixed(1)}" y="${cls?base-7:base-4}" width="2" height="${cls?14:8}" data-g="${j}">${t}</rect>`
                 : `<circle class="nd ${cls}" cx="${X(j).toFixed(1)}" cy="${base}" r="${cls?4.5:3.2}" data-g="${j}">${t}</circle>`; }).join('');
  const cx = X(cur), lab = shortLabel(items[cur])+' · p. '+items[cur].page, lw = lab.length*6.4+14, lx = Math.max(left, Math.min(W-right-lw, cx-lw/2));
  const flag = `<g class="flag"><path d="M${cx.toFixed(1)},${base+8} V${base+32}" stroke="var(--gold)" stroke-dasharray="2 3"/><rect x="${lx.toFixed(1)}" y="${base+32}" width="${lw.toFixed(1)}" height="18" rx="4"/><text x="${(lx+lw/2).toFixed(1)}" y="${base+45}" text-anchor="middle">${esc(lab)}</text></g>`;
  return `<svg viewBox="0 0 ${W} ${base+58}" role="img" aria-label="book map"><defs>
    <marker id="arr-up" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 L10 5 L0 10 Z" fill="var(--violet)"/></marker>
    <marker id="arr-down" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 L10 5 L0 10 Z" fill="var(--sky)"/></marker></defs>
    ${bands}<line x1="${left}" y1="${base}" x2="${W-right}" y2="${base}" stroke="var(--line)"/>${faint}${hi}${nodes}${flag}</svg>`;
}
function neighbourhood(items, cur){
  const it = items[cur], uses = (it.uses||[]).slice(0,12), by = usedBy(items, cur).slice(0,12);
  const more = (usedBy(items, cur).length-by.length) + ((it.uses||[]).length-uses.length);
  const W = 460, rh = 40, rows = Math.max(uses.length, by.length, 1), H = 40 + rows*rh + 24, cy = 40 + (rows*rh)/2;
  const pill = (k, x, y, cls) => `<g class="pill ${cls}" data-g="${k}"><rect x="${x}" y="${y-16}" width="118" height="32" rx="8"/><text class="t" x="${x+59}" y="${y-2}" text-anchor="middle">${esc(shortLabel(items[k]))}</text><text x="${x+59}" y="${y+11}" text-anchor="middle">p. ${items[k].page}</text></g>`;
  const ys = (list) => list.map((_,i) => 40 + (rows*rh - list.length*rh)/2 + i*rh + rh/2);
  let g = `<text x="70" y="16" text-anchor="middle" letter-spacing="1.5">ITS PROOF USES</text><text x="${W/2}" y="16" text-anchor="middle" letter-spacing="1.5">THIS ITEM</text><text x="${W-72}" y="16" text-anchor="middle" letter-spacing="1.5">USED BY LATER PROOFS</text><line x1="10" y1="24" x2="${W-10}" y2="24" stroke="var(--line)"/>`;
  ys(uses).forEach((y,i) => { g += `<path class="ed up" d="M130,${y} C158,${y} 160,${cy} ${W/2-52},${cy}" marker-end="url(#arr-up2)"/>` + pill(uses[i], 12, y, 'up'); });
  ys(by).forEach((y,i) => { g += `<path class="ed down" d="M${W/2+52},${cy} C${W/2+80},${cy} ${W-152},${y} ${W-136},${y}" marker-end="url(#arr-down2)"/>` + pill(by[i], W-130, y, 'down'); });
  if (!uses.length) g += `<text x="70" y="${cy+4}" text-anchor="middle">cites nothing in this book</text>`;
  if (!by.length) g += `<text x="${W-72}" y="${cy+4}" text-anchor="middle">not cited by any proof here</text>`;
  g += `<g class="curbox"><rect x="${W/2-50}" y="${cy-22}" width="100" height="44" rx="10"/><text x="${W/2}" y="${cy-3}" text-anchor="middle">${esc(shortLabel(it))}</text><text x="${W/2}" y="${cy+13}" text-anchor="middle" style="font-weight:400;font-size:10px">p. ${it.page}</text></g>`;
  if (more>0) g += `<text x="${W/2}" y="${H-6}" text-anchor="middle">+${more} more not shown</text>`;
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="neighbourhood"><defs>
    <marker id="arr-up2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0 L10 5 L0 10 Z" fill="var(--violet)"/></marker>
    <marker id="arr-down2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0 L10 5 L0 10 Z" fill="var(--sky)"/></marker></defs>${g}</svg>`;
}
function typeset(){ try { if (window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise([document.getElementById('app')]).catch(()=>{}); } catch(e){} }
function render(){ view.screen === 'home' ? home() : book(); typeset(); }
render();
</script>'''
page = html.replace("__DATA__", payload)
# guard: the page's own script must parse (a stray "${" in a template literal once blanked the whole desk)
import subprocess, tempfile
_js = max(re.findall(r"<script>(.*?)</script>", page, re.S), key=len)
with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as _f:
    _f.write(_js); _tmp = _f.name
_chk = subprocess.run(["node", "--check", _tmp], capture_output=True, text=True)
os.remove(_tmp)
if _chk.returncode != 0:
    sys.exit("REFUSING TO WRITE: page script does not parse: " + _chk.stderr[:800])
out.write_text(page, encoding="utf-8")
print(f"audit desk: {sum(len(b['items']) for b in books.values())} items across {len(books)} books -> {out} ({out.stat().st_size//1024} KB)")
