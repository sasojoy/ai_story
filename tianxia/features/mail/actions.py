"""帖友書信的動作（設計稿 https://claude.ai/artifact/FhMZSwH6aqNsrnNAwHBznn；Joy 2026-11-07「信能寫聯絡方式、網址嗎？不擋，其他按照建議」）。

- 誰能寫給誰：兩邊的名帖匣都收著對方那一張（名帖跨季，帖友也跨季）。不必在同一處、不必在線。
- 一封最多 Config.mail.max_chars 字；一天寄 per_day 封；對方沒回之前同一個人最多連寄 unanswered 封。不花錢、不給數值。
- 內容檢查跟挑釁、名帖自題同一套兩道擋（speech：字表＋鎖外的模型，kind LETTER；聯絡方式與網址不擋）。
- 沒有「已讀」：寄的人只看得到「已寄出」（假人永遠不讀信，有已讀就露餡）。假人不寄信、照樣收信。
- 不收他的信：他照常寄、照常看到「已寄出」，信不進你的信匣（store 的 dropped）；他不會知道。
- 檢舉一封：從你的信匣收起來，管理者看得到那一封（只看得到被檢舉的）；撤下（兩邊都看不到）、停他寄信幾天。
信存在資料庫旁邊的小檔（store.py），不進角色存檔：這裡讀寫的只有那個檔，角色存檔一個字不動。
"""
from __future__ import annotations

import math

from tianxia import speech, zh
from tianxia.characters import CharacterStore, name_key

from . import store as mail_store

# 待 joy 潤：寫給玩家看的字
NOT_FRIENDS = "要先跟{name}互換過名帖，才能寫信給他。"  # 待 joy 潤
NO_ONE = "（江湖上找不到「{name}」這個人。）"  # 待 joy 潤
SELF = "不能寫信給自己。"  # 待 joy 潤
EMPTY = "信上什麼都還沒寫。"  # 待 joy 潤
DAY_FULL = "今天已寄了 {n} 封信，明日 00:00 後再寫。"  # 待 joy 潤
WAIT_REPLY = "已經連寫了 {n} 封給{name}，等他回信再寫。"  # 待 joy 潤
MUTED = "你暫時不能寄信，約 {h} 小時後才能再寄。"  # 待 joy 潤
SENT = "信寄給{name}了。"  # 待 joy 潤
BLOCKED_ON = "不再收{name}的信了。他不會知道；要再收，到信匣底下解開。"  # 待 joy 潤
BLOCKED_OFF = "又收得到{name}的信了（不收的這段時間寄來的不會補給你）。"  # 待 joy 潤
REPORTED = "已檢舉。這一封從你的信匣收起來了，管理者會看。"  # 待 joy 潤
NO_LETTER = "（找不到這一封信。）"  # 待 joy 潤
CLOSED = "（書信暫時關著。）"  # 待 joy 潤


def store_of(ctx) -> mail_store.MailStore | None:
    """這個世界的信件小檔；測試用的記憶體世界沒有資料庫就是 None（書信不開）。"""
    db = getattr(ctx.world, "db", None)
    path = getattr(db, "path", None)
    return None if path is None else mail_store.for_db(path)


def on(ctx) -> bool:
    return bool(ctx.content.config.mail.enabled) and store_of(ctx) is not None


def clean(text: str) -> str:
    """玩家寫的信：每一行去掉頭尾空白、行內連續空白併成一個，空行最多連一行，轉繁體。"""
    lines = [" ".join(line.split()) for line in str(text or "").replace("\r\n", "\n").split("\n")]
    out: list[str] = []
    for line in lines:
        if line or (out and out[-1]):
            out.append(line)
    while out and not out[-1]:
        out.pop()
    return zh.to_traditional("\n".join(out))


def _me(ctx) -> str:
    return name_key(ctx.state.player.name)


def _in_box(state, name: str) -> bool:
    k = name_key(name)
    return any(name_key(x.name) == k for x in state.player.mingtie_box)


def _load(ctx, name: str):
    """別人那一份存檔（只讀，不補算時間）；沒有、讀不懂是 None。"""
    try:
        return CharacterStore(ctx.world.db).load(name)
    except Exception:  # noqa: BLE001  讀不懂的舊存檔：當作找不到
        return None


def _names(ctx) -> dict[str, str]:
    """名帖匣裡那幾位的 key → 名號（易名帖換名時名帖匣跟著換）。"""
    return {name_key(x.name): x.name for x in ctx.state.player.mingtie_box}


def _name_of(ctx, key: str, names: dict[str, str]) -> str:
    if key in names:
        return names[key]
    other = _load(ctx, key)
    return other.player.name if other is not None else key


