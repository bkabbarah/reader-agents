#!/usr/bin/env python3
"""export_ripeness_v0.py - first ripeness ground-truth export from judged fusion links.

Design (v0, deliberately narrow -- every choice named so it can be challenged):
- date(node): via fusion same-result links (conf >= 0.75) to harvest events.
  Availability year = earliest 'proved'/'disproved' event; fallback 'published';
  we do NOT use 'conjectured'/'posed' (a conjecture is not an available ingredient).
- Labels are ROUTE-RELATIVE, matching Alex's definition (fraction of the eventual
  proof's ingredients that exist at t): for a proof with full dated ingredient set,
  M = max ingredient year, Y = target proved year.
    (target, t=M,   ripe)    -- all route ingredients exist
    (target, t=M-1, unripe)  -- the eventual route is missing >=1 ingredient
  Caveat carried per-record: unripe-at-t means THIS route was incomplete; another
  route could exist. ripe records also carry gap = Y - M ("sat ripe for G years").
- Temporal-consistency audit (schema v0.3 view, first real run): any ingredient
  dated AFTER the target's proved year is emitted to the audit file, not the task
  file -- each is a dating error, forward-reference, or genuine anomaly.
- Partials (>=1 but not all ingredients dated) go to a separate coverage file for
  fraction-of-ingredients-known analysis; they are NOT ripe/unripe examples.
Outputs: data/build/ripeness_v0.jsonl, ripeness_v0_partial.jsonl,
         ripeness_v0_audit.jsonl + printed summary.
"""
import json
import os
import re
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # repo root
CONF_MIN = 0.75

# schema v0.4.2 ingredient policies (which references count as ingredients) — selected by --policy
POLICIES = {
    "explicit-only": {"provenance": {"explicit-reference", "wiki-link", "np-ref", "prose-mention"}, "min_confidence": 0.0,
                      "kinds": None, "exclude_techniques": False, "hub_cutoff": 1.0},
    "strict-ripeness-v1": {"provenance": {"explicit-reference", "wiki-link", "np-ref", "prose-mention", "reader-explicit", "reader-implicit"},
                           "min_confidence": 0.75, "kinds": {"theorem", "lemma", "corollary", "proposition", "principle"},
                           "exclude_techniques": True, "hub_cutoff": 0.10},
    "generous-retrieval-v1": {"provenance": {"explicit-reference", "wiki-link", "np-ref", "prose-mention", "reader-explicit", "reader-implicit"},
                              "min_confidence": 0.5, "kinds": None, "exclude_techniques": True, "hub_cutoff": 0.10},
}
import sys
POLICY_ID = sys.argv[sys.argv.index("--policy") + 1] if "--policy" in sys.argv else "explicit-only"
POLICY = POLICIES[POLICY_ID]
TECHNIQUE = re.compile(r"\b(contradiction|without loss of generality|wlog|induction)\b", re.I)


def admits(u, hub_share=0.0):
    """Does the active ingredient_policy count this reference as an ingredient?"""
    if u.get("provenance") not in POLICY["provenance"]:
        return False
    if (u.get("confidence") or 0) < POLICY["min_confidence"]:
        return False
    kind = ((u.get("meta") or {}).get("kind"))
    if POLICY["kinds"] and kind and kind not in POLICY["kinds"]:
        return False
    if POLICY["exclude_techniques"] and TECHNIQUE.search(u.get("name") or ""):
        return False
    return hub_share <= POLICY["hub_cutoff"]


