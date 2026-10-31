"""FB-812：「改幫…」隨時都能換（減法季批 3c 修正輪；整合設計 3.2「隨時換」，PM 2026-10-26 定）。

批 3c 把 faction:lean:<side> 放在「此地還能做」的選單上，結果在路上、有事件待選、人站在正在打決戰的大區時按不到（選單只剩那些）。
引擎改成接受它不看選單：豪強、四勝利開著、賽季在跑就收；帳照舊不清、不發傳聞、不扣體力；決戰那一場的戰功照舊記參戰那一軍，
開打了照決戰的規則這一場照舊站原來那一邊（ALLY_STAYS）。「此地還能做」那顆鈕照留。
唯一的例外是有事件待選（FB-820，PM 2026-10-26）：不收，回 wins.LEAN_EVENT_PENDING。正式內容、建 Game，整個檔標 slow。"""
from __future__ import annotations

import pytest

from wins_kit import wins_content, wins_game
from tianxia import atlas, wins
from tianxia.characters import CharacterStore
from tianxia.engine import Game

pytestmark = pytest.mark.slow

T0 = 1_792_549_800.0
NOPE = ["（此刻無法這麼做。）"]


def _gentry(**kw) -> Game:
    game = wins_game(faction="haoqiang", ally="guan", at=kw.pop("at", "zhuo_militia_hall"), **kw)
    p = game.state.player
    p.contrib, p.ledgers = 30, {"guan": 30}
    game.sync(T0)
    return game


def _lean_ids(game: Game) -> list[str]:
    return [o.id for o in game.options(odds=False) if o.id.startswith(wins.LEAN_PREFIX)]


def _refused(game: Game, option_id: str = "faction:lean:huang") -> bool:
    """被擋下來：回「此刻無法這麼做」，而且什麼都沒動、江湖紀錄不多一則（擋在選單那一關；放進去再被 _lean_step 擋會多寫一則）。"""
    before = (len(game.state.journal), game.state.player.ally, game.state.player.lean_changed, game.state.player.stamina)
    msgs = game.choose(option_id)
    return msgs == NOPE and before == (len(game.state.journal), game.state.player.ally, game.state.player.lean_changed, game.state.player.stamina)


def _assert_switched(game: Game, msgs: list[str], rumors: int, stamina: float) -> None:
    p = game.state.player
    assert msgs and msgs[0] == wins.LEAN_DONE.format(side="黃巾軍", old="官軍"), msgs
    assert (p.ally, p.lean_changed, p.defected, p.contrib, p.ledgers) == ("huang", 1, False, 30, {"guan": 30})
    assert len(game.state.world.rumors) == rumors  # 不發傳聞
    assert p.stamina == stamina  # 不花體力
    assert game.world.roll_of(p.name) == "haoqiang@huang"
    assert game.state.journal[0].title == "改幫黃巾軍"


# ── 在路上 ─────────────────────────────


def test_lean_switch_works_on_the_road():
    game = _gentry()
    game.travel(game.content.locations[game.state.player.location].connections[0], "walk")
    p = game.state.player
    assert p.journey is not None
    assert _lean_ids(game) == []  # 選單上本來就沒有（在路上只剩路上的事）
    rumors, stamina, journey = len(game.state.world.rumors), p.stamina, p.journey.path[:]
    msgs = game.choose("faction:lean:huang")
    _assert_switched(game, msgs, rumors, stamina)
    assert p.journey is not None and p.journey.path == journey  # 人照樣在路上，沒被改道


# ── 有事件待選 ─────────────────────────────


def test_lean_switch_is_refused_with_an_event_pending():
    """FB-820（PM 2026-10-26，設計 3.2「隨時換」的唯一例外）：有事件待選時不收改幫，回一句、什麼都不動——不然同一則事件裡
    依陣營出現的選項（factions_none）兩邊都挑得到。事件了結之後照常換得了。"""
    game = _gentry()
    event_id = next(iter(game.content.events))
    game.state.pending_event = event_id
    assert _lean_ids(game) == []  # 選單只剩事件的選項
    choices = [o.id for o in game.options(odds=False)]
    p = game.state.player
    before = (len(game.state.journal), p.ally, p.lean_changed, p.stamina, game.world.roll_of(p.name))
    assert game.choose("faction:lean:huang") == [wins.LEAN_EVENT_PENDING]
    assert before == (len(game.state.journal), p.ally, p.lean_changed, p.stamina, game.world.roll_of(p.name))
    assert game.state.pending_event == event_id and [o.id for o in game.options(odds=False)] == choices  # 事件與它的選項照舊
    game.state.pending_event = None
    rumors, stamina = len(game.state.world.rumors), p.stamina
    _assert_switched(game, game.choose("faction:lean:huang"), rumors, stamina)  # 了結之後照常換


# ── 決戰 ─────────────────────────────


def _in_region(content, region_id: str) -> str:
    return next(loc for loc in content.locations if (r := atlas.region_of(content, loc)) is not None and r.id == region_id)


