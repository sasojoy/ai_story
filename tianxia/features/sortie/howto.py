"""出陣包：玩法說明自己那幾句（全部拆包第 59 批；原 tianxia/howto.py，字一個不動）：行動列底下遊歷、出陣、約戰那一行（train_line、sortie_line、
duel_line）、說明頁出陣那幾條（順序在核心 HOWTO_ORDER）。"""
from __future__ import annotations

from collections.abc import Sequence

from tianxia import conquest, rules, territory
from tianxia.models import Content
from tianxia.state import WorldState

from . import duel_rules as sortie_duel  # 出陣約戰（減法季批 3b）

PUSH_WORD = "推動戰局"  # 遊歷打贏、操練會推大勢（第一季是戰線，豪強照依附的那一邊）：一律這樣說，不露數字


def train_line(foes: bool, gains: Sequence[str], drops: bool, push: bool, drill_gains: Sequence[str], drills: bool) -> str:
    """遊歷打完會拿到什麼。foes：這裡有會打的對手（不是自己陣營的）；gains：打贏給的（銀兩、心得、經驗，照會打的對手有沒有
    這一項）；drops：打贏有機會掉素材；push：打贏或操練會推大勢（Game.train_trend_push 不是空的）；drill_gains：跟自己人操練
    給的（只有心得、經驗，照 Config.drill_reward_share 算出來不是 0 的）；drills：這裡也有自己陣營的隊伍。沒有會打的對手＝操練。
    沒有會打的對手時，行動列那一格本身就寫「操練」（出陣包 train_actions.train_option），這一行接在它後面：不再開頭寫一次「操練」（FB-101）。"""
    pushed = f"，{PUSH_WORD}" if push else ""
    if not foes:
        got = f"得{'、'.join(drill_gains)}" if drill_gains else "沒什麼賞"
        return f"不冒險：{got}{pushed}；不給銀兩、素材"
    got = f"打贏得{'、'.join(gains)}" if gains else "打贏沒什麼賞"
    return got + ("，可能掉素材" if drops else "") + pushed + ("；遇上自己人是操練" if drills else "")


SORTIE_NOTES = {  # 待 joy 潤：行動列底下出陣那一行（設計第二節）
    "attack": "這裡歸別人：打一場，打贏{push}；只拿對手 {share} 成的心得與經驗，{loot}",
    "hold": "這裡是自家地盤：不用打，{push}（量是攻的{half}）；拿自家隊伍 {share} 成的心得與經驗。",
    # 領地爭奪：自家的區塊守、推不動（沒人在推、剛易手、戰書凍結）：{push} 是 SORTIE_BLOCKED_HOLD，「量是攻的一半」寫在它的括號裡（裁決 21）
    "hold_idle": "這裡是自家地盤：不用打，{push}；拿自家隊伍 {share} 成的心得與經驗。",
    # 截糧週在自家佔著的截糧地點出陣是攻打運糧隊（FB-255）：地方是自己的，不寫「這裡歸別人」
    "convoy": "對面的運糧隊正打這裡經過：打一場，打贏{push}；只拿對手 {share} 成的心得與經驗，{loot}",
    # 領地爭奪：自家的大本營、廣宗（搶不下來的區塊）守，沒有進度可推、不記貢獻（FB-532，不接「量是攻的一半」）
    "home": "這裡是自家地盤，不在爭奪之列：不用打，也沒有進度可推；拿自家隊伍 {share} 成的心得與經驗。",
    # 領地爭奪：還沒人佔的中立地是攻，但不是「歸別人」（FB-533）
    "open": "這裡還沒有人佔：打一場，打贏{push}；只拿對手 {share} 成的心得與經驗，{loot}",
    # 領地爭奪：大本營、廣宗不在爭奪之列，只有截糧的運糧隊經過時打運糧隊（計畫第八章裁決 18）
    "convoy_out": "對面的運糧隊正打這裡經過：此地不在爭奪之列，打贏只算截糧、沒有進度可推；只拿對手 {share} 成的心得與經驗，{loot}",
}
SORTIE_LOOT = "不給銀兩、不掉東西。"
SORTIE_LOOT_SILVER = "銀兩也是 {silver} 成，不掉東西。"  # 素材與經濟設計第八節（Config.economy.sortie_silver）；待 joy 潤
SORTIE_PROGRESS = "推這一塊的進度、記貢獻"  # 領地爭奪：出陣不推線、推那一塊的進度（設計 3.7）；待 joy 潤
SORTIE_HOLD_PROGRESS = "把對面在這裡的進度拉回來、記貢獻"  # 領地爭奪：守把每一條都拉下（翻地與爭搶，輿圖簡化設計 4.1）；待 joy 潤
SORTIE_BLOCKED = "推不動進度（{why}）"  # 領地爭奪：推不動的原因照 conquest.push_problem（剛易手、戰書凍結、不相連、搶不下來）；待 joy 潤
# 自家的區塊守、推不動：那一句本來接「（量是攻的一半）」，兩個括號連在一起（計畫第八節裁決 21）——合成一個括號、意思不變。待 joy 潤
SORTIE_BLOCKED_HOLD = "推不動進度（{why}；有人來攻時守拉的量是攻的{half}）"
SORTIE_LEFT = "今日還能出陣 {n} 次。"


