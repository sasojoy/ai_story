"""Does the gate still tell the truth? On one commit:

  1. --rounds c, base against base: green. --rounds main,v,extra walks those instead: wave D's false rows only showed on main, v and extra.
  2. The same again: the fingerprint is the same (noise counts are allowed to move, they are not in it).
  3. Positive controls, both have to go red: .card padding changed, style.css moved to the end of the stylesheets.
     First through the corpus replay (quick), then through the c round.
  4. A comment added to a stylesheet: the replay runs from the gate and stays green.
  5. Hostile pages: one stuck in a loop stops the walk with exit 2 instead of hanging, an alert on the head alone goes red and the walk goes on.

usage: python selftest.py --sha <x> --out <dir> [--rounds c] [--ports a,b] [--cdp-ports a,b] [--chrome ...] [--node ...] [--replay-only | --walk-only] [--only flows]

Exit 0 all held, 1 something did not. summary: <out>/selftest.json.
"""
import argparse
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import gate  # noqa: E402
import replay  # noqa: E402
import unpack  # noqa: E402


def _gate(a, out_name, *extra, rounds="c") -> dict:
    out = os.path.join(a.out, out_name)
    argv = ["--base", a.sha, "--head", a.sha, "--out", out, "--rounds", rounds, *extra]
    if a.only:
        argv += ["--only", a.only]
    for flag, value in (("--ports", a.ports), ("--cdp-ports", a.cdp_ports), ("--chrome", a.chrome), ("--node", a.node), ("--repo", a.repo)):
        if value:
            argv += [flag, value]
    t0 = time.monotonic()
    code = gate.main(argv)
    with open(os.path.join(out, "summary.json"), encoding="utf-8") as f:
        s = json.load(f)
    s["code"], s["took"] = code, round(time.monotonic() - t0)
    return s


def _replay_controls(a, rows: list) -> None:
    corpus = os.path.join(a.out, "corpus")
    work = os.path.join(a.out, "replay_work")
    shutil.rmtree(work, ignore_errors=True)
    copy = unpack.unpack(a.repo, a.sha, os.path.join(work, "base"))
    web = os.path.join(copy, "web")
    dom = os.path.join(corpus, a.rounds.split(",")[0], "base", "dom")
    r = replay.replay(dom, web, web, os.path.join(work, "same"), cdp_ports=a.cdp_ports, chrome=a.chrome, node=a.node)
    rows.append(("replay same against same", not r["real"] and not r["tool"], f"snapshots {r['snapshots']} (with #map-host {r['with_map_host']}) real {len(r['real'])} noise {r['noise']} {r['seconds']}s"))
    r = replay.replay(dom, web, web, os.path.join(work, "anim"), frozen=False, shoot=False, cdp_ports=a.cdp_ports, chrome=a.chrome, node=a.node)
    rows.append(("replay animation pass, same against same", not r["real"] and not r["tool"], f"real {len(r['real'])} {r['seconds']}s"))
    for which in gate.MUTATIONS:
        other = os.path.join(work, which)
        shutil.copytree(web, os.path.join(other, "web"))
        gate.mutate(other, which)
        r = replay.replay(dom, web, os.path.join(other, "web"), os.path.join(work, "out_" + which), cdp_ports=a.cdp_ports, chrome=a.chrome, node=a.node)
        rows.append((f"replay --mutate {which} goes red", bool(r["real"]), f"real {len(r['real'])}: {sorted({x['class'] for x in r['real']})}"))
    shutil.rmtree(work, ignore_errors=True)


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sha", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--repo", default=gate.REPO)
    ap.add_argument("--rounds", default="c", help="what the two same walks cover (the positive controls stay on c); the first one is the replay's corpus")
    ap.add_argument("--ports")
    ap.add_argument("--cdp-ports")
    ap.add_argument("--chrome")
    ap.add_argument("--node")
    ap.add_argument("--replay-only", action="store_true", help="reuse the corpus already under --out, only the replay controls")
    ap.add_argument("--walk-only", action="store_true", help="skip the replay controls")
    ap.add_argument("--only", help="flows of the c round, for a shorter walk (accounts,smoke,craft is about 2.5 minutes a time, the whole round about 8)")
    a = ap.parse_args(argv)
    a.out = os.path.abspath(a.out)
    os.makedirs(a.out, exist_ok=True)
    rows = []
    corpus = os.path.join(a.out, "corpus")
    if not a.replay_only:
        s1 = _gate(a, "same1", "--keep-corpus", corpus, rounds=a.rounds)
        rows.append(("base against base is green", s1["code"] == 0, f"exit {s1['code']} real {len(s1['real'])} noise {s1['noise']} {s1['took']}s"))
        s2 = _gate(a, "same2", rounds=a.rounds)
        rows.append(("the same walk again has the same fingerprint", s1["fingerprint"] == s2["fingerprint"], f"{s1['fingerprint']} / {s2['fingerprint']} noise {s2['noise']}"))
    if not a.walk_only:
        _replay_controls(a, rows)
    if not a.replay_only:
        for which in gate.MUTATIONS:
            s = _gate(a, "mut_" + which, "--mutate", which)
            rows.append((f"c round --mutate {which} goes red", s["code"] == 1, f"exit {s['code']} real {len(s['real'])}: {sorted({x['class'] for x in s['real']})}"))
            rows.append((f"c round --mutate {which} ran the replay from the gate", s["replay"]["ran"] and any(x["round"].startswith("replay") for x in s["real"]), f"{s['replay']}"[:300]))
        s = _gate(a, "quiet", "--mutate", gate.QUIET)
        rows.append(("a comment in a stylesheet runs the replay and stays green", s["code"] == 0 and s["replay"]["ran"], f"exit {s['code']} real {[x['class'] for x in s['real']][:6]} {s['replay']}"[:300]))
        a.only = a.only or "accounts,smoke"
        s = _gate(a, "hostile_hang", "--mutate", "page-hang")
        rows.append(("a page stuck in a loop is exit 2, not a hang", s["code"] == 2, f"exit {s['code']} {s['took']}s tool {[t[:160] for t in s['tool'][:2]]}"))
        s = _gate(a, "hostile_alert", "--mutate", "page-alert")
        rows.append(("an alert on the head alone goes red and the walk goes on", s["code"] == 1 and any(x["class"] == "console-head-only" for x in s["real"]), f"exit {s['code']} real {[x['class'] for x in s['real']][:6]}"))
    held = all(ok for _, ok, _ in rows)
    for name, ok, detail in rows:
        print("ok  " if ok else "FAIL", name, "|", detail)
    with open(os.path.join(a.out, "selftest.json"), "w", encoding="utf-8") as f:
        json.dump([{"check": n, "held": ok, "detail": d} for n, ok, d in rows], f, ensure_ascii=False, indent=1)
    return 0 if held else 1


if __name__ == "__main__":
    sys.exit(main())
