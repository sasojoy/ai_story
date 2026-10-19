"""找素材分支（第 32 項；docs/superpowers/plans/2026-10-18-找素材分支.md）：按「找素材」照地點地形展開幾條路（挖礦、狩獵、採集、深入），
每一條都一定給素材、差在給哪一種屬性；「深入」偶爾另外悟到這一帶的意境；最後一顆「自己說…」寫 20 字的找法，模型評成算、引擎擲骰。
開關 Config.gather_branches 在測試內容關著，這裡用正式內容（週末設定，一類一顆也開著）。"""
from __future__ import annotations

import random

import pytest
from conftest import real_content

from tianxia import bounties, content as content_mod, explore_modes, insights, materials, rules
from tianxia.content import ContentError
from tianxia.engine import Game
from tianxia.models import GatherBranch
from tianxia.sqlite_world import open_world

pytestmark = pytest.mark.slow  # 建 Game、載正式內容

HOUR = 3600
MON = 1792339200  # 2026-10-19 週一 00:00（台灣）
NOW = MON + 10 * HOUR
COST = 6


def _game(at="deep_mountain", stamina=250.0, profile="weekend", branches=True):
    c = real_content(profile)
    c.config.train_event_chance = 0.0
    c.config.gather_branches.enabled = branches
    store = open_world()
    store.seed_first_season(c)
    store.open_season(c, NOW)
    game = Game.new(c, "沈浪", rng=random.Random(0), world=store)
    game.client = None
    game.sync(NOW)
    p = game.state.player
    p.location, p.stamina = at, stamina
    p.tutorial_step = len(c.tutorial.steps)
    return game


def _ids(game):
    return {o.id: o for o in game.options()}


def _attrs(game, before):
    """這一下多出來的素材的屬性。"""
    mats = game.content.materials
    now = game.state.player.materials
    return {mats[m].attribute for m, n in now.items() if n > before.get(m, 0)}


# ── Task 1：內容與設定 ──


def _check(c):
    errors = []
    content_mod.check_gather_branches(c, lambda ok, msg: ok or errors.append(msg))
    return errors


def test_the_real_content_loads_and_the_test_content_keeps_it_off():
    c = real_content("weekend")
    assert set(c.gather_branches) == {"mine", "hunt", "forage", "deep"}
    assert c.config.gather_branches.enabled
    from conftest import FIXTURE, cached_content  # noqa: PLC0415

    assert not cached_content(FIXTURE).config.gather_branches.enabled
    assert _check(c) == []


def test_bad_branches_are_refused():
    c = real_content("weekend")
    good = dict(c.gather_branches)
    c.gather_branches = {**good, "x": GatherBranch(id="x", name="亂找", tags=["山林"], attributes=["金"], line="你在{place}亂找。")}
    assert any("屬性" in e for e in _check(c))
    c.gather_branches = {**good, "x": GatherBranch(id="x", name="再深入", tags=["山林"], line="你往{place}更深處走。", deep=True)}
    assert any("deep" in e for e in _check(c))
    c.gather_branches = {**good, "say": GatherBranch(id="say", name="說", tags=["山林"], attributes=["剛"], line="你在{place}。")}
    assert any("say" in e for e in _check(c))
    c.gather_branches = {**good, "x": GatherBranch(id="x", name="潛水", tags=["海底"], attributes=["柔"], line="你在{place}。")}
    assert any("海底" in e for e in _check(c))
    c.gather_branches = {**good, "x": GatherBranch(id="x", name="空", tags=["山林"], line="你在{place}。")}
    assert any("attributes" in e for e in _check(c))
    c.gather_branches = {**good, "x": GatherBranch(id="x", name="壞句", tags=["山林"], attributes=["剛"], line="你在{where}。")}
    assert any("{place}" in e for e in _check(c))
    c.gather_branches = good


def test_a_duplicate_id_is_refused_at_load():
    with pytest.raises(ContentError, match="重複"):
        content_mod._index(GatherBranch, [
            {"id": "a", "name": "甲", "tags": ["山林"], "attributes": ["剛"], "line": "{place}"},
            {"id": "a", "name": "乙", "tags": ["山林"], "attributes": ["柔"], "line": "{place}"},
        ])


