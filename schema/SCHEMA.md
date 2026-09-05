# History-of-Math Graph — Schema v0.4
*2026-09-01. Designed from scratch per Alex's ordering (before reading MathAtlas/NaturalProofs schemas — diff done 08-31). Changes go through SCHEMA-CHANGELOG.md. v0.4 folds in the 09-01 over-engineering audit and Alex's citation-granularity ruling: **references resolve to dated paper shadow nodes with zero error; theorem identification is a dotted, revisable, low-confidence link; ripeness is defined over papers wherever theorem dates are absent.***

## Design principles
1. **Two layers.** Extraction emits immutable, source-scoped **instances**; all fallible identity judgments live in a revisable **linking table** that defines **canonical** nodes. Extraction writes facts that cannot be wrong about themselves ("this source says X"); merges can be undone by editing one table.
2. **Proofs are first-class and own the edges.** A theorem can have many proofs; each proof has its own date, actor, and ingredient set. Dependency edges hang off proofs, not theorems.
3. **Dates are typed events with intervals**, never bare years. (Motivating failure: Wikidata's P575 on FLT = 1638 — the *posed* date; Euler's formula carries two conflicting P575 values.)
4. **Provenance on every record**: `(source_doc, locator, method, confidence)`. Never retrofittable, so mandatory from day one.
5. **The correctness test is `freeze(t)`**: every benchmark task must be expressible as a pure function of (frozen canonical graph at time t, target node). If a task needs anything else, the schema is wrong.

## Record types

### statement_instance  (extraction output; immutable)
```jsonc
{
  "instance_id": "inst:<doc-slug>:<local-id>",     // stable, derived from source
  "source": { "doc": "<doc-slug>", "locator": "ch2 §2.3, Thm 2.3.8", "char_span": [10412, 10630] },
  "kind_as_labeled": "theorem|lemma|proposition|corollary|conjecture|definition|axiom|example|exercise|remark",
  "role": "main|exercise|worked-example",           // exercises kept, flagged — many are real named theorems
  "statement_text": "<verbatim or lightly normalized statement>",
  "local_name": "Bolzano–Weierstrass theorem",      // name as the source calls it, if any
  "local_label": "Theorem 2.3.8",                   // source-internal numbering
  "raw_chunk": "<exact source text incl. surrounding context>",
  "refs": [ /* OPTIONAL, v0.4: reference objects (same shape as proof uses[], below) for things the
               STATEMENT itself cites — "in the notation of [3]", a definition it invokes by name.
               Replaces v0.2's notation_context (cut: free-text, never consumed by any view). */ ],
  "names": ["<object(s) a definition introduces>"],   // v0.3 (from MathAtlas): definitions only; one
                                                      // definition can introduce several objects
  "proof_status": "proof-env|prose-proof|deferred-to-exercise|omitted|not-applicable",
                       // v0.2: 10/44 provable statements in the prototype chapter had no \begin{proof};
                       // ripeness must see "claimed true, proof not captured" explicitly
  "extraction": { "method": "rule|llm|agent|human", "model": "...", "prompt_version": "...", "confidence": 0.97 },
  "schema_version": "0.2"
}
```
ID rule (v0.2): unlabeled statements get `inst:<doc>:<section>:h<8-char content hash>` — positional `unlabeled-<n>` IDs break immutability across re-extractions.
```

### proof_instance  (immutable; owns instance-level edges)
```jsonc
{
  "proof_id": "prf:<doc-slug>:<local-id>",
  "proves": "inst:<...>",                            // the statement_instance it is attached to
  "source": { ... },                                 // same shape as above
  "proof_text": "<verbatim>",                        // may be omitted for very long proofs; span always kept
  "presentation": "proof-env|prose",                 // v0.2: prose proofs (incl. proof-before-statement) are real proofs
  "uses": [ /* ingredient REFERENCE OBJECTS as the source states them — shape below */ ],
  "extraction": { ... }, "schema_version": "0.4"
}
```

### reference object  (v0.4: ONE shape, used by proof `uses[]` and statement `refs[]`)
```jsonc
    { "target_kind": "resolved-instance", "target": "inst:lebl-ba1:thm-2.3.4",
      "provenance": "explicit-reference", "confidence": 0.97 },
    { "target_kind": "resolved-instance", "target": "inst:lebl-ba1:...",
      "provenance": "prose-mention", "confidence": 0.8 },     // v0.2: prose mentions MAY resolve when the
                                                              // extractor identifies the target; provenance
                                                              // carries the distinction, confidence capped ≤0.85
    { "target_kind": "resolved-label",    "raw_label": "exercise:infseqlimlims",
      "provenance": "explicit-reference", "confidence": 0.95 },// v0.2: label exists in corpus but no instance
                                                              // record (e.g. plain exercises); resolvable later
    { "target_kind": "cited-document",    "citation_raw": "[14]", "bibkey": "banach1932",
      "resolved_doc": "paper:doi:10.4064/fm-3-1-133-181",     // v0.4 (Alex 09-01 ruling): document-level
      "item": "Théorème 6",                                   // citations are FIRST-CLASS and resolve to a
      "provenance": "explicit-reference", "confidence": 0.99 },// PAPER SHADOW NODE with ~zero error via
                                                              // bibliography matching (DOI/title → spine).
                                                              // `item` (OPTIONAL, any target_kind): the
                                                              // sub-item AS CITED ("Theorem 3(b)") — factual,
                                                              // recorded even when we can't identify which
                                                              // statement that is. Theorem identification is
                                                              // NOT stored here — it is a dotted linking-layer
                                                              // judgment (see below).
    { "target_kind": "named-unresolved",  "name": "the mean value theorem",
      "provenance": "prose-mention", "confidence": 0.9 },     // first-class dangling reference
    { "target_kind": "implicit",          "note": "'by a standard compactness argument'",
      "provenance": "llm-inferred", "confidence": 0.5 }
