"""交友求見包：玩法說明自己那幾句（全部拆包第 59 批；原 tianxia/howto.py，字一個不動）：行動列底下交友、求見那幾行（social_line、CALL_LINE、call_line）、
說明頁交友那一條（順序在核心 HOWTO_ORDER）。"""
from __future__ import annotations

from tianxia import calendar, precise, rules
from tianxia.models import Content
from tianxia.state import WorldState

SEEK_NAME = "找事件"  # 玩法說明「交友的事在探索的找事件裡」那一句（一類一顆開著的季）


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


def socialize_section(content: Content, season: WorldState) -> list[str]:
    """玩法說明交友那一條（HOWTO_ORDER 的 socialize）。"""
    cfg = content.config
    cost = cfg.action_cost
    return [
        f"- **交友**（體力 {cost['socialize']}）：見這裡的人物談話（每輪體力 {cfg.talk_stamina}，同一位人物{day_every(content, season)}最多 "
        + (f"{cfg.talk_turns_per_day} 輪）。名望不夠的人物在名單上灰著，寫還差多少；交友的事在探索的{SEEK_NAME}裡。"
           if precise.on(content, season) else f"{cfg.talk_turns_per_day} 輪），或碰上交友的事。名望不夠的人物會打發你。"),
    ]
