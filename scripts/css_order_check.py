"""切樣式檔的先後檢查（全部拆包第 67 批；計畫 docs/superpowers/plans/2026-11-06-網頁殼化-第67批.md 第三節。第 86 批起比所有樣式，
計畫 docs/superpowers/plans/2026-11-07-第二輪-第86批.md 第四節）。只讀檔。

    python scripts/css_order_check.py <base 根> <head 根>

同權重後蓋前，所以把一段 CSS 搬到別支檔、排到別的規則後面，可能改掉畫面。這支把 base 與 head 各自照 index.html 載入的所有樣式
（/static/ 底下的；一支一支 parse 再接起來，不接文字：多的 } 不跨檔，同瀏覽器）逐條對起來，
找「先後反了」而且「可能打到同一個元素、權重一樣、同一類屬性、值不一樣」的規則對。
0 對才算過；回傳碼 1 表示有。保守：判不出來就算可能（多報只會多留幾段在 style.css）。

「可能打到同一個元素」怎麼算：主體的 class 要在 js、py 的同一個 class 屬性裡一起出現過（classList 加上去的算都可能）；
祖先要包得住對方，照 js 函式的字面巢狀與呼叫圖算（設 innerHTML、等 API 的函式不展開）；放進標籤裡的區域變數
（`<div class="mc-tags">${tags.join("")}</div>`）算它的內容，放進標籤裡的參數算呼叫端傳進去的東西。
抓不到的：class 字串由資料表組出來、或先存進變數再放進 class 屬性，又不是緊貼 ${} 的前綴。這種靠波末實機驗。
"""
from __future__ import annotations

import io
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

# ── 解析 ────────────────────────────────────────────────────────────────
@dataclass
class Rule:
    sels: list[str]
    decls: list[tuple[str, bool]]   # (property, important)
    media: str
    line: int                      # 規則起始行（1 起）
    top: int = -1                  # 屬於第幾個頂層項目

@dataclass
class Top:
    start: int      # 含前導註解的第一行（1 起）
    end: int        # 結束那一行
    prelude: str
    rules: list[Rule] = field(default_factory=list)
    kf: str = ""    # @keyframes 名
    atomic: str = "" # @import 等
    raw: str = ""   # 去掉前導註解的原文（認規則搬到哪裡用）


def _skip_comment(t, i):
    j = t.find("*/", i + 2)
    return j + 2 if j >= 0 else len(t)


def _match_brace(t, i):
    """t[i] 是 {，回對應 } 的位置。"""
    d = 0
    n = len(t)
    while i < n:
        c = t[i]
        if t.startswith("/*", i):
            i = _skip_comment(t, i); continue
        if c in "\"'":
            q = c; i += 1
            while i < n and t[i] != q:
                i += 2 if t[i] == "\\" else 1
        elif c == "{":
            d += 1
        elif c == "}":
            d -= 1
            if d == 0:
                return i
        i += 1
    raise ValueError("unbalanced")


def _strip_comments(s):
    return re.sub(r"/\*.*?\*/", " ", s, flags=re.S)


def split_top(s, sep):
    out, d, cur, q = [], 0, [], None
    for c in s:
        if q:
            cur.append(c)
            if c == q: q = None
            continue
        if c in "\"'":
            q = c; cur.append(c); continue
        if c in "([": d += 1
        elif c in ")]": d -= 1
        if c == sep and d == 0:
            out.append("".join(cur)); cur = []
        else:
            cur.append(c)
    out.append("".join(cur))
    return out


def parse_decls(body):
    out = []
    for d in split_top(_strip_comments(body), ";"):
        if ":" not in d: continue
        p, v = d.split(":", 1)
        p = p.strip().lower()
        if not p or " " in p: continue
        out.append((p, "!important" in v.lower(), re.sub(r"\s+", " ", v).strip().lower()))
    return out


def lineof(starts, off):
    import bisect
    return bisect.bisect_right(starts, off)


def parse(text):
    starts = [0] + [m.end() for m in re.finditer("\n", text)]
    tops: list[Top] = []
    i, n = 0, len(text)
    lead = None

    def walk(a, b, media, sink, top_index):
        i = a
        while i < b:
            if text[i].isspace(): i += 1; continue
            if text.startswith("/*", i): i = _skip_comment(text, i); continue
            j = i
            while j < b and text[j] not in "{;}":
                if text.startswith("/*", j): j = _skip_comment(text, j); continue
                j += 1
            if j >= b or text[j] != "{":
                i = j + 1; continue
            pre = _strip_comments(text[i:j]).strip()
            e = _match_brace(text, j)
            if pre.startswith("@"):
                low = pre.lower()
                if low.startswith(("@media", "@supports", "@container", "@layer")):
                    walk(j + 1, e, (media + " & " if media else "") + re.sub(r"\s+", " ", pre), sink, top_index)
                # keyframes/font-face inside media: atomic ignore
            else:
                sink.append(Rule([re.sub(r"\s+", " ", s).strip() for s in split_top(pre, ",")], parse_decls(text[j + 1:e]), media, lineof(starts, i), top_index))
            i = e + 1

    while i < n:
        c = text[i]
        if c.isspace():
            i += 1; continue
        if text.startswith("/*", i):
            same_line = tops and lineof(starts, i) == tops[-1].end
            if lead is None and not same_line: lead = i
            i = _skip_comment(text, i); continue
        j = i
        while j < n and text[j] not in "{;":
            if text.startswith("/*", j): j = _skip_comment(text, j); continue
            j += 1
        pre = _strip_comments(text[i:j]).strip()
        st = lead if lead is not None else i
        lead = None
        if j < n and text[j] == ";":
            e = j
            top = Top(lineof(starts, st), lineof(starts, e), pre, atomic=pre, raw=text[i:e + 1])
        else:
            e = _match_brace(text, j)
            top = Top(lineof(starts, st), lineof(starts, e), pre, raw=text[i:e + 1])
            low = pre.lower()
            if low.startswith(("@keyframes", "@-webkit-keyframes")):
                top.kf = pre.split()[-1]
            elif low.startswith("@font-face"):
                top.atomic = pre
            elif low.startswith(("@media", "@supports", "@container", "@layer")):
                walk(j + 1, e, re.sub(r"\s+", " ", pre), top.rules, len(tops))
            else:
                top.rules.append(Rule([re.sub(r"\s+", " ", s).strip() for s in split_top(pre, ",")], parse_decls(text[j + 1:e]), "", lineof(starts, i), len(tops)))
        i = e + 1
        # 同一行後面的註解算這一項
        tops.append(top)
    return tops


