"""減法季 2e：探索的三件小修（2d 驗收開的 FB-880、881、882；企劃者 2026-10-26）。

1. FB-880：揭了這裡的討伐懸賞、人又站在這裡，2d 是每一趟都撞懸賞那一路——打不贏的人每趟都輸、一直掉血。企劃者 2026-10-26：
   「勝算是必敗時不強制打懸賞，照原本的表抽。」判勝算用鈕上寫的那一個函式（`Game.odds`），必敗就當這一處沒有懸賞（對手、頭目、鈕上的字、
   行動列底下那一行都照沒有懸賞時），變強到不再必敗自動回到強制遭遇；打探懸賞照舊；判勝算不碰 `Game.rng`。
2. FB-881：「這一帶的對手已經配不上你，所得有限」只在這一場打贏而且真的因為對手檔打了折才寫，輸了、平手了、沒打折都不寫。
3. FB-882：鈕上與四格那一格的小字照這一處此刻的比重寫（跟行動列底下那一行同一份），寺的表是事件 50、感悟 30，不再寫「寺裡多悟」。
用正式內容（season21），整個檔標 slow。"""
from __future__ import annotations

from unittest import mock

import pytest
from jianfa_kit import jianfa_game, ready

from tianxia import explore_one, team
from tianxia.encounter import EncounterResult
from tianxia.state import Bounty

pytestmark = pytest.mark.slow

LOSE = "必敗"
CLOSE_OUTLEVEL = "這一帶的對手已經配不上你，所得有限。"


def _fight(tier: str = "大勝"):
    return mock.patch.object(team, "fight", return_value=EncounterResult(tier=tier, margin=50, our_power=200, difficulty=40))


def _beat(beat: str):
    return mock.patch.object(explore_one, "draw", return_value=beat)


def _reset(game) -> None:
    game.state.player.stamina = 250.0
    game.state.pending_event = None
    game.state.player.sensing = None


def _hopeless_game(loc: str = "yingchuan_wilds"):
    """沒裝武學的 20 級官軍站潁川郊野：威力 0，對這裡的每一路都是必敗。"""
    game = ready(jianfa_game(), side="guan", loc=loc, level=20)
    game.state.player.member.wugong_id = None
    return game


def _able(game) -> None:
    """裝上起手那一門拳腳：對黃巾散兵「難分勝負」，不是必敗。"""
    game.state.player.member.wugong_id = "jichu_quanjiao"


def _strike(game, loc_id: str = "yingchuan_wilds", squad: str = "shanzei") -> Bounty:
    b = Bounty(id="s1", kind="strike", faction="guan", week=1, expires=1e12, silver=10, deeds=1, location=loc_id, squad=squad,
               takers=[game.state.player.name])
    game.state.world.bounties.append(b)
    return b


def _note(game) -> str:
    return game.action_notes([o.id for o in game.options(odds=False)])["act:explore"]


# ── 1. FB-880 ──


def test_a_hopeless_bounty_is_left_to_the_table_as_if_there_were_none():
    game = _hopeless_game()
    assert game.odds("shanzei") == LOSE
    cfg, loc = game.content.config.jianfa, game.content.locations["yingchuan_wilds"]
    before, note_before, mostly_before = game.outing_plan(), _note(game), game.mostly_here()
    _strike(game)
    plan = game.outing_plan()
    assert plan == before  # 對手、頭目、比重、鈕上的字，整份跟沒有懸賞時一樣
    assert plan.how == "foe" and plan.foe.id != "shanzei" and plan.weights == explore_one.weights(cfg, loc, has_foes=True)
    assert plan.hint == "野外多敵" and game.mostly_here() == mostly_before == "野外多敵"
    assert "有賞" not in plan.hint
    assert _note(game) == note_before and "討伐" not in _note(game) and "每一趟" not in _note(game)
    label = next(o for o in game.options(odds=False) if o.id == "act:explore").label
    assert label.endswith("・野外多敵）")


def test_trips_follow_the_table_while_the_bounty_is_hopeless_and_never_target_it():
    game = _hopeless_game()
    b = _strike(game)
    tags, foes = set(), set()
    for _ in range(40):
        _reset(game)
        with _fight("落敗"):
            game.choose("act:explore")
        tags.add(game.state.journal[0].tag)
    foes = {r.opponent for r in game.state.battles}
    assert len(tags) >= 3, tags  # 遇事、得料、有悟都碰得到，不是每一趟都遇敵
    assert game.content.squads["shanzei"].name not in foes and foes <= {game.content.squads["dipi"].name}
    assert next(x for x in game.state.world.bounties if x.id == b.id).takers == [game.state.player.name]  # 沒放棄也沒交差


def test_it_goes_back_to_the_forced_fight_as_soon_as_the_bounty_is_no_longer_hopeless():
    game = _hopeless_game()
    _strike(game)
    assert game.outing_plan().how == "foe"
    _able(game)
    assert game.odds("shanzei") != LOSE
    plan = game.outing_plan()
    assert plan.how == "bounty" and plan.foe.id == "shanzei" and plan.boss is None and plan.hint == "野外有賞"
    assert plan.weights == explore_one.encounter_only() and "每一趟" in _note(game)
    game.state.player.member.wugong_id = None  # 又回到必敗：沒有留下什麼
    assert game.outing_plan().how == "foe" and "每一趟" not in _note(game)


