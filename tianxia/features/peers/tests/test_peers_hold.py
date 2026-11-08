"""扣押期（帳號與客服第 208 批；設計 4.3、4.4、6.4）：贈素材（鍵 gift）。只問送的人：被扣押的帳號送不出去、素材不動，
卡上「贈素材」灰掉寫那一句；對方被扣押不影響我送；對方看我的卡一個字不變（扣押只給本人看）。"""
from __future__ import annotations

import phone_kit
import pytest
from test_peers_phone_gate import ACT, NOW, _buttons, _do, _footprint, _turn, _world
from test_peers_phone_gate import _season  # noqa: F401  autouse：第一季、兩個陣營、金鑰讀得到

from tianxia.core.identity_base import HOLD_STALE

pytestmark = pytest.mark.whole_content


def _stale(content):
    return HOLD_STALE.format(days=content.config.identity.stale_hold_days)


def test_held_giver_blocked_and_button_greyed(content, tmp_path):
    phone_kit.gate(content, on=False)
    world = _world(content, tmp_path, "w", me="unbound")
    phone_kit.hold(world.db, "ray1", NOW + 100)
    shown = _buttons(content, world, "甲", "乙", "gift")
    assert shown and all(not b["enabled"] and b["note"] == _stale(content) for b in shown)
    before = _footprint(world)
    assert _do(content, world, "甲", lambda g: g.peer_act("乙", "gift", dict(ACT["gift"])))[0] == [_stale(content)]
    assert _footprint(world) == before


def test_held_receiver_does_not_block_me(content, tmp_path):
    phone_kit.gate(content, on=False)
    plain = _turn(content, _world(content, tmp_path, "plain", me="unbound"), "gift")
    world = _world(content, tmp_path, "held", me="unbound")
    phone_kit.hold(world.db, "ray2", NOW + 100)
    assert _turn(content, world, "gift") == plain
    assert plain[1] != [_stale(content)]


def test_others_see_my_card_unchanged(content, tmp_path):
    phone_kit.gate(content, on=False)
    plain = _do(content, _world(content, tmp_path, "plain", me="unbound"), "乙", lambda g: g.peer_card("甲"))[0]
    world = _world(content, tmp_path, "held", me="unbound")
    phone_kit.hold(world.db, "ray1", NOW + 100)
    assert _do(content, world, "乙", lambda g: g.peer_card("甲"))[0] == plain
