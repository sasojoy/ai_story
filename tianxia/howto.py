"""玩法說明（explain-1，試玩回饋：Gary「很多東西要一句說明，不然體力用完了還不知道在玩什麼」）：

- 江湖頁行動列底下那幾行：探索、遊歷、交友這一下會怎樣（explore_line、train_line、social_line）；
- 狀態列體力條點開的說明（stamina_lines）與建角色時送回體丹的那一行（gift_line）；
- 江湖頁的戰況圖卡、態勢、大事、主線點開的說明（war_help，explain-2：這一季在打什麼、亂局、大事怎麼定、你能怎麼出力）；
- 設定抽屜的「玩法說明」（page，Markdown）。

這裡只把事實寫成字：比重、獎勵、推不推戰局由呼叫端照引擎真正的規則算好傳進來（Game._explore_weights、遊歷的對手、
Game.train_trend_push），數字一律讀 Config（或內容、規則模組的常數），句子裡不寫死任何數。不改狀態、不擲骰、不讀時鐘。
所有句子待 joy 潤。"""
from __future__ import annotations

from collections.abc import Sequence

from . import allied as allied_rules
from . import calendar, conquest, economy, equipment, explore_modes, figures, four_tiers, precise, renown, rules, seal, sortie, territory, timetable, training
from .features.mall import rules as mall  # 商城那一節（功能包；還沒搬的舊模組可以 import 包，開發規範手冊 3.11）
from . import sortie_duel  # 出陣約戰（減法季批 3b）：出陣那一行與玩法說明
from . import explore_one  # 減法季探索一顆（批 2）：行動列底下那一行用同一份兩個字的叫法
from .models import Content
from .rules import STANCE_NAMES  # 態勢卡上三方的叫法（官軍、黃巾、豪強）：說明跟卡上同一個叫法
from .state import GameState, WorldState

# 探索三選一的三支（models.EXPLORE_BRANCHES）在說明裡怎麼叫
BRANCH_WORDS: dict[str, str] = {"insight": "悟意境", "wild": "遇野怪", "event": "碰上事件"}
PUSH_WORD = "推動戰局"  # 遊歷打贏、操練會推大勢（第一季是戰線，豪強照依附的那一邊）：一律這樣說，不露數字


def explore_line(
    weights: Sequence[tuple[str, float]], legend: str | None = None, blocked: bool = False, until: str | None = None,
    later: bool = False,
) -> str:
    """探索這一下多半會怎樣。weights 是探索真的擲骰用的那一份（支, 比重）：照地點類型（Config.explore_mix）、
    做不了的已經拿掉、悟意境那一支乘過悟性（Game._explore_weights）。比重嚴格最大的那一支寫「多半」，其他寫「也可能」
    （照比重由大到小）；並列最大就一起寫「可能」；只剩一支寫「會」（FB-101）。不寫百分比。legend 是破境丹的名字（探索每次另擲一次撿不撿得到；
    機率是 0 時呼叫端給 None）。blocked：悟意境那一支只因為這個遊戲日在這裡選錯過做法才拿掉（Game._insight_blocked）；
    句尾補一句什麼時候才悟得出——until 是換日的那一刻（rules.day_turn，已經照季的時間寫法寫好），None 是這一季之內
    不會再換日；later：還會換日、只是季末延後了寫不出那一刻（FB-102），不承諾時刻（待 joy 潤）。"""
    ranked = sorted((pair for pair in weights if pair[1] > 0), key=lambda pair: -pair[1])  # 穩定排序：並列照原本的順序
    words = [BRANCH_WORDS[branch] for branch, _ in ranked]
    if not words:
        head = "這裡多半一無所獲"
    elif len(words) == 1:  # 只剩一支走得了（FB-101）：不說「多半」，好像還有別的可能
        head = f"這裡會{words[0]}"
    elif ranked[0][1] > ranked[1][1]:
        head = f"這裡多半{words[0]}，也可能{'、'.join(words[1:])}"
    else:
        head = f"這裡可能{'、'.join(words)}"
    tail = "" if not blocked else f"；這裡要到 {until} 之後才悟得出" if until else "；這裡要過一陣子才悟得出" if later \
        else "；這一季之內這裡悟不出了"
    return head + (f"；偶得{legend}" if legend else "") + tail


EXPLORE_MODES = "點開三選一：找素材{fight}、找事件，或靜心感悟{sense}。"  # 待 joy 潤：行動列底下探索那一行（出陣探索與地盤設計第三節）
# 意境提示設計第二節（不寫數字）。輿圖第三版拿掉了意境濾鏡（第 4 批），第 5 批改寫成區圖名字底下的意境字與卡上的「最濃」（PM 2026-10-22；待 joy 潤）
STRONG_HOWTO = "每個地點有一種意境最濃（區圖上名字底下排第一的意境字、卡上「此地能悟」標著「最濃」的那一個），選對那一種的做法比較容易悟成。"
# 地利（武學隨地理環境計畫 Task 5；不寫倍數，待 joy 潤）
TERRAIN_HOWTO = ("- 各地的氣象不同：身上的武學、內功跟此地最濃的意境同一路，打起來順手；被它剋的，施展不開。"
                 "輿圖上點地點，「地利」那一段寫著此地利哪一路。")
EXPLORE_FIGHT = "（這裡可能撞上怪，打贏是經驗的大宗）"
EXPLORE_CALM = "（這裡不會撞上怪）"
EXPLORE_NO_SENSE = "（這裡悟不出什麼）"


# 減法季探索一顆（整合設計 4.1，批 2）：行動列底下探索那一行。照擲骰用的那一份比重（探索包 explore_actions.outing_weights）排，不寫百分比；都待 joy 潤
OUTING_WORDS = explore_one.BEAT_WORDS
OUTING_HEAD = "出門一趟只碰上一件事"  # 2d（企劃者 2026-10-26「只抽一件事情」）：以前寫「出門一趟走三拍」
OUTING_FOE = {"town": "；城裡遇敵是街上的地痞，給得少", "spar": "；自家營寨遇敵是跟同袍比劃，不掉東西"}
OUTING_BOUNTY = "出門一趟，接了這裡的討伐，每一趟都撞上懸賞那一路，交了差才回到平常"  # 接了這裡的討伐懸賞：整行換成這一句（一定是遭遇，不寫機率）


def outing_line(weights: dict[str, float], foe: str | None = None) -> str:
    """探索一顆開著時行動列底下探索那一行（Game.action_notes）：weights 是這一處這一趟四類事的比重（做不了的已經是 0）；比重最大的寫「多半」、
    其他照大小寫「也可能」，並列最大一起寫「可能」，只剩一類寫「會」（同 explore_line 的寫法）。foe：城裡的地痞（"town"）、自家營寨的比劃
    （"spar"）各補一句；接了這裡的討伐（"bounty"）整行換成 OUTING_BOUNTY（每一趟都是懸賞那一路的遭遇）；其餘 None。"""
    if foe == "bounty":
        return OUTING_BOUNTY
    ranked = sorted(((k, w) for k, w in weights.items() if w > 0), key=lambda pair: -pair[1])
    words = [OUTING_WORDS[k] for k, _ in ranked]
    if len(words) == 1:
        body = f"，會{words[0]}"
    elif ranked and ranked[0][1] > ranked[1][1]:
        body = f"，多半{words[0]}，也可能{'、'.join(words[1:])}"
    else:
        body = f"，可能{'、'.join(words)}" if words else ""
    return OUTING_HEAD + body + OUTING_FOE.get(foe or "", "")


def explore_modes_line(fight: bool, sense: bool) -> str:
    """探索三選一開著時行動列底下探索那一行（Game.action_notes）：找素材會不會撞上怪、靜心感悟悟不悟得出。"""
    return EXPLORE_MODES.format(fight=EXPLORE_FIGHT if fight else EXPLORE_CALM, sense="" if sense else EXPLORE_NO_SENSE)


# 行動列底下練功那一行（FB-670，企劃者 2026-10-22 選練功入口「丙」：練功在行動列自己一格；Game._practice_line 照練功鈕同一個判斷挑一句）。
# 灰著的城鎮寫 PRACTICE_TOWN_NOTE＋「，最近的在某地（步行約 N 分鐘）」（explore_modes.NO_FOE_NEAR、atlas.route_text）。都待 joy 潤
PRACTICE_NOTE = "打這裡的{foe}，不限次數，打贏是經驗的大宗"
PRACTICE_BOSS_NOTE = "這裡只有頭目{foe}，尋敵直接對上他；打一場要等他再現身，次數有限"
PRACTICE_TOWN_NOTE = "城外才有對手"


def train_line(foes: bool, gains: Sequence[str], drops: bool, push: bool, drill_gains: Sequence[str], drills: bool) -> str:
    """遊歷打完會拿到什麼。foes：這裡有會打的對手（不是自己陣營的）；gains：打贏給的（銀兩、心得、經驗，照會打的對手有沒有
    這一項）；drops：打贏有機會掉素材；push：打贏或操練會推大勢（Game.train_trend_push 不是空的）；drill_gains：跟自己人操練
    給的（只有心得、經驗，照 Config.drill_reward_share 算出來不是 0 的）；drills：這裡也有自己陣營的隊伍。沒有會打的對手＝操練。
    沒有會打的對手時，行動列那一格本身就寫「操練」（Game._train_option），這一行接在它後面：不再開頭寫一次「操練」（FB-101）。"""
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


def social_line(figure: str | None, events: bool, hall: bool) -> str:
    """交友這一下會遇上什麼。figure：會直接開口談話的那位（Game._socialize_figure）；events：這裡有交友事件；
    hall：這裡有兩位以上的人物（要按「求見」指名）。"""
    if figure is not None:
        return f"和{figure}談話，聊得投機情誼會漲"
    if events:
        return "結識這裡的人，碰上交友的事" + ("；要見人物按「求見」" if hall else "")
    return "這裡沒有見得到的人物，多半撲空"


CALL_LINE = "挑一位人物談話，聊得投機情誼會漲；名望不夠的會打發你"


def call_line(name: str, meet: bool, gap: int | None = None) -> str:
    """選單上直接列的「求見某某」（這裡只有一位人物）：見得到就是談話；見不到會被打發（Game._brush_off：不花體力）。
    gap：還差幾點名望（選項括號裡的「名望還差 N」），給了就照選項的說法開頭（FB-103：那一行跟格子說同一回事）。"""
    if meet:
        return f"和{name}談話，聊得投機情誼會漲"
    if gap is not None:
        return f"名望還差 {gap}，{name}會打發你（不花體力）"  # FB-103，待 joy 潤
    return f"名望不夠，{name}會打發你（不花體力）"


# ── 體力（explain-1 第三項）──────────────────────────────────────


def _clock(seconds: float) -> str:
    """一小段現實時間：整分鐘寫分鐘，不整的寫秒。"""
    minutes = seconds / 60
    if minutes >= 1 and abs(minutes - round(minutes)) < 1e-9:
        return f"{round(minutes)} 分鐘"
    return f"{seconds:g} 秒"


def _span(seconds: float) -> str:
    """一段現實時間：兩天以上寫幾天（到半天），以下寫約幾小時。"""
    days = seconds / calendar.DAY
    if days >= 2:
        return f"{round(days * 2) / 2:g} 天"
    return f"約 {max(1, round(seconds / calendar.HOUR))} 個小時"