def test_which_branches_show_where():
    c = real_content("weekend")
    here = lambda loc: [b.id for b in explore_modes.branches_here(c, c.locations[loc])]  # noqa: E731
    assert here("deep_mountain") == ["mine", "hunt", "deep"]
    assert here("songshan_foot") == ["mine", "hunt"]  # 危險度 1：沒有深入
    assert here("yingchuan_wilds") == ["hunt", "forage"]
    assert here("yingshui") == ["forage"]  # 只有一條：沒有分支層
    assert here("yingchuan") == [] and here("haozu_fort") == []  # 城鎮、塢堡


# ── Task 2：純規則 ──


def _old_gather_finds(c, loc, rng, sure=False):
    """改之前的 gather_finds（照抄）：attributes=None 要跟它一模一樣。"""
    cfg, econ = c.config.explore_modes, c.config.economy
    kinds = {c.materials[m].attribute for m in loc.materials if m in c.materials}

    def one(tier):
        pool = [m for m in materials.by_tier(c, tier) if m.attribute in kinds] or materials.by_tier(c, tier)
        return rng.choice(pool).id if pool else None

    if explore_modes.is_town(c, loc):
        found = [one(1)] if sure or rng.random() < cfg.town_chance else []
    else:
        found = [one(1)] if sure or not econ.gather_cut or rng.random() < econ.gather_first_chance else []
        if rng.random() < cfg.second_tier.get(loc.danger, 0.0):
            found.append(one(2))
    return [mid for mid in found if mid is not None]


def test_no_attributes_finds_exactly_what_it_found_before():
    c = real_content("weekend")
    for loc_id in ("deep_mountain", "yingchuan", "jade_cave", "yingshui"):
        loc = c.locations[loc_id]
        for sure in (False, True):
            for seed in range(60):
                assert explore_modes.gather_finds(c, loc, random.Random(seed), sure=sure) == \
                    _old_gather_finds(c, loc, random.Random(seed), sure=sure)


def test_each_branch_only_finds_its_own_attributes():
    c = real_content("weekend")
    loc = c.locations["deep_mountain"]
    for branch in explore_modes.branches_here(c, loc):
        want = set(explore_modes.branch_attributes(c, loc, branch))
        seen = set()
        for seed in range(200):
            found = explore_modes.gather_finds(c, loc, random.Random(seed), sure=True,
                                               attributes=explore_modes.branch_attributes(c, loc, branch))
            assert found  # 一定給
            seen |= {c.materials[m].attribute for m in found}
            assert all(c.materials[m].tier <= 2 for m in found)
        assert seen == want, branch.id
    assert explore_modes.branch_attributes(c, loc, c.gather_branches["deep"]) == ["慢", "柔"]  # 深入照地點


def test_deep_insight_only_where_something_can_be_sensed(monkeypatch):
    c = real_content("weekend")
    monkeypatch.setattr(c.config.gather_branches, "deep_insight_chance", 1.0)
    loc = c.locations["deep_mountain"]
    got = {explore_modes.deep_insight(c, loc, random.Random(seed)) for seed in range(40)}
    assert got <= set(insights.explore_gives(loc, c)) and None not in got
    monkeypatch.setattr(insights, "explore_gives", lambda loc, content: [])
    assert explore_modes.deep_insight(c, loc, random.Random(0)) is None


def test_say_choices_are_the_union_of_the_branches_here():
    c = real_content("weekend")
    assert explore_modes.say_choices(c, c.locations["deep_mountain"]) == ["剛", "慢", "快", "柔"]
    assert explore_modes.say_choices(c, c.locations["yingchuan_wilds"]) == ["快", "柔", "慢"]


# ── Task 3：接進 Game ──


def test_gather_unfolds_into_branches_where_there_are_two_or_more():
    game = _game("deep_mountain")
    ids = _ids(game)
    entry = ids["explore:gather"]
    assert entry.enabled and entry.label == "找素材"  # 入口不寫體力
    assert ids["explore:gather:mine"].label == f"挖礦（體力 {COST}・剛、慢）"
    assert ids["explore:gather:hunt"].label == f"狩獵（體力 {COST}・快、柔）"
    assert ids["explore:gather:deep"].label == f"深入（體力 {COST}・慢、柔）"
    assert ids[explore_modes.SAY_ID].label.startswith(f"自己說…（體力 {COST}")
    order = [o.id for o in game.options() if o.id.startswith("explore:")]
    assert order[:5] == ["explore:gather", "explore:gather:mine", "explore:gather:hunt", "explore:gather:deep", explore_modes.SAY_ID]
    assert {"explore:seek", "explore:sense", "explore:practice"} <= set(order)


