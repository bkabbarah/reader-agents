#!/usr/bin/env python3
"""build_graph.py - deterministic assembly of the PoC graph (FLEET-DESIGN stages 2/3/5, PoC-scale).

Reads every chapter's instances.jsonl/proofs.jsonl (pilot dir + data/extracted/lebl-ba1/*),
validates, resolves cross-chapter `resolved-label` edges via a book-wide label map,
joins verified date events (data/dates/events.jsonl) onto instances by name matching,
and emits data/build/graph.json for the visualization plus a validation report to stdout.

PoC canonicalization: one book, so each instance is its own canonical node (trivial merge);
the linking table mechanism is exercised only by label resolution. Cross-source merging
comes later with the second source.
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
CHAPTER_DIRS = ([os.path.join(ROOT, "data", "prototype")]
                + sorted(glob.glob(os.path.join(ROOT, "data", "extracted", "lebl-ba1", "*")))
                + sorted(glob.glob(os.path.join(ROOT, "data", "extracted", "proofwiki", "*")))
                + sorted(glob.glob(os.path.join(ROOT, "data", "extracted", "papers", "*"))))


def src_of(path: str) -> str:
    if os.sep + "proofwiki" + os.sep in path:
        return "proofwiki"
    if os.sep + "papers" + os.sep in path:
        return "arxiv-" + os.path.basename(path)
    return "lebl-ba1"
EVENTS_PATH = os.path.join(ROOT, "data", "dates", "events.jsonl")
OUT_DIR = os.path.join(ROOT, "data", "build")


TECHNIQUE = re.compile(r"\b(contradiction|wlog|without loss of generality|induction hypothesis|induction)\b", re.I)


def ref_kind(u, name):
    """Kind of a reference target, for ingredient_policy filtering. ProofWiki wiki-links carry their page
    namespace in raw_label (Definition:/Axiom:/theorem pages); reader refs carry meta.kind; technique
    words are never ingredients. None = unknown (treated as result-like)."""
    rl = str(u.get("raw_label") or "")
    if rl.startswith("Definition:"):
        return "definition"
    if rl.startswith("Axiom:"):
        return "axiom"
    mk = (u.get("meta") or {}).get("kind")
    if mk:
        return mk
    if name and TECHNIQUE.search(name):
        return "technique"
    return "result" if u.get("provenance") == "wiki-link" else None


def norm_name(s: str) -> str:
    s = re.sub(r"\(.*?\)", " ", s or "")          # parenthetical qualifiers break matching
    s = s.split("/")[0]                            # "Minimum-maximum theorem / Extreme value theorem"
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    s = re.sub(r"\b(the|theorem|thm|test|property|principle|rule|criterion|of|for)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def load_jsonl(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"INVALID JSON {path}:{i}: {e}")
                raise SystemExit(1)
    return rows


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    instances, proofs, problems = [], [], []
    for d in CHAPTER_DIRS:
        ipath, ppath = os.path.join(d, "instances.jsonl"), os.path.join(d, "proofs.jsonl")
        if not os.path.exists(ipath):
            print(f"note: skipping {d} (no instances.jsonl yet)")
            continue
        chap, src = os.path.basename(d), src_of(d)
        for r in load_jsonl(ipath):
            r["_chapter"], r["_src"] = chap, src
            instances.append(r)
        if os.path.exists(ppath):
            for r in load_jsonl(ppath):
                r["_chapter"], r["_src"] = chap, src
                proofs.append(r)

    # --- validation ---
    ids = [r["instance_id"] for r in instances]
    dupes = [k for k, c in Counter(ids).items() if c > 1]
    if dupes:
        problems.append(f"duplicate instance_ids: {dupes[:10]}")
    idset = set(ids)
    label_map = {}  # raw \label -> instance_id (lebl book-wide); wiki slugs map for proofwiki
    for r in instances:
        lab = r.get("local_label")
        if lab and r["_src"] == "lebl-ba1":
            if lab in label_map and label_map[lab] != r["instance_id"]:
                problems.append(f"label '{lab}' claimed by two instances")
            label_map[lab] = r["instance_id"]
        if r["_src"] == "proofwiki":
            label_map[r["instance_id"].split("inst:proofwiki:", 1)[-1]] = r["instance_id"]

    # v0.4.2 linking aids for the reader layer: (a) judged concept->definition links, (b) exact normalized-name
    # index over instance names (unique matches only) — both are linking-layer, never edit extractions
    concept_map = {}
    for fname in ("concept_links.jsonl", "reader_links.jsonl"):   # judged name->statement links (same row shape)
        cpath = os.path.join(ROOT, "data", "linking", fname)
        if os.path.exists(cpath):
            for row in load_jsonl(cpath):
                if row.get("to") in idset and (row.get("confidence") or 0) >= 0.75:
                    concept_map.setdefault(norm_name(row["name"]), row["to"])
    name_index = defaultdict(set)
    for r in instances:
        for nm in (r.get("local_name"),):
            if nm and len(norm_name(nm)) > 3:
                name_index[norm_name(nm)].add(r["instance_id"])
    name_index = {k: next(iter(v)) for k, v in name_index.items() if len(v) == 1}

    # cross-source canonical merges (verdict "same"): pw instance -> lebl canonical
    merged_into, merge_conf = {}, {}
    mpath = os.path.join(ROOT, "data", "linking", "merges.jsonl")
    if os.path.exists(mpath):
        for row in load_jsonl(mpath):
            if row.get("verdict") == "same" and row.get("lebl_instance") in idset and row.get("pw_instance") in idset:
                if row.get("confidence", 0) >= merge_conf.get(row["pw_instance"], 0):
                    merged_into[row["pw_instance"]] = row["lebl_instance"]
                    merge_conf[row["pw_instance"]] = row.get("confidence", 0)
    canon = lambda nid: merged_into.get(nid, nid)

    for p in proofs:
        if p.get("proves") not in idset:
            problems.append(f"{p.get('proof_id')}: proves target {p.get('proves')} missing")

    # --- linking layer: judged resolutions (revisable rows; never edits extractions) ---
    resolutions = defaultdict(list)   # (proof_id, name) -> [rows]
    for path in (os.path.join(ROOT, "data", "linking", "edge_resolutions.jsonl"),
                 os.path.join(ROOT, "data", "linking", "manual_links.jsonl")):
        if os.path.exists(path):
            for row in load_jsonl(path):
                if row.get("verdict") == "resolved" and row.get("target") in idset:
                    resolutions[(row.get("proof"), row.get("name"))].append(row)
    res_by_proof = defaultdict(list)
    for (pid, _name), rows in resolutions.items():
        res_by_proof[pid].extend(rows)

    # --- linking: resolve resolved-label, judged links, dedupe (proof, target) ---
    edge_rows, resolved_now, resolved_judged, resolved_concept, resolved_name = [], 0, 0, 0, 0
    for p in proofs:
        seen_pt = set()
        pv = canon(p["proves"])
        judged_here = {r.get("name"): True for r in res_by_proof.get(p["proof_id"], [])}
        for u in p.get("uses") or []:
            tk, target = u.get("target_kind"), u.get("target")
            name = u.get("name") or u.get("raw_label") or u.get("note")
            prov, conf = u.get("provenance"), u.get("confidence")
            if tk == "resolved-instance":
                if target not in idset:
                    problems.append(f"{p['proof_id']}: uses target {target} missing")
                    continue
            elif tk in ("resolved-label", "named-unresolved") and u.get("raw_label") in label_map:
                target, tk = label_map[u["raw_label"]], "resolved-instance"
                resolved_now += 1
            elif (p["proof_id"], name) in resolutions:
                rows = resolutions.pop((p["proof_id"], name))
                for r in rows:
                    if (pv, canon(r["target"])) in seen_pt:
                        continue
                    seen_pt.add((pv, canon(r["target"])))
                    resolved_judged += 1
                    edge_rows.append({"source": pv, "proof": p["proof_id"], "target": canon(r["target"]),
                                      "target_kind": "resolved-instance", "name": name,
                                      "provenance": "llm-judge-link", "confidence": r.get("confidence")})
                continue
            elif tk == "named-unresolved" and name and norm_name(name) in concept_map:
                target, tk, prov = concept_map[norm_name(name)], "resolved-instance", "concept-link"
                resolved_concept += 1
            elif tk == "named-unresolved" and name and norm_name(name) in name_index and name_index[norm_name(name)] != p["proves"]:
                target, tk, prov = name_index[norm_name(name)], "resolved-instance", (prov or "") + "+name-exact"
                resolved_name += 1
            elif tk != "resolved-instance":
                target = None
            if target:
                target = canon(target)
                if (pv, target) in seen_pt:
                    continue  # P5: duplicate (proof, target) collapses on lift
                seen_pt.add((pv, target))
            edge_rows.append({
                "source": pv, "proof": p["proof_id"], "target": target,
                "target_kind": tk, "name": name,
                "provenance": prov, "confidence": conf,
                "kind": ref_kind(u, name),   # v0.4.2: lets ingredient_policy act on explicit-layer refs too
            })
    # judged links keyed by names the extraction didn't emit verbatim: attach any leftovers by proof id
    for (pid, name), rows in list(resolutions.items()):
        for r in rows:
            src = next((canon(p["proves"]) for p in proofs if p["proof_id"] == pid), None)
            if src and r["target"] in idset:
                resolved_judged += 1
                edge_rows.append({"source": src, "proof": pid, "target": canon(r["target"]),
                                  "target_kind": "resolved-instance", "name": name,
                                  "provenance": "llm-judge-link", "confidence": r.get("confidence")})

    # --- date join: events.jsonl name/aliases vs instance local_name ---
    events_by_norm = {}
    if os.path.exists(EVENTS_PATH):
        for ev in load_jsonl(EVENTS_PATH):
            for nm in [ev["name"], *(ev.get("aliases") or [])]:
                events_by_norm[norm_name(nm)] = ev
    overrides = {}
    lm_path = os.path.join(ROOT, "data", "dates", "label_map.json")
    if os.path.exists(lm_path):
        overrides = {k: v for k, v in json.load(open(lm_path, encoding="utf-8")).items()
                     if not k.startswith("_")}
    events_by_name = {v["name"]: v for v in events_by_norm.values()}
    dated = 0
    for r in instances:
        ev = events_by_name.get(overrides.get(r["instance_id"], ""))
        if ev is None:
            key = norm_name(r.get("local_name") or "")
            ev = events_by_norm.get(key) if key else None
        r["_events"] = ev["events"] if ev else []
        r["_matched_name"] = ev["name"] if ev else None
        if ev:
            dated += 1
    unmatched_events = {v["name"] for v in events_by_norm.values()} - {
        r["_matched_name"] for r in instances if r["_matched_name"]}

    # earliest 'proved' (theorems) / 'stated' (definitions) year per node
    def node_year(r):
        # "available to mathematics": earliest proof wins; else earliest statement/publication.
        # (Motivating case: Leibniz's alternating-series test — stated 1676, formally published 1993.)
        by = defaultdict(list)
        for e in r["_events"]:
            if e.get("when"):
                by[e.get("type")].append(e["when"]["min"])
        for group in (("proved",), ("stated", "published", "rediscovered", "posed")):
            yrs = [y for t in group for y in by.get(t, [])]
            if yrs:
                return min(yrs)
        return None

    absorbed = defaultdict(list)                     # canonical lebl id -> merged pw ids
    for pw, lb in merged_into.items():
        absorbed[lb].append(pw)
    nodes = [{
        "id": r["instance_id"], "kind": r["kind_as_labeled"], "role": r.get("role", "main"),
        "chapter": r["_chapter"], "label": r.get("local_label"),
        "name": r.get("local_name") or r.get("local_label") or r["instance_id"].split(":")[-1],
        "famous": bool(r["_events"]), "year": node_year(r), "events": r["_events"],
        "ename": r["_matched_name"],
        "sources": [r["_src"]] + (["proofwiki"] if absorbed.get(r["instance_id"]) else []),
        "merged_ids": absorbed.get(r["instance_id"]) or [],
        "proof_status": r.get("proof_status"), "locator": (r.get("source") or {}).get("locator"),
        "text": re.sub(r"\s+", " ", (r.get("statement_text") or ""))[:420],
    } for r in instances if r["instance_id"] not in merged_into]
    concrete_edges = [e for e in edge_rows if e["target"]]

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "graph.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({"nodes": nodes, "edges": concrete_edges, "dangling": [e for e in edge_rows if not e["target"]],
                   "meta": {"chapters": len({r['_chapter'] for r in instances}),
                            "sources": len({r['_src'] for r in instances}),
                            "canonical_nodes": len(nodes), "cross_source_merges": len(merged_into),
                            "instances": len(instances), "proofs": len(proofs),
                            "edges_concrete": len(concrete_edges), "edges_dangling": len(edge_rows) - len(concrete_edges),
                            "cross_chapter_resolved_at_build": resolved_now,
                            "dated_nodes": dated}}, f, ensure_ascii=False, indent=1)

    kinds = Counter(r["kind_as_labeled"] for r in instances)
    print(f"sources: {len({r['_src'] for r in instances})}  chapters/docs: {len({r['_chapter'] for r in instances})}"
          f"  instances: {len(instances)} -> canonical nodes: {len(nodes)} (merges: {len(merged_into)}) {dict(kinds)}")
    print(f"reader-layer resolution: concept-links {resolved_concept}, exact-name {resolved_name}")
    print(f"proofs: {len(proofs)}  edges: {len(concrete_edges)} concrete / {len(edge_rows) - len(concrete_edges)} dangling"
          f"  (cross-chapter resolved at build: {resolved_now}, judged links applied: {resolved_judged})")
    print(f"dated nodes: {dated}  unmatched event records: {sorted(unmatched_events)[:15]}")
    print("PROBLEMS:" if problems else "validation: CLEAN")
    for pr in problems[:40]:
        print("  -", pr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
