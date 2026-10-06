"""悟意境（悟意境設計第零節）：讀筆畫、看圖取名、有所感的流程、私有意境在合成與修練裡、首悟紀錄、機器人。"""
import random

import pytest
from conftest import FixedRandom, next_season

from tianxia import bot, fusion, glyph, insight_llm, insights, journal, naming, sensing
from tianxia.engine import Game
from tianxia.models import InsightScene, SenseMethod
from tianxia.sqlite_world import open_world

SCENE = InsightScene(
    id="lake_wind", title="湖風", text="風吹過湖面，停過腳的{痕跡}。", tags=["湖畔"], hints=["柔"],
    methods=[SenseMethod(attribute=a, text=t) for a, t in (("柔", "看水"), ("剛", "打水"), ("快", "追風"), ("慢", "靜坐"))],
)


@pytest.fixture
def lake(content, world):
    content.insight_scenes = {SCENE.id: SCENE}
    content.config.train_event_chance = 0.0
    g = Game.new(content, "沈浪", rng=FixedRandom(0.0), world=world)
    g.state.player.location = "lake"
    return g


def _open(g: Game) -> None:
    sensing.start(g.state, g.content, SCENE, random.Random(0))


def _pick(g: Game, attribute: str) -> list[str]:
    s = g.state.player.sensing
    index = [SCENE.methods[j].attribute for j in s.order].index(attribute)
    return g.choose(f"sense:{index}")


# ── 讀筆畫 ──────────────────────────────────────────

@pytest.mark.parametrize("attribute", sorted(glyph.SAMPLES))
def test_each_sample_stroke_reads_as_its_attribute(attribute):
    assert glyph.read(glyph.SAMPLES[attribute]).attribute == attribute


def test_a_slow_circle_reads_as_soft_and_says_so():
    import math
    circle = [[50 + 40 * math.cos(i / 20 * math.tau), 50 + 40 * math.sin(i / 20 * math.tau), i * 100] for i in range(21)]
    read = glyph.read(circle)
    assert read.attribute == "柔" and read.closed and "圓轉不斷" in read.note() and "頭尾相接" in read.note()
    assert all(0 <= x <= 100 and 0 <= y <= 100 for x, y in read.points) and len(read.points) == glyph.THUMB


@pytest.mark.parametrize("points", [[], [[1, 1, 0]], [[1, 1, 0], [1.5, 1.5, 10]], "x", [[1, "a", 0], [5, 5, 5]], [[1, 2]]])
def test_strokes_that_cannot_be_read_are_refused(points):
    with pytest.raises(glyph.GlyphError):
        glyph.read(points)


# ── 看圖取名（B 段）─────────────────────────────────

class FakeClient:
    timeout = 30.0

    def __init__(self, replies):
        self.replies, self.seen = list(replies), []
        self.retry = True

    def chat_structured(self, messages, schema, required_fields=None):
        self.seen.append(messages)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return schema(name=reply[0], description=reply[1])


FACTS = {"place": "湖邊", "scene": "湖風", "text": "風吹過湖面。", "method": "看水", "note": "一筆畫成，圓轉不斷", "attribute": "陰"}


def test_the_model_looks_at_the_picture_first(content):
    client = FakeClient([("湖心月", "一圈一圈的圓轉。")])
    assert insight_llm.name(client, content, FACTS, image="AAAA", budget=30) == ("湖心月", "一圈一圈的圓轉。", "看圖")
    assert client.seen[0][1]["images"] == ["AAAA"] and "線條形狀" in client.seen[0][1]["content"]


def test_when_the_picture_fails_it_asks_with_words_only(content):
    client = FakeClient([RuntimeError("看不懂"), ("湖心月", "")])
    assert insight_llm.name(client, content, FACTS, image="AAAA", budget=30)[2] == "文字"
    assert "images" not in client.seen[1][1]


def test_no_client_or_a_bad_name_gives_nothing(content):
    assert insight_llm.name(None, content, FACTS) == (None, "", "")
    assert insight_llm.name(FakeClient([("abc", ""), ("123", "")]), content, FACTS, image="A", budget=30) == (None, "", "")


# ── 有所感的流程 ────────────────────────────────────

def test_the_card_shows_shuffled_methods(lake):
    _open(lake)
    ids = [o.id for o in lake.options()]
    assert ids == [f"sense:{i}" for i in range(4)]


def test_a_wrong_method_ends_it_for_today(lake):
    _open(lake)
    msgs = _pick(lake, "剛")  # 湖邊只悟得到柔（水）與快（風）
    assert any("心浮氣躁" in m for m in msgs) and lake.state.player.sensing is None
    assert sensing.missed_today(lake.state, lake.content.locations["lake"])
    assert not lake._explore_can("insight", lake.content.locations["lake"])


def test_a_missed_roll_gives_a_little_xinde(lake):
    lake.rng = FixedRandom(0.99)
    _open(lake)
    before = lake.state.player.stats.get("xinde", 0)
    _pick(lake, "柔")
    assert lake.state.player.sensing is None
    assert lake.state.player.stats["xinde"] == before + lake.content.config.sense_miss_xinde


def test_letting_go_gives_the_base_insight_and_a_journal_entry(lake):
    _open(lake)
    _pick(lake, "柔")
    assert [o.id for o in lake.options()] == [sensing.DRAW, sensing.LET_GO]
    lake.choose(sensing.LET_GO)
    assert "shui" in lake.state.player.insights and lake.state.player.sensing is None
    assert lake.state.journal[0].title == "有所感・湖風"
    assert lake.state.world.marks.get(sensing.mark_key("lake"))


