"""玩法說明（explain-1，試玩回饋 Gary：「很多東西要一句說明，不然體力用完了還不知道在玩什麼」）。

一、行動列底下那幾行：探索、遊歷、交友這一下會怎樣（Game.action_notes，句子在 tianxia/howto.py）；有所感選做法之前先說選錯的代價。
句子待 joy 潤；這裡驗的是「說的跟規則一樣」：探索照探索真的擲骰用的那一份比重、遊歷照對手與操練的規則。"""
from __future__ import annotations

import random

import pytest
from test_explore import _lake

from tianxia import howto, sensing
from tianxia.engine import Game
from tianxia.models import ExploreMix, InsightScene, SenseMethod
from tianxia.rules import current_day


def _notes(game):
    return game.action_notes([o.id for o in game.options(odds=False)])


# ── 探索：照這個地點那一類的比例（Config.explore_mix），跟擲骰同一份 ─────────────────────


@pytest.mark.parametrize("tags, line", [
    (["營寨"], "這裡多半碰上事件，也可能遇野怪、悟意境"),  # 營寨 15／35／50
    (["城鎮"], "這裡多半碰上事件，也可能悟意境"),  # 城鎮 15／0／85：野怪那一支是 0，不提
    (["湖畔"], "這裡多半悟意境，也可能遇野怪、碰上事件"),  # 其餘 40／35／25
])
def test_the_explore_line_follows_the_mix_of_each_place_kind(game, tags, line):
    _lake(game, tags=tags)
    assert _notes(game)["act:explore"] == line


def test_the_explore_line_follows_the_config_when_it_changes(game):
    _lake(game, tags=["城鎮"])
    game.content.config.explore_mix[1] = ExploreMix(kind="town", tags=["城鎮"], weights={"insight": 60, "wild": 0, "event": 40})
    assert _notes(game)["act:explore"] == "這裡多半悟意境，也可能碰上事件"
    game.content.config.explore_mix[1] = ExploreMix(kind="town", tags=["城鎮"], weights={"insight": 50, "wild": 0, "event": 50})
    assert _notes(game)["act:explore"] == "這裡可能悟意境、碰上事件"  # 並列最大：不說「多半」


def test_the_explore_line_drops_what_cannot_happen_here_like_the_roll_does(game):
    """做不了的那一支擲骰時拿掉、比例分給另外兩支（Game._explore_can）：說明也不提。"""
    _lake(game, tags=["營寨"], enemies=())  # 沒有會打的對手：營寨也遇不到野怪
    assert _notes(game)["act:explore"] == "這裡多半碰上事件，也可能悟意境"
    game.state.player.sense_misses["lake"] = current_day(game.state)  # 今天在這裡選錯過做法：悟意境那一支沒了
    assert _notes(game)["act:explore"] == "這裡多半碰上事件"


def test_the_explore_line_and_the_roll_read_the_same_weights(game, monkeypatch):
    """說明與擲骰都讀 Game._explore_weights：換掉它，兩邊一起變（說的跟擲的不會各寫一份）。"""
    _lake(game)
    monkeypatch.setattr(Game, "_explore_weights", lambda self, loc: [("wild", 1.0)])
    assert _notes(game)["act:explore"] == "這裡多半遇野怪"
    seq = game.state.battle_seq
    game._explore()
    assert game.state.battle_seq == seq + 1  # 真的打了一場野怪


def test_the_explore_line_follows_wisdom_like_the_roll(game):
    """悟意境那一支乘悟性（武學與成長設計 6.1），擲骰跟說明都一樣：悟性夠高，城裡也會「多半悟意境」。"""
    _lake(game, tags=["城鎮"])
    game.content.config.explore_mix[1] = ExploreMix(kind="town", tags=["城鎮"], weights={"insight": 45, "wild": 0, "event": 55})
    assert _notes(game)["act:explore"].startswith("這裡多半碰上事件")
    game.state.player.stats["wis"] = 15  # ×1.3：58.5 比 55
    assert _notes(game)["act:explore"].startswith("這裡多半悟意境")


def test_the_explore_line_mentions_the_breakthrough_pill_only_when_it_can_drop(game):
    _lake(game)
    assert "破境丹" not in _notes(game)["act:explore"]  # 測試內容把機率設成 0
    game.content.config.explore_legend_chance = 0.02
    assert _notes(game)["act:explore"].endswith("；偶得破境丹")


def test_explore_line_words():
    assert howto.explore_line([]) == "這裡多半一無所獲"
    assert howto.explore_line([("insight", 0.0), ("event", 3.0)]) == "這裡多半碰上事件"  # 比重 0 的不提
    assert howto.explore_line([("insight", 2.0), ("wild", 2.0), ("event", 1.0)], "破境丹") == "這裡可能悟意境、遇野怪、碰上事件；偶得破境丹"


# ── 遊歷：打贏得什麼；自己人的地盤是操練 ─────────────────────────────────


