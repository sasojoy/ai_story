"""傳承測試共用的局面：正式內容（season21）、傳承開著、身上有一份神品意境。"""
from __future__ import annotations

from jianfa_kit import jianfa_game, ready

from tianxia import insight_fx, insights
from tianxia.martial_arts import Insight
from tianxia.state import InsightFx


def god_game(name: str = "寒江獨照"):
    """回 (game, 那一份神品意境的 id)。"""
    game = ready(jianfa_game(), side="guan", loc="yingshui")
    game.content.config.legacy.enabled = True
    give_god(game, name)
    return game, next(iter(game.state.player.own_insights))


def give_god(game, name: str) -> str:
    p, c = game.state.player, game.content
    god = c.traits.god[0]
    p.own_serial += 1
    iid = f"{insights.OWN_PREFIX}{p.own_serial}"
    p.own_insights[iid] = Insight(id=iid, name=name, attribute=god.attribute, lean=god.lean, note=god.desc, creator=p.name)
    p.insights.append(iid)
    p.insight_fx[iid] = InsightFx(quality=insight_fx.QUALITIES[-1], general={god.general: insight_fx.MAX_LAYERS}, grand=god.id)
    return iid


def next_season(game) -> None:
    game._reset_player_for_new_season(game.state.player.season_number + 1)