# ── 選擇器 ──────────────────────────────────────────────────────────────
_PSEUDO_EL = {"before", "after", "first-line", "first-letter", "marker", "selection", "placeholder", "backdrop", "-webkit-scrollbar", "-webkit-scrollbar-thumb", "-webkit-scrollbar-track", "-webkit-details-marker", "-webkit-slider-thumb", "-moz-range-thumb", "file-selector-button"}


def strip_args(sel):
    """回 (去掉括號內容的選擇器, 括號內容清單)。"""
    out, args, d, cur = [], [], 0, []
    for c in sel:
        if c == "(":
            if d == 0: cur = []
            else: cur.append(c)
            d += 1
        elif c == ")":
            d -= 1
            if d == 0: args.append("".join(cur)); out.append("()")
            else: cur.append(c)
        elif d: cur.append(c)
        else: out.append(c)
    return "".join(out), args


def specificity(sel):
    plain, args = strip_args(sel)
    a = len(re.findall(r"#[\w-]+", plain))
    b = len(re.findall(r"\.[\w-]+", plain)) + len(re.findall(r"\[[^\]]*\]", plain))
    c = 0
    for m in re.finditer(r"(::?)([\w-]+)(\(\))?", plain):
        name = m.group(2).lower()
        if m.group(1) == "::" or name in ("before", "after", "first-line", "first-letter"):
            c += 1
        elif name in ("not", "is", "has"):
            pass
        elif name == "where":
            pass
        else:
            b += 1
    # :not/:is/:has 算參數裡最大的
    names = re.findall(r":([\w-]+)\(\)", plain)
    for name, arg in zip(names, args):
        if name.lower() in ("not", "is", "has"):
            best = max((specificity(s.strip()) for s in split_top(arg, ",")), default=(0, 0, 0))
            a += best[0]; b += best[1]; c += best[2]
    # 標籤
    tmp = re.sub(r"\[[^\]]*\]", " ", plain)
    tmp = re.sub(r"::?[\w-]+(\(\))?", " ", tmp)
    tmp = re.sub(r"[#.][\w-]+", " ", tmp)
    c += len(re.findall(r"(?<![\w-])[a-zA-Z][\w-]*", tmp))
    return (a, b, c)


def subject(sel):
    plain, args = strip_args(sel)
    plain = re.sub(r"\[[^\]]*\]", lambda m: m[0].replace(" ", "\u0001").replace(">", "\u0002").replace("+", "\u0003").replace("~", "\u0004"), plain)
    last = re.split(r"[\s>+~]+", plain.strip())[-1]
    classes = set(re.findall(r"\.([\w-]+)", last))
    ids = set(re.findall(r"#([\w-]+)", last))
    tag = None
    m = re.match(r"^([a-zA-Z][\w-]*)", last)
    if m: tag = m.group(1).lower()
    pe = ""
    m = re.search(r"::?(before|after|first-line|first-letter|marker|selection|placeholder|backdrop|-webkit-[\w-]+|-moz-[\w-]+|file-selector-button)", last)
    if m: pe = m.group(1)
    return classes, ids, tag, pe


# ── 屬性家族 ────────────────────────────────────────────────────────────
def family(p):
    p = p.lower()
    if p.startswith("--"): return p
    p = re.sub(r"^-(webkit|moz|ms)-", "", p)
    if p.startswith("border-radius") or re.match(r"border-(top|bottom|start|end)-(left|right|start|end)-radius", p): return "border-radius"
    for pre, fam in (("border", "border"), ("background", "background"), ("margin", "margin"), ("padding", "padding"),
                     ("font", "font"), ("line-height", "font"), ("flex", "flex"), ("grid", "grid"), ("overflow", "overflow"),
                     ("transition", "transition"), ("animation", "animation"), ("text-decoration", "text-decoration"),
                     ("outline", "outline"), ("list-style", "list-style"), ("mask", "mask"), ("scroll-margin", "scroll-margin"), ("scroll-padding", "scroll-padding"), ("break", "break"), ("page-break", "break")):
        if p.startswith(pre): return fam
    if p in ("gap", "row-gap", "column-gap", "grid-gap"): return "gap"
    if p in ("top", "right", "bottom", "left", "inset", "inset-block", "inset-inline"): return "inset"
    if p in ("align-items", "justify-items", "place-items"): return "place-items"
    if p in ("align-content", "justify-content", "place-content"): return "place-content"
    if p in ("align-self", "justify-self", "place-self"): return "place-self"
    if p in ("width", "inline-size"): return "width"
    if p in ("height", "block-size"): return "height"
    if p in ("min-width", "min-inline-size"): return "min-width"
    if p in ("max-width", "max-inline-size"): return "max-width"
    if p in ("min-height", "min-block-size"): return "min-height"
    if p in ("max-height", "max-block-size"): return "max-height"
    return p


