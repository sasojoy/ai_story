"""初入江湖（新手引導第四段，Joy 2026-10-17「不要讓玩家可以亂點，新玩家現在迷路機率太高」）：走出草廬到了潁川，
賣茶的老周一步一步帶：醫館療傷 → 操練 → 修練 → 出城到潁水河畔練功 → 野外探索 → 進店再出店 → 打開輿圖（新手引導重做，Joy 2026-10-22）。
走這幾步時「此地還能做」只留教到的，畫面一樣一樣亮。"""
import random

import pytest

from tianxia import prologue
from tianxia.engine import Game
from tianxia.state import ONBOARDING_VERSION

STEPS = ["e1_clinic", "e2_drill", "e3_cultivate", "e4_field", "e5_wild", "e6_shops", "e7_world"]


@pytest.fixture
def newcomer(real):
    """剛走出草廬、到了潁川的真人：帶著雪恥留下的內傷，身上有師父給的盤纏。"""
    game = Game.new(real, "沈浪", rng=random.Random(0))
    p = game.state.player
    p.tutorial_step = real.tutorial.prologue_steps
    p.location = "yingchuan"
    p.member.injury = 12.0
    p.stats["silver"] = 30
    return game


def _ids(game):
    return [o.id for o in game.options()]


def _step(game):
    return game.content.tutorial.steps[game.state.player.tutorial_step].id


def test_the_seven_steps_follow_the_farewell(real):
    t = real.tutorial
    assert [s.id for s in t.steps[t.prologue_steps:]] == STEPS
    assert all(not s.season_one for s in t.steps[t.prologue_steps:])


def test_arriving_shows_only_the_clinic_under_here(newcomer):
    assert _step(newcomer) == "e1_clinic"
    box = newcomer.guide_box()
    assert box["speaker"] == "賣茶的老周" and box["key"] == "e1_clinic"
    ids = _ids(newcomer)
    assert "act:heal" in ids and "act:explore" in ids and any(i.startswith("move:") for i in ids)
    assert not any(i in ids for i in ("act:smith", "act:bounties", "act:arena")) and not any(i.startswith("learn:") for i in ids)
    view = newcomer.onboard_view()
    assert "orders" not in view["reveal"] and "tab:map" in view["reveal"]
    assert "tab:news" in view["reveal"]  # 見聞跟輿圖一起在出師那一步亮（玩家反映「看不到見聞」，Joy 2026-10-22）
    assert newcomer.enlist_glow(ids) == ["act:heal"]
    assert newcomer.prologue_view() is None  # 草廬的規矩（略過序章、師父的框）不跟出來


def test_walking_the_seven_steps_opens_everything(newcomer):
    p = newcomer.state.player
    newcomer.choose("act:heal")
    assert _step(newcomer) == "e2_drill"
    assert "act:drill" in _ids(newcomer) and "act:practice" in newcomer.onboard_view()["reveal"]
    newcomer.choose("act:drill")
    assert _step(newcomer) == "e3_cultivate"
    p.stats["xinde"] = 500
    newcomer.practice("武學")
    assert _step(newcomer) == "e4_field"
    newcomer.choose(next(i for i in _ids(newcomer) if i.startswith("move:yingshui")))
    newcomer.advance(3600)
    assert p.location == "yingshui"
    for _ in range(30):  # 打贏一場練功才算（輸了把氣血體力補回來再打）
        p.stamina, p.member.injury = 250.0, 0.0
        newcomer.choose("explore:practice")
        if _step(newcomer) != "e4_field":
            break
    assert _step(newcomer) == "e5_wild"
    p.stamina = 250.0
    newcomer.choose("explore:gather")
    while newcomer.state.pending_event is not None:  # 撞上的事件先了結
        newcomer.choose(next(i for i in _ids(newcomer) if i.startswith("choice:")))
    assert _step(newcomer) == "e6_shops"
    newcomer.choose(next(i for i in _ids(newcomer) if i.startswith("move:yingchuan")))
    newcomer.advance(3600)
    assert "act:smith" in _ids(newcomer) and "act:arena" not in _ids(newcomer)
    newcomer.choose("act:smith")
    assert _step(newcomer) == "e6_shops"  # 進了店還不算：出店才算（下一步才不會被店面蓋住）
    newcomer.choose("smith:back")
    assert _step(newcomer) == "e7_world"
    assert "act:arena" in _ids(newcomer)
    newcomer.view_map()
    assert p.tutorial_step == len(newcomer.content.tutorial.steps)
    assert newcomer.onboard_view() is None


