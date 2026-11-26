"""慢慢長出來的小事卡（提案表「七個系統第一次碰到的小事」，Joy 2026-11-25）：門派、結義、書信、稱號、江湖錄、合成第一次碰到時，
攤一張卡——一張圖、一兩句話、一顆真的做第一步的鈕（拜入、邀他結義、寫一封、戴上、翻開、去煉製），另一顆「改天」收起。
親衛是現在那一件撞見孩子的事，不另出卡。每一種一個角色只出一次，同一時間只攤一張，其他排著等下一次看。

這裡只看狀態、挑下一張、寫卡上的字；卡怎麼畫、鈕怎麼帶過去在 web/unfold.js。只讀核心與共用層（fusion 是共用層）。"""
from __future__ import annotations

from tianxia import fusion, library
from tianxia.core import jieyi_base
from tianxia.state import UnfoldBook

ORDER = ("gift", "buy", "sect", "mail", "jieyi", "jieyi_ok", "title", "guard", "codex", "fuse")  # 同時成立時先出哪一張
NEW_ONLY = ("gift", "buy")  # 只給新角色的（舊角色那一本不出：見面禮、買了之後教一次）

# 待 joy 潤：卡上的字（{x} 是對象的名字）；圖在 web/unfold.js
WHO = {
    "gift": "萬寶閣掌櫃", "sect": "{x}山門口", "mail": "{x}的名帖", "jieyi": "{x}", "title": "一枚剛蓋下的印", "codex": "江湖錄", "fuse": "夜裡",
    "guard": "{x}", "jieyi_ok": "金蘭帖",
}
SAY = {
    "gift": "「聽說你替{x}把事辦成了。這 {n} 元寶是見面禮，進來挑一件吧。」",
    "sect": "掃地的門人抬頭：「進來喝口茶？」",
    "mail": "名帖背面寫著：「有事捎個信來。」",
    "jieyi": "打完那一場，他拍拍你的肩：「下回還一起。」",
    "title": "江湖上開始這樣叫你了：{x}。",
    "codex": "這件事，你記下了。",
    "fuse": "兩股意在身上互相頂著，睡不安穩。",
    "guard": "「你回來啦。」他站在門邊，像是有話要說。",
    "jieyi_ok": "{x}答應了。往後你們以兄弟相稱。",
}
GO = {"gift": "收下，進去看看", "sect": "進去看看", "mail": "寫一封", "jieyi": "邀他結義", "title": "戴上", "codex": "翻開", "fuse": "去煉製",
      "guard": "回去看他", "jieyi_ok": "看金蘭帖"}
LATER = "改天"

# 買了之後教一次怎麼用（Joy 2026-11-25「很多商城裡面的東西也要教學」）：照商品的效果分種類，每一種第一次買到才出。待 joy 潤
BUY_SAY = {
    "pills": "回體丹收進行囊了。腿軟的時候服一顆。",
    "xinshen": "凝神香點上了，心神足了。找個人好好聊一聊。",
    "inscribe": "題壁墨帶在身上。走完一趟，在那兒留一句話。",
    "move_basic": "絕招的帖子到手了。替你的武功寫一句樣子。",
    "legend": "破境丹收好了。卡在關口上的時候服一顆。",
    "card_days": "月卡掛上了。每天來萬寶閣領一份。",
    "rename": "易名帖到手了。想好新名號就改。",
}
BUY_GO = {"pills": "服一顆", "xinshen": "去找人聊", "inscribe": "出門走走", "move_basic": "去寫一招", "legend": "去衝關",
          "card_days": "領今天的", "rename": "去改名"}


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


def _gift(ctx) -> tuple[str, str] | None:
    """辦完第一件託付（PlayerState.errands 有一件 done）：掌櫃送見面禮。商城關著、數字是 0 不出。"""
    s, c = ctx.state, ctx.content
    if c.config.unfold.gift <= 0 or ctx._wallet() is None:  # noqa: SLF001  核心的錢包（同 looks 包）
        return None
    e = next((e for e in s.player.errands if e.status == "done"), None)
    if e is None:
        return None
    return e.figure, c.figures[e.figure].name if e.figure in c.figures else ""


def gift_ref(owner: str) -> str:
    return f"grant:unfold:{owner}"  # 一個錢包一輩子一次（ref UNIQUE）


