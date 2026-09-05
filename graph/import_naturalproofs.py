#!/usr/bin/env python3
"""
Deterministic import of the on-disk NaturalProofs ProofWiki snapshot
(corpus/naturalproofs/naturalproofs_proofwiki.json) into the project's
instance layer (schema/SCHEMA.md v0.3).

No LLM judgment calls on content. Every field is a mechanical function of
the source record. Design decisions that are NOT literal mappings (i.e.
values invented to satisfy schema fields the source doesn't carry) are
marked "DEFAULT ASSUMPTION" below and reported in IMPORT-REPORT.md.

Outputs:
  data/extracted/naturalproofs/instances.jsonl
  data/extracted/naturalproofs/proofs.jsonl
  data/extracted/naturalproofs/source_doc.json
  data/extracted/naturalproofs/IMPORT-REPORT.md   (written by report step below;
                                                     counts/validation printed here too)

Run: python import_naturalproofs.py
"""
import json
import os
import sys
import collections

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_JSON = os.path.join(REPO, "corpus", "naturalproofs", "naturalproofs_proofwiki.json")
OUT_DIR = os.path.join(REPO, "data", "extracted", "naturalproofs")
INSTANCES_OUT = os.path.join(OUT_DIR, "instances.jsonl")
PROOFS_OUT = os.path.join(OUT_DIR, "proofs.jsonl")
SOURCE_DOC_OUT = os.path.join(OUT_DIR, "source_doc.json")

DOC_SLUG = "naturalproofs-pw-2021"
SNAPSHOT_DATE = "2020-11-12"  # NaturalProofs' ProofWiki crawl date (the provenance point)
STATEMENT_TEXT_CAP = 4000
SCHEMA_VERSION = "0.3"

KIND_MAP = {
    "theorem": "theorem",
    "definition": "definition",
    "other": "remark",
}


def kind_from_type(t):
    return KIND_MAP.get(t, "remark")


def clip(text, cap):
    if len(text) <= cap:
        return text, False
    return text[:cap], True


def build_instance(rec):
    rid = rec["id"]
    instance_id = f"inst:np2021:{rid}"
    contents = rec.get("contents") or []
    joined = "\n".join(contents)
    statement_text, truncated = clip(joined, STATEMENT_TEXT_CAP)
    has_proofs = bool(rec.get("proofs"))
    proof_status = "proof-env" if has_proofs else "omitted"

    ref_ids = rec.get("ref_ids") or []
    statement_refs = [f"inst:np2021:{r}" for r in ref_ids]

    inst = {
        "instance_id": instance_id,
        "source": {
            "doc": DOC_SLUG,
            "locator": f"naturalproofs_proofwiki.json#id={rid}",
            "char_span": None,
            "retrieved": SNAPSHOT_DATE,
        },
        "kind_as_labeled": kind_from_type(rec.get("type")),
        "role": "main",  # DEFAULT ASSUMPTION: NP has no exercise/worked-example marker; all pages treated as main.
        "statement_text": statement_text,
        "local_name": rec.get("title"),
        "local_label": rec.get("label"),
        "raw_chunk": None,  # deliberately NOT duplicated -- source JSON on disk (source.locator) is the raw store
        "notation_context": [],
        "proof_status": proof_status,
        "statement_refs": statement_refs,  # v0.4-preview field: statement-body refs/ref_ids as instance_ids (see report)
        "extraction": {
            "method": "rule",
            "model": None,
            "prompt_version": "np-import-v1",
            "confidence": 1.0,
        },
        "schema_version": SCHEMA_VERSION,
    }
    return inst, truncated, len(ref_ids)


