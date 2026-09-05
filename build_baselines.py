#!/usr/bin/env python3
"""build_baselines.py - export the first two benchmark task files + scoring.

Task 1 (year-knowledge): given a named result, predict the year it was proved.
  Ground truth: consolidated harvest events (high-confidence proved events only).
  Measures LLM parametric knowledge of math history — the contamination-relevant prior.
Task 2 (ingredient retrieval): given a theorem statement and a candidate list of
  pre-dating statements, select the ingredients its proof actually uses.
  Ground truth: resolved uses-edges in the canonical graph (Lebl+ProofWiki+papers).

Usage:
  python build_baselines.py export   -> data/baselines/year_task.jsonl, retrieval_task.jsonl
  python build_baselines.py score <answers.jsonl> -> metrics printed
Answers format: {"task_id": ..., "answer": <year int>} or {"task_id": ..., "answer": [candidate ids]}
"""
from __future__ import annotations

import json
import os
import random
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
BDIR = os.path.join(ROOT, "data", "baselines")
random.seed(20260901)


def load_jsonl(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def export():
    os.makedirs(BDIR, exist_ok=True)
    # ---- Task 1: year prediction, stratified by era ----
    rows = load_jsonl(os.path.join(ROOT, "data", "dates", "harvest", "consolidated", "events.jsonl"))
    insts = {r["instance_id"].split(":")[-1]: r for r in
             load_jsonl(os.path.join(ROOT, "data", "dates", "harvest", "consolidated", "instances.jsonl"))}
    cands = []
    for r in rows:
        proved = [e for e in r.get("events") or []
                  if e.get("type") in ("proved", "disproved")
                  and (e.get("provenance") or {}).get("confidence") == "high"
                  and e.get("when") and e["when"]["min"] == e["when"]["max"]]
        if proved:
            cands.append((r, min(e["when"]["min"] for e in proved)))
    by_era = defaultdict(list)
    for r, y in cands:
        by_era[min(y // 50 * 50, 2000)].append((r, y))
    sample = []
    eras = sorted(by_era)
    while len(sample) < 120 and any(by_era[e] for e in eras):
        for e in eras:
            if by_era[e] and len(sample) < 120:
                sample.append(by_era[e].pop(random.randrange(len(by_era[e]))))
    with open(os.path.join(BDIR, "year_task.jsonl"), "w", encoding="utf-8", newline="\n") as f, \
         open(os.path.join(BDIR, "year_truth.jsonl"), "w", encoding="utf-8", newline="\n") as g:
        for i, (r, y) in enumerate(sample):
            f.write(json.dumps({"task_id": f"yr-{i:03d}", "name": r["name"],
                                "question": f"In what year was the following mathematical result first proved (or disproved)? Answer with a single integer year (negative for BCE). Result: {r['name']}"},
                               ensure_ascii=False) + "\n")
            g.write(json.dumps({"task_id": f"yr-{i:03d}", "year": y, "slug": r["slug"]}) + "\n")

    # ---- Task 2: ingredient retrieval from the canonical graph ----
    g_ = json.load(open(os.path.join(ROOT, "data", "build", "graph.json"), encoding="utf-8"))
    nodes = {n["id"]: n for n in g_["nodes"]}
    uses = defaultdict(set)
    for e in g_["edges"]:
        if e.get("target") and e["target"] in nodes and e["source"] in nodes and e["target"] != e["source"]:
            uses[e["source"]].add(e["target"])
    targets = [nid for nid, deps in uses.items()
               if len(deps) >= 2 and nodes[nid].get("text") and nodes[nid]["kind"] in ("theorem", "proposition", "lemma", "corollary")]
    random.shuffle(targets)
    pool = [nid for nid, n in nodes.items() if n.get("text") and n["kind"] != "definition"]
    # v2 blinding: identical tasks/candidates (same seed), but candidates get opaque ids
    # (cd-XX) so structural metadata (source book, label, chapter) cannot leak. The
    # opaque->real mapping lives ONLY in the truth file; subjects answer in opaque ids.
    blind = "--v2" in sys.argv
    suffix = "_v2" if blind else ""
    with open(os.path.join(BDIR, f"retrieval_task{suffix}.jsonl"), "w", encoding="utf-8", newline="\n") as f, \
         open(os.path.join(BDIR, f"retrieval_truth{suffix}.jsonl"), "w", encoding="utf-8", newline="\n") as g2:
        for i, nid in enumerate(targets[:30]):
            truth = sorted(uses[nid])
            distract = [d for d in random.sample(pool, min(60, len(pool)))
                        if d not in truth and d != nid][:24 - len(truth)]
            cand = truth + distract
            random.shuffle(cand)
            if blind:
                opaque = {c: f"cd-{i:03d}-{j:02d}" for j, c in enumerate(cand)}
            else:
                opaque = {c: c for c in cand}
            f.write(json.dumps({
                "task_id": f"rt-{i:03d}",
                "target": {"name": nodes[nid]["name"], "statement": nodes[nid]["text"]},
                "question": "Which of the candidate results does the standard proof of the target use as ingredients? Answer with the list of candidate ids (typically 1-5).",
                "candidates": [{"id": opaque[c], "name": nodes[c]["name"], "statement": (nodes[c].get("text") or "")[:240]} for c in cand],
            }, ensure_ascii=False) + "\n")
            g2.write(json.dumps({"task_id": f"rt-{i:03d}", "truth": [opaque[t] for t in truth],
                                 "mapping": {opaque[c]: c for c in cand} if blind else None}) + "\n")
    print(f"exported: {len(sample)} year tasks, {min(30, len(targets))} retrieval tasks{' (v2 blinded)' if blind else ''} -> {BDIR}")


def score(ans_path):
    answers = {a["task_id"]: a["answer"] for a in load_jsonl(ans_path)}
    yt = {t["task_id"]: t["year"] for t in load_jsonl(os.path.join(BDIR, "year_truth.jsonl"))}
    diffs = [abs(int(answers[k]) - y) for k, y in yt.items() if k in answers and answers[k] is not None]
    if diffs:
        diffs.sort()
        w10 = sum(d <= 10 for d in diffs) / len(diffs)
        w1 = sum(d <= 1 for d in diffs) / len(diffs)
        print(f"YEAR: n={len(diffs)}/{len(yt)}  median abs err={diffs[len(diffs)//2]}  "
              f"mean={sum(diffs)/len(diffs):.1f}  within±1y={w1:.0%}  within±10y={w10:.0%}")
    suffix = "_v2" if "--v2" in sys.argv else ""
    rt = {t["task_id"]: set(t["truth"]) for t in load_jsonl(os.path.join(BDIR, f"retrieval_truth{suffix}.jsonl"))}
    p_s, r_s, n = 0.0, 0.0, 0
    for k, truth in rt.items():
        if k not in answers or not isinstance(answers[k], list):
            continue
        pred = set(answers[k])
        n += 1
        p_s += len(pred & truth) / len(pred) if pred else 0
        r_s += len(pred & truth) / len(truth)
    if n:
        print(f"RETRIEVAL: n={n}/{len(rt)}  precision={p_s/n:.0%}  recall={r_s/n:.0%}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "score":
        score(sys.argv[2])
    else:
        export()
