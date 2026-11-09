"""Replay the DOM snapshots of a walk against two candidates' stylesheets: for the batches that only move CSS.

usage: python replay.py --corpus <dom dir> --a-web <web dir> --b-web <web dir> --out <dir> [--no-freeze] [--styles-only]

No game server and no page scripts: each snapshot's body under the candidate's <head>, /static/* from the candidate's web/, six windows.
Snapshots with the same normalized DOM play once. --no-freeze --styles-only is the animation pass: nothing frozen, motion allowed,
only animation-* and transition-* are compared (what frozen walks cannot see is the declaration, not the frames); @keyframes come with the rules.
The corpus is a product of a walk and never goes into git (gate.py --keep-corpus).

Exit 0 same, 1 differs, 2 the tool broke.
"""
import argparse
import hashlib
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    import compare  # noqa: E402
except ImportError as e:  # no PIL: the tool is what broke, not the pages
    print("TOOL", e)
    sys.exit(2)
import gate  # noqa: E402
import noise  # noqa: E402

ORIGIN = re.compile(r"https?://(?:127\.0\.0\.1|localhost):\d+")
SCRIPT = re.compile(r"<script\b.*?</script>", re.S | re.I)
HEAD = re.compile(r"<head\b[^>]*>(.*?)</head>", re.S | re.I)
ANIMATION_PROPS = ("animation-", "transition-")
REPLAY_SECONDS = 3600  # about 1.3 seconds a snapshot
TYPES = {".css": "text/css", ".js": "text/javascript", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".svg": "image/svg+xml", ".gif": "image/gif", ".ico": "image/x-icon", ".woff2": "font/woff2", ".woff": "font/woff"}


def page_attrs(attrs: dict) -> str:
    return " ".join(f'{k}="{v}"' for k, v in sorted(attrs.items()))


def load_corpus(folder: str) -> dict:
    """id -> (html attributes, body) for each different snapshot. Later duplicates of a normalized DOM drop out."""
    pages, seen = {}, set()
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".html"):
            continue
        sid = name[:-5]
        with open(os.path.join(folder, name), encoding="utf-8") as f:
            body = f.read()
        if not body.lstrip().lower().startswith("<body"):
            continue  # shootRaw pages (public share pages) are whole documents with their own styles
        attrs = {}
        p = os.path.join(folder, sid + ".attrs.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                attrs = json.load(f)
        body = ORIGIN.sub("", body)
        key = hashlib.sha256((noise.mask_dom(body) + page_attrs(attrs)).encode("utf-8", "replace")).hexdigest()
        if key not in seen:
            seen.add(key)
            pages[sid] = (attrs, body)
    return pages


def candidate_head(web: str) -> str:
    with open(os.path.join(web, "index.html"), encoding="utf-8") as f:
        m = HEAD.search(f.read())
    if not m:
        raise gate.ToolBroke(f"no <head> in {web}/index.html")
    return SCRIPT.sub("", m.group(1))


def serve(web: str, pages: dict) -> tuple:
    head = candidate_head(web)
    root = os.path.abspath(web)

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, ctype, data):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path.startswith("/__page/"):
                sid = path[len("/__page/"):]
                from urllib.parse import unquote

                row = pages.get(unquote(sid))
                if row is None:
                    return self._send(404, "text/plain", b"")
                attrs, body = row
                html = f"<!doctype html><html {page_attrs(attrs)}><head>{head}</head>{body}</html>"
                return self._send(200, "text/html; charset=utf-8", html.encode("utf-8"))
            if path.startswith("/static/"):
                from urllib.parse import unquote

                p = os.path.abspath(os.path.join(root, unquote(path[len("/static/"):])))
                if p.startswith(root) and os.path.isfile(p):
                    with open(p, "rb") as f:
                        return self._send(200, TYPES.get(os.path.splitext(p)[1].lower(), "application/octet-stream"), f.read())
            return self._send(404, "text/plain", b"")

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def filter_props(out: dict) -> dict:
    """The animation pass: only animation-* and transition-* count."""
    keep = []
    for row in out["real"]:
        if row["class"] == "style":
            props = [p for p in row["detail"].get("props", []) if p.startswith(ANIMATION_PROPS)]
            if not props:
                continue
            row["detail"]["props"] = props
        keep.append(row)
    out["real"] = keep
    return out


