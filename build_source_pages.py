"""build_source_pages.py - one "source pages" viewer per batch-0 book: every page that carries an audited
statement or proof, rendered as an inline grayscale JPEG with an anchor #pNNN, so the Audit Desk can link
"source page" for each item. Inline data URIs because the artifact sandbox blocks external images and this
account has no asset store; one artifact per book keeps each under the 16 MB page limit.

usage: build_source_pages.py <out_dir> [--dpi 96] [--quality 40]
Writes <out_dir>/source-<slug>.html and prints sizes. Pages come from blocks_nougat.jsonl (page + proof_page).
"""
import base64, glob, json, os, sys
import fitz

ROOT = os.path.dirname(os.path.abspath(__file__))
BOOKS = [
    ("armstrong", "groups-and-symmetry-armstrong.pdf", "Armstrong — Groups and Symmetry"),
    ("dixon-mortimer", "permutation-groups-dixon-mortimer.pdf", "Dixon & Mortimer — Permutation Groups"),
    ("silverman-tate", "rational-points-on-elliptic-curves-silverman-tate.pdf", "Silverman & Tate — Rational Points on Elliptic Curves"),
    ("silverman-aec", "the-arithmetic-of-elliptic-curves-silverman-2ed.pdf", "Silverman — The Arithmetic of Elliptic Curves (2nd ed.)"),
    ("chung-aitsahlia", "elementary-probability-theory-chung-aitsahlia-4ed.pdf", "Chung & AitSahlia — Elementary Probability Theory (4th ed.)"),
    ("karatzas-shreve", "brownian-motion-and-stochastic-calculus-karatzas-shreve-2ed.pdf", "Karatzas & Shreve — Brownian Motion and Stochastic Calculus (2nd ed.)"),
]

CSS = """
:root{--bg:#FAF8F4;--card:#FFFFFF;--line:#E4E0D6;--ink:#22242C;--muted:#6A6E7C;--gold:#8A6210;
--sans:'IBM Plex Sans',system-ui,sans-serif;--mono:'IBM Plex Mono',ui-monospace,monospace;--disp:'Fraunces',Georgia,serif}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#0E1220;--card:#171C2E;--line:#272E48;--ink:#E8E4D8;--muted:#989DB0;--gold:#E0AF52}}
:root[data-theme="dark"]{--bg:#0E1220;--card:#171C2E;--line:#272E48;--ink:#E8E4D8;--muted:#989DB0;--gold:#E0AF52}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:15px;line-height:1.5}
header{position:sticky;top:0;z-index:2;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 20px;display:flex;gap:16px;align-items:baseline;flex-wrap:wrap}
header h1{font-family:var(--disp);font-weight:600;font-size:18px;margin:0}
header .k{font-family:var(--mono);font-size:12px;color:var(--muted)}
header form{margin-left:auto;display:flex;gap:6px;align-items:center}
header input{width:6em;font-family:var(--mono);font-size:13px;padding:4px 6px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--ink)}
header button{font:inherit;font-size:13px;padding:4px 10px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--ink);cursor:pointer}
main{max-width:760px;margin:0 auto;padding:16px 20px 80px;display:grid;gap:22px}
figure{margin:0;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px;scroll-margin-top:64px}
figure:target{outline:2px solid var(--gold)}
figcaption{font-family:var(--mono);font-size:12px;color:var(--muted);margin-bottom:6px;display:flex;justify-content:space-between}
img{display:block;width:100%;height:auto;background:#fff}
.note{font-size:13px;color:var(--muted);max-width:760px;margin:12px auto 0;padding:0 20px}
"""

def build(slug, pdf, title, pages, dpi, quality, out_dir):
    doc = fitz.open(os.path.join(ROOT, "corpus", "batch0", pdf))
    figs = []
    for p in sorted(pages):
        pix = doc[p - 1].get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
        b64 = base64.b64encode(pix.tobytes("jpeg", jpg_quality=quality)).decode("ascii")
        figs.append(f'<figure id="p{p}"><figcaption><span>p. {p}</span><span>{pix.width}×{pix.height}, {dpi} dpi</span></figcaption>'
                    f'<img loading="lazy" alt="page {p}" src="data:image/jpeg;base64,{b64}"></figure>')
    html = (f"<meta charset=\"utf-8\"><title>Source pages · {title.split(' — ')[0]}</title>\n"
            "<link rel=\"stylesheet\" href=\"https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap\">\n"
            f"<style>{CSS}</style>\n"
            f"<header><h1>{title}</h1><span class=\"k\">{len(figs)} pages with audited statements · reviewer copy, do not redistribute</span>"
            "<form onsubmit=\"event.preventDefault();const p=document.getElementById('p'+this.q.value.trim());if(p){location.hash='p'+this.q.value.trim();}else{this.q.value='';this.q.placeholder='no such page';}\">"
            "<label class=\"k\" for=\"q\">go to page</label><input id=\"q\" name=\"q\" inputmode=\"numeric\" placeholder=\"e.g. 34\"><button>Go</button></form></header>\n"
            "<div class=\"note\">Scanned pages for checking the Audit Desk's text against the book. Only pages that carry an audited statement or proof are included.</div>\n"
            "<main>" + "\n".join(figs) + "</main>\n")
    path = os.path.join(out_dir, f"source-{slug}.html")
    open(path, "w", encoding="utf-8").write(html)
    return path, len(html)

def main():
    out_dir = sys.argv[1]
    dpi = int(sys.argv[sys.argv.index("--dpi") + 1]) if "--dpi" in sys.argv else 96
    quality = int(sys.argv[sys.argv.index("--quality") + 1]) if "--quality" in sys.argv else 40
    os.makedirs(out_dir, exist_ok=True)
    for slug, pdf, title in BOOKS:
        pages = set()
        for l in open(os.path.join(ROOT, "data", "extracted", "batch0", slug, "blocks_nougat.jsonl"), encoding="utf-8"):
            b = json.loads(l)
            if b["kind"] == "exercise":
                continue
            pages.add(b["page"])
            if b.get("proof_page"):
                pages.add(b["proof_page"])
        d = dpi
        while True:
            path, size = build(slug, pdf, title, pages, d, quality, out_dir)
            if size <= 14_500_000 or d <= 72:
                break
            d -= 8                                                   # shrink until the page fits the 16 MB limit
        print(f"{slug}: {len(pages)} pages at {d} dpi -> {size / 1e6:.1f} MB  {path}")

if __name__ == "__main__":
    main()
