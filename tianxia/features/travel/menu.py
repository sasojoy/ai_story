"""移動的選單（功能包 tianxia/features/travel/；原本是 Game._move_option、_back_way、_back_option、_road_task_options、set_move_mode，
全部拆包第 47 批）。ctx 是 Game（第一階）。選單的順序算行為（「前往」夾在求見、招募之後、拜師之前；路上那串是折返、帶路一句、喊停、路上小事、擂台），
所以不能改成 Feature.options 登記（會排進 FEATURES 的順序）：Game 原位那幾行只叫委派。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import atlas  # 過渡：待搬（輿圖：路程、體力、時間的字）
from tianxia.core.option import Option
from tianxia.core.services import MOVE_BLOCKED, ROAD_REWARD_TASKS, ROAD_TASKS
from tianxia.state import Journey

from . import road_actions

if TYPE_CHECKING:
    from tianxia.engine import Game


def move_option(ctx: Game, here: str, dest_id: str) -> Option:
    """選單上的「前往 相鄰地點」，照主畫面選的走法（move_mode）：標籤寫這種走法的時間與體力，體力不夠就按不下去、
    寫明原因（跟大地圖的「安排前往」按鈕同一個說法）。步行的 id 維持 move:<地點>（機器人、假人與舊的呼叫端
    只認這個）；趕路、疾行是 move:<地點>:<走法>，所以 choose() 照樣只認選單上真的有的 id。
    時間與體力走 atlas.route_text／route_stamina，跟 _move 出發時 _depart 實際扣的是同一條路（騎著馬照腳力省、步調照坐騎，
    裝備四欄 5.3；閒著時不在路上，不會是剛出發就折返）。"""
    c, mode = ctx.content, ctx.move_mode
    dest = c.locations[dest_id]
    route = atlas.Route((dest_id,), (atlas.leg_minutes(c, here, dest_id),))
    option_id = f"move:{dest_id}" if mode == "walk" else f"move:{dest_id}:{mode}"
    if ctx.state.player.ambush is not None:  # 守著埋伏不能移動（設伏劫道：沒有分身）
        return Option(id=option_id, label=f"前往 {dest.name}（{MOVE_BLOCKED}）", enabled=False)
    cost = atlas.route_stamina(ctx.state, c, route, mode)
    if ctx.state.player.stamina < cost:
        return Option(id=option_id, label=f"前往 {dest.name}（{atlas.MODES[mode]}・體力不足，要 {cost}）", enabled=False)
    # 尋敵分級不寫在移動清單上（Joy 2026-10-22）：兇險程度只在輿圖的地點詳情寫一句（place_detail）
    return Option(id=option_id, label=f"前往 {dest.name}（{atlas.route_text(ctx.state, c, route, mode)}）")


def back_way(ctx: Game) -> atlas.Route:
    """折返的路：從路上回到身後那一站（路上設計 3.2：折返就是「改去」那一站，見 atlas.way_to）。
    掉頭那一種走法到身後那一站一定算得出來，所以在路上時不會是 None。"""
    spot = atlas.road_spot(ctx.state, ctx.content)
    return atlas.way_to(ctx.state, ctx.content, spot.behind)


def back_option(ctx: Game) -> Option:
    """路上的「折返 某站」，照主畫面選的走法（move_mode）：標籤寫這種走法的時間與體力，體力不夠就按不下去、寫明原因
    （跟「前往」同一個說法，見 move_option）。id 也跟「前往」一樣：步行是 road:back，趕路、疾行是 road:back:<走法>，
    所以 choose() 照樣只認選單上真的有的 id。"""
    c, mode = ctx.content, ctx.move_mode
    way = back_way(ctx)
    name = c.locations[way.path[-1]].name
    option_id = "road:back" if mode == "walk" else f"road:back:{mode}"
    cost = atlas.route_stamina(ctx.state, c, way, mode)
    if ctx.state.player.stamina < cost:
        return Option(id=option_id, label=f"折返 {name}（{atlas.MODES[mode]}・體力不足，要 {cost}）", enabled=False)
    return Option(id=option_id, label=f"折返 {name}（{atlas.route_text(ctx.state, c, way, mode)}）")


def road_task_options(ctx: Game, j: Journey) -> list[Option]:
    """路上小事（路上設計第四節）：步行、趕路時每樣一顆（四樣；全圖開放時沒有留意地形，三樣），不花體力；這一段路做過的灰掉、寫「這段路已經……」。
    疾行一站一站立刻抵達，沒有。這個遊戲日的收穫拿滿了（每天上限，遊戲日跟著季長縮）的邊走邊想、路邊採集照樣按得下去，
    補充改寫「收穫拿滿了」（待 joy 潤）。鈕上不寫換日的那一刻：375 px 上 2×2 格子一格的小字只有約 143 px，時刻本身就約 118 px，
    再加字就折成兩行、整個格子變高（day-scale 審查 M1）；時刻寫在按下去的那一句（road_actions.think、gather）。"""
    if j.mode == "dash":
        return []
    hints = {
        "think": f"心得 +{ctx.content.config.road_think_xinde}",
        "ask": "聽一則這一帶的傳聞",
        "gather": "有機會撿到素材",
    }
    if not road_actions.reward_due(ctx, "task"):
        for what in ROAD_REWARD_TASKS:
            hints[what] = "收穫拿滿了"  # 不留「心得 +3」：拿滿了就沒有
    done = ctx.state.player.leg_actions
    return [
        Option(id=f"road:{what}", label=f"{name}（{did}，到下一站再說）", enabled=False) if what in done
        else Option(id=f"road:{what}", label=f"{name}（{hints[what]}）")
        for what, (name, did) in ROAD_TASKS.items()
    ]


def set_move_mode(ctx: Game, mode: str) -> None:
    """主畫面的「走法」切換：之後選單上的「前往」用這種走法；不認得的走法當成步行。不存檔（見 Game.__init__ 的 move_mode）。"""
    ctx.move_mode = mode if mode in atlas.MODES else "walk"
