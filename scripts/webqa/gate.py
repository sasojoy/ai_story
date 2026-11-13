"""The web comparison gate: walk the same screens on two commits and say whether anything a player can see changed.

    python scripts/webqa/gate.py --base <sha> --head <sha> --out <dir>

Exit 0 green, 1 real differences, 2 the tool broke (no browser, node or PIL; a server did not start; a patch target is gone;
the driver died or stopped answering; a flow threw; a scene that has to be reached was not). Everything below --out is throwaway except
summary.json, report.txt and red/. Noise is classified by noise.py; only what is left counts.
--changed-files that picks no round (an empty list; package files NOT_ON_TABLE says no round reaches while they are off) is exit 0 with
nothing unpacked, and summary.not_walked says which files and why. --dry-run prints the pick and stops.
--new <pkg,...> lists the css-rules of the new packages' own sheets (web/<pkg>.css) as NEW instead of red; every other sheet counts as before.
Codes (identity) never go to the server log (batch 208: only the notice line, LOG_LINE): a round that reaches a code reads the fake
senders' outbox, --outbox, which serve.py appends to <round>/<base|head>.outbox.jsonl when identity and fake_services are on. No round
reaches a code yet (identity is off in season21): ready, never walked.

What the walk cannot see: it freezes animation, and it takes no pictures at 640, 641 and 900. Both come from the corpus replay (replay.py), and the
replay is about stylesheets, so it runs here when a stylesheet or index.html differs between the two commits; summary.replay says whether it ran and
why. Without it those three windows only have the page's size behind them: used values moving there are counted apart, as layout-no-pixels.
"""
import argparse
import concurrent.futures
import glob
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
REPO = os.path.dirname(os.path.dirname(HERE))
ROUNDS = ("main", "x", "y", "z", "v", "c", "cs", "extra")
MUST_REACH = os.path.join(HERE, "must_reach.txt")
FORBIDDEN_PORTS = {7861}
DETACHED = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS if os.name == "nt" else 0
STATIC_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".ico", ".woff", ".woff2", ".mp3", ".ogg")
STYLE_EXT = (".css", ".html")
MUTATIONS = ("card-padding", "css-last")
PKG_CSS = "pkg-css"  # batch 110: one rule more in web/identity.css: red without --new, NEW (not red) with --new identity; not a selftest control
HOSTILE = {  # selftest only: a page that does what the walk must survive
    "page-hang": 'document.addEventListener("click", () => { for (;;) {} }, true);',
    "page-alert": 'document.addEventListener("click", () => { alert("webqa selftest"); }, { capture: true, once: true });',
}
QUIET = "css-comment"  # selftest only: a stylesheet that differs with nothing to see: the replay runs and stays green
ROUND_SECONDS = {"fast": 5400, "full": 16200}  # the slowest round so far, main on fast, took 34 minutes
PORT_LOCK = threading.Lock()
COVERAGE = os.path.join(HERE, "coverage.json")  # round -> web files it calls into (batch 107; scripts/webqa/coverage.py build/check)
SHELL_FILES = {"web/app.js", "web/main.js", "web/shell.js", "web/index.html", "web/style.css"}  # every round stands on these


NOT_ON_TABLE = {  # batch 110: page files no round reaches, and why; coverage.py check wants every web/*.js on the table, in SHELL_FILES or here
    "web/sw.js": "not a page script: the notify package's route serves it to the service worker",
    "web/explore.js": "the gather branches (explore:gather) left the engine with explore three-ways (batch 13): no season offers the option",
    "web/state.js": "top-level state only, no named function to count (every page loads it); not a package file, so a change walks every round",
    "web/tale_page.js": "its own page (/zhanji/<code>, tale_html.py), not loaded by /; no round calls its toast; not a package file, so a change walks every round",
    "web/zhuan_page.js": "its own page (zhuan_html.py), not loaded by /; no round calls its set or toast; not a package file, so a change walks every round",
    "web/titles.js": "the titles package (Config.titles) is off in every profile the walk runs: no main.titles, so nothing calls into it",
    "web/terms.js": "the terms package (Config.terms) is off in every profile the walk runs: /api/terms is 404, so its sheet never shows",
    "web/jieyi.js": "the jieyi package (Config.jieyi) is off in every profile the walk runs: no main.jieyi and no offer card, so nothing calls into it",
    "web/mail.js": "the mail package (Config.mail) is off in every profile the walk runs: no main.mail, so the 信匣 entry is not drawn and nothing calls into it",
    "web/zongmen.js": "the zongmen package (Config.zongmen) is off in every profile the walk runs: no main.zongmen, so nothing calls into it",
    "web/guard.js": "the guard package (Config.guard) is off in every profile the walk runs: no main.guard, so the 養成冊 is not drawn and nothing calls into it",
    "web/codex.js": "the codex package (Config.codex) is off in every profile the walk runs: no main.codex, so the 江湖錄 tab is not drawn and nothing calls into it",
    "web/intro.js": "serve.py turns the intro package (Config.intro) off for the walk: every walk account is new and the 開場 layer would cover the clicks; tianxia/features/intro/tests covers it",
}


