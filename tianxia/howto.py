"""玩法說明（explain-1，試玩回饋：Gary「很多東西要一句說明，不然體力用完了還不知道在玩什麼」）：

- 江湖頁行動列底下那幾行：探索、遊歷、交友這一下會怎樣（explore_line、train_line、social_line）；
- 狀態列體力條點開的說明（stamina_lines）與建角色時送回體丹的那一行（gift_line）；
- 江湖頁的戰況圖卡、態勢、大事、主線點開的說明（war_help，explain-2：這一季在打什麼、亂局與割據、大事怎麼定、你能怎麼出力）；
- 設定抽屜的「玩法說明」（page，Markdown）。

這裡只把事實寫成字：比重、獎勵、推不推戰局由呼叫端照引擎真正的規則算好傳進來（Game._explore_weights、遊歷的對手、
Game.train_trend_push），數字一律讀 Config（或內容、規則模組的常數），句子裡不寫死任何數。不改狀態、不擲骰、不讀時鐘。
所有句子待 joy 潤。"""
from __future__ import annotations

from collections.abc import Sequence

from . import calendar, rules, timetable
from .models import Content
from .rules import STANCE_NAMES  # 態勢卡上三方的叫法（官軍、黃巾、豪強）：說明跟卡上同一個叫法
from .state import GameState, WorldState

# 探索三選一的三支（models.EXPLORE_BRANCHES）在說明裡怎麼叫
BRANCH_WORDS: dict[str, str] = {"insight": "悟意境", "wild": "遇野怪", "event": "碰上事件"}
PUSH_WORD = "推動戰局"  # 遊歷打贏、操練會推大勢（第一季是戰線，豪強在亂局推割據）：一律這樣說，不露數字


def explore_line(
    weights: Sequence[tuple[str, float]], legend: str | None = None, blocked: bool = False, until: str | None = None,
) -> str:
    """探索這一下多半會怎樣。weights 是探索真的擲骰用的那一份（支, 比重）：照地點類型（Config.explore_mix）、
    做不了的已經拿掉、悟意境那一支乘過悟性（Game._explore_weights）。比重嚴格最大的那一支寫「多半」，其他寫「也可能」
    （照比重由大到小）；並列最大就一起寫「可能」；只剩一支寫「會」（FB-101）。不寫百分比。legend 是破境丹的名字（探索每次另擲一次撿不撿得到；
    機率是 0 時呼叫端給 None）。blocked：悟意境那一支只因為這個遊戲日在這裡選錯過做法才拿掉（Game._insight_blocked）；
    句尾補一句什麼時候才悟得出——until 是換日的那一刻（rules.day_ends_text，已經照季的時間寫法寫好），None 是這一季之內
    不會再換日（待 joy 潤）。"""
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
    tail = "" if not blocked else f"；這裡要到 {until} 之後才悟得出" if until else "；這一季之內這裡悟不出了"
    return head + (f"；偶得{legend}" if legend else "") + tail


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


def social_line(figure: str | None, events: bool, hall: bool) -> str:
    """交友這一下會遇上什麼。figure：會直接開口談話的那位（Game._socialize_figure）；events：這裡有交友事件；
    hall：這裡有兩位以上的人物（要按「求見」指名）。"""
    if figure is not None:
        return f"和{figure}談話，聊得投機情誼會漲"
    if events:
        return "結識這裡的人，碰上交友的事" + ("；要見人物按「求見」" if hall else "")
    return "這裡沒有見得到的人物，多半撲空"


CALL_LINE = "挑一位人物談話，聊得投機情誼會漲；名望不夠的會打發你"


def call_line(name: str, meet: bool) -> str:
    """選單上直接列的「求見某某」（這裡只有一位人物）：見得到就是談話；見不到會被打發（Game._brush_off：不花體力）。"""
    return f"和{name}談話，聊得投機情誼會漲" if meet else f"名望不夠，{name}會打發你（不花體力）"


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


