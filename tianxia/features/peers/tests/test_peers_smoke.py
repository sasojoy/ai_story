"""玩家互動的煙霧測試（開發規範手冊 4.1 第三級：一包一條，走一次最常見的路）：兩個人在同一個地點，甲看得到乙（此地還有）、打開乙的玩家卡、
挑釁一次；乙的選單上多出回禮的邀請（invite:，這一包的前綴），挑一個回——這一包的 choose 掛鉤接走（標題「與甲」），甲下次上線在江湖紀錄裡看到回應。
測試內容、沒有模型（client=None）。"""
import random

import pytest

from tianxia.characters import CharacterStore
from tianxia.core.registry import FEATURES
from tianxia.engine import Game

NOW = 1_000_000.0


def _player(content, name):
    game = Game.new(content, name, rng=random.Random(0))
    game.sync(NOW)
    game.state.player.location = "town"
    CharacterStore(game.world.db).save(game.state)
    return game


@pytest.mark.smoke
def test_two_people_meet_and_a_taunt_gets_answered_through_the_invite_hook(content):
    feature = next(f for f in FEATURES if f.name == "peers")
    assert feature.prefix == "invite" and feature.bot_always == ("invite:",) and "mingtie" in feature.player_fields
    a = _player(content, "甲")
    _player(content, "乙")
    assert feature.enabled(a) and a.peers_here() == [{"name": "乙", "side": "散人"}]
    assert a.peer_card("乙")["name"] == "乙"
    assert a.peer_act("乙", "greet", {"arg": "taunt"}) == ["你向乙斜眼打量，出言挑釁。"]
    CharacterStore(a.world.db).save(a.state)
    b = Game(content, CharacterStore(a.world.db).load("乙"), random.Random(0), a.world)
    b.client = None
    b.sync(NOW + 10)
    [reply] = [o for o in b.options(odds=False) if o.id.startswith("invite:retort:")]
    assert reply.enabled and b.choose(reply.id)[-1] == "你出言回敬。"
    assert "與甲" in [e.title for e in b.state.journal]  #標題由這一包的 choose 掛鉤給（原 _action_title 的 invite 那一支）
    assert not [o for o in b.options(odds=False) if o.id.startswith("invite:")]  # 回過了，邀請收掉
