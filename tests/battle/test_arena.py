"""擂台賽（隨時挑擂；docs/superpowers/specs/2026-10-14-擂台賽-design.md）。Joy 2026-10-14 選「隨時挑擂」：報名的人留下守擂的分身，
別人隨時來挑，對的是分身，只算本季；同一天的配套（PM 轉述）改成名次制：報名排到榜尾、只能挑前三名內、贏了交換名次、不花體力
一天十次、哪裡都能挑、名次給稱號、每天發俸。規則在 tianxia/arena.py，接到 Game 的在 engine.py 的「擂台」那一段。

兩個角色開在同一個資料庫；每一個動作照伺服器的做法先從資料庫重讀自己（server._locked），做完存回去（同 test_raid）。"""
from __future__ import annotations

import random

import pytest

from tianxia import arena, atlas, bot, bot_policy, rules, shopview, social
from tianxia.characters import CharacterStore
from tianxia.engine import ARENA_YIELD, Game
from tianxia.models import MOVES
from tianxia.state import ArenaEntry

NOW = 1000.0


@pytest.fixture
def ring(content, world):
    """甲、乙兩個人都在小鎮，都學了拳腳。"""
    return _ring(content, world, ("甲", "乙"))


def _ring(content, world, names):
    content.config.auto_open_first_season = True
    content.config.arena.enabled = True
    for name in names:
        game = Game.new(content, name, rng=random.Random(0), world=world)
        game.client = None
        rules.learn_skill(game.state, content, "fist")
        game.state.player.location = "town"
        game.state.player.stamina = 100.0
        game.sync(NOW)
        CharacterStore(world.db).save(game.state)
    return content, world


def _do(content, world, name, act, now=NOW):
    state = CharacterStore(world.db).load(name)
    game = Game(content, state, random.Random(0), world)
    game.client = None
    game.sync(now)
    msgs = act(game)
    game._save_season()
    CharacterStore(world.db).save(game.state)
    return msgs, game


def _ids(game):
    return [o.id for o in game.options()]


def _join(content, world, name):
    return _do(content, world, name, lambda g: g.choose("act:arena") + g.choose("arena:join") + g.choose("arena:back"))


def _fight(content, world, name="甲", foe="乙", moves=None, now=NOW):
    """甲挑乙，一路出招打完；回傳最後一下的訊息與甲的 Game。"""
    def go(g):
        msgs = g.choose("act:arena") + g.choose(f"arena:fight:{foe}")
        i = 0
        while g.state.player.arena is not None:
            msgs = g.choose(f"arena:{(moves or MOVES)[i % len(moves or MOVES)]}")
            i += 1
        return msgs
    return _do(content, world, name, go, now)


DAY = 86400.0


def _ladder(world, *names, bouts=0):
    """直接排好一張榜（第一個是第一名），每個人 bouts 場勝績。"""
    w = world.get_season()
    for i, name in enumerate(names, 1):
        w.arena[name] = ArenaEntry(name=name, power=10, hp_cap=100, rank=i, wins=bouts, arts=["基礎拳腳"])
    world.save_season(w)
    return w


@pytest.mark.smoke
def test_the_ring_is_anywhere_and_opening_it_costs_nothing(ring):
    content, world = ring
    _, game = _do(content, world, "甲", lambda g: [])
    assert "act:arena" in _ids(game)
    msgs = game.choose("act:arena")
    assert msgs[0] == arena.UNRANKED.format(n=content.config.arena.reach)
    assert game.state.player.stamina == 100.0
    assert _ids(game) == ["arena:join", "arena:back"]
    assert atlas.travel_block(game.state, content) is not None  # 擂台邊：先返回
    game.choose("arena:back")
    game.state.player.location = "lake"  # 不是城鎮也有
    assert "act:arena" in _ids(game)
    game.state.player.busy_until = game.state.world.time + 3600  # 閉關中也有
    assert _ids(game) == ["act:break", "act:arena"]
    game.choose("act:arena")
    assert game._shop_open() == "arena" and "arena:back" in _ids(game)