def sortie_line(how: str, left: int, content: Content, progress: bool = True, why: str | None = None) -> str:
    """出陣這一下會怎樣（Game._sortie_line 照規則算好傳進來）。數字讀 Config：給自己的成數、守是攻的幾成。
    progress：這一塊的進度推不推得動（conquest.push_problem）。why：推不動的原因（push_problem 的那一句），寫在 SORTIE_BLOCKED 的括號裡。自家的區塊守、推不動寫 SORTIE_NOTES["hold_idle"]＋
    SORTIE_BLOCKED_HOLD：一個括號（裁決 21）；這一塊被戰書凍結（原因是 conquest.FROZEN_WHY 的一句：已下戰書、集結中、開打中）時不接
    「有人來攻時…」——攻城已經排了，照實寫在哪一步就好（FB-552）。"""
    cfg = content.config
    half = "一半" if cfg.sortie.hold_share == 0.5 else f" {cfg.sortie.hold_share * 10:g} 成"
    if progress:
        pushed = SORTIE_HOLD_PROGRESS if how == "hold" else SORTIE_PROGRESS
    else:
        pushed = SORTIE_BLOCKED.format(why=why or conquest.WHY_OUT)
    if how == "hold" and progress is False:
        if why in conquest.FROZEN_WHY.values():
            how = "hold_idle"
        else:
            how, pushed = "hold_idle", SORTIE_BLOCKED_HOLD.format(why=why or conquest.WHY_IDLE, half=half)
    text = SORTIE_NOTES[how].format(push=pushed, share=f"{cfg.drill_reward_share * 10:g}", half=half,
                                    loot=sortie_loot(content))
    return text + SORTIE_LEFT.format(n=left)


def sortie_loot(content: Content) -> str:
    """出陣攻打贏給不給銀兩（素材與經濟設計第八節）：開著寫對手銀兩的幾成，關著照舊「不給銀兩、不掉東西」。"""
    econ = content.config.economy
    return SORTIE_LOOT_SILVER.format(silver=f"{econ.sortie_silver_share * 10:g}") if econ.sortie_silver else SORTIE_LOOT


# 減法季批 3b：約戰開著時行動列底下出陣那一行（Game._duel_line；整合設計 4.3）。待 joy 潤
DUEL_NOTES = {
    "go": "在這一塊貼約戰：封好三招，{window} 分鐘內對面同一區的人可以應戰，沒人應由對面趕來的人或守軍迎戰；"
          "贏了推這一塊的進度、記貢獻、拿戰利，輸了內傷加重、多等 {lose} 分。",
    "wait": "這裡是自家的地方，守不是一顆鈕：對面來約戰時在約戰卡上應戰（一天 {answers} 次，跟出陣分開算），守住了把對面的進度拉回來。",
    "blocked": "此刻貼不了約戰（{why}）。",
    "convoy": "這週截糧的運糧隊正打這裡經過：出陣就是去截糧，打一場，打贏算截糧（不推進度、不貼約戰）。",
}
DUEL_LEFT = "今日還能出陣 {n} 次、應戰 {answers} 次。"


def duel_line(content: Content, why: str | None, left: int, answers: int, convoy: bool = False) -> str:
    """約戰開著時出陣這一下會怎樣（Game._duel_line 照規則算好傳進來）：截糧、貼得了、自家的地方等對面來約、其他原因各一句，再接今天還能幾次。"""
    cfg = content.config.sortie
    key = "convoy" if convoy else "go" if why is None else "wait" if why == sortie_duel.WHY_WAIT else "blocked"
    text = DUEL_NOTES[key].format(window=f"{cfg.window_minutes:g}", lose=f"{cfg.lose_cooldown_minutes:g}", answers=cfg.answer_per_day,
                                  why=why or "")
    return text + DUEL_LEFT.format(n=left, answers=answers)