def give_gift(ctx) -> int:
    """按了見面禮那一張（收下或改天都算收下）：入帳，回入了幾個；入過了、商城關著回 0。"""
    wallet, amount = ctx._wallet(), ctx.content.config.unfold.gift  # noqa: SLF001
    if wallet is None or amount <= 0:
        return 0
    return amount if wallet.post(ctx._mall_owner(), amount, "grant", gift_ref(ctx._mall_owner()), time=ctx.now) else 0  # noqa: SLF001


def _bought(ctx, done: list[str]) -> tuple[str, str] | None:
    """第一次買到某一種東西（照購買的先後）：(種類, 商品名)。"""
    for buy in reversed(ctx.wallet.purchases()):
        item = ctx.content.mall.get(buy.item)
        if item is None or buy.refunded is not None:
            continue
        kind = next((k for k in item.effects if k in BUY_SAY), None)
        if kind is not None and f"buy:{kind}" not in done:
            return kind, item.name
    return None


def _guard(ctx) -> tuple[str, str] | None:
    """收養之後家裡第一件事攤在眼前（紀事還沒有一筆是你待他的）。"""
    kid = ctx.state.player.guard
    if not ctx.content.config.guard.enabled or kid is None or kid.stage != "grow" or kid.event is None or kid.event.kind != "home":
        return None
    return (str(kid.event.seq), kid.name) if len(kid.log) <= 1 else None


def _jieyi_ok(ctx) -> tuple[str, str] | None:
    """邀過人結義（出過結義那一張）之後，第一次真的結成了。"""
    if not ctx.content.config.jieyi.enabled:
        return None
    bros = jieyi_base.brothers(ctx.content, ctx.world, ctx.state.player.name)
    bk = jieyi_base.book(ctx.world)
    bond = jieyi_base.bond_of(bk, ctx.state.player.name) if bk is not None and bros else None
    if bond is None:
        return None
    other = next((m for m in bond.members if m != ctx.state.player.name), "")
    return other, other


FIND = {"gift": _gift, "sect": _sect, "mail": _mail, "jieyi": _jieyi, "title": _title, "codex": _codex, "fuse": _fuse,
        "guard": _guard, "jieyi_ok": _jieyi_ok}


def touched(ctx, kind: str) -> bool:
    """舊角色開本那一刻：這個系統碰過了（碰過的不帶）。此刻已經成立的也算碰過（不是「第一次碰到」那一下）。"""
    p = ctx.state.player
    if kind in NEW_ONLY:
        return True
    if kind == "sect" and (p.sect is not None or any(f.startswith("叛出:") for f in p.flags)):
        return True
    if kind == "title" and (p.title_book or (p.titles_worn or {}).get("id")):
        return True
    if kind == "codex" and p.codex is not None and p.codex.ended:
        return True
    if kind == "fuse" and p.fusion_book:
        return True
    if kind == "guard" and p.guard is not None and (len(p.guard.log) > 1 or p.guard.stage != "grow"):
        return True
    if kind == "jieyi_ok" and jieyi_base.brothers(ctx.content, ctx.world, p.name):
        return True
    finder = FIND.get(kind)
    return finder is not None and finder(ctx) is not None


def old_book(ctx) -> UnfoldBook:
    """舊角色那一本：碰過的記成出過，往後只出還沒碰過的。"""
    book = UnfoldBook(old=True)
    book.done = [k for k in ORDER if touched(ctx, k)]
    return book


def _later_until(ctx, book: UnfoldBook, kind: str) -> float | None:
    for x in book.later:
        k, _, t = x.partition("@")
        if k == kind:
            try:
                return float(t) + ctx.content.config.unfold.later_hours * 3600
            except ValueError:
                return None
    return None


def look(ctx, book: UnfoldBook) -> None:
    """沒有攤著的卡、也沒在帶的時候，挑下一張成立、還沒出過的攤上去（記成出過）。帶著的那一件照身上的東西往下走一步。"""
    if book.lead:
        step(ctx, book)
    if book.card or book.lead:
        return
    for kind in ORDER:
        if kind == "buy":
            hit = _bought(ctx, book.done) if not book.old else None
            if hit is not None:
                book.done.append(f"buy:{hit[0]}")
                book.card = f"buy|{hit[0]}|{hit[1]}"
                return
            continue
        if kind in book.done or (book.old and kind in NEW_ONLY):
            continue
        if kind == "jieyi_ok" and "jieyi" not in book.done:  # 邀過人才有這一張（舊角色開本時就結義了的記成出過）
            continue
        until = _later_until(ctx, book, kind)
        if until is not None and ctx.now < until:  # 按過一次改天：隔一陣子再碰到才再出
            continue
        hit = FIND[kind](ctx)
        if hit is not None:
            book.done.append(kind)
            book.card = f"{kind}|{hit[0]}|{hit[1]}"
            return