def test_joining_puts_you_at_the_bottom_and_joining_again_only_refreshes_it(ring):
    content, world = ring
    msgs, game = _join(content, world, "乙")
    assert any("排在第 1 名" in m for m in msgs)
    msgs, game = _join(content, world, "甲")
    assert any("排在第 2 名" in m for m in msgs)
    entry = arena.entry_of(game.state.world, "甲")
    assert entry.power > 0 and entry.hp_cap > 0 and entry.arts and entry.rank == 2
    entry.wins = 3
    game._save_season()
    msgs, game = _join(content, world, "甲")
    assert any("換了一份守擂的分身" in m for m in msgs)
    entry = arena.entry_of(game.state.world, "甲")
    assert (entry.rank, entry.wins) == (2, 3)  # 名次與戰績照舊


def test_a_fighter_without_arts_cannot_join(ring):
    content, world = ring
    _, game = _do(content, world, "甲", lambda g: g.choose("act:arena"))
    game.state.player.member.wugong_id = None
    game.state.player.member.neigong_id = None
    assert not next(o for o in game.options() if o.id == "arena:join").enabled
    assert game._arena_join() == [arena.NO_ARTS]


def test_you_can_only_reach_the_three_ranks_above_you(ring):
    content, world = ring
    w = _ladder(world, "子", "丑", "寅", "卯", "辰")
    _, game = _do(content, world, "甲", lambda g: g.choose("act:arena"))
    assert not any(o.startswith("arena:fight:") for o in _ids(game))  # 沒報名：誰都挑不了
    game.choose("arena:join")
    assert arena.entry_of(game.state.world, "甲").rank == 6
    fights = [o for o in game.options() if o.id.startswith("arena:fight:")]
    assert [o.id for o in fights] == ["arena:fight:寅", "arena:fight:卯", "arena:fight:辰"]
    assert all(o.enabled and "第 " in o.label for o in fights)
    assert "擂台三甲" in fights[0].label and "擂台十傑" in fights[1].label
    cfg = content.config.arena
    w = game.state.world
    assert arena.challenge_problem(w, "甲", w.arena["丑"], cfg, 5) == arena.OUT_OF_REACH.format(n=cfg.reach)
    assert arena.challenge_problem(w, "辰", w.arena["甲"], cfg, 5) == arena.BEHIND
    assert arena.challenge_problem(w, "甲", w.arena["辰"], cfg, 0) == arena.SPENT.format(n=cfg.per_day)


def test_a_win_swaps_ranks_and_spares_the_body_and_stamina(ring):
    content, world = ring
    _join(content, world, "乙")
    _join(content, world, "甲")
    before = CharacterStore(world.db).load("甲")
    hp_before, wear_before = before.player.member.neili, before.player.member.injury
    rng_state = random.Random(0).getstate()

    def win(g):
        g.choose("act:arena")
        g.choose("arena:fight:乙")
        g.state.player.arena.edge = 95  # 氣勢到頂：提前大勝
        return g.choose(f"arena:{MOVES[0]}")
    msgs, game = _do(content, world, "甲", win)
    p = game.state.player
    assert p.arena is None and p.stamina == 100.0  # 不花體力
    assert game.arena_left() == content.config.arena.per_day - 1
    assert (p.member.neili, p.member.injury) == (hp_before, wear_before)  # 打完不扣回角色
    record = game.state.battles[0]
    assert record.kind == "arena" and record.opponent == "乙的分身" and record.rounds
    assert arena.SWAPPED.format(before=2, after=1) in record.changes
    w = game.state.world
    assert (arena.entry_of(w, "甲").rank, arena.entry_of(w, "乙").rank) == (1, 2)
    assert any("擂台易主" in r.text for r in w.rumors)  # 第一名換人上天下大事
    assert game.rng.getstate() == rng_state  # 不碰 Game.rng
    assert any(e.title == "擂台・乙" for e in game.state.journal)
    assert p.arena_last is not None and p.picking_arena  # 打完回到擂台那一頁、有收場卡
    # 守的人下次同步補一份戰報與一則「守擂・甲」
    _, defender = _do(content, world, "乙", lambda g: [])
    assert defender.state.battles[0].kind == "arena" and defender.state.battles[0].event == "守擂・甲"
    assert arena.SWAPPED.format(before=1, after=2) in defender.state.battles[0].changes
    assert arena.entry_of(defender.state.world, "乙").inbox == []


def test_the_challenge_notes_the_foes_name_to_keep_for_the_biography(content, world):
    """FB-9020：「上擂台挑某某」的對手是玩家，名號帶「你」或阿拉伯數字時季末備援列傳不能改它；行狀記 keep。"""
    content, world = _ring(content, world, ("甲", "你好嗎2"))
    content.config.biography.enabled = True
    _join(content, world, "你好嗎2")
    _join(content, world, "甲")
    _, game = _fight(content, world, "甲", "你好嗎2")
    (note,) = [e for e in game.state.player.annals if e.kind == "fight"]
    assert note.text.startswith("上擂台挑你好嗎2，") and note.keep == ["你好嗎2"]


