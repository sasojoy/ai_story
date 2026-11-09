"""Compare two walks: scene lists, clicks, the DOM, computed styles, /api/main, stylesheet rules, console and network, screenshots.

usage: python compare.py <walk A> <walk B> --origins 127.0.0.1:8292,localhost:8293 [--red <dir>]

What counts as noise is noise.py; everything else comes back as a row in "real". The side-by-side images only for real pixel rows.
"""
import argparse
import collections
import difflib
import gzip
import hashlib
import json
import os
import sys

from PIL import Image, ImageChops, ImageDraw

import noise

MAX_RED_IMAGES = 40
STYLE_ONLY_VIEWS = ("640", "641", "900")
VIEW_ORDER = ("375-light", "375-dark", "1280", *STYLE_ONLY_VIEWS)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16]


def read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def load_report(walk: str) -> dict:
    with open(os.path.join(walk, "report.json"), encoding="utf-8") as f:
        return json.load(f)


def view_of(file: str) -> str:
    return file.split("__")[1].removesuffix(".png")


def walk_json(x, y, path=""):
    if isinstance(x, dict) and isinstance(y, dict):
        for k in sorted(set(x) | set(y)):
            if k not in x or k not in y:
                yield f"{path}.{k} only in {'A' if k in x else 'B'}"
            else:
                yield from walk_json(x[k], y[k], f"{path}.{k}")
    elif isinstance(x, list) and isinstance(y, list) and len(x) == len(y):
        for i, (p, q) in enumerate(zip(x, y)):
            yield from walk_json(p, q, f"{path}[{i}]")
    elif x != y:
        yield f"{path}: {str(x)[:110]!r} vs {str(y)[:110]!r}"