def newbie_line(content: Content, season: WorldState, still: bool | None = None) -> str:
    """新手期體力回復加快（roster.newbie 的 newbie_stamina_days、newbie_stamina_multiplier）：第一季從自己加入的那一刻起算，beta 那一季
    從開季算，都是季曆天；寫成現實時間（季曆天 ÷ cal_scale ÷ time_scale，季長照這一季蓋的章）。倍數是 1 時沒有這一行（空字串）。
    still 給了就補一句還在不在這段時間裡。"""
    cfg = content.config
    if cfg.newbie_stamina_multiplier <= 1:
        return ""
    real = cfg.newbie_stamina_days * calendar.DAY / calendar.cal_scale(content, season) / cfg.time_scale
    since = "加入這一季後" if calendar.season_one_on(season, content) else "開季後"
    tail = "" if still is None else ("（你還在新手期）" if still else "（你的新手期已經過了）")
    span = _span(real)
    gap = "" if span.startswith("約") else " "  # 「開季後的 3 天內」「加入這一季後的約 13 個小時內」
    return f"新手期：{since}的{gap}{span}內，體力回復 ×{cfg.newbie_stamina_multiplier:g}{tail}。"


def rest_line(content: Content) -> str:
    """打坐（Game._advance_player_local：打坐中回復乘 rest_regen_multiplier，跟新手期疊乘）。"""
    cfg = content.config
    stack = "，跟新手期疊乘" if cfg.newbie_stamina_multiplier > 1 else ""
    return f"打坐時體力回復 ×{cfg.rest_regen_multiplier:g}{stack}；坐著不能做別的，隨時可以起身。"


def pill_line(content: Content, count: int | None = None) -> str:
    """體力條右端那顆鈕：測試期間一鍵補滿打開時（Config.beta_free_refill）是「補滿」，不花丹；關著時是回體丹，一顆回多少
    （count 給了就寫還有幾顆，0 顆沒有這一行；None 是玩法說明那種不看個人的說法）。"""
    cfg = content.config
    if cfg.beta_free_refill:
        return f"測試期間按體力條上的「{cfg.beta_free_refill_label}」直接補滿，不花{cfg.stamina_pill_name}。"
    if count is not None and count <= 0:
        return ""
    have = "" if count is None else f"（還有 {count} 顆）"
    return f"{cfg.stamina_pill_name}一顆回 {cfg.stamina_pill_restore} 點{have}，按體力條右端的「丹」服下。"


def stamina_lines(
    content: Content, season: WorldState, newbie: bool | None = None, pills: int | None = None, button: bool = True,
) -> list[str]:
    """體力條點開的說明（也是玩法說明「體力」那一節）：回復、新手期、打坐、回體丹或補滿。button：體力條上有沒有那顆鈕
    （序章裡沒有，就不提）。空的行不列。"""
    lines = [regen_line(content), newbie_line(content, season, newbie), rest_line(content)]
    if button:
        lines.append(pill_line(content, pills))
    return [line for line in lines if line]


def gift_line(content: Content) -> str:
    """建角色時送的回體丹（Config.beta_gift、beta_gift_stamina_pills），記在江湖紀錄開場那一則的一行（建角色那一刻寫下）。
    測試期一鍵補滿打開時（Config.beta_free_refill），體力條那顆鈕寫 beta_free_refill_label、不花丹：說丹先收著、按那顆鈕免費補滿
    （控制者走查）；關著時說按「丹」服下。兩句都待 joy 潤。"""
    cfg = content.config
    name, n, restore = cfg.stamina_pill_name, cfg.beta_gift_stamina_pills, cfg.stamina_pill_restore
    if cfg.beta_free_refill:
        return (f"內測贈禮：{name} {n} 顆（一顆回 {restore} 點體力），先收著；"
                f"測試期間按體力條上的「{cfg.beta_free_refill_label}」就能免費補滿，不花丹。")
    return f"內測贈禮：{name} {n} 顆，一顆回 {restore} 點體力，按體力條右端的「丹」服下。"


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
    """這一季在打什麼（第一季設計第一、四節）：劇本名、官軍與黃巾爭的幾條戰線、豪強割據。"""
    fronts = [rules.trend_name(content, f) for f in rules.front_ids(content)]
    guan, huang, hao = (STANCE_NAMES[k] for k in ("guan", "huang", "haoqiang"))
    return (f"這一季是{content.scenario.name}：{guan}與{huang}在{_count(len(fronts))}條戰線上爭（{'、'.join(fronts)}），"
            f"{hao}趁亂割據。")


# 亂局帶與割據的規則各只寫一次（審查 Minor 7）：態勢、戰況圖卡、玩法說明「這一季在打什麼」都拿這兩句，改一處三處一起變