def day_every(content: Content, season: WorldState) -> str:
    """「每個遊戲日」寫給玩家看（交友輪數上限那一句；遊戲日跟著季長縮，rules.day_seconds，企劃者 2026-10-08）：一個遊戲日剛好是
    現實一天（14 天的季）寫「每天」，一個字都不變；週末那一季的一天不是 24 小時，寫成現實的長度「每 4 小時 17 分（現實時間）」
    （世界秒 ÷ time_scale，到整分）。待 joy 潤。"""
    real = rules.day_seconds(content, season) / content.config.time_scale
    if abs(real - calendar.DAY) < 1:
        return "每天"
    hours, minutes = divmod(round(real / 60), 60)
    parts = [f"{hours} 小時"] * bool(hours) + [f"{minutes} 分"] * bool(minutes)
    return f"每 {' '.join(parts)}（現實時間）"


def regen_line(content: Content) -> str:
    """體力怎麼回（Game._advance_player_local）：每 stamina_regen_seconds 遊戲秒回 1 點（現實時間再除 time_scale），滿了就不再回。"""
    cfg = content.config
    return f"體力每 {_clock(cfg.stamina_regen_seconds / cfg.time_scale)}回 1 點，滿 {cfg.stamina_max} 就不再回。"


def newbie_line(content: Content, season: WorldState, still: bool | None = None, card: int = 0) -> str:
    """新手期體力回復加快（roster.newbie 的 newbie_stamina_days、newbie_stamina_multiplier）：第一季從自己加入的那一刻起算，beta 那一季
    從開季算，都是季曆天；寫成現實時間（季曆天 ÷ cal_scale ÷ time_scale，季長照這一季蓋的章）。倍數是 1 時沒有這一行（空字串）。
    still 給了就補一句還在不在這段時間裡。card：今天月卡讓回體丹上限多幾顆（Game._pill_card_bonus，FB-480），0 一個字都不變。"""
    cfg = content.config
    tail = "" if still is None else ("（你還在新手期）" if still else "（你的新手期已經過了）")
    if cfg.newbie_real_hours > 0:  # 新手期照現實時間（Joy 2026-10-17「新手期 48 小時」）：寫這段時間裡有什麼
        perks = []
        if cfg.newbie_stamina_multiplier > 1:
            perks.append(f"體力回復 ×{cfg.newbie_stamina_multiplier:g}")
        if cfg.stamina_pills_per_day > 0 and cfg.newbie_pills_per_day > 0:
            extra = f"（月卡多 {card} 顆）" if card > 0 else ""  # 待 joy 潤
            perks.append(f"{cfg.stamina_pill_name}一天能服 {cfg.newbie_pills_per_day + card} 顆{extra}")
        if cfg.raid.enabled:
            perks.append("別人截殺不了你")
        if not perks:
            return ""
        return f"新手期：加入這一季後的 {cfg.newbie_real_hours:g} 個小時內，{'，'.join(perks)}{tail}。"
    if cfg.newbie_stamina_multiplier <= 1:
        return ""
    real = cfg.newbie_stamina_days * calendar.DAY / calendar.cal_scale(content, season) / cfg.time_scale
    since = "加入這一季後" if calendar.season_one_on(season, content) else "開季後"
    span = _span(real)
    gap = "" if span.startswith("約") else " "  # 「開季後的 3 天內」「加入這一季後的約 13 個小時內」
    return f"新手期：{since}的{gap}{span}內，體力回復 ×{cfg.newbie_stamina_multiplier:g}{tail}。"


def pill_line(content: Content, count: int | None = None, today: int | None = None, card: int = 0) -> str:
    """體力條右端那顆鈕：測試期間一鍵補滿打開時（Config.beta_free_refill）是「補滿」，不花丹；關著時是回體丹，一顆回多少
    （count 給了就寫還有幾顆，0 顆沒有這一行；None 是玩法說明那種不看個人的說法）。一天有上限時（stamina_pills_per_day）
    多一句上限與換日，today 給了再寫今天還能服幾顆。card：今天月卡讓上限多幾顆（Game._pill_card_bonus，跟 Game.pill_cap 加的同一份；
    FB-480），兩個上限都加上去、括號裡寫月卡多幾顆；0 一個字都不變。"""
    cfg = content.config
    if cfg.beta_free_refill:
        return f"測試期間按體力條上的「{cfg.beta_free_refill_label}」直接補滿，不花{cfg.stamina_pill_name}。"
    if count is not None and count <= 0:
        return ""
    have = "" if count is None else f"（還有 {count} 顆）"
    line = f"{cfg.stamina_pill_name}一顆回 {cfg.stamina_pill_restore} 點{have}，按體力條右端的「丹」服下。"
    if cfg.stamina_pills_per_day > 0:
        left = "" if today is None else f"（今天還能服 {today} 顆）"
        parts = [f"新手期 {cfg.newbie_pills_per_day + card} 顆"] * (cfg.newbie_pills_per_day > 0)
        parts += [f"月卡多 {card} 顆"] * (card > 0)  # 待 joy 潤
        rookie = f"（{'；'.join(parts)}）" if parts else ""
        line += f"一天最多服 {cfg.stamina_pills_per_day + card} 顆{rookie}，每天 00:00（台灣時間）重新計算{left}。"
    return line


def stamina_lines(
    content: Content, season: WorldState, newbie: bool | None = None, pills: int | None = None, button: bool = True,
    today: int | None = None, card: int = 0,
) -> list[str]:
    """體力條點開的說明（也是玩法說明「體力」那一節）：回復、新手期、回體丹或補滿。button：體力條上有沒有那顆鈕
    （序章裡沒有，就不提）。today：今天還能服幾顆（Game.pills_left_today）。card：今天月卡讓回體丹上限多幾顆（FB-480；
    玩法說明不看個人，是 0）。空的行不列。打坐 2026-10-12 拿掉了。"""
    lines = [regen_line(content), newbie_line(content, season, newbie, card)]
    if button:
        lines.append(pill_line(content, pills, today, card))
    return [line for line in lines if line]


def gift_line(content: Content) -> str:
    """建角色時送的回體丹（Config.beta_gift、beta_gift_stamina_pills），記在江湖紀錄開場那一則的一行（建角色那一刻寫下）。
    測試期一鍵補滿打開時（Config.beta_free_refill），體力條那顆鈕寫 beta_free_refill_label、不花丹：說丹先收著、按那顆鈕免費補滿
    （控制者走查）；關著時說按「丹」服下。兩句都待 joy 潤。開頭從「內測贈禮」改成「新手福利」（正式季整合 6.3，企劃者 10/16）。"""
    cfg = content.config
    name, n, restore = cfg.stamina_pill_name, cfg.beta_gift_stamina_pills, cfg.stamina_pill_restore
    if cfg.beta_free_refill:
        return (f"新手福利：{name} {n} 顆（一顆回 {restore} 點體力），先收著；"
                f"測試期間按體力條上的「{cfg.beta_free_refill_label}」就能免費補滿，不花丹。")
    return f"新手福利：{name} {n} 顆，一顆回 {restore} 點體力，按體力條右端的「丹」服下。"


def top_up_line(content: Content, added: int) -> str:
    """拿掉一鍵補滿之後，舊角色補回體丹的那一行（Game._top_up_pills）。"""
    cfg = content.config
    return (f"體力條上的「{cfg.beta_free_refill_label}」收起來了；補給你{cfg.stamina_pill_name} {added} 顆，"
            f"手上一共 {cfg.beta_gift_stamina_pills} 顆，一顆回 {cfg.stamina_pill_restore} 點體力，按體力條右端的「丹」服下。")


# ── 江湖頁的戰況、態勢、大事、主線點開的說明（explain-2 第一項，FB-100）──────────────────────
# 第一季濃縮版才有（呼叫端在 rules.season_one 後面）。亂局帶讀 Config.chaos_low／chaos_high，此刻在亂局的戰線讀 rules.chaos_fronts，
# 大事的件數讀時刻表、擲骰的上下限讀 timetable 的常數、改寫得了的大事讀伏筆的鏈：不另寫一份判斷。戰況的變化照舊不寫數字（FB-064），
# 這裡寫的只有規則的門檻與此刻的狀態。


_count = rules.count_word  # 幾條：十以內寫國字（跟態勢卡底下「三條戰線合計」同一種寫法），再多寫數字


def _band(content: Content) -> str:
    cfg = content.config
    return f"{cfg.chaos_low}～{cfg.chaos_high}"


def _tenths(p: float) -> str:
    """機率寫成「幾成」：0.1 → 一成。"""
    return f"{_count(round(p * 10))}成"


def season_line(content: Content) -> str:
    """這一季在打什麼（第一季設計第一、四節）：劇本名、官軍與黃巾爭的幾條戰線、豪強依附其中一邊（豪強分屬兩軍，allied.on；
    第一季才寫，2026-10-31 豪強割據的那一句連豪強第三方的季一起拿掉）。"""
    fronts = [rules.trend_name(content, f) for f in rules.front_ids(content)]
    guan, huang, hao = (STANCE_NAMES[k] for k in ("guan", "huang", "haoqiang"))
    tail = f"地方{hao}依附其中一邊。"
    return f"這一季是{content.scenario.name}：{guan}與{huang}在{_count(len(fronts))}條戰線上爭（{'、'.join(fronts)}），{tail}"


# 亂局帶與態勢的規則各只寫一次（審查 Minor 7）：態勢、戰況圖卡、玩法說明「這一季在打什麼」都拿這兩句，改一處三處一起變


def front_rule(content: Content, card: bool = True) -> str:
    """戰線的兩端與亂局帶（rules.in_chaos：chaos_low～chaos_high，含兩端），亂局是兩軍拉鋸的地方。card：在戰況圖卡上說（指著條上淺色那一段）。"""
    guan, huang = (STANCE_NAMES[k] for k in ("guan", "huang"))
    shade = "（條上淺色那一段）" if card else ""
    return f"每條戰線 0 是{guan}穩控、100 是{huang}控制；戰況落在 {_band(content)} 是亂局{shade}，兩軍在這裡拉鋸。"


# 豪強分屬兩軍：態勢那一句（豪強割據的那一句 geju_rule 2026-10-31 拿掉）
ALLIED_RULE = "{guan}、{huang}的態勢是{n}條戰線合起來的；地方{hao}依附其中一邊，算那一邊的人，沒有自己的態勢。"


def allied_rule(content: Content) -> str:
    guan, huang, hao = (STANCE_NAMES[k] for k in ("guan", "huang", "haoqiang"))
    return ALLIED_RULE.format(guan=guan, huang=huang, hao=hao, n=_count(len(rules.front_ids(content))))


def stance_help(content: Content) -> list[str]:
    """態勢小標點開的說明：這一季在打什麼、兩方的態勢怎麼算、豪強依附一邊。"""
    return [season_line(content), allied_rule(content)]


# 推線的那一句只說「有些地方」（FB-112）：推不推看地點的 train_trend（Game.train_trend_push），很多有對手的地方不推（潁水河畔），
# 行動列底下那一行（train_line 的 PUSH_WORD）照這一處的實情寫
SOME_PLACES = "有些地方遊歷打贏、操練會推動戰況（行動列底下那一行寫著這裡推不推）"
SORTIE_RANGER = "散人不出陣，靠懸賞與事件出力"  # 出陣開著時（出陣探索與地盤設計第二節）；待 joy 潤
# 出陣（＝領地爭奪，第 38 項改版第一批）：出陣推的是那一塊的進度、戰線照佔領算——出陣開著時取代 SOME_PLACES 的幾處（待 joy 潤）
CONQUEST_PLACES = "在官軍、黃巾的領地與中立地出陣，推的是那一塊的進度，不直接推戰線"
CONQUEST_JOIN = "在官軍、黃巾的領地與中立地出陣：別人的地方打贏把那一塊的進度往你那一邊推，自家的地方守一回、推一半"
# 約戰開著（減法季批 3b；FB-857）：沒有零風險的守，出陣是貼約戰、守就是應戰；取代上面那一句（sortie_duel.on 的季）。待 joy 潤
CONQUEST_JOIN_DUEL = "在官軍、黃巾的領地與中立地出陣：別人的地方、中立地封好三招貼約戰，打贏把那一塊的進度往你那一邊推，自家的地方等對面來約、應戰守住了把進度拉回來"
CONQUEST_FRONTS = "戰線照兩軍佔了多少地來算：佔下中立地、打進敵方的領地，戰線就往那一邊偏"


