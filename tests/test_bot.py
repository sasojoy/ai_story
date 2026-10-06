import random

from tianxia import bot, fusion, library
from tianxia.bot import pick, play_season, spend_xinde, wants_heal
from tianxia.engine import Game
from tianxia.martial_arts import generate_from_name
from tianxia.models import (
    BattleAct, BattleDef, BattleFaction, BattleOption, BattleOutcome,
)
from tianxia.sqlite_world import open_world


def test_wants_heal_only_with_internal_injury(game):
    """療傷照內傷計價：氣血低但沒有內傷時會自己回，不用去療傷（不然只會一直寫「氣血無恙」）。"""
    member = game.state.player.member
    assert not wants_heal(game)
    member.neili = 1.0
    assert not wants_heal(game)
    member.injury = 10.0
    assert wants_heal(game)


def test_spend_xinde_practices_each_worn_art_one_level(content):
    content.config.starter_skills = ["basic_breath", "basic_fist"]
    game = Game.new(content, "新人", rng=random.Random(0))
    rng = random.Random(0)
    member = game.state.player.member
    assert (member.neigong_level, member.wugong_level) == (1, 1)
    game.state.player.stats["xinde"] = 100  # 練成要花心得
    spend_xinde(game, rng)
    assert (member.neigong_level, member.wugong_level) == (2, 2)
    spend_xinde(game, rng)
    assert (member.neigong_level, member.wugong_level) == (3, 3)
    assert game.state.player.stats["xinde"] == 100 - 2 * (1 + 2)  # 兩門各花 1、再各花 2


def test_spend_xinde_only_practises_what_it_can_afford(content):
    content.config.starter_skills = ["basic_breath", "basic_fist"]
    game = Game.new(content, "新人", rng=random.Random(0))
    member = game.state.player.member
    member.neigong_level, member.wugong_level = 3, 5  # 下一成要 3、5 點
    game.state.player.stats["xinde"] = 4
    spend_xinde(game, random.Random(0))
    assert (member.neigong_level, member.wugong_level) == (4, 5)  # 武學付不起：留著，不去撞「心得不足」
    assert game.state.player.stats["xinde"] == 1
    spend_xinde(game, random.Random(0))
    assert (member.neigong_level, member.wugong_level) == (4, 5)  # 剩 1 點，兩門都付不起


def test_spend_xinde_leaves_a_maxed_art_alone(content):
    content.config.starter_skills = ["basic_breath", "basic_fist"]
    game = Game.new(content, "新人", rng=random.Random(0))
    game.state.player.member.wugong_level = 10
    game.state.player.stats["xinde"] = 100
    spend_xinde(game, random.Random(0))
    assert game.state.player.member.wugong_level == 10
    assert game.state.player.stats["xinde"] == 99  # 只有內功練了一成（第 1 成升第 2 成花 1 點）


def test_spend_xinde_leaves_an_empty_slot_empty(game):
    """沒有開局送的功夫時（fixture 的設定）也不會去自創：空著的欄位就是空著。"""
    spend_xinde(game, random.Random(0))
    member = game.state.player.member
    assert member.neigong_id is None and member.wugong_id is None


def test_spend_xinde_heals_first_when_neili_is_low(game):
    game.state.player.member.neili = 10.0
    game.state.player.member.injury = 40.0  # 有內傷才有東西可以療（療傷按內傷計價）
    game.state.player.stats["silver"] = 999
    spend_xinde(game, random.Random(0))
    assert game.state.player.member.injury == 0.0 and game.state.player.member.neili is None


class Fixed(random.Random):
    """random() 永遠回傳固定值（同 conftest.FixedRandom）：讓機器人「偶爾合併」那個機會必中或必不中。"""

    def __init__(self, value):
        super().__init__(0)
        # random() 不會回 1.0 以上；rng.choice 又靠 random() < 1 才跳得出迴圈：Fixed(1.0) 以上會讓它永遠轉下去。
        # 常數被改到逼近 1（例如 BLEND_SHARE + 0.01 越過 1.0）時要讓測試失敗，不是卡住整個測試套件
        if not 0.0 <= value < 1.0:
            raise ValueError(f"Fixed 的值要在 [0, 1) 裡：{value}")
        self.value = value

    def random(self):
        return self.value


