"""回來的理由：手機跳通知的五種事（減法季整合設計第十章，批 9）——來信、約戰、決戰集結、被截殺、被〈天下形勢〉提到。

這裡只認「這個人此刻身上有哪幾件值得叫他回來的事」，每一件一個穩定的 key；哪幾件已經跳過通知、什麼時候跳、跳給哪一台裝置，
是伺服器看守的事（server.py 的 notice_round、server_push.WebPush）。看守拿上一輪的 key 比，新冒出來的才跳。
純函式：只讀傳進來的存檔與決戰，不碰時鐘、不改任何東西。

- 來信：還沒看過的信（letters；開口求人的「條件」是自己當面談的，不算）；
- 約戰（批 3b 的出陣約戰，sortie_duel）：你這一區有對面貼了約戰、等人應戰；你貼的約戰有人應了（DUEL_SOURCES，傳進 state、content、全服的約戰）；
- 決戰集結：全服決戰開始集結（攻城戰不算，那是第 4 階的人自己下的戰書）；
- 被截殺：江湖紀錄裡「遭某某截殺」那一則（Game._raid_record、_raid_fled 寫的；替被截的人寫，真人假人同一句）；
- 被〈天下形勢〉提到：最新一篇的文章或「是日」裡寫到你的名號。

通知的字只寫玩家本來就看得到的東西，跟畫面同一套話，看不出誰是假人。"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Literal

from pydantic import BaseModel

from . import allied, atlas
from .characters import name_key
from .models import Content
from .state import GameState
from .world_state import SortieDuel

Kind = Literal["letter", "duel", "rally", "raid", "xingshi"]
KINDS: tuple[Kind, ...] = ("letter", "duel", "rally", "raid", "xingshi")  # 設定頁一種一個開關（PushStore.kinds_off），照這個順序排

# 待 joy 潤：通知的字（標題一律「天下大勢」，這裡是內文）
LETTER = "{who}派人送來一封信。"
RALLY = "{battle}開始集結，速來參戰。"
RAID = "{title}（{tag}）。"
RAID_BARE = "{title}。"
XINGSHI = "〈天下形勢〉第 {n} 篇提到了你。"
DUEL_OPEN = "{who}在{place}下了約戰，就在你這一區，等人應戰。"
DUEL_ANSWERED = "{who}應了你在{place}的約戰。"


class Notice(BaseModel):
    key: str  # 同一件事每一輪都是同一個 key
    kind: Kind
    text: str


def _duels(state: GameState, content: Content, sorties: Mapping[str, SortieDuel]) -> list[Notice]:
    """出陣約戰（批 3b）的兩件事：對面在你這一區貼的、還沒人應的約戰（你應得了的那一種：不是散人、不是同一邊、同一個大區）；
    你自己貼的約戰有人應了。名號照卡上寫的（真人、補位一樣）。"""
    p = state.player
    me = name_key(p.name) if p.name else ""
    side = allied.side_of(state, content)
    region = atlas.region_of(content, p.location) if p.location else None
    out: list[Notice] = []
    for duel in sorties.values():
        if duel.status == "open" and side is not None and duel.attacker.side != side and name_key(duel.attacker.name) != me \
                and (duel.region is None or (region is not None and region.id == duel.region)):
            out.append(Notice(key=f"duel:open:{duel.id}", kind="duel", text=DUEL_OPEN.format(who=duel.attacker.name, place=duel.place)))
        elif duel.status == "answered" and duel.defender is not None and name_key(duel.attacker.name) == me:
            out.append(Notice(key=f"duel:answered:{duel.id}", kind="duel",
                              text=DUEL_ANSWERED.format(who=duel.defender.name, place=duel.place)))
    return out


# 約戰的通知來源：(state, content, 全服的約戰 SharedWorldState.sorties) → [Notice]；key 用 "duel:" 開頭
DUEL_SOURCES: list[Callable[[GameState, Content, Mapping[str, SortieDuel]], list[Notice]]] = [_duels]


def _who(content: Content, cid: str) -> str:
    ch = content.characters.get(cid)
    return ch.name if ch is not None else cid


def current(state: GameState, content: Content, battle=None, sorties: Mapping[str, SortieDuel] | None = None) -> list[Notice]:
    """這個人此刻的五種事。battle 是正在進行的那一場（WorldStore.get_battle()；沒有就 None）；sorties 是全服的出陣約戰
    （WorldStore.sortie_duels()；沒有就不看約戰）。"""
    p = state.player
    season = p.season_number
    out: list[Notice] = []
    for x in p.letters:
        if not x.read and not x.lapsed and x.kind != "條件":
            out.append(Notice(key=f"letter:{season}:{x.id}", kind="letter", text=LETTER.format(who=_who(content, x.sender))))
    for make in DUEL_SOURCES:
        out += make(state, content, sorties or {})
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
