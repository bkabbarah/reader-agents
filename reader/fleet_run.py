#!/usr/bin/env python3
"""fleet_run.py - account-rotating headless Claude Code runner (runs on vm-inimai).

usage: python3 fleet_run.py <stage_dir> [--model opus] [--workers 3]
  <stage_dir>/tasks/*.txt   prompts (one file = one claude -p call)
  <stage_dir>/out/<task>.json  raw --output-format json result
  <stage_dir>/out/<task>.txt   the model's result text
  <stage_dir>/fleet.log
Accounts: CLAUDE_CONFIG_DIR rotates over ACCOUNTS; a worker that hits a usage/rate limit
marks its account exhausted (with a 30-min cool-off) and the task is re-queued for
another account. Tasks are claimed atomically by rename. Idempotent: re-run to resume.
Never uses the box's default ~/.claude (that is Inimai's).
"""
import json, os, re, subprocess, sys, threading, time, shutil
from pathlib import Path

HOME = os.path.expanduser("~")
ACCOUNTS = [f"{HOME}/{d}" for d in os.environ.get("FLEET_ACCOUNTS", ".claude").split(":")]   # CLAUDE_CONFIG_DIRs to rotate over, colon-separated
LIMIT_RE = re.compile(r"usage limit|rate limit|limit reached|out of extra usage|hit your limit|overloaded|429|disabled Claude subscription access|API key instead|not authorized|authentication", re.I)

stage = Path(sys.argv[1])
model = sys.argv[sys.argv.index("--model") + 1] if "--model" in sys.argv else "opus"
workers = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else len(ACCOUNTS)
tasks, running, out = stage / "tasks", stage / "running", stage / "out"
running.mkdir(exist_ok=True); out.mkdir(exist_ok=True)
for f in running.glob("*.txt"):          # resume: anything left running was interrupted
    shutil.move(str(f), tasks / f.name)
lock = threading.Lock()
cooloff = {a: 0.0 for a in ACCOUNTS}

def log(msg):
    with lock, open(stage / "fleet.log", "a") as f:
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}\n")

def claim():
    with lock:
        for f in sorted(tasks.glob("*.txt")):
            if (out / (f.stem + ".txt")).exists():
                f.unlink(); continue
            dest = running / f.name
            f.rename(dest)
            return dest
    return None

_rr = [0]
def pick_account():
    with lock:
        ok = [a for a in ACCOUNTS if cooloff[a] <= time.time()]
        if not ok: return None
        _rr[0] += 1
        return ok[_rr[0] % len(ok)]

def worker(wid):
    while True:
        task = claim()
        if task is None:
            return
        acct = pick_account()
        if acct is None:
            log(f"w{wid}: all accounts cooling off; waiting 10 min"); task.rename(tasks / task.name); time.sleep(600); continue
        prompt = task.read_text(encoding="utf-8")
        t0 = time.time()
        env = dict(os.environ, CLAUDE_CONFIG_DIR=acct, PATH=f"{HOME}/.local/bin:" + os.environ.get("PATH", ""))
        try:
            r = subprocess.run(["claude", "-p", prompt, "--model", model, "--output-format", "json"],
                               capture_output=True, text=True, env=env, timeout=1800, cwd="/tmp")
            raw = r.stdout
            res = json.loads(raw) if raw.strip().startswith("{") else {"is_error": True, "result": raw + r.stderr}
        except Exception as e:
            res = {"is_error": True, "result": f"runner exception: {e}"}
            raw = json.dumps(res)
        text = str(res.get("result", ""))
        limited = bool(LIMIT_RE.search(text[:300])) or res.get("api_error_status") == 429 or (res.get("is_error") and LIMIT_RE.search(text))
        if limited:
            with lock:
                cooloff[acct] = time.time() + (6 * 3600 if "subscription access" in text else 1800)
            log(f"w{wid}: LIMIT on {Path(acct).name} for {task.name}; re-queued")
            task.rename(tasks / task.name)
            continue
        (out / (task.stem + ".json")).write_text(raw, encoding="utf-8")
        (out / (task.stem + ".txt")).write_text(text, encoding="utf-8")
        task.unlink()
        log(f"w{wid}: done {task.name} acct={Path(acct).name} err={bool(res.get('is_error'))} dt={time.time()-t0:.0f}s")

log(f"fleet start: stage={stage} model={model} workers={workers} tasks={len(list(tasks.glob('*.txt')))}")
ths = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(workers)]
[t.start() for t in ths]; [t.join() for t in ths]
log("fleet finished (queue empty)")
