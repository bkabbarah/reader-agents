# Schema changelog

## v0.4.2 — 2026-09-02 (reader protocol + Bashar's granularity question)
- **`ingredient_policy` added as an export parameter** (provenance set, min_confidence, kinds, exclude_techniques, hub_cutoff). Motivation: reader-protocol extraction (finding #40) records ingredients at every granularity with confidence and kind; which ones "count" is benchmark-dependent and must not be a human per-edge decision. Named policies: `explicit-only` (NaturalProofs-comparable), `strict-ripeness-v1`, `generous-retrieval-v1`. Every reported number names its policy.
- **Reference provenance vocabulary extended**: `reader-explicit` / `reader-implicit` (the reader layer), kept distinct from `explicit-reference` so the NaturalProofs-style layer is always recoverable.
- Hub-degree demotion codified as the mechanical guard for the ingredient criterion.

## v0.4.1 — 2026-09-01 (notes from the TheoremGraph mapping, 24M references)
- **`meta` passthrough bag blessed, with constraint**: extraction may carry a source-specific `meta: {}` on any record (their edge_type/role, file paths); NOTHING derived (freeze, ripeness, exports) may ever read from it — it exists for audit/debug only. Violating this constraint is a schema bug.
- **Flat reference serialization declared legal**: a reference owned by a proof/statement may be stored as one row `{owner, proof?, ...ref}` instead of inside a `uses[]`/`refs[]` array — same shape, streaming-friendly at 10M+ scale. Assembly into arrays is a derived view.
- Validation note: TheoremGraph's informal edges mapped onto v0.4 target_kinds with zero schema changes (14.99M resolved / 3.33M cited-document / 21 named-unresolved) — first external corpus to fit natively at scale.

## v0.4 — 2026-09-01 (Alex 09-01 meeting ruling + over-engineering audit + finding #32)
Evidence: meeting-notes/meeting-9-1-26.txt (citation-granularity ruling), 09-01 schema audit with Bashar ("elegance but also function"), FINDINGS.md #32.
- **Paper shadow nodes**: every source_doc projects one; cited external papers get one from the zbMATH/OpenAlex spine or a bare citation. Dated by publication metadata → `cited-document` references carry ~zero error (Alex: "rely on papers and have zero error").
- **`cited-document` target_kind** on references: document-level citations recorded at the source's own precision, resolved to a paper shadow node via bibliography matching. Optional `item` field (any target_kind) records the sub-item as cited ("Theorem 3(b)") — factual, not a judgment.
- **Dotted theorem identification** = new linking-table relation `theorem-identification` (proof-use → instance/canonical, low confidence allowed, deletable) — the judgment layer for "which result inside the cited paper", community-fixable post-release; the upgrade task = the doc→theorem benchmark (Re²Math-style).
- **ripeness(X,t) resolves per-ingredient at finest dated granularity**: theorem-level where dates exist (incl. via confirmed dotted links), paper-level for cited-document (freeze(t) now admits papers by published date), unknown only for named-unresolved/implicit. Verdicts carry per-ingredient granularity annotations.
- **Reference object unified**: one shape shared by proof `uses[]` and new optional statement `refs[]`.
- **Cut `notation_context`** (audit: free-text, only 15 non-empty across all extracted data, consumed by no view; statement-level deps now expressible as `refs[]`). Existing instance files untouched (immutable); build simply stops reading the field.
- **Vocabulary quarantine codified**: judgment-process vocab (no_match_reason etc.) lives in linking-layer reports, never the core schema.
Migration: additive except the notation_context cut — no re-extraction needed; the 3 arXiv papers recorded no bracketed citations as refs (pre-cited-document extraction), so their citation upgrade rides along with the P1/P2 paper lanes.

## v0.3 — 2026-08-31 (post prior-schema diff: MathAtlas 2605.14061, NaturalProofs 2104.01112)
Adopted: `names[]` on definition instances (MathAtlas — multi-object definitions); dependency depth/mass + hard-subset as derived views (MathAtlas); ordered-vs-set ingredient reading noted on task exports (NaturalProofs); temporal-consistency audit on freeze(t) — forward-edge check adapted from NaturalProofs' leaf-node split, used as validator not split axis.
Deliberately NOT copied (with reasons in the diff reports): flat resolved-or-nothing refs (erases the uncertainty ripeness needs); nested proofs-in-statement (makes proof dates second-class); sequential positional IDs (breaks immutability); 3-way kind enum (loses proof_status/role distinctions the prototype showed are load-bearing); no-cross-source-merge default (identity resolution is our core). Pipeline lessons (gold slice, context caution, reference-resolution recipe, proof-extraction QA weight) went to FLEET-DESIGN.md, not the schema.
Diff evidence: agent reports in session 08-31; neither prior schema has a temporal layer, cross-source identity, or per-edge confidence.

## v0.2 — 2026-08-31 (same day; driven by first prototype extraction, lebl-ba1 ch-seq-ser)
Evidence: data/prototype/EXTRACTION-REPORT.md (14 friction items, 8 unspecified decisions).
- `proof_status` added to statement_instance — 10 of 44 provable statements had no \begin{proof} (prose proofs, "left as exercise", proof-precedes-statement); ripeness needs "claimed, not captured" to be visible.
- proof_instance gains `presentation: proof-env|prose`.
- `uses`: prose mentions may now resolve to instances (provenance "prose-mention", confidence ≤0.85) — the macro-only rule cost real connectivity (extractor knew the target in ≥3 cases but was forbidden to link). New `resolved-label` target_kind for labels that exist in the corpus without an instance record.
- Codified: self-refs to own enumerated items are not uses; "(why?)" reader prompts are not implicit edges.
- Unlabeled-instance IDs switch from positional to content-hash (immutability across re-extractions).
- extraction.method enum gains "agent".
File renamed SCHEMA-v0.1.md → SCHEMA.md (version in header + this log).

## v0.1 — 2026-08-31
Initial design (before reading MathAtlas/NaturalProofs schemas, per anti-anchoring rule).
Core commitments: two-layer identity (immutable instances + revisable linking table); proofs first-class and edge-owning; typed date-events with intervals; provenance on every record; freeze(t) as the correctness contract; named-unresolved/implicit references first-class so ripeness degrades visibly.
