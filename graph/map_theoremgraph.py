#!/usr/bin/env python3
"""map_theoremgraph.py - deterministic mapping of TheoremGraph stage-1 CSVs into
our schema v0.4 shapes. Runs ON VM-3 against /shared/theoremgraph/; streaming
(constant memory). No LLM anywhere - every judgment-shaped field is left for the
linking layer.

Outputs (/shared/theoremgraph/mapped/):
  statements_formal.jsonl  statement_instance records (Lean declarations)
  refs_formal.jsonl        flat v0.4 reference records, statement-level (sig/def/extends/field/docref)
  uses_formal.jsonl        flat v0.4 reference records, proof-level (edge_type=proof), kernel-derived
  edges_informal.jsonl     flat v0.4 reference records from informal_dependency:
                           resolved-instance | cited-document (cite_key, item=dep_name) | named-unresolved
  MAPPING-REPORT.txt       counts + category breakdowns
Statement bodies for the informal side are NOT in stage 1; informal targets use
stable ids (inst:tg-informal:<uuid>) that stage 2 will fill in.
"""
import csv
import json
import sys
from collections import Counter

BASE = "/shared/theoremgraph"
OUT = f"{BASE}/mapped"
import os
os.makedirs(OUT, exist_ok=True)
csv.field_size_limit(sys.maxsize)

report = Counter()


def w(f, obj):
    f.write(json.dumps(obj, ensure_ascii=False) + "\n")


# ---- 1. statement_formal.csv -> statement_instance ----
kinds = Counter()
with open(f"{BASE}/statement_formal.csv", newline="", encoding="utf-8") as src, \
     open(f"{OUT}/statements_formal.jsonl", "w", encoding="utf-8") as out:
    for r in csv.DictReader(src):
        kinds[r["kind"]] += 1
        report["formal_statements"] += 1
        w(out, {
            "instance_id": f"inst:tg-formal:{r['statement_id']}",
            "source": {"doc": "uw-math-graph-formal", "locator": f"{r['module']}:{r['decl_name']}"},
            "kind_as_labeled": r["kind"],
            "role": "main",
            "statement_text": r["body"] or None,
            "local_name": r["decl_name"],
            "local_label": r["decl_name"],
            "names": None,
            "proof_status": "proof-env" if r["proof"] else "omitted",
            "meta": {"paper_id": r["paper_id"], "file_path": r["file_path"],
                     "is_instance": r["is_instance"] == "True", "docstring_present": bool(r["docstring"])},
            "extraction": {"method": "rule", "model": None,
                           "prompt_version": "tg-map-v1", "confidence": 1.0},
            "schema_version": "0.4",
        })

# ---- 2. formal_dependency.csv -> proof-level uses / statement-level refs ----
STMT_LEVEL = {"sig", "def", "extends", "field", "docref"}
with open(f"{BASE}/formal_dependency.csv", newline="", encoding="utf-8") as src, \
     open(f"{OUT}/uses_formal.jsonl", "w", encoding="utf-8") as fu, \
     open(f"{OUT}/refs_formal.jsonl", "w", encoding="utf-8") as fr:
    for r in csv.DictReader(src):
        if r["src_id"] == r["dep_id"]:
            report["formal_self_edges_skipped"] += 1
            continue
        rec = {
            "owner": f"inst:tg-formal:{r['src_id']}",
            "target_kind": "resolved-instance",
            "target": f"inst:tg-formal:{r['dep_id']}",
            "provenance": "kernel-derived" if r["edge_type"] != "docref" else "prose-mention",
            "confidence": 1.0 if r["edge_type"] != "docref" else 0.85,
            "meta": {"edge_type": r["edge_type"], "role": r["role"] or None,
                     "position": r["position"] or None},
        }
        if r["edge_type"] == "proof":
            rec["proof"] = f"prf:tg-formal:{r['src_id']}"
            w(fu, rec)
            report["formal_proof_uses"] += 1
        elif r["edge_type"] in STMT_LEVEL:
            w(fr, rec)
            report["formal_stmt_refs"] += 1
        else:
            report[f"formal_other_{r['edge_type']}"] += 1

# ---- 3. informal_dependency.csv -> mixed v0.4 reference flavors ----
METHOD_CONF = {"deterministic": 0.95, "heuristic": 0.7, "llm": 0.7}
flavors = Counter()
with open(f"{BASE}/informal_dependency.csv", newline="", encoding="utf-8") as src, \
     open(f"{OUT}/edges_informal.jsonl", "w", encoding="utf-8") as out:
    for r in csv.DictReader(src):
        methods = [m.strip(" '\"[]") for m in (r["methods"] or "").strip("[]").split(",") if m.strip()]
        conf = max((METHOD_CONF.get(m, 0.6) for m in methods), default=0.6)
        rec = {
            "owner": f"inst:tg-informal:{r['src_id']}",
            "location": r["location"] or None,  # body -> statement refs[]; proof -> proof uses[]
            "provenance": "explicit-reference" if "deterministic" in methods else "llm-inferred",
            "confidence": conf,
            "meta": {"methods": methods},
        }
        if r["dep_id"]:
            rec["target_kind"] = "resolved-instance"
            rec["target"] = f"inst:tg-informal:{r['dep_id']}"
            if r["dep_key"]:
                rec["meta"]["dep_key"] = r["dep_key"]
        elif r["cite_key"] or r["cite_id"]:
            rec["target_kind"] = "cited-document"
            rec["citation_raw"] = r["cite_key"] or r["cite_id"]
            if r["cite_id"]:
                rec["resolved_doc"] = f"paper:tg:{r['cite_id']}"
            if r["dep_name"]:
                rec["item"] = r["dep_name"]
        elif r["dep_name"] or r["dep_key"]:
            rec["target_kind"] = "named-unresolved"
            rec["name"] = r["dep_name"] or r["dep_key"]
        else:
            report["informal_empty_rows_skipped"] += 1
            continue
        flavors[rec["target_kind"]] += 1
        report["informal_edges"] += 1
        w(out, rec)

with open(f"{OUT}/MAPPING-REPORT.txt", "w", encoding="utf-8") as f:
    f.write("TheoremGraph stage-1 -> schema v0.4 mapping (tg-map-v1, deterministic)\n\n")
    for k, v in sorted(report.items()):
        f.write(f"{k}: {v}\n")
    f.write("\nformal statement kinds:\n")
    for k, v in kinds.most_common():
        f.write(f"  {k}: {v}\n")
    f.write("\ninformal reference flavors:\n")
    for k, v in flavors.most_common():
        f.write(f"  {k}: {v}\n")
print(json.dumps({**report, **{f"flavor_{k}": v for k, v in flavors.items()}}, indent=1))