def test_pressing_gather_itself_only_unfolds():
    game = _game("deep_mountain")
    p = game.state.player
    journal, mats, seq = len(game.state.journal), dict(p.materials), p.explore_seq
    msgs = game.choose("explore:gather")
    assert explore_modes.GATHER_PICK in msgs
    assert p.stamina == 250.0 and p.materials == mats and p.explore_seq == seq
    assert len(game.state.journal) == journal  # 不寫紀錄


def test_a_branch_gives_its_own_materials_and_costs_stamina(monkeypatch):
    scouted = []
    real = bounties.on_explore
    monkeypatch.setattr(bounties, "on_explore", lambda *a, **k: scouted.append(a[3]) or real(*a, **k))
    game = _game("deep_mountain")
    p = game.state.player
    for _ in range(25):
        p.stamina = 250.0
        before = dict(p.materials)
        game.choose("explore:gather:mine")
        assert p.stamina == 250.0 - COST
        got = _attrs(game, before)
        assert got and got <= {"剛", "慢"}
        assert not game.state.battles and game.state.pending_event is None
    assert scouted == ["deep_mountain"] * 25  # 算打探懸賞的交差
    entry = game.state.journal[0]
    assert entry.title == "挖礦・嵩山深處"
    assert entry.lines[0] == game.content.gather_branches["mine"].line.format(place="嵩山深處")


def test_hunting_gives_quick_and_soft():
    game = _game("yingchuan_wilds")
    p = game.state.player
    seen = set()
    for _ in range(30):
        p.stamina = 250.0
        before = dict(p.materials)
        game.choose("explore:gather:hunt")
        seen |= _attrs(game, before)
    assert seen == {"快", "柔"}


def test_deep_sometimes_senses_and_known_ones_turn_into_xinde(monkeypatch):
    game = _game("deep_mountain")
    monkeypatch.setattr(game.content.config.gather_branches, "deep_insight_chance", 1.0)
    p = game.state.player
    p.insights = [i for i in p.insights if i not in insights.explore_gives(game.content.locations["deep_mountain"], game.content)]
    msgs = game.choose("explore:gather:deep")
    assert explore_modes.DEEP_LINE in msgs
    learned = [i for i in insights.explore_gives(game.content.locations["deep_mountain"], game.content) if i in p.insights]
    assert len(learned) == 1
    p.insights += [i for i in insights.explore_gives(game.content.locations["deep_mountain"], game.content) if i not in p.insights]
    xinde = p.stats.get("xinde", 0)
    p.stamina = 250.0
    game.choose("explore:gather:deep")
    assert p.stats.get("xinde", 0) > xinde  # 會了的化心得


def test_deep_does_not_sense_with_the_default_chance_most_of_the_time():
    game = _game("deep_mountain")
    p = game.state.player
    hits = 0
    for _ in range(60):
        p.stamina = 250.0
        hits += explore_modes.DEEP_LINE in game.choose("explore:gather:deep")
    assert hits <= 20  # 10%【預設】：附帶的小驚喜，不是主菜


def test_one_branch_or_a_town_keeps_plain_gathering():
    for at in ("yingshui", "yingchuan"):
        game = _game(at)
        ids = _ids(game)
        assert ids["explore:gather"].label == f"找素材（體力 {COST}）"
        assert not any(i.startswith("explore:gather:") for i in ids)
        p = game.state.player
        before = sum(p.materials.values())
        game.choose("explore:gather")
        assert sum(p.materials.values()) > before and p.stamina == 250.0 - COST


def test_switch_off_keeps_the_menu_and_the_finds():
    on, off = _game("deep_mountain"), _game("deep_mountain", branches=False)
    ids = _ids(off)
    assert ids["explore:gather"].label == f"找素材（體力 {COST}）"
    assert not any(i.startswith("explore:gather:") for i in ids)
    assert [o.id for o in off.options() if o.id.startswith("explore:")] == \
        ["explore:gather", "explore:seek", "explore:sense", "explore:practice"]
    p = off.state.player
    before = dict(p.materials)
    off.choose("explore:gather")
    roll = explore_modes.rng_for(off.world.get_season_number(), p.name, p.explore_seq, "找素材")
    want = explore_modes.gather_finds(off.content, off.content.locations["deep_mountain"], roll, sure=True)
    got = {m: n - before.get(m, 0) for m, n in p.materials.items() if n > before.get(m, 0)}
    assert sorted(m for m, n in got.items() for _ in range(n)) == sorted(want)
    assert off.state.journal[0].title == "找素材・嵩山深處"
    assert on  # 開著的那一份只是對照：同一個地點有分支