def duel_lines(content: Content) -> list[str]:
    """玩法說明「行動」裡出陣那一條的約戰版（減法季批 3b；整合設計 4.3；sortie_duel.on 的季取代 sortie_lines；待 joy 潤）。數字讀 Config.sortie。"""
    cfg = content.config.sortie
    reset = "台灣時間 00:00 換日" if content.config.pill_day_utc_offset_hours == 8 else "每天 00:00 換日"
    return [
        f"- **出陣**（約戰；體力 {cfg.jianfa_stamina}，每天 {cfg.jianfa_per_day} 次、兩次之間隔 {cfg.cooldown_minutes:g} 分，{reset}）："
        "投靠了陣營才有。站在推得動的那一塊（中立地或敵方的領地）按出陣、封好三招，就貼出一張約戰；"
        f"{cfg.window_minutes:g} 分鐘內對面站在同一個大區的人可以應戰（一天 {cfg.answer_per_day} 次，跟出陣分開算），先按的那一位是守方；"
        "同一邊的人可以同去（也算一次出陣），一起推、集火。窗滿就開打，不必守在畫面前，打完戰報送到。",
        "- **約戰怎麼打**：三回合，一回合一招——固守剋強攻、強攻剋奇襲、奇襲剋固守，撤退是這一回合認輸、少扣氣血。"
        "三勝大勝、兩勝勝、一勝或三回合全平僵持、零勝敗。攻方贏把攻方那一條往前推（大勝推得最多，僵持推一點），守方贏把攻方那一條拉回同樣的量；"
        f"兩邊照回合扣氣血，輸的另加內傷 {cfg.lose_injury:g}、下一次出陣與應戰多等 {cfg.lose_cooldown_minutes:g} 分，不碰銀兩。"
        "窗滿了沒人應戰，對面的人會趕來應戰；連人都沒有，由那裡的守軍迎戰。",
        "- 自家的地方不能出陣（守就是應戰）；巡哨、傳道、保境安民是此地的花樣，不推線、一天記一點貢獻。截糧的運糧隊經過時，出陣照舊是去截糧。",
    ]


def sortie_lines(content: Content, allied: bool = False, season: WorldState | None = None) -> list[str]:
    """玩法說明「行動」裡出陣那一條（出陣開著時取代遊歷；待 joy 潤）。數字讀 Config。
    allied：豪強分屬兩軍，豪強照依附那一邊攻守。出陣在每一塊領地都有、推的是那一塊的進度（待 joy 潤）。
    約戰開著的季（sortie_duel.on，減法季批 3b）換成 duel_lines。"""
    if sortie_duel.on(content, season):
        return duel_lines(content)
    cfg = content.config
    reset = "台灣時間 00:00 換日" if cfg.pill_day_utc_offset_hours == 8 else "每天 00:00 換日"
    half = "一半" if cfg.sortie.hold_share == 0.5 else f" {cfg.sortie.hold_share * 10:g} 成"
    gentry = "地方豪強照依附的那一邊攻守。" if allied else ""
    where = "官軍、黃巾的領地與中立地上都有（各家的大本營與廣宗不在爭奪之列，攻不得）"  # 裁決 18
    return [
        f"- **出陣**（體力 {cfg.action_cost['train']}，每天 {cfg.sortie.per_day} 次，{reset}）：投靠了陣營才有，{where}。"
        f"這裡歸別人或還沒人佔就打一場，打贏推那一塊的進度、記貢獻；歸自家就守，不用打；{gentry}"
        f"守推的量是攻的{half}。只拿對手 {cfg.drill_reward_share * 10:g} 成的心得與經驗，"  # 推進度沒有盡頭阻力（FB-533；待 joy 潤）
        + ("攻打贏" + sortie_loot(content) if cfg.economy.sortie_silver else sortie_loot(content)),
    ]


def sortie_section(content: Content, season: WorldState) -> list[str]:
    """玩法說明出陣那幾條（HOWTO_ORDER 的 sortie）：地盤開著寫 sortie_lines，關著寫遊歷。"""
    cfg = content.config
    cost = cfg.action_cost
    if territory.on(content):
        return sortie_lines(content, rules.haoqiang_allied(content, season), season)
    old_train = [  # 出陣關著時的遊歷（出陣開著時換成 sortie_lines）
        # 操練看的是遇上的隊伍（Game._drills_with），不是地方：兩種都有的地方 _train 隨機挑一路（審查 M2）
        f"- **遊歷**（體力 {cost['train']}）：只在有隊伍的地方出現。遇上對手一定開打，按鈕上寫勝算：打贏得銀兩、心得、經驗，"
        "可能掉素材；每一場都會扣些氣血，輸了還會掉銀兩。遇上自己陣營的隊伍是操練：不打、不會輸，"
        f"得對手 {cfg.drill_reward_share * 10:g} 成的心得與經驗，不給銀兩、素材。兩種都有的地方，遇上誰看運氣。"
        f"有些地方打贏或操練還會{PUSH_WORD}（行動列底下那一行寫著這裡、今天還推不推得動）。",  # 審查 M4：不是「多半」（SOME_PLACES），待 joy 潤
    ]
    return old_train