def front_rule(content: Content, card: bool = True) -> str:
    """戰線的兩端與亂局帶（rules.in_chaos：chaos_low～chaos_high，含兩端）。card：在戰況圖卡上說（指著條上淺色那一段）。"""
    guan, huang, hao = (STANCE_NAMES[k] for k in ("guan", "huang", "haoqiang"))
    shade = "（條上淺色那一段）" if card else ""
    return f"每條戰線 0 是{guan}穩控、100 是{huang}控制；戰況落在 {_band(content)} 是亂局{shade}，{hao}趁機割據。"


def geju_rule(content: Content) -> str:
    """三方的態勢怎麼算（rules.stances）與割據怎麼漲落（rules.geju_per_day：有戰線在亂局就漲、乘投靠人數的係數，一條都沒有就落）。
    漲、落的速度設成 0 時照實說不動；此刻漲還是落，態勢面板上本來就有一句（status.stance_notes 的 chaos_note），這裡只寫規則。"""
    cfg = content.config
    n = _count(len(rules.front_ids(content)))
    guan, huang, hao = (STANCE_NAMES[k] for k in ("guan", "huang", "haoqiang"))
    rise = "就漸長，投靠陣營的人越多長得越快" if cfg.geju_chaos_per_day > 0 else "也不漲"
    calm = "就漸消" if cfg.geju_calm_per_day > 0 else "就停住"
    return (f"{guan}、{huang}的態勢是{n}條戰線合起來的；{hao}的態勢是割據：有戰線在亂局（戰況 {_band(content)}）{rise}，"
            f"{n}條都穩下來{calm}。")


def stance_help(content: Content) -> list[str]:
    """態勢小標點開的說明：這一季在打什麼、三方的態勢怎麼算、割據怎麼漲落。"""
    return [season_line(content), geju_rule(content)]


def fronts_help(state: GameState, content: Content) -> list[str]:
    """戰況圖卡點開的說明：兩端、亂局帶、此刻哪幾條在亂局（rules.chaos_fronts）、玩家怎麼推（Game.train_trend_push：
    官軍、黃巾往自己那一邊，散人照地方本來的方向，豪強只在亂局裡推割據；軍令達成時整個陣營推一把）。"""
    hao = STANCE_NAMES["haoqiang"]
    chaos = [rules.trend_name(content, f) for f in rules.chaos_fronts(state, content)]
    now = f"現在{'、'.join(chaos)}在亂局。" if chaos else "現在沒有戰線在亂局。"
    return [
        front_rule(content) + now,
        # 一個人照做軍令不推戰線，全陣營湊滿額度那一刻才推（orders.credit，審查 Minor 5）
        f"在戰線上遊歷打贏、操練，會把那條戰線往你陣營那一邊推，軍令湊滿額度時整個陣營再推一把；散人照那個地方本來的方向，"
        f"{hao}只在亂局裡推割據。",
    ]


def _lockable(content: Content) -> int:
    """關鍵伏筆改寫得了的大事有幾件：官軍、黃巾的鏈指著的那幾件（豪強的鏈是第三方，不改寫結果，foreshadow 文件 2.4）。"""
    sides = {"guan", "huang"}
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


def quest_help(content: Content) -> list[str]:
    """主線小標點開的說明：你能怎麼影響這一季（遊歷、軍令、伏筆）。"""
    return [
        "你能做的：在戰線上遊歷打贏、操練，推動戰況；投靠陣營之後每週一有軍令，照做記功，全陣營湊滿額度就一起推一把；"
        "聽傳聞、跟人物交好，湊齊關鍵伏筆，能暗中改寫一件大事。",
    ]


def war_help(state: GameState, content: Content) -> dict[str, list[str]]:
    """江湖頁四個地方點開的說明（status.war_help）：stance＝態勢小標、fronts＝戰況圖卡、board＝大事小標、quest＝主線小標。"""
    return {
        "stance": stance_help(content),
        "fronts": fronts_help(state, content),
        "board": board_help(content),
        "quest": quest_help(content),
    }