def build_proofs(rec):
    rid = rec["id"]
    stmt_instance_id = f"inst:np2021:{rid}"
    out = []
    for k, proof in enumerate(rec.get("proofs") or []):
        proof_id = f"prf:np2021:{rid}-{k}"
        ref_ids = proof.get("ref_ids") or []
        uses = [
            {
                "target_kind": "resolved-instance",
                "target": f"inst:np2021:{r}",
                "provenance": "np-ref",
                "confidence": 0.99,
            }
            for r in ref_ids  # order + multiplicity preserved as in source (source does not dedup)
        ]
        p = {
            "proof_id": proof_id,
            "proves": stmt_instance_id,
            "source": {
                "doc": DOC_SLUG,
                "locator": f"naturalproofs_proofwiki.json#id={rid}&proof={k}",
                "char_span": None,
                "retrieved": SNAPSHOT_DATE,
            },
            "proof_text": None,  # deliberately NOT duplicated -- see source.locator; source JSON is the raw store
            "presentation": "proof-env",  # DEFAULT ASSUMPTION: NP proof bodies are ProofWiki equation-env proofs;
                                           # classifying proof-env vs prose would require content judgment (out of scope).
            "uses": uses,
            "extraction": {
                "method": "rule",
                "model": None,
                "prompt_version": "np-import-v1",
                "confidence": 1.0,
            },
            "schema_version": SCHEMA_VERSION,
        }
        out.append((p, len(ref_ids)))
    return out


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    print(f"Loading {SRC_JSON} ...")
    with open(SRC_JSON, encoding="utf-8") as f:
        data = json.load(f)
    d = data["dataset"]
    print("Loaded. Top-level groups:", list(d.keys()))

    groups = ["theorems", "definitions", "others"]

    all_ids = set()
    dup_ids = []
    instance_ids_seen = set()
    proof_ids_seen = set()

    kind_counts = collections.Counter()
    proof_status_counts = collections.Counter()
    truncated_count = 0
    statement_refs_total = 0

    n_proofs_total = 0
    uses_total = 0
    proof_ref_count_list = []  # for avg/top stats
    in_degree = collections.Counter()  # target instance_id -> count of uses edges pointing at it

    print(f"Writing {INSTANCES_OUT} and {PROOFS_OUT} (streaming) ...")
    with open(INSTANCES_OUT, "w", encoding="utf-8") as inst_f, \
         open(PROOFS_OUT, "w", encoding="utf-8") as proof_f:

        for grp in groups:
            for rec in d[grp]:
                rid = rec["id"]
                if rid in all_ids:
                    dup_ids.append(rid)
                all_ids.add(rid)

                inst, truncated, n_refs = build_instance(rec)
                if inst["instance_id"] in instance_ids_seen:
                    dup_ids.append(inst["instance_id"])
                instance_ids_seen.add(inst["instance_id"])

                kind_counts[inst["kind_as_labeled"]] += 1
                proof_status_counts[inst["proof_status"]] += 1
                if truncated:
                    truncated_count += 1
                statement_refs_total += n_refs

                inst_f.write(json.dumps(inst, ensure_ascii=False) + "\n")

                for p, n_uses in build_proofs(rec):
                    if p["proof_id"] in proof_ids_seen:
                        dup_ids.append(p["proof_id"])
                    proof_ids_seen.add(p["proof_id"])
                    n_proofs_total += 1
                    uses_total += n_uses
                    proof_ref_count_list.append(n_uses)
                    for edge in p["uses"]:
                        in_degree[edge["target"]] += 1
                    proof_f.write(json.dumps(p, ensure_ascii=False) + "\n")

    print(f"Instances written: {len(instance_ids_seen)}")
    print(f"Proofs written: {n_proofs_total}")
    print(f"Uses edges written: {uses_total}")

    # ---- source_doc.json ----
    source_doc = {
        "doc_slug": DOC_SLUG,
        "title": "NaturalProofs ProofWiki snapshot (Welleck et al., NeurIPS 2021)",
        "authors": ["Sean Welleck", "et al.", "(ProofWiki contributors, underlying content)"],
        "doc_kind": "database",
        "published": {"min": 2020, "max": 2020},
        "snapshot_date": SNAPSHOT_DATE,
        "license": "CC BY-SA 4.0",
        "license_verified": True,
        "license_verification_note": (
            "Verified via the Zenodo record's shipped LICENSE.txt (per-file breakdown), not the "
            "Zenodo top-level 'other-at' metadata field. naturalproofs_proofwiki.json -> CC BY-SA 4.0. "
            "See data/recon-datasets/NATURALPROOFS-COMPARISON.md section 1 for the full verification chain, "
            "including cross-check against ProofWiki's own footer license text (CC BY-SA, commonly cited as 3.0). "
            "This is a dated 2020-11-12 snapshot: content and licensing reflect ProofWiki as of that date, "
            "not the live site."
        ),
        "acquisition": (
            "Zenodo record 4902289 (github.com/wellecks/naturalproofs paper release), file "
            "naturalproofs_proofwiki.json, 116,780,142 bytes, downloaded via curl, byte count "
            "matches Zenodo-reported size exactly (no truncation). See NATURALPROOFS-COMPARISON.md."
        ),
        "raw_stored_at": "corpus/naturalproofs/naturalproofs_proofwiki.json",
        "schema_version": SCHEMA_VERSION,
    }
    with open(SOURCE_DOC_OUT, "w", encoding="utf-8") as f:
        json.dump(source_doc, f, ensure_ascii=False, indent=2)
    print(f"Wrote {SOURCE_DOC_OUT}")

    # ---- Validation pass ----
    print("\n=== VALIDATION ===")
    errors = []

    if dup_ids:
        errors.append(f"Duplicate ids found: {len(dup_ids)} (sample: {dup_ids[:10]})")
    else:
        print("No duplicate instance/proof ids. OK.")

    # Every uses target must exist as an instance_id we emitted.
    missing_targets = collections.Counter()
    for target, cnt in in_degree.items():
        if target not in instance_ids_seen:
            missing_targets[target] = cnt
    if missing_targets:
        errors.append(
            f"{len(missing_targets)} distinct uses-target instance_ids do not exist among emitted "
            f"instances ({sum(missing_targets.values())} edge occurrences). Sample: "
            f"{list(missing_targets.items())[:10]}"
        )
    else:
        print(f"All {len(in_degree)} distinct uses-edge targets resolve to an emitted instance. OK.")

    # statement_refs targets should also resolve (checked separately, informationally).
    # (Re-derive: any statement_refs value not in instance_ids_seen.)
    missing_stmt_ref_targets = 0
    with open(INSTANCES_OUT, encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            for t in rec["statement_refs"]:
                if t not in instance_ids_seen:
                    missing_stmt_ref_targets += 1
    if missing_stmt_ref_targets:
        errors.append(f"{missing_stmt_ref_targets} statement_refs entries point at non-existent instance_ids.")
    else:
        print("All statement_refs entries resolve to an emitted instance. OK.")

    print(f"\nCounts by kind_as_labeled: {dict(kind_counts)}")
    print(f"Counts by proof_status: {dict(proof_status_counts)}")
    print(f"statement_text truncated at {STATEMENT_TEXT_CAP} chars: {truncated_count} instances")
    print(f"Total statement-level ref_ids (statement_refs, not deduped): {statement_refs_total}")
    print(f"Total proof-level uses edges (not deduped): {uses_total}")
    if n_proofs_total:
        print(f"Avg uses edges per proof: {uses_total / n_proofs_total:.3f}")

    top10 = in_degree.most_common(10)
    print("\nTop-10 in-degree (most-referenced instances, by uses edges):")
    for target, cnt in top10:
        print(f"  {target}: {cnt}")

    if errors:
        print("\n*** VALIDATION ERRORS ***")
        for e in errors:
            print(" - " + e)
    else:
        print("\nValidation passed with no errors.")

    # Dump machine-readable summary for the report-writing step.
    summary = {
        "n_instances": len(instance_ids_seen),
        "n_proofs": n_proofs_total,
        "n_uses_edges": uses_total,
        "n_statement_refs": statement_refs_total,
        "kind_counts": dict(kind_counts),
        "proof_status_counts": dict(proof_status_counts),
        "truncated_count": truncated_count,
        "avg_uses_per_proof": (uses_total / n_proofs_total) if n_proofs_total else 0,
        "top10_in_degree": top10,
        "n_distinct_in_degree_targets": len(in_degree),
        "validation_errors": errors,
        "dup_id_count": len(dup_ids),
    }
    with open(os.path.join(OUT_DIR, "_import_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