def test_drawing_the_same_attribute_lands_on_the_base(lake):
    _open(lake)
    _pick(lake, "快")
    req = lake.sense_request(glyph.SAMPLES["快"])
    assert not req.needs_name and req.base == "feng"
    lake.sense_draw(req)
    assert "feng" in lake.state.player.insights


def _own(g: Game, proposed=("湖心月", "一圈一圈的圓轉。")):
    _open(g)
    _pick(g, "柔")
    req = g.sense_request(glyph.SAMPLES["慢"])  # 柔＋慢＝陰：湖邊沒有陰的基本意境，悟一個自己的
    assert req.needs_name and req.attribute == "陰" and req.base is None
    return req, g.sense_draw(req, proposed)


def test_drawing_something_new_gives_a_private_insight(lake):
    req, msgs = _own(lake)
    own = lake.state.player.own_insights["悟:1"]
    assert own.name == "湖心月" and own.attribute == "陰" and own.place == "湖邊" and own.glyph == req.points
    assert "悟:1" in lake.state.player.insights and lake.world.get_insight("悟:1") is None  # 全服查不到
    assert any("你是第一個" in m for m in msgs)
    assert lake.state.journal[0].glyph == req.points
    assert "<polyline" in journal.card_html(lake.state.journal[0])
    assert lake.world.insight_first(sensing.first_key(req)) == ("湖心月", "沈浪")


def test_only_the_first_one_is_recorded(lake, content, world):
    _own(lake)
    other = Game.new(content, "王語", rng=FixedRandom(0.0), world=world)
    other.state.player.location = "lake"
    _, msgs = _own(other, ("湖中影", ""))
    assert not any("第一個" in m for m in msgs)
    assert other.state.player.own_insights["悟:1"].name == "湖中影"  # 後到的照樣自己悟、自己取名


def test_a_fallback_name_is_not_recorded_as_first(lake):
    req, msgs = _own(lake, (None, ""))
    assert lake.state.player.own_insights["悟:1"].name and not any("第一個" in m for m in msgs)
    assert lake.world.insight_first(sensing.first_key(req)) is None


def test_a_request_goes_stale_when_the_player_leaves(lake):
    _open(lake)
    _pick(lake, "柔")
    req = lake.sense_request(glyph.SAMPLES["慢"])
    lake.state.player.location = "town"
    assert lake.sense_draw(req, ("湖心月", "")) == [sensing.STALE]
    assert lake.state.player.own_insights == {}


def test_the_first_finds_go_into_the_chronicle_at_season_change(lake, content, world):
    _own(lake)
    next_season(content, world, lake)
    texts = [e.text for e in world.chronicle_before(2)[0][1]]
    assert any("感悟首悟 1 處" in t and "「湖心月」沈浪（湖邊）" in t for t in texts)


# ── 私有意境在合成與修練裡 ──────────────────────────

def test_fusing_a_private_insight_shares_the_recipe_by_attribute(lake, content, world):
    _own(lake)
    p = lake.state.player
    p.stats["xinde"], p.stamina = 100, 150
    p.member.wugong_id = "basic_fist"
    lake.forge("basic_fist", ["悟:1"], proposed=("陰風腿", ""))
    art = world.lookup_recipe(fusion.fuse_key("basic_fist", "悟:1", "陰"))
    assert art is not None and art.insight is None and art.insight_attr == "陰"
    assert art.id in p.arts or art.id in (p.member.wugong_id, p.member.neigong_id)
    other = Game.new(content, "王語", rng=FixedRandom(0.0), world=world)
    other.state.player.location = "lake"
    _own(other, ("湖中影", ""))
    other.state.player.member.wugong_id = "basic_fist"
    assert fusion.forge_request(other.state, content, world, "basic_fist", ["悟:1"]) is None  # 同屬性：查表就好


def test_cultivating_a_private_fused_art_uses_any_same_attribute_insight(lake, world):
    _own(lake)
    p = lake.state.player
    p.stats["xinde"], p.stamina = 100, 150
    p.member.wugong_id = "basic_fist"
    lake.forge("basic_fist", ["悟:1"], proposed=("陰風腿", ""))
    art = world.lookup_recipe(fusion.fuse_key("basic_fist", "悟:1", "陰"))
    assert insights.for_cultivation(lake.state, lake.content, world, art).id == "悟:1"
    msgs = lake.melt_insight("悟:1")
    assert any("不能再修練" in m for m in msgs)
    assert "屬陰" in lake.cultivate(art.id)[0]


def test_merging_with_a_private_insight_is_private_and_not_repeatable(lake):
    _own(lake)
    p = lake.state.player
    p.insights.append("shui")
    p.stats["xinde"], p.stamina = 100, 150
    assert isinstance(fusion.forge_request(lake.state, lake.content, lake.world, None, ["悟:1", "shui"]), naming.NamingRequest)
    lake.forge(None, ["悟:1", "shui"], proposed=("深潭", ""))
    made = p.own_insights["悟:2"]
    assert made.name == "深潭" and made.parents == sorted(["悟:1", "shui"])
    assert lake.world.get_insight("深潭") is None
    assert "已經合過了" in fusion.merge_problem(lake.state, lake.content, lake.world, "悟:1", "shui")


# ── 機器人 ──────────────────────────────────────────

def test_the_season_bot_finishes_every_sensing(lake):
    rng = random.Random(3)
    for _ in range(20):
        lake.state.player.sense_misses = {}
        _open(lake)
        for _ in range(3):
            choice = bot.sense_pick(lake, rng)
            if choice is None:
                break
            bot.sense_draw(lake, rng) if choice == sensing.DRAW else lake.choose(choice)
        assert lake.state.player.sensing is None