# ── 同一個元素上會一起出現的 class：掃 js、html、py 裡的 class 屬性與字串 ─────────
TOKEN = re.compile(r"[A-Za-z_][\w-]*")


def class_attrs(text):
    """找 class="…"（含 ${…} 洞、含跳脫引號），回 (字面 token, 洞裡字串 token, 是否有打不開的洞, 洞的原文)。"""
    out = []
    for m in re.finditer(r"""class(?:Name)?\s*=\s*(\\?["'`])""", text):
        q = m.group(1)
        i = m.end()
        lits, holes = [], []
        cur = []
        n = len(text)
        while i < n:
            if text.startswith(q, i):
                break
            if text.startswith("${", i):
                d, j = 1, i + 2
                while j < n and d:
                    if text[j] == "{": d += 1
                    elif text[j] == "}": d -= 1
                    j += 1
                holes.append(text[i + 2:j - 1])
                i = j
                cur.append("\u0001 ")
                continue
            if text[i] == "\n" and q in ('"', "'"):
                break
            cur.append(text[i]); i += 1
        lit = "".join(cur)
        toks = set(TOKEN.findall(lit.replace("\u0001", " ")))
        toks |= {x + "*" for x in re.findall(r"([A-Za-z_][\w-]*)\u0001", lit)}
        out.append((toks, holes))
    return out


LIT = re.compile(r"""\"([^\"\n]*)\"|'([^'\n]*)'|`([^`]*)`""")
CLOSED_HOLE = re.compile(r"""^\s*[^?]*\?\s*(\"[^\"]*\"|'[^']*'|`[^`$]*`)\s*:\s*(\"[^\"]*\"|'[^']*'|`[^`$]*`)\s*$""")


def hole_tokens(hole):
    """class 屬性洞裡的字串：字面的 token，加上動態前綴（洞裡的 ` mood-${a.mood}`、"k-" + kind 算 mood-*、k-*）。"""
    toks = set()
    for g in LIT.finditer(hole):
        s = next(x for x in g.groups() if x is not None)
        found = TOKEN.findall(s)
        toks |= set(found)
        toks |= {x + "*" for x in found if x.endswith("-")}
        toks |= {x + "*" for x in re.findall(r"([A-Za-z_][\w-]*)\$\{", s)}
    return toks


def inventory(paths):
    co: dict[str, set[str]] = {}
    open_attr: set[str] = set()
    wild: set[str] = set()
    open_holes = []
    def link(ts):
        for a in ts:
            co.setdefault(a, set()).update(ts)
    for p in paths:
        t = Path(p).read_text(encoding="utf-8", errors="replace")
        for lits, holes in class_attrs(t):
            toks = set(lits)
            is_open = False
            for h in holes:
                toks |= hole_tokens(h)
                if not CLOSED_HOLE.match(h):
                    is_open = True
                    open_holes.append((sorted(lits)[:4], h[:80], Path(p).name))
            link(toks)
            if is_open:
                open_attr |= toks
        for m in re.finditer(r"classList\.(?:add|toggle|remove|replace)\(([^)]*)\)", t):
            for g in LIT.finditer(m.group(1)):
                wild |= set(TOKEN.findall(next(x for x in g.groups() if x is not None)))
    return co, open_attr, wild, open_holes


def prefix_hit(star, tok):
    """star 是 "side-*" 這種。字根兩個字以內又沒有連字號的（r、t）只算兩個字以內的尾巴（r1、t12）；
    g-、k-、q- 這種寫明了是前綴，後面接的是資料值（g-redgold、k-material），多長都算。"""
    stem = star[:-1]
    if not tok.startswith(stem):
        return False
    return len(stem) > 2 or stem.endswith("-") or len(tok) - len(stem) <= 2


class Co:
    def __init__(self, co, open_attr, wild, loose):
        self.co, self.open_attr, self.wild, self.loose = co, open_attr, wild, loose
        self.pre = [t for t in co if t.endswith("*")]
    def can(self, a, b):
        if a == b: return True
        if frozenset((a, b)) in NOT_SAME_EL: return False
        if a in self.wild or b in self.wild: return True
        if b in self.co.get(a, ()): return True
        pa = [t for t in self.pre if prefix_hit(t, a)]
        pb = [t for t in self.pre if prefix_hit(t, b)]
        for t in pa:
            if b in self.co.get(t, ()) or any(u in self.co.get(t, ()) for u in pb): return True
        for t in pb:
            if a in self.co.get(t, ()): return True
        return False


def same_el(sa, sb, co):
    ca, ia, ta, pa = sa
    cb, ib, tb, pb = sb
    if pa != pb: return False
    if ta and tb and ta != tb: return False
    if ia and ib and not (ia & ib): return False
    if ca and cb:
        return all(co.can(x, y) for x in ca for y in cb)
    return True


# ── 比對 ────────────────────────────────────────────────────────────────
def leaves(tops, owner_of_top):
    """(top index, rule, selector, spec, subject, family, important) 的清單。"""
    out = []
    for ti, top in enumerate(tops):
        for r in top.rules:
            for s in r.sels:
                sp, su = specificity(s), subject(s)
                for p, imp, _v in r.decls:
                    out.append((ti, r, s, sp, su, family(p), imp))
    return out


