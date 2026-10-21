"""破境（招式與絕學稿案第三節）：自創的練成絕學，自己的招升為絕招、接後勁、破境卡、江湖史與傳聞，不再定名。"""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from tianxia import ascend, create, cultivation, moves, skillview, tactics, team, traits
from tianxia.content import load_content
from tianxia.engine import Game

ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def content():
    c = load_content(ROOT / "tests" / "fixtures" / "content")
    c.config.auto_open_first_season = True
    return c


class Always:
    def random(self):
        return 0.0


def _made(content, name="破境人"):
    game = Game.new(content, name, rng=random.Random(3))
    game.world.open_season(content, now=0.0)
    p = game.state.player
    p.stats["xinde"] = 5000
    assert game.create_begin("武學", "拳腳")
    game.create_pose(create.preset(content, "進擊"))
    game.create_intent("風過林梢，影不留痕", reading=create.IntentReading(score=80, attributes=["快"], move="追風影"))
    game.create_name("疾風掌")
    p.member.wugong_id, p.member.wugong_level = "疾風掌", 10
    if "疾風掌" in p.arts:
        p.arts.remove("疾風掌")
    return game


def test_the_own_move_ascends_and_the_card_is_written(content):
    game = _made(content)
    s, w, p = game.state, game.world, game.state.player
    before = team.player_art(s, content, w, "疾風掌")
    was = moves.move_of(content, before, 10)
    msgs = ascend.ascend(s, content, w, "疾風掌", "seize")
    assert p.art_quality["疾風掌"] == "絕學" and p.naming is None  # 破境不取名
    assert "〔追風影〕忽然通了" in msgs[0]
    after = team.player_art(s, content, w, "疾風掌")
    now = moves.move_of(content, after)
    assert now.rate == 1.0 and now.name == "追風影" and was.rate < 1.0
    assert tactics.title_of(now, after) == tactics.ULTIMATE_SEAL
    card = p.ascension
    assert card.after.startswith("絕〔追風影〕") and card.before.startswith(p.name[:1] + "〔追風影〕")
    assert card.power[1] > card.power[0]
    assert any("練到了絕處" in r.text for r in s.world.rumors)
    held = [h for h in team.tactic_holders(s, content, w) if h.skill == "疾風掌"]
    assert held and held[0].tactic.rate == 1.0


def test_the_card_line_is_rechecked_and_dismissed(content):
    game = _made(content, "寫卡人")
    s = game.state
    ascend.ascend(s, content, game.world, "疾風掌", "pill")
    req = game.ascend_request()
    assert req is not None and req.move == "追風影" and req.via == "pill"
    assert ascend.read(None, req) == ascend.FALLBACK_PILL
    game.ascend_line(req, "123")  # 寫壞了：照套句
    assert s.player.ascension.line == ascend.FALLBACK_PILL
    assert game.ascend_request() is None  # 寫過了不再叫
    game.ascend_dismiss()
    assert s.player.ascension is None and ascend.view(s) is None


def test_seize_in_a_fight_goes_through_the_ascension(content):
    game = _made(content, "契機人")
    s, p = game.state, game.state.player
    p.art_quality["疾風掌"] = "上品"
    if content.config.breakthrough.chance <= 0:
        pytest.skip("測試內容關了契機")
    msgs = cultivation.seize(s, content, game.world, 1.0, Always())
    assert msgs and "忽然通了" in msgs[0] and p.ascension is not None


def test_the_row_shows_the_fifth_ring_and_the_ripe_marks(content):
    game = _made(content, "看卡人")
    s, w = game.state, game.world
    row = next(r for r in skillview.art_rows(s, content, w) if r["id"] == "疾風掌")
    assert row["fifth"] == {"on": False, "name": "", "note": skillview.RIPE_NOTE}
    assert f"（{skillview.RIPE_MOVE}）" in row["tactic"]
    ascend.ascend(s, content, w, "疾風掌", "seize")
    row = next(r for r in skillview.art_rows(s, content, w) if r["id"] == "疾風掌")
    assert row["fifth"]["on"] and row["fifth"]["name"] == "追風影"
    assert row["tactic"].startswith("絕〔追風影〕") and skillview.RIPE_MOVE not in row["tactic"]


def test_the_after_blow_follows_the_slots():
    """後勁要內容寫了絕招（測試內容沒寫）：用正式內容。"""
    content = load_content(ROOT / "content")
    content.config.auto_open_first_season = True
    game = _made(content, "後勁人")
    s, w = game.state, game.world
    p = s.player  # 舊樣子的意境（沒擲效果）：功效就是那一路的一般功效，強度 3（同 test_ultimates._mastered）
    p.insights.append("feng")
    p.insight_strength["feng"] = 3
    p.art_slots["疾風掌"] = ["feng", None, None]
    ascend.ascend(s, content, w, "疾風掌", "seize")
    art = team.player_art(s, content, w, "疾風掌")
    tail = traits.ultimate_of(content, art)
    assert tail is not None and tail.name != art.name  # 後勁照功效取名，不再叫門名
    assert s.player.ascension.after_tail.startswith(traits.AFTER_TITLE + "〔")
    names = [h.tactic.name for h in team.tactic_holders(s, content, w)]
    assert "追風影" in names and tail.name in names
