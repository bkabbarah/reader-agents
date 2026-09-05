#!/usr/bin/env python3
"""
Small, scripted (not judged) linking pass: map the 32 statement_instance
records in data/extracted/proofwiki/batch1/instances.jsonl (live 2026-08-31
ProofWiki scrape) to their counterpart records in the just-imported
NaturalProofs 2020-11-12 ProofWiki snapshot (data/extracted/naturalproofs/
instances.jsonl), by exact page-title match only.

Method: derive each pw batch1 instance's real ProofWiki page title from its
source.locator URL (percent-decode the /wiki/<path> segment, underscores ->
spaces) -- NOT from instance_id or local_name, both of which carry synthetic
disambiguation suffixes ("Darboux's_Theorem:main"/":corollary-2" both live at
the single URL .../Darboux's_Theorem) or encoding artifacts (see report).
Normalize (case-fold, collapse whitespace) and compare against the same
normalization of every NaturalProofs title. Exact matches only -- no fuzzy
matching, consistent with the strict syntactic method used in
NATURALPROOFS-COMPARISON.md section 3.

Output: data/linking/np2021_links.jsonl (one row per exact match).
Non-matches are collected for the import report (a separate step).
"""
import json
import os
import collections
from urllib.parse import unquote, urlparse

REPO = os.path.dirname(os.path.abspath(__file__))
PW_INSTANCES = os.path.join(REPO, "data", "extracted", "proofwiki", "batch1", "instances.jsonl")
NP_INSTANCES = os.path.join(REPO, "data", "extracted", "naturalproofs", "instances.jsonl")
OUT_LINKS = os.path.join(REPO, "data", "linking", "np2021_links.jsonl")
OUT_SUMMARY = os.path.join(REPO, "data", "extracted", "naturalproofs", "_link_summary.json")


def normalize(title):
    return " ".join(title.strip().split()).casefold()


def title_from_locator(url):
    path = urlparse(url).path  # e.g. /wiki/Taylor%27s_Theorem/One_Variable
    prefix = "/wiki/"
    assert path.startswith(prefix), path
    slug = path[len(prefix):]
    decoded = unquote(slug)
    return decoded.replace("_", " ")


def main():
    os.makedirs(os.path.dirname(OUT_LINKS), exist_ok=True)

    # Build NaturalProofs title index: normalized title -> list of (instance_id, raw_title, kind)
    np_by_norm = collections.defaultdict(list)
    with open(NP_INSTANCES, encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            title = rec["local_name"]
            if not title:
                continue
            np_by_norm[normalize(title)].append(
                (rec["instance_id"], title, rec["kind_as_labeled"])
            )

    pw_records = []
    with open(PW_INSTANCES, encoding="utf-8") as f:
        for line in f:
            pw_records.append(json.loads(line))

    matched = []
    unmatched = []

    for rec in pw_records:
        pw_id = rec["instance_id"]
        locator = rec["source"]["locator"]
        derived_title = title_from_locator(locator)
        norm = normalize(derived_title)
        candidates = np_by_norm.get(norm, [])

        if len(candidates) == 1:
            np_id, np_title, np_kind = candidates[0]
            matched.append({
                "pw_instance": pw_id,
                "np_instance": np_id,
                "pw_derived_title": derived_title,
                "np_title": np_title,
                "np_kind": np_kind,
            })
        elif len(candidates) > 1:
            # Ambiguous exact match (title collision on the NP side) -- not resolved here,
            # not a "same" verdict without a tie-break judgment. Report as unmatched w/ reason.
            unmatched.append({
                "pw_instance": pw_id,
                "derived_title": derived_title,
                "reason": f"ambiguous: {len(candidates)} NaturalProofs records share this normalized title",
                "candidates": [c[0] for c in candidates],
            })
        else:
            unmatched.append({
                "pw_instance": pw_id,
                "derived_title": derived_title,
                "reason": "no NaturalProofs record with this exact normalized title",
                "candidates": [],
            })

    with open(OUT_LINKS, "w", encoding="utf-8") as f:
        for m in matched:
            row = {
                "np_instance": m["np_instance"],
                "pw_instance": m["pw_instance"],
                "verdict": "same",
                "confidence": 0.93,
                "method": "snapshot-title-match",
                "justification": "same ProofWiki page, 2021 snapshot vs 2026 live",
                "decided_by": "np-import-script",
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"pw batch1 instances: {len(pw_records)}")
    print(f"Matched (exact title): {len(matched)}")
    print(f"Unmatched: {len(unmatched)}")
    print(f"Wrote {OUT_LINKS}")

    for m in matched:
        print(f"  MATCH  {m['pw_instance']}  <->  {m['np_instance']}  ({m['np_title']!r}, kind={m['np_kind']})")
    for u in unmatched:
        print(f"  NO MATCH  {u['pw_instance']}  derived_title={u['derived_title']!r}  reason={u['reason']}")

    summary = {"matched": matched, "unmatched": unmatched}
    with open(OUT_SUMMARY, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