def _sortie_places(content: Content, season: WorldState | None) -> str:
    """「你能做的」那一句的出陣怎麼推：出陣（＝領地爭奪）開著時推進度（CONQUEST_PLACES），沒有出陣的季照舊遊歷。"""
    return CONQUEST_PLACES if sortie.on(content) else SOME_PLACES


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


def explore_lines(content: Content, season: WorldState | None = None) -> list[str]:
    """玩法說明「行動」裡探索那一條（三選一開著時取代照地點比例那一條；待 joy 潤）。數字讀 Config。
    一類一顆在這一季生效時（precise.on）寫另一版：找素材一定給、不打仗，練功另一條（FB-422）；舊季一個字都不變。"""
    cfg = content.config
    names = explore_modes.NAMES
    if rules.jianfa(content, season, "explore_one"):  # 減法季探索一顆（批 2）：只剩一顆、出門一趟；關著下面一個字不變
        return outing_lines(content, season) + jianfa_growth_lines(content, season)
    if precise.on(content, season):
        return precise_explore_lines(content, season) + gather_branch_lines(content, season) + jianfa_growth_lines(content, season)
    legend = f"三種都有機會撿到{cfg.legend_item_name}。" if cfg.explore_legend_chance > 0 else ""
    econ = cfg.economy  # 素材與經濟設計第七節：一階從一定給改成七成
    first = f"（一階約 {econ.gather_first_chance * 10:g} 成撿得到）" if econ.gather_cut else ""
    return [
        f"- **探索**（體力 {cfg.action_cost['explore']}）：點開三選一。{names['gather']}：照這裡的地形撿素材{first}，"
        f"城外約 {cfg.explore_modes.encounter_chance * 10:g} 成會撞上怪，打贏是經驗的大宗；{names['seek']}：碰上這一帶的事，偶有奇遇；"
        f"{names['sense']}：只在悟得到意境的地方。{legend}",
    ]


def _pct(share: float) -> str:
    return f"{share * 10:g} 成"


def outing_lines(content: Content, season: WorldState | None = None) -> list[str]:
    """減法季探索一顆（整合設計 4.1，批 2；2d 企劃者 2026-10-26 改成一趟一件事；待 joy 潤）的玩法說明：一顆、出門一趟碰上一件事、
    地點決定多半給什麼、地痞與比劃、懸賞。數字讀 Config.jianfa。"""
    jf = content.config.jianfa
    tables = "，".join(explore_one.named_hint(t) for t in jf.explore_tables)
    legend = f"偶爾撿到{content.config.legend_item_name}。" if content.config.explore_legend_chance > 0 else ""
    return [
        f"- **探索**（體力 {jf.explore_stamina}）：只有一顆，按一下是出門一趟，一趟只碰上一件事，"
        f"照這個地方抽遇事、遇敵、得料或有悟其中一件——地點決定多半給什麼（{tables}），危險的地方遇敵多些、遇事少些，運氣決定這一趟給什麼。"
        "得料、遇敵當場算完；遇事、有悟要你自己選。回來是一段話，底下一行寫這一趟的得失。"
        "城裡沒有對手時遇上的是街上的地痞，給得少；自家營寨遇敵是跟同袍比劃，不受傷也不掉東西。"
        f"接了這裡的討伐懸賞，在那裡出門每一趟都撞上懸賞那一路，交了差才回到平常。{legend}",
    ]


def jianfa_growth_lines(content: Content, season: WorldState | None = None) -> list[str]:
    """減法季三道閘與屬性五段（整合設計 4.2、4.5，批 2；待 joy 潤）的玩法說明；各自的子開關關著就不寫（關著的季一個字都不多）。"""
    jf = content.config.jianfa
    out: list[str] = []
    if rules.jianfa(content, season, "drill_gates"):
        out.append(
            f"- **練得多了收穫漸少**：出門遇敵，一天前 {jf.drill_full_per_day} 場收穫全額，之後一場比一場少（最少剩 {_pct(jf.drill_floor)}，"
            f"天亮 00:00 重算）；對手比你低一截給一半、低兩截只給一成，要找配得上的對手。"
            f"第 {jf.drill_level_cap} 級以後只有打出來的經驗（遇敵、頭目、出陣、切磋、截殺、擂台、決戰、挑戰人物）算數，其餘的經驗化作心得。")
    if rules.jianfa(content, season, "stat_milestones"):
        levels = "、".join(str(lv) for lv in jf.milestone_levels)
        out.append(
            f"- **境界與配點**：升級不再給屬性點；到第 {levels} 級各是一次境界，給 {jf.stat_points_per_milestone} 點自己配。"
            f"點少了、每一點重了：臂力、根骨一點多 {jf.stat_rates.bonus_per_point * 100:g}% 的威力，身法一點多 {jf.stat_rates.dodge_per_point * 100:g}% 的閃避，"
            f"博聞一點多 {jf.stat_rates.holding_per_lore_point} 格持有。配滿一項是一條路，配下去那一刻會寫多了什麼。")
    return out


def precise_explore_lines(content: Content, season: WorldState | None = None) -> list[str]:
    """一類一顆的探索與練功（FB-422；正式季整合 2.4、2.5；待 joy 潤）。數字讀 Config。
    城裡操練開著時（training.on，新手引導重做）：練功在行動列自成一格，城裡那一格是操練，練功點分三級。"""
    cfg = content.config
    names = explore_modes.NAMES
    cost = cfg.action_cost["explore"]
    legend = f"每一種都有機會撿到{cfg.legend_item_name}。" if cfg.explore_legend_chance > 0 else ""
    explore = (f"- **探索**（體力 {cost}）：點開來挑一種。{names['gather']}：照這裡的地形一定撿得到素材，不打仗；"
               f"{names['seek']}：碰上這一帶的事（交友的事也在這裡），偶有奇遇；{names['sense']}：只在悟得到意境的地方。{legend}")
    if not training.on(content, season):
        return [explore,
                f"- **{names['practice']}**（在探索裡，體力 {cost}）：找這裡的對手打一場，一定開打、不限次數，打贏是經驗的大宗；"
                "城鎮與沒有對手的地方灰著。有頭目的地方，頭目在尋敵時碰上。"]
    t = cfg.training
    loot = "、".join(f"{w} ×{x:g}" for w, x in zip(training.TIER_WORDS, t.tier_loot))
    return [
        explore,
        f"- **{training.DRILL}**（城裡，行動列那一格，體力 {cost}）：跟校場的教頭過招，不打仗、不受傷，一天 {t.drill_per_day} 次"
        f"（00:00 換日）；一次給心得 {t.drill_xinde_base}＋等級、經驗一點點。用完了那一格寫著最近能尋敵的地方。",
        f"- **{names['practice']}**（城外，同一格，體力 {cost}）：找這裡的對手打一場，一定開打、不限次數，打贏是經驗的大宗。"
        f"照這裡最弱的對手分三等（難度 {t.tier_bounds[0]} 以下、{t.tier_bounds[1]} 以下、再上去），"
        f"越遠越兇；打贏的心得與銀兩照這一帶多兇加成（{loot}），經驗不加成。多兇寫在格子上與輿圖的地點詳情。有頭目的地方，頭目在尋敵時碰上。",
    ]


def gather_branch_lines(content: Content, season: WorldState | None) -> list[str]:
    """找素材分支（第 32 項；待 joy 潤）開著時多一條：哪幾條路多給哪幾種屬性、深入偶有所悟、「自己說」。照 content/gather_branches.json 寫，
    關著是空的（一個字都不變）。"""
    if not explore_modes.branches_on(content, season):
        return []
    names = explore_modes.NAMES
    roads = "，".join(f"{b.name}多{'、'.join(b.attributes)}" for b in content.gather_branches.values() if not b.deep)
    deep = next((b for b in content.gather_branches.values() if b.deep), None)
    deep_line = f"；深山裡「{deep.name}」偶爾另有所悟" if deep is not None and content.config.gather_branches.deep_insight_chance > 0 else ""
    say = (f"最後一顆「{explore_modes.SAY_LABEL}」寫一句自己的找法（{explore_modes.SAY_MAX} 字內），寫得好多一份。"
           if content.config.gather_branches.say_enabled else "")
    return [f"- **{names['gather']}的路**：城外有兩條以上的路可走時，按{names['gather']}會再攤開幾條——{roads}{deep_line}。{say}"]


def _tenth(share: float) -> str:
    """0.1 → 一成、0.2 → 兩成（rules.count_word）；不是整成照寫百分比。"""
    tenths = round(share * 10, 6)
    return f"{'兩' if tenths == 2 else rules.count_word(int(tenths))}成" if tenths == int(tenths) else f"{share * 100:g}%"