def armed(content, world, **stats):
    """一個有一門武學、一個意境、心得與體力都夠的機器人。"""
    game = Game.new(content, "機器人", rng=random.Random(0), world=world)
    p = game.state.player
    p.member.wugong_id = "basic_fist"
    p.insights = ["feng"]
    p.stats["xinde"] = 100
    p.stamina = 150
    for key, value in stats.items():
        p.stats[key] = value
    return game


def _two_arts(world, *, plain_top=30.0, rich_top=29.0, rich_traits=("剛", "剛", "剛"), rich_special=None, quality="下品"):
    """素拳（只有自己屬性的一個功效）與繁拳（多幾層功效、威力少一點）：都登記到全服。"""
    plain = generate_from_name("素拳", "武學", "素拳", attribute="剛").model_copy(
        update={"origin": "fused", "quality": quality, "base_power": 10.0, "top_power": plain_top, "traits": ["剛"]},
    )
    rich = plain.model_copy(update={
        "id": "繁拳", "name": "繁拳", "top_power": rich_top, "traits": list(rich_traits), "special": rich_special,
    })
    for art in (plain, rich):
        world.claim_skill_name(art)
    return plain, rich


def _wear_and_switch(game, plain, rich, quality="下品"):
    p = game.state.player
    p.member.wugong_id, p.arts = plain.id, [rich.id]
    for art_id in (plain.id, rich.id):
        p.art_quality[art_id] = quality
    bot._switch_to_the_strongest(game)
    return p.member.wugong_id


def test_the_bot_weighs_traits_when_it_picks_what_to_wear(content, world):
    """設計 13.7：機器人選身上那門要看功效，不然整季模擬量不出功效的價值。威力差一點、功效多兩層的那一門贏。"""
    game = armed(content, world)
    plain, rich = _two_arts(world)
    assert _wear_and_switch(game, plain, rich) == rich.id


def test_a_much_stronger_art_still_beats_a_trait_rich_one(content, world):
    """功效只是加成（每層 5%）：威力差很多的那一門照樣贏。"""
    game = armed(content, world)
    plain, rich = _two_arts(world, plain_top=60.0, rich_top=29.0)
    assert _wear_and_switch(game, plain, rich) == plain.id


def test_a_special_counts_as_one_more_layer_and_quality_scales_the_layers(content, world):
    """特別功效算一層；品質越高每一層越值（跟遊戲裡的倍數同一份：Config.trait_quality_multiplier）。"""
    plain, rich = _two_arts(world, rich_top=29.0, rich_traits=("剛",), rich_special="lianhuan")
    # 29 × (1 + 0.05 × 2) = 31.9 > 30 × 1.05 = 31.5：特別功效那一層讓威力少一點的贏
    assert bot._worth(content, rich) > bot._worth(content, plain)
    ordinary = rich.model_copy(update={"special": None})
    assert bot._worth(content, ordinary) < bot._worth(content, plain)
    gold = plain.model_copy(update={"quality": "上品"})
    assert bot._worth(content, gold) == plain.top_power * (1 + bot.TRAIT_WEIGHT * 2)  # 上品 ×2 層


def test_the_bot_stays_put_on_equal_worth_and_without_traits_in_the_content(content, world):
    """沒有功效的內容（舊內容）：只看威力，跟以前一樣；一樣值錢的不換。"""
    plain, rich = _two_arts(world)
    content.traits.general.clear()
    content.traits.special.clear()
    assert bot._worth(content, plain) == plain.top_power and bot._worth(content, rich) == rich.top_power
    game = armed(content, world)
    assert _wear_and_switch(game, plain, rich) == plain.id  # 30 > 29：照第十成威力選
    twin = plain.model_copy(update={"id": "雙生拳", "name": "雙生拳"})
    world.claim_skill_name(twin)
    game2 = armed(content, world)
    p = game2.state.player
    p.member.wugong_id, p.arts = plain.id, [twin.id]
    bot._switch_to_the_strongest(game2)
    assert p.member.wugong_id == plain.id


