"""交友求見的煙霧測試（開發規範手冊 4.1 第三級：一包一條，走一次最常見的路）：week7 的官軍站在長社（五位人物的地點），名望夠，
按「交友」打開求見名單，點皇甫嵩——這一包的 call: 接走（標題「求見・皇甫嵩」），沒有模型（client=None）他無心多談，名單收起、體力退回。"""
import pytest

from stances_kit import real_game
from tianxia.core.registry import FEATURES


@pytest.mark.smoke
def test_a_famed_newcomer_asks_for_an_audience_and_the_list_closes():
    feature = next(f for f in FEATURES if f.name == "socialize")
    g = real_game("week7", location="changshe")
    p = g.state.player
    assert feature.enabled(g) and feature.prefix == "call" and feature.player_fields == ("talks_today", "picking_audience")
    p.stats["fame"] = 999
    assert "act:call" in {o.id for o in g.options(odds=False) if o.enabled}
    g.choose("act:call")
    assert p.picking_audience
    options = {o.id: o for o in g.options(odds=False)}
    assert options["call:huangfusong"].enabled and "call:back" in options  # 名單：每位人物一顆，最後是返回
    stamina = p.stamina
    msgs = g.choose("call:huangfusong")
    assert msgs == ["皇甫嵩似乎無心多談，你只好先行告辭。"] and not p.picking_audience and p.stamina == stamina
