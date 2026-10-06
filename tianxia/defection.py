"""叛投（第一季設計 5.1、傳聞分層設計第五節；計畫 2026-10-06-第一季正式版-甲-叛投）。

已經投靠的人，在別的陣營的投靠點改投：一季最多一次，身份歸零，舊陣營的個人進度帶不走、部下全部離隊；
新、舊兩個陣營的軍情各一則（寫名字），當地一則地方傳聞（可以匿名）。只有第一季的規則開著才有。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import opportunities, ranks
from .models import Content, FactionDef, Sect
from .rules import add_rumor, display_name, season_one
from .state import GameState, PlayerState

if TYPE_CHECKING:
    from .battle_instance import BattleInstance


def enlisted(battle: BattleInstance | None, name: str) -> bool:
    """名字還在一場沒打完的決戰的參戰名單上（集結中或開打中；出局的、離開大區的也算，名字還在陣上）。
    參戰者的陣營是加入那一刻記下的，叛投不會跟著改：讓他叛投，就會留在舊陣營那一邊打到底，
    叛去不在交戰雙方的陣營甚至會拿到舊陣營的戰鬥選單（最終審查 Important 1）。所以還在名單上就不能叛投。"""
    return battle is not None and battle.phase != "ended" and name in battle.participants


def can_defect(state: GameState, content: Content, battle: BattleInstance | None = None) -> bool:
    """這一季還能叛投嗎：第一季的規則開著、已經投靠、這一季還沒叛投過、名字不在沒打完的決戰的參戰名單上。
    battle 是目前全服的那一場決戰（Game 傳 world.get_battle()；這個模組不碰全服狀態），沒有決戰就不傳。"""
    p = state.player
    return season_one(content, state.world) and p.faction is not None and not p.defected \
        and not enlisted(battle, p.name)


def targets_here(state: GameState, content: Content, battle: BattleInstance | None = None) -> list[FactionDef]:
    """所在地點是哪些別的陣營的投靠點（照劇本的陣營順序）；不能叛投時是空的。"""
    if not can_defect(state, content, battle):
        return []
    p = state.player
    return [f for f in content.scenario.factions if f.id != p.faction and p.location in f.join_at]


def refusal(state: GameState, content: Content, target: FactionDef, battle: BattleInstance | None = None) -> str | None:
    """現在不能叛投去 target 的原因（一句話，不含括號）；可以就是 None。跟 targets_here 同一套規則（target 在
    targets_here 裡 ⇔ 這裡是 None），確認畫面按「確定」時用它再驗一次，並把真正的原因說給玩家聽。"""
    p = state.player
    if not season_one(content, state.world) or p.faction is None:
        return "現在不能叛投。"
    if p.defected:
        return "這一季你已經叛投過一次了。"
    if enlisted(battle, p.name):
        return f"決戰還沒打完，你名字還在{content.scenario.faction(p.faction).name}的陣上，打完再說。"
    if target.id == p.faction or p.location not in target.join_at:
        return "你已經不在叛投的地方了。"
    return None


def _sect_left(p: PlayerState, old: FactionDef, content: Content) -> Sect | None:
    """叛投時會一起離開的門派：玩家拜的是舊陣營的門派（拜入門派等於加入陣營，第一季設計 5.1）；不是就沒有。"""
    sect = content.sects.get(p.sect) if p.sect else None
    return sect if sect is not None and sect.id in old.sects else None


def prompt(state: GameState, content: Content, target: FactionDef, counts_text: str) -> str:
    """確認畫面的話：寫明真的會失去什麼（晉升過的頭銜、還沒去的召見、部下、押著的糧車、要離開的門派、功勞）、一季一次，
    接上三方目前的人數。只寫真的有的：第 1 階（鄉勇）叛投之後在新陣營一樣是第 1 階，不算損失；沒有召見、糧車、部下、
    門派、功勞就不提；什麼都沒有的人，話說「沒有什麼進度要作廢」。"""
    p = state.player
    old = content.scenario.faction(p.faction)
    lost = []
    if ranks.rank_of(state) > 1:
        title = ranks.title(content, state)
        lost.append(f"身份歸零（你現在是{title}）" if title else "身份歸零")
    if p.summons is not None:
        lost.append("還沒去的召見作廢")
    if p.followers:
        lost.append(f"{len(p.followers)} 名部下全部離隊")
    if p.convoy is not None:
        lost.append("押著的糧車作廢、交出去的糧草不退")
    if opportunities.in_plot(state):  # 乙二：響應或牽頭、還沒收場也沒領的集體密謀（句子待 joy 潤）
        lost.append("響應的密謀作廢（你做的那幾處也不算）")
    sect = _sect_left(p, old, content)
    if sect is not None:  # 離開門派之後這一季拜不回去（叛出旗標，content/events/sects.json 的 flags_none）
        lost.append(f"離開{sect.name}、這一季拜不回去")
    if p.contrib > 0:
        lost.append(f"這一季替{old.name}記下的功勞全部作廢")
    head = f"叛投{target.name}之後，" + "，".join(lost) if lost else f"叛投{target.name}沒有什麼進度要作廢"
    return f"{head}；一季只能叛投一次。{counts_text}。確定叛投{target.name}？"


def clear_progress(p: PlayerState) -> None:
    """叛投時清掉舊陣營的個人進度（第一季設計 5.1；晉升奇遇文件第一節：取消還沒去的召見；軍備物資 4.5：donations 歸零）。
    之後的計畫把自己的陣營進度加在這裡（乙一：機緣已加；丙：靠山；丁：第四階資格），叛投就不會漏清。
    這裡只放玩家**個人**的進度（PlayerState 上的欄位）；全服狀態那一側的清理（例如活躍名單）寫在 defect() 裡，
    跟 active_pushers 的清理放在一起。"""
    p.rank = 0
    p.summons = None
    p.followers = []
    p.contrib = 0
    p.contrib_weeks = {}
    p.donations = {}
    p.convoy = None  # 押著的糧車留給舊陣營，交出去的糧草不退【預設】
    # 舊陣營的引薦人排著還沒說的提示作廢（新手引導計畫三，N7）：換了邊之後由新的引薦人說；師父的（by 是空的）不動
    p.hint_queue = [n for n in p.hint_queue if p.faction is None or n.by != p.faction]
    opportunities.clear(p)  # 機緣的完成、計數、物品、線索全部作廢（機緣文件第一節；正式版乙一）


def defect(state: GameState, content: Content, target: FactionDef) -> list[str]:
    """真的叛投：離開舊陣營的門派、清掉舊陣營的進度、改投、記下這一季叛投過、退出舊陣營的活躍名單，發三則傳聞。
    呼叫端（Game._defect_step）先確認過還在投靠點、還能叛投。"""
    p, w = state.player, state.world
    old = content.scenario.faction(p.faction)
    msgs = [target.defect_text] if target.defect_text else []
    sect = _sect_left(p, old, content)
    if sect is not None:  # 拜入門派等於加入陣營（第一季設計 5.1）：叛投就一起離開
        p.flags.add(f"叛出:{sect.id}")
        p.sect = None
        msgs.append(f"你也就此離開了{sect.name}。")
    clear_progress(p)
    opportunities.leave_plots(state)  # 還開著的集體密謀退出，做過的那幾處不再算（乙二；企劃者 2026-10-06 裁決）；全服的那一份在 state.world
    p.faction, p.defected = target.id, True
    names = w.active_pushers.get(old.id)
    if names is not None:  # 舊陣營的人數緩衝不再算他；新陣營等他下次推大勢才算（Game.push_trend）
        names.pop(p.name, None)
        if not names:
            del w.active_pushers[old.id]
    # 企劃者定：只有地方傳聞匿名；陣營軍情（只給那個陣營自己人看）一律寫真名，也不帶地點（同 orders、ranks 的陣營軍情）
    add_rumor(state, f"{p.name}叛離了{old.name}，投奔{target.name}。", layer="faction", faction=old.id)
    add_rumor(state, f"{p.name}從{old.name}投奔過來了。", layer="faction", faction=target.id)
    here = content.locations[p.location].name
    add_rumor(state, f"{display_name(state)}在{here}改投了{target.name}。", p.location, content=content, layer="local",
              named=not p.anonymous)
    msgs.append(f"你叛出{old.name}，投了{target.name}。")
    return msgs
