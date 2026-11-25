"""慢慢長出來的小事卡（提案表「七個系統第一次碰到的小事」，Joy 2026-11-25）：門派、結義、書信、稱號、江湖錄、合成第一次碰到時，
攤一張卡——一張圖、一兩句話、一顆真的做第一步的鈕（拜入、邀他結義、寫一封、戴上、翻開、去煉製），另一顆「改天」收起。
親衛是現在那一件撞見孩子的事，不另出卡。每一種一個角色只出一次，同一時間只攤一張，其他排著等下一次看。

這裡只看狀態、挑下一張、寫卡上的字；卡怎麼畫、鈕怎麼帶過去在 web/unfold.js。只讀核心與共用層（fusion 是共用層）。"""
from __future__ import annotations

from tianxia import fusion
from tianxia.state import UnfoldBook

ORDER = ("sect", "mail", "jieyi", "title", "codex", "fuse")  # 同時成立時先出哪一張

# 待 joy 潤：卡上的字（{x} 是對象的名字）；圖在 web/unfold.js
WHO = {
    "sect": "{x}山門口", "mail": "{x}的名帖", "jieyi": "{x}", "title": "一枚剛蓋下的印", "codex": "江湖錄", "fuse": "夜裡",
}
SAY = {
    "sect": "掃地的門人抬頭：「進來喝口茶？」",
    "mail": "名帖背面寫著：「有事捎個信來。」",
    "jieyi": "打完那一場，他拍拍你的肩：「下回還一起。」",
    "title": "江湖上開始這樣叫你了：{x}。",
    "codex": "這件事，你記下了。",
    "fuse": "兩股意在身上互相頂著，睡不安穩。",
}
GO = {"sect": "進去看看", "mail": "寫一封", "jieyi": "邀他結義", "title": "戴上", "codex": "翻開", "fuse": "去煉製"}
LATER = "改天"


def _sect(ctx) -> tuple[str, str] | None:
    c, p = ctx.content, ctx.state.player
    if not c.config.zongmen.enabled or p.sect is not None or p.journey is not None:
        return None
    s = next((s for s in c.sects.values() if s.switch == "zongmen" and s.location == p.location and c.sect_open(s.id)
              and f"叛出:{s.id}" not in p.flags), None)  # 同 zongmen.rules.sect_here、join_problem（包不能 import 包）
    return (s.id, s.name) if s is not None else None


def _swapped(p) -> list[str]:
    """互換過名帖的人（你收著他的，也遞過你的給他）。"""
    return [x.name for x in p.mingtie_box if x.gave > 0]


def _jieyi(ctx) -> tuple[str, str] | None:
    """跟同一個人交過名帖、又一起打過（切磋過他、或並肩打過同一場）。"""
    c, s = ctx.content, ctx.state
    if not c.config.jieyi.enabled:
        return None
    for name in _swapped(s.player):
        if any(r.opponent == name or any(f.name == name for f in r.ours[1:]) for r in s.battles):
            return name, name
    return None


def _mail(ctx) -> tuple[str, str] | None:
    if not ctx.content.config.mail.enabled:
        return None
    names = _swapped(ctx.state.player)
    return (names[0], names[0]) if names else None


def _title(ctx) -> tuple[str, str] | None:
    worn = ctx.state.player.titles_worn
    if not ctx.content.config.titles.enabled or not worn.get("id"):
        return None
    return worn["id"], worn.get("name", "")


def _codex(ctx) -> tuple[str, str] | None:
    b = ctx.state.player.codex
    if not ctx.content.config.codex.enabled or b is None or not b.ended:
        return None
    e = b.ended[0]
    return f"{e.season}:{e.line}", ""


def fuse_pair(ctx) -> tuple[str, str] | None:
    """身上兩個合得起來的意境（第一對；煉製那一格也照它長出來）。"""
    s = ctx.state
    held = list(s.player.insights)
    for i, a in enumerate(held):
        for b in held[i + 1:]:
            if fusion.merge_problem(s, ctx.content, ctx.world, a, b) is None:
                return a, b
    return None


def _fuse(ctx) -> tuple[str, str] | None:
    pair = fuse_pair(ctx)
    return (f"{pair[0]}+{pair[1]}", "") if pair else None  # 「|」是卡的分隔，兩個意境用「+」


FIND = {"sect": _sect, "mail": _mail, "jieyi": _jieyi, "title": _title, "codex": _codex, "fuse": _fuse}


def look(ctx, book: UnfoldBook) -> None:
    """沒有攤著的卡時，挑下一張成立、還沒出過的攤上去（記成出過）。"""
    if book.card:
        return
    for kind in ORDER:
        if kind in book.done:
            continue
        hit = FIND[kind](ctx)
        if hit is not None:
            book.done.append(kind)
            book.card = f"{kind}|{hit[0]}|{hit[1]}"
            return


def close(book: UnfoldBook | None) -> None:
    """按了鈕或「改天」：收起這一張。"""
    if book is not None:
        book.card = ""


def view(book: UnfoldBook) -> dict | None:
    """網頁畫卡要的：種類、對象、說話的、那一句、鈕上的字。"""
    if not book.card:
        return None
    kind, arg, name = (book.card.split("|", 2) + ["", ""])[:3]
    if kind not in SAY:
        return None
    x = name or arg
    return {"kind": kind, "arg": arg, "who": WHO[kind].format(x=x), "say": SAY[kind].format(x=x), "go": GO[kind], "later": LATER}