def package_file(f: str, repo: str = REPO) -> bool:
    """web/<pkg>.js or web/<pkg>.css with tianxia/features/<pkg>/ there. Anything else under web/ (shop.css, battle_panel.css, tale_page.js…) is the shell."""
    name = f[len("web/"):] if f.startswith("web/") else ""
    stem, ext = os.path.splitext(name)
    return bool(stem) and "/" not in name and ext in (".js", ".css") and os.path.isdir(os.path.join(repo, "tianxia", "features", stem))


def rounds_detail(changed, table, rounds=ROUNDS, not_on_table=NOT_ON_TABLE, repo=REPO):
    """rounds_for with the files left unwalked: (rounds, why, not_walked). A package's file no round reaches is not walked only when
    NOT_ON_TABLE says why; without a reason it walks every round (a table that was never built must not leave a package unchecked)."""
    changed = [c.strip().replace("\\", "/") for c in changed if c.strip()]
    if not changed:
        return [], "--changed-files lists no file: no round", []
    if not table:
        return list(rounds), "no coverage.json: every round", []
    picked, not_walked = set(), []
    for f in changed:
        if f in SHELL_FILES or f.startswith("scripts/webqa/"):
            return list(rounds), f"{f} is the shell or the tool: every round", []
        if not f.startswith("web/"):
            return list(rounds), f"{f} is outside web/: every round", []
        if not package_file(f, repo):
            return list(rounds), f"{f} is the shell (no tianxia/features/ package of that name): every round", []
        key = f[:-4] + ".js" if f.endswith(".css") else f
        hit = {r for r in rounds if key in table.get(r, ())}
        if not hit:
            if key in not_on_table:
                not_walked.append(f"{f}: no round reaches it ({not_on_table[key]})")
                continue
            return list(rounds), f"{f} is reached by no round in coverage.json and NOT_ON_TABLE gives no reason: every round", []
        picked |= hit
    got = [r for r in rounds if r in picked]
    why = "from coverage.json: " + ", ".join(sorted(changed)) if got else "no changed file is reached by a round: no round"
    return got, why, not_walked


def rounds_for(changed, table, rounds=ROUNDS, not_on_table=NOT_ON_TABLE, repo=REPO):
    """--changed-files: which rounds to walk, and why. Wide when unsure: the shell (SHELL_FILES, and web/ files with no package of that name),
    scripts/webqa, no table, a file outside web/, or a package file no round reaches with no reason in NOT_ON_TABLE, all walk every round.
    web/<pkg>.css goes with web/<pkg>.js. An empty list walks nothing (not giving --changed-files at all walks every round)."""
    return rounds_detail(changed, table, rounds, not_on_table, repo)[:2]


def load_coverage(path=COVERAGE):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


class ToolBroke(Exception):
    """Something the comparison stands on is not there: exit 2, whatever the pages look like."""


class NothingToWalk(Exception):
    """Batch 110: --changed-files picked no round (an empty list, or package files no round reaches while they are off): exit 0, nothing unpacked."""


def find_chrome(arg: str | None) -> str:
    want = arg or os.environ.get("TIANXIA_WEBQA_CHROME")
    if want:
        if not os.path.exists(want):
            raise ToolBroke(f"no browser at {want}")
        return want
    root = os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright", "chromium-*", "chrome-win64", "chrome.exe")
    found = sorted(glob.glob(root), key=lambda p: int("".join(c for c in p.split("chromium-")[1].split(os.sep)[0] if c.isdigit()) or 0))
    if not found:
        raise ToolBroke("no browser: give --chrome or TIANXIA_WEBQA_CHROME (this tool does not download one)")
    return found[-1]


def find_node(arg: str | None) -> str:
    want = arg or shutil.which("node")
    if not want or not os.path.exists(want):
        raise ToolBroke("no node: give --node")
    return want


def need_pil() -> None:
    try:
        import PIL  # noqa: F401
    except ImportError as e:
        raise ToolBroke("no PIL in this python (requirements-studio.txt)") from e


def port_free(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) != 0


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def pick_ports(arg: str | None, what: str) -> tuple[int, int]:
    if arg:
        try:
            a, b = (int(x) for x in arg.split(","))
        except ValueError as e:
            raise ToolBroke(f"--{what} wants two numbers, a,b") from e
    else:
        a, b = free_port(), free_port()
    for p in (a, b):
        if p in FORBIDDEN_PORTS:
            raise ToolBroke(f"port {p} is the real server's")
        if not port_free(p):
            raise ToolBroke(f"port {p} is taken")
    if a == b:
        raise ToolBroke("two ports, not one")
    return a, b


