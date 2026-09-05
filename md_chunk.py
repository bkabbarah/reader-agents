"""Chunk Nougat markdown (one .md per page from nougat_ocr.py) into statement/proof blocks.

usage: md_chunk.py <nougat_dir> <out blocks.jsonl> [--named]

Same record schema as pdf_chunk.py (kind, label, page, statement_text, proof_text, proof_status) so the reader
prep and the Audit Desk consume it unchanged. Text keeps Nougat's LaTeX (\\( \\), \\[ \\]) so MathJax can render it.
Nougat is inconsistent about header markup even within one book ("**2.8**: **Lemma.**", "### 2.17 Problem",
"**3.4 Problem**", "Theorem 1.4A."), so headers are matched on the de-starred, de-hashed line.
--named additionally accepts unnumbered named results ("Mordell's Theorem.", "Nagell-Lutz Theorem. Let ...").
"""
import glob, json, os, re, sys

KW = r"(Theorem|Lemma|Proposition|Corollary|Definition|Claim|Problem|Exercise|Example|Remark|Note|Notation)"
NUM = r"\(?(\d+(?:\.\d+)*[A-Za-z]?)\)?"
# number-first ("2.8 Lemma."), word-first ("Lemma 2.8."), bare-number ("(5.1) Theorem.")
HEAD_NF = re.compile(rf"^{NUM}[.:]?\s+{KW}\b[.:]*\s*(.*)$")
HEAD_WF = re.compile(rf"^{KW}\s*(?:{NUM})?\s*[.:]*\s*(.*)$")
HEAD_NAMED = re.compile(r"^((?:[A-Z][A-Za-z'’\-]*\s+){1,4}(Theorem|Lemma|Proposition|Corollary))\s*[.:]\s*(.*)$")
PROOF = re.compile(rf"^(?:_|\*)*\s*(PROOF|Proof)(?:\s+of\s+(?:the\s+)?(?:(?i:{KW})\s*{NUM})?[^.:]{{0,60}})?\s*[.:]*\s*(?:_|\*)*\s*(.*)$")
QED = re.compile(r"(\\qed|\\blacksquare|\\square|∎|□|■|Q\.E\.D\.)[\s\\\]\)\$]*$")
SECTION = re.compile(r"^#{1,6}\s")
# after "Theorem 3.2B" (optionally "(ii)"), these words mean a sentence ABOUT the theorem, not its statement
PROSE_VERB = re.compile(r"^\s*(?:\([ivxa-z]{1,4}\)\s*)?(shows?|and|then|enables?|raises?|asserts?|says?|gives?|implies|yields?|"
                        r"is|are|was|were|has|have|holds?|follows?|coupled|can|could|characterizes?|tells?|now|also|thus|so|"
                        r"provides?|states?|guarantees?|ensures?|applies|applied|together|above|below|will|may|does|do|of the)\b")
# books without a QED glyph (Dixon-Mortimer, Chung) end proofs in words; the paragraph containing one closes the proof
QED_PHRASE = re.compile(r"(?i)\b(this (completes|proves|establishes) the (proof|theorem|lemma|proposition|corollary|result)|"
                        r"which (completes|proves) the (proof|theorem|lemma|proposition|result)|the proof is complete|"
                        r"as (required|claimed|desired|asserted)\.|completing the proof)")
# "## Chapter 3 …", "## 6 Mean, Variance…", "### 5.2 …", "#### 8.2.2 …", "## Chapter III" (Silverman AEC): the chapter is the
# first numeric/roman component of any numbered heading, so a heading whose "Chapter N" Nougat garbled is repaired by
# the next numbered section heading.
CHAPTER = re.compile(rf"^#{{1,6}}\s*(?:Chapter\s+|CHAPTER\s+)?(\d{{1,2}}|[IVXLC]{{1,5}})(?:\.\d+)*\.?\s+(?!{KW}\b)[A-Z(\\]")   # not "### 2.17 Problem"
# prose that announces the proof is elsewhere / omitted / coming later, rather than giving it
DEFER = re.compile(r"(?i)\b(proof|proofs|method used to prove|reader is referred|we omit|left (to|as an exercise)|"
                   r"can be found in|will be (given|proved|established)|is deferred|requires the following|"
                   r"is (an )?(easy|immediate|direct|straightforward) consequence|follows (immediately|directly|at once) from)\b")