def _showdown(game: Game) -> object:
    """管理者「立刻開」長社火攻，回傳那一場的定義；人站到決戰的大區。"""
    game.content.config.admins = [game.state.player.name]
    game.admin_start_showdown("changshe_fire", T0 + 60)
    definition = game.content.battles[game.world.get_battle().battle_id]
    game.state.player.location = _in_region(game.content, definition.region)
    return definition


def _start_fighting(game: Game) -> None:
    """集結截止，決戰開打（排程推一下），每個人再同步一次。"""
    t = game.world.get_battle().muster_deadline_real + 1
    Game.for_world(game.content, game.world).world_tick(t)
    game.sync(t)
    assert game.world.get_battle().phase != "muster"


def test_lean_switch_works_while_mustering_and_follows_the_roster():
    game = _gentry()
    _showdown(game)
    game.choose("battle:join:guan")
    assert "faction:lean:huang" in _lean_ids(game)  # 集結時選單照常有它
    rumors, stamina = len(game.state.world.rumors), game.state.player.stamina
    msgs = game.choose("faction:lean:huang")
    assert any("集結名單上，你也跟著換到黃巾軍那一邊" in line for line in msgs), msgs
    assert game.world.get_battle().participants[game.state.player.name].faction == "huang"
    _assert_switched(game, msgs, rumors, stamina)


def test_lean_switch_works_in_the_fighting_region_and_the_fight_stays_on_the_joined_side():
    """開打之後人在決戰的大區（選單只剩戰鬥的事）：改幫照收；這一場照舊站原來那一邊（ALLY_STAYS），戰功照舊記參戰那一軍。"""
    game = _gentry()
    _showdown(game)
    game.choose("battle:join:guan")
    _start_fighting(game)
    assert _lean_ids(game) == []  # 修之前：開打之後選單上沒有
    rumors, stamina = len(game.state.world.rumors), game.state.player.stamina
    msgs = game.choose("faction:lean:huang")
    assert any("已經開打，這一場你照舊站在官軍那一邊" in line for line in msgs), msgs
    _assert_switched(game, msgs, rumors, stamina)
    me = game.world.get_battle().participants[game.state.player.name]
    assert me.faction == "guan"
    assert game._showdown_credits(me)  # 這一場的戰功照舊記進參戰那一軍那一本（官軍）
    assert game._side() == "huang"  # 打完這一場才算黃巾的人


def test_lean_switch_works_for_a_gentry_who_has_not_joined_the_fighting_battle():
    game = _gentry()
    _showdown(game)
    other = wins_game(name="乙客", faction="haoqiang", ally="guan", at="zhuo_militia_hall", world=game.world)
    other.state.player.location = game.state.player.location
    other.sync(T0)
    CharacterStore(other.world.db).save(other.state)
    game.choose("battle:join:guan")
    _start_fighting(game)
    other.sync(game.world.get_battle().muster_deadline_real + 1)
    assert other.state.player.name not in game.world.get_battle().participants
    assert _lean_ids(other) == []
    assert other.choose("faction:lean:huang")[0] == wins.LEAN_DONE.format(side="黃巾軍", old="官軍")
    assert other.state.player.ally == "huang"


# ── 照舊該擋的 ─────────────────────────────


def test_the_place_menu_button_stays():
    game = _gentry(at="changshe")
    assert _lean_ids(game) == ["faction:lean:huang"]


def test_lean_is_still_refused_when_it_should_be():
    game = _gentry()
    game.travel(game.content.locations[game.state.player.location].connections[0], "walk")
    assert _refused(game, "faction:lean:guan")  # 本來就幫它
    assert _refused(game, "faction:lean:haoqiang")  # 不是它能幫的那一軍
    assert _refused(game, "faction:lean:nobody")
    assert game.state.player.ally == "guan" and game.state.player.lean_changed == 0
    army = wins_game(name="乙客", faction="guan", at="changshe")
    army.travel(army.content.locations["changshe"].connections[0], "walk")
    assert _refused(army)  # 兩軍的人不能改
    free = wins_game(name="丙客", at="changshe")
    free.travel(free.content.locations["changshe"].connections[0], "walk")
    assert _refused(free)  # 散人不能改
    assert (army.state.player.faction, free.state.player.faction) == ("guan", None)


def test_lean_is_refused_when_the_season_is_not_running():
    ended = _gentry()
    ended.state.world.ended = True
    assert _refused(ended)
    paused = _gentry(name="乙客")
    assert paused.world.pause_clock(T0 + 5)
    assert _refused(paused)


def test_lean_is_refused_while_the_season_is_still_preparing():
    content = wins_content()
    content.config.auto_open_first_season = False  # 管理者還沒開季
    game = wins_game(content, faction="haoqiang", ally="guan", at="zhuo_militia_hall")
    assert [o.id for o in game.options()] == ["season:preparing"]
    assert _refused(game)
