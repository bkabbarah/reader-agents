"""Math-aware OCR of a scanned textbook with Nougat (facebook/nougat-small via transformers).

usage: nougat_ocr.py <book.pdf> <out_dir> [--pages A-B] [--batch N]

Writes one Markdown file per page to <out_dir>/pages/NNNN.md (1-based page numbers) and is resumable:
pages that already have a file are skipped. Pages that hit the token cap are flagged in <out_dir>/truncated.txt
so they can be re-run at a higher cap. Runs on CUDA when available, else CPU.
"""
import glob, os, sys, time, torch, pypdfium2 as pdfium
from transformers import NougatProcessor, VisionEncoderDecoderModel

MODEL = "facebook/nougat-small"
MAX_TOKENS = 3072
MIN_WORDS = 15

def main():
    pdf_path, out_dir = sys.argv[1], sys.argv[2]
    global MAX_TOKENS
    pages_arg = sys.argv[sys.argv.index("--pages") + 1] if "--pages" in sys.argv else None
    batch = int(sys.argv[sys.argv.index("--batch") + 1]) if "--batch" in sys.argv else 4
    if "--max-tokens" in sys.argv:                                  # re-run truncated pages with a higher cap
        MAX_TOKENS = int(sys.argv[sys.argv.index("--max-tokens") + 1])
    only = None
    if "--only" in sys.argv:                                        # comma-separated page list; existing files are redone
        only = [int(x) for x in sys.argv[sys.argv.index("--only") + 1].split(",")]
        for p in only:
            f = os.path.join(out_dir, "pages", f"{p:04d}.md")
            if os.path.exists(f):
                os.remove(f)
    os.makedirs(os.path.join(out_dir, "pages"), exist_ok=True)
    for f in glob.glob(os.path.join(out_dir, "pages", "*.tmp")):    # leftovers from an interrupted run
        os.remove(f)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    if dev == "cpu":
        torch.set_num_threads(os.cpu_count() or 4)
    proc = NougatProcessor.from_pretrained(MODEL)
    model = VisionEncoderDecoderModel.from_pretrained(MODEL).to(dev).eval()
    if dev == "cuda":
        model = model.half()
    pdf = pdfium.PdfDocument(pdf_path)
    lo, hi = (1, len(pdf)) if not pages_arg else map(int, pages_arg.split("-"))
    todo = [p for p in (only or range(lo, hi + 1)) if not os.path.exists(os.path.join(out_dir, "pages", f"{p:04d}.md"))]
    # Near-blank pages (title, blank, full-page figures) make Nougat hallucinate whole chapters: skip any page whose
    # own text layer has fewer than MIN_WORDS words, writing a stub so the run stays resumable.
    try:
        import fitz
        doc = fitz.open(pdf_path)
        skipped = []
        for p in list(todo):
            if len(doc[p - 1].get_text().split()) < MIN_WORDS:
                with open(os.path.join(out_dir, "pages", f"{p:04d}.md"), "w", encoding="utf-8") as f:
                    f.write(f"<!-- skipped: text layer has < {MIN_WORDS} words -->\n")
                skipped.append(p); todo.remove(p)
        if skipped:
            print(f"skipped {len(skipped)} near-blank pages: {skipped[:20]}{'...' if len(skipped) > 20 else ''}", flush=True)
    except ImportError:
        pass
    print(f"{os.path.basename(pdf_path)}: {len(pdf)} pages, {len(todo)} to do on {dev}", flush=True)
    t_start = time.time()
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        t0 = time.time()
        imgs = [pdf[p - 1].render(scale=2).to_pil().convert("RGB") for p in chunk]
        px = proc(imgs, return_tensors="pt").pixel_values.to(dev)
        if dev == "cuda":
            px = px.half()
        with torch.no_grad():
            ids = model.generate(px, min_length=1, max_new_tokens=MAX_TOKENS,
                                 bad_words_ids=[[proc.tokenizer.unk_token_id]])
        texts = proc.batch_decode(ids, skip_special_tokens=True)
        for p, txt, row in zip(chunk, texts, ids):
            tmp = os.path.join(out_dir, "pages", f"{p:04d}.md.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(txt)
            os.replace(tmp, tmp[:-4])                             # atomic: a power cut never leaves a half page
            n_tok = int((row != proc.tokenizer.pad_token_id).sum())
            if n_tok >= MAX_TOKENS:                                # this row hit the cap: page text may be cut off
                with open(os.path.join(out_dir, "truncated.txt"), "a") as f:
                    f.write(f"{p}\n")
        done = i + len(chunk)
        rate = (time.time() - t_start) / done
        print(f"pages {chunk[0]}-{chunk[-1]}: {time.time() - t0:.1f}s | {done}/{len(todo)} | "
              f"{rate:.1f} s/page, ~{rate * (len(todo) - done) / 60:.0f} min left", flush=True)

if __name__ == "__main__":
    main()
