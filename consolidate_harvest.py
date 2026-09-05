#!/usr/bin/env python3
"""consolidate_harvest.py - merge all date-harvest batches into one validated event/instance layer.

Policies applied here (not in the batches):
- RECENCY CAP: any event with when.min >= 2025 is forced to confidence "low" + flag "recent-unverified"
  (harvest found vandalism/injected claims in recent Wikipedia content, incl. a self-referential fake).
- Person-page/junk exclusion list (from batch report flags).
- Slug-level dedupe across batches (slices are disjoint; duplicates indicate a bug).
Writes data/dates/harvest/consolidated/{events.jsonl,instances.jsonl} and prints a stats report.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.abspath(__file__))
HDIR = os.path.join(ROOT, "data", "dates", "harvest")
OUT = os.path.join(HDIR, "consolidated")

# person pages / non-results flagged in batch reports
EXCLUDE_SLUGS = {"Bernhard_Riemann", "Fermat", "Euclid", "Lerner_symmetry_theorem", "Marginal_value_theorem"}


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as e:
                    sys.exit(f"BAD JSON {path}:{i}: {e}")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    batches = sorted(glob.glob(os.path.join(HDIR, "batch-*")))
    events_rows, inst_rows, seen_slugs, dupes, capped = [], [], set(), [], 0
    per_batch = {}
    for b in batches:
        ep, ip = os.path.join(b, "events.jsonl"), os.path.join(b, "instances.jsonl")
        if not os.path.exists(ep):
            print(f"note: {os.path.basename(b)} incomplete, skipping")
            continue
        n = dated = 0
        for r in load_jsonl(ep):
            n += 1
            slug = r.get("slug")
            if slug in EXCLUDE_SLUGS:
                continue
            if slug in seen_slugs:
                dupes.append(slug)
                continue
            seen_slugs.add(slug)
            for e in r.get("events") or []:
                w = e.get("when") or {}
                if (w.get("min") or 0) >= 2025:
                    if e.get("provenance", {}).get("confidence") != "low":
                        capped += 1
                    e.setdefault("provenance", {})["confidence"] = "low"
                    e["flags"] = sorted(set(e.get("flags", []) + ["recent-unverified"]))
            if r.get("events"):
                dated += 1
            events_rows.append(r)
        for r in load_jsonl(ip):
            if r.get("instance_id", "").split(":")[-1] not in EXCLUDE_SLUGS and r.get("local_name"):
                inst_rows.append(r)
        per_batch[os.path.basename(b)] = (n, dated)

    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "events.jsonl"), "w", encoding="utf-8", newline="\n") as f:
        for r in events_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(os.path.join(OUT, "instances.jsonl"), "w", encoding="utf-8", newline="\n") as f:
        for r in inst_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    total_events = sum(len(r.get("events") or []) for r in events_rows)
    etypes = Counter(e.get("type") for r in events_rows for e in r.get("events") or [])
    econf = Counter((e.get("provenance") or {}).get("confidence") for r in events_rows for e in r.get("events") or [])
    dated_n = sum(1 for r in events_rows if r.get("events"))
    proved_n = sum(1 for r in events_rows if any(e.get("type") in ("proved", "disproved") for e in r.get("events") or []))
    yrs = [e["when"]["min"] for r in events_rows for e in r.get("events") or [] if e.get("when")]
    print(f"batches merged: {len(per_batch)}  results: {len(events_rows)}  dated: {dated_n}  "
          f"with proved/disproved: {proved_n}")
    print(f"events: {total_events}  by type: {dict(etypes)}")
    print(f"confidence: {dict(econf)}  recency-capped: {capped}")
    print(f"year span: {min(yrs)} .. {max(yrs)}" if yrs else "no dated events")
    print(f"instances: {len(inst_rows)}  cross-batch slug dupes: {dupes or 'none'}")
    for b, (n, d) in per_batch.items():
        print(f"  {b}: {n} results, {d} dated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
