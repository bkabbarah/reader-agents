#!/usr/bin/env python3
"""pdf_chunk.py - segment a math textbook PDF into statement/proof blocks using font metadata + a
per-book style profile (the only book-specific part). Deterministic; no LLM.

usage: pdf_chunk.py <pdf> <profile-name> <out.jsonl>
Profile = header regex + which font weight marks headers, how proofs open, what marks QED.
Output rows: {kind, label, page, statement_text, proof_text|None, proof_status, spans}
"""
import fitz, json, re, sys
from pathlib import Path

PROFILES = {
    # Springer-like / LaTeX amsthm defaults: bold "Theorem 2.3.4." header, italic "Proof." opener, □ (Dingbats) terminator
    "amsthm-bold": {
        "header": re.compile(r"^(Theorem|Lemma|Proposition|Corollary|Definition|Claim)\s+(\d+(?:\.\d+)*)\.?"),
        "header_font": "Bold",
        "skip_header": re.compile(r"^(Example|Exercise|Remark|Note|Figure|Table)\b"),
        "proof_open": re.compile(r"^Proof\b"),
        "proof_font": "Italic",
        "qed_font": "Dingbats",
    },
    # Trench-style: header AND statement set in bold (CMBX), often with dropped spaces ("Theorem1.2.2Let…");
    # "Proof" is a bold line; no QED glyph — a proof ends at the next bold header/section/exercise line
    "bold-statement": {
        "header": re.compile(r"^(Theorem|Lemma|Corollary|Definition|Claim)\s*(\d+(?:\.\d+)*)\s*"),
        "header_font": "CMBX",
        "skip_header": re.compile(r"^(Example|Exercises?|Remark|Note|Figure|Table|\d+\.\d+\s*[A-Z]|\d+\.\s*$)"),
        "proof_open": re.compile(r"^Proof\b"),
        "proof_font": "CMBX",
        "qed_font": None,
        "statement_bold_only": True,
    },
}


# ---- OCR-text profiles (font-agnostic): headers by text pattern; statement runs until the proof opener /
# next header / max_stmt_lines; proof runs until next header / section / exercise / QED text. One per batch-0 book.
KW = r"(Theorem|Lemma|Proposition|Corollary|Definition|Claim)"
def _ocr(header, proof_open=r"^(PROOF|Proof)\s*[.:]?\s*", skip=r"^(EXAMPLE|Example|Exercises?|EXERCISES|Remark|REMARK|Notes?|Chapter|CHAPTER)", max_stmt_lines=14):
    return {"font_agnostic": True, "header": re.compile(header), "proof_open": re.compile(proof_open),
            "skip_header": re.compile(skip), "section": re.compile(r"^\d+\.\d+\s+[A-Z][a-z]"), "max_stmt_lines": max_stmt_lines,
            "qed_text": re.compile(r"(∎|□|■|Q\.E\.D\.|QED)\s*$")}
PROFILES.update({
    "ocr-number-first":  _ocr(rf"^(\d+\.\d+)\s+{KW}\.?\s*"),                      # Karatzas–Shreve: "1.1 Definition."
    "ocr-paren-number":  _ocr(rf"^\((\d+\.\d+)\)\s*{KW}\.?\s*"),                 # Armstrong: "(5.1) Theorem."
    "ocr-word-letter":   _ocr(rf"^{KW}\s+(\d+\.\d+[A-Z]?)\.?\s*"),                 # Dixon–Mortimer: "Theorem 1.4A."
    "ocr-word-chapter":  _ocr(rf"^{KW}\s+(\d+)\.\s*"),                            # Silverman–Tate, Chung: "Lemma 1."
    "ocr-word-dotted":   _ocr(rf"^{KW}\s*(\d+(?:\.\d+)+)\.?\s*"),                 # Silverman 2ed: "Proposition 1.7."
    # Silverman–Tate: NAMED, unnumbered results — "Mordell's Theorem.", "Nagell-Lutz Theorem. Let", "Proposition.", "Corollary. (a)"
    "ocr-named":         _ocr(r"^((?:[A-Z][A-Za-z'’\-]*\s+){0,4}(Theorem|Proposition|Corollary|Lemma|Definition))\s*(\d+)?\.\s+"),
})

def lines_of(doc):
    """Yield (page, font, size, text, has_qed, y) per rendered line."""
    for pno in range(doc.page_count):
        for b in doc[pno].get_text("dict")["blocks"]:
            if b.get("type") != 0:
                continue
            for ln in b["lines"]:
                spans = [s for s in ln["spans"] if s["text"].strip()]
                if not spans:
                    continue
                qed = any(s["font"].startswith("Dingbats") for s in spans) if True else False
                text = "".join(s["text"] for s in spans).replace(chr(0xFB01), "fi").replace(chr(0xFB02), "fl").replace(chr(0xFB00), "ff").replace(chr(0xFB03), "ffi").strip()
                yield pno + 1, spans[0]["font"], round(spans[0]["size"], 1), text, qed, ln["bbox"][1]