# ── 名望怎麼來（explain-2 第二項，FB-100「名望不知道怎麼來」）──────────────────────────
# 引擎裡真的給名望的只有三條路：事件的效果（rules.apply_effect，內容寫的 stats.fame）、第一季的首創回饋（Game._deliver_echoes，
# Config.first_echo）、決戰最有戲的那一搏（Game._file_showdown，BattleTuning.highlight_fame）。事件照種類分三堆、照內容算出範圍（一個一個列出來沒有用）；這一季關掉的 beta 事件（season_one_off）不算。

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
    """玩法說明「名望」那一節：從哪裡來（事件三堆、第一季的首創回饋、決戰最有戲的那一搏）、拿來做什麼（求見門檻、視野、拜師學藝）。數字讀內容與設定。"""
    cfg = content.config
    spans = fame_ranges(content, season)
    lines = []
    if "common" in spans:
        lines.append(f"事件裡出頭、仗義、露臉的做法（探索、交友、遊歷之後碰上的事）：一次 {_plus(spans['common'])}。")
    if "big" in spans:
        lines.append(f"劇情裡打贏強敵、奇遇與一次性的大事：一次 {_plus(spans['big'])}。")
    if "loss" in spans:
        most, least = spans["loss"]
        lines.append(f"檢定失手、做了丟臉的事會掉：{-least}～{-most}。" if most != least else f"檢定失手、做了丟臉的事會掉 {-most}。")
    echo = cfg.first_echo
    if calendar.season_one_on(season, content) and echo.fame_per > 0:
        lines.append(f"你首創的武學或意境，別人照著合出同一門：每多一個人 +{echo.fame_per}，一門最多算 {echo.cap} 個人。")
    if cfg.battle.highlight_fame > 0:
        lines.append(f"決戰裡放手一搏，成了、而且是那一仗最有戲的一幕：+{cfg.battle.highlight_fame}。")
    bars = sorted(ch.audience_fame for ch in content.characters.values() if ch.deep_interaction and ch.audience_fame > 0)
    uses = []
    if bars:
        uses.append(f"求見大勢人物（門檻最低 {bars[0]}、最高 {bars[-1]}；不夠的會打發你）")
    uses.append(f"名望到 {cfg.vision_fame}，輿圖多看一站")
    lessons = sorted(s.learn.fame for s in content.skills.values() if s.learn is not None and s.learn.fame > 0)
    if lessons:
        uses.append(f"有些師父要名望 {lessons[0]} 以上才肯教")
    lines.append(f"名望拿來：{'；'.join(uses)}。")
    return lines


# ── 投靠、軍令與三方（explain-2 第二項）──────────────────────────────


def _place_names(content: Content, ids: Sequence[str]) -> str:
    return "、".join(content.locations[i].name for i in ids if i in content.locations)


def join_lines(content: Content, season: WorldState) -> list[str]:
    """玩法說明「投靠與軍令」那一節：投靠（劇本有陣營才寫）；軍令、晉升、叛投只在第一季（orders、ranks、defection 都掛在開關後面）。"""
    cfg = content.config
    if not content.scenario.factions:
        return []
    lines = [
        "**投靠**：在陣營收人的地方按「投靠」，要再確認一次；也可以拜入陣營名下的門派。投靠之後，遊歷打贏、操練把戰況推向你那一邊，"
        "遇上自己陣營的隊伍是操練；全服決戰只能替自己的陣營出戰。散人照樣能玩，只是沒有軍令與晉升。",
    ]
    if not calendar.season_one_on(season, content):
        return lines
    from . import orders  # noqa: PLC0415  orders → timetable、figures：只有第一季的這幾行用到

    kinds = "、".join(orders.KIND_NAMES.values())
    lines += [
        f"**軍令**：每週一發令（{kinds}，各陣營拿到的不一樣），照做一次記一次功；全陣營湊滿額度的那一刻，整個陣營一起推一把。"
        "本週的軍令卡在江湖頁行動列底下。",
        f"**晉升**：替陣營出力記貢獻（推 1 點戰況記 {cfg.contrib_per_push}），到 {cfg.rank2_contrib} 會有人召見，去應召就晉升；"
        f"自己陣營的大勢人物，你每晉升一階，求見他的門檻就低 {cfg.audience_rank_discount}。",
        "**叛投**：一季一次，到別的陣營收人的地方叛投；晉升、召見、部下、這一季的貢獻歸零，屬性、武學、同伴、銀兩不動。",
    ]
    return lines