# paragraph shapes that continue a statement: display math, equation tags, enumerations, italic runs
CONT = re.compile(r"^\s*(\\\[|\$\$|\(\d+(?:\.\d+)*\)|\(?[ivx]+\)|\(?[a-z]\)|\d+\.\s|_|\*|\\begin)")
BOUNDARY = re.compile(r"^\s*(?:\*\*|_)?\s*(Definition|Theorem|Lemma|Proposition|Corollary|Remark|Example|Examples|Exercise|Exercises|Notation)s?\s*(?:\*\*)?\s*[.:]")
KEEP = {"theorem", "lemma", "proposition", "corollary", "definition", "claim"}
SOFT = {"problem", "exercise"}                  # kept as items (kind=exercise) but never carry a proof
MAX_STMT_PARAS = 8
NUMERIC = re.compile(r"^[IVXLC]*\.?\d+(\.\d+)*[A-Za-z]?$")     # a book-assigned number like 3.2.3, 1.4A, III.1.7
IMPLICIT_PROOFS = False  # --implicit-proofs: unmarked prose after an italic statement counts as its proof (Chung only)
UNLABELED = False        # --labels-from: accept bare "**Theorem**.:" headers (margin numbers Nougat drops) and
                         # recover labels by aligning with the PDF text-layer blocks on the same page

class _Paren:
    def __init__(self, inner, end): self._inner, self._end = inner, end
    def group(self, i=1): return self._inner
    def end(self): return self._end

def leading_paren(rest, limit=120):
    """A balanced parenthetical at the start of the statement text: returns an object with .group(1) = inner text
    and .end() = index just past it and any trailing '.:' punctuation; None if absent or unbalanced."""
    m = re.match(r"^\s*\(", rest)
    if not m:
        return None
    depth, i = 0, m.end() - 1
    while i < min(len(rest), limit + m.end()):
        if rest[i] == "(":
            depth += 1
        elif rest[i] == ")":
            depth -= 1
            if depth == 0:
                inner = rest[m.end():i].strip()
                j = i + 1
                while j < len(rest) and rest[j] in ".: ":
                    j += 1
                return _Paren(inner, j) if 2 <= len(inner) <= limit else None
        i += 1
    return None

def prose(s):
    s = re.sub(r"\\\(.*?\\\)|\\\[.*?\\\]|\$[^$]*\$", " ", s, flags=re.S)
    return re.sub(r"[^a-z ]", "", s.lower())

