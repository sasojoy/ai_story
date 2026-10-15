"""意境提示（意境提示設計第一、二節）：每個地點最濃的意境——選對它的做法感悟擲中 +15、在那裡重複悟到心得 15、
悟到時多一句；開關關著一個字都不變。測試內容（湖邊悟得到水、風），自己打開開關。"""
import random

import pytest
from conftest import FixedRandom

from tianxia import insights, sensing
from tianxia.engine import Game
from tianxia.martial_arts import Insight
from tianxia.models import InsightScene, SenseMethod

SCENE = InsightScene(
    id="lake_wind", title="湖風", text="風吹過湖面，停過腳的{痕跡}。", tags=["湖畔"], hints=["柔"],
    methods=[SenseMethod(attribute=a, text=t) for a, t in (("柔", "看水"), ("剛", "打水"), ("快", "追風"), ("慢", "靜坐"))],
)
LINE = "此地水氣最濃。"


@pytest.fixture
def lake(content, world):
    content.insight_scenes = {SCENE.id: SCENE}
    content.config.train_event_chance = 0.0
    content.config.insight_strong.enabled = True
    content.locations["lake"].insight_strong = "shui"
    content.insights["shui"].strong_line = LINE
    g = Game.new(content, "沈浪", rng=FixedRandom(0.0), world=world)
    g.state.player.location = "lake"
    return g


def _open(g: Game) -> None:
    sensing.start(g.state, g.content, SCENE, random.Random(0))


def _pick(g: Game, attribute: str) -> list[str]:
    s = g.state.player.sensing
    index = [SCENE.methods[j].attribute for j in s.order].index(attribute)
    return g.choose(f"sense:{index}")


def _here(g: Game):
    return g.content.locations["lake"]


def test_the_strongest_is_read_through_one_place(lake):
    assert insights.strong_of(_here(lake), lake.content) == "shui"
    assert insights.strong_of(None, lake.content) is None
    lake.content.config.insight_strong.enabled = False
    assert insights.strong_of(_here(lake), lake.content) is None


def test_the_strongest_method_adds_the_points(lake):
    base = sensing.rate(lake.state, lake.content, _here(lake))
    assert sensing.rate(lake.state, lake.content, _here(lake), "柔") == base + 15
    assert sensing.rate(lake.state, lake.content, _here(lake), "快") == base


def test_the_points_stop_at_the_top_of_the_range(lake):
    lake.state.player.stats["wis"] = 15  # 70＋30 已經夾在 95
    assert sensing.rate(lake.state, lake.content, _here(lake), "柔") == lake.content.config.sense_rate_range[1]


def test_a_roll_between_the_two_rates_lands_with_the_strongest_method(lake):
    lake.rng = FixedRandom(0.75)  # 70 擲不中、85 擲中
    _open(lake)
    _pick(lake, "柔")
    assert lake.state.player.sensing is not None and lake.state.player.sensing.stage == "draw"


def test_the_same_roll_misses_with_another_right_method(lake):
    lake.rng = FixedRandom(0.75)
    _open(lake)
    _pick(lake, "快")
    assert lake.state.player.sensing is None


def test_learning_the_strongest_here_adds_the_line(lake):
    _open(lake)
    _pick(lake, "柔")
    msgs = lake.choose(sensing.LET_GO)
    assert LINE in msgs and "shui" in lake.state.player.insights


def test_learning_another_kind_here_has_no_line(lake):
    _open(lake)
    _pick(lake, "快")
    msgs = lake.choose(sensing.LET_GO)
    assert "feng" in lake.state.player.insights and not any("最濃" in m for m in msgs)


def test_a_repeat_of_the_strongest_gives_more_xinde(lake):
    p = lake.state.player
    p.insights.append("shui")
    before = p.stats.get("xinde", 0)
    msgs = insights.learn(lake.state, lake.content, lake.world, "shui", at=_here(lake))
    assert p.stats["xinde"] == before + 15 and msgs[0] == LINE


def test_a_repeat_of_another_kind_gives_the_usual_xinde(lake):
    p = lake.state.player
    p.insights.append("feng")
    before = p.stats.get("xinde", 0)
    insights.learn(lake.state, lake.content, lake.world, "feng", at=_here(lake))
    assert p.stats["xinde"] == before + lake.content.config.duplicate_insight_xinde


def test_a_repeat_without_a_place_gives_the_usual_xinde(lake):
    p = lake.state.player
    p.insights.append("shui")
    before = p.stats.get("xinde", 0)
    msgs = insights.learn(lake.state, lake.content, lake.world, "shui")
    assert p.stats["xinde"] == before + lake.content.config.duplicate_insight_xinde and LINE not in msgs


def test_a_private_insight_at_the_strongest_place_is_left_alone(lake):  # Review Focus 3
    own = sensing.add_own(lake.state, Insight(id="", name="湖心月", attribute="柔", lean="無", note=""))
    before = lake.state.player.stats.get("xinde", 0)
    msgs = insights.learn(lake.state, lake.content, lake.world, own.id, at=_here(lake))
    assert lake.state.player.stats["xinde"] == before + lake.content.config.duplicate_insight_xinde and LINE not in msgs


def test_switch_off_changes_nothing(lake):
    lake.content.config.insight_strong.enabled = False
    assert sensing.rate(lake.state, lake.content, _here(lake), "柔") == sensing.rate(lake.state, lake.content, _here(lake))
    p = lake.state.player
    p.insights.append("shui")
    before = p.stats.get("xinde", 0)
    msgs = insights.learn(lake.state, lake.content, lake.world, "shui", at=_here(lake))
    assert p.stats["xinde"] == before + 10 and not any("最濃" in m for m in msgs)