def test_the_train_line_says_what_winning_gives_on_enemy_ground(game):
    _lake(game)
    line = _notes(game)["act:train"]
    assert line == "打贏得銀兩、心得、經驗，可能掉素材，推動戰局"  # 水寇小隊：銀兩 5、心得 10、經驗 20；湖邊推大勢


def test_the_train_line_is_a_drill_on_your_own_ground(game):
    """自己陣營的隊伍不打、改操練（Game._drill）：不冒險，只給心得與經驗（對手的 drill_reward_share），不給銀兩、素材。"""
    _lake(game)
    game.state.player.faction = "guan"
    game.content.squads["thug"].faction = "guan"
    line = _notes(game)["act:train"]
    assert line == "操練不冒險：得心得、經驗，推動戰局；不給銀兩、素材"
    game.content.config.drill_reward_share = 0.0  # 操練什麼都不給的話，就不說給
    assert _notes(game)["act:train"] == "操練不冒險：沒什麼賞，推動戰局；不給銀兩、素材"


def test_the_train_line_mentions_the_drill_where_both_sides_are(game):
    _lake(game, enemies=("thug", "boss"))
    game.state.player.faction = "guan"
    game.content.squads["thug"].faction = "guan"
    boss = game.content.squads["boss"]
    boss.reward_xinde, boss.exp = 50, 30
    # 會打的只剩翻江龍：他給心得、經驗，不給銀兩（水寇小隊的銀兩是自己人的，操練不給）
    assert _notes(game)["act:train"] == "打贏得心得、經驗，可能掉素材，推動戰局；遇上自己人是操練"


def test_the_train_line_leaves_out_the_push_where_the_place_pushes_nothing(game):
    _lake(game)
    game.content.locations["lake"].train_trend = {}
    assert _notes(game)["act:train"] == "打贏得銀兩、心得、經驗，可能掉素材"


# ── 交友：會遇上誰 ──────────────────────────────────────────


def test_the_socialize_line_says_what_you_meet(game):
    game.state.player.location = "town"
    assert _notes(game)["act:socialize"] == "結識這裡的人，碰上交友的事"


def test_the_socialize_line_names_the_figure_you_will_talk_to(game, monkeypatch):
    monkeypatch.setattr(Game, "_socialize_figure", lambda self: "sage")
    game.state.player.location = "town"
    assert _notes(game)["act:socialize"] == "和隱士談話，聊得投機情誼會漲"


def test_no_notes_in_the_prologue(prologue_content, world):
    hut = Game.new(prologue_content, "沈浪", rng=random.Random(0), world=world, prologue=True)
    assert hut.action_notes(["act:explore", "act:train", "act:socialize"]) == {}


def test_notes_only_for_what_is_on_the_menu(game):
    game.state.player.location = "town"  # 小鎮沒有對手：沒有遊歷
    assert set(_notes(game)) == {"act:explore", "act:socialize"}


# ── 有所感：選做法之前先說選錯的代價（sensing.choose：選錯了這一處今天不再悟）─────────────────


def _feeling(game, prologue=False):
    scene = InsightScene(
        id="lake_view", title="湖光", text="湖水拍岸。", locations=["lake"], prologue=prologue,
        methods=[SenseMethod(attribute=a, text=t) for a, t in (("柔", "看水"), ("剛", "打水"), ("快", "追風"), ("慢", "靜坐"))],
    )
    game.content.insight_scenes = {scene.id: scene}
    game.state.player.location = "lake"
    sensing.start(game.state, game.content, scene, random.Random(0))
    return scene


def test_the_feeling_card_warns_before_a_method_is_chosen(game):
    _feeling(game)
    text = game.scene_text()
    assert sensing.MISS_WARNING in text and text.index("湖水拍岸") < text.index(sensing.MISS_WARNING)
    assert sensing.MISS_WARNING == "選錯了做法，今天在這裡就悟不出了。"


def test_the_warning_matches_the_rule(game):
    """說的是真的：選錯了，這一處今天不再落在悟意境那一支（Game._explore_can 看 sensing.missed_today）。"""
    scene = _feeling(game)
    wrong = [scene.methods[j].attribute for j in game.state.player.sensing.order].index("剛")  # 湖邊悟得到水、風：剛是錯的
    game.choose(f"sense:{wrong}")
    assert sensing.missed_today(game.state, game.content.locations["lake"])
    assert not game._explore_can("insight", game.content.locations["lake"])


def test_no_warning_once_drawing_or_in_the_hut(game):
    _feeling(game)
    game.state.player.sensing.stage, game.state.player.sensing.method = "draw", "柔"
    assert "有所感・湖光" in game.scene_text() and sensing.MISS_WARNING not in game.scene_text()
    game.state.player.sensing = None
    _feeling(game, prologue=True)  # 序章草廬的四景：四個做法都對，不嚇人
    assert "有所感・湖光" in game.scene_text() and sensing.MISS_WARNING not in game.scene_text()