def close(ctx, book: UnfoldBook | None) -> None:
    """按了「改天」：收起這一張；見面禮那一張這一下入帳。第一次改天的隔 later_hours 再碰到還會出一次，第二次就不出了。"""
    if book is None or not book.card:
        return
    kind = book.card.split("|", 1)[0]
    if kind == "gift":
        give_gift(ctx)
    elif kind in FIND and kind not in NEW_ONLY and not any(x.partition("@")[0] == kind for x in book.later):
        book.later.append(f"{kind}@{int(ctx.now)}")
        if kind in book.done:
            book.done.remove(kind)
    book.card = ""


# ── 帶著做一次（Joy 2026-11-26「照建議」；設計稿 https://claude.ai/artifact/JGmeBcjLtjU1HWPYjhfwkD）──────────────
# 卡上的鈕按下去不再只帶過去就放手：照這張表一步一步走，畫面上下一步要按的那一顆亮一圈墨暈（web/unfold.js 的 UF_STEPS 認是哪一顆），
# 底下一條「說話的人＋一句＋改天」，走到 end 落一個印、按「好」才收。哪一步做完了：身上看得出來的由這裡照存檔判（STATE_STEPS），
# 看不出來的（寄出一封信、讀了結局、翻到圖鑑）由網頁做完那一下回報（/api/unfold/lead）。
# 待 joy 潤：每一步的一句話（end 那一句是做成了的那一刻）
STEPS: dict[str, tuple[tuple[str, str], ...]] = {
    "sect": (("join", "「想留下，就在這兒拜一拜。」"), ("learn", "「入了門，先學這一式。」"), ("end", "「往後師兄弟寫的招，都在這本譜裡。」")),
    "mail": (("write", "挑一句開頭，寄出去。"), ("end", "信寄出去了。他回了，信匣會亮。")),
    "jieyi": (("invite", "在他的名帖上，邀他結義。"), ("end", "帖子遞出去了，等他回話。")),
    "title": (("end", "往後有人翻你的名帖，就看得到這一枚。"),),
    "guard": (("pick", "他在等你開口。"), ("end", "他記住了。")),
    "codex": (("read", "翻到結局那一頁。"), ("gallery", "這一路見過的人，也記下了。"), ("end", "往後走過的，都記在這本錄裡。")),
    "fuse": (("fire", "兩股意都在爐裡了。開爐看看。"), ("end", "合出來的，往後也能再拿去合。")),
}
WEB_STEPS = frozenset({("mail", "write"), ("codex", "read"), ("codex", "gallery")})  # 存檔看不出來、由網頁回報的
LEAD_WHO = {"sect": "{x}的門人", "mail": "{x}的名帖", "jieyi": "{x}", "title": "一枚剛蓋下的印", "guard": "{x}", "codex": "江湖錄", "fuse": "爐火"}


def _parse(lead: str) -> tuple[str, str, str, str]:
    kind, arg, stp, base = (lead.split("|", 3) + ["", "", "", ""])[:4]
    return kind, arg, stp, base


def _next(kind: str, stp: str) -> str:
    names = [n for n, _ in STEPS.get(kind, ())]
    return names[names.index(stp) + 1] if stp in names and names.index(stp) + 1 < len(names) else "end"


def _first_art(ctx, sect_id: str) -> str | None:
    return next((k for k, s in ctx.content.skills.items() if s.learn is not None and s.learn.sect == sect_id), None)  # 同 zongmen.rules.first_art