def assign_labels(blocks, textlayer_path):
    """Give unlabeled/mislabeled blocks the label of the best-matching text-layer block within +-1 page."""
    import difflib
    tl = [json.loads(l) for l in open(textlayer_path, encoding="utf-8")]
    # keys are (kind, label): Dixon-Mortimer numbers Theorem 1.4A and Corollary 1.4A alike
    tl_keys = {(t["kind"], t["label"]) for t in tl}
    used, n_ok = set(), 0
    # pass 1: a numeric label Nougat did keep, and which the text layer also has, is trusted as is
    for b in blocks:
        lab = b["label"].split("#")[0].upper()                  # Nougat lowercases letter suffixes: 1.4a -> 1.4A
        if lab and (b["kind"], lab) in tl_keys and (b["kind"], lab) not in used:
            b["label"] = lab; b["label_source"] = "nougat"; used.add((b["kind"], lab)); n_ok += 1
    # pass 2: statement similarity within +-1 page
    for b in blocks:
        if b.get("label_source"):
            continue
        cands = [t for t in tl if abs(t["page"] - b["page"]) <= 1 and (t["kind"], t["label"]) not in used]
        best, score = None, 0.0
        pb = prose(b["statement_text"])[:400]
        for t in cands:
            r = difflib.SequenceMatcher(None, pb, prose(t["statement_text"])[:400]).ratio()
            if t["kind"] == b["kind"]:
                r += 0.05
            if r > score:
                best, score = t, r
        if best and score >= 0.45:
            b["label"], b["label_source"] = best["label"], f"text-layer match {score:.2f}"
            if best["kind"] != b["kind"]:
                b["kind_textlayer"] = best["kind"]
            used.add((best["kind"], best["label"])); n_ok += 1
    # pass 3: page order - the only unused same-page text-layer label of the same kind
    for b in blocks:
        if b.get("label_source"):
            continue
        cands = [t for t in tl if t["page"] == b["page"] and (t["kind"], t["label"]) not in used and t["kind"] == b["kind"]]
        if len(cands) == 1:
            b["label"], b["label_source"] = cands[0]["label"], "page-order"; used.add((b["kind"], b["label"])); n_ok += 1
        else:
            n_un = sum(1 for x in blocks if x.get("label_source") == "unmatched") + 1
            b["label_source"] = "unmatched"
            b["label"] = b["name"] if b.get("name") and b["kind"] != "exercise" else f"p{b['page']}-{b['kind'][:3]}{n_un}"
    seen = {}
    for b in blocks:                                            # unique labels (two "(Thue)" theorems -> Thue, Thue#2)
        k = (b["kind"], b["label"]); seen[k] = seen.get(k, 0) + 1
        if seen[k] > 1:
            b["label"] = f"{b['label']}#{seen[k]}"
    print(f"labels from text layer: {n_ok}/{len(blocks)} matched; text-layer had {len(tl)} blocks")
    return blocks

def merge_restatements(blocks):
    """Books that state a lemma early and restate it verbatim before proving it (Silverman-Tate ch. 3): keep the
    first occurrence, give it the later proof, drop the restatement."""
    import difflib
    norm = lambda s: re.sub(r"[^a-z0-9\\{}^_=<>+-]", "", s.lower())     # keep the math, drop spacing/markup noise
    keep, dropped = [], 0
    for b in blocks:
        nb = norm(b["statement_text"])
        dup = None
        if len(nb) > 40 and b["kind"] != "exercise":
            for k in keep:
                if k["kind"] != b["kind"]:
                    continue
                lb, lk = b["label"].split("#")[0], k["label"].split("#")[0]
                if lb and lk and lb != lk and NUMERIC.match(lb) and NUMERIC.match(lk):
                    continue                                    # two distinct book numbers are two results (Trench 3.2.2/3.2.3)
                nk = norm(k["statement_text"])
                L = min(len(nb), len(nk), 300)                  # compare the common prefix: a restatement may be
                if L >= 40 and difflib.SequenceMatcher(None, nb[:L], nk[:L]).ratio() > 0.85:   # followed by a remark
                    dup = k; break
        if dup is None:
            keep.append(b); continue
        dropped += 1
        if b["proof_text"] and not dup["proof_text"]:
            dup["proof_text"], dup["proof_status"] = b["proof_text"], b["proof_status"]
            dup["proof_page"] = b["page"]
        dup.setdefault("restated_on", []).append(b["page"])
    if dropped:
        print(f"merged {dropped} restatements into their first occurrence")
    return keep

MATH = re.compile(r"(\\\(.*?\\\)|\\\[.*?\\\]|\$\$.*?\$\$|\$[^$]*\$)", re.S)

def strip_md(s):
    """Remove bold/italic markers from prose spans only; LaTeX spans (with their _ and *) pass through."""
    out = []
    for i, part in enumerate(MATH.split(s)):
        if i % 2 == 0:
            part = re.sub(r"\*\*|__", "", part)
            part = re.sub(r"(?<![\w\\])_|_(?![\w{])", "", part)
        out.append(part)
    return "".join(out).strip()