def test_no_injury_skips_the_clinic(newcomer):
    newcomer.state.player.member.injury = 0.0
    newcomer.view_map()  # 任何一下動作都看一次：沒有內傷，醫館那一步直接過
    assert _step(newcomer) == "e2_drill"


def test_a_short_purse_still_counts_as_having_gone_to_the_clinic(newcomer):
    newcomer.state.player.member.injury = 200.0  # 盤纏不夠全治：治一部分也算去過
    newcomer.choose("act:heal")
    assert newcomer.state.player.member.injury > 0 and _step(newcomer) == "e2_drill"


def test_skipping_ends_it(newcomer):
    newcomer.skip_tutorial()
    assert newcomer.onboard_view() is None and "act:smith" in _ids(newcomer)


def test_bots_and_scripts_never_walk_it(real):
    t = real.tutorial
    script = Game.new(real, "腳本", rng=random.Random(0))
    bot = Game.new(real, "假人", rng=random.Random(0), graduated=True)
    for g in (script, bot):
        assert g.state.player.tutorial_step == len(t.steps) and g.onboard_view() is None


def test_players_out_of_the_hut_before_this_version_skip_it(newcomer, real):
    from tianxia.engine import ONBOARD_SEGMENT

    p = newcomer.state.player
    p.onboarding = ONBOARD_SEGMENT - 1  # 初入江湖上線之前
    again = Game(real, newcomer.state, world=newcomer.world)
    assert again.state.player.tutorial_step == len(real.tutorial.steps)
    assert again.onboard_view() is None


def test_players_still_in_the_hut_walk_it_after_the_upgrade(real):
    game = Game.new(real, "草廬裡的", rng=random.Random(0), prologue=True)
    game.state.player.onboarding = ONBOARDING_VERSION - 1
    again = Game(real, game.state, world=game.world)
    assert again.state.player.tutorial_step == 0 and prologue.active(again.state, real)


def test_joining_a_side_hands_the_rest_to_the_recruiter(newcomer):
    """走到最後一步（投靠與輿圖）就投靠了：初入江湖當場走完，框不跟引薦人搶。"""
    p = newcomer.state.player
    p.tutorial_step = len(newcomer.content.tutorial.steps) - 1
    p.location = "changshe"
    newcomer.choose("faction:guan")
    newcomer.choose("faction:confirm")
    assert p.faction == "guan" and p.tutorial_step == len(newcomer.content.tutorial.steps)
    assert newcomer.onboard_view() is None


@pytest.mark.parametrize(("old", "new"), [(11, "e1_clinic"), (12, "e2_drill"), (13, "e6_shops"), (14, "e7_world"), (15, None)])
def test_players_halfway_through_the_four_steps_land_on_the_matching_seven_step(newcomer, real, old, new):
    """新手引導重做（ONBOARDING_VERSION 5）：章是 4（老周四步）的存檔讀檔時接到七步裡對應的那一步；走完的照舊走完。"""
    p = newcomer.state.player
    p.onboarding, p.tutorial_step = 4, old
    again = Game(real, newcomer.state, world=newcomer.world)
    step = again.state.player.tutorial_step
    assert (real.tutorial.steps[step].id if step < len(real.tutorial.steps) else None) == new
    assert again.state.player.onboarding == ONBOARDING_VERSION


def test_a_save_stopped_at_the_old_rest_step_gets_pills_for_the_new_one(real):
    game = Game.new(real, "草廬裡的", rng=random.Random(0), prologue=True)
    p = game.state.player
    p.onboarding, p.tutorial_step, p.stamina_pills = 4, 6, 0  # 停在以前「調息」那一步，身上沒丹
    again = Game(real, game.state, world=game.world)
    assert again.state.player.tutorial_step == 6 and again.state.player.stamina_pills == 3


def test_the_shop_step_also_passes_by_walking_out_of_town(newcomer):
    """逛鋪子那一步（e6）：沒進鋪子、直接出城也算過（Joy 2026-10-22）；走回城裡不算。"""
    p = newcomer.state.player
    p.tutorial_step = [s.id for s in newcomer.content.tutorial.steps].index("e6_shops")
    p.location = "yingshui"
    newcomer.choose(next(i for i in _ids(newcomer) if i.startswith("move:yingchuan")))
    newcomer.advance(3600)
    assert p.location == "yingchuan" and _step(newcomer) == "e6_shops"  # 回到城裡還不算
    newcomer.choose(next(i for i in _ids(newcomer) if i.startswith("move:yingshui")))
    newcomer.advance(3600)
    assert p.location == "yingshui" and _step(newcomer) == "e7_world"
