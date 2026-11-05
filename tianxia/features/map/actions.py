"""輿圖的動作（全部拆包第 49 批：原本 Game 上的 map_base、map_state、_map_foes、_fierce_line、world_map_svg、minimap_svg、map_legend、
map_header、map_places、place_detail、travel_options，Game 留一行委派，server 與假人照舊叫 Game）。ctx 就是 Game（第一階）。
全部只讀，不擲骰、不動存檔；函式名＝原本的方法名去掉前導底線。

`_map_foes`、`_fierce_line` 在這裡也經 ctx 叫（Game 上的一行委派）：測試換掉 Game._map_foes 看地點卡的對手跟著變（tianxia/features/map/tests/test_jianfa_3d_map_foes.py）。
open_places、mostly_here 是探索包問輿圖包的兩個查詢（原本探索包直接 import mapview、mapdata；成包之後包不能 import 包，經 Game 的委派叫這裡）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import atlas, orders  # 過渡：待搬（地點與路的資料、詳情、移動的選項：atlas 第 50 批拆兩半〔第 49 批 PM 認定第 2 條〕，留下的那一半不進包）
from tianxia import conquest, territory, training  # 共用規則層

from . import mapdata
from .mapview import legend_data, open_places as _open_places, render_map, render_minimap

if TYPE_CHECKING:
    from tianxia.engine import Game
    from tianxia.models import Location


def map_base(ctx: Game, *, viewer: bool = True) -> dict:
    """輿圖升級的底圖與清單（mapdata.base）：伺服器照 mapdata.base_key 快取。名字旁的兩個字是看的人的（map_mostly，2f）；viewer=False 是跟人無關
    的那一份（名字旁照地點種類的表），伺服器快取這一份、每個人再換上自己的（mapdata.with_mostly）。"""
    return mapdata.base(ctx.state, ctx.content, ctx.map_mostly() if viewer else None)


def map_state(ctx: Game) -> dict:
    """輿圖升級的疊層（mapdata.state）：勝算、出陣、分鐘換算由這裡傳進去。只讀，不擲骰。"""
    s, c = ctx.state, ctx.content
    faction = ctx._side()  # 豪強分屬兩軍：照依附那一軍畫出陣與地盤
    on = territory.on(c) and faction is not None  # 出陣開著＝地盤開著（sortie.on 就是 territory.on，出陣包不能被輿圖包 import）
    duel = ctx.duel_on()
    judged: dict[str, tuple[str | None, bool]] = {}

    def judge(loc_id: str) -> tuple[str | None, bool]:
        """（出陣那一格是哪一種, 攻被約戰擋下）：同一處只算一次。"""
        if loc_id in judged:
            return judged[loc_id]
        how = ctx._sortie_mode(c.locations[loc_id]) if on else None
        # 約戰開著（減法季批 3b）：沒有零風險的守，自家的地方出陣那一格灰著「等對面來約」——輿圖不畫「出陣・守」、不推薦去那裡出陣
        # 攻也一樣（FB-855）：貼不了約戰的敵方地方（跟自家領地不相連、冷卻、戰書凍結、碎片鎮地……）不標「攻」、不推薦——問的跟貼約戰
        # （sortie_go_problem）同一個 conquest.push_problem；截糧的運糧隊正打那裡經過的，出陣照舊攻打運糧隊（_duel_option），照舊是攻
        shut = duel and how == "attack" and not orders.extra_enemies(s, c, loc_id, faction) \
            and conquest.push_problem(s.world, c, ctx._conquest_side(), loc_id, "attack") is not None
        judged[loc_id] = (None if shut or (duel and how == "hold") else how, shut)
        return judged[loc_id]

    def foes(loc_id: str) -> list[str] | None:
        # 地點卡的對手與勝算照出陣真的會打的那一路（_map_foes）：標攻的地方（FB-858，3d），還有約戰開著、此刻攻不了的敵方與中立區塊
        # （FB-878：不相連、冷卻、戰書凍結——卡上照舊寫攻不了的原因，對手照貼約戰時會迎戰的守軍那一路寫，不再列站在那裡的隊伍）
        how, shut = judge(loc_id)
        return ctx._map_foes(loc_id) if how == "attack" or shut else None

    out = mapdata.state(
        s, c, odds=ctx.odds, sortie_mode=lambda loc_id: judge(loc_id)[0], sorties_left=ctx.sorties_left() if on else None,
        real_minutes=ctx._real_minutes, sortie_foes=foes, mostly=ctx.map_mostly(),
        # 截糧的運糧隊正打那裡經過：出陣那一格是「出陣・截糧」、打運糧隊（_duel_option），輿圖卡上的鈕也寫截糧、不掛攻的勝算（FB-9005）
        convoy=(lambda loc_id: bool(orders.extra_enemies(s, c, loc_id, faction))) if duel else None,
    )
    for loc_id, info in out["places"].items():  # 地點卡上那一句這一帶多兇（尋敵分級，Joy 2026-10-22：不寫幾級）；沒有是空字串
        info["fierce"] = ctx._fierce_line(c.locations[loc_id])
    return out


def map_foes(ctx: Game, loc_id: str) -> list[str] | None:
    """輿圖地點卡的對手與勝算照「出陣真的會打的那一路」列（FB-858，減法季 3d；mapdata.state 的 sortie_foes，在那一處的出陣是攻時問，
    約戰開著、此刻攻不了〔不相連、冷卻、戰書凍結〕的敵方與中立區塊也問，FB-878）：
    領地爭奪開著，約戰關著是出陣擲的那一批（_sortie_foes：conquest.sortie_foes——中立地那裡站的全部、別人的陣營區塊控制方的兵、那裡沒兵時
    退回 Scenario.territory.side_garrison——加上截糧的運糧隊），約戰開著是貼約戰時守軍迎戰挑的那一路（_duel_squad，經驗最高的一路）；
    截糧的運糧隊正打那裡經過的，出陣那一格照舊攻打運糧隊（_duel_entry），就只有運糧隊。領地爭奪關著、散人、不是區塊、沒有對手是 None＝
    照舊列站的隊伍（atlas.foes）。只讀，不擲骰。"""
    s, c = ctx.state, ctx.content
    side = ctx._side()
    if side is None or not territory.on(c) or not conquest.on(c, s.world) or loc_id not in conquest.blocks(c):
        return None
    if not ctx.duel_on() or ctx._conquest_side() is None:
        return ctx._sortie_foes(c.locations[loc_id]) or None
    extra = orders.extra_enemies(s, c, loc_id, side)
    if extra:
        return extra[:1]
    squad = ctx._duel_squad(loc_id)
    return None if squad is None else [squad.id]


def fierce_line(ctx: Game, loc: Location) -> str:
    """輿圖地點卡與舊地點詳情的那一句（training.PLACE_LINE）：城外尋敵得到的地方照分級寫「此地宵小出沒。」，城鎮、沒有對手、
    城裡操練關著是空字串。只讀。"""
    tier = None if training.is_town(ctx.content, loc) else ctx._practice_tier(loc)
    return "" if tier is None else training.PLACE_LINE.format(tier=training.TIER_WORDS[tier])


def world_map_svg(ctx: Game, layer: str = "situation", selected: str | None = None) -> str:
    odds = ctx.odds if layer == "enemies" else None
    return render_map(ctx.state, ctx.content, layer, selected, odds)


def minimap_svg(ctx: Game) -> str:
    return render_minimap(ctx.state, ctx.content)


def map_legend(ctx: Game, layer: str = "situation") -> dict:
    """大地圖的圖例（資料，見 mapview.legend_data）：不畫進 SVG，網頁自己疊在地圖框角落。"""
    return legend_data(ctx.state, ctx.content, layer)


def map_header(ctx: Game) -> str:
    return atlas.header_text(ctx.state, ctx.content)


def map_places(ctx: Game) -> list[tuple[str, str]]:
    return atlas.place_choices(ctx.state, ctx.content)


def place_detail(ctx: Game, loc_id: str) -> str:
    text = atlas.detail_text(ctx.state, ctx.content, loc_id, lambda squad_id: ctx.odds(squad_id, at=loc_id))  # 照那一處的地利
    loc = ctx.content.locations.get(loc_id)
    fierce = ctx._fierce_line(loc) if loc is not None else ""  # 尋敵分級：一句這一帶多兇（Joy 2026-10-22）
    return f"{text}\n\n{fierce}" if fierce else text


def travel_options(ctx: Game, loc_id: str) -> list[atlas.TravelOption] | None:
    return atlas.travel_options(ctx.state, ctx.content, loc_id)


# ── 探索包問輿圖包的兩個查詢（原本探索包直接 import mapview、mapdata）──


def open_places(ctx: Game) -> list[str]:
    """畫得出來的地點（mapview.open_places）：探索三選一替每一處算名字旁的兩個字（map_mostly）時問。"""
    return _open_places(ctx.state, ctx.content)


def mostly_here(ctx: Game) -> str:
    """腳下這一處「多半給什麼」那一句，照地點的小圖（mapdata.mostly_here）：探索一顆沒有比重可看（關著、序章）時四格探索那一格的退路。"""
    return mapdata.mostly_here(ctx.state, ctx.content)