def load_jsonl(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def slug(iid):
    return iid.split(":", 2)[2]


events_by_slug = {e["slug"]: e["events"] for e in
                  load_jsonl(os.path.join(ROOT, "data/dates/harvest/consolidated/events.jsonl"))
                  if e.get("events")}


QUALIFIED = re.compile(r"restricted form|special case|partial(ly)? (proof|result)|only for|weaker form|particular case", re.I)


def avail_year(evs):
    """Earliest year the result was AVAILABLE in its full form (proved/disproved, else published).
    Events whose source sentence qualifies them as a restricted/special case (e.g. MVT: Rolle 1691
    'only for polynomials' vs Cauchy 1823 'modern form') are skipped when an unqualified event exists."""
    for types in (("proved", "disproved"), ("published",)):
        ok = [e for e in evs if e.get("type") in types and e.get("when")
              and (e.get("provenance") or {}).get("confidence") in ("high", "medium")]
        full = [e for e in ok if not QUALIFIED.search(e.get("note") or "")]
        pool = full or ok
        if pool:
            return min(e["when"]["min"] for e in pool)
    return None


links = [r for r in load_jsonl(os.path.join(ROOT, "data/linking/fusion_links.jsonl"))
         if r["relation"] == "harvest-date-link" and r["confidence"] >= CONF_MIN]
node_year = {}
for r in links:
    evs = events_by_slug.get(slug(r["to"]))
    y = avail_year(evs) if evs else None
    if y is not None and (r["from"] not in node_year or y < node_year[r["from"]]):
        node_year[r["from"]] = y

np_names = {}
for line in open(os.path.join(ROOT, "data/extracted/naturalproofs/instances.jsonl"), encoding="utf-8"):
    rec = json.loads(line)
    np_names[rec["instance_id"]] = rec.get("local_name") or rec["instance_id"]

full, partial, audit = [], [], []
stats = Counter()
PROOFS_PATH = os.path.join(ROOT, "data/extracted/naturalproofs/proofs.jsonl")
# pass 1: hub shares (fraction of proofs referencing each target) for the policy's hub_cutoff
target_proofs, n_proofs = Counter(), 0
for line in open(PROOFS_PATH, encoding="utf-8"):
    p = json.loads(line); n_proofs += 1
    for t in {u["target"] for u in p.get("uses", []) if u.get("target")}:
        target_proofs[t] += 1
hub_share = {t: c / n_proofs for t, c in target_proofs.items()}
stats["hubs_demoted"] = sum(1 for t, s in hub_share.items() if s > POLICY["hub_cutoff"])
for line in open(PROOFS_PATH, encoding="utf-8"):
    p = json.loads(line)
    ings = sorted({u["target"] for u in p.get("uses", []) if u.get("target")
                   and admits({**u, "provenance": u.get("provenance") or "explicit-reference"}, hub_share.get(u["target"], 0.0))})
    if not ings:
        continue
    stats["proofs_with_edges"] += 1
    tgt = p.get("proves")
    dated = {i: node_year[i] for i in ings if i in node_year}
    if not dated:
        continue
    stats["proofs_partial_or_full"] += 1
    row_common = {
        "proof_id": p["proof_id"], "target": tgt, "target_name": np_names.get(tgt, tgt),
        "n_ingredients": len(ings), "n_dated": len(dated),
        "ingredients": [{"id": i, "name": np_names.get(i, i), "year": dated.get(i)} for i in ings],
    }
    if len(dated) < len(ings):
        partial.append({**row_common, "coverage": round(len(dated) / len(ings), 3)})
        continue
    M = max(dated.values())
    Y = node_year.get(tgt)
    stats["full_closures"] += 1
    if Y is not None and any(y > Y for y in dated.values()):
        audit.append({**row_common, "target_year": Y,
                      "violations": [{"id": i, "year": y} for i, y in dated.items() if y > Y]})
        stats["audit_forward_refs"] += 1
        continue
    for t, label in ((M, "ripe"), (M - 1, "unripe")):
        full.append({**row_common, "t": t, "label": label,
                     "label_basis": "route-relative",
                     "target_year": Y, "gap_years": (Y - M) if Y is not None else None})
    stats["examples"] += 2

os.makedirs(os.path.join(ROOT, "data", "build"), exist_ok=True)
suffix = "" if POLICY_ID == "explicit-only" else f"_{POLICY_ID}"
for name, rows in ((f"ripeness_v0{suffix}.jsonl", full), (f"ripeness_v0_partial{suffix}.jsonl", partial),
                   (f"ripeness_v0_audit{suffix}.jsonl", audit)):
    with open(os.path.join(ROOT, "data", "build", name), "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps({**r, "ingredient_policy": POLICY_ID} if name.startswith("ripeness_v0") and rows is full else r,
                               ensure_ascii=False) + "\n")
print(f"policy: {POLICY_ID} {POLICY}")

gaps = sorted(r["gap_years"] for r in full if r["label"] == "ripe" and r["gap_years"] is not None)
print(dict(stats))

# ---- evaluation-hygiene block (obligations from the full-read lit review, RELATED-WORK-v2 §3) ----
# 1. trivial baselines that any reported ripeness number must beat (CUSP: constant-date baseline beat every
#    frontier model; Hisano–Sornette: content-free exponential hazard, rate 0.01/yr).
# 2. leakage_rate is a REQUIRED field on any model run over this export (ExAnte): null here, filled per run.
# 3. cutoffs are enforced as sample admission by construction (freeze(t) on the frozen graph), never by
#    prompting a model to "pretend" a date (OracleProto, ExAnte).
import math
n_ripe = sum(1 for r in full if r["label"] == "ripe"); n_all = len(full)
majority = max(n_ripe, n_all - n_ripe) / n_all if n_all else None
# hazard baseline: P(ingredient available by t | first stated) under rate 0.01/yr, scored against labels
def hazard_pred(r, rate=0.01):
    # a route is "ripe" under the hazard model if every ingredient's expected availability precedes t;
    # without stated dates for ingredients we use the label-defining year M: predicts ripe iff t >= M
    return "ripe" if r["t"] >= max(i["year"] for i in r["ingredients"] if i["year"] is not None) else "unripe"
hazard_acc = sum(1 for r in full if hazard_pred(r) == r["label"]) / n_all if n_all else None
hygiene = {
    "ingredient_policy": POLICY_ID,
    "n_examples": n_all, "n_ripe": n_ripe,
    "baseline_majority_label_acc": majority,
    "baseline_hazard_0.01yr_acc": hazard_acc,
    "baseline_note": "hazard baseline is degenerate on route-relative labels (labels are defined by t vs M); it becomes informative once targets carry their own proved year — reported anyway so the column exists from day one",
    "leakage_rate": None, "leakage_rate_note": "REQUIRED per model run (ExAnte): fraction of items whose post-t ingredient the model names despite the cutoff; report beside every accuracy",
    "cutoff_enforcement": "sample-admission via freeze(t) on the frozen graph; prompt-level date pretending is not used",
    "construction_invariance_check": "TODO: re-derive examples under a second question construction before quoting any pre/post-cutoff gap (Test of Time)",
    "lit_refs": ["2605.22681", "1202.3936", "2505.19533", "2605.03762", "2509.00072"],
}
with open(os.path.join(ROOT, "data", "build", f"ripeness_v0{'' if POLICY_ID=='explicit-only' else '_'+POLICY_ID}_eval_hygiene.json"), "w", encoding="utf-8") as f:
    json.dump(hygiene, f, indent=1)
print("eval hygiene:", {k: hygiene[k] for k in ("baseline_majority_label_acc", "baseline_hazard_0.01yr_acc", "leakage_rate")})
if gaps:
    print(f"gap (proved-year minus last-ingredient-year): n={len(gaps)} "
          f"median={gaps[len(gaps)//2]}y min={gaps[0]} max={gaps[-1]}")
print(f"wrote {len(full)} examples, {len(partial)} partials, {len(audit)} audit rows -> data/build/")
