#!/usr/bin/env python3
"""build_atlas.py - inject data/build/graph.json into atlas/ripeness-atlas.template.html
(`const G = __GRAPH_DATA__;`) and write the publishable page. usage: build_atlas.py <out.html>"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).parent
out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "atlas" / "ripeness-atlas.html"
g = json.loads((ROOT / "data/build/graph.json").read_text(encoding="utf-8"))
# keep the page small: drop bulky per-node raw text beyond what the drawer shows
for n in g.get("nodes", []):
    if isinstance(n.get("text"), str) and len(n["text"]) > 600:
        n["text"] = n["text"][:600] + " …"
# display policy: resolved edges from every layer, but unresolved markers only from the explicit layer —
# reader-layer names await the judged linking pass and would otherwise flood the map (ingredient_policy: explicit-only for dangling)
g["dangling"] = [e for e in g.get("dangling", []) if not str(e.get("provenance", "")).startswith("reader-")
                 and e.get("kind") not in ("definition", "axiom", "technique") and e.get("target_kind") != "implicit"]   # strict-ripeness display policy
for e in g["dangling"]:
    e.pop("meta", None)
tpl = (ROOT / "atlas/ripeness-atlas.template.html").read_text(encoding="utf-8")
assert "__GRAPH_DATA__" in tpl
html = tpl.replace("__GRAPH_DATA__", json.dumps(g, ensure_ascii=False))
out.write_text(html, encoding="utf-8")
print(f"wrote {out} ({out.stat().st_size//1024} KB): nodes {len(g['nodes'])}, edges {len(g['edges'])}, dangling {len(g['dangling'])}")