def test_an_unstamped_season_has_no_branches():
    game = _game("deep_mountain")
    game.state.world.precise_actions = False  # 一類一顆沒蓋章的季：找素材還在撞仗，不接分支
    assert not any(i.startswith("explore:gather:") for i in _ids(game))


def test_a_tired_player_sees_the_branches_greyed():
    game = _game("deep_mountain", stamina=3.0)
    ids = _ids(game)
    assert not ids["explore:gather"].enabled
    assert not ids["explore:gather:mine"].enabled and not ids[explore_modes.SAY_ID].enabled


def test_the_howto_mentions_the_roads_only_when_on():
    from tianxia import howto

    game = _game("deep_mountain")
    lines = howto.explore_lines(game.content, game.state.world)
    assert any("挖礦多剛、慢" in line and "深入" in line and "自己說" in line for line in lines)
    off = _game("deep_mountain", branches=False)
    assert not any("挖礦" in line for line in howto.explore_lines(off.content, off.state.world))


# ── Task 4：「自己說」三段式 ──


def test_saying_alone_only_asks_for_a_line():
    game = _game("deep_mountain")
    p = game.state.player
    msgs = game.choose(explore_modes.SAY_ID)
    assert p.stamina == 250.0 and "20" in msgs[0]


def test_the_request_carries_place_turn_line_and_choices():
    game = _game("deep_mountain")
    req = game.gather_text_request("  沿著獸徑找鐵礦 ")
    assert req.location == "deep_mountain" and req.seq == game.state.player.explore_seq
    assert req.text == "沿著獸徑找鐵礦" and req.choices == ["剛", "慢", "快", "柔"]
    assert isinstance(game.gather_text_request(""), list)
    assert isinstance(game.gather_text_request("字" * 21), list)


def test_no_say_where_there_is_no_branch_layer_or_no_stamina():
    assert isinstance(_game("yingshui").gather_text_request("找石頭"), list)
    assert isinstance(_game("deep_mountain", stamina=3.0).gather_text_request("找石頭"), list)


def _sure(monkeypatch, value):
    """「自己說」那一擲（用途「自己說」）固定成 value。"""
    real = explore_modes.rng_for

    def fake(season, name, serial, what):
        rng = real(season, name, serial, what)
        if what == explore_modes.SAY_ROLL:
            rng.random = lambda: value
        return rng

    monkeypatch.setattr(explore_modes, "rng_for", fake)


def test_a_good_line_gives_one_more_of_that_attribute(monkeypatch):
    _sure(monkeypatch, 0.0)
    game = _game("deep_mountain")
    p = game.state.player
    req = game.gather_text_request("敲開山岩找鐵砂")
    before = dict(p.materials)
    msgs = game.gather_say(req, 70, "剛")
    assert p.stamina == 250.0 - COST and p.explore_seq == req.seq + 1
    got = {m: n - before.get(m, 0) for m, n in p.materials.items() if n > before.get(m, 0)}
    tier1 = sum(n for m, n in got.items() if game.content.materials[m].tier == 1)
    assert tier1 == 2 and {game.content.materials[m].attribute for m in got} == {"剛"}
    rate = rules.stat_rate(70, "wis", game.state, game.content, game.world)
    assert f"你：「敲開山岩找鐵砂」（{rules.rate_words(rate)}）" in msgs and "（成功）" in msgs
    assert game.state.journal[0].title == "找素材・嵩山深處"


def test_a_miss_still_gives_the_sure_share(monkeypatch):
    _sure(monkeypatch, 0.999)
    game = _game("deep_mountain")
    p = game.state.player
    req = game.gather_text_request("隨便看看")
    before = dict(p.materials)
    msgs = game.gather_say(req, 5, "柔")
    got = {m: n - before.get(m, 0) for m, n in p.materials.items() if n > before.get(m, 0)}
    assert sum(n for m, n in got.items() if game.content.materials[m].tier == 1) == 1
    assert {game.content.materials[m].attribute for m in got} == {"柔"} and "（失敗）" in msgs