def conquest_lines(content: Content, season: WorldState | None = None) -> list[str]:
    """玩法說明「地盤」一節的領地爭奪版（第 38 項改版第一批；開關在這一季生效時取代拔河那一版；待 joy 潤）。數字讀 Config。
    season 給了而且約戰在這一季開著（減法季批 3b）：出陣、守勢行動、集火那三句換成約戰版（沒有守與混戰）；沒給、關著一個字都不變。"""
    cfg, terr = content.config.conquest, content.config.territory
    gather = f"{cfg.gather_bonus_chance * 100:g}%"
    lines = [
        "地圖分三種：官軍的領地、黃巾的領地，和中立地。中立地開季沒人佔，兩軍爭的就是它；各家的投靠點永遠是自家的，廣宗只照廣宗決戰易手。",
        "能挑的是跟自家領地有路直通的那一塊——中立地，或者敵方的領地，一塊一塊往前推。",
        f"三條戰線的大勢照兩軍佔了多少地來算：一條線上的中立地全被一方拿下，那條線往那一邊偏 {cfg.share:g} 點；"
        "打進敵方的領地份量加倍。時刻表的大事、事件、大勢人物、軍令照舊推線。",
        "出陣不再直接推戰線，推的是那一塊的進度：每一塊對每一個來攻的一方各有一條進度。在別人的地方、還沒人佔的中立地出陣是攻、"
        "推自己那一條；在自家的地方是守、把對面每一條都拉回來；照樣記貢獻。各家的大本營與廣宗不在爭奪之列：別人的攻不得，"  # 裁決 18
        "自家的守了也沒有進度。找不到對手的地方推不動。",
        # 裁決 24（PM 2026-10-20）；待 joy 潤
        "巡哨、傳道、保境安民這類守勢行動也只在自家的領地做：別人的地方、還沒人佔的中立地，那一顆灰著，按不下去。",
        f"哪一條推滿 100，那一塊當場易手：天下大事一句，推過的人照出力分銀兩、經驗、名望，推最多的上江湖史。剛易手的地 "
        f"{cfg.cooldown_minutes:g} 分鐘內兩邊都推不動，那一塊的加成也先停著。沒人推的地每天往回 {cfg.decay_per_day:g}。",  # 待 joy 潤
        f"同一邊的人一小時內一起推同一塊，每多一個人每一下多推 {cfg.focus_step * 100:g}%（最多 {cfg.focus_cap * 100:g}%）。"
        f"出陣時對面 {cfg.clash_minutes:g} 分鐘內在這一塊推過、人還在，就撞上打一場（照截殺的規矩，城裡也打、不搶東西）："
        f"贏的那一下多推 {(cfg.clash_scale - 1) * 100:g}%，輸的那一下白跑。守方把五成以上的進度拉回零，也照出力分守城功。",
        f"進度到 {cfg.letter_at:g}，那一邊這一週在任的第 4 階可以下戰書（一邊一天一張）：挑最近的攻城時段"
        f"（{cfg.slot_first // 60}:00～{cfg.slot_last // 60}:00 的整點或半點）打一場攻城戰，那一塊的進度凍結到打完。"
        f"開打前 {cfg.muster_minutes} 分鐘開集結，人要在那個大區才加得進去。攻城戰是決戰的縮小版：攻方贏了直接易手、"
        f"輸了進度砍半，守方沒人時打那裡的留守，攻方沒人到這一場作罷。軍餉是決戰的{_tenth(cfg.pay_share)}。",
        # 裁決 22（企劃者 2026-10-21）；待 joy 潤
        "兩軍都對同一塊中立地下了戰書，就併成一場三方混戰：那裡的守將兩邊都打，兩軍之間也照常交鋒；強攻打得到守將，"
        "戰線壓向哪一軍，那一軍打守將就越有力。誰補上守將最後一刀，這一塊就歸誰；回合打完守將還沒倒，照舊沒人佔。"
        "散人可以投效兩軍之一，或助守。",
        f"人站在自家領地：療傷、打造、買馬便宜{_tenth(1 - terr.own_price)}，在敵方的領地貴{_tenth(terr.enemy_price - 1)}"
        f"（新手期在敵方領地療傷不加價）；找素材有 {gather} 的機會多撿一個，靜心感悟更容易抓住。",
        "散人在開季是中立地的地方也算自家：一樣便宜、一樣多撿一份，不論那裡此刻被誰佔了。",
        "中立地站著另一批強對手，掉的東西也好；被佔下之後照樣在那裡，兩邊的人去都得打。",
        # 輿圖第三版（第 5 批改字）：沒有局勢層了，天下圖的地面與區圖的名字框照誰佔著上色；待 joy 潤
        "輿圖上，天下圖的地面、區圖名字框的顏色就是此刻誰佔著，灰的是還沒人佔的中立地；正在翻的地泛著攻方的顏色，易手時天下大事會傳一句。",
    ]
    if season is not None and sortie_duel.on(content, season):  # 約戰開著（減法季批 3b）：出陣是約戰、沒有守與混戰；待 joy 潤
        lines[3] = ("出陣不再直接推戰線，推的是那一塊的進度：每一塊對每一個來攻的一方各有一條進度。在別人的地方、還沒人佔的中立地出陣是貼約戰，"
                    "打贏推自己那一條；守是應戰，守住了把攻方那一條拉回來；照樣記貢獻。各家的大本營與廣宗不在爭奪之列，攻不得。")
        lines[4] = "巡哨、傳道、保境安民只在自家的領地做，不推線、一天記一點貢獻：別人的地方、還沒人佔的中立地，那一顆灰著。"
        lines[6] = (f"同一邊的人一小時內一起推同一塊（約戰的同去也算），每多一個人每一下多推 {cfg.focus_step * 100:g}%（最多 {cfg.focus_cap * 100:g}%）。"
                    "守方把五成以上的進度拉回零，也照出力分守城功。")
    if seal.on(content):  # 第三批 B（設計 3.9）：碎片的來源；只說「在哪一類地方」，藏在哪一塊不公開；待 joy 潤
        lines.insert(-1, "傳說傳國玉璽的碎片就藏在這些中立地的某一處：一季最多一片，到那裡探索（四種探索都算）才有極小的機會撿到，"
                         "藏在哪一處沒人知道；那一塊此刻若歸你的陣營，機會再高一點；剛易手、還在冷卻的地方撿不到。")
    return lines


def territory_lines(content: Content, allied: bool = False, season: WorldState | None = None) -> list[str]:
    """玩法說明「地盤」一節（地盤開著時＝領地爭奪，conquest_lines；待 joy 潤）。allied 留著給舊的呼叫寫法。"""
    return conquest_lines(content, season)


ECONOMY_TITLE = "素材的出路"  # 待 joy 潤：玩法說明那一節的標題（素材與經濟設計第四～六節）


def economy_lines(content: Content, allied: bool = False) -> list[str]:
    """玩法說明「素材的出路」一節（Config.economy 的收購、升階、捐軍備，開著的才寫；都關著是空的；待 joy 潤）。數字讀 Config。
    allied：豪強分屬兩軍的季，豪強捐的進依附那一邊、在自己的莊院與那一邊的大本營都能捐（新寫）。"""
    econ = content.config.economy
    reset = "台灣時間 00:00 換日" if content.config.pill_day_utc_offset_hours == 8 else "每天 00:00 換日"
    tier_word = {1: "一階", 2: "二階", 3: "三階", 4: "四階"}
    four = four_tiers.on(content)
    lines = []
    if econ.sell:
        tiers = economy.sell_tiers(content)
        prices = [f"{tier_word.get(t, f'{t}階')} {econ.sell_price[t]} 兩" for t in tiers]
        prices[0] = prices[0].replace(" ", "一個 ", 1)  # 「一階一個 2 兩、二階 6 兩」
        refused = "四階不收，留著打神器" if four else "三階不收，留著打神器"  # 素材四階（正式季整合 4.2）
        lines.append(f"城鎮的鐵匠鋪收素材：{'、'.join(prices)}；{refused}。")
        rcfg = content.config.renown
        dark_prices = {t: p for t, p in rcfg.black_market_prices.items() if t in tiers}
        if renown.on(content, "black_market") and dark_prices:  # 名聲 5.2：寇的黑市價（待 joy 潤）
            title = renown.VIRTUE_TITLES["寇"][rcfg.black_market_tier]
            dark = "、".join(f"{tier_word.get(t, f'{t}階')} {p} 兩" for t, p in sorted(dark_prices.items()))
            lines.append(f"走寇的路、到了「{title}」，鐵匠照黑市價收：{dark}。")
    if econ.upgrade:
        steps = []
        needs = economy.upgrade_needs(content)
        for tier in sorted(needs):
            if four:  # 素材四階：一般的不設每日上限，三換四一季幾個、一定同屬性（4.2、4.5）
                cap_text = f"，一季{four_tiers.count_text(content.config.four_tiers.season_cap)}個、一定出同屬性" if tier == four_tiers.TIER else ""
            else:
                cap = econ.upgrade_per_day.get(tier)
                cap_text = f"，一天{rules.count_word(cap)}個，{reset}" if cap is not None else ""
            cost = content.config.four_tiers.upgrade_silver if four and tier == four_tiers.TIER else econ.upgrade_silver.get(tier, 0)
            steps.append(f"{tier_word.get(tier - 1)}{rules.count_word(needs[tier])}個換一個{tier_word.get(tier)}"
                         f"（工錢 {cost} 兩{cap_text}）")
        astray = ""
        if econ.upgrade_same_share < 1:  # 升階隨機（企劃者 2026-10-15）：投入的屬性幾成，其餘落到別的屬性
            share = round(econ.upgrade_same_share * 10)
            astray = f"熬出來的約 {share} 成是同屬性的，其餘隨機落到別的屬性。"
        lines.append(f"鐵匠鋪也幫你把素材熬成高一階的：同屬性的{'；'.join(steps)}。{astray}工錢照地盤福利算。")
    if econ.donate:
        points = "、".join(f"{tier_word[t]} {n} 點" for t, n in sorted(econ.donate_points.items()) if t in tier_word)
        names = "、".join(econ.armaments.values())
        where = "（豪強：自己的莊院與依附那一邊的大本營都算）" if allied else ""
        gentry = "（豪強捐的進依附那一邊）" if allied else ""
        lines.append(
            f"投靠了陣營，在自家的大本營{where}可以捐軍備：{points}，一天最多 {econ.donate_daily_cap} 點（{reset}）。"
            f"捐的記成貢獻（第一季），也把大本營那一條戰線往自家推一點{gentry}；素材累積成陣營的{names}，"
            "在大決戰怎麼用，之後再定。"
        )
    return lines


def _order_pushers(content: Content) -> list[str]:
    """軍令湊滿額度時會推戰況的陣營（orders.json 的範本裡有 effect.trend > 0 的）；豪強只有打擊（挫聲威，不推線）。"""
    return [f.id for f in content.scenario.factions if any(t.side == f.id and t.effect.trend > 0 for t in content.orders.templates)]


def fronts_help(state: GameState, content: Content) -> list[str]:
    """戰況圖卡點開的說明：兩端、亂局帶、此刻哪幾條在亂局（rules.chaos_fronts）、玩家怎麼推（Game.train_trend_push：
    有 train_trend 的地方才推；官軍、黃巾往自己那一邊，散人照地方本來的方向，豪強往依附的那一邊；軍令達成時，軍令會推線的陣營
    整個推一把）。句子照內容（FB-112）。第一季才有（Game.status 的 war_help），豪強分屬兩軍。"""
    chaos = [rules.trend_name(content, f) for f in rules.chaos_fronts(state, content)]
    now = f"現在{'、'.join(chaos)}在亂局。" if chaos else "現在沒有戰線在亂局。"
    on = sortie.on(content)
    if on:  # 領地爭奪：出陣不直接推線，戰線照佔領算（設計 3.7、3.8）
        parts = [f"{CONQUEST_FRONTS}（地方豪強算依附的那一邊）；{CONQUEST_PLACES}，大事、事件、大勢人物照舊推線"]
    else:
        parts = [f"{SOME_PLACES}，往你陣營那一邊推（地方豪強往依附的那一邊）"]
    pushers = _order_pushers(content)
    if pushers:  # 一個人照做軍令不推戰線，全陣營湊滿額度那一刻才推（orders.credit，審查 Minor 5）
        parts.append(f"{'、'.join(STANCE_NAMES.get(f, f) for f in pushers)}的軍令湊滿額度時整個陣營再推一把")
    tail = SORTIE_RANGER if on else "散人照那個地方本來的方向推"
    return [front_rule(content) + now, "；".join(parts) + f"；{tail}。"]


def _lockable(content: Content) -> int:
    """關鍵伏筆改寫得了的大事有幾件：會鎖定大事的兩方（timetable.SIDE_NAMES，跟 foreshadow.LOCK_SIDES 同一份；官軍、黃巾）的鏈指著的
    那幾件。"""
    sides = set(timetable.SIDE_NAMES)
    return len({chain.event for chain in content.foreshadows.chains if chain.side in sides})


def board_help(content: Content) -> list[str]:
    """大事小標點開的說明：時刻表的大事怎麼定（timetable.resolve：給了結果照它→有人鎖定照鎖定→固定的照寫好的→其餘照戰況擲骰；
    擲骰的機率照 roll_chance：有戰線的照戰況、先夾在 CHANCE_FLOOR～CHANCE_CEIL，沒有戰線的照它自己的 base_chance；軍令與一般伏筆的
    修正另加）。skip_if_out 的人物先退場了那件就跳過（resolve）。件數讀時刻表。"""
    kinds = [e.kind for e in content.timetable]
    fixed, roll, showdown = (kinds.count(k) for k in ("fixed", "roll", "showdown"))
    fronted = sum(e.kind == "roll" and e.front is not None for e in content.timetable)
    parts = []
    if fixed:
        parts.append(f"{fixed} 件史書寫定，到時候照寫好的揭曉")
    if roll:
        how = []
        if fronted:
            how.append(f"{fronted} 件看戰況：那條戰線越偏向哪一邊，那一邊越容易成，戰況最多給到{_tenths(timetable.CHANCE_CEIL)}、"
                       f"最少也有{_tenths(timetable.CHANCE_FLOOR)}")
        if roll - fronted:
            how.append(f"{roll - fronted} 件不在戰線上，各有各的機會")  # 例：盧植下獄（審查 Minor 5）
        parts.append(f"{roll} 件擲骰（{'；'.join(how)}），軍令與伏筆還能再推一點")
    if showdown:
        parts.append(f"{showdown} 場決戰由上陣的人在戰場上打出來")
    finale = "；最後是季末收場" if "finale" in kinds else ""
    lines = [f"這一季有 {len(kinds)} 件大事，照時刻表一件件揭曉：{'；'.join(parts)}{finale}。"]
    skips = sum(e.skip_if_out is not None for e in content.timetable)
    if skips:  # 寫好的、擲骰的都可能：那位人物先退場（重創、被打敗）就不公告、不套效果（審查 Minor 5）
        lines.append(f"有 {skips} 件要看那位人物還在不在：他先退場了，那件就不發生。")
    locks = _lockable(content)
    if locks:
        lines.append(f"其中 {locks} 件可以被關鍵伏筆改寫：有人暗中做成了最後一步，那件大事就照他那一邊揭曉，揭曉之前誰也看不出來。")
    return lines