def test_yielding_is_a_loss_and_ranks_stay(ring):
    content, world = ring
    _join(content, world, "乙")
    _join(content, world, "甲")

    def go(g):
        g.choose("act:arena")
        g.choose("arena:fight:乙")
        assert _ids(g) == [f"arena:{m}" for m in MOVES] + [ARENA_YIELD]
        assert atlas.travel_block(g.state, content) is not None
        return g.choose(ARENA_YIELD)
    msgs, game = _do(content, world, "甲", go)
    assert msgs[0] == arena.YIELDED
    assert game.state.battles[0].tier == "落敗"
    w = game.state.world
    assert arena.entry_of(w, "甲").losses == 1 and arena.entry_of(w, "乙").wins == 1
    assert (arena.entry_of(w, "甲").rank, arena.entry_of(w, "乙").rank) == (2, 1)
    assert arena.KEPT.format(rank=2) in game.state.battles[0].changes


def test_the_pair_cooldown_and_no_daily_protection(ring):
    content, world = ring
    cfg = content.config.arena
    _join(content, world, "乙")
    _join(content, world, "甲")
    _do(content, world, "甲", lambda g: g.choose("act:arena") + g.choose("arena:fight:乙") + g.choose(ARENA_YIELD))
    _, game = _do(content, world, "甲", lambda g: g.choose("act:arena"))
    option = next(o for o in game.options() if o.id == "arena:fight:乙")
    assert not option.enabled and "剛挑過，約 3 小時後可再挑" in option.label
    w = game.state.world
    foe = arena.entry_of(w, "乙")
    w.arena_pairs.clear()
    foe.defended = [arena.day_of(w), 99]  # 舊存檔記的被挑場數不再擋人
    assert arena.challenge_problem(w, "甲", foe, cfg, 5) is None


def test_the_cooldown_says_how_long_to_wait(ring):
    """Joy 2026-10-16「擂台打過的對手短時間不能打，但是玩家現在無法看出還有多久才能打」：鈕上、被拒那句都寫現實的倒數。"""
    content, world = ring
    cfg = content.config.arena
    _join(content, world, "乙")
    _join(content, world, "甲")
    _, game = _do(content, world, "甲", lambda g: g.choose("act:arena"))
    w = game.state.world
    foe = arena.entry_of(w, "乙")
    w.arena_pairs[arena.pair_key("甲", "乙")] = w.time - (cfg.pair_cooldown_seconds - 40 * 60)
    assert arena.challenge_problem(w, "甲", foe, cfg, 5) == "剛挑過，約 40 分鐘後可再挑"
    assert arena.challenge_problem(w, "甲", foe, cfg, 5, time_scale=2.0) == "剛挑過，約 20 分鐘後可再挑"
    w.arena_pairs[arena.pair_key("甲", "乙")] = w.time - (cfg.pair_cooldown_seconds - 135 * 60)
    assert arena.challenge_problem(w, "甲", foe, cfg, 5) == "剛挑過，約 2 小時 15 分後可再挑"
    assert game.choose("arena:fight:乙") == ["（剛挑過，約 2 小時 15 分後可再挑。）"]
    assert arena.wait_text(10) == "約 1 分鐘" and arena.wait_text(3600) == "約 1 小時"
    assert "明日 00:00" in arena.challenge_problem(w, "甲", foe, cfg, 0)
    from tianxia import shopview
    view = shopview.arena_view(game.state, content, world, 100.0, 5)
    assert view["foes"][0]["short"] == ["約 2 小時 15 分後", "可再挑"]
    spent = shopview.arena_view(game.state, content, world, 100.0, 0)
    assert spent["foes"][0]["short"][0] == "明日 00:00" and spent["purse"] == arena.SPENT_PURSE


def test_the_daily_count_resets_at_midnight(ring):
    content, world = ring
    cfg = content.config.arena
    _, game = _do(content, world, "甲", lambda g: [])
    today = game._pill_day()
    game.state.player.arena_day, game.state.player.arena_today = today, cfg.per_day
    assert game.arena_left() == 0
    game.state.player.arena_day = today - 1
    assert game.arena_left() == cfg.per_day