def friends(ctx) -> list[str]:
    """帖友（名帖匣裡收著的那幾位，新的在前）；寫得成要對方的名帖匣也收著你，寄的那一下才查。"""
    seen, out = set(), []
    for x in reversed(ctx.state.player.mingtie_box):
        k = name_key(x.name)
        if k not in seen and k != _me(ctx):
            seen.add(k)
            out.append(x.name)
    return out


def left_today(ctx, box: mail_store.MailStore) -> int:
    return max(0, ctx.content.config.mail.per_day - box.sent_on(_me(ctx), ctx._pill_day()))


def mute_line(ctx, box: mail_store.MailStore) -> str | None:
    until = box.muted_until(_me(ctx), ctx.now)
    return None if until is None else MUTED.format(h=max(1, math.ceil((until - ctx.now) / 3600)))


def status(ctx) -> dict:
    """江湖畫面的 main.mail：信匣有幾封還沒看（見聞分頁的紅點）。關著沒有這一格。"""
    if not on(ctx):
        return {}
    return {"mail": {"unread": store_of(ctx).unread(_me(ctx))}}


def inbox(ctx) -> dict:
    """見聞「信匣」：一位帖友一行（最新那一封的開頭、他寄來還沒看的幾封），還沒寫過信的帖友，今天還能寄幾封，不收誰的信。"""
    if not on(ctx):
        return {"closed": True}
    box, me, names = store_of(ctx), _me(ctx), _names(ctx)
    rows = []
    for t in box.threads(me):
        last = t["last"]
        rows.append({"name": _name_of(ctx, t["other"], names), "peek": last["text"].replace("\n", " ")[:40], "mine": last["sender"] == me,
                     "stamp": last["stamp"], "season": last["season"], "unread": t["unread"]})
    talked = {name_key(r["name"]) for r in rows}
    return {
        "threads": rows,
        "friends": [n for n in friends(ctx) if name_key(n) not in talked],
        "blocked": [_name_of(ctx, k, names) for k in box.blocked(me)],
        "left": left_today(ctx, box),
        "max_chars": ctx.content.config.mail.max_chars,
        "muted": mute_line(ctx, box),
        "season": ctx.state.player.season_number,
    }


def thread(ctx, name: str, before: int = 0) -> dict:
    """跟一位帖友的往來（新的在前，一次 store.PAGE 封；before 是上一頁最舊那一封的 id）。打開就把他寄來的都記成看過。"""
    if not on(ctx):
        return {"closed": True}
    box, me = store_of(ctx), _me(ctx)
    other = name_key(name)
    rows, more = box.page(me, other, before or None)
    if not before:
        box.mark_read(me, other)
    names = _names(ctx)
    return {
        "name": _name_of(ctx, other, names),
        "letters": [{"id": r["id"], "mine": r["sender"] == me, "text": r["text"], "stamp": r["stamp"], "place": r["place"],
                     "season": r["season"]} for r in rows],
        "more": more,
        "blocked": box.blocks(me, other),
        "problem": write_problem(ctx, name),
        "left": left_today(ctx, box),
        "max_chars": ctx.content.config.mail.max_chars,
    }


def write_problem(ctx, name: str) -> str | None:
    """寫不寫得了這一封（不看內文）：關著、停寄、自己、不是帖友、今天寄滿、連寫太多封。行是 None。"""
    if not on(ctx):
        return CLOSED
    box, me, other = store_of(ctx), _me(ctx), name_key(name)
    muted = mute_line(ctx, box)
    if muted:
        return muted
    if other == me:
        return SELF
    if not _in_box(ctx.state, name):
        return NOT_FRIENDS.format(name=name)
    peer = _load(ctx, name)
    if peer is None:
        return NO_ONE.format(name=name)
    if not _in_box(peer, ctx.state.player.name):
        return NOT_FRIENDS.format(name=peer.player.name)
    cfg = ctx.content.config.mail
    if left_today(ctx, box) <= 0:
        return DAY_FULL.format(n=cfg.per_day)
    if box.unanswered(me, other) >= cfg.unanswered:
        return WAIT_REPLY.format(n=cfg.unanswered, name=peer.player.name)
    return None


def screen(ctx, name: str, text: str) -> bool:
    """三段式的 A 段：這一封值不值得在鎖外請模型審（寫得了、字表與字數擋不下）。"""
    return bool(text) and write_problem(ctx, name) is None and speech.word_problem(text, ctx.content, speech.LETTER, ctx.content.config.mail.max_chars) is None