def conflicts(tops, rank, co, want=None):
    """rank[ti] = 頭尾新順序；回 (ti, tj, sel_i, sel_j, family) 清單，ti 在原本的前面、搬完在後面。"""
    idx: dict[tuple, list] = {}
    for leaf in leaves(tops, None):
        ti, r, s, sp, su, fam, imp = leaf
        idx.setdefault((sp, fam, imp), []).append(leaf)
    res = []
    seen = set()
    for key, lst in idx.items():
        if len(lst) < 2: continue
        for i in range(len(lst)):
            ai = lst[i]
            for j in range(i + 1, len(lst)):
                bj = lst[j]
                if ai[0] == bj[0]: continue
                x, y = (ai, bj) if ai[0] < bj[0] else (bj, ai)
                if rank[x[0]] <= rank[y[0]]: continue
                if not same_el(x[4], y[4], co): continue
                k = (x[0], y[0], x[2], y[2], key[1])
                if k in seen: continue
                seen.add(k)
                res.append(k)
    # keyframes 同名
    names = {}
    for ti, top in enumerate(tops):
        if top.kf: names.setdefault(top.kf, []).append(ti)
    for nm, tis in names.items():
        for a in tis:
            for b in tis:
                if a < b and rank[a] > rank[b]:
                    res.append((a, b, "@keyframes " + nm, "@keyframes " + nm, "keyframes"))
    return res


DECL2 = re.compile(r"^  (?:async function|function|const|let|var|class)\s+([A-Za-z_$][\w$]*)", re.M)
_TAGRE = re.compile(r"^[a-zA-Z][\w-]*")


def split_compounds(sel):
    """回 [(compound 字串, 它左邊的連接符)]，最右邊是主體。"""
    out, cur, d, br = [], [], 0, 0
    comb = " "
    i, n = 0, len(sel)
    last = None
    while i < n:
        c = sel[i]
        if c == "(":
            d += 1
        elif c == ")":
            d -= 1
        elif c == "[":
            br += 1
        elif c == "]":
            br -= 1
        if d == 0 and br == 0 and c in " >+~":
            if cur:
                out.append(("".join(cur), last))
                cur = []
                last = " "
            if c != " ":
                last = c
            i += 1
            continue
        cur.append(c)
        i += 1
    if cur:
        out.append(("".join(cur), last))
    return out


def comp_info(comp):
    """(classes, anyofs, tag, ids, pseudo_el)"""
    anyofs = []
    plain = []
    i, n = 0, len(comp)
    while i < n:
        m = re.match(r":(is|where|not|has|nth-child|nth-of-type|nth-last-child)\(", comp[i:])
        if comp[i] == ":" and m:
            j = i + m.end()
            d = 1
            k = j
            while k < n and d:
                if comp[k] == "(":
                    d += 1
                elif comp[k] == ")":
                    d -= 1
                k += 1
            if m.group(1) in ("is", "where"):
                alts = [a.strip() for a in split_top(comp[j:k - 1], ",")]
                cl = []
                for a in alts:
                    last = split_compounds(a)[-1][0]
                    cs = re.findall(r"\.([\w-]+)", last)
                    if cs:
                        cl.append(cs[0])
                    else:
                        cl = None
                        break
                if cl:
                    anyofs.append(set(cl))
            i = k
            continue
        plain.append(comp[i])
        i += 1
    p = "".join(plain)
    p = re.sub(r"\[[^\]]*\]", "", p)
    classes = set(re.findall(r"\.([\w-]+)", p))
    ids = set(re.findall(r"#([\w-]+)", p))
    m = _TAGRE.match(p)
    tag = m.group(1).lower() if False else (m.group(0).lower() if m else None)
    pe = ""
    m = re.search(r"::?(before|after|first-line|first-letter|marker|selection|placeholder|backdrop|-webkit-[\w-]+|-moz-[\w-]+|file-selector-button)", p)
    if m:
        pe = m.group(1)
    return classes, anyofs, tag, ids, pe


@dataclass(frozen=True)
class Sel:
    text: str
    sub: frozenset
    sub_any: tuple
    tag: str | None
    ids: frozenset
    pe: str
    anc: tuple   # tuple of frozenset (any-of)
    parent: frozenset = frozenset()  # 主體左邊是「>」時，爸爸身上的 class


@lru_cache(maxsize=None)
def sel_of(sel: str) -> Sel:
    comps = split_compounds(sel)
    if not comps:
        return Sel(sel, frozenset(), (), None, frozenset(), "", ())
    subj = comp_info(comps[-1][0])
    parent = frozenset(comp_info(comps[-2][0])[0]) if len(comps) > 1 and comps[-1][1] == ">" else frozenset()
    anc = []
    # 從右往左：連接符是 + ~ 的左邊那一個不是祖先（是手足），不算進要求
    for idx in range(len(comps) - 1, 0, -1):
        comb = comps[idx][1]
        left = comps[idx - 1][0]
        if comb in ("+", "~"):
            continue
        cs, ao, _, _, _ = comp_info(left)
        for c in cs:
            anc.append(frozenset({c}))
        for a in ao:
            anc.append(frozenset(a))
    return Sel(sel, frozenset(subj[0]), tuple(frozenset(a) for a in subj[1]), subj[2], frozenset(subj[3]), subj[4], tuple(anc), parent)