def quest_help(content: Content, season: WorldState | None = None) -> list[str]:
    """主線小標點開的說明：你能怎麼影響這一季（遊歷、軍令、伏筆）。FB-112：推線只說有些地方；伏筆只有會鎖定大事的兩方
    （foreshadow.LOCK_SIDES＝timetable.SIDE_NAMES）改寫得了，豪強照依附的那一邊，散人做不了（foreshadow.capable 要陣營對得上）。season 給了照季寫軍令多久一道（軍令每天發的季〔21 天季、7 天濃縮季〕「每天」，FB-501、FB-502）。"""
    locks = "、".join(timetable.SIDE_NAMES.values())
    aside = f"地方{STANCE_NAMES['haoqiang']}照依附的那一邊；"  # 豪強分屬兩軍：沒有第三方
    return [
        f"你能做的：{_sortie_places(content, season)}；"
        f"投靠陣營之後{calendar.week_word('order_each', content, season)}有軍令，照做記功，全陣營湊滿額度就一起見效；"
        f"{locks}的人聽傳聞、跟人物交好，湊齊關鍵伏筆，能暗中改寫一件大事（{aside}散人拿不到伏筆）。",
    ]


def war_help(state: GameState, content: Content) -> dict[str, list[str]]:
    """江湖頁四個地方點開的說明（status.war_help）：stance＝態勢小標、fronts＝戰況圖卡、board＝大事小標、quest＝主線小標。"""
    return {  # 第一季才有（Game.status），豪強分屬兩軍（設計第十四節）
        "stance": stance_help(content),
        "fronts": fronts_help(state, content),
        "board": board_help(content),
        "quest": quest_help(content, state.world),
    }


# ── 名望怎麼來（explain-2 第二項，FB-100「名望不知道怎麼來」）──────────────────────────
# 引擎裡真的給名望的只有四條路：事件的效果（rules.apply_effect，內容寫的 stats.fame）、第一季的首創回饋（Game._deliver_echoes，
# Config.first_echo）、決戰最有戲的那一搏（Game._file_showdown，BattleTuning.highlight_fame）、打贏頭目（Game._duel_finish，DuelBoss.fame）、
# 奪璽單挑（Game._file_seal，Config.seal.fame；玉璽碎片設計 5.9）。事件照種類分三堆、照內容算出範圍（一個一個列出來沒有用）；這一季關掉的 beta 事件（season_one_off）不算。

FameRange = tuple[int, int]


def _effects(event) -> list[tuple[object, bool]]:
    """一則事件的每一個效果，連同它是不是動手才拿得到的（動手的選項：劇情戰打贏）。"""
    out: list[tuple[object, bool]] = []
    for choice in event.choices:
        out += [(choice.effect, choice.combat is not None), (choice.fail_effect, choice.combat is not None)]
    if event.free_text is not None:
        out += [(event.free_text.effect, False), (event.free_text.fail_effect, False)]
    return out


def fame_ranges(content: Content, season: WorldState) -> dict[str, FameRange]:
    """事件給、扣的名望（只看內容）：
    - "common"：可重複的事件（探索、交友、遊歷之後碰上的；劇情接下去的那幾段、晉升的劇情也算）裡不動手就拿得到的；
    - "big"：動手打贏的（劇情戰）、一次性與奇遇（events.is_rare）、新立門戶福緣；
    - "loss"：任何一個效果扣的（檢定失手、做了丟臉的事；寫成負數，(最多扣, 最少扣)）。
    每堆（最小, 最大）；這一堆沒有就不在回傳裡。"""
    from .events import is_rare  # noqa: PLC0415  events → rules → …：只有這裡用到

    off = rules.season_one_off(content, season, "events")
    piles: dict[str, list[int]] = {"common": [], "big": [], "loss": []}
    for event in content.events.values():
        if event.id in off:
            continue
        rare = is_rare(event) or event.fortune
        for effect, fight in _effects(event):
            fame = effect.stats.get("fame", 0)
            if fame < 0:
                piles["loss"].append(fame)
            elif fame > 0:
                piles["big" if rare or fight else "common"].append(fame)
    return {key: (min(values), max(values)) for key, values in piles.items() if values}


def _plus(span: FameRange) -> str:
    low, high = span
    return f"+{low}" if low == high else f"+{low}～+{high}"


def fame_lines(content: Content, season: WorldState) -> list[str]:
    """玩法說明「名望」那一節：從哪裡來（事件三堆、第一季的首創回饋、決戰最有戲的那一搏）、拿來做什麼（求見門檻、視野〔全圖開放時沒有〕、拜師學藝）。數字讀內容與設定。"""
    return [*_fame_sources(content, season), _fame_uses(content, season=season)]


def _fame_sources(content: Content, season: WorldState) -> list[str]:
    """名望從哪裡來（「名望」與「名聲」兩節共用）。"""
    cfg = content.config
    spans = fame_ranges(content, season)
    lines = []
    if "common" in spans:
        # 出陣開著時沒有遊歷，戰後事件接在探索找素材撞上的那一場之後（FB-257；待 joy 潤）
        # 一類一顆：戰後事件與交友事件都併進找事件（FB-420 同一批；待 joy 潤）
        where = ("探索找事件時" if precise.on(content, season)
                 else "探索、交友、找素材撞上的仗之後" if sortie.on(content) else "探索、交友、遊歷之後")
        lines.append(f"事件裡出頭、仗義、露臉的做法（{where}碰上的事）：一次 {_plus(spans['common'])}。")
    if "big" in spans:
        lines.append(f"劇情裡打贏強敵、奇遇與一次性的大事：一次 {_plus(spans['big'])}。")
    if "loss" in spans:
        most, least = spans["loss"]
        lines.append(f"檢定失手、做了丟臉的事會掉：{-least}～{-most}。" if most != least else f"檢定失手、做了丟臉的事會掉 {-most}。")
    echo = cfg.first_echo
    if calendar.season_one_on(season, content) and echo.fame_per > 0:
        lines.append(f"你首創的武學或意境，別人照著合出同一門：每多一個人 +{echo.fame_per}，一門最多算 {echo.cap} 個人。")
    if cfg.battle.highlight_fame > 0:
        lines.append(f"決戰裡放手一搏，成了、而且是那一仗最令人印象深刻的一幕：+{cfg.battle.highlight_fame}。")
    duel_fame = sorted(boss.fame for boss in content.duels.values() if boss.fame > 0)
    if duel_fame:  # 單人頭目戰打贏（Game._duel_finish）
        lines.append(f"探索時遇上攔路的頭目、打贏了：{_plus((duel_fame[0], duel_fame[-1]))}。")
    if seal.on(content):  # 奪璽單挑（Game._file_seal，玉璽碎片設計 5.9）；待 joy 潤
        fame = cfg.seal.fame
        lines.append(f"奪璽單挑：懷璽的人守住了 +{fame['keep']}、被奪走 +{fame['lose']}；挑戰的人打贏了單挑、碎片卻沒易手 +{fame['near']}。")
        if seal.mandate_event(content) is not None and cfg.seal.mandate.fame > 0:  # 得天命的那一軍（Game._showdown_pay，玉璽二）
            lines.append(seal.MANDATE_FAME.format(fame=cfg.seal.mandate.fame))
    gen = cfg.battle.generals
    if gen.enabled and gen.slay_fame > 0 and content.figures:  # 決戰陣前擊退對面的龍頭（Game._showdown_pay，generals）；待 joy 潤
        lines.append(f"決戰裡給對面上陣的大勢人物最後一擊、把他打到敗走：+{gen.slay_fame}。")
    aid = cfg.figure_aid
    if aid.enabled and aid.guard_fame > 0 and content.figures:  # 護衛替人物擋下挑戰（Game._deliver_guard_credits，figure_aid）；待 joy 潤
        lines.append(f"護衛自己陣營的大勢人物，每替他擋下一次挑戰：+{aid.guard_fame}。")
    ring = cfg.arena
    if ring.enabled:  # 擂台賽（Game._arena_finish 的最險一搏、Game._deliver_arena 的每日俸與季末前三名）
        if ring.highlight_fame > 0:
            lines.append(f"擂台上放手一搏，成算不過 {ring.highlight_rate}% 卻成了：+{ring.highlight_fame}。")
        if ring.wages:  # 每天換日照名次發俸（Game._deliver_arena）
            lines.append(f"擂台每天的俸：第一名 +{ring.wages[0][1]}，前 {len(ring.wages)} 名都有。")
        if ring.prizes:
            lines.append("擂台賽季末前三名：" + "、".join(f"第{'一二三四五'[i]}名 +{fame}" for i, fame in enumerate(ring.prizes)) + "。")
    land = cfg.conquest
    if conquest.on(content, season) and land.take_fame > 0:  # 翻地與爭搶的分紅、守城功（Game._deliver_conquest）；待 joy 潤
        lines.append(f"一塊地推滿易手，推過的人照出力分名望：中立地一塊總共 +{land.take_fame}，敵方的領地 "
                     f"+{round(land.take_fame * land.faction_pool_share)}；守方把五成以上的進度拉回零，照拉回的分守城功（再打"
                     f"{_tenth(land.guard_pool_share)}）。")
    from . import tavern  # noqa: PLC0415  酒肆（Game._tavern_treat 請酒、Game._tavern_hit_fight 打退殺手）；待 joy 潤
    if tavern.on(content):
        bar = cfg.tavern
        if bar.treat_fame > 0:
            lines.append(f"在酒肆請全店喝一輪：+{bar.treat_fame}（一天一次）。")
        if bar.hit_win_fame > 0:
            lines.append(f"打退別人雇來找你的殺手：+{bar.hit_win_fame}。")
    return lines


def _fame_uses(content: Content, k: float = 1.0, season: WorldState | None = None) -> str:
    """名望拿來做什麼：求見與拜師的門檻乘 k（名聲開著時是這一季的倍數，rules.audience_parts、library 照同一個算法）。
    一類一顆在這一季生效時求見併進交友、不夠的見不到（FB-422）。"""
    cfg = content.config
    scaled = lambda n: int(n * k + 0.5)  # noqa: E731
    bars = sorted(ch.audience_fame for ch in content.characters.values() if ch.deep_interaction and ch.audience_fame > 0)
    uses = []
    if bars:
        span = f"門檻最低 {scaled(bars[0])}、最高 {scaled(bars[-1])}"
        uses.append(f"跟大勢人物說上話（{span}；不夠的見不到）" if precise.on(content, season)
                    else f"求見大勢人物（{span}；不夠的會打發你）")
    lessons = sorted(s.learn.fame for s in content.skills.values() if s.learn is not None and s.learn.fame > 0)
    if lessons:
        uses.append(f"有些師父要名望 {scaled(lessons[0])} 以上才肯教")
    return f"名望拿來：{'；'.join(uses)}。"


