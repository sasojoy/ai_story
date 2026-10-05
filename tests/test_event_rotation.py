"""joy #16 的事件輪替（PlayerState.event_rounds）只在事件真的端到玩家眼前時才往前走（Game._present）。

events.pick_event 只負責「這一輪還沒看過的裡面抽一則」，不改狀態；記帳在 events.note_round，只有 Game._present
呼叫它。所以選單、勝算、地圖、管理者頁面、機器人挑選項怎麼預覽，都不會讓輪替前進（取代 FB-058 的看過次數遞減，
那一套的計次也是放在 _present）。"""
import random
from collections import Counter

from conftest import walk_to
from tianxia import bot, bot_policy, events
from tianxia.engine import Game
from tianxia.events import pick_event
from tianxia.models import ExploreMix
from tianxia.state import BotProfile, GameState


def _rounds_total(state) -> Counter:
    return Counter(eid for ids in state.player.event_rounds.values() for eid in ids)


def test_pick_event_alone_never_advances_the_rotation(state, content):
    rng = random.Random(0)
    for _ in range(10):
        assert pick_event(state, content, "explore", rng) is not None
        assert pick_event(state, content, "socialize", rng) is not None
    assert state.player.event_rounds == {}


def test_exploring_into_an_event_records_it_once(game):
    game.content.config.explore_mix = [ExploreMix(kind="wild", tags=[], weights={"event": 1})]
    game.choose("act:explore")
    assert game.state.pending_event == "drunk"
    assert game.state.player.event_rounds == {"town:explore": ["drunk"]}
    game.choose("choice:1")  # 選一個選項不再多記一次
    assert game.state.player.event_rounds == {"town:explore": ["drunk"]}


def test_socializing_into_an_event_records_it_once(game):
    game.choose("act:socialize")
    assert game.state.pending_event == "join"
    assert game.state.player.event_rounds == {"town:socialize": ["join"]}


def test_training_into_an_event_records_it_once(game):
    """遊歷打完接戰後事件走 _train 的事件那一段、一樣經過 _present。夾具湖邊的遊歷事件只有 chain_a。"""
    game.content.config.train_event_chance = 1.0
    walk_to(game, "lake")
    game.choose("act:train")
    assert game.state.pending_event == "chain_a"
    assert game.state.player.event_rounds == {"lake:train": ["chain_a"]}


def test_a_next_event_chain_and_a_bare_present_do_not_touch_the_rotation(game):
    """next_event 串接、晉升召見這類不是從池子抽出來的事件，不算進任何一輪（joy 的輪替本來就只記抽中的）。"""
    game._present(game.content.events["chain_a"])
    assert game.state.player.event_rounds == {}
    game.choose("choice:0")
    assert game.state.pending_event == "chain_b"
    assert game.state.player.event_rounds == {}


def test_a_seen_through_pool_restarts_when_the_next_event_is_shown(game):
    """整池輪完，下一次端出來的是新一輪的第一則：這時才清空、重開。"""
    content = game.content
    content.config.explore_mix = [ExploreMix(kind="wild", tags=[], weights={"event": 1})]
    content.events["brawl"] = content.events["drunk"].model_copy(update={"id": "brawl", "title": "鬥毆"})
    shown = []
    for _ in range(3):
        game.choose("act:explore")
        shown.append(game.state.pending_event)
        game.state.pending_event = None
    assert sorted(shown[:2]) == ["brawl", "drunk"]
    assert shown[2] != shown[1]  # 換輪時不會連著兩次一樣
    assert game.state.player.event_rounds == {"town:explore": [shown[2]]}


def test_previews_do_not_advance_the_rotation(game):
    """選單（含勝算）、狀態列、場景、地圖、地點詳情、走法、管理者的事件清單都只是看：輪替一步都不動。"""
    content = game.content
    content.config.admins = ["沈浪"]
    for _ in range(3):
        game.options()
        game.options(odds=False)
        game.status_data()
        game.scene_text()
        game.world_map_svg()
        game.minimap_svg()
        game.map_places()
        game.place_detail("lake")
        game.travel_options("lake")
        game.admin_fires()
        game.admin_battles()
        game.quest_text()
        game.guide_box()
    assert game.state.player.event_rounds == {}


def _watch_presents(monkeypatch):
    """記下每一次 _present 端出的事件，並確認 note_round 只在 _present 裡面被叫到。"""
    presented: list[str] = []
    inside = {"depth": 0}
    real_present, real_note = Game._present, events.note_round

    def present(self, event, *args, **kwargs):
        inside["depth"] += 1
        try:
            presented.append(event.id)
            return real_present(self, event, *args, **kwargs)
        finally:
            inside["depth"] -= 1

    def note(*args, **kwargs):
        assert inside["depth"] > 0, "輪替在 _present 以外被記了一筆"
        return real_note(*args, **kwargs)

    monkeypatch.setattr(Game, "_present", present)
    monkeypatch.setattr(events, "note_round", note)
    return presented


def test_a_bot_season_only_advances_the_rotation_through_present(content, world, monkeypatch):
    """機器人整季（bot.play_season 每一步先看選單才挑）：每一步新記進輪替的事件，一定是這一步真的端出來的。"""
    presented = _watch_presents(monkeypatch)
    content.config.train_event_chance = 1.0
    before = {"rounds": Counter(), "shown": 0}

    def observe(game):
        rounds = _rounds_total(game.state)
        added = rounds - before["rounds"]
        shown_now = Counter(presented[before["shown"]:])
        assert not (added - shown_now), (added, shown_now)
        before["rounds"], before["shown"] = rounds, len(presented)

    game = bot.play_season(content, seed=3, max_steps=400, observe=observe, world=world)
    assert presented and game.state.player.event_rounds  # 真的有端出事件、也真的記了


def test_server_bot_turns_only_advance_the_rotation_through_present(content, world, monkeypatch):
    presented = _watch_presents(monkeypatch)
    game = Game.new(content, "假人甲", rng=random.Random(5), world=world)
    profile = BotProfile(personality="普通", seed=5, season_number=1)
    rng = random.Random(5)
    for _ in range(150):
        before_rounds, before_shown = _rounds_total(game.state), len(presented)
        bot_policy.take_turn(game, profile, rng)
        added = _rounds_total(game.state) - before_rounds
        assert not (added - Counter(presented[before_shown:]))
        game.advance(1800)
    assert presented


def test_old_saves_with_the_retired_seen_counter_still_load(game):
    """FB-058 的 event_seen 已經拿掉（joy 的輪替取代了它）：舊存檔裡還有這一欄照樣讀得進來。"""
    raw = game.state.model_dump(mode="json")
    raw["player"]["event_seen"] = {"drunk": 3}
    loaded = GameState.model_validate(raw)
    assert not hasattr(loaded.player, "event_seen")
    assert loaded.player.event_rounds == {}