def replay(corpus: str, a_web: str, b_web: str, out_dir: str, *, frozen=True, shoot=True, chrome=None, node=None, cdp_ports=None, red_budget=40, new_sheets=None) -> dict:
    chrome, node = gate.find_chrome(chrome), gate.find_node(node)
    cdps = gate.pick_ports(cdp_ports, "cdp-ports")
    pages = load_corpus(corpus)
    if not pages:
        raise gate.ToolBroke(f"no snapshots in {corpus}")
    work = os.path.join(out_dir, "_replay")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    list_file = os.path.join(work, "pages.json")
    with open(list_file, "w", encoding="utf-8") as f:
        json.dump(sorted(pages), f, ensure_ascii=False)
    t0 = time.monotonic()
    env = dict(gate.clean_env(), TIANXIA_WEBQA_CHROME=chrome)
    flags = ([] if frozen else ["--no-freeze"]) + ([] if shoot else ["--styles-only"])
    servers, procs, walks = [], [], []
    try:
        for label, web, cdp in (("a", a_web, cdps[0]), ("b", b_web, cdps[1])):
            srv, origin = serve(web, pages)
            servers.append(srv)
            walk = os.path.join(work, label)
            os.makedirs(walk)
            walks.append(walk)
            procs.append(subprocess.Popen([node, "--no-warnings", os.path.join(HERE, "replay.mjs"), label, origin, walk, str(cdp), list_file, *flags],
                                          stdout=open(os.path.join(work, f"{label}.out"), "wb"), stderr=open(os.path.join(work, f"{label}.err"), "wb"), env=env, cwd=work, creationflags=gate.DETACHED))
        gate.wait_all(procs, REPLAY_SECONDS, "replay")
    finally:
        for p in procs:
            if p.poll() is None:
                gate.kill_tree(p.pid)
        for s in servers:
            s.shutdown()
    seconds = round(time.monotonic() - t0)
    for walk, p in zip(walks, procs):
        if not os.path.exists(os.path.join(walk, "report.json")):
            raise gate.ToolBroke(f"replay left no report (exit {p.returncode})")
    # the two ports differ and the snapshots carry no host; the stylesheet rules can, so both hosts go through the same mask
    origins = [f"127.0.0.1:{s.server_address[1]}" for s in servers]
    res = compare.compare(walks[0], walks[1], origins, os.path.join(out_dir, "red"), red_budget=red_budget, want_fingerprint=False, new_sheets=new_sheets)
    if not frozen:
        res = filter_props(res)
    with_map = sum(1 for _, body in pages.values() if 'id="map-host"' in body)
    res.update({"snapshots": len(pages), "with_map_host": with_map, "seconds": seconds})
    shutil.rmtree(work, ignore_errors=True)
    return res


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--a-web", required=True)
    ap.add_argument("--b-web", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-freeze", action="store_true")
    ap.add_argument("--styles-only", action="store_true")
    ap.add_argument("--chrome")
    ap.add_argument("--node")
    ap.add_argument("--cdp-ports")
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    try:
        res = replay(a.corpus, a.a_web, a.b_web, a.out, frozen=not a.no_freeze, shoot=not a.styles_only, chrome=a.chrome, node=a.node, cdp_ports=a.cdp_ports)
    except gate.ToolBroke as e:
        print("TOOL", e)
        return 2
    code = 2 if res["tool"] else 1 if res["real"] else 0
    res["exit"] = code
    with open(os.path.join(a.out, "replay.json"), "w", encoding="utf-8") as f:
        json.dump({k: v for k, v in res.items() if k != "scene_names"}, f, ensure_ascii=False, indent=1)
    print(f"replay exit {code}: snapshots {res['snapshots']} (with #map-host {res['with_map_host']}) real {len(res['real'])} noise {res['noise']} seconds {res['seconds']}")
    for row in res["real"][:20]:
        print("REAL", row["scene"], row["class"], json.dumps(row["detail"], ensure_ascii=False)[:300])
    return code


if __name__ == "__main__":
    sys.exit(main())