def test_an_attribute_off_the_list_falls_back_to_the_first_branch(monkeypatch):
    _sure(monkeypatch, 0.999)
    game = _game("yingchuan_wilds")
    p = game.state.player
    req = game.gather_text_request("挖礦")
    before = dict(p.materials)
    game.gather_say(req, 50, "金")
    assert _attrs(game, before) == {"快"}  # 狩獵是這裡的第一條


def test_the_rate_is_clamped_with_wisdom():
    game = _game("deep_mountain")
    s, c, w = game.state, game.content, game.world
    s.player.stats["wis"] = 5
    assert rules.stat_rate(100, "wis", s, c, w) == 85 and rules.stat_rate(0, "wis", s, c, w) == 5
    assert rules.stat_rate(40, "wis", s, c, w) == 40


def test_the_c_step_rechecks_place_turn_and_line():
    game = _game("deep_mountain")
    p = game.state.player
    req = game.gather_text_request("找礦")
    game.choose("explore:gather:mine")  # 中間做了別的事：explore_seq 變了
    stamina = p.stamina
    msgs = game.gather_say(req, 80, "剛")
    assert p.stamina == stamina and explore_modes.SAY_GONE in " ".join(msgs)
    req = game.gather_text_request("找礦")
    p.location = "beimang_hill"
    assert explore_modes.SAY_GONE in " ".join(game.gather_say(req, 80, "剛"))
    p.location = "deep_mountain"
    req = game.gather_text_request("找礦")
    other = req.model_copy(update={"location": "beimang_hill"})
    assert explore_modes.SAY_GONE in " ".join(game.gather_say(other, 80, "剛")) and p.stamina == stamina


def test_without_a_rate_it_scores_in_the_lock_and_falls_back_to_forty(monkeypatch):
    from tianxia import gather_llm

    _sure(monkeypatch, 0.999)
    game = _game("deep_mountain")
    seen = []
    monkeypatch.setattr(gather_llm, "score", lambda client, req: seen.append(client) or (gather_llm.DEFAULT_RATE, None))
    req = game.gather_text_request("找礦")
    msgs = game.gather_say(req)
    assert seen == [None]  # 沒有 client：鎖內的短逾時複本也是 None
    rate = rules.stat_rate(gather_llm.DEFAULT_RATE, "wis", game.state, game.content, game.world)
    assert f"（{rules.rate_words(rate)}）" in msgs[0] or any(rules.rate_words(rate) in m for m in msgs)


def test_say_switch_off_hides_the_button():
    game = _game("deep_mountain")
    game.content.config.gather_branches.say_enabled = False
    try:
        ids = _ids(game)
        assert explore_modes.SAY_ID not in ids and "explore:gather:mine" in ids
        assert isinstance(game.gather_text_request("找礦"), list)
    finally:
        game.content.config.gather_branches.say_enabled = True


# ── Task 6：假人與整季機器人 ──


def _score(game, option_id):
    from tianxia import bot_policy
    from tianxia.engine import Option
    from tianxia.state import BotProfile

    profile = BotProfile(personality="普通", seed=1, faction=game.state.player.faction, season_number=1)
    return bot_policy.score(game, Option(id=option_id, label=""), profile)


def test_server_bots_pick_the_branch_for_what_they_lack():
    """只有一條分支打分（分數跟沒有分支層時的找素材一樣），缺料時是給得出缺的那種屬性的那一條；不缺時照 explore_seq 輪。"""
    from tianxia import bot_policy

    game = _game("deep_mountain")
    c, p = game.content, game.state.player
    loc = c.locations[p.location]
    branches = {explore_modes.branch_option(b.id): b for b in explore_modes.layered(c, game.state.world, loc)}
    assert len(branches) == 3
    p.materials = {m.id: 1 for m in c.materials.values() if m.tier == 1 and m.attribute != "剛"}  # 缺剛、總數也不夠
    assert _score(game, "explore:gather") is None  # 入口按了不做事
    assert _score(game, explore_modes.SAY_ID) is None  # 不寫自由文字
    for seq in range(4):
        p.explore_seq = seq
        scores = {oid: _score(game, oid) for oid in branches}
        scored = [oid for oid, value in scores.items() if value is not None]
        assert len(scored) == 1
        assert scores[scored[0]] == pytest.approx(bot_policy.PRECISE_GATHER_SCORE + bot_policy.NEED_MATERIAL_SCORE)
        assert "剛" in explore_modes.branch_attributes(c, loc, branches[scored[0]])
    p.materials = {m.id: 5 for m in c.materials.values() if m.tier == 1}  # 不缺：幾條輪著走
    seen = set()
    for seq in range(len(branches)):
        p.explore_seq = seq
        scored = {oid: value for oid in branches if (value := _score(game, oid)) is not None}
        assert len(scored) == 1 and list(scored.values()) == [pytest.approx(bot_policy.PRECISE_GATHER_SCORE)]
        seen |= set(scored)
    assert seen == set(branches)