def test_titles_follow_the_current_rank(ring):
    content, world = ring
    _ladder(world, "子", "丑", "寅", "卯")
    w = world.get_season()
    assert [arena.title_of(w, n) for n in ("子", "丑", "寅", "卯")] == ["天下第一", "擂台三甲", "擂台三甲", "擂台十傑"]
    assert arena.title_for(11) is None and arena.title_of(w, "甲") is None
    _ladder(world, "甲")
    _, game = _do(content, world, "甲", lambda g: [])
    assert social.affiliation(game.state, content).endswith("・天下第一")
    assert arena.board(game.state.world, content.config.arena)[0]["title"] == "天下第一"


def test_wages_are_paid_by_rank_once_a_day(ring):
    content, world = ring
    cfg = content.config.arena
    _ladder(world, "甲", "乙", bouts=1)
    _, game = _do(content, world, "甲", lambda g: [])  # 第一次看到這一天：只記天、不發
    silver = game.state.player.stats.get("silver", 0)
    assert arena.entry_of(game.state.world, "甲").wages == []
    _, game = _do(content, world, "甲", lambda g: [], now=NOW + DAY)
    paid, fame = cfg.wages[0]
    assert game.state.player.stats.get("silver", 0) == silver + paid
    assert any("俸發下來了" in line for e in game.state.journal for line in e.lines)
    _, game = _do(content, world, "甲", lambda g: [], now=NOW + DAY + 60)
    assert game.state.player.stats.get("silver", 0) == silver + paid  # 一天一次
    _, other = _do(content, world, "乙", lambda g: [], now=NOW + DAY + 120)  # 換日時記好的那一筆，乙晚一點上線也領得到
    assert arena.entry_of(other.state.world, "乙").wages == []
    assert any("擂台第 2 名" in line for e in other.state.journal for line in e.lines)


def test_a_gamble_rides_the_boss_duel_box_and_tells_the_model_who_it_faces(ring):
    content, world = ring
    _join(content, world, "乙")
    _join(content, world, "甲")
    _, game = _do(content, world, "甲", lambda g: g.choose("act:arena") + g.choose("arena:fight:乙"))
    assert game.duel_free_text_prompt() == arena.PROMPT
    request = game.duel_text_request("踢沙迷他的眼")
    assert request.boss.startswith("arena:") and request.target.startswith("乙") and request.setting == arena.SETTING
    msgs = game.duel_gamble("踢沙迷他的眼", 5, ("甲一把沙揚過去，竟然奏效。", "沙被風吹回來。"), request=request)
    assert "第 1 回合" in msgs[0]
    fight = game.state.player.arena
    assert fight is None or fight.best_set


def test_a_stale_arena_rating_says_the_round_is_over(ring, monkeypatch):
    """M-05：擂台的單子是上一回合開的就回「這一回合已經結算」，不在鎖內重評、不套用。"""
    from tianxia import battle_instance, duel

    content, world = ring
    _join(content, world, "乙")
    _join(content, world, "甲")
    _, game = _do(content, world, "甲", lambda g: g.choose("act:arena") + g.choose("arena:fight:乙"))
    request = game.duel_text_request("踢沙迷他的眼")
    game.choose(f"arena:{MOVES[0]}")
    fight = game.state.player.arena
    assert fight is not None  # 一招分不出勝負
    seen = []
    monkeypatch.setattr(battle_instance, "assess_gamble", lambda *a, **k: seen.append(a) or battle_instance.GambleVerdict(40))
    rounds = fight.round
    assert game.duel_gamble("踢沙迷他的眼", 5, ("成", "敗"), request=request) == [f"（{duel.STALE}）"]
    assert seen == [] and fight.round == rounds


def test_a_long_shot_that_lands_makes_the_news(ring):
    content, world = ring
    _join(content, world, "乙")
    _join(content, world, "甲")
    _, game = _do(content, world, "甲", lambda g: g.choose("act:arena") + g.choose("arena:fight:乙"))
    fight = game.state.player.arena
    fight.best_text, fight.best_rate, fight.best_won, fight.best_set = "倒立出拳", 10, True, True
    fame = game.state.player.stats.get("fame", 0)
    game.choose(ARENA_YIELD)
    assert game.state.player.stats.get("fame", 0) == fame + content.config.arena.highlight_fame
    assert any("倒立出拳" in r.text for r in game.state.world.rumors)