def test_the_bot_weighs_the_traits_of_the_inner_art_too(content, world):
    """內功一樣：功效多的那門內功換上身（照種類各挑各的）。"""
    game = armed(content, world)
    plain = generate_from_name("素功", "內功", "素功", attribute="柔").model_copy(
        update={"origin": "fused", "quality": "下品", "base_power": 10.0, "top_power": 30.0, "traits": ["柔"]},
    )
    rich = plain.model_copy(update={"id": "繁功", "name": "繁功", "top_power": 29.0, "traits": ["柔", "柔", "柔"]})
    for art in (plain, rich):
        world.claim_skill_name(art)
    p = game.state.player
    p.member.neigong_id, p.arts = plain.id, [rich.id]
    for art_id in (plain.id, rich.id):
        p.art_quality[art_id] = "下品"
    bot._switch_to_the_strongest(game)
    assert p.member.neigong_id == rich.id and p.member.wugong_id == "basic_fist"


def test_the_trait_measure_script_still_runs():
    """scripts/measure_traits.py（計畫六 Task 5，只量不擋）：另開一個行程跑單一功效的兩段（少量場數、不跑整季），退出碼 0、
    每一個功效都有一行——引擎改了名字它就會壞，這條抓得到（整季那一段由 sim 跑，太慢不放進測試）。"""
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    done = subprocess.run(
        [sys.executable, "scripts/measure_traits.py", "--no-season", "--runs", "20"],
        cwd=root, capture_output=True, timeout=300,
    )
    out = done.stdout.decode("utf-8", "replace")
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")[-2000:]
    for name in ("先手", "穩", "破甲", "化勁", "乘勝", "吸取", "險", "厚", "連環", "不動", "護命", "悟招", "借力", "回春", "輕身"):
        assert f"〔{name}〕" in out, name
    assert "一、單一功效" in out and "三、勢均力敵的仗" in out


def test_the_bot_fuses_cultivates_and_melts_when_full(content, world):
    game = Game.new(content, "機器人", rng=random.Random(0), world=world)
    p = game.state.player
    p.member.wugong_id = "basic_fist"
    p.insights = ["feng"]
    p.stats["xinde"] = 100
    p.stamina = 150
    bot.forge_and_cultivate(game, random.Random(0))
    fused = [a for a in library.owned_arts(game.state) if a != "basic_fist"]
    assert len(fused) == 1
    assert p.art_quality.get(fused[0]) == "中品" or p.art_mastery.get(fused[0]) == 1  # 也修練了一次
    p.insights = []  # 沒有意境可合成：這一輪只會熔，不會又合成回來
    content.config.holding_cap_base = library.held_count(game.state)  # 正好滿了
    bot.forge_and_cultivate(game, random.Random(0))
    assert library.held_count(game.state) == content.config.holding_cap_base - 1  # 滿了先熔一門


def test_the_bot_sometimes_merges_two_insights_instead(content, world):
    """手上有兩個以上意境時，一部分機會改做合併（兩個意境→新意境，兩個都留著）。"""
    game = armed(content, world)
    game.state.player.insights = ["feng", "huo"]
    before = set(game.state.player.insights)
    bot.forge_and_cultivate(game, Fixed(0.0))
    assert before < set(game.state.player.insights) and len(game.state.player.insights) == 3
    assert library.owned_arts(game.state) == ["basic_fist"]  # 這一輪做的是合併，沒有合成


def test_the_bot_fuses_when_the_merge_chance_does_not_come_up(content, world):
    game = armed(content, world)
    game.state.player.insights = ["feng", "huo"]
    bot.forge_and_cultivate(game, Fixed(0.99))
    assert len(game.state.player.insights) == 2 and len(library.owned_arts(game.state)) == 2


def test_the_bot_blends_two_arts_when_it_has_no_insight_to_fuse(content, world):
    """武學＋武學（設計 12.3）：沒有意境可合成、手上有兩門武學時，機器人把兩門合成第三門。"""
    game = armed(content, world)
    game.state.player.member.neigong_id = "basic_breath"
    game.state.player.insights = []
    bot.forge_and_cultivate(game, random.Random(0))
    assert len(library.owned_arts(game.state)) == 3