def paragraphs(nougat_dir):
    """Yield (page, paragraph_text) across pages in order; a paragraph is a blank-line-separated run."""
    badf = os.path.join(nougat_dir, "bad_pages.txt")
    bad = {int(x) for x in open(badf).read().split()} if os.path.exists(badf) else set()   # from nougat_check.py
    held = None                                   # last paragraph of the previous page, pending page-break merge
    for f in sorted(glob.glob(os.path.join(nougat_dir, "pages", "*.md"))):
        page = int(os.path.basename(f)[:4])
        if page in bad:
            continue
        text = open(f, encoding="utf-8").read()
        if text.startswith("<!-- skipped"):
            continue
        paras, buf = [], []
        for line in text.splitlines() + [""]:
            if line.strip():
                buf.append(line.rstrip())
            elif buf:
                paras.append(" ".join(buf)); buf = []
        if not paras:
            continue
        if held is not None:
            hp, ht = held
            first = paras[0]
            # a page break inside a sentence: previous page ends without terminal punctuation and/or the new page
            # opens with a lowercase fragment ("tion of a right-continuous martingale ...")
            opens_unit = bool(PROOF.match(strip_md(first)) or match_header(first, True))   # never glue "Proof." / a header
            if not opens_unit and (re.match(r"^[a-z]", first) or not re.search(r"[.:;!?\]\)]\s*[_*]*\s*$", ht)):
                paras[0] = ht + " " + first
                paras[0] = re.sub(r"(\w)- (\w)", r"\1\2", paras[0], count=1) if re.match(r"^[a-z]", first) and ht.endswith("-") else paras[0]
            else:
                yield hp, ht
            held = None
        for p in paras[:-1]:
            yield page, p
        held = (page, paras[-1])
    if held is not None:
        yield held

def match_header(text, named):
    """Return (kind, label, rest) if this paragraph opens a numbered/named item, else None."""
    t = strip_md(re.sub(r"^#{1,6}\s*", "", text))
    m = HEAD_NF.match(t)
    if m:
        marked = text.lstrip().startswith(("**", "#", "_"))
        after = t[m.end(2):].lstrip()
        if not (marked or after[:1] in (".", ":", "(", "") or after.startswith("of ")):
            return None                                                 # "2.8 Lemma then yields" is prose
        if PROSE_VERB.match(m.group(3)):
            return None
        return m.group(2).lower(), m.group(1), m.group(3)
    m = HEAD_WF.match(t)
    if m and (m.group(2) or named or UNLABELED):
        marked = text.lstrip().startswith(("**", "#", "_"))            # Nougat bolds real headers
        after = t[m.end(2) if m.group(2) else m.end(1):].lstrip()      # what follows the label
        punct = after[:1] in (".", ":", "(", "") or after.startswith("**")
        if not (marked or punct):
            return None                                                 # "Theorem 3.2B and 3.3A show that ..." is prose
        if not m.group(2) and not marked and after[:1] not in (".", ":"):
            return None                                                 # an unlabeled header is bold or "Theorem." — never "Theorem X (iii) shows"
        if PROSE_VERB.match(m.group(3)):
            return None                                                 # "**Theorem 6.5.1 (iii)** shows that ..." is prose about a theorem
        return m.group(1).lower(), m.group(2) or "", m.group(3)
    if named:
        m = HEAD_NAMED.match(t)
        if m:
            return m.group(2).lower(), m.group(1).strip(), m.group(3)
    return None

def toc_chapters(pdf_path):
    """Chapter start pages from the PDF's own bookmarks (born-digital books): [(start_page, 'III'), ...].
    A level-1 entry whose title starts with a roman numeral, an integer, or a single capital letter (appendix)."""
    import fitz
    out = []
    for level, title, page in fitz.open(pdf_path).get_toc():
        m = re.match(r"^\s*(?:Chapter\s+)?([IVXLC]{1,5}|\d{1,2}|[A-Z])\b[\s.:]", title + " ")
        if level == 1 and m and page > 0:
            out.append((page, m.group(1)))
    return sorted(out)