VOID = {"img", "input", "br", "hr", "meta", "link", "source", "path", "circle", "line", "rect", "polyline", "polygon", "ellipse", "use"}
TAG = re.compile(r"<(/?)([a-zA-Z][\w-]*)((?:[^<>`]|`[^`]*`|\$\{[^}]*\})*?)(/?)>")
CALLRE = re.compile(r"(?<![\w$.])([A-Za-z_$][\w$]*)\(")
MAPRE = re.compile(r"\.(?:map|filter|flatMap)\(([A-Za-z_$][\w$]*)[,)]")


LOCALNAME = re.compile(r"(?<![\w$.])(?:const|let|var)\s+([A-Za-z_$][\w$]*)")
PARAMS = re.compile(r"\s*(?:async\s+)?(?:function\s+[\w$]+\s*|(?:const|let|var)\s+[\w$]+\s*=\s*(?:async\s*)?)\(([^()]*)\)")


def scan_end(body, i):
    """從 i 往後找這個述句（或這組呼叫參數）的結尾：括號、字串、樣板與裡面的 ${} 都收完之後的分號，或多出來的右括號。"""
    stack = []
    n = len(body)
    while i < n:
        c = body[i]
        if stack and stack[-1] == "`":
            if c == "\\":
                i += 2
                continue
            if c == "`":
                stack.pop()
            elif body.startswith("${", i):
                stack.append("${")
                i += 2
                continue
            i += 1
            continue
        if c in "\"'":
            j = i + 1
            while j < n and body[j] != c and body[j] != "\n":
                j += 2 if body[j] == "\\" else 1
            i = j + 1
            continue
        if c == "`" or c in "([{":
            stack.append(c)
        elif c in ")]}":
            if not stack:
                return i
            stack.pop()
        elif c == ";" and not stack:
            return i
        i += 1
    return n


def local_vars(body):
    """函式裡的區域變數 → 它的內容（宣告的右邊，加上 x = …、x += …、x.push(…) 這幾種往裡面放東西的地方）。"""
    first = len(body) - len(body.lstrip())
    names = {m.group(1) for m in LOCALNAME.finditer(body) if m.start() != first}  # 第一個是這個函式自己的宣告
    out = {n: set() for n in names}
    if names:
        alt = "|".join(re.escape(n) for n in sorted(names))
        for m in re.finditer(r"(?<![\w$.])(" + alt + r")\s*(?:\+=|=(?![=>])|\.push\(|\.unshift\()", body):
            out[m.group(1)].add(body[m.end():scan_end(body, m.end())])
    return out


def refs_re(names):
    return re.compile(r"(?<![\w$.])(" + "|".join(re.escape(n) for n in sorted(names)) + r")(?![\w$])") if names else None


def carried(text, vars_, calls, seen=None):
    """一段程式放進標籤裡時帶進去的東西：寫到的 class、叫到的函式；寫到別的區域變數就跟著看。回 (class token, 函式名)。"""
    seen = set() if seen is None else seen
    toks = set()
    for lits, holes in class_attrs(text):
        toks |= lits
        for h in holes:
            toks |= hole_tokens(h)
    callees = (set(CALLRE.findall(text)) | set(MAPRE.findall(text))) & calls
    ref = refs_re(vars_)
    for v in (set(ref.findall(text)) if ref else ()):
        if v in seen:
            continue
        seen.add(v)
        for chunk in vars_[v]:
            more = carried(chunk, vars_, calls, seen)
            toks |= more[0]
            callees |= more[1]
    return toks, callees


def params_of(body):
    m = PARAMS.match(body)
    return set(re.findall(r"(?:^|,)\s*([A-Za-z_$][\w$]*)", m.group(1))) if m else set()


def lexical(body, calls):
    """把函式本體當成一條 HTML 流，算字面上的巢狀。回 pairs：(外層 token, 內層 token 或 ("call", 名字))。
    loose=True 表示收不起來（開收標籤對不上、或有 innerHTML 這種放進去的動作），呼叫端退回保守算法。
    wrap：包住參數的外層 token（呼叫端傳進去的東西也算包在裡面，`.xxx` 取值的不算，那是資料）；vars：local_vars 的結果。"""
    stack = []  # [(tag, tokens)]
    pairs = set()
    seen = set()
    loose = bool(re.search(r"\.innerHTML|insertAdjacentHTML|\.append\(|appendChild", body))
    pos = 0
    vars_ = local_vars(body)
    ref = refs_re(vars_)
    params = params_of(body) - set(vars_)
    pref = re.compile(r"(?<![\w$.])(?:" + "|".join(re.escape(n) for n in sorted(params)) + r")(?![\w$])(?!\.(?!join\(|map\())") if params else None
    wrap = set()
    def add_calls(text):
        names = (set(CALLRE.findall(text)) | set(MAPRE.findall(text))) & calls
        for n in names:
            for _, toks in stack:
                for o in toks:
                    pairs.add((o, ("call", n)))
        if not stack:
            return
        for v in (set(ref.findall(text)) if ref else ()):
            in_toks, in_calls = carried("".join(vars_[v]), vars_, calls, {v})
            for _, toks in stack:
                for o in toks:
                    pairs.update((o, t) for t in in_toks)
                    pairs.update((o, ("call", n)) for n in in_calls)
        if pref and pref.search(text):
            for _, toks in stack:
                wrap.update(toks)
    bad = 0
    for m in TAG.finditer(body):
        add_calls(body[pos:m.start()])
        pos = m.end()
        closing, tag, attrs, selfclose = m.group(1), m.group(2).lower(), m.group(3), m.group(4)
        if closing:
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] == tag:
                    del stack[i:]
                    break
            else:
                bad += 1
            continue
        toks = set()
        for lits, holes in class_attrs("<" + attrs + ">"):
            toks |= lits
            for h in holes:
                toks |= hole_tokens(h)
        add_calls(attrs)
        seen |= toks
        for _, outer in stack:
            for o in outer:
                for t in toks:
                    pairs.add((o, t))
        if tag not in VOID and not selfclose:
            stack.append((tag, toks))
    add_calls(body[pos:])
    if stack:
        bad += len(stack)
    return {"pairs": pairs, "seen": seen, "loose": loose or bad > 0, "wrap": wrap, "vars": vars_}


