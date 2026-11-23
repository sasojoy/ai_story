"""Which differences between two walks are noise. Pure functions on numbers and strings: no files, no images.

The classes (each one came from a real row of waves B and C):
  aa           anti-aliasing on rounded corners: at most 12 levels and 100 pixels
  gutter       the 15px scrollbar landed on one side only: never at phone width, sw 15 apart (1265 against 1280, 626 against 641); grid tracks may move with it.
               Each picture goes by sw read at its own time (batch 258): the first picture by sw before it, the scrolled ones and the
               window's styles by sw at the end of the window (compare.py reads layoutEnd, which the driver keeps when the gutter moved
               mid-window even after shooting it again). Both sides at the same time, 15 apart; the same scrollbar and a 15px move is real.
  share        a fresh share code: the difference is only in /zhuan/CODE, /zhanji/CODE and the share row's rect
  tale         the chronicle link written earlier on one side: only in the link
  layout-used  used values read while layout was moving: only the properties below, and the pixels of that window agree
  layout-no-pixels  the same properties on a window the walk takes no pictures of (640, 641, 900): only the page's size says they agree, so it is counted apart.
               The pictures of those windows come from the replay, which gate.py runs when a stylesheet differs.
  render-variants  the replay only (batch 237): the DOM and every computed style agree, neither side unstable, only pixels beyond aa
               differ; each side reloads and draws that window again (replay.RERENDER_TIMES) and one side draws a picture the other drew.
               That is the page's own way of drawing, not the stylesheets (wave AA: the forge scenes 044-047, a round button's arc
               1 level apart, a material icon's edge 40 levels, two or three pictures per window at random; A against A went red too).
  repaint-variants  the walk only (batch 260), the same conditions as render-variants (DOM and every computed style agree, neither side
               unstable, the same size): a light scene's 375-light window is shot again on each side with no reload, once after a
               whole-page paint and once 1.1 s later (driver.mjs shootVariants, facts.variants), and each side drew the other side's very
               picture. That came from the c round's bt_watch_open/shut: batch 254's dpr flip took it from every c round to 1 in 6, and
               batch 260 measured why the rest: with no reload the battle card's countdown, rewritten every second, makes one side draw
               three ways (a whole-page paint; the countdown's piece repainted alone, 713 px 1 level; the whole card's picture, 4448 px
               3 levels), and the first picture is one of them at random (red 2 runs in 8). Left red: a side stuck in the third way for
               the whole scene (1 time in 32), and anything only one side can draw: its picture is never in the other side's set.
Not a class: main's nx_invite at 1280 (456 px, 36 levels, LCD against grayscale text behind the invite) is fixed when the page loads and
no repaint changes it; flows/main.mjs loads the page once more before it (batch 260), and it is still red when it shows.
Not differences at all: ?v=, the host, the toast's DOM, animation-delay, whitespace; stylesheet rules with the same text in another
order (that is what splitting a file looks like: the pixels and computed styles still have to agree). The toast's words do count,
when both sides still show them (compare.py).
All of it needs the DOM and the styles to agree after masking, and neither side unstable. Anything else is real.
"""
import re

AA_MAX_LEVELS = 12
AA_MAX_PIXELS = 100
GUTTER_PX = 15

LAYOUT_USED_EXACT = {"width", "height", "block-size", "inline-size", "top", "right", "bottom", "left", "perspective-origin", "transform-origin"}
LAYOUT_USED_PREFIX = ("margin-", "inset")
GUTTER_ALSO = {"grid-template-columns", "grid-template-rows"}  # the used tracks of a grid move with the 15px; only when the scrollbar is what differs

SHARE_PATTERNS = ((re.compile(r"/zhuan/[A-Za-z0-9_-]+"), "/zhuan/CODE"), (re.compile(r"/zhanji/[A-Za-z0-9_-]+"), "/zhanji/CODE"))
TOAST = re.compile(r'<div id="toast"[^>]*>.*?</div>', re.S)
TALE_LINK = re.compile(r'<button class="linkish huaben-link"[^>]*>[^<]*</button>')
VERSION = re.compile(r"\?v=[0-9a-zA-Z_-]+")
DELAY = re.compile(r"animation-delay:-?[0-9.]+s")
SPACE = re.compile(r"\s+")
BOT_WORDS = re.compile(r"假人|機器人")
BOT_TEXT = re.compile(r"假人|機器人|(^|[^a-zA-Z])bot([^a-zA-Z]|$)", re.I)


def hosts_pattern(origins) -> re.Pattern | None:
    """The hosts of this run, in every spelling the two sides can show them. origins are ("127.0.0.1:8292", "localhost:8293")."""
    ports = sorted({o.rsplit(":", 1)[1] for o in origins})
    if not ports:
        return None
    return re.compile(r"(?:127\.0\.0\.1|localhost):(?:" + "|".join(ports) + r")\b")


def mask_common(text: str, hosts=None) -> str:
    text = VERSION.sub("?v=X", text)
    if hosts is not None:
        text = hosts.sub("HOST", text)
    return text


def mask_dom(text: str, hosts=None) -> str:
    """The DOM the two sides have to agree on."""
    text = TOAST.sub("<toast/>", text)
    text = mask_common(text, hosts)
    text = DELAY.sub("animation-delay:X", text)
    text = _mask_share(text)
    text = TALE_LINK.sub("<tale-link/>", text)
    return SPACE.sub(" ", text)