def faction_lines(content: Content, season: WorldState) -> list[str]:
    """玩法說明「三方有什麼不同」：每個陣營在哪裡投靠、往哪裡推、拿得到哪幾種軍令、守勢與晉升之後多的行動、頭銜。
    全照內容（劇本的陣營與目標、orders.json 的軍令範本、守勢行動、第 2 階行動、第 3、4 階行動）與 ranks.TITLES；第一季才有。"""
    if not calendar.season_one_on(season, content) or not content.scenario.factions:
        return []
    from . import orders, ranks  # noqa: PLC0415  第一季的這一節才用到

    fronts = set(rules.front_ids(content))
    out = []
    for faction in content.scenario.factions:
        fid = faction.id
        goals = faction.goals
        pushed = {d for key, d in goals.items() if key in fronts}
        if pushed:
            side = STANCE_NAMES["guan"] if pushed == {-1} else STANCE_NAMES["huang"] if pushed == {1} else "各自"
            aim = f"把戰線往{side}那一邊推"
        elif rules.GEJU in goals:
            aim = "不推戰線，戰線在亂局時遊歷、操練推割據"
        else:
            aim = "照地方本來的方向推"
        kinds = [orders.KIND_NAMES[k] for k in orders.KIND_NAMES if any(t.kind == k and t.side == fid for t in content.orders.templates)]
        orders_text = (f"軍令只有{kinds[0]}" if len(kinds) == 1 else f"軍令有{'、'.join(kinds)}") if kinds else "沒有軍令"
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
    lines = [season_line(content), front_rule(content, card=False), geju_rule(content), *board_help(content)]
    if rule:
        lines.append(f"收季：{rule}")
    lines += quest_help(content)
    lines.append("江湖頁最上面的「態勢」「大事」「主線」與底下的戰況圖卡，點開都有說明。")
    return lines