class Nest:
    """token → 寫到它的函式；函式 → 碰得到的函式。"""
    def __init__(self, web: Path, py_paths, co: Co):
        self.co = co
        self.emit: dict[str, set[str]] = {}
        self.lit_toks = {}
        self.bodies = {}
        self.lex = {}   # 函式 → [(外層 token, 內層 token 或 ("call", 名字))]
        self.calls: dict[str, set[str]] = {}
        self.unknown_ok = set()
        names = set()
        bodies = {}
        for p in sorted(web.glob("*.js")):
            if p.name == "sw.js":
                continue
            t = p.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
            ms = list(DECL2.finditer(t))
            for i, m in enumerate(ms):
                b = t[m.start(): ms[i + 1].start() if i + 1 < len(ms) else len(t)]
                nm = m.group(1)
                key = nm if nm not in bodies else f"{nm}@{p.name}"
                bodies[key] = b
                names.add(nm)
        for f, b in bodies.items():
            toks = set()
            for lits, holes in class_attrs(b):
                toks |= lits
                for h in holes:
                    toks |= hole_tokens(h)
            for tk in toks:
                self.emit.setdefault(tk, set()).add(f)
            self.lit_toks[f] = set()
            for g in LIT.finditer(b):
                s = next(x for x in g.groups() if x is not None)
                if len(s) < 80:
                    self.lit_toks[f] |= set(TOKEN.findall(s))
            called = set(re.findall(r"(?<![\w$.])([A-Za-z_$][\w$]*)\(", b)) | set(re.findall(r"\.(?:map|filter|flatMap)\(([A-Za-z_$][\w$]*)[,)]", b))
            local = set(re.findall(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=", b[1:])) | set(re.findall(r"\(([A-Za-z_$][\w$]*)(?:\s*=[^,)]*)?[,)]", b))
            self.calls[f] = ((called & names) - local) - {f.split("@")[0]}
        # 驅動者（自己設 innerHTML、等 API、叫 render）不當被叫的那一方：一路展開會碰到整個程式
        self.driver = {f.split("@")[0] for f, b in bodies.items() if re.search(r"\.innerHTML|\bawait\b|\brender\(|addEventListener|refreshPage\(|\bsetMain\(", b)}
        self.driver |= {"render", "renderPage", "enter", "choose", "onAction", "poll", "act", "api"}
        self.bodies = bodies
        for f, b in bodies.items():
            self.lex[f] = lexical(b, self.calls[f])
        # 參數放進標籤裡的函式（fireHtml(fire, open, extra)）：每個呼叫的地方傳進去的東西，都算包在那些標籤裡面
        self.arg_pairs: dict[str, set] = {}
        wrappers = {}
        for f, info in self.lex.items():
            if info["wrap"]:
                wrappers.setdefault(f.split("@")[0], []).append(f)
        for g, b in bodies.items():
            for m in CALLRE.finditer(b):
                for f in wrappers.get(m.group(1), ()):
                    in_toks, in_calls = carried(b[m.end():scan_end(b, m.end())], self.lex[g]["vars"], self.calls[g])
                    for o in self.lex[f]["wrap"]:
                        self.arg_pairs.setdefault(f, set()).update({(o, t) for t in in_toks} | {(o, ("call", n)) for n in in_calls})
        self.reach_cache = {}
        self.pre = [t for t in self.emit if t.endswith("*")]
        pytext = []
        for p in py_paths:
            pytext.append(Path(p).read_text(encoding="utf-8", errors="replace"))
        self.py_tokens = set()
        for t in pytext:
            for lits, holes in class_attrs(t):
                self.py_tokens |= lits

    def reach(self, f):
        if f in self.reach_cache:
            return self.reach_cache[f]
        seen = {f}
        stack = [f]
        while stack:
            x = stack.pop()
            for y in self.calls.get(x, ()):
                if y in self.driver:
                    continue
                if y not in seen:
                    seen.add(y)
                    stack.append(y)
        self.reach_cache[f] = seen
        return seen

    @lru_cache(maxsize=None)
    def emitters(self, tok):
        out = set(self.emit.get(tok, ()))
        for t in self.pre:
            if prefix_hit(t, tok):
                out |= self.emit[t]
        if not out:
            pat = re.compile(r"(?<![\w-])" + re.escape(tok) + r"(?![\w-])")
            out = {f for f, b in self.bodies.items() if pat.search(b)}
        return out

    @lru_cache(maxsize=None)
    def may_contain(self, x, y):
        if x == y:
            return True
        if (x, y) in NOT_INSIDE:
            return False
        if x in self.co.wild or y in self.co.wild:
            return True
        ex, ey = self.emitters(x), self.emitters(y)
        if not ex or not ey or x in self.py_tokens or y in self.py_tokens:
            return True
        names_x = {x} | {t for t in self.pre if prefix_hit(t, x)}
        names_y = {y} | {t for t in self.pre if prefix_hit(t, y)}
        for f in ex:
            info = self.lex.get(f)
            for outer, inner in self.arg_pairs.get(f, ()):
                if outer not in names_x:
                    continue
                if isinstance(inner, tuple):
                    if inner[1] not in self.driver and self.reach(inner[1]) & ey:
                        return True
                elif inner in names_y:
                    return True
            if info is None or info["loose"]:
                if self.reach(f) & ey:
                    return True
                continue
            # 這個函式裡：x 的元素底下字面寫了 y，或叫了碰得到 y 的函式
            hit_any_x = False
            for outer, inner in info["pairs"]:
                if outer not in names_x:
                    continue
                hit_any_x = True
                if isinstance(inner, tuple):
                    callee = inner[1]
                    if callee in self.driver:
                        continue
                    if self.reach(callee) & ey:
                        return True
                elif inner in names_y:
                    return True
            if not hit_any_x and not info["seen"] & names_x:
                # 字面找不到（後備字面才找到的）：保守
                if self.reach(f) & ey:
                    return True
        return False

    def nestable(self, x, y):
        return self.co.can(x, y) or self.may_contain(x, y) or self.may_contain(y, x)


_DEAD = {}


def is_dead(s: Sel, nest: Nest) -> bool:
    """選擇器要求的 class 在 js、py、index.html 都找不到（連動態前綴都沒有）：這條規則碰不到任何元素。"""
    got = _DEAD.get(s.text)
    if got is None:
        got = _DEAD[s.text] = _is_dead(s, nest)
    return got


def _is_dead(s: Sel, nest: Nest) -> bool:
    for c in list(s.sub) + [next(iter(r)) for r in s.anc if len(r) == 1]:
        if c in nest.co.wild or c in nest.py_tokens or c in nest.co.co:
            continue
        if not nest.emitters(c):
            return True
    return False


def can_same(a: Sel, b: Sel, nest: Nest) -> bool:
    co = nest.co
    if a.pe != b.pe:
        return False
    if is_dead(a, nest) or is_dead(b, nest):
        return False
    if a.tag and b.tag and a.tag != b.tag:
        return False
    if a.ids and b.ids and not (a.ids & b.ids):
        return False
    # 兩邊都寫了「>」：爸爸是同一個元素，爸爸的 class 要能寫在一起（.muster-head > p 對 .rv-scene > p 打不到同一個 p）
    for x in a.parent:
        for y in b.parent:
            if not co.can(x, y):
                return False
    for x in a.sub:
        for y in b.sub:
            if not co.can(x, y):
                return False
    for ao in a.sub_any:
        if b.sub and not any(all(co.can(x, y) for y in b.sub) for x in ao):
            return False
    for ao in b.sub_any:
        if a.sub and not any(all(co.can(x, y) for y in a.sub) for x in ao):
            return False
    # a 的祖先要包得住 b 這個元素（或就是它），也要跟 b 的祖先在同一條線上
    def check(p: Sel, q: Sel):
        for req in p.anc:
            ok = False
            for x in req:
                if x in co.wild:
                    ok = True
                    break
                sub_ok = all(nest.may_contain(x, y) or co.can(x, y) for y in q.sub)
                anc_ok = all(any(nest.nestable(x, z) for z in r) for r in q.anc)
                if sub_ok and anc_ok:
                    ok = True
                    break
            if not ok:
                return False
        return True
    return check(a, b) and check(b, a)


def leaves2(tops):
    out = []
    for ti, top in enumerate(tops):
        for r in top.rules:
            for s in r.sels:
                sp, se = specificity(s), sel_of(s)
                fams = {}
                for p, imp, v in r.decls:
                    fams.setdefault((family(p), imp), set()).add((p, v))
                for (fam, imp), pv in fams.items():
                    out.append((ti, s, sp, se, fam, imp, frozenset(pv)))
    return out


def conflicts2(tops, rank, nest, leaves_cache=None):
    idx = leaves_cache
    if idx is None:
        idx = {}
        for leaf in leaves2(tops):
            ti, s, sp, se, fam, imp, pv = leaf
            idx.setdefault((sp, fam, imp), []).append(leaf)
    res = []
    seen = set()
    memo = {}
    for key, lst in idx.items():
        if len(lst) < 2:
            continue
        for i in range(len(lst)):
            ai = lst[i]
            ra = rank[ai[0]]
            for j in range(i + 1, len(lst)):
                bj = lst[j]
                if ai[0] == bj[0]:
                    continue
                rb = rank[bj[0]]
                if (ai[0] < bj[0]) == (ra < rb):
                    continue
                x, y = (ai, bj) if ai[0] < bj[0] else (bj, ai)
                if x[6] == y[6]:
                    continue  # 同屬性同值：誰蓋誰都一樣
                mk = (x[1], y[1])
                if mk not in memo:
                    memo[mk] = can_same(x[3], y[3], nest)
                if not memo[mk]:
                    continue
                k = (x[0], y[0], x[1], y[1], key[1])
                if k in seen:
                    continue
                seen.add(k)
                res.append(k)
    names = {}
    for ti, top in enumerate(tops):
        if top.kf:
            names.setdefault(top.kf, []).append(ti)
    for nm, tis in names.items():
        for a in tis:
            for b in tis:
                if a < b and rank[a] > rank[b]:
                    res.append((a, b, "@keyframes " + nm, "@keyframes " + nm, "keyframes"))
    return res, idx


# ── 手動認定（讀過程式才寫）──────────────────────────────────────────────
NOT_EVERYWHERE = {"peer-focus": {"btn", "small", "peer-acts"}}  # classList 加的，但只加在玩家卡那幾顆鈕上（peers.js 的 peerFocus）
# 逐對的認定：這兩個 class 碰不到同一個元素（第 86 批讀過 map.js、guide.js、app.js 才寫）。不放進 NOT_EVERYWHERE：它把整個 class 拿出 wild，
# .glow 會落在 #page 任何一顆鈕上、夥伴列不完，放進去 .glow 對 .btn 這種也一起不算了，工具變鬆。
# 共同的事實：.mapx 與底下的東西只在有底圖時畫（map.js 的 pageMap，沒底圖只有一行 .muted），有底圖就畫在 #map-host（showMapHost），
# 它在 body 底下、不在 #app 裡（mapHost）。node 的假瀏覽器才畫在 #page。
NOT_SAME_EL = {frozenset(pair) for pair in (
    # guide.js 的 applyFocus：只加在 #top、#page、nav.tabs 裡的元素（不在這三塊裡的跳過）
    ("onb-dim", "mv-side"), ("onb-dim", "mv-geo"), ("onb-dim", "mv-reg"), ("onb-dim", "mv-fab"), ("onb-dim", "mv-ground"), ("onb-dim", "mdrawer"),
    # guide.js 的 .glow：#page [data-id]、#page .act-move [data-id]、[data-glow~=…]；map.js 一處 data-glow 都沒寫
    ("glow", "mv-fight"), ("glow", "mv-pulse"), ("glow", "mv-side"), ("glow", "mv-you"), ("glow", "mv-eta"), ("glow", "mv-q"), ("glow", "w-melee"), ("glow", "mdrawer"),
    # guide.js 的 .lit：只有 [data-glow~=…]
    ("lit", "mv-fight"), ("lit", "mv-pulse"), ("lit", "w-melee"),
    # 工具把 class="mv-pin ink${dim}"（map.js）認成前綴 ink*；.ink-drop 只由 drop.className = "ink-drop"（app.js）建，身上沒別的 class
    ("ink-drop", "mv-pin"),
)}
DEAD_CLASSES = ("insight",)  # 沒有任何 class 屬性寫到（"insight" 只是資料的 kind），規則碰不到元素
NOT_INSIDE = {("vn-menu", "gather-branches")}  # vn-menu 放的是對話選單（companions.js 的 vnTalkHtml）；對話時選項只有 talk:*（talk_actions.py），沒有 explore:gather:*


def page_sheets(root: Path) -> list[str]:
    """index.html 載入的所有樣式，照載入的先後（/journal.css 是伺服器生的，不在 web/ 底下，不算）。"""
    return re.findall(r'href="/static/([^"]+\.css)"', (root / "web" / "index.html").read_text(encoding="utf-8"))


def read_css(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def main(argv: list[str]) -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    base, head = Path(argv[1]), Path(argv[2])
    tops = []
    where = []  # 每一條規則在 base 哪一支
    for name in page_sheets(base):
        for top in parse(read_css(base / "web" / name)):
            tops.append(top)
            where.append(name)
    waiting: dict[str, list[int]] = {}
    for ti, top in enumerate(tops):
        waiting.setdefault(top.raw, []).append(ti)
    rank: dict[int, int] = {}
    sheet_of: dict[int, str] = {}
    extra = []
    n = 0
    sheets = page_sheets(head)
    for name in sheets:
        for top in parse(read_css(head / "web" / name)):
            got = waiting.get(top.raw)
            if not got:
                extra.append((name, top.start, top.raw[:60]))
                continue
            ti = got.pop(0)
            rank[ti], sheet_of[ti] = n, name
            n += 1
    lost = [(where[ti], tops[ti].start, tops[ti].raw[:60]) for ti in range(len(tops)) if ti not in rank]
    print("載入先後：", sheets)
    print("base 有、head 不見的規則：", len(lost), lost[:5])
    print("head 多出來的規則：", len(extra), extra[:5])
    if lost or extra:
        return 1
    print("換了檔的規則：", sum(1 for ti in rank if sheet_of[ti] != where[ti]), "／", len(tops))
    web = head / "web"
    pys = [str(p) for p in head.joinpath("tianxia").rglob("*.py") if "tests" not in p.parts] + [str(head / "server.py")]
    paths = [str(p) for p in web.glob("*.js") if p.name != "sw.js"] + [str(web / "index.html")] + pys
    co, open_attr, wild, _ = inventory(paths)
    together = Co(co, open_attr, wild, set())
    nest = Nest(web, pys, together)
    for cls, partners in NOT_EVERYWHERE.items():
        together.wild.discard(cls)
        together.co.setdefault(cls, set()).update(partners)
    for top in tops:
        for r in top.rules:
            for s in r.sels:
                if any(re.search(r"\." + c + r"(?![\w-])", s) for c in DEAD_CLASSES):
                    _DEAD[s] = True
    res, _ = conflicts2(tops, rank, nest, None)
    print("先後反了又可能打架的規則對：", len(res))
    shown = set()
    for x in res:
        if (x[2], x[3]) in shown:
            continue
        shown.add((x[2], x[3]))
        print(f"  {x[2][:56]} ｜ {x[3][:56]}  {x[4]}  base {where[x[0]]}:{tops[x[0]].start}、{where[x[1]]}:{tops[x[1]].start}（head {sheet_of[x[0]]}、{sheet_of[x[1]]}）")
    return 1 if res else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