def _step_done(ctx, kind: str, arg: str, stp: str, base: str) -> bool:
    """存檔看得出來的那幾步：做完了沒。"""
    p = ctx.state.player
    if kind == "sect" and stp == "join":
        return p.sect == arg
    if kind == "sect" and stp == "learn":
        art = _first_art(ctx, arg)
        return art is None or art in library.owned_arts(ctx.state)
    if kind == "jieyi" and stp == "invite":
        bk = jieyi_base.book(ctx.world)
        return bk is not None and any(o.sender == p.name and o.target == arg for o in bk.offers) or bool(
            jieyi_base.brothers(ctx.content, ctx.world, p.name))
    if kind == "guard" and stp == "pick":
        kid = p.guard
        return kid is None or kid.event is None or str(kid.event.seq) != base
    if kind == "fuse" and stp == "fire":
        return bool(p.fusion_book) or str(len(p.insights)) != base
    return False


def start(ctx, book: UnfoldBook) -> None:
    """卡上的鈕按下去：收起卡，有帶法的開始帶（第一步）。"""
    if not book.card:
        return
    kind, arg, _name = (book.card.split("|", 2) + ["", ""])[:3]
    book.card = ""
    if kind == "gift":
        give_gift(ctx)
    if kind not in STEPS:
        return
    base = ""
    if kind == "guard":
        base = arg
    elif kind == "fuse":
        base = str(len(ctx.state.player.insights))
    book.lead = f"{kind}|{arg}|{STEPS[kind][0][0]}|{base}"
    step(ctx, book)


def _advanced(ctx, lead: str) -> str:
    """存檔看得出來的那一步做完了，往下一步（可能一次走好幾步）；回走完之後的那一串。"""
    for _ in range(4):
        kind, arg, stp, base = _parse(lead)
        if kind not in STEPS or stp == "end" or (kind, stp) in WEB_STEPS or not _step_done(ctx, kind, arg, stp, base):
            break
        lead = f"{kind}|{arg}|{_next(kind, stp)}|{base}"
    return lead


def step(ctx, book: UnfoldBook) -> None:
    book.lead = _advanced(ctx, book.lead)


def report(ctx, book: UnfoldBook | None, kind: str, stp: str) -> None:
    """網頁回報「這一步做完了」：只認此刻正帶到的那一步、而且是網頁回報的那幾步；end 是按了「好」，收起。"""
    if book is None or not book.lead:
        return
    book.lead = _advanced(ctx, book.lead)  # 存檔看得出來的先走到（畫面上看到的那一步）
    k, arg, now_step, base = _parse(book.lead)
    if k != kind or now_step != stp:
        return
    if stp == "end":
        book.lead = ""
    elif (k, stp) in WEB_STEPS:
        book.lead = f"{k}|{arg}|{_next(k, stp)}|{base}"


def stop(book: UnfoldBook | None) -> None:
    """帶到一半按「改天」：不帶了（那一件已經出過，不再出）。"""
    if book is not None:
        book.lead = ""


def lead_view(ctx, book: UnfoldBook) -> dict | None:
    if not book.lead:
        return None
    kind, arg, stp, _base = _parse(_advanced(ctx, book.lead))  # 不經同步的動作（煉製頁開爐）回來的畫面也照身上的東西算到哪一步；下一次同步才寫回本子
    if kind not in STEPS:
        return None
    say = dict(STEPS[kind]).get(stp, "")
    x = arg
    if kind == "sect":
        x = ctx.content.sects[arg].name if arg in ctx.content.sects else arg
    elif kind == "guard":
        kid = ctx.state.player.guard
        x = kid.name if kid is not None else ""
    out = {"kind": kind, "arg": arg, "step": stp, "who": LEAD_WHO[kind].format(x=x), "say": say, "end": stp == "end"}
    if kind == "sect":
        art = _first_art(ctx, arg)
        out["learn"] = f"learn:{art}" if art else ""
    if kind == "title":
        out["seal"] = (ctx.state.player.titles_worn or {}).get("name", "")
    return out




def view(book: UnfoldBook, gift: int = 0) -> dict | None:
    """網頁畫卡要的：種類、對象、說話的、那一句、鈕上的字。"""
    if not book.card:
        return None
    kind, arg, name = (book.card.split("|", 2) + ["", ""])[:3]
    if kind == "buy":
        if arg not in BUY_SAY:
            return None
        return {"kind": kind, "arg": arg, "who": name, "say": BUY_SAY[arg], "go": BUY_GO[arg], "later": LATER}
    if kind not in SAY:
        return None
    x = name or arg
    return {"kind": kind, "arg": arg, "who": WHO[kind].format(x=x), "say": SAY[kind].format(x=x, n=gift), "go": GO[kind], "later": LATER}
