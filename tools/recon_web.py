#!/usr/bin/env python3
"""recon_web.py - web-grounded, cited answers via the Perplexity Agent API, for this project's recon docs.

The RECON-*.md workflow ("every claim from a fetched source, URLs inline, UNVERIFIED marked") needs exactly
this: one question in, a sourced answer out. Uses POST https://api.perplexity.ai/v1/agent through the official
SDK (`pip install perplexityai`); the key is read from the PERPLEXITY_API_KEY environment variable only.

  python recon_web.py "What license is Goedel-Pset-v1 released under?"          # preset medium (default)
  python recon_web.py -p high "Current theorem count in Lean 4 Mathlib?"        # deeper: gpt-5.6-sol, 15 steps
  python recon_web.py -m openai/gpt-5.6-sol "..."                               # explicit model (+web_search/fetch_url)
  python recon_web.py --schema licenses.schema.json --schema-name licenses "..."# structured JSON out
  python recon_web.py --follow <response_id> "And the dataset size?"            # multi-turn continuation
  python recon_web.py -o RECON-foo-2026-08-31.md "..."                          # append answer+sources to a file

Presets (docs.perplexity.ai/docs/agent-api/presets): fast | low | medium | high | xhigh | wide-research.
Smoke test:  python recon_web.py --smoke     (one minimal request; prints status/shape only, never the key)
"""
from __future__ import annotations

import argparse
import json
import os
import sys

PRESETS = ("fast", "low", "medium", "high", "xhigh", "wide-research")
CONSOLE = "https://console.perplexity.ai"


def _client():
    if not os.environ.get("PERPLEXITY_API_KEY"):
        sys.exit(f"PERPLEXITY_API_KEY is not set. Create a key in the API Console ({CONSOLE}) and "
                 "export it in your terminal (never paste it into chat or commit it).")
    from perplexity import Perplexity  # deferred so --help works without the SDK
    return Perplexity()  # SDK reads PERPLEXITY_API_KEY itself


def ask(question: str, *, preset: str | None = "medium", model: str | None = None,
        schema: dict | None = None, schema_name: str = "result",
        previous_response_id: str | None = None, max_output_tokens: int | None = None):
    """One Agent API call. Returns the SDK response object (answer in .output_text)."""
    kwargs: dict = {"input": question}
    if model:
        kwargs["model"] = model
        kwargs["tools"] = [{"type": "web_search"}, {"type": "fetch_url"}]  # a bare model has no tools
        if model.startswith("anthropic/") and max_output_tokens is None:
            max_output_tokens = 8192  # required for anthropic/* models (api-reference/agent-post)
    else:
        kwargs["preset"] = preset or "medium"  # presets bundle model + tools + limits
    if max_output_tokens is not None:
        kwargs["max_output_tokens"] = max_output_tokens
    if previous_response_id:
        kwargs["previous_response_id"] = previous_response_id
    if schema is not None:
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "schema": {**schema, "additionalProperties": False}},
        }
    return _client().responses.create(**kwargs)


def sources(response) -> list[dict]:
    """URL citations: text-annotation URLs first (what the answer actually cites), then search-result metadata."""
    out, seen = [], set()
    for item in getattr(response, "output", None) or []:
        itype = getattr(item, "type", None)
        if itype == "message":
            for part in getattr(item, "content", None) or []:
                for ann in getattr(part, "annotations", None) or []:
                    url = getattr(ann, "url", None)
                    if url and url not in seen:
                        seen.add(url)
                        out.append({"url": url, "title": getattr(ann, "title", None) or url, "cited": True})
        elif itype == "search_results":
            for r in getattr(item, "results", None) or []:
                url = getattr(r, "url", None)
                if url and url not in seen:
                    seen.add(url)
                    out.append({"url": url, "title": getattr(r, "title", None) or url, "cited": False})
    return out


def render_markdown(question: str, response) -> str:
    lines = [f"### Q: {question}", "", response.output_text or "(empty output_text)", "", "**Sources**"]
    srcs = sources(response)
    lines += [f"- {'[cited] ' if s['cited'] else ''}[{s['title']}]({s['url']})" for s in srcs] or ["- (none returned)"]
    lines += ["", f"<!-- response_id: {response.id} (use --follow for a follow-up) -->", ""]
    return "\n".join(lines)


def smoke() -> int:
    """Minimal real request; prints only status/shape — never the key."""
    try:
        r = ask("What year was Lean 4 first released? One sentence.", preset="fast")
    except Exception as e:  # SDK raises typed errors; report class + status, no secrets
        status = getattr(e, "status_code", None)
        hint = {401: f"authentication problem — check/rotate the key in {CONSOLE}",
                429: "rate limited — honor Retry-After and retry"}.get(status, "")
        print(f"SMOKE FAIL: {type(e).__name__} status={status} {hint}", file=sys.stderr)
        return 1
    n_src = len(sources(r))
    print(f"SMOKE OK: object={getattr(r, 'object', '?')} status={getattr(r, 'status', '?')} "
          f"output_items={len(getattr(r, 'output', []) or [])} sources={n_src} "
          f"output_text_chars={len(r.output_text or '')}")
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252; answers contain arbitrary Unicode
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("question", nargs="?", help="the recon question")
    ap.add_argument("-p", "--preset", choices=PRESETS, default="medium")
    ap.add_argument("-m", "--model", help="explicit model (e.g. openai/gpt-5.6-sol); overrides --preset")
    ap.add_argument("--schema", help="path to a JSON-schema file -> structured output (prints JSON)")
    ap.add_argument("--schema-name", default="result", help="json_schema name (1-64 alphanumerics)")
    ap.add_argument("--follow", metavar="RESPONSE_ID", help="continue a previous response (multi-turn)")
    ap.add_argument("--max-output-tokens", type=int)
    ap.add_argument("-o", "--out", help="append the markdown (answer + sources) to this file")
    ap.add_argument("--smoke", action="store_true", help="run the minimal smoke test and exit")
    a = ap.parse_args()

    if a.smoke:
        return smoke()
    if not a.question:
        ap.error("a question is required (or --smoke)")

    schema = json.load(open(a.schema, encoding="utf-8")) if a.schema else None
    try:
        r = ask(a.question, preset=a.preset, model=a.model, schema=schema, schema_name=a.schema_name,
                previous_response_id=a.follow, max_output_tokens=a.max_output_tokens)
    except Exception as e:
        status = getattr(e, "status_code", None)
        if status == 401:
            sys.exit(f"401 authentication error — create/rotate the key in {CONSOLE} and re-export "
                     "PERPLEXITY_API_KEY (never paste it into chat).")
        if status == 429:
            sys.exit("429 rate limited — wait for the Retry-After window and retry "
                     "(docs.perplexity.ai/docs/admin/rate-limits-usage-tiers).")
        sys.exit(f"Agent API error: {type(e).__name__} status={status}: {e}")

    if schema is not None:
        print(r.output_text)  # structured: output_text is the JSON document
        print(f"response_id: {r.id}", file=sys.stderr)
        return 0
    md = render_markdown(a.question, r)
    print(md)
    if a.out:
        with open(a.out, "a", encoding="utf-8", newline="\n") as f:
            f.write("\n" + md)
        print(f"(appended to {a.out})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