def send(ctx, name: str, text: str, verdict: str = "") -> tuple[bool, str]:
    """C 段：再查一次寫不寫得了、字表、模型的判斷，寄出去。回傳（寄成了沒, 那一句）。收件人不收你的信時照樣說寄出去了。"""
    text = clean(text)
    problem = write_problem(ctx, name)
    if problem:
        return False, problem
    if not text:
        return False, EMPTY
    problem = speech.problem(text, ctx.content, speech.LETTER, ctx.content.config.mail.max_chars, verdict)
    if problem:
        return False, problem
    box, me, other = store_of(ctx), _me(ctx), name_key(name)
    p = ctx.state.player
    loc = ctx.content.locations.get(p.location)
    peer_name = _name_of(ctx, other, _names(ctx))
    box.add(season=p.season_number, at=ctx.now, day=ctx._pill_day(), stamp=ctx.stamp(ctx.state.world.time),
            place=loc.name if loc is not None else "", sender=me, recipient=other, text=text,
            dropped=box.blocks(other, me), keep=ctx.content.config.mail.keep_per_pair)
    return True, SENT.format(name=peer_name)


def set_block(ctx, name: str, value: bool) -> str:
    if not on(ctx):
        return CLOSED
    box, me, other = store_of(ctx), _me(ctx), name_key(name)
    if other == me:
        return SELF
    shown = _name_of(ctx, other, _names(ctx))
    if value:
        box.block(me, other)
        return BLOCKED_ON.format(name=shown)
    box.unblock(me, other)
    return BLOCKED_OFF.format(name=shown)


def report(ctx, lid: int) -> str:
    """檢舉寄給你的一封：收起來、記給管理者看。"""
    if not on(ctx):
        return CLOSED
    box, me = store_of(ctx), _me(ctx)
    letter = box.letter(lid)
    if letter is None or letter["recipient"] != me or letter["dropped"] or letter["removed"]:
        return NO_LETTER
    box.report(lid, me, ctx.now)
    return REPORTED


# ── 管理者（管理頁「書信檢舉」）──


def admin_reports(ctx) -> list[dict]:
    """被檢舉、還沒處理的信（同一封幾個人檢舉併成一筆）：誰寄給誰、寫了什麼、這個人現在停不停寄。只有被檢舉的看得到。"""
    if not ctx.is_admin() or not on(ctx):
        return []
    box = store_of(ctx)
    grouped: dict[int, dict] = {}
    for r in box.open_reports():
        letter = r["letter"]
        row = grouped.get(letter["id"])
        if row is None:
            sender = _load(ctx, letter["sender"])
            recipient = _load(ctx, letter["recipient"])
            sender_name = sender.player.name if sender is not None else letter["sender"]
            row = grouped[letter["id"]] = {
                "id": letter["id"], "sender": sender_name,
                "recipient": recipient.player.name if recipient is not None else letter["recipient"],
                "text": letter["text"], "stamp": letter["stamp"], "season": letter["season"], "count": 0, "removed": bool(letter["removed"]),
                "muted": box.muted_until(letter["sender"], ctx.now) is not None,
            }
        row["count"] += 1
    return list(grouped.values())


def admin_settle(ctx, lid: int, remove: bool) -> list[str]:
    if not ctx.is_admin():
        return ["（只有管理者能做。）"]
    box = store_of(ctx)
    if box is None or box.letter(lid) is None:
        return [NO_LETTER]
    n = box.settle(lid, remove=remove)
    return [f"這一封信撤下了（結了 {n} 筆檢舉），兩邊都看不到了。" if remove else f"這一封信看過沒事，檢舉清掉了（{n} 筆）。"]  # 待 joy 潤


def admin_mute(ctx, name: str, days: int) -> list[str]:
    """停他寄信 days 天（0 是解開）。天數只收 Config.mail.mute_days 那幾種。"""
    if not ctx.is_admin():
        return ["（只有管理者能做。）"]
    box = store_of(ctx)
    if box is None:
        return [CLOSED]
    target = _load(ctx, name)
    if target is None:
        return [NO_ONE.format(name=name)]
    key = name_key(target.player.name)
    if days <= 0:
        box.unmute(key)
        return [f"{target.player.name}又能寄信了。"]  # 待 joy 潤
    if days not in ctx.content.config.mail.mute_days:
        return [f"（停寄只能挑 {'、'.join(str(d) for d in ctx.content.config.mail.mute_days)} 天。）"]
    box.mute(key, ctx.now + days * 86400)
    return [f"{target.player.name}停寄信 {days} 天。"]  # 待 joy 潤