def test_the_bot_sometimes_blends_instead_of_fusing(content, world):
    game = armed(content, world)
    game.state.player.member.neigong_id = "basic_breath"
    before = set(library.owned_arts(game.state))
    bot.forge_and_cultivate(game, Fixed(bot.BLEND_SHARE - 0.01))  # 只有一個意境不會合併；這個數落在武學＋武學那一段
    new = [a for a in library.owned_arts(game.state) if a not in before]
    assert len(new) == 1 and game.world.get_skill(new[0]).parents == ["basic_breath", "basic_fist"]


def test_the_bot_fuses_when_the_blend_chance_does_not_come_up(content, world):
    """兩種都能做時，BLEND_SHARE 以上的數仍然是武學＋意境：新的那門有底（base）、沒有 parents。"""
    game = armed(content, world)
    game.state.player.member.neigong_id = "basic_breath"
    before = set(library.owned_arts(game.state))
    bot.forge_and_cultivate(game, Fixed(bot.BLEND_SHARE + 0.01))
    new = [a for a in library.owned_arts(game.state) if a not in before]
    assert len(new) == 1
    art = game.world.get_skill(new[0])
    assert art.parents == [] and art.base in ("basic_breath", "basic_fist") and art.insight == "feng"


def test_the_forge_reserve_is_more_than_a_forge_costs(content):
    """低於保留量的測試才有意義：少一點的體力要還付得起一爐，被擋下的才是保留量、不是體力不夠。"""
    assert bot.FORGE_RESERVE - 1 >= content.config.fuse_stamina
    assert bot.FORGE_RESERVE - 1 >= content.config.merge_stamina


def test_the_bot_does_not_forge_below_the_forge_reserve(content, world):
    game = armed(content, world)
    game.state.player.stamina = bot.FORGE_RESERVE - 1
    bot.forge_and_cultivate(game, random.Random(0))
    assert library.owned_arts(game.state) == ["basic_fist"]
    assert game.state.player.stamina == bot.FORGE_RESERVE - 1


def test_the_bot_does_not_blend_below_the_forge_reserve(content, world):
    """兩門武學、沒有意境：只剩武學＋武學這一條路，低於保留量也一樣不合（保留量擋的是三種合成，不只合成）。"""
    game = armed(content, world)
    game.state.player.member.neigong_id = "basic_breath"
    game.state.player.insights = []
    game.state.player.stamina = bot.FORGE_RESERVE - 1
    bot.forge_and_cultivate(game, random.Random(0))
    assert len(library.owned_arts(game.state)) == 2
    assert not any(key.startswith(fusion.BLEND_PREFIX) for key in world.recipe_keys())
    assert game.state.player.stamina == bot.FORGE_RESERVE - 1 and game.state.player.stats["xinde"] == 100


def test_the_bot_forges_with_exactly_the_forge_reserve(content, world):
    game = armed(content, world)
    game.state.player.stamina = bot.FORGE_RESERVE
    bot.forge_and_cultivate(game, random.Random(0))
    assert len(library.owned_arts(game.state)) == 2
    assert game.state.player.stamina == bot.FORGE_RESERVE - content.config.fuse_stamina


def test_the_bot_with_one_art_and_no_insight_forges_nothing(content, world):
    game = armed(content, world)
    game.state.player.insights = []
    bot.forge_and_cultivate(game, random.Random(0))
    assert library.owned_arts(game.state) == ["basic_fist"]
    assert game.state.player.stamina == 150  # 什麼都沒花（也沒修練：沒有意境就沒有修練的東西）