def test_a_streak_makes_the_news(ring):
    content, world = ring
    cfg = content.config.arena
    _ladder(world, "乙", "甲")
    w = world.get_season()
    w.arena["甲"].streak = cfg.streak_news - 1
    world.save_season(w)

    def win(g):
        g.choose("act:arena")
        g.choose("arena:fight:乙")
        g.state.player.arena.edge = 95
        return g.choose(f"arena:{MOVES[0]}")
    _, game = _do(content, world, "甲", win)
    assert any(f"連勝 {cfg.streak_news} 場" in r.text for r in game.state.world.rumors)


def test_season_end_crowns_a_champion_and_pays_the_top_three_during_the_break(ring):
    content, world = ring
    _join(content, world, "乙")
    _join(content, world, "甲")
    _do(content, world, "甲", lambda g: g.choose("act:arena") + g.choose("arena:fight:乙") + g.choose(ARENA_YIELD))
    content.config.admins = ["管理者"]
    admin = Game.new(content, "管理者", rng=random.Random(1), world=world)
    admin.admin_end_season(now=NOW + 10)
    texts = [r.text for r in admin.state.world.chronicle]
    assert any("擂台榜" in t for t in texts) and arena.CHAMPION.format(name="乙") in texts
    assert any("本季擂台前三名" in r.text for r in admin.state.world.rumors)
    assert "歷屆擂主" in admin.chronicle_text() and "乙" in admin.chronicle_text().split("歷屆擂主")[1]
    fame = CharacterStore(world.db).load("乙").player.stats.get("fame", 0)
    _, winner = _do(content, world, "乙", lambda g: [], now=NOW + 20)
    assert winner.state.player.stats.get("fame", 0) == fame + content.config.arena.prizes[0]
    assert any("本季擂台第 1 名" in line for e in winner.state.journal for line in e.lines)
    _, again = _do(content, world, "乙", lambda g: [], now=NOW + 30)
    assert again.state.player.stats.get("fame", 0) == fame + content.config.arena.prizes[0]  # 只補一次
    assert "act:arena" not in _ids(again)  # 休季沒有擂台


def test_champions_read_every_season():
    text = arena.champions([(3, ["本季擂主：甲。"]), (2, ["別的事", "本季擂主：乙。"]), (1, [])])
    assert text.splitlines()[2:] == ["- 第 3 季：甲", "- 第 2 季：乙"]
    assert arena.champions([(1, ["別的事"])]) == ""


def test_a_bout_left_open_when_the_season_closes_is_void(ring):
    content, world = ring
    _join(content, world, "乙")
    _join(content, world, "甲")
    _do(content, world, "甲", lambda g: g.choose("act:arena") + g.choose("arena:fight:乙"))
    content.config.admins = ["管理者"]
    Game.new(content, "管理者", rng=random.Random(1), world=world).admin_end_season(now=NOW + 10)
    _, game = _do(content, world, "甲", lambda g: [], now=NOW + 20)
    assert game.state.player.arena is None
    assert any(arena.UNSETTLED in e.lines for e in game.state.journal)


def test_the_arena_page_shows_rank_reach_and_the_board(ring):
    content, world = ring
    _ladder(world, "子", "丑", "寅", "卯")
    _, game = _do(content, world, "甲", lambda g: g.choose("act:arena"))
    view = game.shop_view()
    assert view["shop"] == "arena" and not view["me"]["joined"] and view["foes"] == []
    assert view["purse"] == f"今天還能挑 {content.config.arena.per_day} 次"
    game.choose("arena:join")
    view = game.shop_view()
    assert view["me"]["rank"] == 5 and view["me"]["title"] == "擂台十傑"
    assert [f["name"] for f in view["foes"]] == ["丑", "寅", "卯"]
    assert [r["name"] for r in view["board"]][:1] == ["子"] and any(r["me"] for r in view["board"])
    assert view["fight"] is None and view["result"] is None


def test_bots_join_then_challenge_and_read_the_tell(ring):
    content, world = ring
    _join(content, world, "乙")
    _, game = _do(content, world, "甲", lambda g: [])
    rng = random.Random(0)
    bot_policy._arena(game, rng)
    assert arena.entry_of(game.state.world, "甲") is not None and not game.state.player.picking_arena
    bot_policy.ARENA_CHANCE, old = 1.0, bot_policy.ARENA_CHANCE
    try:
        bot_policy._arena(game, rng)
    finally:
        bot_policy.ARENA_CHANCE = old
    fight = game.state.player.arena
    assert fight is not None and fight.foe.name == "乙"
    move = bot_policy.duel_move(game, random.Random(0), fight)
    assert move in MOVES