def pages_lines() -> list[str]:
    """玩法說明「修練與煉製」：底部兩個分頁各做什麼（修練頁 pagePractice、煉製頁 pageCraft 的實際內容）。價錢寫在「心得」那一節。"""
    return [
        "**修練**：身上的內功與武學。練成（花心得升一成）、修練（融過意境的武學，拿它融的那個意境衝品質，花體力）、改練、"
        "熔掉用不上的武學與意境（拿回心得）、閉關；也看得到同伴與人物卡。",
        "**煉製**：太極火爐。一門武學＋一個意境合出新武學、兩門武學合出第三門、兩個意境合出新的意境；放進爐裡的都不會用掉。"
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


def page(content: Content, season: WorldState, *, recruitable: bool, rule: str = "") -> str:
    """設定抽屜的「玩法說明」（Markdown）：這一季在打什麼（第一季）、五個行動、體力、名望、投靠與軍令、三方有什麼不同（第一季）、
    情誼、心得、修練與煉製、意境、背包，各一兩句。數字全讀 Config（名望的範圍讀內容），句子不寫死。
    不看個人狀態（新手期還在不在、還有幾顆丹寫在體力條點開的說明），網頁每次攤開問一次。
    season：這一季（第一季才有的事只在第一季說；新手期照這一季蓋的季長換成現實時間）。recruitable：內容裡有沒有能招募的人物
    （正式內容現在沒有：不提招募）。rule：收季規則（rules.stance_rule_note，呼叫端照這一季算好；第一季才有）。"""
    cfg = content.config
    cost = cfg.action_cost
    first = calendar.season_one_on(season, content)
    legend = f"每次探索還有機會撿到{cfg.legend_item_name}。" if cfg.explore_legend_chance > 0 else ""
    bond = [
        "- 跟人物談話，照你說的話漲跌；談話時他的名字旁邊寫著（求見名單上也有）。",
        f"- 情誼到 {cfg.signature_affinity}，有些人物會把本命武學傳給你。",
    ]
    if first:
        bond.append("- 情誼夠深，他會跟你聊起一些風聲：伏筆的片段、機緣的話題。")
    if recruitable:
        bond.append(f"- 想招攬的人，情誼越高成算越高（最多多 {cfg.recruit_affinity_bonus * 100:g} 個百分點）。")
    if first:  # 挑戰大勢人物本人只有第一季才有（Game._challenge）
        bond.append(f"- 打贏大勢人物本人，他對你的情誼會掉 {cfg.figure_defeat_affinity}。")
    bond.append(f"- 換季只帶 {cfg.affinity_carry_ratio * 10:g} 成到下一季。")
    lines = [
        *_section("這一季在打什麼", season_page_lines(content, season, rule)),
        "#### 行動",
        f"- **探索**（體力 {cost['explore']}）：照地點三選一：悟意境、遇野怪、碰上事件。{mix_sentence(content)}。偶有奇遇。{legend}",
        # 操練看的是遇上的隊伍（Game._drills_with），不是地方：兩種都有的地方 _train 隨機挑一路（審查 M2）
        f"- **遊歷**（體力 {cost['train']}）：只在有隊伍的地方出現。遇上對手一定開打，按鈕上寫勝算：打贏得銀兩、心得、經驗，"
        "可能掉素材；每一場都會扣些氣血，輸了還會掉銀兩。遇上自己陣營的隊伍是操練：不打、不會輸，"
        f"得對手 {cfg.drill_reward_share * 10:g} 成的心得與經驗，不給銀兩、素材。兩種都有的地方，遇上誰看運氣。"
        f"打贏或操練多半還會{PUSH_WORD}（行動列底下那一行寫著這裡、今天還推不推得動）。",
        f"- **打坐**：坐下來體力回復 ×{cfg.rest_regen_multiplier:g}，期間不能做別的；隨時起身，回滿了自己起身。",
        f"- **交友**（體力 {cost['socialize']}）：見這裡的人物談話（每輪體力 {cfg.talk_stamina}，同一位人物{day_every(content, season)}最多 "
        f"{cfg.talk_turns_per_day} 輪），或碰上交友的事。名望不夠的人物會打發你。",
        "- **移動**：步行不花體力、只花時間；趕路快一些、疾行立刻到，兩種都花體力。步行、趕路時，每一段路可以邊走邊想、"
        "沿途打聽、留意地形、路邊採集各一次。",
        "",
        "#### 體力",
        *[f"- {line}" for line in stamina_lines(content, season)],
        "- 點狀態列的體力條，也看得到這幾句。",
        "",
        *_section("名望", fame_lines(content, season)),
        *_section("投靠與軍令", join_lines(content, season)),
        *_section("三方有什麼不同", faction_lines(content, season)),
        "#### 情誼",
        *bond,
        "",
        "#### 心得",
        f"- 學武的本錢：練成（第 N 成升下一成花 N×{cfg.practice_xinde_per_level}）、合成（{cfg.fuse_xinde} 心得、"
        f"{cfg.fuse_stamina} 體力）、合併（{cfg.merge_xinde} 心得、{cfg.merge_stamina} 體力）都花它。",
        f"- 打贏、操練、閉關（每小時至少 {cfg.seclusion_xinde_per_hour}，悟性越高越多）、邊走邊想（{cfg.road_think_xinde}）都有心得；"
        "用不上的功法熔掉也能拿回一些。狀態列的 💡 會在你付得起、又真的有事可做時提醒你去哪一頁。",
        "",
        *_section("修練與煉製", pages_lines()),
        "#### 意境",
        # 有所感（sensing.choose、sensing.menu）：選對了還要擲一次（rate，沒中給 sense_miss_xinde）；中了可以畫、也可以順其自然（審查 M2）
        # 選錯了要到換日才悟得出（sensing.missed_today；遊戲日跟著季長縮）：說明頁不看此刻，不寫「今天」，寫「一陣子」，時刻看卡上那一行
        "- 探索落在悟意境時「有所感」，先選做法：選錯了，那裡要過一陣子才悟得出（選之前卡上就寫著要到什麼時候）；"
        "選對了還要看機緣（沒抓住也有一點心得），"
        "抓住了可以畫一筆，也可以順其自然。哪裡悟得到什麼看地形。",
        "- 善名、惡名夠高也會悟到意境。合成、合併都不會把意境用掉（自己熔掉才沒了）。",
        "- 一門武學融一個意境，合成新的武學；兩門武學也能合出第三門；兩個意境合併成新的意境。"
        f"悟到已經會的，化成 {cfg.duplicate_insight_xinde} 心得。",
        "",
        "#### 背包",
        "- 素材不拿來煉製：第一季裡折成糧草，押糧車、準備伏筆都要用。",
    ]
    return "\n".join(lines)