# 玩法說明「名聲」那一節（名聲設計第九節；名聲開著時取代「名望」）。待 joy 潤
RENOWN_INTRO = "江湖上用兩個稱號認你：一個看名望（江湖上多少人認得你），一個看善名、惡名（你是怎樣的人）。稱號寫在狀態列、玩家卡上；名望不加戰力。"
RENOWN_FAME = "名望稱號：{rows}。到了就換；名望掉回去，稱號也跟著掉。"
RENOWN_VIRTUE = "善惡稱號：善名比惡名高（一樣多也算）走俠，{xia}；惡名高走寇，{kou}。"
RENOWN_DEEDS = "立功也給名望：{deeds}。"
RENOWN_TOP = "決戰收場，兩軍各一位首功：+{n}。"
RENOWN_VIRTUE_FROM = "善名、惡名：事件裡的選擇；散人交懸賞，照你走的路記善名或惡名。"
RENOWN_RESONANCE = "身上的正派功法吃善名、邪派功法吃惡名：每點 +{per:g}%，最多 +{cap:g}%。"
RENOWN_PRACTICE = "惡名高的人做壞事手熟：有些檢定每 {per} 點惡名 +1，最多 +{cap}。"


def renown_lines(content: Content, season: WorldState) -> list[str]:
    """玩法說明「名聲」那一節：兩個稱號與這一季的門檻（renown.fame_bars／virtue_bars，長的季多一句倍數）、各段給什麼、
    名望從哪裡來（「名望」那一節的來源，加上立功與首功）與拿來做什麼（求見、拜師照倍數）、善名惡名從哪裡來、共鳴與熟練。"""
    cfg, rcfg = content.config, content.config.renown
    fb, vb = renown.fame_bars(content, season), renown.virtue_bars(content, season)
    ladder = lambda titles, bars: "、".join(f"{t} {at}" for t, at in zip(titles[1:], bars))  # noqa: E731
    lines = [
        RENOWN_INTRO,
        RENOWN_FAME.format(rows=ladder(renown.FAME_TITLES, fb)),
        RENOWN_VIRTUE.format(xia=ladder(renown.VIRTUE_TITLES["俠"], vb), kou=ladder(renown.VIRTUE_TITLES["寇"], vb)),
    ]
    note = renown.scale_note(season, content)
    if note:
        lines.append(note)
    for tier in range(1, len(fb) + 1):
        perks = renown.fame_perks(content, tier, season)
        if perks:
            lines.append(f"{renown.FAME_TITLES[tier]}：{'；'.join(perks)}。")
    for way in renown.PATHS:
        for tier in range(1, len(vb) + 1):
            perks = renown.virtue_perks(content, way, tier, season)
            if perks:
                lines.append(f"{renown.VIRTUE_TITLES[way][tier]}：{'；'.join(perks)}。")
    if renown.on(content, "deed_fame"):
        d = rcfg.deeds
        deeds = []
        if sortie.on(content) and d.get("sortie", 0) > 0:
            deeds.append(f"{sortie.NAME}攻打贏 +{d['sortie']}")
        if figures.challenge_on(content, season) and d.get("challenge", 0) > 0:
            deeds.append(f"挑戰大勢人物本人打贏 +{d['challenge']}")
        if d.get("showdown", 0) > 0:
            rout = f"（自己那一邊大勝再 +{d['showdown_rout']}）" if d.get("showdown_rout", 0) > 0 else ""
            deeds.append(f"決戰自己出手 +{d['showdown']}{rout}")
        if deeds:
            lines.append(RENOWN_DEEDS.format(deeds="、".join(deeds)))
    if cfg.battle.top_fame > 0:
        lines.append(RENOWN_TOP.format(n=cfg.battle.top_fame))
    lines += _fame_sources(content, season)
    lines.append(_fame_uses(content, renown.scale(season), season))
    lines.append(RENOWN_VIRTUE_FROM)
    if cfg.resonance_cap > 0:
        lines.append(RENOWN_RESONANCE.format(per=cfg.resonance_per_point * 100, cap=cfg.resonance_cap * 100))
    evil = cfg.practice_bonus.get("evil")
    if evil is not None and evil.cap > 0:
        lines.append(RENOWN_PRACTICE.format(per=evil.per, cap=evil.cap))
    return lines


# ── 投靠、軍令與三方（explain-2 第二項）──────────────────────────────


def _place_names(content: Content, ids: Sequence[str]) -> str:
    return "、".join(content.locations[i].name for i in ids if i in content.locations)


def join_lines(content: Content, season: WorldState) -> list[str]:
    """玩法說明「投靠與軍令」那一節：投靠（劇本有陣營才寫）；軍令、晉升、叛投只在第一季（orders、ranks、defection 都掛在開關後面）。"""
    cfg = content.config
    if not content.scenario.factions:
        return []
    allied = rules.haoqiang_allied(content, season)  # 豪強分屬兩軍的季：豪強先挑依附哪一邊、算那一邊的人（新寫）
    # FB-112：推線只說有些地方；散人與不是交戰兩軍的陣營（地方豪強，Joy 2026-10-13）可以在決戰的大區臨時投效兩軍之一，
    # 只算那一場（Game._free_agent、_enlist_options；不進投靠名冊、不算叛投）。決戰的職位這一版不寫（控制者裁示：戰鬥那條線還在改，戰場上本來就寫著）
    gentry = ("地方豪強要先挑依附官軍或黃巾，算那一邊的人，決戰也站那一邊。" if allied
              else "陣營不是交戰的兩軍時，跟散人一樣臨時投效。")
    lines = [
        "**投靠**：在陣營收人的地方按「投靠」，要再確認一次；也可以拜入陣營名下的門派。投靠之後，"
        f"{(CONQUEST_JOIN_DUEL if sortie_duel.on(content, season) else CONQUEST_JOIN) if sortie.on(content) else SOME_PLACES + '，推向你那一邊，遇上自己陣營的隊伍是操練'}"
        "；全服決戰替自己的陣營出戰，"
        f"{gentry}"
        "散人照樣能玩，只是沒有軍令與晉升；遇上決戰，人到了決戰的大區，可以臨時投效交戰兩軍之一，只算那一場，打完照樣是散人。",
    ]
    if not calendar.season_one_on(season, content):
        return lines
    from . import orders  # noqa: PLC0415  orders → timetable、figures：只有第一季的這幾行用到

    kinds = "、".join(orders.KIND_NAMES.values())
    # 湊滿額度那一刻的效果照 orders.json（FB-112：打擊不推線，是挫大勢人物的聲威）
    pushing = [orders.KIND_NAMES[k] for k in orders.KIND_NAMES if any(t.kind == k and t.effect.trend > 0 for t in content.orders.templates)]
    denting = [orders.KIND_NAMES[k] for k in orders.KIND_NAMES
               if any(t.kind == k and t.effect.figure_prestige < 0 for t in content.orders.templates)]
    effects = [f"{'、'.join(pushing)}推一把戰況"] if pushing else []
    effects += [f"{'、'.join(denting)}挫大勢人物的聲威"] if denting else []
    met = f"全陣營湊滿額度的那一刻一起見效（{'，'.join(effects)}）" if effects else "全陣營湊滿額度的那一刻一起見效"
    lines += [
        # 軍令每天一道的季（21 天季、7 天濃縮季）：「每天發令」「今日的軍令卡」（calendar.week_word，FB-501、FB-502）
        f"**軍令**：{calendar.week_word('order_each', content, season)}發令（{kinds}，各陣營拿到的不一樣），照做一次記一次功；{met}。"
        f"{calendar.week_word('order_this', content, season)}的軍令卡在江湖頁行動列底下。",
        f"**晉升**：替陣營出力記貢獻（推 1 點戰況記 {cfg.contrib_per_push}），到 {cfg.rank2_contrib} 會有人召見，去應召就晉升；"
        f"自己陣營的大勢人物，你每晉升一階，求見他的門檻就低 {cfg.audience_rank_discount}。"
        + f"地方豪強最多做到第 {allied_rules.CAP_RANK} 階。",
        "**叛投**：一季一次，到別的陣營收人的地方叛投；晉升、召見、部下、這一季的貢獻歸零，屬性、武學、同伴、銀兩不動。"
        + "換依附的一邊、豪強與同一邊的官軍或黃巾互換，也算叛投。",
    ]
    return lines


def faction_lines(content: Content, season: WorldState) -> list[str]:
    """玩法說明「三方有什麼不同」：每個陣營在哪裡投靠、往哪裡推、拿得到哪幾種軍令、守勢與晉升之後多的行動、頭銜。
    全照內容（劇本的陣營與目標、orders.json 的軍令範本、守勢行動、第 2 階行動、第 3、4 階行動）與 ranks.TITLES；第一季才有。"""
    if not calendar.season_one_on(season, content) or not content.scenario.factions:
        return []
    from . import orders, ranks  # noqa: PLC0415  第一季的這一節才用到

    fronts = set(rules.front_ids(content))
    pushers = _order_pushers(content)
    out = []
    for faction in content.scenario.factions:
        fid = faction.id
        goals = faction.goals
        pushed = {d for key, d in goals.items() if key in fronts}
        if faction.allies:  # 豪強分屬兩軍：豪強那一列另寫
            titles = [t for t in ranks.TITLES.get(fid, []) if t][:allied_rules.CAP_RANK]
            where = _place_names(content, faction.join_at)
            head = f"**{faction.name}**" + (f"（在{where}投靠）" if where else "")
            sides = "或".join(a.name for a in allied_rules.allies_of(content, fid))
            duty = content.orders.duties.get(fid)
            acts = [f"在戰線上的差事是「{duty.name}」"] if duty is not None else []
            acts += [f"第 {a.rank} 階起多「{a.name}」" for a in sorted(content.orders.rank_actions, key=lambda a: a.rank)
                     if a.faction == fid and a.rank <= allied_rules.CAP_RANK]
            title = f"；頭銜從{titles[0]}做到{titles[-1]}（第 {allied_rules.CAP_RANK} 階為止）" if len(titles) > 1 else ""
            out.append(f"{head}：依附{sides}，照那一邊推戰線、接那一邊的軍令；{'，'.join(acts) or '沒有額外的行動'}{title}。")
            continue
        if pushed:
            side = STANCE_NAMES["guan"] if pushed == {-1} else STANCE_NAMES["huang"] if pushed == {1} else "各自"
            aim = f"把戰線往{side}那一邊推"
        else:
            aim = "照地方本來的方向推"
        kinds = [orders.KIND_NAMES[k] for k in orders.KIND_NAMES if any(t.kind == k and t.side == fid for t in content.orders.templates)]
        orders_text = (f"軍令只有{kinds[0]}" if len(kinds) == 1 else f"軍令有{'、'.join(kinds)}") if kinds else "沒有軍令"
        if kinds and fid not in pushers:  # 豪強只有打擊：湊滿額度是挫大勢人物的聲威，不推線（FB-112）
            orders_text += "，不推戰線"
        acts = []
        duty = content.orders.duties.get(fid)
        if duty is not None:
            acts.append(f"在戰線上的差事是「{duty.name}」")
        rank2 = content.orders.rank2.get(fid)
        if rank2 is not None:
            acts.append(f"第 2 階起多「{rank2.name}」")
        acts += [f"第 {a.rank} 階起多「{a.name}」" for a in sorted(content.orders.rank_actions, key=lambda a: a.rank) if a.faction == fid]
        titles = [t for t in ranks.TITLES.get(fid, []) if t]
        title = f"；頭銜從{titles[0]}做到{titles[-1]}" if len(titles) > 1 else ""
        where = _place_names(content, faction.join_at)
        head = f"**{faction.name}**" + (f"（在{where}投靠）" if where else "")
        out.append(f"{head}：{aim}。{orders_text}；{'，'.join(acts) or '沒有額外的行動'}{title}。")
    return out