def chunk(nougat_dir, named=False, chapter_labels=False, toc=None):
    blocks, cur, proof, deferred, n_paras, seen, chapter = [], None, None, None, 0, {}, None
    by_label = {}
    def close():
        nonlocal cur, proof, deferred
        if deferred is not None:                                # "Proof of Theorem 3.13." given after later lemmas
            if proof:
                deferred["proof_text"], deferred["proof_status"] = strip_md(proof), "proof-env"
            deferred, proof = None, None
            return
        if cur:
            cur["statement_text"] = strip_md(cur["statement_text"])
            if proof:
                cur["proof_text"] = strip_md(proof)
                if cur["proof_status"] != "proof-implicit":
                    cur["proof_status"] = "proof-env"
            blocks.append(cur)
            by_label.setdefault((cur["kind"], cur["label"]), cur)
            by_label.setdefault(("*", cur["label"]), cur)
        cur, proof = None, None
    for page, para in paragraphs(nougat_dir):
        if toc:                                                     # bookmarks beat heading heuristics
            chapter = next((c for p, c in reversed(toc) if page >= p), None)
        elif chapter_labels:
            cm = CHAPTER.match(para)
            if cm:
                level = len(para) - len(para.lstrip("#"))
                if level <= 2:                                      # "## Chapter 5 …" / "## 6 Mean, Variance…" sets the chapter
                    chapter = cm.group(1)
                else:                                               # deeper "#### 8.2.2 …" only repairs a garbled chapter
                    try:                                            # heading, by stepping exactly one chapter forward
                        if chapter is not None and int(cm.group(1)) == int(chapter) + 1:
                            chapter = cm.group(1)
                    except ValueError:
                        pass
        h = match_header(para, named)
        if h:
            kind, label, rest = h
            close()
            if kind in SOFT and not label:                      # bare "Exercises" section heading: a break, not an item
                continue
            if kind in KEEP or kind in SOFT:
                if not label:                                   # named result: label = the name
                    label = rest.split(".")[0][:60] if kind not in SOFT else ""
                elif (chapter_labels or toc) and chapter and label.count(".") < 2:
                    label = f"{chapter}.{label}"                # book numbers within chapters: 3.13 -> 1.3.13
                key = (kind, label)
                seen[key] = seen.get(key, 0) + 1
                if seen[key] > 1:
                    label = f"{label}#{seen[key]}"
                cur = {"kind": "exercise" if kind in SOFT else kind, "label": label, "page": page,
                       "statement_text": rest, "proof_text": None, "proof_status": "none",
                       "_italic": kind in KEEP and kind != "definition"
                                  and bool(re.search(rf"(?i:{KW}).{{0,160}}?[\s.:)*]_\S", para))}   # raw para keeps the _
                nm = leading_paren(rest)                                  # "(Doob-Meyer Decomposition)." / "(Daniell (1918), Kolmogorov (1933))" / "(Hasse, Weil)"
                if nm and not re.fullmatch(r"[a-z]|[ivx]+|[A-Z]|\d+", nm.group(1).strip()) and not re.search(r"page \d", nm.group(1)):
                    # attribution/name is metadata: "(Doob-Meyer Decomposition)", "(Daniell (1918), Kolmogorov (1933))", "(Hasse, Weil)";
                    # but "(a)" / "(ii)" enumerations stay in the statement
                    cur["name"] = re.sub(r"\s*\[\d+\]", "", nm.group(1)).strip()     # drop "[1]" citation marks
                    cur["statement_text"] = rest[nm.end():]                              # name is metadata, not statement
                else:
                    # "Corollary to Theorem 2.2.:" / "Definition 4.2.1 of Random Variable." -> name, not statement prefix
                    nm2 = re.match(r"^\s*(?:to|of)\s+((?:(?:Theorem|Lemma|Proposition|Corollary)\s*[\dIVX.]+[A-Za-z]?)|(?:[A-Z][A-Za-z'’\-]*(?:\s+[A-Za-z'’\-]+){0,5}))\s*[.:]+\s*", rest)
                    if nm2:
                        cur["name"] = (("Corollary to " if rest.lstrip().startswith("to") else "") + nm2.group(1)).strip()
                        cur["statement_text"] = rest[nm2.end():]
                n_paras = 1
            continue                                            # example/remark/note: break, not an item
        if SECTION.match(para) or BOUNDARY.match(para):
            close(); continue                                       # a new unit starts here even if we don't keep it
        pm = PROOF.match(strip_md(para))
        if pm:
            t_kind, t_num, body = pm.group(2), pm.group(3), pm.group(4)
            if t_num:                                           # deferred proof: attach to the named block
                close()
                if (chapter_labels or toc) and chapter and t_num.count(".") < 2:
                    t_num = f"{chapter}.{t_num}"
                tgt = by_label.get((t_kind.lower(), t_num)) or by_label.get(("*", t_num))
                if tgt and not tgt["proof_text"]:
                    deferred, proof = tgt, body
                    if QED.search(para):
                        close()
                continue
            if cur and cur["kind"] != "exercise":
                proof = body
                if QED.search(para):
                    close()
                continue
        if proof is not None:
            proof += "\n" + para
            if QED.search(para) or QED_PHRASE.search(para):
                close()
        elif cur:
            if n_paras >= MAX_STMT_PARAS:
                close(); continue
            if cur.get("_stmt_done"):
                continue                                            # commentary between statement and a later "Proof."
            if cur.get("_italic") and not CONT.match(para):
                if DEFER.search(strip_md(para)[:200]):
                    # "The reader is referred to Meyer (1966)…", "The proof of Theorem 3.13 requires the following…"
                    cur["proof_status"] = "deferred-or-omitted"
                    if IMPLICIT_PROOFS:
                        close(); continue
                    cur["_stmt_done"] = True; continue
                if not IMPLICIT_PROOFS:
                    # Statement is over; what follows is discussion unless the book habitually omits "Proof" markers
                    # (Chung). On Trench (LaTeX truth) the implicit rule was wrong 31:3, so it is opt-in. Keep the item
                    # OPEN with the statement frozen so a "Proof." after a figure caption or remark still attaches
                    # (Armstrong 5.1: "Figure 5.2:" sits between statement and proof).
                    cur["_stmt_done"] = True; continue
                # italic statement followed by plain prose with no "Proof." marker: the book just starts proving
                # (Karatzas-Shreve 4.10 Doob-Meyer). Keep it as the proof, flagged implicit.
                proof, cur["proof_status"] = para, "proof-implicit"
                if QED.search(para):
                    close()
                continue
            cur["statement_text"] += "\n" + para; n_paras += 1
    close()
    pf = os.path.join(nougat_dir, "partial_pages.txt")
    partial = {int(x) for x in open(pf).read().split()} if os.path.exists(pf) else set()
    for b in blocks:
        b.pop("_italic", None); b.pop("_stmt_done", None)
        if b["page"] in partial or b.get("proof_page") in partial:
            b["page_partial"] = True                                # OCR of this page is incomplete (see nougat_check)
    return blocks

if __name__ == "__main__":
    src, out = sys.argv[1], sys.argv[2]
    if "--labels-from" in sys.argv:
        UNLABELED = True
    if "--implicit-proofs" in sys.argv:
        IMPLICIT_PROOFS = True
    toc = toc_chapters(sys.argv[sys.argv.index("--toc-chapters") + 1]) if "--toc-chapters" in sys.argv else None
    if toc:
        print("chapters from PDF bookmarks:", toc)
    bl = chunk(src, named="--named" in sys.argv, chapter_labels="--chapter-labels" in sys.argv, toc=toc)
    bl = merge_restatements(bl)
    if "--labels-from" in sys.argv:
        bl = assign_labels(bl, sys.argv[sys.argv.index("--labels-from") + 1])
    with open(out, "w", encoding="utf-8") as f:
        for b in bl:
            f.write(json.dumps(b, ensure_ascii=False) + "\n")
    kinds = {}
    for b in bl:
        kinds[b["kind"]] = kinds.get(b["kind"], 0) + 1
    print(f"{src}: {len(bl)} blocks; kinds {kinds}; with proof {sum(1 for b in bl if b['proof_text'])}")