def test_season_bots_never_open_the_ring_or_yield(ring):
    content, world = ring
    _, game = _do(content, world, "甲", lambda g: [])
    assert "act:arena" in _ids(game)
    picks = {bot.pick(game, game.options(), random.Random(i)) for i in range(40)}
    assert "act:arena" not in picks
    _join(content, world, "乙")
    _join(content, world, "甲")
    _, game = _do(content, world, "甲", lambda g: g.choose("act:arena") + g.choose("arena:fight:乙"))
    picks = {bot.pick(game, game.options(), random.Random(i)) for i in range(40)}
    assert ARENA_YIELD not in picks and picks <= {f"arena:{m}" for m in MOVES}


def test_the_ring_board_is_one_of_the_season_boards(ring):
    from tianxia import leaderboard
    content, world = ring
    _ladder(world, "子", "丑", bouts=1)
    board = leaderboard.compute_boards(content, world)
    assert [row[0] for row in board["擂台"]] == ["子", "丑"]
    view = {b["id"]: b for b in leaderboard.view(board, me="丑")}
    rows = view["擂台"]["rows"]
    assert [r["rank"] for r in rows] == [1, 2] and rows[0]["text"].startswith("天下第一") and rows[1]["you"]
    content.config.arena.enabled = False
    assert leaderboard.compute_boards(content, world)["擂台"] == []


def test_roll_day_never_walks_the_day_backwards():
    """2026-10-14 線上：擂台的俸無限發放。

    「今天」是每個 Game 各算各的（Game._pill_day 讀 pill_now＝now＋advanced_real，而 advanced_real 只有管理者的
    「時間快轉」會加，加完留在那個 Game 物件上直到伺服器重開）。快轉過的那個人認為今天是第 20741 天、其他人還是
    20740，舊的寫法無條件把 world.arena_day 設成自己的今天，兩邊輪流同步就讓它在兩個日子之間來回跳，每跳回來一次
    就再記一輪俸：線上一個人累積到 144 筆（4320 銀、144 名望），九個人的江湖紀錄被俸洗滿。"""
    from tianxia.models import ArenaTuning
    from tianxia.world_state import WorldState

    cfg = ArenaTuning()
    world = WorldState()
    world.arena = {"jia": ArenaEntry(name="甲", power=300.0, hp_cap=1000.0, rank=1, wins=3)}
    world.arena_day = 20740

    assert arena.roll_day(world, cfg, 20741) is True  # 快轉過的那個人：記一筆
    assert len(world.arena["jia"].wages) == 1
    assert arena.roll_day(world, cfg, 20740) is False  # 一般玩家：不能把日子推回去
    assert world.arena_day == 20741
    for _ in range(5):  # 兩邊再怎麼輪流同步，也只有那一筆
        arena.roll_day(world, cfg, 20741)
        arena.roll_day(world, cfg, 20740)
    assert len(world.arena["jia"].wages) == 1


def test_roll_day_records_one_wage_per_day():
    """同一天只記一筆：就算日子真的往前走了，也不會重複記。"""
    from tianxia.models import ArenaTuning
    from tianxia.world_state import WorldState

    cfg = ArenaTuning()
    world = WorldState()
    world.arena = {"jia": ArenaEntry(name="甲", power=300.0, hp_cap=1000.0, rank=1, wins=3)}
    world.arena_day = 20740
    arena.roll_day(world, cfg, 20741)
    world.arena_day = 20740  # 假裝舊存檔留下來的壞資料
    arena.roll_day(world, cfg, 20741)
    assert [d for d, _ in world.arena["jia"].wages] == [20741]


def test_the_finishing_blow_reports_whole_numbers():
    """池子是小數：見底那一下扣的是剩的那一截，回合那一句照 :+d 寫，得是整數（2026-10-16 假人擂台每次見底都丟 ValueError）。"""
    from tianxia.state import ArenaSide
    side = ArenaSide(name="甲", power=100.0, hp=37.4, hp_cap=400.0)
    lost = arena._pool(side, 120)
    assert isinstance(lost, int) and f"{-lost:+d}" == "-37" and side.hp == 0
    side = ArenaSide(name="乙", power=100.0, hp=399.5, hp_cap=400.0)
    assert isinstance(arena._pool(side, -30), int) and side.hp == 400.0
