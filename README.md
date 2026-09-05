# Textbook extraction pipeline — setup overview

How batch 0 (six Springer textbooks) was turned into audited statement/proof/ingredient data, what runs where, what it costs, and how to add a book. Written 2026-09-05 for the Imperial collaborators. This repository holds the code only; the extracted book text stays in a private data repository (see "Data and licensing"). Set `FLEET_ACCOUNTS` (colon-separated Claude Code config directories) before running `fleet_run.py`.

## The pipeline in one picture

```
PDF (scan or born-digital)
  │  1. OCR            nougat_ocr.py        GPU, ~3 s/page          → nougat/pages/NNNN.md  (markdown + LaTeX)
  │  2. Page QC        nougat_check.py      CPU, seconds            → bad_pages.txt, partial_pages.txt
  │  3. Chunking       md_chunk.py          CPU, seconds, deterministic → blocks_nougat.jsonl  (statement, proof, label, page)
  │  4. Reader         prep_reader_pass.py + fleet_run.py   Claude Opus agents  → ingredients per proof, with evidence quotes
  │  5. Collect        collect_reader_out.py                 → _reader_out_nougat/*.txt
  │  6. Review UI      build_audit_desk.py  → one HTML page (Audit Desk) published as a Claude artifact
  │  7. Answers        ingest_answers.py    reviewer JSON exports, git-tracked → reader precision/recall per field
  └─ 8. Graph          apply_reader_layer.py, linking passes, build_graph.py, export_ripeness_v0.py  (batch 0 not yet linked)
```

Everything is a plain Python script run from the repo root; there is no orchestration framework. Intermediate files are JSONL so any stage can be re-run alone.

## Stage by stage

**1. OCR.** `nougat_ocr.py` runs Meta's Nougat (`facebook/nougat-small`, 250M parameters) through Hugging Face `transformers` (the `nougat-ocr` pip package does not install on Python 3.12). One markdown file per page, resumable, near-blank pages skipped (Nougat invents text on them). Runs in fp16 on a laptop RTX 4050 (6 GB) at 3–5 s/page; CPU is ~60 s/page and not viable for whole books. Batch 0 = 2,275 pages ≈ 2.5 h on the laptop. Nougat's weights are CC-BY-NC; the code is MIT.

**2. Page QC.** `nougat_check.py` compares every page's word set with the PDF's own (bad, but page-true) text layer. Median agreement 0.96–0.99; pages under 0.35 are excluded as hallucinated (front matter, figure pages), pages whose Nougat text is far shorter than the text layer are flagged partial and carry a warning in the review UI.

**3. Chunking.** `md_chunk.py` turns the markdown into statement/proof units. It is regex-based and deterministic, with per-book flags because books differ: chapter-prefixed labels (`--chapter-labels`, or `--toc-chapters <pdf>` to take chapter boundaries from PDF bookmarks when headings are garbled), named theorems (`--named`, Silverman–Tate), label recovery from the text layer when Nougat drops margin numbers (`--labels-from`, Armstrong, Dixon–Mortimer), and opt-in unmarked proofs (`--implicit-proofs`, Chung, which rarely writes "Proof"). It also attaches deferred "Proof of Theorem X" paragraphs, merges verbatim restatements, captures attributions ("(Doob–Meyer Decomposition)") as names, ends proofs at QED glyphs or phrases, and refuses prose *about* a theorem as a header. Measured against two books with LaTeX source (`compare_pdf_latex.py`): Trench statement precision 100%, recall 97%, proof attachment 97%; Lebl 100% / 89% / 93%. `pdf_chunk.py` is the older text-layer chunker, kept for label recovery and as the baseline (84% / 68% recall on the same books).

**4. Reader.** `prep_reader_pass.py batch0` writes one task file per five proofs: a fixed prompt (list every prior result or substantive definition the proof relies on, with an evidence quote, explicit/implicit, confidence; criterion "a result or concept that at some point in history did not yet exist"; citation-only proofs yield `cited-document` ingredients) followed by the statements and proofs. `fleet_run.py` runs the tasks as headless Claude Code calls (`claude -p --model opus --output-format json`) with three workers rotating over Claude Code subscription accounts, cooling an account off when it hits a limit and re-queueing the task. No API keys are used anywhere.

**5. Collect.** `collect_reader_out.py` parses the JSON envelopes (line-first, then a string-aware scan, because LaTeX braces inside quotes break naive parsing), keeps the newest non-empty result per proof, and writes the reader output the UI and the graph consume.

