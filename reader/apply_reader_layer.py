#!/usr/bin/env python3
"""apply_reader_layer.py - add reader-protocol ingredients to proof_instances as a SECOND reference
layer (provenance 'reader-explicit' / 'reader-implicit', target_kind named-unresolved, confidence from
the reader, evidence quote kept). The explicit layer is untouched, so exports can select 'explicit only'
(NaturalProofs-comparable) or 'explicit + reader'. Idempotent (re-running replaces the reader layer).

usage: apply_reader_layer.py trench   -> data/extracted/trench-ra/{reader_out,proofs.jsonl}
       apply_reader_layer.py corpus   -> reader outputs in data/extracted/_reader_corpus/reader_out/,
                                         patched into every proofs.jsonl under lebl-ba1/*, proofwiki/*, papers/*
"""
import json, glob, sys
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]      # repo root (scripts live one folder down)
mode = sys.argv[1] if len(sys.argv) > 1 else "trench"

def load_reader(d):
    out = {}
    for f in glob.glob(str(d / "*.txt")):
        for line in open(f, encoding="utf-8"):
            if line.strip():
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                out[r["proof_id"]] = r.get("ingredients", [])
    return out

def patch(proofs_path, reader, stat):
    proofs = [json.loads(l) for l in open(proofs_path, encoding="utf-8") if l.strip()]
    touched = 0
    for p in proofs:
        if p["proof_id"] not in reader:
            continue
        p["uses"] = [u for u in p.get("uses", []) if not str(u.get("provenance", "")).startswith("reader-")]
        for ing in reader[p["proof_id"]]:
            p["uses"].append({"target_kind": "named-unresolved", "target": None, "name": ing["name"],
                              "provenance": "reader-" + ing.get("how", "implicit"), "confidence": ing.get("confidence"),
                              "meta": {"kind": ing.get("kind"), "evidence": ing.get("evidence")}})
            stat[ing.get("how", "implicit")] += 1
        touched += 1
    with open(proofs_path, "w", encoding="utf-8") as f:
        for p in proofs:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    stat["proofs"] += touched
    return touched

stat = Counter()
if mode == "trench":
    D = ROOT / "data/extracted/trench-ra"
    reader = load_reader(D / "reader_out")
    patch(D / "proofs.jsonl", reader, stat)
else:
    reader = load_reader(ROOT / "data/extracted/_reader_corpus/reader_out")
    files = glob.glob(str(ROOT / "data/extracted/lebl-ba1/*/proofs.jsonl")) + \
            glob.glob(str(ROOT / "data/extracted/proofwiki/*/proofs.jsonl")) + \
            glob.glob(str(ROOT / "data/extracted/papers/*/proofs.jsonl"))
    for pf in files:
        n = patch(pf, reader, stat)
        if n:
            print(f"  {Path(pf).parent.name}: {n} proofs patched")
print(f"reader layer applied to {stat['proofs']} proofs (of {len(reader)} reader outputs): explicit {stat['explicit']}, implicit {stat['implicit']}")