def test_the_bot_pays_only_when_a_blend_really_makes_something(content, world):
    """合出來的你已經有了就不再合（blend_problem 先擋，試 FORGE_TRIES 組都被擋就這一輪不合）：連跑幾輪，每一輪要嘛
    多一門、花一次價錢，要嘛什麼都沒花；每一組只合過一次（配方鍵不重複）。"""
    game = armed(content, world)
    p = game.state.player
    p.member.neigong_id, p.insights = "basic_breath", []
    cfg = content.config
    low = bot.FORGE_RESERVE + 5  # 合完還低於修練的保留量：每一輪只看合成
    made_in_all = 0
    for turn in range(10):
        p.stamina, p.stats["xinde"] = low, 100
        held = len(library.owned_arts(game.state))
        bot.forge_and_cultivate(game, random.Random(turn))
        made = len(library.owned_arts(game.state)) - held
        assert made in (0, 1)
        assert (p.stats["xinde"], p.stamina) == (100 - made * cfg.fuse_xinde, low - made * cfg.fuse_stamina)
        made_in_all += made
    blends = [key for key in world.recipe_keys() if key.startswith(fusion.BLEND_PREFIX)]
    assert made_in_all >= 2 and len(blends) == made_in_all and len(set(blends)) == len(blends)


def test_the_bot_names_the_art_it_mastered_with_a_fallback_name(content, world):
    """練成絕學的第一人要自己取名：機器人不叫模型，走退路字表（取出來的名字過得了命名過濾）。"""
    game = armed(content, world)
    game.forge("basic_fist", ["feng"])
    game.state.player.stats["xinde"] = 0
    art_id = next(a for a in library.owned_arts(game.state) if a != "basic_fist")
    world.claim_master(art_id, game.state.player.name)
    game.state.player.naming = art_id
    bot.forge_and_cultivate(game, random.Random(0))
    assert game.state.player.naming is None
    assert world.get_skill(art_id).name != art_id  # 全服的這門改了名


def test_the_bot_keeps_its_stamina_for_the_road_below_the_reserve(content, world):
    game = armed(content, world)
    game.state.player.stamina = bot.CULTIVATE_RESERVE - 1
    bot.forge_and_cultivate(game, random.Random(0))
    # 合成也花體力了（設計 12.1）：這一輪合了一爐，但體力沒到修練的保留量，沒有修練
    assert game.state.player.stamina == bot.CULTIVATE_RESERVE - 1 - content.config.fuse_stamina
    assert not game.state.player.art_mastery and not game.state.player.art_quality


def ready_to_climb(content, world, quality):
    """已經融過意境、品質是 quality、手上有一枚破境丹的機器人；心得歸零，所以這一輪只會修練、不會再合成。"""
    game = armed(content, world)
    game.forge("basic_fist", ["feng"])
    p = game.state.player
    art_id = next(a for a in library.owned_arts(game.state) if a != "basic_fist")
    p.art_quality[art_id] = quality
    p.stats["xinde"] = 0
    p.stamina = 150
    p.legend_items = 1
    return game, art_id


def test_the_bot_takes_a_pill_when_it_goes_for_a_peerless_art(content, world):
    """破境丹（企劃者：玩家自己決定哪一次衝絕學要服）：機器人手上有、而且這一次衝的是絕學就服。"""
    game, art_id = ready_to_climb(content, world, "上品")
    bot.forge_and_cultivate(game, random.Random(0))
    assert game.state.player.legend_items == 0
    assert game.state.player.stamina < 150  # 真的修練了


def test_the_bot_keeps_its_pill_for_the_peerless_step(content, world):
    """下品→中品、中品→上品用不上丹：不傳 use_legend，丹留著、也不會多一句「這一回沒服」。"""
    for quality in ("下品", "中品"):
        game, art_id = ready_to_climb(content, world, quality)
        bot.forge_and_cultivate(game, random.Random(0))
        assert game.state.player.legend_items == 1
        assert game.state.player.stamina < 150  # 真的修練了
        assert not any("沒服" in line for line in game.state.log)


def test_pick_accepts_whoever_the_event_wants_to_recruit(game):
    game.state.player.flags.add("heard_music")
    game.state.pending_event = "meet"
    options = game.options()
    assert pick(game, options, random.Random(0)) == "choice:0"  # 「請他入門」


def test_pick_is_random_when_nothing_wants_to_be_recruited(game):
    options = [o for o in game.options(odds=False) if o.enabled]
    seeds = {pick(game, options, random.Random(seed)) for seed in range(20)}
    assert seeds <= {o.id for o in options} and len(seeds) > 1