def kill_tree(pid: int) -> None:
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)


def wait_all(procs, seconds: float, what: str) -> None:
    """Each of them done within seconds, or the tool broke. The caller's finally kills what is left."""
    deadline = time.monotonic() + seconds
    for p in procs:
        try:
            p.wait(max(0.01, deadline - time.monotonic()))
        except subprocess.TimeoutExpired as e:
            raise ToolBroke(f"{what} still running after {seconds}s") from e


def clean_env() -> dict:
    """Nothing from outside decides how the walk goes: no QA_*, no TIANXIA_* (admins, database, profile, public url). The hash seed stays fixed or sets come out in another order."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("QA_", "TIANXIA_"))}
    env.update(PYTHONIOENCODING="utf-8", PYTHONHASHSEED="0")
    return env


def mutate(copy: str, which: str) -> None:
    """Selftest only: a change the gate has to catch."""
    if which == "card-padding":
        p = os.path.join(copy, "web", "style.css")
        with open(p, encoding="utf-8", newline="") as f:
            t = f.read()
        marker = "\n.card {"
        i = t.find(marker)
        if i < 0:
            raise ToolBroke("mutate card-padding: no .card rule")
        j = t.index("}", i)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(t[:j] + "  padding: 31px 23px;\n" + t[j:])
    elif which == "css-last":
        p = os.path.join(copy, "web", "index.html")
        with open(p, encoding="utf-8", newline="") as f:
            lines = f.read().split("\n")
        mine = [i for i, x in enumerate(lines) if "stylesheet" in x and "/static/style.css" in x]
        links = [i for i, x in enumerate(lines) if "stylesheet" in x and "/static/" in x]
        if len(mine) != 1:
            raise ToolBroke("mutate css-last: no single style.css link")
        line = lines.pop(mine[0])
        lines.insert(links[-1], line)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write("\n".join(lines))
    elif which == PKG_CSS:
        p = os.path.join(copy, "web", "identity.css")
        if not os.path.isfile(p):
            raise ToolBroke("mutate pkg-css: no web/identity.css")
        with open(p, "a", encoding="utf-8", newline="") as f:
            f.write("\n.webqa-selftest-rule { outline: 3px solid red; }\n")
    elif which == QUIET:
        with open(os.path.join(copy, "web", "style.css"), "a", encoding="utf-8", newline="") as f:
            f.write("\n/* webqa selftest */\n")
    elif which in HOSTILE:
        with open(os.path.join(copy, "web", "app.js"), "a", encoding="utf-8", newline="") as f:
            f.write("\n" + HOSTILE[which] + "\n")
    else:
        raise ToolBroke(f"no mutation {which}")


VAPID_TEST_SCALAR = 0x7E6B_A110_5EED_0000_0000_0000_0000_0000_0000_0000_0000_0000_0000_0000_0000_0001  # batch 110: a fixed P-256 key, the same on both copies


IDENTITY_TEST_KEYS = {"key": "webqa-test-key-0123456789", "notify_key": "webqa-notify-key-0123456789", "turnstile_secret": "webqa-test"}  # --outbox only


def seed_local(copy: str, outbox: bool = False) -> None:
    """Batch 110: the copy's .local/ before any server starts. git archive leaves it out, and server.py makes the push key on first use
    (server.VAPID_FILE, .local/webpush_vapid.pem): with --jobs N the servers of one copy wrote it at once and one read half a file (MalformedFraming).
    One fixed test key, never the repo's .local/, never random: base and head get the same bytes. With --outbox the identity package's test keys
    go in too (.local/identity.json, identity_base.KEY_FILE), so a copy with the switch on can send a code."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.derive_private_key(VAPID_TEST_SCALAR, ec.SECP256R1())
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    local = os.path.join(copy, ".local")
    os.makedirs(local, exist_ok=True)
    with open(os.path.join(local, "webpush_vapid.pem"), "wb") as f:
        f.write(pem)
    if outbox:
        with open(os.path.join(local, "identity.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(IDENTITY_TEST_KEYS, f)


def static_digest(web: str, ext=STATIC_EXT) -> dict:
    out = {}
    for root, _, files in os.walk(web):
        for n in files:
            if n.lower().endswith(ext):
                p = os.path.join(root, n)
                with open(p, "rb") as f:
                    out[os.path.relpath(p, web).replace(os.sep, "/")] = hashlib.sha256(f.read()).hexdigest()[:16]
    return out


class Server:
    def __init__(self, label, copy, port, db, profile, logs, env, outbox=False):
        self.label, self.port = label, port
        self.out = open(os.path.join(logs, f"{label}.server.out"), "wb")
        self.err = open(os.path.join(logs, f"{label}.server.err"), "wb")
        self.errpath = self.err.name
        extra = ["--outbox", os.path.join(logs, f"{label}.outbox.jsonl")] if outbox else []
        self.proc = subprocess.Popen([sys.executable, "-u", os.path.join(HERE, "serve.py"), copy, str(port), db, profile, *extra], stdout=self.out, stderr=self.err, env=env, cwd=os.path.dirname(db),
                                     creationflags=DETACHED)

    def wait_up(self, seconds=120):
        t0 = time.monotonic()
        while time.monotonic() - t0 < seconds:
            code = self.proc.poll()
            if code is not None:
                self.out.flush()
                with open(self.out.name, encoding="utf-8", errors="replace") as f:
                    said = f.read()[-400:]
                with open(self.errpath, encoding="utf-8", errors="replace") as f:
                    said += f.read()[-800:]
                raise ToolBroke(f"{self.label} server stopped with {code}: {said}")
            if not port_free(self.port):
                return
            time.sleep(0.4)
        raise ToolBroke(f"{self.label} server did not start in {seconds}s")

    def stop(self):
        kill_tree(self.proc.pid)
        self.out.close()
        self.err.close()


def run_round(name, args, work, copies, ports, cdps, origins, env_base) -> dict:
    """One round: fresh servers, fresh databases, two walks side by side. State does not cross rounds."""
    import compare

    folder = os.path.join(work, name)
    os.makedirs(folder)
    env = dict(env_base, QA_ROUND=name, TIANXIA_WEBQA_CHROME=args.chrome)
    if args.corpus == "fast":
        env["QA_FAST"] = "0"
    if args.only:
        env["QA_ONLY"] = args.only
    if args.quick:
        env["QA_QUICK"] = "1"
    servers, drivers = [], []
    t0 = time.monotonic()
    while not all(port_free(p) for p in (*ports, *cdps)):  # the last round's processes are on their way out
        if time.monotonic() - t0 > 20:
            raise ToolBroke(f"ports still taken after the last round: {ports} {cdps}")
        time.sleep(0.5)
    try:
        rows = (("base", copies[0], ports[0], f"http://{origins[0]}", f"http://127.0.0.1:{ports[0]}", cdps[0]), ("head", copies[1], ports[1], f"http://{origins[1]}", f"http://127.0.0.1:{ports[1]}", cdps[1]))
        for label, copy, port, *_ in rows:
            servers.append(Server(label, copy, port, os.path.join(folder, f"{label}.db"), args.profile, folder, env, outbox=args.outbox))
        for s in servers:
            s.wait_up()
        walks = []
        for label, _, _, page, api, cdp in rows:
            walk = os.path.join(folder, label)
            os.makedirs(walk)
            walks.append(walk)
            drivers.append(subprocess.Popen([args.node, "--no-warnings", os.path.join(HERE, "driver.mjs"), label, page, api, walk, str(cdp)],
                                            stdout=open(os.path.join(folder, f"{label}.driver.out"), "wb"), stderr=open(os.path.join(folder, f"{label}.driver.err"), "wb"), env=env, cwd=folder, creationflags=DETACHED))
        wait_all(drivers, args.round_seconds or ROUND_SECONDS[args.corpus], f"round {name}")
    finally:
        for d in drivers:
            if d.poll() is None:
                kill_tree(d.pid)
        for s in servers:
            s.stop()
    for walk, d, label in zip(walks, drivers, ("base", "head")):
        if not os.path.exists(os.path.join(walk, "report.json")):
            with open(os.path.join(folder, f"{label}.driver.err"), encoding="utf-8", errors="replace") as f:
                raise ToolBroke(f"{label} driver left no report (exit {d.returncode}): {f.read()[-800:]}")
    walked = time.monotonic() - t0
    out = compare.compare(walks[0], walks[1], origins, os.path.join(args.out, "red"), red_budget=args.red_left, new_sheets=args.new_sheets)
    args.red_left -= out["red_images"]
    out["seconds"] = round(walked)
    out["compare_seconds"] = round(time.monotonic() - t0 - walked)
    if args.keep:
        out["walks"] = walks
    if args.dom_to:
        for walk, label in zip(walks, ("base", "head")):
            shutil.copytree(os.path.join(walk, "dom"), os.path.join(args.dom_to, name, label, "dom"), dirs_exist_ok=True)
    if not args.keep:
        shutil.rmtree(folder, ignore_errors=True)
    return out


def stylesheet_changes(base_web: str, head_web: str) -> list[str]:
    """The stylesheets and index.html (which lists them) that differ: what the replay is for."""
    a, b = static_digest(base_web, STYLE_EXT), static_digest(head_web, STYLE_EXT)
    return sorted(n for n in set(a) | set(b) if a.get(n) != b.get(n))


def run_replay(args, work, copies, rounds, changed, expect, summary) -> None:
    """Every round's snapshots against both commits' stylesheets: frozen with pictures at all six windows, then unfrozen for the animation declarations."""
    sys.modules.setdefault("gate", sys.modules[__name__])  # replay.py imports this file by name: one module, one ToolBroke
    import replay

    corpus = os.path.join(work, "replay_corpus")
    os.makedirs(corpus)
    for r in rounds:
        folder = os.path.join(args.dom_to, r, "base", "dom")
        for name in os.listdir(folder):
            shutil.copy(os.path.join(folder, name), os.path.join(corpus, f"{r}-{name}"))
    t0 = time.monotonic()
    done = {"ran": True, "changed": changed, "passes": {}}
    summary["replay"] = done
    for label, how in (("replay", {"frozen": True, "shoot": True}), ("replay-anim", {"frozen": False, "shoot": False})):
        res = replay.replay(corpus, os.path.join(copies[0], "web"), os.path.join(copies[1], "web"), os.path.join(args.out, label), chrome=args.chrome, node=args.node, red_budget=args.red_left, new_sheets=args.new_sheets, **how)
        args.red_left -= res["red_images"]
        if "new_css" in res:
            summary["new_css"] += [{"round": label, **x} for x in res["new_css"]]
        kept, excused = apply_expect(res["real"], expect)
        summary["real"] += [{"round": label, **x} for x in kept]
        summary["expected"] += [{"round": label, **x} for x in excused]
        summary["tool"] += [f"{label}: {x}" for x in res["tool"]]
        done["passes"][label] = {"snapshots": res["snapshots"], "shots": res["shots"], "same_shots": res["same_shots"], "real": len(res["real"]), "noise": res["noise"], "seconds": res["seconds"]}
    done["seconds"] = round(time.monotonic() - t0)


def must_reach_rows(rounds) -> tuple[dict, set]:
    """The names each round has to reach, and the rounds whose list came from a --quick walk (no pictures taken yet): those only warn."""
    rows, quick = {}, set()
    if os.path.exists(MUST_REACH):
        with open(MUST_REACH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("# quick: "):
                    quick.add(line[len("# quick: "):])
                elif line and not line.startswith("#"):
                    r, name = line.split(":", 1)
                    rows.setdefault(r, []).append(name)
    return {r: v for r, v in rows.items() if r in rounds}, quick


def write_must_reach(per_round: dict, quick: bool) -> None:
    """The rounds of this walk are replaced, the others stay. A round from a --quick walk says so: pictures were not taken, so a click that depends on a window size may land elsewhere."""
    rows, notes = {}, {}
    if os.path.exists(MUST_REACH):
        with open(MUST_REACH, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if line.startswith("# quick: "):
                    notes[line[len("# quick: "):]] = True
                elif line and not line.startswith("#"):
                    r, name = line.split(":", 1)
                    rows.setdefault(r, []).append(name)
    for r, v in per_round.items():
        rows[r] = [n.split("_", 1)[-1] for n in v["scene_names"]]
        notes.pop(r, None)
        if quick:
            notes[r] = True
    with open(MUST_REACH, "w", encoding="utf-8", newline="\n") as f:
        f.write("# Scene names (without the running number) the fast walk has to reach, round:scene. gate.py --write-must-reach replaces the rounds it walked.\n")
        for r in ROUNDS:
            if r in notes:
                f.write(f"# quick: {r}\n")
        for r in ROUNDS:
            for name in rows.get(r, []):
                f.write(f"{r}:{name}\n")


def apply_expect(real, expect):
    import noise

    kept, excused = [], []
    for row in real:
        hit = noise.matches_expect(expect, row["scene"], row["class"])
        if hit:
            excused.append({**row, "reason": hit.get("reason", "")})
        else:
            kept.append(row)
    return kept, excused


def write_report(out_dir: str, summary: dict, per_round: dict) -> None:
    if summary["green"] and not summary["rounds"]:
        lines = [f"webqa {summary['base']} -> {summary['head']}: NOTHING TO WALK (exit 0): {summary['rounds_why']}"]
        lines += [f"NOT WALKED {x}" for x in summary.get("not_walked", [])]
        with open(os.path.join(out_dir, "report.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return
    lines = [f"webqa {summary['base']} -> {summary['head']}: {'GREEN' if summary['green'] else 'RED' if summary['exit'] == 1 else 'TOOL BROKE'} (exit {summary['exit']})",
             f"scenes {summary['scenes']} shots {summary['shots']} identical {summary['same_shots']} seconds {summary['seconds']}",
             f"noise {summary['noise']}", f"fingerprint {summary['fingerprint']}", f"replay (pictures at 640, 641, 900; animation declarations) {summary['replay']}", ""]
    for t in summary["tool"]:
        lines.append(f"TOOL {t}")
    lines += [f"NOT WALKED {x}" for x in summary.get("not_walked", [])]
    for row in summary.get("new_css", []):
        lines.append(f"NEW {row['round']} {row['sheet']} only A {json.dumps(row['only A'], ensure_ascii=False)[:300]} only B {json.dumps(row['only B'], ensure_ascii=False)[:300]}")
    for row in summary["real"]:
        lines.append(f"REAL {row['round']}:{row['scene']} {row['class']} {json.dumps(row['detail'], ensure_ascii=False)[:600]}")
    for row in summary["expected"]:
        lines.append(f"EXPECTED {row['round']}:{row['scene']} {row['class']} because {row['reason']}")
    lines.append("")
    for r, v in per_round.items():
        lines.append(f"round {r}: scenes {v['scenes']} shots {v['shots']} identical {v['same_shots']} noise {v['noise']} walk {v.get('seconds')}s compare {v.get('compare_seconds')}s")
        for k, x in v.get("info", {}).items():
            lines.append(f"  {k}: {x[:12]}")
    cov = summary.get("coverage")
    if cov:
        lines.append(f"page functions called {cov['called']} / {cov['functions']} (information only)")
    if summary["must_reach_quick_missing"]:
        lines.append("must-reach list from a --quick walk, missed here (a warning until --write-must-reach on a real walk): " + ", ".join(summary["must_reach_quick_missing"][:40]))
    if summary["not_reached"]:
        lines.append("")
        lines.append("not reached (both or either side; click results that differ are REAL above):")
        lines += [f"  {x[:200]}" for x in summary["not_reached"]]
    with open(os.path.join(out_dir, "report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def run(args) -> int:
    t0 = time.monotonic()
    summary = {"base": args.base, "head": args.head, "green": False, "exit": 2, "real": [], "expected": [], "noise": {}, "scenes": 0, "shots": 0, "same_shots": 0, "noise_rows": [], "not_reached": [], "missing_must_reach": [], "must_reach_quick_missing": [], "tool": [], "seconds": 0,
               "fingerprint": {}, "corpus": args.corpus, "profile": args.profile, "rounds": [], "replay": {"ran": False, "why": "did not get that far"},
               "round_files": {}, "rounds_why": "every round (no --changed-files)"}
    per_round = {}
    args.new_sheets = None
    work = os.path.join(args.out, "_work")
    try:
        shutil.rmtree(work, ignore_errors=True)
        os.makedirs(work)
        rounds = [r.strip() for r in args.rounds.split(",") if r.strip()] if args.rounds else list(ROUNDS)
        if args.changed_files is not None:  # batch 107: only the rounds coverage.json says reach the changed files; --rounds too: both
            wanted, why, not_walked = rounds_detail(args.changed_files.split(","), load_coverage())
            summary["rounds_why"] = why
            summary["not_walked"] = not_walked
            if not wanted:  # batch 110: nothing to walk is green, not the tool broken: no copies, no servers
                raise NothingToWalk(why)
            rounds = [r for r in rounds if r in wanted]
            if not rounds:
                raise ToolBroke(f"--rounds and --changed-files leave no round ({why})")
        args.chrome = find_chrome(args.chrome)
        args.node = find_node(args.node)
        need_pil()
        fixed_ports = pick_ports(args.ports, "ports") if args.ports else None  # checked early, before anything is unpacked
        fixed_cdps = pick_ports(args.cdp_ports, "cdp-ports") if args.cdp_ports else None
        if fixed_ports or fixed_cdps:
            args.jobs = 1  # one pair of ports, one round at a time
        for r in rounds:
            if not os.path.exists(os.path.join(HERE, "flows", f"{r}.mjs")):
                raise ToolBroke(f"no round {r}")
        summary["rounds"] = rounds
        import unpack

        copies = (unpack.unpack(args.repo, args.base, os.path.join(work, "copy_base")), unpack.unpack(args.repo, args.head, os.path.join(work, "copy_head")))
        for copy in copies:
            seed_local(copy, outbox=args.outbox)
        if args.mutate:
            mutate(copies[1], args.mutate)
        if args.new:  # batch 110: the new packages' own sheets are listed, not red (same_behavior compare --new: new things listed, the rest the same)
            pkgs = [p.strip() for p in args.new.split(",") if p.strip()]
            args.new_sheets = {f"{p}.css" for p in pkgs if any(os.path.isfile(os.path.join(c, "web", f"{p}.css")) for c in copies)}
            summary["new"] = pkgs
            summary["new_css"] = []
        sa, sb = static_digest(os.path.join(copies[0], "web")), static_digest(os.path.join(copies[1], "web"))
        for name in sorted(set(sa) | set(sb)):
            if sa.get(name) != sb.get(name):
                summary["real"].append({"round": "(static)", "scene": name, "class": "static-file", "detail": [sa.get(name), sb.get(name)]})
        expect = []
        if args.expect:
            with open(args.expect, encoding="utf-8") as f:
                expect = json.load(f)
        changed = stylesheet_changes(os.path.join(copies[0], "web"), os.path.join(copies[1], "web"))
        why_not = "--quick" if args.quick else "--no-replay" if args.no_replay else None if changed else "no stylesheet and no index.html differs"
        args.dom_to = args.keep_corpus or (os.path.join(work, "corpus") if not why_not else None)
        summary["replay"] = {"ran": False, "why": why_not or "the walk did not finish"}
        env = clean_env()
        args.red_left = 40
        coverage = {}
        must, soft = must_reach_rows(rounds) if args.profile == "season21" and not args.only and not args.no_must_reach else ({}, set())
        def one(r):
            with PORT_LOCK:
                ports, cdps = fixed_ports or pick_ports(None, "ports"), fixed_cdps or pick_ports(None, "cdp-ports")
            print(f"== round {r} on {ports}", flush=True)
            hosts = ("localhost", "127.0.0.1") if args.swap_hosts else ("127.0.0.1", "localhost")
            out = run_round(r, args, work, copies, ports, cdps, (f"{hosts[0]}:{ports[0]}", f"{hosts[1]}:{ports[1]}"), env)
            print(f"   {r}: scenes {out['scenes']} shots {out['shots']} real {len(out['real'])} noise {out['noise']} tool {len(out['tool'])} {out['seconds']}s", flush=True)
            return out

        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            results = list(pool.map(one, rounds))
        for r, out in zip(rounds, results):
            per_round[r] = out
            kept, excused = apply_expect(out["real"], expect)
            summary["real"] += [{"round": r, **x} for x in kept]
            summary["expected"] += [{"round": r, **x} for x in excused]
            for k, v in out["noise"].items():
                summary["noise"][k] = summary["noise"].get(k, 0) + v
            summary["scenes"] += out["scenes"]
            summary["shots"] += out["shots"]
            summary["same_shots"] += out["same_shots"]
            summary["not_reached"] += [f"{r}: {x}" for x in out["not_reached"]]
            summary["tool"] += [f"{r}: {x}" for x in out["tool"]]
            summary["fingerprint"][r] = out.get("fingerprint")
            if "new_css" in out:
                summary["new_css"] += [{"round": r, **x} for x in out["new_css"]]
            summary["noise_rows"] += [{"round": r, **x} for x in out["noise_rows"]]
            summary["round_files"][r] = sorted(f"web/{file}" for file, functions in out.get("coverage", {}).items() if any(functions.values()))  # both walks, merged
            for file, functions in out.get("coverage", {}).items():
                mine = coverage.setdefault(file, {})
                for fn, hit in functions.items():
                    mine[fn] = mine.get(fn, False) or hit
            reached = {n.split("_", 1)[-1] for n in out["scene_names"]}
            for name in must.get(r, []):
                if name not in reached:
                    summary["must_reach_quick_missing" if r in soft else "missing_must_reach"].append(f"{r}:{name}")
        if summary["missing_must_reach"]:
            summary["tool"].append("scenes that have to be reached were not: " + ", ".join(summary["missing_must_reach"][:20]))
        if not why_not and not summary["tool"]:  # a walk the tool already gave up on proves nothing about its snapshots
            run_replay(args, work, copies, rounds, changed, expect, summary)
        total = sum(len(v) for v in coverage.values())
        summary["coverage"] = {"functions": total, "called": sum(1 for v in coverage.values() for hit in v.values() if hit), "not_called": {k: sorted(fn for fn, hit in v.items() if not hit) for k, v in sorted(coverage.items()) if not all(v.values())}}
        summary["exit"] = 2 if summary["tool"] else 1 if summary["real"] else 0
        summary["green"] = summary["exit"] == 0
    except NothingToWalk as e:
        summary["rounds"] = []
        summary["replay"] = {"ran": False, "why": str(e)}
        summary["exit"], summary["green"] = 0, True
    except ToolBroke as e:
        summary["tool"].append(str(e))
        summary["exit"] = 2
    except Exception as e:  # anything else that dies here is the tool, not the pages
        import traceback

        summary["tool"].append(f"{type(e).__name__}: {e}\n{traceback.format_exc()[-1200:]}")
        summary["exit"] = 2
    finally:
        summary["seconds"] = round(time.monotonic() - t0)
        if args.write_must_reach and summary["exit"] != 2:
            write_must_reach(per_round, quick=args.quick)
        os.makedirs(args.out, exist_ok=True)
        with open(os.path.join(args.out, "summary.json"), "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=1)
        write_report(args.out, summary, per_round)
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)
    print(f"webqa exit {summary['exit']}: real {len(summary['real'])} noise {summary['noise']} tool {len(summary['tool'])} seconds {summary['seconds']}", flush=True)
    for t in summary["tool"]:
        print("TOOL", t[:500], flush=True)
    return summary["exit"]


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", help="required unless --dry-run")
    ap.add_argument("--head", help="required unless --dry-run")
    ap.add_argument("--out", help="required unless --dry-run")
    ap.add_argument("--dry-run", action="store_true", help="print the rounds --changed-files and --rounds pick, why, and the files not walked; walk nothing")
    ap.add_argument("--repo", default=REPO, help="the clone the two commits are in")
    ap.add_argument("--ports", help="a,b; default two free ones. 7861 is refused")
    ap.add_argument("--cdp-ports", help="a,b; default two free ones")
    ap.add_argument("--chrome", help="default TIANXIA_WEBQA_CHROME, then the newest ms-playwright chromium")
    ap.add_argument("--node", help="default node on PATH")
    ap.add_argument("--profile", default="season21")
    ap.add_argument("--jobs", type=int, default=2, help="rounds walked at the same time, each on its own free ports; --ports means one at a time")
    ap.add_argument("--rounds", help="comma separated; default all: " + ",".join(ROUNDS))
    ap.add_argument("--changed-files", help="comma separated repo paths (wave_gate --changed passes the web/ files): walk only the rounds coverage.json says reach them; "
                                            "the shell, scripts/webqa or an unmapped file walk every round; with --rounds, both")
    ap.add_argument("--new", help="comma separated new packages (behind a switch): the css-rules of their own web/<pkg>.css are listed as NEW, not red; other sheets as before")
    ap.add_argument("--outbox", action="store_true", help="each server appends the fake SMS and mail it sends to <round>/<base|head>.outbox.jsonl (identity and fake_services on only)")
    ap.add_argument("--corpus", choices=("fast", "full"), default="fast", help="fast: no crawls")
    ap.add_argument("--expect", help="json file: [{scene: regex, class: dom|style|pixel|main|..., reason: text}]. A row only counts when it matches a difference")
    ap.add_argument("--keep", action="store_true", help="keep the copies, databases and raw walks")
    ap.add_argument("--keep-corpus", help="keep the DOM snapshots here, for replay.py")
    ap.add_argument("--mutate", choices=(*MUTATIONS, PKG_CSS, QUIET, *HOSTILE), help="selftest only: break the head on purpose")
    ap.add_argument("--round-seconds", type=int, help=f"a round still walking after this is the tool broken, exit 2; default {ROUND_SECONDS}")
    ap.add_argument("--quick", action="store_true", help="clicks, the DOM and /api/main only, no pictures and no styles: a look that the flows still walk, not a verdict")
    ap.add_argument("--only", help="comma separated flow names inside the round (reproductions); turns off the must-reach check")
    ap.add_argument("--no-must-reach", action="store_true", help="for walking old commits")
    ap.add_argument("--no-replay", action="store_true", help="skip the replay even if a stylesheet differs (reproductions; the summary says so)")
    ap.add_argument("--swap-hosts", action="store_true", help="base on localhost, head on 127.0.0.1: does a difference follow the host or the code")
    ap.add_argument("--write-must-reach", action="store_true", help="write must_reach.txt from this walk")
    return ap


def dry_run(args) -> int:
    """Batch 110: the pick only, the same one run() makes."""
    rounds = [r.strip() for r in args.rounds.split(",") if r.strip()] if args.rounds else list(ROUNDS)
    why, not_walked = "every round (no --changed-files)", []
    if args.changed_files is not None:
        wanted, why, not_walked = rounds_detail(args.changed_files.split(","), load_coverage())
        rounds = [r for r in rounds if r in wanted]
    print(f"rounds: {','.join(rounds) or '(none)'}")
    print(f"why: {why}")
    for x in not_walked:
        print(f"not walked: {x}")
    return 0


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    ap = parser()
    args = ap.parse_args(argv)
    if args.dry_run:
        return dry_run(args)
    missing = [n for n in ("base", "head", "out") if not getattr(args, n)]
    if missing:
        ap.error("the following arguments are required: " + ", ".join(f"--{n}" for n in missing))
    args.out = os.path.abspath(args.out)
    os.makedirs(args.out, exist_ok=True)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
