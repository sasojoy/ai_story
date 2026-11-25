"""合璧榜（意境合成改版批四，features/craft/board.py）：合璧成神那一下記進 WorldState.he_gods；榜列這一季合出過的意境，
成神過的在前面；改版沒開的季路由 404。"""
import pytest

from conftest import real_content

from tianxia import fusion
from tianxia.features.craft import board
from tianxia.state import QUIET, InsightFx, WorldState, new_game_state

pytestmark = pytest.mark.whole_content


@pytest.fixture
def rc():
    c = real_content()
    c.config.craft.enabled = True
    c.config.craft.near_chance = 0.0
    c.config.craft.bonus_chance = 0.0
    return c


@pytest.fixture
def me(rc):
    s = new_game_state(rc, "韓霜")
    s.world.craft_v2 = True
    s.player.stats["xinde"] = 500
    s.player.stamina = 500
    return s


def give(s, piece, key, layers):
    if piece not in s.player.insights:
        s.player.insights.append(piece)
    s.player.insight_fx[piece] = InsightFx(quality="中品", general={key: layers})


def test_god_is_recorded_and_the_board_puts_it_first(rc, me, world, monkeypatch):
    give(me, "shui", "柔", 1)
    give(me, "shan", "慢", 1)
    plain, _ = fusion.merge(me, rc, world, None, "shui", "shan", proposed=("沉淵", ""))
    assert me.world.he_gods == {}  # 平常的一爐不記
    give(me, "huo", "剛", 3)
    give(me, "feng", "快", 3)
    me.player.location = "changshe"
    monkeypatch.setattr(fusion, "secret_met", lambda *a: True)
    god, _ = fusion.merge(me, rc, world, None, "huo", "feng", proposed=("焚風", ""))
    assert me.world.he_gods == {god.id: [["韓霜", "he_yang_bian"]]}
    got = board.rows(me, rc, world)
    assert [r["name"] for r in got["rows"]] == [god.name, plain.name] and got["gods"] == 1
    top = got["rows"][0]
    assert top["gods"] == 1 and top["first"] == "韓霜" and top["grand"] and top["mine"] and top["path"] == "陽"
    assert top["by"] == ["韓霜"]
    assert got["rows"][1]["gods"] == 0 and got["rows"][1]["first"] is None


def test_the_field_stays_out_of_old_saves():
    assert WorldState.model_fields["he_gods"].json_schema_extra == QUIET  # 空的不寫鍵：換回舊程式讀得進來


def test_switched_off_season_has_no_board(rc, me):
    assert board.on(rc, me)
    me.world.craft_v2 = False
    assert not board.on(rc, me)
