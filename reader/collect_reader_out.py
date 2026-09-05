"""Collect fleet results (<stage>/out/<task>.json from fleet_run.py) into reader-output files.

usage: collect_reader_out.py <pulled_out_dir> <dest_dir>

Each fleet result is the `claude -p --output-format json` envelope; its `result` field holds the agent's answer,
which the reader prompt asks for as one JSON object per proof ({"proof_id": ..., "ingredients": [...]}).
Writes <dest_dir>/<task>.txt with one such object per line (the format build_audit_desk.py / apply_reader_layer.py
read) and prints how many proofs came back, how many tasks errored, and any proofs with zero ingredients.
"""
import glob, json, os, re, sys

def objects_from(text):
    r"""Pull the JSON objects containing "proof_id" out of the agent's answer. One object per line is the
    requested format, so try that first; then a string-aware brace scan for objects wrapped in prose or
    code fences (braces inside JSON strings, e.g. LaTeX \frac{1}{2} or \right\}, must not count)."""
    out, seen = [], set()
    def keep(o):
        if isinstance(o, dict) and "proof_id" in o and o["proof_id"] not in seen:
            seen.add(o["proof_id"]); out.append(o)
    for line in text.splitlines():
        line = line.strip().strip("`")
        if line.startswith("{") and line.endswith("}"):
            try:
                keep(json.loads(line)); continue
            except json.JSONDecodeError:
                pass
    if out:
        return out
    depth, start, in_str, esc = 0, None, False, False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                chunk = text[start:i + 1]
                if '"proof_id"' in chunk:
                    try:
                        keep(json.loads(chunk))
                    except json.JSONDecodeError:
                        pass
                start = None
    return out

def main():
    src, dst = sys.argv[1], sys.argv[2]
    os.makedirs(dst, exist_ok=True)
    n_tasks = n_err = 0
    best = {}                                    # proof_id -> (rank, task, obj): newest non-empty result wins
    for f in sorted(glob.glob(os.path.join(src, "*.json"))):
        n_tasks += 1
        try:
            env = json.load(open(f, encoding="utf-8"))
        except json.JSONDecodeError:
            n_err += 1; continue
        if env.get("is_error"):
            n_err += 1; continue
        objs = objects_from(str(env.get("result", "")))
        if not objs:
            n_err += 1; continue
        task, mtime = os.path.basename(f)[:-5], os.path.getmtime(f)
        for o in objs:
            rank = (1 if o.get("ingredients") else 0, mtime)   # a re-run that found ingredients beats an older empty one
            if o["proof_id"] not in best or rank > best[o["proof_id"]][0]:
                best[o["proof_id"]] = (rank, task, o)
    by_task = {}
    for pid, (rank, task, o) in best.items():
        by_task.setdefault(task, []).append(o)
    for f in glob.glob(os.path.join(dst, "*.txt")):
        os.remove(f)
    for task, objs in by_task.items():
        with open(os.path.join(dst, task + ".txt"), "w", encoding="utf-8") as g:
            for o in objs:
                g.write(json.dumps(o, ensure_ascii=False) + "\n")
    zero = [pid for pid, (rank, task, o) in best.items() if not o.get("ingredients")]
    print(f"{n_tasks} tasks, {n_err} errored/empty, {len(best)} proofs with reader output, {len(zero)} with zero ingredients")
    if zero:
        print("zero-ingredient proofs:", zero[:20])

if __name__ == "__main__":
    main()