def test_the_season_bot_skips_the_entry_and_the_say():
    from tianxia import bot

    game = _game("deep_mountain")
    options = [o for o in game.options(odds=False) if o.enabled]
    picks = {bot.pick(game, options, random.Random(seed)) for seed in range(80)}
    assert "explore:gather" not in picks and explore_modes.SAY_ID not in picks
    # 分支只留一條（照 explore_seq 輪）：隨機挑時找素材的份量跟沒有分支層時一樣是一顆
    branched = {p for p in picks if p.startswith("explore:gather:")}
    assert len(branched) == 1
    game.state.player.explore_seq += 1
    again = {bot.pick(game, options, random.Random(seed)) for seed in range(80)}
    assert len({p for p in again if p.startswith("explore:gather:")} - branched) == 1
    ids = [o.id for o in options]
    assert bot.explore_choice(ids) == "explore:gather:mine"  # 第一條分支
    assert bot.explore_choice(set(ids)) == "explore:gather:deep"  # set 照字排：結果固定
    assert bot.explore_choice({"explore:gather", "explore:seek"}) == "explore:gather"  # 沒有分支照舊


# ── gather_llm：模型回的東西 ──


class _Client:
    def __init__(self, reply=None, boom=False):
        self.reply, self.boom, self.sent = reply, boom, []

    def chat_structured(self, messages, schema, **kwargs):
        self.sent.append((messages, kwargs))
        if self.boom:
            raise RuntimeError("壞了")
        return schema(**self.reply)


def test_gather_llm_clamps_and_checks_the_attribute():
    from tianxia import gather_llm
    from tianxia.explore_modes import GatherTextRequest

    req = GatherTextRequest(location="deep_mountain", place="嵩山深處", tags=["山林"], seq=3, text="找礦", choices=["剛", "柔"])
    assert gather_llm.score(None, req) == (gather_llm.DEFAULT_RATE, None)
    assert gather_llm.score(_Client(boom=True), req) == (gather_llm.DEFAULT_RATE, None)
    assert gather_llm.score(_Client({"rate": 150, "attribute": "刚"}), req) == (100, "剛")  # 簡體轉繁體再比
    assert gather_llm.score(_Client({"rate": -3, "attribute": "金"}), req) == (0, None)
    client = _Client({"rate": 60, "attribute": "柔"})
    assert gather_llm.score(client, req) == (60, "柔")
    messages, kwargs = client.sent[0]
    assert "找礦" in messages[-1]["content"] and "嵩山深處" in messages[-1]["content"]
    assert kwargs["num_predict"] == gather_llm.SCORE_PREDICT


# ── 伺服器：鎖外評分 ──


def test_gather_text_scores_outside_the_lock(monkeypatch):
    import time

    import server
    from tianxia import gather_llm
    from tianxia.characters import open_characters

    c = server.CONTENT
    game = Game.new(c, "測試")
    game.world.open_season(c, time.time())
    game.state.player.tutorial_step = len(c.tutorial.steps)
    game.client = type("Fake", (), {})()
    game.sync(time.time())
    p = game.state.player
    p.location, p.stamina = "deep_mountain", 250.0
    open_characters().save(game.state)
    seen = []

    def score(client, req):
        seen.append((open_world().db.writing(), req.text, req.choices))
        return 90, "剛"

    monkeypatch.setattr(gather_llm, "score", score)
    before = dict(p.materials)
    msgs = server.gather_text(game, "敲開山岩找鐵砂")
    assert seen == [(False, "敲開山岩找鐵砂", ["剛", "慢", "快", "柔"])]
    assert any("敲開山岩找鐵砂" in m for m in msgs)
    assert _attrs(game, before) == {"剛"} and game.state.player.stamina <= 250.0 - COST + 1
    assert server.gather_text(game, "") == [explore_modes.SAY_BAD]