```
`named-unresolved`, `resolved-label`, and `implicit` are first-class so that missing-edge uncertainty degrades ripeness *visibly*, never silently. `cited-document` records citations at the source's own precision — never faking statement-level precision the source didn't give (finding #32: upgrading these IS the doc→theorem benchmark task).
Codified exclusions (v0.2): `\ref{}` to the statement's own enumerated items is not a `uses` edge; rhetorical reader-prompts ("(why?)") are not `implicit` edges.

### source_doc
```jsonc
{ "doc_slug": "lebl-basic-analysis-v6.2",
  "title": "Basic Analysis: Introduction to Real Analysis, Vol I", "authors": ["Jiří Lebl"],
  "doc_kind": "textbook|paper|wiki|encyclopedia|database",
  "published": { "min": 2023, "max": 2023 },        // the document's own date (≠ theorem dates)
  "license": "CC BY-SA 4.0", "license_verified": true,
  "acquisition": "github.com/jirilebl/ra @ <commit>",// how we legally obtained it — audit trail for the no-piracy rule
  "raw_stored_at": "corpus/lebl-ba1/" }
```
v0.4: every source_doc **projects a paper shadow node** (below); ingested docs are just shadow nodes we also have the contents of.

### paper shadow node  (v0.4, from Alex's 09-01 ruling)
```jsonc
{ "paper_id": "paper:doi:10.4064/fm-3-1-133-181",    // id spine: DOI when it exists, else zbMATH/OpenAlex id,
                                                      // else "paper:unmatched:<content-hash>" until spine-matched
  "title": "Sur les opérations dans les ensembles abstraits...",
  "authors": ["Stefan Banach"],
  "published": { "min": 1922, "max": 1922 },          // THE date that makes citations zero-error ingredients
  "external_ids": { "doi": "...", "openalex": "W...", "zbmath": "..." },
  "derived_from": "spine|source_doc|bare-citation",   // spine = zbMATH/OpenAlex metadata (P1 pull);
  "contains": [ /* instance_ids, when ingested */ ] } // bare-citation = known only from a bibliography entry
```
A paper shadow node is **not a judgment** — its date and identity come from publication metadata, so `cited-document` edges into it carry essentially zero error. It may contain several theorems we haven't separated; that's the point.

**Dotted theorem identification** (the "dotted line"): best-effort guesses at *which* result inside a cited paper a proof actually uses are linking-table rows, never fields on immutable records:
```jsonc
{ "relation": "theorem-identification",
  "from": { "proof": "prf:...", "use_index": 3 },     // the cited-document reference being sharpened
  "to": "inst:<...>" ,                                 // or a canonical_id once the paper is ingested/merged
  "method": "llm-judge|human|community", "confidence": 0.55,
  "decided_at": "2026-09-01", "decided_by": "<agent/human id>" }
```
Low confidence is allowed and expected; rows are deletable/replaceable (community fixes post-release, per Alex). The judged upgrade task is itself the doc→theorem benchmark.

### canonical_node + linking table  (revisable layer)
```jsonc
// linking table row — the ONLY place identity judgments live
{ "canonical_id": "thm:bolzano-weierstrass",
  "instance": "inst:lebl-ba1:thm-2.3.8",
  "method": "name-match|embedding|llm-judge|human", "confidence": 0.98,
  "decided_at": "2026-08-31", "decided_by": "<agent/human id>" }

// canonical node — mostly DERIVED from members; only curated fields stored
{ "canonical_id": "thm:bolzano-weierstrass",
  "kind": "theorem",                                 // curated (source kind labels vary)
  "preferred_name": "Bolzano–Weierstrass theorem",
  "aliases": ["BW theorem", ...],                    // union of member local_names + curated
  "external_ids": { "wikidata": "Q207754", "proofwiki": "..." },   // identity spine
  "events": [                                        // the historical date layer (curated + extracted)
    { "type": "posed|stated|proved|published|disproved|rediscovered|formalized",
      "when": { "min": 1817, "max": 1817 },          // interval; century-precision OK for antiquity
      "actor": "Bolzano",
      "provenance": { "source": "mactutor:<url>", "method": "llm-extracted", "confidence": "high" },
      "note": "proved as a lemma toward IVT" }
  ],
  "fields": ["real analysis"],                       // MSC-ish tags, coarse
  "schema_version": "0.1" }
