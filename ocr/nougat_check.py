"""Sanity-check Nougat pages against the PDF's own text layer.

usage: nougat_check.py <book.pdf> <nougat_dir>

For each page, compares the word set of Nougat's markdown (LaTeX stripped) with the word set of the PDF text
layer (PyMuPDF). Nougat hallucinates fluent but unrelated text on near-blank / figure pages, and the text layer
(even a bad OCR one) is always about the right page, so low overlap = hallucinated or wrong page. Writes
<nougat_dir>/page_check.jsonl (page, words_layer, words_nougat, overlap) and <nougat_dir>/bad_pages.txt
(overlap < BAD) which md_chunk.py excludes.
"""
import json, os, re, sys
import fitz

BAD = 0.35
WORD = re.compile(r"[A-Za-z]{3,}")

def words(s):
    s = re.sub(r"\\\(.*?\\\)|\\\[.*?\\\]|\$[^$]*\$", " ", s, flags=re.S)     # drop math
    s = re.sub(r"\\[A-Za-z]+", " ", s)                                          # stray commands
    return {w.lower() for w in WORD.findall(s)}

def main():
    pdf, nd = sys.argv[1], sys.argv[2]
    doc = fitz.open(pdf)
    bad, rows = [], []
    for p in range(1, len(doc) + 1):
        f = os.path.join(nd, "pages", f"{p:04d}.md")
        if not os.path.exists(f):
            continue
        md = open(f, encoding="utf-8").read()
        if md.startswith("<!-- skipped"):
            rows.append({"page": p, "skipped": True}); continue
        a, b = words(doc[p - 1].get_text()), words(md)
        ov = len(a & b) / max(1, min(len(a), len(b))) if a and b else 0.0
        rows.append({"page": p, "words_layer": len(a), "words_nougat": len(b), "overlap": round(ov, 3)})
        if ov < BAD or len(a) < 15:            # low agreement, or a near-blank page (Nougat invents text there)
            bad.append(p)
    with open(os.path.join(nd, "page_check.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    with open(os.path.join(nd, "bad_pages.txt"), "w") as f:
        f.write("\n".join(map(str, bad)))
    # pages where Nougat returned far fewer words than the text layer: it looped or hit the token cap, so
    # part of the page is missing. Kept (what is there is right) but flagged; md_chunk tags their blocks.
    partial = [r["page"] for r in rows if "overlap" in r and r["page"] not in bad
               and r["words_layer"] > 100 and r["words_nougat"] < 0.6 * r["words_layer"]]
    with open(os.path.join(nd, "partial_pages.txt"), "w") as f:
        f.write("\n".join(map(str, partial)))
    print(f"partial pages (Nougat text much shorter than the text layer): {len(partial)} {partial[:30]}")
    checked = [r for r in rows if "overlap" in r]
    print(f"{os.path.basename(pdf)}: {len(checked)} pages checked, {len(bad)} flagged (overlap < {BAD}): {bad[:30]}")
    if checked:
        ovs = sorted(r["overlap"] for r in checked)
        print(f"overlap median {ovs[len(ovs)//2]:.2f}, p10 {ovs[len(ovs)//10]:.2f}")

if __name__ == "__main__":
    main()