**6. Review UI.** `build_audit_desk.py` builds a single self-contained HTML page: name → field → book → item; statement and proof on the left (MathJax), three questions on the right (genuine statement? strike wrong ingredients; what is missing), a reading-order citation map of the book and a directed neighbourhood of the current item (edges are explicit in-book citations found in the reader's evidence: numbered labels, named results cited as phrases, chapter-local lemma numbers). Progress lives in the reviewer's browser; "Show my answers" exports JSON. The builder refuses to write a page whose script does not parse (node --check). Published as a Claude artifact so external reviewers need no account.

**7. Answers.** Reviewer exports go in `data/audit/batch0-answers/<name>.json` (git history is the audit trail); `ingest_answers.py` reports per-field/book reader precision and flags missing-ingredient notes for follow-up.

**8. Graph.** Reader rows enter the graph as named references with provenance `reader-explicit` / `reader-implicit`; a separate linking pass (Opus judges with 20 blind decoys per pass) resolves names to graph nodes; `build_graph.py` and `export_ripeness_v0.py` produce the graph and the ripeness export with a named `ingredient_policy` (which provenance layers, confidence floor, kinds count). Batch 0 is deliberately not linked until the human evaluations are in, since a reader-prompt change after the evaluations would force a re-run anyway.

**Quality checks that run alongside.** Two LaTeX-truth books in every extraction round (Trench, Lebl). A blind recall audit (`prep_recall_audit.py`, `prep_recall_match.py`, `score_recall.py`): two independent Opus enumerators list ingredients for 30 proofs without seeing the reader, a third judges matches; on batch 0 the reader captured 76% of everything enumerated (71–80% CI), 83% of both-auditor consensus, 232 of 233 of its own ingredients judged legitimate.

## Models

| Role | Model | How it runs |
|---|---|---|
| Page OCR | Nougat-small (Meta, 2023) | local GPU, transformers |
| Reader, judges, linking | Claude Opus (current) | headless Claude Code, subscription seats |
| Literature/tool recon | Claude Sonnet subagents | in-session |
| Math rendering in the UI | MathJax 3 (tex-svg) | CDN, viewer's browser |

## Runtime and cost (batch 0, measured)

| Stage | Size | Wall time | Compute | Money |
|---|---|---|---|---|
| OCR | 2,275 pages, six books | ~2.5 h | laptop RTX 4050 | $0 |
| QC + chunking | 908 items, 622 proofs | minutes | laptop CPU | $0 |
| Reader | 135 tasks (661 proofs, 5/task) | 39 min, mean 52 s/task, 2–3 workers | Claude Code seats | $0 beyond the seats |
| Recall audit | 12 enumerator + 6 judge tasks | ~20 min | Claude Code seats | $0 |
| Review UI | one 3 MB page | seconds | laptop | $0 |
| Hosting | fleet box (Azure VM, 8 cores), shared-drive VM (4 cores, 1 TB requested) | — | existing | existing |

Scaling to Alex's textbook tier (say 200 books, ~80K pages): OCR is ~4 days per pass on the laptop or hours on one 24–80 GB GPU (which also unlocks the 2025–26 document models: olmOCR-2, MinerU 2.5, PaddleOCR-VL); the reader is tens of thousands of proofs, i.e. seat-hours or an API budget, and is the real scaling cost. See `data/litreview/OCR-RECON-SYNTHESIS-2026-09-04.md`.

## Adding a book

1. Put the PDF in `corpus/batch0/` (gitignored). 2. `python nougat_ocr.py <pdf> data/extracted/batch0/<slug>/nougat --batch 8`. 3. `python nougat_check.py <pdf> <that dir>`. 4. Look at three or four pages of the markdown for the header style and pick the `md_chunk.py` flags; run it. 5. `python prep_reader_pass.py batch0:<slug>`, stage the task files and `fleet_run.py` on the fleet box, pull `out/`, `collect_reader_out.py`. 6. Add the book to `FIELDS` in `build_audit_desk.py` with its edition and year, rebuild, republish. If the book has LaTeX source, also run `compare_pdf_latex.py` against it and record the numbers.

## Data and licensing

The PDFs are library/publisher copies processed for research; the extracted text (`data/extracted/batch0/*/blocks_nougat.jsonl`, the reader outputs, the desk page) contains book excerpts and stays in this private repository. A public code-only repository can carry every script and this README; the OCR page directories are already gitignored. Nougat's weights are non-commercial. NaturalProofs, ProofWiki, Stacks, TheoremGraph licences are recorded in `CORPORA.md`.

## Where things are

Scripts at the repo root (names above). State and decisions: `SESSION-STATE.md`; findings ledger: `FINDINGS.md`; schema: `schema/SCHEMA.md`; audits: `data/audit/` (recall reports, desk QA); literature: `data/litreview/`, `RELATED-WORK-v2-2026-09-03.md`.