def season_page_lines(content: Content, season: WorldState, rule: str = "") -> list[str]:
    """玩法說明「這一季在打什麼」：跟點戰況、態勢、大事、主線看的是同一套句子（不看此刻的戰況），加上收季規則（rule＝
    rules.stance_rule_note，呼叫端照這一季算好）。第一季才有。"""
    if not calendar.season_one_on(season, content):
        return []
    lines = [season_line(content), front_rule(content, card=False), allied_rule(content), *board_help(content)]
    if rule:
        lines.append(f"收季：{rule}")
    lines += quest_help(content, season)
    lines.append("江湖頁最上面的「態勢」「大事」「主線」與底下的戰況圖卡，點開都有說明。")
    return lines


MALL_TITLE = "商城"  # 玩法說明那一節的標題（商城第三批）；以下待 joy 潤
MALL_WHERE = "齒輪旁的元寶鈕、底部的「寶」都打開商城，架上的東西花元寶買；買過的、元寶的進出在「紀錄」那一頁查得到。"
MALL_COIN = "元寶只能儲值取得，不能拿銀兩換，也換不成銀兩。"
MALL_BETA = "這一版是封閉測試：每個角色第一次進來先撥 {n} 元寶（只發一次，之後開新的一季也不再發），正式開服時清空。"
MALL_CARD = "月卡：有效的那幾天，每天能服的{pill}多 {bonus} 顆（{caps}）。買的那一天算第一天；還沒到期再買，從到期日往後接。"


def mall_lines(content: Content) -> list[str]:
    """玩法說明「商城」那一節（商城架構設計 4.2、4.5；商城第三批）：入口、元寶怎麼來、封測發放（Config.mall.beta_grant，0 不寫）、
    月卡（架上有月卡、回體丹一天有上限才寫；上限照 Config，跟 Game.pill_cap 加的同一份 card_pill_bonus）。不看個人：
    這個人此刻的上限寫在點體力條看的那幾句（stamina_lines 的 card，FB-480）。商城關著是空的（玩法說明一個字都不提）。"""
    if not mall.on(content):
        return []
    cfg = content.config
    lines = [MALL_WHERE, MALL_COIN]
    if cfg.mall.beta_grant > 0:
        lines.append(MALL_BETA.format(n=cfg.mall.beta_grant))
    bonus = cfg.mall.card_pill_bonus
    sells_card = any("card_days" in item.effects for item in content.mall.values())
    if sells_card and bonus > 0 and cfg.stamina_pills_per_day > 0:
        caps = [f"平常 {cfg.stamina_pills_per_day} → {cfg.stamina_pills_per_day + bonus}"]
        caps += [f"新手期 {cfg.newbie_pills_per_day} → {cfg.newbie_pills_per_day + bonus}"] * (cfg.newbie_pills_per_day > 0)
        lines.append(MALL_CARD.format(pill=cfg.stamina_pill_name, bonus=bonus, caps="、".join(caps)))
    return lines


def pages_lines() -> list[str]:
    """玩法說明「修練與煉製」：底部兩個分頁各做什麼（修練頁 pagePractice、煉製頁 pageCraft 的實際內容）。價錢寫在「心得」那一節。"""
    return [
        "**修練**：最上面是你的人物，點身上的光點看那一門功夫或那一件裝備。練成（花心得升一成）、每一門底下的意境槽（點空格裝意境、"
        "點 × 拆下，隨時換；槽收得下的屬性才裝得進去）、改練、熔掉用不上的武學與意境（拿回心得；功法庫上頭的「批量熔煉」一次勾一堆）、"
        "閉關、療傷（只在有醫館的城鎮）；上品、練滿十成的武學才有「修練」那一顆：等打贏硬仗的契機，或服破境丹強行衝關；"
        "底下是裝備（兵器、防具、坐騎、寶物）、同伴與部下（心得夠了可以傳功給他們）。",
        "**煉製**：太極火爐只放意境：兩個不同的意境合出新的意境、同一種的兩份揣摩得更深；放進爐裡的都不會用掉。"
        "武學不拿來合，意境到「修練」去裝進武學的槽。爐子底下的「自創武學」另開一頁，花心得自創一門上品武學"
        "（執器、擺式、立意、成形、立名五步；按下立意就收心得、擱下不退，成了形不滿意可以用萬寶閣的重悟帖重骰形、或重讀那一句意）。每一門功夫都有自己的一手招，功法卡上招名前面蓋一枚印：學來的蓋「看家」、"
        "人物的本命蓋「本命」、自創的蓋你名號的第一個字、練成絕學的絕招蓋金色的「絕」。"  # 待 joy 潤
        "最底下是背包。",
    ]


# ── 設定抽屜的「玩法說明」（explain-1 第四項）──────────────────────────────


def _kind_name(tags: Sequence[str]) -> str:
    """一種地點類型（Config.explore_mix 的一筆）怎麼叫：照它的標籤（三個以上寫「等地」）；沒有標籤的是「其他地方」。"""
    if not tags:
        return "其他地方"
    return "、".join(tags[:3]) + ("等地" if len(tags) > 3 else "")


def mix_sentence(content: Content) -> str:
    """玩法說明裡探索的比例：每一種地點類型一句「營寨、祭壇、塢堡多半碰上事件，也可能遇野怪、悟意境」——跟探索擲骰讀同一份
    Config.explore_mix（還沒扣掉「這裡做不了」的支：那是行動列底下那一行的事）。"""
    return "；".join(
        _kind_name(mix.tags) + explore_line(list(mix.weights.items())).removeprefix("這裡") for mix in content.config.explore_mix
    )


def _section(title: str, lines: Sequence[str]) -> list[str]:
    """一節：標題與每一行一個項目；沒有句子就整節不寫。"""
    return [f"#### {title}", *[f"- {line}" for line in lines], ""] if lines else []


# 挑戰大勢人物（挑戰每季都有設計 3.9，待 joy 潤）：沒有時刻表的季多寫的幾句；數字從 Config 讀，回復、上限是 0 時不寫那半句
CHALLENGE_UNTIMED = (
    "- 打贏一次他的聲威掉 {n}；沒人去打，聲威會慢慢回來。",
    "- 每位人物一天最多被打掉 {cap} 點聲威。",
    "- 聲威掉到 0 就退場，這一季不再出現。",
    "- {names}退場之後，不再替自己那一方出力。",
)
CHALLENGE_SEASON21_REGEN = "- 沒人去打，大勢人物的聲威會慢慢回來（一天回 {n} 點）。"  # 待 joy 潤：21 天季的第一季（正式季整合 3.9）


# 玩法說明「挑戰大勢人物」那一段（FB-190：以前插在「情誼」中間，最後那句「換季只帶一成」讀起來像在講聲威）。待 joy 潤
CHALLENGE_TITLE = "挑戰大勢人物"
CHALLENGE_WHO = "- 投靠了陣營的人，可以在敵方大勢人物所在的地方挑戰他本人（按鈕上寫勝算，體力同{act}）；自己陣營的人物不打{both}，散人不能挑戰。"
CHALLENGE_BOTH = "，{names}兩邊的人物都能挑戰"
CHALLENGE_SNUB = "- 打贏之後 {hours:g} 個現實小時內，他閉門不見：挑戰、求見、交友都不行。"


CHALLENGE_RISE = "- 你的隊伍越強，大勢人物越拚命：他照你們的身手出全力，這一季每被你打贏一次，下一次就更難打。鈕上的勝算照這個算。"
CHALLENGE_DRAW = "- 跟他打成平手也不白打：拿得到打贏的一半心得與經驗，也算一次頓悟的契機；不掉東西、他的聲威不動、情誼也不扣。"


def _challenge_lines(content: Content, season: WorldState) -> list[str]:
    """挑戰大勢人物本人那一段（FB-190 另起一段）：誰能挑戰（有陣營、打敵方的人物，自己陣營沒有人物的〔地方豪強〕兩邊都打，散人不行；
    同 Game._challenge_options）、閉門不見、情誼會掉；沒有時刻表的季多寫聲威怎麼掉、怎麼回、一天上限、退場與龍頭人物停手。"""
    cfg = content.config
    if not figures.challenge_on(content, season):
        return []
    sides = {fig.faction for fig in content.figures.values()}
    # 豪強分屬兩軍的季：豪強照依附那一邊只打對面的人物（Game._challenge_options 照 _side），不寫「兩邊都打」
    both = [] if rules.haoqiang_allied(content, season) else [f.name for f in content.scenario.factions if f.id not in sides]
    act = sortie.NAME if sortie.on(content) else "遊歷"  # FB-251：出陣開著時寫「體力同出陣」（挑戰本人照舊讀 action_cost["train"]）
    lines = [CHALLENGE_WHO.format(both=CHALLENGE_BOTH.format(names="、".join(both)) if both else "", act=act)]
    if cfg.snub_hours > 0:
        lines.append(CHALLENGE_SNUB.format(hours=cfg.snub_hours))
    lines.append(f"- 打贏大勢人物本人，他對你的情誼會掉 {cfg.figure_defeat_affinity}。")
    if cfg.rise.enabled:
        lines.append(CHALLENGE_RISE)
    if cfg.figure_draw_share > 0:
        lines.append(CHALLENGE_DRAW)
    if not figures.untimed(content, season):
        if figures.upkept(content, season):  # 21 天季的第一季（正式季整合 3.9）：聲威會回、一天有上限；退場照時刻表與照舊的規矩
            if cfg.figure_prestige_regen > 0:
                lines.append(CHALLENGE_SEASON21_REGEN.format(n=f"{cfg.figure_prestige_regen:g}"))
            if cfg.figure_daily_loss_cap:
                lines.append(CHALLENGE_UNTIMED[1].format(cap=cfg.figure_daily_loss_cap))
        return lines
    first = CHALLENGE_UNTIMED[0].format(n=cfg.figure_defeat_prestige)
    lines.append(first if cfg.figure_prestige_regen > 0 else first.partition("；")[0] + "。")
    if cfg.figure_daily_loss_cap:
        lines.append(CHALLENGE_UNTIMED[1].format(cap=cfg.figure_daily_loss_cap))
    lines.append(CHALLENGE_UNTIMED[2])
    leaders = list(dict.fromkeys(sim.name for sim in content.scenario.sim_players if figures.by_name(content, sim.name)))
    if leaders:
        lines.append(CHALLENGE_UNTIMED[3].format(names="、".join(leaders)))
    return lines


