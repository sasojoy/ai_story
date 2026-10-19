"""叛投（第一季設計 5.1、傳聞分層設計第五節；計畫 2026-10-06-第一季正式版-甲-叛投）。

已經投靠的人，在別的陣營的投靠點改投：一季最多一次，身份歸零，舊陣營的個人進度帶不走、部下全部離隊；
新、舊兩個陣營的軍情各一則（寫名字），當地一則地方傳聞（可以匿名）。
不看第一季的開關（企劃者 2026-10-08：開關打開之前就開著的那一季也要能轉陣營）：劇本有陣營就有。
章關著的那一季，舊陣營進度裡第一季才有的那幾樣（晉升、席次、機緣、密謀、軍令貢獻）本來就是空的，清掉也沒事；
陣營軍情那一層在那一季沒地方顯示，照記不畫。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import allied, bounties, opportunities, ranks, roster, seats
from .models import Content, FactionDef, Sect
from .rules import add_rumor, display_name
from .state import GameState, PlayerState

if TYPE_CHECKING:
    from .battle_instance import BattleInstance


def enlisted(battle: BattleInstance | None, name: str) -> bool:
    """名字還在一場沒打完的決戰的參戰名單上（集結中或開打中；出局的、離開大區的也算，名字還在陣上）。
    參戰者的陣營是加入那一刻記下的，叛投不會跟著改：讓他叛投，就會留在舊陣營那一邊打到底，
    叛去不在交戰雙方的陣營甚至會拿到舊陣營的戰鬥選單（最終審查 Important 1）。所以還在名單上就不能叛投。"""
    return battle is not None and battle.phase != "ended" and name in battle.participants


def can_defect(state: GameState, content: Content, battle: BattleInstance | None = None) -> bool:
    """這一季還能叛投嗎：劇本有陣營、已經投靠、這一季還沒叛投過、名字不在沒打完的決戰的參戰名單上。
    battle 是目前全服的那一場決戰（Game 傳 world.get_battle()；這個模組不碰全服狀態），沒有決戰就不傳。"""
    p = state.player
    return bool(content.scenario.factions) and p.faction is not None and not p.defected \
        and not enlisted(battle, p.name)


def targets_here(state: GameState, content: Content, battle: BattleInstance | None = None) -> list[FactionDef]:
    """所在地點是哪些別的陣營的投靠點（照劇本的陣營順序）；不能叛投時是空的。"""
    if not can_defect(state, content, battle):
        return []
    p = state.player
    return [f for f in content.scenario.factions if f.id != p.faction and p.location in f.join_at]


def _slot(state: GameState, content: Content) -> tuple[str | None, str | None]:
    """（陣營, 依附的那一軍）：豪強分屬兩軍的季，換依附的一邊也是換一個槽。"""
    p = state.player
    return p.faction, (p.ally if allied.on(content, state.world) else None)


def slots_here(
    state: GameState, content: Content, battle: BattleInstance | None = None,
) -> list[tuple[FactionDef, str | None]]:
    """這裡能叛投去的「陣營＋依附哪一軍」（照劇本的陣營順序）：規則同 targets_here。豪強分屬兩軍的季（企劃者 2026-10-15 第 2 題甲），
    要依附的陣營（豪強）的投靠點每一軍一個槽，自己現在的那一個不算——換依附的一邊、豪強與同一邊的純兩軍互換都是叛投。"""
    if not allied.on(content, state.world):
        return [(f, None) for f in targets_here(state, content, battle)]
    if not can_defect(state, content, battle):
        return []
    here = [f for f in content.scenario.factions if state.player.location in f.join_at]
    mine = _slot(state, content)
    out: list[tuple[FactionDef, str | None]] = []
    for f in here:
        for ally in [a.id for a in allied.allies_of(content, f.id)] or [None]:
            if (f.id, ally) != mine:
                out.append((f, ally))
    return out


def slot_label(state: GameState, content: Content, target: FactionDef, ally: str | None) -> str:
    """叛投鈕上的字（新寫）：同一個陣營換一軍是「改依附X」、換到同一邊是「改投X」，其餘是「叛投X」（豪強寫「地方豪強（依附官軍）」）。
    開關關著時一律「叛投X」，一個字都不變。"""
    faction, mine_ally = _slot(state, content)
    if target.id == faction and ally is not None:
        return f"改依附{content.scenario.faction_name(ally, ally)}"
    same_side = (ally or target.id) == (mine_ally or faction)
    return f"{'改投' if same_side else '叛投'}{allied.label(content, target.id, ally)}"


def refusal(
    state: GameState, content: Content, target: FactionDef, battle: BattleInstance | None = None, ally: str | None = None,
) -> str | None:
    """現在不能叛投去 target（豪強分屬兩軍：依附 ally）的原因（一句話，不含括號）；可以就是 None。跟 slots_here 同一套規則
    （這個槽在 slots_here 裡 ⇔ 這裡是 None），確認畫面按「確定」時用它再驗一次，並把真正的原因說給玩家聽。"""
    p = state.player
    if not content.scenario.factions or p.faction is None:
        return "現在不能叛投。"
    if p.defected:
        return "這一季你已經叛投過一次了。"
    if enlisted(battle, p.name):
        return f"決戰還沒打完，你名字還在{content.scenario.faction(p.faction).name}的陣上，打完再說。"
    if (target.id, ally) == _slot(state, content) or p.location not in target.join_at:
        return "你已經不在叛投的地方了。"
    return None


def _sect_left(p: PlayerState, old: FactionDef, content: Content) -> Sect | None:
    """叛投時會一起離開的門派：玩家拜的是舊陣營的門派（拜入門派等於加入陣營，第一季設計 5.1）；不是就沒有。"""
    sect = content.sects.get(p.sect) if p.sect else None
    return sect if sect is not None and sect.id in old.sects else None


def prompt(
    state: GameState, content: Content, target: FactionDef, counts_text: str, ally: str | None = None, companions: list[str] | None = None,
) -> str:
    """確認畫面的話：寫明真的會失去什麼（晉升過的頭銜、還沒去的召見、部下、押著的糧車、要離開的門派、功勞、手上揭著的舊陣營懸賞）、一季一次，
    接上三方目前的人數。只寫真的有的：第 1 階（鄉勇）叛投之後在新陣營一樣是第 1 階，不算損失；沒有召見、糧車、部下、
    門派、功勞、懸賞就不提；什麼都沒有的人，話說「沒有什麼進度要作廢」。"""
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
    held = bounties.stranded(state, content, ally or target.id)
    if held:  # 手上揭著的懸賞（FB-151）：新陣營的人接不了舊陣營掛的單，確定的那一下 defect() 拿掉名字
        lost.append(bounties.STRANDED_LOST.format(n=len(held), faction=old.name))
    if companions:  # 歷史武將同行 9.5：寫了 side、跟新陣營不合的同伴帶不走（Game._leave_behind 放回江湖）；名字由呼叫端給（要查全服名冊）
        lost.append(roster.DEFECT_LOST.format(names="、".join(companions)))
    verb = slot_label(state, content, target, ally)  # 「叛投官軍」；豪強分屬兩軍時也可能是「改投官軍」「改依附黃巾軍」
    head = f"{verb}之後，" + "，".join(lost) if lost else f"{verb}沒有什麼進度要作廢"
    return f"{head}；一季只能叛投一次。{counts_text}。確定{verb}？"


def clear_progress(p: PlayerState) -> None:
    """叛投時清掉舊陣營的個人進度（第一季設計 5.1；晉升奇遇文件第一節：取消還沒去的召見；軍備物資 4.5：donations 歸零）。
    之後的計畫把自己的陣營進度加在這裡（乙一：機緣已加；乙二：靠山隨機緣清；丙一：第 4 階資格與說過的「只缺一個機會」已加），叛投就不會漏清。
    這裡只放玩家**個人**的進度（PlayerState 上的欄位）；全服狀態那一側的清理（活躍名單、第四階席次的帳與名單）寫在 defect() 裡，
    跟 active_pushers 的清理放在一起。
    刻意沒清的：`runic_pieces`（符文殘片，丙二）、聽過的伏筆片段（`fragments`）與聽過的機緣線索（`opp_clues`，企劃者裁決 E5.2）
    ——它們是「知道的事」、不是陣營給的身份，跟伏筆物品一樣留著。殘片與片段當初是現在的做法、待企劃者確認（在 PM 那裡）；
    tests/test_promotions_huang.py 的 test_defecting_keeps_the_runic_pieces_for_now 釘著它，改了就改那個測試。"""
    p.rank = 0
    p.summons = None
    p.qualified, p.rank_hinted = False, []  # 第 4 階資格（候缺）與說過的「只缺一個機會」（正式版丙一）
    p.summons_stall = ""  # 說過的「沒有人能引見」（企劃者裁決 E3）：換了陣營，卡住了照新陣營再說
    p.followers = []
    p.follower_drill = []  # 傳功給部下的跟著部下一起走（Config.chuangong）
    p.contrib = 0
    p.contrib_weeks = {}
    p.donations = {}
    p.convoy = None  # 押著的糧車留給舊陣營，交出去的糧草不退【預設】
    # 舊陣營的引薦人排著還沒說的提示作廢（新手引導計畫三，N7）：換了邊之後由新的引薦人說；師父的（by 是空的）不動
    p.hint_queue = [n for n in p.hint_queue if p.faction is None or n.by != p.faction]
    opportunities.clear(p)  # 機緣的完成、計數、物品全部作廢（機緣文件第一節；正式版乙一）；聽過的線索留著（裁決 E5.2）


def defect(state: GameState, content: Content, target: FactionDef, ally: str | None = None) -> list[str]:
    """真的叛投：離開舊陣營的門派、讓出舊陣營的第四階席次（帳與這一週的名單，seats.leave）、清掉舊陣營的進度、改投、
    記下這一季叛投過、退出舊陣營的活躍名單，發三則傳聞，手上新陣營接不了的懸賞拿掉名字（bounties.drop_stranded，FB-151）。
    呼叫端（Game._defect_step）先確認過還在投靠點、還能叛投。
    豪強分屬兩軍的季（企劃者 2026-10-15 第 2 題甲）：ally 是新的依附；名字照 allied.label 寫（「地方豪強（依附官軍）」），
    活躍名單照那一邊清；換到同一邊（例：依附官軍的豪強改投官軍）只發一則那一邊的軍情「某某從甲改投乙」（新寫）。
    開關關著時 ally 是 None、舊與新一定不同邊，句子一字不變。"""
    p, w = state.player, state.world
    old = content.scenario.faction(p.faction)
    old_side = allied.side_of(state, content)
    old_name = allied.label_of(state, content)
    msgs = [target.defect_text] if target.defect_text else []
    sect = _sect_left(p, old, content)
    if sect is not None and target.id != old.id:  # 拜入門派等於加入陣營（第一季設計 5.1）：叛投就一起離開（只換依附的一邊不離開）
        p.flags.add(f"叛出:{sect.id}")
        p.sect = None
        msgs.append(f"你也就此離開了{sect.name}。")
    # 第四階席次的帳與這一週的名單：在任的人讓出缺、候缺的人不再排進去（正式版丁）。leave 只讀名號與舊陣營的 id，
    # 排在 clear_progress 前後、改投前後結果都一樣；放這裡是因為舊陣營的 id 在這一段都還拿得到
    seats.leave(state, old.id)
    clear_progress(p)
    opportunities.leave_plots(state)  # 還開著的集體密謀退出，做過的那幾處不再算（乙二；企劃者 2026-10-06 裁決）；全服的那一份在 state.world
    p.faction, p.ally, p.defected = target.id, ally, True
    new_side = ally or target.id
    new_name = allied.label(content, target.id, ally)
    names = w.active_pushers.get(old_side)
    if names is not None:  # 舊陣營的人數緩衝不再算他；新陣營等他下次推大勢才算（Game.push_trend）
        names.pop(p.name, None)
        if not names:
            del w.active_pushers[old_side]
    # 企劃者定：只有地方傳聞匿名；陣營軍情（只給那個陣營自己人看）一律寫真名，也不帶地點（同 orders、ranks 的陣營軍情）
    if new_side == old_side:  # 同一邊換身分（豪強分屬兩軍）：那一邊的人看到「改投」
        add_rumor(state, f"{p.name}從{old_name}改投{new_name}。", layer="faction", faction=new_side)
    else:
        add_rumor(state, f"{p.name}叛離了{old_name}，投奔{new_name}。", layer="faction", faction=old_side)
        add_rumor(state, f"{p.name}從{old_name}投奔過來了。", layer="faction", faction=new_side)
    here = content.locations[p.location].name
    add_rumor(state, f"{display_name(state)}在{here}改投了{new_name}。", p.location, content=content, layer="local",
              named=not p.anonymous)
    msgs.append(f"你叛出{old_name}，投了{new_name}。" if new_side != old_side or target.id != old.id
                else f"你改依附{content.scenario.faction_name(ally, ally)}。")
    msgs += bounties.drop_stranded(state, content, new_side)  # 手上舊陣營掛的懸賞作廢、每張一句（FB-151）；改的是共用的季，Game.choose 結尾統一存
    return msgs
