# Consolidate fusion-judgment verdicts -> data/linking/fusion_links.jsonl
# - joins verdicts back to candidate pairs (ids were hidden from judges only in the visible batch files)
# - scores the decoy control (false-accept rate) and EXCLUDES decoys from output
# - emits linking rows in the two-layer format (revisable; deleting a row undoes the link)
import json, sys
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]      # repo root (scripts live one folder down)
SCRATCH = Path(sys.argv[1]) if len(sys.argv) > 1 else None  # scratchpad dir holding fusion-judge/ + keys
if SCRATCH is None:
    raise SystemExit("usage: consolidate_fusion.py <scratchpad-dir>")
JDIR = SCRATCH / "fusion-judge"

pairs = {p["pair_id"]: p for p in json.loads((SCRATCH / "fusion_pairs_full.json").read_text(encoding="utf-8"))}
decoy_key = json.loads((SCRATCH / "fusion_decoy_key.json").read_text(encoding="utf-8"))

verdicts = {}
for f in sorted(JDIR.glob("verdicts-*.jsonl")):
    for line in f.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        v = json.loads(line)
        verdicts[v["pair_id"]] = v

missing = [pid for pid in pairs if pid not in verdicts]
extra = [pid for pid in verdicts if pid not in pairs]
print(f"verdicts: {len(verdicts)} / pairs: {len(pairs)}  missing: {len(missing)} extra: {len(extra)}")
if missing:
    print("MISSING:", missing[:20])

# decoy control
d_total = d_accepted = 0
for pid in decoy_key:
    v = verdicts.get(pid)
    if not v:
        continue
    d_total += 1
    if v["verdict"] == "same-result":
        d_accepted += 1
        print(f"DECOY FALSE-ACCEPT: {pid} conf={v['confidence']} reason={v['reason']}")
print(f"decoy control: {d_accepted}/{d_total} falsely accepted ({(d_accepted/max(d_total,1)):.1%})")

# real rows only
rows, dist = [], Counter()
for pid, p in pairs.items():
    if pid in decoy_key:
        continue
    v = verdicts.get(pid)
    if not v:
        continue
    dist[v["verdict"]] += 1
    if v["verdict"] not in ("same-result", "related"):
        continue
    rows.append({
        "relation": "harvest-date-link" if v["verdict"] == "same-result" else "harvest-date-related",
        "from": p["from_id"], "to": p["to_id"], "tier": p["tier"],
        "method": "llm-judge", "model": "opus", "confidence": v["confidence"],
        "reason": v["reason"], "decided_at": "2026-09-01", "decided_by": "fusion-judge-v1",
    })
print("verdict distribution (real pairs):", dict(dist))
same_dated = sum(1 for r in rows if r["relation"] == "harvest-date-link")
out = ROOT / "data" / "linking" / "fusion_links.jsonl"
with open(out, "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"wrote {out}: {len(rows)} rows ({same_dated} same-result date links)")
