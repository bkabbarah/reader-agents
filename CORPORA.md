# Candidate problem corpora — supply inventory

**Surveyed 2026-08-21.** Row counts verified against the HuggingFace datasets-server `/size` API
unless the row says otherwise. Following `SYSTEM.md`'s convention: every figure states how it was
obtained, and everything unverified is named as such rather than smoothed over.

**Why this document exists.** The entire current roster is 2,806 problems / 704 playable
candidates (`RESULTS.md`, cross-checked against SYSTEM.md's "pool 704/9 tasks"). Against a 100K
trace target that is a ~140x shortfall *if* traces are counted per problem. This inventory asks:
does problem supply at that scale exist, already formalized, openly licensed?

**Answer: yes, for Lean.** See §1.

---

## 0. The property that decides usefulness: statements-only vs statements+proofs

A corpus that ships **proofs** is close to useless here — the answer leaks directly into the
pipeline, and any "win" built on it is contaminated. A corpus of **unproved statements** is exactly
what this project consumes: a problem the weak Solver can attempt and fail, honestly.

Read the "Format" column with that first.

---

## 1. Lean 4 — formalized, kernel-checkable

| Corpus | Rows | Verified how | License | Format | Contamination note |
|---|---|---|---|---|---|
| **`Goedel-LM/Goedel-Pset-v1`** | **1,732,594** | size API | none declared, open | Lean `formal_statement` + `informal_statement` — **statements only** | trained Goedel-Prover-V2 |
| `kfdong/STP_Lean_0320` | 3,262,558 | size API | MIT | statements **+ proofs** — leaks | contains Lean Workbook |
| `Goedel-LM/SFT_dataset_v2` | 1,745,010 | size API | Apache-2.0 | statements **+ proofs** — leaks | Goedel-V2 training data |
| `AI-MO/NuminaMath-LEAN` | 104,155 | size API | Apache-2.0 | statements + `formal_proof` (**strip the proof column**) | newer, Kimina line |
| `Goedel-LM/RL_dataset_V2` | 98,632 | size API | Apache-2.0 | **statements only** | Goedel-V2 RL set |
| `internlm/Lean-Workbook` | 140,124 claimed | **card only** — parquet preview shows 25,214 | Apache-2.0 | mostly statements only | trained essentially every recent prover |
| `deepseek-ai/DeepSeek-Prover-V1` | 27,503 | size API | DeepSeek license | statements + proofs | trained DeepSeek-Prover |
| `quinn-dougherty/fvapps` (FVAPPS) | 4,715 total / 1,083 curated | **paper only** — gated | MIT, gated | Lean statements with `sorry`, **no proofs** | APPS-derived; **project had it, dropped it** |

**`Goedel-Pset-v1` is the headline: 1.73M already-formalized statements with no proofs attached** —
~620x the current roster, in the format the pipeline already consumes.

⚠️ **`Lean-Workbook` is partly spent**: the repo's `lean_goedel` task already builds on
`Goedel-LM/Lean-workbook-proofs` (29,750 rows, size API), referenced 9x in-repo.

---

## 2. Natural-language math — checkable by exact numeric answer

| Corpus | Rows | Verified how | License | Checkable? |
|---|---|---|---|---|
| `nvidia/OpenMathInstruct-2` | 21,972,791 rows (~592K unique problems, **paper only**) | size API | CC-BY-4.0 | numeric answer |
| `nvidia/OpenMathReasoning` | 5,678,317 | size API | CC-BY-4.0 | numeric answer (proof-type rows not) |
| `AI-MO/NuminaMath-1.5` | 896,215 | size API | Apache-2.0 | numeric answer; clean `answer` column |
| `AI-MO/NuminaMath-CoT` | 859,594 | size API | Apache-2.0 | answer embedded in solution text (extraction needed) |
| `PrimeIntellect/verifiable-math-problems` | 777,457 | size API | none declared | numeric + `verification_info` |
| `SynthLabsAI/Big-Math-RL-Verified` | 251,122 | cardData (gated) | Apache-2.0, gated | verified closed-form answer + llama8b solve-rate |
| `zwhe99/DeepMath-103K` | 103,022 | size API | MIT | numeric; **authors claim decontaminated** |

**Note:** these are *natural language*, so using them in the Lean pipeline requires autoformalization
first. `Goedel-Pset-v1` skips that step entirely — relevant to a 2-week budget.

`Big-Math-RL-Verified` carries a per-problem **llama8b solve rate**, which is a ready-made proxy for
the weak-solver gap — potentially a cheap pre-filter before spending a full baseline ladder.

---

## 3. Code — checkable by test suite

| Corpus | Rows | Verified how | License | Test quality |
|---|---|---|---|---|
| `nvidia/OpenCodeInstruct` | 1,400,000 | size API | CC-BY-4.0 | LLM-generated tests, variable; has `average_test_score` to filter on |
| `PrimeIntellect/verifiable-coding-problems` | 144,169 | size API | none declared | executable tests |
| **`open-r1/codeforces`** | 10,024 total / **8,760 verifiable** | size API | CC-BY-4.0 | **best found** — complete official tests + generated checkers for special-judge problems |
| `BAAI/TACO` | 26,443 | cardData (script dataset) | Apache-2.0 | **known noisy** |
| `likaixin/TACO-verified` | 12,898 | size API | MIT | cleaner TACO subset |
| `deepmind/code_contests` | ~13.3K train (**"around 13000"**, exact count unverified) | repo statement | CC-BY-4.0 | good — includes generated tests | **already in roster** |
| `codeparrot/apps` | 10,000 | card (script dataset) | MIT | **known flaky/underspecified** |
| `nvidia/OpenCodeReasoning` | 735,255 claimed / 337,766 via API | **conflicting** | CC-BY-4.0 | tests NOT included — must join back to source sets |

---

## 4. Other verifiers

| Corpus | Rows | Notes |
|---|---|---|
| `microsoft/FStarDataSet` | 32,054 | F* definition-synthesis goals. Niche, **low contamination** — a genuinely fresh family. |
| `microsoft/Verus_Training_Data` | **unverified** (no viewer) | Verus SFT + trajectories, SAFE/AutoVerus line, updated Feb 2026 |
| `metareflection/dafny-disco` | 81,342 | content unaudited; appears mined/synthetic, **not problem-shaped** |
| `hath995/DafnyGithub-Dataset` | 106,404 | scraped GitHub Dafny — **not problem-shaped** |
| `wendy-sun/DafnyBench` | 782 | **already in roster** |

**No large curated Verus or Coq/Rocq *problem* corpus exists on the Hub.** Dafny beyond DafnyBench
is scraped code, not problems. `theostos/pile-of-rocq` (47.3M) is proof-step metadata, not problems.

---

## 5. Explicitly NOT verified

Recorded rather than smoothed over, per SYSTEM.md convention:

- Exact `code_contests` train count — parquet conversion partial; repo says "around 13000".
- `OpenCodeReasoning` full count — card says 735,255, API reports 337,766.
- `Lean-Workbook` 140,124 — card claim; parquet holds 25,214.
- FVAPPS per-split counts — dataset is gated; 4,715 / 1,083 come from the paper.
- `microsoft/Verus_Training_Data` row counts — no viewer available.
- `OpenMathInstruct-2` unique-problem count (~592K) — paper only.
- Content/quality of `dafny-disco` and `DafnyGithub-Dataset` — unaudited.
- **`Goedel-LM/Goedel-Pset-v1-solved` returns 401** — removed or made private.
- Tooling note: the HF MCP server was connected but **its tools were not actually exposed to the
  surveying agent**; every number above came from the public datasets-server / Hub JSON APIs. The
  figures stand; the MCP's usefulness remains untested.

### Re-verifying any row
```bash
curl -s "https://datasets-server.huggingface.co/size?dataset=<HF_PATH>" | python -m json.tool
curl -s "https://huggingface.co/api/datasets/<HF_PATH>" | python -m json.tool | head -40
```

---

## 6. Interpretation

**If Alex confirms problem-level counting, supply stops being the blocker.** 1.73M formalized,
proof-free Lean statements exist today under an open license — the constraint moves back to win
rate and throughput, which is where the harness work already points.

**Contamination needs measuring, not assuming.** Goedel-Pset trained Goedel-Prover-V2, but our
Solver is Qwen3.5-9B — a different model. Contamination only matters relative to *our* Solver, and
the baseline ladder measures it directly: a problem the Solver solves instantly is either easy or
memorized, and either way it leaves the candidate pool.

**Three fresh-family candidates worth a look for paper breadth:** F* (`FStarDataSet`, low
contamination), `open-r1/codeforces` verifiable split (best test quality found anywhere in this
survey), and FVAPPS — which this project *already had and dropped*, and which is Lean-formalized
with no proofs. Worth learning why it was cut before assuming it should return.

## TheoremGraph stage 1 (P3) — acquired 2026-09-01 (Bashar-approved setup card)
- Location: `bashar@vm-bashar-3:/shared/theoremgraph/` (box, not laptop). Source: HF `uw-math-ai/math-graph` @ main, CC BY 4.0 (verified in THEOREMSEARCH-PROBE.md).
- Files (sizes match HF tree API exactly; SHA-256 in MANIFEST.txt on the box): informal_dependency.csv 2.37GB · formal_dependency.csv 1.05GB · statement_formal.csv 89.5MB · paper_lean_community.csv 8.3KB · paper_lean_repo.csv 3.8KB. Headers verified against probed schemas.
- Stage 2 (awaits 1TB or explicit OK): paper_arxiv.csv 4.03GB, statement_informal.csv 5.04GB, slogan.csv 1.05GB.
- Note: informal_dependency exhibits our v0.4 `cited-document` pattern natively (cite_key + dep_name item, null dep_id) with per-edge method provenance — direct schema-mapping path.

## Trench, Introduction to Real Analysis (P6 textbook lane) — acquired 2026-09-02
- `corpus/trench-ra/` — manual download by Bashar from https://digitalcommons.trinity.edu/mono/7/ (Cloudflare blocks automation); original zip kept as `_source.zip`; nested `trench-latex.zip` is a broken multipart fragment (ignore).
- License: **CC BY-NC-SA 3.0 Unported** (stated in the LaTeX preamble, lines 61–62; solutions manual explicitly excluded — not included here). NonCommercial → note for redistribution/licensing gates.
- Content: `TRENCH_REAL_ANALYSIS.tex` (1.3 MB, single file; the `EPS/` copy differs only in preamble paths — use the root one) + two supplement chapters (improper functions 106 KB, Lagrange multipliers 122 KB) + 78 EPS figures + 2 .sty.
- Markup is custom, not amsthm-standard: chapters via `\setcounter{chapter}{N}` + `\chaptertitle{}`; proofs `\proof … \bbox` (365 / 349); ~253 `\begin{theorem}`, 29 lemma, 25 corollary, 177 definition, 317 example per copy. NaturalProofs reported 298 theorem-like statements / 235 proofs / 86 definitions from this book at 1.6 explicit refs per proof — the natural head-to-head test for our reader-protocol extraction.
- 2026-09-02: added `corpus/naturalproofs/naturalproofs_trench.json` (1.0MB, Zenodo 4902289, CC BY-SA) for the Trench head-to-head; `naturalproofs_stein.json` download returned 14KB (likely an error page) — not used.

## TheoremGraph license question — RESOLVED 2026-09-03 (live HF cards + paper §Data availability)
Three separate UW releases were being conflated:
- `uw-math-ai/math-graph` (the 16.8GB graph; what we pulled 3.5GB of): **CC BY 4.0** on the card, not gated (lastModified 2026-06-28). README §"Content licensing & gating": "The graph structure (statements' existence, dependencies, metadata) is released openly. Statement content … is populated only for papers carrying an open, redistributable license (CC0, CC BY, or CC BY-SA); otherwise these fields are NULL … per-record reuse of statement content is governed by each statement's source license" (kept in `paper_arxiv.csv.license`).
- `uw-math-ai/theorem-matching` (the 23,399 judged formal–informal matches): the PAPER says "gated for non-commercial research … CC-BY-NC-SA-4.0"; the LIVE card (2026-06-26) says **CC BY-SA 4.0**, not gated. Live card is more permissive; cite the paper's wording if in doubt.
- `uw-math-ai/theorem-search-dataset` (TheoremSearch's 9.2M statements): **CC BY-SA 4.0** (our lit note said CC BY/CC0 — corrected).
**Operative for us:** dependency tables + statement_formal (Lean, Mathlib Apache 2.0) already on VM-3 are usable under CC BY 4.0 with attribution. Stage-2 informal statement bodies: only open-licensed papers carry text (NULL otherwise); anything CC BY-SA we redistribute inherits share-alike. Nothing NC applies to what we hold.

## Batch 0 — Tim's six expert-evaluated textbooks (all six received 2026-09-03 via Berkeley library access, most recent editions; **CLEARED to process by Bashar 2026-09-03 (his call; lawyer check no longer gating)**)
| area | book | publisher/series | status |
|---|---|---|---|
| Group theory | Armstrong, *Groups and Symmetry* | Springer UTM | **on disk** `batch0/groups-and-symmetry-armstrong.pdf` (13 MB) — untouched |
| Group theory | Dixon & Mortimer, *Permutation Groups* | Springer GTM 163 | **on disk** `corpus/batch0/Permutation_groups_Dixon_Mortimer.pdf` (8.8 MB, from Bashar) — untouched |
| Elliptic curves | Silverman & Tate, *Rational Points on Elliptic Curves* | Springer UTM | **on disk** `batch0/rational-points-on-elliptic-curves-silverman-tate.pdf` (24 MB) — untouched |
| Elliptic curves | Silverman, *The Arithmetic of Elliptic Curves*, 2nd ed. | Springer GTM 106 | **on disk** `batch0/the-arithmetic-of-elliptic-curves-silverman-2ed.pdf` (5.6 MB) — untouched |
| Stochastic processes | Chung & AitSahlia, *Elementary Probability Theory…*, 4th ed. | Springer UTM | **on disk** `batch0/elementary-probability-theory-chung-aitsahlia-4ed.pdf` (33 MB) — untouched |
| Stochastic processes | Karatzas & Shreve, *Brownian Motion and Stochastic Calculus*, 2nd ed. | Springer GTM 113 | **on disk** `batch0/brownian-motion-and-stochastic-calculus-karatzas-shreve-2ed.pdf` (41 MB) — untouched |
Rule in force: no publisher PDF is opened, chunked, or copied to any box until Alex reports the company-lawyer answer (Imperial's copyright team: UK-only processing; visiting-researcher / UK-server workarounds discussed). Expert evaluators lined up by Tim per area. Edition/year metadata to be verified before use as book-level date bounds.
- 2026-09-03 text-layer check (nothing else opened): all batch-0 files carry a text layer. Six are **scans with an OCR layer** (generic Times/Helvetica font names, one page image per page): Armstrong 197 pp; Dixon & Mortimer 360 pp (`permutation-groups-dixon-mortimer.pdf`, canonical — the earlier `Permutation_groups_Dixon_Mortimer.pdf` is a 2-up scan, 178 sheets, superseded); Silverman & Tate 292 pp; Chung & AitSahlia 4ed 411 pp; Karatzas & Shreve 2ed 490 pp. One is **born-digital LaTeX** (CMR/CMMI fonts): Silverman, *Arithmetic of Elliptic Curves* 2ed, 525 pp. Implication: header detection on the six scans must use text patterns (numbered "Theorem x.y.z") rather than font weight; math in OCR layers will be noisy → reader pass reads prose, formulas need the math-aware path.
