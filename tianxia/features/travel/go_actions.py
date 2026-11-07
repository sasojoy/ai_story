"""喊停、安排前往（功能包 tianxia/features/travel/；原本是 Game._halt、travel、travel_refusal，全部拆包第 47 批）。
ctx 是 Game（第一階）。出發（departure.depart）經 ctx._depart 叫；結伴同行（party.lead）直接叫包內的函式（第 48 批）。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import atlas, ranks  # 共用規則層（輿圖：路程與前往的檢查，第 50 批收進；階級 ranks）
from tianxia import journal
from tianxia.core.services import PREPARING_TEXT
from tianxia.journal import Draft
from tianxia.models import TravelMode

from . import party

if TYPE_CHECKING:
    from tianxia.engine import Game


def halt(ctx: Game) -> list[str]:
    """喊停（地圖擴充設計 3.3）：到下一站就停下，不走完全程。不花體力；趕路已經扣的體力也不退。"""
    s, c = ctx.state, ctx.content
    j = s.player.journey
    j.stop_at = j.reached
    msgs = [f"你喊停，到了{c.locations[j.path[j.reached]].name}就停下來。"]
    if j.mode == "hurry":
        msgs.append("（趕路已經花掉的體力不退。）")  # 拿掉趕路之前出發、還在路上的那一趟
    msgs += party.lead(ctx, None, 0, f"{s.player.name}喊停，到了{c.locations[j.path[j.reached]].name}就停下來。")
    ctx._sync_battle_presence()  # 這一趟縮短了：最後一站落在決戰的大區內，就不再算離開
    return msgs


def travel(ctx: Game, dest_id: str, mode: TravelMode = "walk") -> list[str]:
    """安排前往（大地圖詳情欄的按鈕）：照路程最短的路線出發，走法見 departure.depart。在路上也行（路上設計 3.1）：
    取掉頭與繼續兩種走法裡路程短的（見 atlas.way_to），新路程從路中間出發。"""
    refusal = ctx.travel_refusal(dest_id, mode)  # 經 Game 的委派叫：測試換掉 game.travel_refusal 繞過檢查，照樣生效
    if refusal is not None:
        return ctx._log([f"（{refusal}。）"])
    s, c = ctx.state, ctx.content
    route = atlas.way_to(s, c, dest_id)
    s.battle_card = None
    s.player.guide_done = []
    ctx._draft = Draft(atlas.journey_title(c, route.path))
    stamina = s.player.stamina
    try:
        msgs = ctx._depart(route, mode)
        msgs += ctx._hear_after_stamina(stamina)
        msgs += ranks.check_summons(s, c)  # 疾行送到糧車也記貢獻（計畫 T5）
        msgs += ctx._report_seat()  # 同上：第四階席次的帳也要抄（正式版丁）
        ctx._check_hints()  # 出發之後看一遍（疾行立刻到：抵達的地方教基礎武學、站著大勢人物，新手引導計畫三）
        journal.add_entry(s, ctx._draft.entry(s.world.time, msgs))
    finally:
        ctx._draft = None
    ctx._save_season()
    return ctx._log(msgs)


def travel_refusal(ctx: Game, loc_id: str, mode: TravelMode = "walk") -> str | None:
    """用這種走法安排前往這裡，不行的原因；可以時為 None。/api/travel 拿它分辨「沒能出發」。"""
    if ctx._preparing():
        return PREPARING_TEXT
    if loc_id not in ctx.content.locations or mode not in atlas.MODES:
        return "無法安排前往這裡"
    return atlas.travel_refusal(ctx.state, ctx.content, loc_id, mode)
