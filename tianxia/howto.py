"""玩法說明（explain-1，試玩回饋：Gary「很多東西要一句說明，不然體力用完了還不知道在玩什麼」）：

- 江湖頁行動列底下那幾行：探索、遊歷、交友這一下會怎樣（explore_line、train_line、social_line）；
- 狀態列體力條點開的說明（stamina_lines）與建角色時送回體丹的那一行（gift_line）；

這裡只把事實寫成字：比重、獎勵、推不推戰局由呼叫端照引擎真正的規則算好傳進來（Game._explore_weights、遊歷的對手、
Game.train_trend_push），數字一律讀 Config，句子裡不寫死任何數。不改狀態、不擲骰、不讀時鐘。所有句子待 joy 潤。"""
from __future__ import annotations

from collections.abc import Sequence

from . import calendar
from .models import Content
from .state import WorldState

# 探索三選一的三支（models.EXPLORE_BRANCHES）在說明裡怎麼叫
BRANCH_WORDS: dict[str, str] = {"insight": "悟意境", "wild": "遇野怪", "event": "碰上事件"}
PUSH_WORD = "推動戰局"  # 遊歷打贏、操練會推大勢（第一季是戰線，豪強在亂局推割據）：一律這樣說，不露數字


def explore_line(weights: Sequence[tuple[str, float]], legend: str | None = None) -> str:
    """探索這一下多半會怎樣。weights 是探索真的擲骰用的那一份（支, 比重）：照地點類型（Config.explore_mix）、
    做不了的已經拿掉、悟意境那一支乘過悟性（Game._explore_weights）。比重嚴格最大的那一支寫「多半」，其他寫「也可能」
    （照比重由大到小）；並列最大就一起寫「可能」。不寫百分比。legend 是破境丹的名字（探索每次另擲一次撿不撿得到；
    機率是 0 時呼叫端給 None）。"""
    ranked = sorted((pair for pair in weights if pair[1] > 0), key=lambda pair: -pair[1])  # 穩定排序：並列照原本的順序
    words = [BRANCH_WORDS[branch] for branch, _ in ranked]
    if not words:
        head = "這裡多半一無所獲"
    elif len(words) == 1 or ranked[0][1] > ranked[1][1]:
        head = f"這裡多半{words[0]}" + (f"，也可能{'、'.join(words[1:])}" if len(words) > 1 else "")
    else:
        head = f"這裡可能{'、'.join(words)}"
    return head + (f"；偶得{legend}" if legend else "")


def train_line(foes: bool, gains: Sequence[str], drops: bool, push: bool, drill_gains: Sequence[str], drills: bool) -> str:
    """遊歷打完會拿到什麼。foes：這裡有會打的對手（不是自己陣營的）；gains：打贏給的（銀兩、心得、經驗，照會打的對手有沒有
    這一項）；drops：打贏有機會掉素材；push：打贏或操練會推大勢（Game.train_trend_push 不是空的）；drill_gains：跟自己人操練
    給的（只有心得、經驗，照 Config.drill_reward_share 算出來不是 0 的）；drills：這裡也有自己陣營的隊伍。沒有會打的對手＝操練。"""
    pushed = f"，{PUSH_WORD}" if push else ""
    if not foes:
        got = f"得{'、'.join(drill_gains)}" if drill_gains else "沒什麼賞"
        return f"操練不冒險：{got}{pushed}；不給銀兩、素材"
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
    """建角色時送的回體丹（Config.beta_gift、beta_gift_stamina_pills），記在江湖紀錄開場那一則的一行。補滿打開時說那顆鈕不花丹。"""
    cfg = content.config
    name, n, restore = cfg.stamina_pill_name, cfg.beta_gift_stamina_pills, cfg.stamina_pill_restore
    if cfg.beta_free_refill:
        return f"內測贈禮：{name} {n} 顆，一顆回 {restore} 點體力；測試期間體力條上的「{cfg.beta_free_refill_label}」不花丹，丹先留著。"
    return f"內測贈禮：{name} {n} 顆，一顆回 {restore} 點體力，按體力條右端的「丹」服下。"