def _mask_share(text: str) -> str:
    for pattern, sub in SHARE_PATTERNS:
        text = pattern.sub(sub, text)
    return text


def dom_noise(a: str, b: str, hosts=None) -> list[str]:
    """Two DOMs that agree after mask_dom: which volatile mask did the work. Empty when neither was needed."""
    def plain(text):
        return SPACE.sub(" ", DELAY.sub("animation-delay:X", mask_common(TOAST.sub("<toast/>", text), hosts)))
    x, y = plain(a), plain(b)
    if x == y:
        return []
    if _mask_share(x) == _mask_share(y):
        return ["share"]
    if TALE_LINK.sub("<tale-link/>", x) == TALE_LINK.sub("<tale-link/>", y):
        return ["tale"]
    return ["share", "tale"]


def mask_main(text: str, hosts=None) -> str:
    return _mask_share(mask_common(text, hosts))


def is_layout_used(prop: str) -> bool:
    return prop in LAYOUT_USED_EXACT or prop.startswith(LAYOUT_USED_PREFIX)


def used_only(props, flip: bool = False) -> bool:
    """Every property is a used value; flip: the two sides disagree about the scrollbar, so the grid tracks count too."""
    return all(is_layout_used(p) or (flip and p in GUTTER_ALSO) for p in props)


def style_class(props, pixels_same: bool, unstable: bool = False, has_pixels: bool = True) -> str | None:
    """props differ between the two sides on one window. Noise only when they are used values and that window looks the same.
    has_pixels False: "looks the same" only means the page has the same size."""
    props = set(props)
    if unstable or not props or not pixels_same or not all(is_layout_used(p) for p in props):
        return None
    return "layout-used" if has_pixels else "layout-no-pixels"


def within_aa(pixels: int, levels: int) -> bool:
    return pixels <= AA_MAX_PIXELS and levels <= AA_MAX_LEVELS


def pixel_class(pixels: int, levels: int, *, view: str, sw_a=None, sw_b=None, only_share: bool = False, only_tale: bool = False,
                clean: bool = True, unstable: bool = False, same_size: bool = True) -> str | None:
    """One screenshot differs. clean: DOM and styles agree after masking (for the gutter: styles differ only in used values)."""
    if unstable or not clean or not same_size:
        return None
    if only_share:
        return "share"
    if only_tale:
        return "tale"
    if view not in ("375-light", "375-dark") and sw_a is not None and sw_b is not None and abs(sw_a - sw_b) == GUTTER_PX:
        return "gutter"
    if within_aa(pixels, levels):
        return "aa"
    return None


def recheck_candidate(*, clean_strict: bool, unstable: bool, same_size: bool) -> bool:
    """The replay draws a picture again only when nothing but its pixels differ: the DOM and all computed styles agree
    (used values that moved count as a style difference here), neither side unstable, the same size."""
    return clean_strict and not unstable and same_size


def render_variants(seen_a, seen_b) -> bool:
    """The pictures (hashes) each side drew of one window over its re-renders: one in common and it is the page's own variants."""
    return bool(set(seen_a) & set(seen_b))


def repaint_variants(own_a, seen_a, own_b, seen_b) -> bool:
    """The walk (batch 260): own_* the hash of each side's picture, seen_* the hashes that side drew of the same window afterwards with no
    reload (driver.mjs shootVariants). Each side must have drawn the other side's very picture: a change only one side can draw is
    never in the other side's set, so it stays real (stricter than render_variants, which takes any picture in common)."""
    seen_a, seen_b = {own_a, *seen_a}, {own_b, *seen_b}
    return own_a in seen_b and own_b in seen_a


def scrollbar_flip(view: str, sw_a, sw_b) -> bool:
    """The two sides disagree only about the scrollbar."""
    return view not in ("375-light", "375-dark") and sw_a is not None and sw_b is not None and abs(sw_a - sw_b) == GUTTER_PX


def strip_scene(line: str) -> str:
    """Console and network lines start with the scene they happened in; the same message a scene later is the same message."""
    return line.split(": ", 1)[1] if ": " in line else line


def head_only(base_lines, head_lines, hosts=None) -> list[str]:
    """Messages (console, exceptions, 4xx) only the head has. A message both sides have is not a difference (the favicon of /zhanji/)."""
    def clean(line):
        return mask_common(strip_scene(line), hosts)
    seen = {clean(x) for x in base_lines}
    out, shown = [], set()
    for line in head_lines:
        c = clean(line)
        if c not in seen and c not in shown:
            shown.add(c)
            out.append(line)
    return out


def bot_words(text: str, *, dom: bool = False) -> str | None:
    """The visible text and the DOM must never give away who is a server player."""
    m = (BOT_WORDS if dom else BOT_TEXT).search(text or "")
    return m.group(0) if m else None


def matches_expect(expect, scene: str, cls: str) -> dict | None:
    """--expect rows: {"scene": regex, "class": "dom|style|pixel|main|...", "reason": "..."}. A row only counts when it matches a difference."""
    for row in expect or []:
        if re.search(row["scene"], scene) and row.get("class") in (cls, "*"):
            return row
    return None