def load_style(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def style_rows(doc: dict):
    """(key, pseudo or "", hash) for every element and pseudo-element; the chronicle link is left out, it may be written on one side already."""
    for row in doc["els"]:
        if "huaben-link" in row[0]:
            continue
        yield row[0], "", row[1]
        for i in range(2, len(row), 2):
            yield row[0], row[i], row[i + 1]


def style_diff(a: dict, b: dict) -> tuple[set, list, bool]:
    """Which properties differ, a few examples, and whether the element lists themselves differ."""
    ra, rb = list(style_rows(a)), list(style_rows(b))
    if [r[:2] for r in ra] != [r[:2] for r in rb]:
        return {"(elements)"}, [x for x in difflib.unified_diff([" ".join(r[:2]) for r in ra], [" ".join(r[:2]) for r in rb], lineterm="", n=0)][:4], True
    props, examples, seen = set(), [], set()
    names = a["props"]
    for (key, pseudo, ha), (_, _, hb) in zip(ra, rb):
        if ha == hb or (ha, hb) in seen:
            continue
        seen.add((ha, hb))
        va, vb = a["dict"][ha].split("\x01"), b["dict"][hb].split("\x01")
        for name, p, q in zip(names, va, vb):
            if p != q:
                props.add(name)
                if len(examples) < 4:
                    examples.append(f"{key}{pseudo} {name}: {p[:60]} vs {q[:60]}")
    return props, examples, False


_masked = {}


def masked_style_hash(doc: dict) -> str:
    """The styles with used-value properties and the chronicle link taken out: what has to be the same run after run."""
    keep = None
    h = hashlib.sha256()
    for key, pseudo, k in style_rows(doc):
        m = _masked.get(k)
        if m is None:
            if keep is None:
                keep = [i for i, p in enumerate(doc["props"]) if not noise.used_only([p], flip=True)]  # grid tracks move with the scrollbar, and the scrollbar is not in the fingerprint
            vals = doc["dict"][k].split("\x01")
            m = hashlib.md5("\x01".join(vals[i] for i in keep if i < len(vals)).encode("utf-8", "replace")).hexdigest()[:12]
            _masked[k] = m
        h.update(f"{key}{pseudo}={m}\n".encode("utf-8", "replace"))
    return h.hexdigest()[:16]


def fingerprint(walk: str, report: dict, hosts) -> dict:
    """Same program, same walk, same fingerprint. Noise is not in it: how many pixels flicker changes from run to run."""
    dom, sty, main = hashlib.sha256(), hashlib.sha256(), hashlib.sha256()
    names = [n.split("_", 1)[-1] for n in report["scenes"]]
    for sid, facts in report["scenes"].items():
        p = os.path.join(walk, "dom", sid + ".html")
        if os.path.exists(p):
            dom.update(f"{sid} {sha(noise.mask_dom(read(p), hosts))}\n".encode())
        for view in sorted(facts.get("sty", {})):
            doc = load_style(os.path.join(walk, "style", f"{sid}__{view}.json.gz"))
            if doc:
                sty.update(f"{sid} {view} {masked_style_hash(doc)}\n".encode())
        p = os.path.join(walk, "main", sid + ".json")
        if os.path.exists(p):
            main.update(f"{sid} {sha(noise.mask_main(read(p), hosts))}\n".encode())
    return {"scenes": sha("\n".join(names)), "dom": dom.hexdigest()[:16], "style": sty.hexdigest()[:16], "main": main.hexdigest()[:16]}


def pixel_diff(pa: str, pb: str, vol_a, vol_b) -> dict | None:
    with Image.open(pa) as x, Image.open(pb) as y:
        ia, ib = x.convert("RGB"), y.convert("RGB")
    if ia.size != ib.size:
        return {"size": [ia.size, ib.size]}
    d = ImageChops.difference(ia, ib)
    box = d.getbbox()
    if box is None:
        return None
    r, g, b = d.split()
    n = d.width * d.height - ImageChops.add(ImageChops.add(r, g), b).histogram()[0]
    levels = max(e[1] for e in d.getextrema())
    out = {"pixels": n, "levels": levels, "box": list(box)}
    for kind in ("share", "tale"):
        rects = [v[1:] for v in (vol_a or []) + (vol_b or []) if v[0] == kind]
        if rects:
            e = d.copy()
            pen = ImageDraw.Draw(e)
            for a0, b0, a1, b1 in rects:
                pen.rectangle([a0 - 2, b0 - 2, a1 + 2, b1 + 2], fill=(0, 0, 0))
            out["only_" + kind] = e.getbbox() is None
    return out


def side_by_side(pa: str, pb: str, out: str) -> None:
    with Image.open(pa) as x, Image.open(pb) as y:
        ia, ib = x.convert("RGB"), y.convert("RGB")
    w, h = max(ia.width, ib.width), max(ia.height, ib.height)
    s = Image.new("RGB", (w * 2 + 16, h), (235, 30, 200))
    s.paste(ia, (0, 0))
    s.paste(ib, (w + 16, 0))
    if w > 900:
        s = s.resize((s.width // 2, s.height // 2))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    s.save(out, optimize=True)


class Result:
    def __init__(self):
        self.real = []
        self.noise = collections.Counter()
        self.noise_rows = []
        self.info = collections.defaultdict(list)
        self.tool = []
        self.scenes = 0
        self.shots = 0
        self.same_shots = 0
        self.red_images = 0

    def red(self, scene: str, cls: str, detail) -> None:
        self.real.append({"scene": scene, "class": cls, "detail": detail})


def css_rule(row) -> tuple[str, str]:
    """(sheet, cssText). Batch 110 rows are [sheet, text]; a plain string is an older walk's rule with no sheet."""
    return ("", row) if isinstance(row, str) else (row[0], row[1])


def split_new_css(xa, xb, new_sheets, hosts):
    """Batch 110 --new: the new packages' own sheets come out of both sides before css-rules compares; what differed in them is listed, not red."""
    keep_a, keep_b, listed = [], [], []
    mine = {s: ([], []) for s in sorted(new_sheets)}
    for rows, keep, side in ((xa, keep_a, 0), (xb, keep_b, 1)):
        for row in rows:
            sheet, text = css_rule(row)
            (mine[sheet][side] if sheet in mine else keep).append(text)
    for sheet, (ta, tb) in mine.items():
        ma, mb = collections.Counter(noise.mask_common(t, hosts) for t in ta), collections.Counter(noise.mask_common(t, hosts) for t in tb)
        if ma != mb:
            listed.append({"sheet": sheet, "only A": [t[:160] for t in list(ma - mb)[:5]], "only B": [t[:160] for t in list(mb - ma)[:5]], "counts": [len(ta), len(tb)]})
    return keep_a, keep_b, listed


def compare(a: str, b: str, origins, red_dir: str | None = None, red_budget: int = MAX_RED_IMAGES, want_fingerprint: bool = True, new_sheets=None) -> dict:
    hosts = noise.hosts_pattern(origins)
    ra, rb = load_report(a), load_report(b)
    res = Result()
    for r in (ra, rb):
        if r.get("fatal"):
            res.tool.append(f"{r['label']} fatal: {r['fatal'][:400]}")
        for s in r["steps"]:
            if s.startswith("FLOW"):
                res.tool.append(f"{r['label']} {s[:600]}")
        for s in r.get("pyErrors", []):
            res.tool.append(f"{r['label']} staging failed: {s[:500]}")
    sa, sb = list(ra["scenes"]), list(rb["scenes"])
    res.scenes = len(set(sa) | set(sb))
    if sa != sb:
        res.red("(walk)", "scene-list", list(difflib.unified_diff(sa, sb, lineterm="", n=0))[:40])

    def norm_steps(lines):
        return [noise.mask_common(x, hosts) for x in lines]

    def no_polls(lines):  # how many times a flow asked whether the chronicle is written depends on when the writer got to it
        return [x for x in lines if " /api/tale/" not in x]

    for name, x, y in (("steps", ra["steps"], rb["steps"]), ("api-calls", no_polls(ra["apiCalls"]), no_polls(rb["apiCalls"]))):
        if norm_steps(x) != norm_steps(y):
            res.red("(walk)", name, list(difflib.unified_diff(norm_steps(x), norm_steps(y), lineterm="", n=0))[:30])
    for k in sorted(set(ra["facts"]) | set(rb["facts"])):
        x, y = ra["facts"].get(k), rb["facts"].get(k)
        if json.dumps(x, ensure_ascii=False) != json.dumps(y, ensure_ascii=False):
            res.red(k, "facts", list(walk_json(x, y))[:6] if isinstance(x, dict) and isinstance(y, dict) else f"{x!r} vs {y!r}"[:300])

    for sid in sorted(set(sa) & set(sb)):
        x, y = ra["scenes"][sid], rb["scenes"][sid]
        unstable = bool(x.get("unstable") or y.get("unstable"))
        if unstable:
            res.info["unstable"].append(sid)
        for side, f in (("A", x), ("B", y)):
            if f.get("gutterOdd"):
                res.info["gutterOdd"].append(f"{side} {sid}")
        # the toast's words: screenshots hide it and the DOM masks it. It goes by itself after 3.2 s, so it only counts when both sides still show it
        ta, tb = x.get("toast"), y.get("toast")
        if ta and tb:
            if noise.mask_main(ta, hosts) != noise.mask_main(tb, hosts):
                res.red(sid, "toast", {"A": ta[:200], "B": tb[:200]})
        elif ta or tb:
            res.info["toast on one side"].append(sid)
        # the DOM
        fa, fb = os.path.join(a, "dom", sid + ".html"), os.path.join(b, "dom", sid + ".html")
        dom_same = True
        if os.path.exists(fa) and os.path.exists(fb):
            ta, tb = read(fa), read(fb)
            na, nb = noise.mask_dom(ta, hosts), noise.mask_dom(tb, hosts)
            if na != nb:
                dom_same = False
                i = next((n for n, (p, q) in enumerate(zip(na, nb)) if p != q), min(len(na), len(nb)))
                res.red(sid, "dom", {"len": [len(na), len(nb)], "A": na[max(0, i - 60):i + 90], "B": nb[max(0, i - 60):i + 90]})
            else:
                for cls in noise.dom_noise(ta, tb, hosts):
                    res.noise[cls] += 1
            pa, pb = fa[:-5] + ".attrs.json", fb[:-5] + ".attrs.json"
            if os.path.exists(pa) and os.path.exists(pb) and noise.mask_common(read(pa), hosts) != noise.mask_common(read(pb), hosts):
                dom_same = False
                res.red(sid, "dom", {"html attributes": [read(pa)[:200], read(pb)[:200]]})
        # /api/main
        if x.get("mainHash") != y.get("mainHash"):
            pa, pb = os.path.join(a, "main", sid + ".json"), os.path.join(b, "main", sid + ".json")
            ma, mb = noise.mask_main(read(pa), hosts) if os.path.exists(pa) else "", noise.mask_main(read(pb), hosts) if os.path.exists(pb) else ""
            if ma != mb:
                try:
                    detail = list(walk_json(json.loads(ma), json.loads(mb)))[:6]
                except ValueError:
                    detail = [ma[:200], mb[:200]]
                res.red(sid, "main", detail)
        # styles, view by view
        props_of, examples_of, broken = {}, {}, set()
        for view in sorted(set(x.get("sty", {})) | set(y.get("sty", {}))):
            if x.get("sty", {}).get(view) == y.get("sty", {}).get(view):
                continue
            da = load_style(os.path.join(a, "style", f"{sid}__{view}.json.gz"))
            db = load_style(os.path.join(b, "style", f"{sid}__{view}.json.gz"))
            if not da or not db:
                res.red(sid, "style", f"{view}: dump on one side only")
                continue
            props, examples, structure = style_diff(da, db)
            if structure:
                broken.add(view)
            if props:
                props_of[view], examples_of[view] = props, examples
        # screenshots
        files = sorted(set(x.get("shots", [])) | set(y.get("shots", [])))
        only = sorted(set(x.get("shots", [])) ^ set(y.get("shots", [])))
        if only:
            res.red(sid, "shot-list", only[:8])
        results = {}
        for f in files:
            if f in only:
                continue
            res.shots += 1
            if ra["hashes"].get(f) == rb["hashes"].get(f):
                res.same_shots += 1
                continue
            pa, pb = os.path.join(a, "shots", f), os.path.join(b, "shots", f)
            if not (os.path.exists(pa) and os.path.exists(pb)):
                res.tool.append(f"screenshot file gone: {f}")
                continue
            d = pixel_diff(pa, pb, x.get("vol", {}).get(f), y.get("vol", {}).get(f))
            if d is None:
                res.same_shots += 1
            else:
                results[f] = d
        for view in VIEW_ORDER:
            mine = {f: d for f, d in results.items() if view_of(f) == view}
            la, lb = x.get("layout", {}).get(view) or {}, y.get("layout", {}).get(view) or {}
            flip = noise.scrollbar_flip(view, la.get("sw"), lb.get("sw"))
            props = props_of.get(view, set())
            used_only = bool(props) and view not in broken and noise.used_only(props, flip)
            if props:
                if flip and used_only and dom_same and not unstable:
                    res.noise["gutter"] += 1
                else:
                    has_shots = any(view_of(f) == view for f in files)  # the walk has no pixels at the three breakpoint widths, the replay does: gate.py runs it when a stylesheet differs
                    # an image that only differs by anti-aliasing is still the same picture (wave D: 124_ex_1_choose, 13 px and 1 level beside a .shell margin)
                    pixels_same = all("size" not in d and noise.within_aa(d["pixels"], d["levels"]) for d in mine.values()) if has_shots else la == lb
                    cls = None if view in broken else noise.style_class(props, pixels_same, unstable, has_pixels=has_shots)
                    if cls:
                        res.noise[cls] += 1
                    else:
                        res.red(sid, "style", {"view": view, "props": sorted(props), "examples": examples_of.get(view, [])})
            elif flip and view in STYLE_ONLY_VIEWS and not unstable:
                res.noise["gutter"] += 1
            for f, d in sorted(mine.items()):
                clean = dom_same and (not props or used_only)
                cls = None
                if "size" not in d:
                    cls = noise.pixel_class(d["pixels"], d["levels"], view=view, sw_a=la.get("sw"), sw_b=lb.get("sw"), only_share=d.get("only_share", False),
                                            only_tale=d.get("only_tale", False), clean=clean, unstable=unstable)
                if cls:
                    res.noise[cls] += 1
                    res.noise_rows.append({"file": f, "class": cls, "pixels": d["pixels"], "levels": d["levels"], "box": d["box"]})
                    continue
                res.red(sid, "pixel", {"file": f, **d, "clean": clean, "unstable": unstable})
                if red_dir and res.red_images < red_budget:
                    side_by_side(os.path.join(a, "shots", f), os.path.join(b, "shots", f), os.path.join(red_dir, f))
                    res.red_images += 1

    # only the head has it
    for key in ("console", "exceptions", "http", "failed"):
        for line in noise.head_only(ra[key], rb[key], hosts):
            res.red(line.split(": ", 1)[0], key + "-head-only", line[:300])
    # what the browser parsed
    new_css = []
    ca, cb = os.path.join(a, "cssrules.json"), os.path.join(b, "cssrules.json")
    if os.path.exists(ca) and os.path.exists(cb):
        xa, xb = json.loads(read(ca)), json.loads(read(cb))
        if new_sheets is not None:
            xa, xb, new_css = split_new_css(xa, xb, new_sheets, hosts)
        else:
            xa, xb = [css_rule(t)[1] for t in xa], [css_rule(t)[1] for t in xb]
        ma, mb = collections.Counter(noise.mask_common(t, hosts) for t in xa), collections.Counter(noise.mask_common(t, hosts) for t in xb)
        if ma != mb:
            res.red("(css)", "css-rules", {"only A": [t[:160] for t in list(ma - mb)[:5]], "only B": [t[:160] for t in list(mb - ma)[:5]], "counts": [len(xa), len(xb)]})
        elif xa != xb:
            res.info["css order changed"].append(f"{len(xa)} rules, same text, another order")
    elif os.path.exists(ca) != os.path.exists(cb):
        res.tool.append("cssrules.json on one side only")
    # who is who never shows
    for sid, facts in rb["scenes"].items():
        word = noise.bot_words(facts.get("text", ""))
        p = os.path.join(b, "dom", sid + ".html")
        word = word or (noise.bot_words(read(p), dom=True) if os.path.exists(p) else None)
        if word:
            res.red(sid, "words", word)
    missed = sorted({s for r in (ra, rb) for s in r["steps"] if s.endswith(("-> missing", "-> hidden", "-> disabled"))})
    out = {"scenes": res.scenes, "scene_names": sa, "shots": res.shots, "same_shots": res.same_shots, "real": res.real, "noise": dict(res.noise), "noise_rows": res.noise_rows, "info": {k: v[:40] for k, v in res.info.items()},
           "tool": res.tool, "not_reached": missed, "red_images": res.red_images}
    if new_sheets is not None:
        out["new_css"] = new_css
    coverage = {}
    for walk in (a, b):
        p = os.path.join(walk, "coverage.json")
        if os.path.exists(p):
            for file, functions in json.loads(read(p)).items():
                mine = coverage.setdefault(file, {})
                for fn, hit in functions.items():
                    mine[fn] = mine.get(fn, False) or hit
    out["coverage"] = coverage
    if want_fingerprint:
        out["fingerprint"] = {"A": fingerprint(a, ra, hosts), "B": fingerprint(b, rb, hosts)}
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--origins", required=True)
    ap.add_argument("--red")
    args = ap.parse_args()
    out = compare(args.a, args.b, args.origins.split(","), args.red)
    print(json.dumps({k: v for k, v in out.items() if k != "scene_names"}, ensure_ascii=False, indent=1))
    sys.exit(1 if out["real"] else 0)