def furniture(doc, P):
    """Running headers/footers: short lines in the top/bottom 9% of the page that recur on >= 6 pages.
    Structural lines (theorem headers, proof openers) are never furniture, however often they recur."""
    from collections import Counter
    c, pages = Counter(), {}
    heights = [pg.rect.height for pg in doc]
    for pno, _, _, text, _, y in lines_of(doc):
        h = heights[pno - 1]
        if not (y < 0.09 * h or y > 0.91 * h):
            continue
        if P["header"].match(text) or P["proof_open"].match(text):
            continue
        t = re.sub(r"\d+", "#", text.strip())
        if len(t) < 70 and pno not in pages.setdefault(t, set()):
            pages[t].add(pno); c[t] += 1
    return {t for t, n in c.items() if n >= 6}

def chunk(pdf, profile):
    P = PROFILES[profile]
    doc = fitz.open(pdf)
    FURN = furniture(doc, P)
    blocks, cur, proof = [], None, None
    def close_stmt():
        nonlocal cur
        if cur:
            cur["statement_text"] = " ".join(cur["_s"]).strip(); cur.pop("_s"); blocks.append(cur); cur = None
    def close_proof():
        nonlocal proof
        if proof and blocks:
            tgt = proof["_owner"]
            tgt["proof_text"] = " ".join(proof["_p"]).strip(); tgt["proof_status"] = "proof-env"; proof = None
    FA = P.get("font_agnostic", False)
    INLINE = re.compile(r"(?<=[.:;)\]])\s+(PROOF|Proof)\s*[.:]\s+")
    def split_inline(text):
        m = INLINE.search(text)
        return (text[:m.start()].rstrip(), text[m.end():]) if (FA and m) else (text, None)
    for page, font, size, text, qed, y in lines_of(doc):
        if re.fullmatch(r"\d{1,4}", text.strip()) or re.sub(r"\d+", "#", text.strip()) in FURN:
            continue                                     # page numbers / running headers
        head, tail = split_inline(text)
        if tail is not None and cur is not None and proof is None:
            cur["_s"].append(head); close_stmt()
            proof = {"_owner": blocks[-1], "_p": [tail]}
            continue
        if FA and P["qed_text"].search(text): qed = True
        m = P["header"].match(text)
        if m and (FA or P.get("header_font", "NOFONT") in font):
            close_proof(); close_stmt()
            g = m.groups()
            if len(g) == 3 and g[0] and g[1] and g[0].endswith(g[1]):          # ocr-named: (full name, keyword, optional number)
                kind, label = g[1], (g[0] + (" " + g[2] if g[2] else "")).strip()
            else:
                kind, label = (g[0], g[1]) if g[0][:1].isalpha() else (g[1], g[0])   # word-first vs number-first
            cur = {"kind": kind.lower(), "label": label, "page": page, "_s": [text[m.end():].strip()],
                   "proof_text": None, "proof_status": "omitted"}
            continue
        if P["skip_header"].match(text) and (FA or P.get("header_font", "NOFONT") in font):
            close_proof(); close_stmt(); continue
        if FA and P["section"].match(text):
            close_proof(); close_stmt(); continue
        if P["proof_open"].match(text) and (FA or P.get("proof_font", "NOFONT") in font) and (blocks or cur):
            close_stmt()
            proof = {"_owner": blocks[-1], "_p": [P["proof_open"].sub("", text, 1).lstrip(". ")]}
            if qed: close_proof()
            continue
        if proof is not None:
            if P.get("qed_font") is None and P.get("header_font", "NOFONT") in font and (P["skip_header"].match(text) or re.match(r"^\d+\.\d+", text)):
                close_proof(); continue          # no QED glyph: next bold section/exercise header ends the proof
            proof["_p"].append(text)
            if qed: close_proof()
        elif cur is not None:
            if FA and len(cur["_s"]) >= P["max_stmt_lines"]:
                close_stmt(); continue
            if P.get("statement_bold_only") and P.get("header_font", "NOFONT") not in font and not any(f in font for f in ("CMMI", "CMSY", "CMR", "CMEX", "CMMIB", "CMBSY")):
                close_stmt(); continue           # statement body = bold lines (+ math lines set in CM math fonts)
            if size < 10:   # footnotes / page furniture
                continue
            cur["_s"].append(text)
    close_proof(); close_stmt()
    return blocks

if __name__ == "__main__":
    pdf, prof, out = sys.argv[1], sys.argv[2], sys.argv[3]
    blocks = chunk(pdf, prof)
    with open(out, "w", encoding="utf-8") as f:
        for b in blocks:
            f.write(json.dumps(b, ensure_ascii=False) + "\n")
    from collections import Counter
    print(f"{Path(pdf).name}: {len(blocks)} blocks; kinds {dict(Counter(b['kind'] for b in blocks))}; with proof {sum(1 for b in blocks if b['proof_text'])}")