def test_pick_returns_none_with_nothing_to_choose(game):
    assert pick(game, [], random.Random(0)) is None


def test_pick_never_takes_the_road_options_meant_for_humans(game):
    """路上設計第六節：機器人不折返、不改道、不做路上小事。折返在路上永遠按得下去，不排除的話
    play_season「沒有能選的就推進時間」這個訊號會失效。"""
    game.choose("move:lake")
    options = [o for o in game.options(odds=False) if o.enabled]
    assert "road:back" in [o.id for o in options]
    assert pick(game, options, random.Random(0)) is None


def test_play_season_completes_a_full_season(content):
    game = play_season(content, 0, max_steps=500)
    assert game.state.world.ended
    assert game.state.world.ending_title
    assert game.state.world.time > 0


def test_play_season_is_deterministic_for_a_given_seed(tmp_path, content):
    """同一顆種子要重現一模一樣的結果——各自給獨立的共用世界狀態，不然招募/取名的
    競態結果會因為兩次呼叫共用同一份檔案而互相汙染，讓比較失去意義。"""
    a = play_season(content, 1, max_steps=200, world=open_world(tmp_path / "a.db"))
    b = play_season(content, 1, max_steps=200, world=open_world(tmp_path / "b.db"))
    assert a.state.player.member.level == b.state.player.member.level
    assert a.state.world.time == b.state.world.time


def test_play_season_grows_the_players_arts_with_xinde(content):
    game = play_season(content, 1, max_steps=500)
    member = game.state.player.member
    assert member.neigong_level > 1 or member.wugong_level > 1


def test_play_season_observe_is_called_before_and_after_every_step(content):
    seen = []
    play_season(content, 0, max_steps=5, observe=lambda g: seen.append(g.state.world.time))
    assert len(seen) == 6  # 開季一次 + 每步一次
    assert seen[0] == 0.0


def test_the_bot_opens_the_season_itself_when_the_server_is_still_preparing(content):
    content.config.auto_open_first_season = False
    game = play_season(content, 1)
    assert game.state.world.ended


def test_a_bot_does_not_try_to_heal_what_it_cannot_afford(game):
    """付不起療傷費就先不療傷，不然每一輪都會在江湖紀錄裡寫一筆「銀兩不足」。"""
    member = game.state.player.member
    member.injury = 40.0
    game.state.player.stats["silver"] = 0
    assert not wants_heal(game)
    game.state.player.stats["silver"] = 999
    assert wants_heal(game)


def test_the_bot_backs_out_of_an_audience_list_it_cannot_use(content, game):
    """機器人隨機挑選項，可能按到「求見」；名單上的人都見不到時「返回」永遠按得下去，整季模擬不會卡住。"""
    for cid in ("mate", "scholar"):
        content.characters[cid].deep_interaction = True
        content.characters[cid].audience_fame = 99
    game.choose("act:call")
    options = [o for o in game.options(odds=False) if o.enabled]
    assert [o.id for o in options] == ["call:mate", "call:scholar", "call:back"]  # 名望不夠的求見也按得下去（會被打發）
    assert pick(game, options, random.Random(0)) == "call:back"  # 但機器人不挑，只剩「返回」可選


def test_the_bot_does_not_knock_on_a_door_that_will_not_open(content, game):
    """名望不夠的求見永遠按得下去（會被打發）：機器人不挑，不然「沒事可做就推進時間」的訊號會失效（同 act:rest）。"""
    ch = content.characters["mate"]
    ch.deep_interaction, ch.audience_fame = True, 30
    options = [o for o in game.options(odds=False) if o.enabled]
    assert "call:mate" in [o.id for o in options]  # 按得下去
    for seed in range(50):
        assert pick(game, options, random.Random(seed)) != "call:mate"


def test_the_bot_still_may_call_on_a_figure_it_can_meet(content, game):
    """見得到的人物不排除（跟以前一樣隨機挑到才求見）。"""
    ch = content.characters["mate"]
    ch.deep_interaction, ch.audience_fame = True, 30
    game.state.player.stats["fame"] = 30
    options = [o for o in game.options(odds=False) if o.enabled]
    assert any(pick(game, options, random.Random(seed)) == "call:mate" for seed in range(200))