```
Canonical proofs are the same move one level up: a `canonical_proof` groups proof_instances judged to be the same argument (same linking-table mechanism), carries its own `events` (a proof has a date!), and its canonical `uses` edges are **derived by lifting** member instance edges through the linking table — never hand-authored.

## Ingredient policy (v0.4.2) — granularity is a parameter of every export, never a fact in the data
Every reference carries `provenance`, `confidence`, and `meta.kind`. An **`ingredient_policy`** selects which references count as ingredients for a given view or benchmark; the same stored graph serves every policy. No human decides per edge; humans calibrate error rates per protocol, and consumers pick the policy.
```jsonc
{ "policy_id": "strict-ripeness-v1",
  "provenance": ["explicit-reference", "reader-explicit", "reader-implicit"],   // "explicit-only" = NaturalProofs-comparable
  "min_confidence": 0.75,
  "kinds": ["theorem", "lemma", "corollary", "proposition", "principle"],      // add "definition" for generous retrieval
  "exclude_techniques": true,           // proof techniques (contradiction, WLOG, induction-as-technique) are never ingredients
  "hub_cutoff": 0.10 }                  // a target referenced by > 10% of all proofs is background: demoted, not an ingredient
```
Named policies ship with the release (`explicit-only`, `strict-ripeness-v1`, `generous-retrieval-v1`); every reported number names its policy. The **criterion** behind all of them is fixed once, by people: *an ingredient is a result or concept that at some historical moment did not yet exist.* Hub-degree is the mechanical guard for that criterion — "induction" would be cited by most proofs and is therefore background by construction.

## Derived views (computed, never stored as truth)
- `freeze(t)` = canonical nodes having a `proved` (or `stated`, for definitions/axioms) event with `when.max <= t`, **plus (v0.4) every paper shadow node with `published.max <= t`**, plus lifted edges among them.
- `ripeness(X, t)` (v0.4, per the 09-01 ruling — each ingredient resolves at the **finest granularity with a real date**):
  1. **theorem-level** when the reference reaches a canonical node with a dated event (directly, or via a `theorem-identification` row above the confidence threshold);
  2. else **paper-level** for `cited-document` references — ripe iff the paper shadow node is in `freeze(t)`. Zero-error but coarse; the result records which granularity each ingredient used, so mixed-granularity verdicts are explicit, never laundered;
  3. else **unknown** — `named-unresolved`/`implicit` references above the confidence threshold still degrade visibly.
  Returns `{ripe, unripe, unknown}` + per-ingredient granularity annotations. Three-valued on purpose.
- Task exports: ripeness triples `(t, X, label)`; retrieval `(t, X, ingredient-set)`; proving `(t, X, ingredients, proof-text)`. v0.3 note (from NaturalProofs' export design): retrieval reads a proof's `uses` as a *set*; proving/generation may read it as an *ordered sequence with multiplicity* — the proof_instance preserves source order, so both exports are derivable.
- `dependency_depth(X)` / `dependency_mass(X)` over the lifted closure (v0.3, from MathAtlas — diagnostic + a "hard subset" export of deepest-dependency targets; their models degrade with depth).
- **Temporal-consistency audit** (v0.3, adapting NaturalProofs' leaf-split idea into validation): after any `freeze(t)`, flag every train-side node whose lifted `uses` edge points to a node dated *after* t — each hit is a dating error, a forward-referencing source, or a genuine leak, and must be resolved or excluded, never silently kept. The temporal cutoff stays the split axis; the graph check is its auditor.

## Deliberate v0.1 exclusions (add only under data pressure)
Formal (Lean) links; statement-equivalence relations (thm A ⟺ thm B); generalization/specialization edges; person/institution nodes; per-field ontologies. Each has an obvious slot (external_ids, a typed relation on canonical nodes) when needed.

## Vocabulary quarantine (v0.4 audit rule)
Working vocabularies of the judgment process (`no_match_reason: coverage-gap|...`, merge verdict labels, review-queue states) live in the **linking-layer reports and tables**, never in this core schema — they are process metadata, free to churn without a schema version bump.

## Known open questions (to resolve during prototype)
1. ~~Definitions in `uses`~~ RESOLVED (v0.4): definitions cited in a proof body are ordinary `uses[]` references; definitions a *statement* invokes go in the statement's own `refs[]` (same shape). `notation_context` cut.
2. What is a "proved" event for a definition/axiom? (Leaning: `stated` event type plays the role in freeze(t).)
3. Chapter-level vs book-level doc_slug for multi-volume sources.
4. Dedup *within* a document (restated theorems, e.g., a theorem repeated in an appendix).
