"""回來的理由：手機跳通知的五種事（減法季整合設計第十章，批 9）——來信、約戰、決戰集結、被截殺、被〈天下形勢〉提到。

這裡只認「這個人此刻身上有哪幾件值得叫他回來的事」，每一件一個穩定的 key；哪幾件已經跳過通知、什麼時候跳、跳給哪一台裝置，
是伺服器看守的事（server.py 的 notice_round、server_push.WebPush）。看守拿上一輪的 key 比，新冒出來的才跳。
純函式：只讀傳進來的存檔與決戰，不碰時鐘、不改任何東西。

- 來信：還沒看過的信（letters；開口求人的「條件」是自己當面談的，不算）；
- 約戰：出陣改約戰（批 3b）還沒做，DUEL_SOURCES 留給它登記——傳進 state、content，回 [Notice]；
- 決戰集結：全服決戰開始集結（攻城戰不算，那是第 4 階的人自己下的戰書）；
- 被截殺：江湖紀錄裡「遭某某截殺」那一則（Game._raid_record、_raid_fled 寫的；替被截的人寫，真人假人同一句）；
- 被〈天下形勢〉提到：最新一篇的文章或「是日」裡寫到你的名號。

通知的字只寫玩家本來就看得到的東西，跟畫面同一套話，看不出誰是假人。"""
from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel

from .models import Content
from .state import GameState

Kind = Literal["letter", "duel", "rally", "raid", "xingshi"]

# 待 joy 潤：通知的字（標題一律「天下大勢」，這裡是內文）
LETTER = "{who}派人送來一封信。"
RALLY = "{battle}開始集結，速來參戰。"
RAID = "{title}（{tag}）。"
RAID_BARE = "{title}。"
XINGSHI = "〈天下形勢〉第 {n} 篇提到了你。"


class Notice(BaseModel):
    key: str  # 同一件事每一輪都是同一個 key
    kind: Kind
    text: str


# 批 3b（出陣改約戰）在這裡登記約戰的通知：有人向你約戰、你約的戰有人應了……key 用 "duel:" 開頭
DUEL_SOURCES: list[Callable[[GameState, Content], list[Notice]]] = []


def _who(content: Content, cid: str) -> str:
    ch = content.characters.get(cid)
    return ch.name if ch is not None else cid


def current(state: GameState, content: Content, battle=None) -> list[Notice]:
    """這個人此刻的五種事。battle 是正在進行的那一場（WorldStore.get_battle()；沒有就 None）。"""
    p = state.player
    season = p.season_number
    out: list[Notice] = []
    for x in p.letters:
        if not x.read and not x.lapsed and x.kind != "條件":
            out.append(Notice(key=f"letter:{season}:{x.id}", kind="letter", text=LETTER.format(who=_who(content, x.sender))))
    for make in DUEL_SOURCES:
        out += make(state, content)
    if battle is not None and battle.siege is None and battle.phase == "muster" and not state.world.ended:
        definition = content.battles.get(battle.battle_id)
        name = definition.name if definition is not None else "決戰"
        out.append(Notice(key=f"rally:{battle.battle_id}:{battle.muster_deadline_real:.0f}", kind="rally", text=RALLY.format(battle=name)))
    for e in state.journal:
        if e.title.startswith("遭") and e.title.endswith("截殺"):
            text = RAID.format(title=e.title, tag=e.tag) if e.tag else RAID_BARE.format(title=e.title)
            out.append(Notice(key=f"raid:{season}:{e.time:.0f}:{e.title}", kind="raid", text=text))
    essay = state.world.xingshi[-1] if state.world.xingshi else None
    if essay is not None and p.name and (p.name in essay.essay or p.name in essay.line):
        out.append(Notice(key=f"xingshi:{season}:{essay.n}", kind="xingshi", text=XINGSHI.format(n=essay.n)))
    return out