def forge_lines(content: Content, season: WorldState) -> list[str]:
    """玩法說明「鐵匠鋪與神器」（待 joy 潤）：神器配方與線索照這一季開季時蓋的章寫（素材與經濟設計第二、三節；沒蓋章的季照舊的說法），
    殘譜照 Config.forge_secrets.scrap_every_mode。兵器、防具都關著是空的（整段不畫）。
    FB-268（PM 定，設計第九節「開關關著一個字都不變」）：只在新規則用得上時才畫——這一季蓋了每種兵器一條或線索分片的章，
    或線索分片、殘譜三種探索的開關開著；三個開關都關、季也沒蓋章時是空的（玩法說明跟改之前一字不差）。"""
    if not (equipment.on(content, "weapon") or equipment.on(content, "armor")):
        return []
    rule = content.config.forge_secrets
    if not (season.forge_divine_per_kind or season.forge_split_clues or rule.split_clues or rule.scrap_every_mode):
        return []
    lines = ["城鎮的鐵匠鋪賣兵器防具、修、淬煉，也能自己打造：照主料定階、輔料定屬性；打中這一季藏著的配方，打出名器。"]
    if any(r.divine for r in content.forge_secrets.values()):
        if season.forge_divine_per_kind and calendar.season_one_on(season, content):
            lines.append("每一種兵器這一季都有一條神器配方（防具一條）：全服第一把是原品、由你定名，之後照著打的是仿品。")
        elif season.forge_divine_per_kind:
            lines.append("神器配方照天機挑，同一種兵器最多一條：全服第一把是原品、由你定名，之後照著打的是仿品。")
        else:
            lines.append("這一季藏著幾條神器配方：全服第一把是原品、由你定名，之後照著打的是仿品。")
    if season.forge_split_clues:
        lines.append("神器配方的線索拆成三片：哪一種兵器、主料、輔料。在各家鐵匠鋪花了錢，鐵匠會順口說出他知道的片子（同一家說完之前不重複），"
                     "說書、殘譜也聽得到；三片湊齊，鑄譜上那一條就完整。")
    else:
        lines.append("配方的口訣聽說書、聽鐵匠順口、撿殘譜都聽得到，記在鑄譜上。")
    if rule.scrap_every_mode and explore_modes.on(content) and (rule.scrap_chance > 0 or content.config.secrets.scrap_chance > 0):
        lines.append("殘譜三種探索都撿得到。")
    return lines


def ambush_lines(content: Content) -> list[str]:
    """設伏劫道（Config.ambush，Joy 2026-10-30 打開）：開著才寫一行；數字讀設定。待 joy 潤"""
    from . import ambush  # noqa: PLC0415

    if not ambush.on(content):
        return []
    a = content.config.ambush
    return [
        f"- **設伏**（體力 {a.stamina}）：投靠了陣營、過了新手期，在兩頭都不是城鎮的路上守 {a.hours:g} 小時，敵對的人走過那一段"
        f"（步行、疾行都算，下線也照守）就打一場：贏的搶走輸的{_tenth(a.silver_share)}銀兩（最多 {a.silver_cap} 兩）與 {a.materials} 個素材，"
        "輸的扣氣血；伏兵輸了，埋伏就散了。守著的時候不能移動，可以隨時收伏。散人只劫得了自己揭了通緝的人。",
    ]


def page(content: Content, season: WorldState, *, recruitable: bool, rule: str = "") -> str:
    """設定抽屜的「玩法說明」（Markdown）：這一季在打什麼（第一季）、四個行動、體力、名望、投靠與軍令、三方有什麼不同（第一季）、
    情誼、心得、修練與煉製、意境、背包，各一兩句。數字全讀 Config（名望的範圍讀內容），句子不寫死。
    不看個人狀態（新手期還在不在、還有幾顆丹寫在體力條點開的說明），網頁每次攤開問一次。
    season：這一季（第一季才有的事只在第一季說；新手期照這一季蓋的季長換成現實時間）。recruitable：內容裡有沒有能招募的人物
    （正式內容現在沒有：不提招募）。rule：收季規則（rules.stance_rule_note，呼叫端照這一季算好；第一季才有）。"""
    cfg = content.config
    cost = cfg.action_cost
    first = calendar.season_one_on(season, content)
    allied = rules.haoqiang_allied(content, season)  # 豪強分屬兩軍的季（企劃者 2026-10-15）
    legend = f"每次探索還有機會撿到{cfg.legend_item_name}。" if cfg.explore_legend_chance > 0 else ""
    bond = [
        "- 跟人物談話，照你說的話漲跌；談話時他的名字旁邊寫著（"
        + ("交友名單上也有）。" if precise.on(content, season) else "求見名單上也有）。"),
        f"- 情誼到 {cfg.signature_affinity}，有些人物會把本命武學傳給你。",
    ]
    if first:
        # 片段只給做得了那條鏈的人（foreshadow.capable 要陣營對得上）：散人聽不到（審查 M4，待 joy 潤）
        bond.append("- 情誼夠深，他會跟你聊起一些風聲：機緣的話題，還有你那一邊的伏筆的片段（散人聽不到片段）。")
    if recruitable:
        gate = f"情誼到 {cfg.recruit_min_affinity} 才開得了口招攬，" if cfg.recruit_min_affinity > 0 else ""
        bond.append(f"- 想招攬的人，{gate}情誼越高成算越高（最多多 {cfg.recruit_affinity_bonus * 100:g} 個百分點）。")
    bond.append(f"- 換季只帶 {cfg.affinity_carry_ratio * 10:g} 成到下一季。")
    challenge = _challenge_lines(content, season)  # 挑戰大勢人物本人：每季都有（figures.challenge_on），另起一段（FB-190）
    old_train = [  # 出陣關著時的遊歷（出陣開著時換成 sortie_lines）
        # 操練看的是遇上的隊伍（Game._drills_with），不是地方：兩種都有的地方 _train 隨機挑一路（審查 M2）
        f"- **遊歷**（體力 {cost['train']}）：只在有隊伍的地方出現。遇上對手一定開打，按鈕上寫勝算：打贏得銀兩、心得、經驗，"
        "可能掉素材；每一場都會扣些氣血，輸了還會掉銀兩。遇上自己陣營的隊伍是操練：不打、不會輸，"
        f"得對手 {cfg.drill_reward_share * 10:g} 成的心得與經驗，不給銀兩、素材。兩種都有的地方，遇上誰看運氣。"
        f"有些地方打贏或操練還會{PUSH_WORD}（行動列底下那一行寫著這裡、今天還推不推得動）。",  # 審查 M4：不是「多半」（SOME_PLACES），待 joy 潤
    ]
    # 三選一關著時的探索（照地點比例自動抽；開著時換成 explore_lines）
    old_explore = [f"- **探索**（體力 {cost['explore']}）：照地點三選一：悟意境、遇野怪、碰上事件。{mix_sentence(content)}。偶有奇遇。{legend}"]
    sense_when = "靜心感悟" if explore_modes.on(content) else "探索落在悟意境"
    lines = [
        *_section("這一季在打什麼", season_page_lines(content, season, rule)),
        "#### 行動",
        *(explore_lines(content, season) if explore_modes.on(content) else old_explore),
        *(sortie_lines(content, allied, season) if sortie.on(content) else old_train),
        f"- **交友**（體力 {cost['socialize']}）：見這裡的人物談話（每輪體力 {cfg.talk_stamina}，同一位人物{day_every(content, season)}最多 "
        + (f"{cfg.talk_turns_per_day} 輪）。名望不夠的人物在名單上灰著，寫還差多少；交友的事在探索的{explore_modes.NAMES['seek']}裡。"
           if precise.on(content, season) else f"{cfg.talk_turns_per_day} 輪），或碰上交友的事。名望不夠的人物會打發你。"),
        "- **移動**：步行不花體力、只花時間；疾行立刻到、要花體力。步行時，每一段路可以邊走邊想、"
        + "沿途打聽、路邊採集各一次。",  # 全圖開放拿掉了留意地形
        *ambush_lines(content),
        "",
        "#### 體力",
        *[f"- {line}" for line in stamina_lines(content, season)],
        "- 點狀態列的體力條，也看得到這幾句。",
        "",
        *(_section("名聲", renown_lines(content, season)) if renown.on(content) else _section("名望", fame_lines(content, season))),
        *_section("投靠與軍令", join_lines(content, season)),
        *_section("各陣營有什麼不同", faction_lines(content, season)),
        *(_section("地盤", territory_lines(content, allied, season)) if territory.on(content) else []),
        "#### 情誼",
        *bond,
        "",
        *([f"#### {CHALLENGE_TITLE}", *challenge, ""] if challenge else []),
        "#### 心得",
        f"- 學武的本錢：練成（第 N 成升下一成花 N×{cfg.practice_xinde_per_level}）、"
        f"兩個意境合併（{cfg.merge_xinde} 心得、{cfg.merge_stamina} 體力）、自創武學都花它。",
        f"- 打贏、操練、閉關（每小時至少 {cfg.seclusion_xinde_per_hour}，悟性越高越多）、邊走邊想（{cfg.road_think_xinde}）都有心得；"
        "用不上的功法熔掉也能拿回一些。狀態列的 💡 會在你付得起、又真的有事可做時提醒你去哪一頁。",
        "",
        *_section("修練與煉製", pages_lines()),
        *_section("鐵匠鋪與神器", forge_lines(content, season)),
        "#### 意境",
        # 有所感（sensing.choose、sensing.menu）：選對了還要擲一次（rate，沒中給 sense_miss_xinde）；中了可以畫、也可以順其自然（審查 M2）
        # 選錯了要到換日才悟得出（sensing.missed_today；遊戲日跟著季長縮）：說明頁不看此刻，不寫「今天」，寫「一陣子」，時刻看卡上那一行
        f"- {sense_when}時「有所感」，先選做法："
        + (f"選錯了得 {cfg.sense_miss_xinde} 心得，那裡照樣悟得出；" if precise.on(content, season)
           else "選錯了，那裡要過一陣子才悟得出（選之前卡上就寫著要到什麼時候）；")
        + "選對了還要看機緣（沒抓住也有一點心得），"
        "抓住了可以畫一筆，也可以順其自然。哪裡悟得到什麼看地形。" + (STRONG_HOWTO if cfg.insight_strong.enabled else ""),
        *([TERRAIN_HOWTO] if cfg.terrain_arts.enabled and cfg.insight_strong.enabled else []),
        "- 善名、惡名夠高也會悟到意境。合併、揣摩都不會把意境用掉（自己熔掉才沒了）。",
        "- 意境就是技能：裝進武學的意境槽才生效，一個意境同時只能裝在一門上。武學的品級定槽數"
        f"（{'、'.join(f'{q} {n} 格' for q, n in cfg.arts.slots.items())}），也定威力的上限；槽只收那門武學相容的屬性（基礎武學什麼都收）。"
        f"悟到已經會的，化成 {cfg.duplicate_insight_xinde} 心得。",
        # 同效果好幾份（Joy 2026-10-22 選「第二份算半」；「玩家需要知道這個知識」）。照身上兩門一起算（traits.loadout）。待 joy 潤
        f"- 身上兩門武學的意境一起算：同一個效果第二份起算{'一半' if cfg.arts.stack_share == 0.5 else _tenth(cfg.arts.stack_share)}，"
        f"最多到上限的{'一倍半' if cfg.arts.stack_ceiling == 1.5 else f' {cfg.arts.stack_ceiling:g} 倍'}；"
        "同一個真意第二份多一半發動的機會"
        + (f"（本來就每次發動的{'、'.join(always)}改成多撐一回合）" if (always := [h.name for h in content.traits.high if (h.tactic.rate or 0) >= 1]) else "")
        + "，第三份起不再加。修練頁格子上寫著每一份算了幾成。",
        "- 同一個意境放兩次揣摩，強度從 ● 到 ●●●，就是那一招的層數；兩個不同的意境合出複合的意境，是更高階的一招。"
        "兩門武學合出第三門：品級取高的，兩門都練滿、槽都裝滿再升一品（最高上品），槽收的屬性是兩門合起來。",
        "",
        "#### 背包",
        "- 素材不進太極火爐：拿去鐵匠鋪當主料、輔料打兵器防具，修兵器、餵馬也用得上；第一季裡還折成糧草，押糧車、準備伏筆都要用。",
    ]
    economy = economy_lines(content, allied)
    if economy:  # 素材與經濟（收購、升階、捐軍備）：開著的才寫
        lines += ["", *_section(ECONOMY_TITLE, economy)]
    shop = mall_lines(content)
    if shop:  # 商城（商城第三批）：開著才寫，關著一個字都不變
        lines += ["", *_section(MALL_TITLE, shop)]
    return "\n".join(lines)