def test_the_bot_joins_a_muster_before_doing_anything_else(content, game):
    """集結時選單照常有別的事可做（FB-009）；機器人還沒參戰就先加入，加入之後才照常隨機挑（不會在兩邊之間一直換）。"""
    definition = BattleDef(
        id="t1", name="測試決戰",
        factions=[BattleFaction(id="guan", name="官軍"), BattleFaction(id="huang", name="黃巾")],
        acts=[BattleAct(id="a1", title="初探", text="雙方試探。", goal="推動戰局",
                        options=[BattleOption(text=f"{s}{m}", tag=f"{s}_{c}", faction=s, move=m)
                                 for s in ("guan", "huang") for m, c in (("強攻", "strong"), ("固守", "hold"), ("奇襲", "raid"))])],
        outcomes=[BattleOutcome(faction="guan", title="官軍大勝", text="官軍獲勝。")],
        muster_seconds=600, round_seconds=120,
    )
    content.battles[definition.id] = definition
    game.world.start_battle(definition, now=game.now)
    options = [o for o in game.options(odds=False) if o.enabled]
    assert len(options) > 2
    assert all(pick(game, options, random.Random(seed)) == "battle:join:guan" for seed in range(5))
    game.choose("battle:join:guan")
    options = [o for o in game.options(odds=False) if o.enabled]
    picks = {pick(game, options, random.Random(seed)) for seed in range(20)}
    assert len(picks - {"battle:join:huang"}) >= 2  # 已經加入：照常在平常的選項裡隨機挑，不是每一步都換邊


def test_the_bot_spends_its_stat_points(game):
    game.state.player.stat_points = 3
    bot.allocate_points(game, random.Random(0))
    p = game.state.player
    assert p.stat_points == 0 and sum(p.stats[k] for k in ("str", "agi", "con", "wis", "lore")) == 28  # 五項各 5，加上 3 點


def test_the_bot_leaves_capped_stats_alone_and_stops_when_all_are_capped(game):
    p = game.state.player
    p.stat_points = 4
    p.stats.update({"str": 15, "agi": 15, "con": 15, "wis": 14, "lore": 15})
    bot.allocate_points(game, random.Random(0))
    assert p.stats["wis"] == 15 and p.stat_points == 3  # 只有悟性還能加；全到頂後剩下的點留著
    assert (p.stats["str"], p.stats["agi"], p.stats["con"], p.stats["lore"]) == (15, 15, 15, 15)


def test_the_bot_puts_points_into_lore_when_the_rest_are_full(content, world):
    game = Game.new(content, "機器人", rng=random.Random(0), world=world)
    p, cap = game.state.player, content.config.stat_cap
    for key in ("str", "agi", "con", "wis"):
        p.stats[key] = cap
    p.stat_points = 2
    bot.allocate_points(game, random.Random(0))
    assert p.stats["lore"] == 7 and p.stat_points == 0


def test_the_bot_does_nothing_without_points(game):
    before = dict(game.state.player.stats)
    bot.allocate_points(game, random.Random(0))
    assert game.state.player.stats == before and game.state.player.stat_points == 0


def test_the_bot_does_not_spin_when_the_game_refuses_every_allocation(content, world):
    """賽季籌備中 Game.allocate_stat 一律拒絕、點數不會少：迴圈要有界、馬上回來（它在全服寫入鎖裡跑，空轉會凍住伺服器）。"""
    content.config.auto_open_first_season = False
    game = Game.new(content, "甲", rng=random.Random(1), world=world)
    game.state.player.stat_points = 1
    real, calls = game.allocate_stat, []

    def counted(stat):
        calls.append(stat)
        assert len(calls) <= 3, "allocate_points keeps calling a refusing allocate_stat"
        return real(stat)

    game.allocate_stat = counted
    bot.allocate_points(game, random.Random(0))
    assert len(calls) == 1 and game.state.player.stat_points == 1  # 試了一次、被拒絕就停；那一點還在