@pytest.mark.parametrize("word", ["穩勝", "有把握", "五五波", "難分勝負", "凶險"])
def test_only_the_lose_word_releases_the_bounty(word):
    game = ready(jianfa_game(), side="guan", loc="yingchuan_wilds")
    _strike(game)
    with mock.patch.object(game, "odds", return_value=word) as odds:
        assert game.outing_plan().how == "bounty"
        odds.assert_called_with("shanzei")  # 問的是懸賞那一路，用鈕上的同一個函式
    with mock.patch.object(game, "odds", return_value=LOSE):
        assert game.outing_plan().how == "foe"


def test_asking_the_odds_never_touches_the_game_rng():
    for hopeless in (True, False):
        game = _hopeless_game()
        if not hopeless:
            _able(game)
        _strike(game)
        state = game.rng.getstate()
        game.outing_plan()
        game.options()
        _note(game)
        game.mostly_here()
        assert game.rng.getstate() == state, hopeless


def test_without_a_bounty_the_odds_are_never_asked():
    """沒有懸賞的趟連勝算都不算：同一個種子下跟修前逐位元組一樣。"""
    game = _hopeless_game()
    with mock.patch.object(game, "odds", side_effect=AssertionError("沒有懸賞不該算勝算")):
        game.outing_plan()
        game.options(odds=False)
        _note(game)
        _reset(game)
        with _fight("落敗"):
            game.choose("act:explore")


def test_a_bounty_for_another_place_or_a_friendly_squad_does_not_ask_either():
    game = _hopeless_game()
    _strike(game, loc_id="yingshui", squad="hetan_popi")  # 揭的是別處的
    with mock.patch.object(game, "odds", side_effect=AssertionError("不在這裡的懸賞不該算勝算")):
        assert game.outing_plan().how == "foe"


def test_the_scout_bounty_still_counts_when_the_strike_one_is_released():
    game = _hopeless_game()
    _strike(game)
    scout = Bounty(id="c1", kind="scout", faction="guan", week=1, expires=1e12, silver=10, deeds=1, location="yingchuan_wilds",
                   takers=[game.state.player.name])
    game.state.world.bounties.append(scout)
    assert game.outing_plan().how == "foe"
    _reset(game)
    with _beat("material"):
        game.choose("act:explore")
    done = next(x for x in game.state.world.bounties if x.id == scout.id)
    assert game.state.player.name in done.done_by  # 打探：出門一趟就算，照舊


def test_a_hopeless_bounty_at_a_boss_only_place_leaves_the_boss_roll_alone():
    """官軍在長社沒有一般對手、只有頭目：揭了討伐又必敗時，這一處跟沒有懸賞一樣（頭目照舊擲、遭遇那格分給其餘）。"""
    game = _hopeless_game(loc="changshe")
    before = game.outing_plan()
    assert before.how is None and before.boss is not None and before.weights[explore_one.ENCOUNTER] == 0
    _strike(game, loc_id="changshe")
    assert game.odds("shanzei") == LOSE and game.outing_plan() == before  # 頭目還在、遭遇那格還是 0
    _able(game)
    assert game.odds("shanzei") != LOSE
    forced = game.outing_plan()
    assert forced.how == "bounty" and forced.boss is None and forced.weights == explore_one.encounter_only()  # 打得過才是整趟懸賞、不擲頭目


# ── 2. FB-881 ──


def _story(game, tier: str, loc_beat: str = "encounter") -> str:
    _reset(game)
    with _beat(loc_beat), _fight(tier):
        return game.choose("act:explore")[0]


def _closes(game, story: str) -> bool:
    return any(line in story for line in game.content.outing_lines["close"]["outlevel"]) or CLOSE_OUTLEVEL in story


def test_the_out_of_your_league_close_is_only_written_when_you_won_and_it_cut_the_pay():
    game = ready(jianfa_game(), side="guan", loc="yingchuan", level=30)  # 城裡的地痞：難度 8，三十級低三檔
    assert _closes(game, _story(game, "大勝"))
    assert _closes(game, _story(game, "險勝"))
    assert not _closes(game, _story(game, "僵持"))  # 平手：沒拿到什麼，也不是因為對手檔
    assert not _closes(game, _story(game, "落敗"))
    wilds = ready(jianfa_game(), side="guan", loc="yingchuan_wilds", level=20)  # 難度 8 的流寇，二十級低兩檔
    for tier in ("僵持", "落敗"):
        assert not _closes(wilds, _story(wilds, tier)), tier
    assert _closes(wilds, _story(wilds, "大勝"))


def test_no_close_when_the_foe_did_not_cut_the_pay():
    game = ready(jianfa_game(), side="guan", loc="yingchuan_wilds", level=1)  # 一級打流寇：同一檔
    for tier in ("大勝", "僵持", "落敗"):
        assert not _closes(game, _story(game, tier)), tier


def test_a_lost_fight_does_not_read_as_a_won_one_in_the_same_paragraph():
    """FB-881 原例：吃了虧只得退走，下一句不再說對手配不上你。"""
    game = ready(jianfa_game(), side="guan", loc="yingchuan_wilds", level=20)
    story = _story(game, "落敗")
    assert not _closes(game, story)
    assert "配不上你" not in story
