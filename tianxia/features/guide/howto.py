"""玩法說明的底（全部拆包第 59 批「引導二」；原 tianxia/howto.py，字一個不動；計畫 docs/superpowers/plans/2026-11-06-玩法說明-第59批.md）：
狀態列體力條點開的說明與建角色送回體丹那一行、江湖頁戰況圖卡與態勢點開的說明（war_help）、名望與名聲怎麼來、設定抽屜那一頁的組裝（page）。
其餘每一節在各包自己的 howto.py，page 照核心的順序表 HOWTO_ORDER 接起來；別節中間判斷在別包的句子走 HOWTO_INSERTS。
這裡只把事實寫成字：數字一律讀 Config（或內容、規則模組的常數），不改狀態、不擲骰、不讀時鐘。所有句子待 joy 潤。"""
from __future__ import annotations

from tianxia import calendar, conquest, figures, precise, renown, rules, territory, timetable
from tianxia.core import features as features_core
from tianxia.core.howto_base import SOME_PLACES
from tianxia.core.howto_base import order_pushers as _order_pushers
from tianxia.core.howto_base import section as _section
from tianxia.core.howto_base import tenth as _tenth
from tianxia.models import Content
from tianxia.rules import STANCE_NAMES  # 態勢卡上三方的叫法（官軍、黃巾、豪強）：說明跟卡上同一個叫法
from tianxia.state import GameState, WorldState

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


SORTIE_RANGER = "散人不出陣，靠懸賞與事件出力"  # 出陣開著時（出陣探索與地盤設計第二節）；待 joy 潤


# 出陣（＝領地爭奪，第 38 項改版第一批）：出陣推的是那一塊的進度、戰線照佔領算——出陣開著時取代 SOME_PLACES 的幾處（待 joy 潤）
CONQUEST_PLACES = "在官軍、黃巾的領地與中立地出陣，推的是那一塊的進度，不直接推戰線"


CONQUEST_FRONTS = "戰線照兩軍佔了多少地來算：佔下中立地、打進敵方的領地，戰線就往那一邊偏"


def _sortie_places(content: Content, season: WorldState | None) -> str:
    """「你能做的」那一句的出陣怎麼推：出陣（＝領地爭奪）開著時推進度（CONQUEST_PLACES），沒有出陣的季照舊遊歷。"""
    return CONQUEST_PLACES if territory.on(content) else SOME_PLACES


def _pct(share: float) -> str:
    return f"{share * 10:g} 成"


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


def fronts_help(state: GameState, content: Content) -> list[str]:
    """戰況圖卡點開的說明：兩端、亂局帶、此刻哪幾條在亂局（rules.chaos_fronts）、玩家怎麼推（Game.train_trend_push：
    有 train_trend 的地方才推；官軍、黃巾往自己那一邊，散人照地方本來的方向，豪強往依附的那一邊；軍令達成時，軍令會推線的陣營
    整個推一把）。句子照內容（FB-112）。第一季才有（Game.status 的 war_help），豪強分屬兩軍。"""
    chaos = [rules.trend_name(content, f) for f in rules.chaos_fronts(state, content)]
    now = f"現在{'、'.join(chaos)}在亂局。" if chaos else "現在沒有戰線在亂局。"
    on = territory.on(content)
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
    from tianxia.events import is_rare  # noqa: PLC0415  過渡：待搬（events → rules → …：只有這裡用到）

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
                 else "探索、交友、找素材撞上的仗之後" if territory.on(content) else "探索、交友、遊歷之後")
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
    lines += features_core.howto_insert("fame_seal", content, season)  # 奪璽單挑那幾句：判斷在玉璽包（HOWTO_INSERTS）
    gen = cfg.battle.generals
    if gen.enabled and gen.slay_fame > 0 and content.figures:  # 決戰陣前擊退對面的龍頭（Game._showdown_pay，generals）；待 joy 潤
        lines.append(f"決戰裡給對面上陣的大勢人物最後一擊、把他打到敗走：+{gen.slay_fame}。")
    aid = cfg.figure_aid
    if aid.enabled and aid.guard_fame > 0 and content.figures:  # 護衛替人物擋下挑戰（大勢人物包 aid_actions.deliver_guard_credits，figure_aid）；待 joy 潤
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
    lines += features_core.howto_insert("fame_tavern", content, season)  # 酒肆那兩句：判斷在酒肆包（HOWTO_INSERTS）
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
        if territory.on(content) and d.get("sortie", 0) > 0:
            deeds.append(f"{territory.SORTIE_NAME}攻打贏 +{d['sortie']}")
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


# ── 設定抽屜的「玩法說明」（explain-1 第四項）──────────────────────────────


def season_section(content: Content, season: WorldState, rule: str) -> list[str]:
    """「這一季在打什麼」那一節（HOWTO_ORDER 的 season）。"""
    return _section("這一季在打什麼", season_page_lines(content, season, rule))


def act_head() -> list[str]:
    """「行動」的標題（act_head）：底下探索、出陣、交友、移動、設伏各是各包的格。"""
    return ["#### 行動"]


def stamina_section(content: Content, season: WorldState) -> list[str]:
    """「體力」那一節（stamina）：開頭多一個空行（接在行動那幾條後面）。"""
    return [
        "",
        "#### 體力",
        *[f"- {line}" for line in stamina_lines(content, season)],
        "- 點狀態列的體力條，也看得到這幾句。",
        "",
    ]


def fame_section(content: Content, season: WorldState) -> list[str]:
    """「名聲」或「名望」那一節（fame）。"""
    return _section("名聲", renown_lines(content, season)) if renown.on(content) else _section("名望", fame_lines(content, season))


def bag_section() -> list[str]:
    """「背包」那一節（bag）：沒有末尾空行。"""
    return [
        "#### 背包",
        "- 素材不進太極火爐：拿去鐵匠鋪當主料、輔料打兵器防具，修兵器、餵馬也用得上；第一季裡還折成糧草，押糧車、準備伏筆都要用。",
    ]


def page(content: Content, season: WorldState, *, recruitable: bool, rule: str = "") -> str:
    """設定抽屜的「玩法說明」（Markdown）：這一季在打什麼（第一季）、四個行動、體力、名望、投靠與軍令、三方有什麼不同（第一季）、
    情誼、心得、修練與煉製、意境、背包，各一兩句。數字全讀 Config（名望的範圍讀內容），句子不寫死。
    不看個人狀態（新手期還在不在、還有幾顆丹寫在體力條點開的說明），網頁每次攤開問一次。
    season：這一季（第一季才有的事只在第一季說；新手期照這一季蓋的季長換成現實時間）。recruitable：內容裡有沒有能招募的人物
    （正式內容現在沒有：不提招募）。rule：收季規則（rules.stance_rule_note，呼叫端照這一季算好；第一季才有）。"""
    lines: list[str] = []
    view = features_core.HowtoPage(recruitable=recruitable, rule=rule)
    for hook in features_core.howto_table():  # 順序就是行為：寫死在核心的 HOWTO_ORDER（第 59 批）
        lines += hook.lines(content, season, view)
    return "\n".join(lines)
