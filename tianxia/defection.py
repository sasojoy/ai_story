"""叛投（第一季設計 5.1、傳聞分層設計第五節；計畫 2026-10-06-第一季正式版-甲-叛投）。

已經投靠的人，在別的陣營的投靠點改投：一季最多一次，身份歸零，舊陣營的個人進度帶不走、部下全部離隊；
新、舊兩個陣營的軍情各一則（寫名字），當地一則地方傳聞（可以匿名）。只有第一季的規則開著才有。"""
from __future__ import annotations

from . import ranks
from .models import Content, FactionDef
from .rules import add_rumor, display_name, season_one
from .state import GameState, PlayerState


def _faction(content: Content, faction_id: str) -> FactionDef:
    return next(f for f in content.scenario.factions if f.id == faction_id)


def can_defect(state: GameState, content: Content) -> bool:
    """這一季還能叛投嗎：第一季的規則開著、已經投靠、這一季還沒叛投過。"""
    p = state.player
    return season_one(content, state.world) and p.faction is not None and not p.defected


def targets_here(state: GameState, content: Content) -> list[FactionDef]:
    """所在地點是哪些別的陣營的投靠點（照劇本的陣營順序）；不能叛投時是空的。"""
    if not can_defect(state, content):
        return []
    p = state.player
    return [f for f in content.scenario.factions if f.id != p.faction and p.location in f.join_at]


def prompt(state: GameState, content: Content, target: FactionDef, counts_text: str) -> str:
    """確認畫面的話：寫明代價（頭銜、部下、功勞）、一季一次，接上三方目前的人數。"""
    p = state.player
    old = _faction(content, p.faction)
    title = ranks.title(content, state)
    lost = [f"身份歸零（你現在是{title}）" if title else "身份歸零"]
    if p.followers:
        lost.append(f"{len(p.followers)} 名部下全部離隊")
    lost.append(f"這一季替{old.name}記下的功勞全部作廢")
    return f"叛投{target.name}之後，" + "，".join(lost) + f"；一季只能叛投一次。{counts_text}。確定叛投{target.name}？"


def clear_progress(p: PlayerState) -> None:
    """叛投時清掉舊陣營的個人進度（第一季設計 5.1；晉升奇遇文件第一節：取消還沒去的召見；軍備物資 4.5：donations 歸零）。
    之後的計畫把自己的陣營進度加在這裡（乙：機緣；丙：靠山；丁：第四階資格），叛投就不會漏清。"""
    p.rank = 0
    p.summons = None
    p.followers = []
    p.contrib = 0
    p.contrib_weeks = {}
    p.donations = {}
    p.convoy = None  # 押著的糧車留給舊陣營，交出去的糧草不退【預設】


def defect(state: GameState, content: Content, target: FactionDef) -> list[str]:
    """真的叛投：離開舊陣營的門派、清掉舊陣營的進度、改投、記下這一季叛投過、退出舊陣營的活躍名單，發三則傳聞。
    呼叫端（Game._defect_step）先確認過還在投靠點、還能叛投。"""
    p, w = state.player, state.world
    old = _faction(content, p.faction)
    msgs = [target.defect_text] if target.defect_text else []
    sect = content.sects.get(p.sect) if p.sect else None
    if sect is not None and sect.id in old.sects:  # 拜入門派等於加入陣營（第一季設計 5.1）：叛投就一起離開
        p.flags.add(f"叛出:{sect.id}")
        p.sect = None
        msgs.append(f"你也就此離開了{sect.name}。")
    clear_progress(p)
    p.faction, p.defected = target.id, True
    names = w.active_pushers.get(old.id)
    if names is not None:  # 舊陣營的人數緩衝不再算他；新陣營等他下次推大勢才算（Game.push_trend）
        names.pop(p.name, None)
        if not names:
            del w.active_pushers[old.id]
    name = display_name(state)
    here = content.locations[p.location].name
    add_rumor(state, f"{name}叛離了{old.name}，投奔{target.name}。", p.location, content=content,
              layer="faction", faction=old.id)
    add_rumor(state, f"{name}從{old.name}投奔過來了。", p.location, content=content, layer="faction", faction=target.id)
    add_rumor(state, f"{name}在{here}改投了{target.name}。", p.location, content=content, layer="local",
              named=not p.anonymous)
    msgs.append(f"你叛出{old.name}，投了{target.name}。")
    return msgs
