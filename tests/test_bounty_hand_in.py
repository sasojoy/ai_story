"""懸賞榜的求藝、求兵（懸賞榜設計第四節、第九節；企劃者 2026-10-10）：官軍、黃巾、地方豪強每週各掛一張求藝、一張求兵，
不用揭、在城鎮的懸賞榜上直接交（交了就沒了），前三個交的有賞；散人三方都能交，陣營的人只交自己陣營的、拿全額。

角色開在同一個資料庫，照伺服器的做法一個動作一次讀存（test_bounties 的 _do、_direct）。"""
from __future__ import annotations

import pytest

from conftest import real_content
from test_bounties import _direct, _do, _ids, _load, _post, beta_setup  # noqa: F401  （beta_setup 是 fixture）
from tianxia import bot, bot_policy, bounties, calendar, library
from tianxia.characters import CharacterStore
from tianxia.content import ContentError, validate
from tianxia.martial_arts import generate_from_name
from tianxia.models import WEAPON_KINDS
from tianxia.state import BotProfile, Equipment, GameState, PlayerState, Weapon, WorldState
from tianxia.world_state import fresh_season

LOW = {"下品": 100.0, "中品": 0.0, "上品": 0.0, "絕學": 0.0}


def _fused(world, name, attribute="剛", kind="武學", **update):
    """全服登記一門合成出來的武學（同 test_library._fused；update 蓋掉幾個欄位，例如 preset）。"""
    art = generate_from_name(name, kind, name, weights=LOW, attribute=attribute).model_copy(update={"origin": "fused", **update})
    world.claim_skill_name(art)
    return art


def _edit(world, name, fn):
    """讀一個角色的存檔、改玩家那一份（fn(player)）、存回去。"""
    state = CharacterStore(world.db).load(name)
    fn(state.player)
    CharacterStore(world.db).save(state)


def _blade(weapon_id, kind="劍", attribute="柔", tier=1, quality="下品", **kw) -> Weapon:
    return Weapon(id=weapon_id, name=f"{attribute}{kind}{weapon_id[-1]}", kind=kind, attribute=attribute, tier=tier, quality=quality, **kw)


def _art(world, attribute="剛", faction="guan", quota=3, **kw):
    """貼一張求藝（每週的自動掛單另外測）。"""
    return _post(world, kind="art", faction=faction, silver=20, deeds=2, quota=quota, attribute=attribute, **kw)


def _arms(world, attribute="柔", weapon_kind="劍", faction="guan", quota=3, **kw):
    """貼一張求兵。"""
    return _post(world, kind="arms", faction=faction, silver=0, deeds=2, quota=quota, attribute=attribute, weapon_kind=weapon_kind, **kw)


def _issue(content, week=1) -> list:
    """照劇本掛第 week 週的那一批（bounties.issue；兩種季都是它），回整個榜。"""
    state = GameState(player=PlayerState(name="測", location="town", stats={}, stamina=0), world=fresh_season(content))
    state.world.time = calendar.week_start(week, content, state.world)
    bounties.issue(state, content, week)
    return state.world.bounties


def test_each_side_posts_one_art_and_one_arms_bounty_with_attributes_that_do_not_repeat():
    """設計 4.1：劇本的每個陣營（含地方豪強）每期各掛一張求藝、一張求兵；屬性從剛柔快慢挑，同一期同一種三方不重複；求兵另挑種類；
    名額 3、不掛地點，期限同其他懸賞。正式內容（兵器開著）一批 8＋6＝14 張。"""
    content = real_content()
    board = _issue(content)
    sides = [f.id for f in content.scenario.factions]
    assert len(board) == 14 and sides == ["guan", "huang", "haoqiang"]
    for kind in ("art", "arms"):
        asks = [b for b in board if b.kind == kind]
        assert [b.faction for b in asks] == sides
        assert len({b.attribute for b in asks}) == 3 and {b.attribute for b in asks} <= {"剛", "柔", "快", "慢"}
        assert all(b.quota == 3 and b.location is None for b in asks)
    assert all(b.weapon_kind in WEAPON_KINDS for b in board if b.kind == "arms")
    assert all(b.weapon_kind is None for b in board if b.kind == "art")
    assert len({b.expires for b in board}) == 1


def test_fewer_attributes_than_sides_still_posts_for_every_side():
    """give_attributes 比陣營少（只寫兩個）：三方照樣掛得出來（不丟 ValueError），先不重複、多的那一方可以重複（設計 4.1）。"""
    content = real_content()
    content.config.bounties.give_attributes = ["剛", "柔"]
    asks = [b for b in _issue(content) if b.kind == "art"]
    assert len(asks) == 3 and {asks[0].attribute, asks[1].attribute} == {"剛", "柔"} and asks[2].attribute in ("剛", "柔")


def test_no_arms_bounties_with_weapons_off():
    content = real_content()
    content.config.weapons.enabled = False
    board = _issue(content)
    assert not any(b.kind == "arms" for b in board) and sum(b.kind == "art" for b in board) == 3 and len(board) == 11


def test_the_hand_in_bounties_draw_from_their_own_dice():
    """求藝、求兵另開一份亂數（設計 4.1）：同一週的討伐、打探、護送地點跟沒有求藝、求兵時一樣。"""
    content = real_content()
    spots = [(b.kind, b.faction, b.location, b.end) for b in _issue(content) if b.kind not in bounties.GIVE_KINDS]
    content.config.bounties.give_kinds = []
    assert [(b.kind, b.faction, b.location, b.end) for b in _issue(content)] == spots


def test_titles_how_and_rewards_name_the_attribute_and_the_weapon_kind():
    """標題寫「求藝・剛」「求兵・屬柔的劍」（不是「求藝・」；種類照兵器名的字，拳腳寫拳套、弓弩寫弩）；賞那一段照 reward_text：
    陣營的人全額、不寫俠名（設計 4.2、4.7）。"""
    content = real_content()
    board = _issue(content)
    art = next(b for b in board if b.kind == "art")
    arms = next(b for b in board if b.kind == "arms")
    assert bounties.title(content, art) == f"求藝・{art.attribute}"
    fist, crossbow = (arms.model_copy(update={"weapon_kind": k}) for k in ("拳腳", "弓弩"))
    assert bounties.title(content, fist) == f"求兵・屬{arms.attribute}的拳套"  # 種類照 weapons.NOUNS 寫（同兵器名；FB-133）
    assert f"一把屬{arms.attribute}的弩（" in bounties.how(content, crossbow)
    assert f"屬{art.attribute}、合成出來的武學或內功" in bounties.how(content, art) and "None" not in bounties.how(content, arms)
    loner = GameState(player=PlayerState(name="測", location="town", stats={}, stamina=0), world=WorldState())
    assert bounties.reward_text(loner, content, art) == "賞銀 20・經驗 30・心得 20・俠名 +2・素材，偶有兵器"
    assert bounties.reward_text(loner, content, arms) == "賞銀 20～50（照品質，高階另加）・經驗 30・心得 10・俠名 +2"
    loner.player.faction = art.faction
    assert bounties.reward_text(loner, content, art) == "賞銀 20・經驗 30・心得 20・素材，偶有兵器"
    content.config.weapons.enabled = False
    assert bounties.reward_text(loner, content, art).endswith("心得 20・素材")  # 兵器關著：不送兵器


def test_hand_ins_are_not_taken(beta_setup):
    """求藝、求兵不用揭（設計 4.3）：揭了會佔掉 max_taken 的格子、擋掉討伐與打探，整季機器人與假人也會一直揭。"""
    content, world = beta_setup
    art = _post(world, kind="art", faction="guan", silver=20, deeds=2, quota=3, attribute="剛")
    msgs, _ = _direct(content, world, "丙", lambda g: bounties.take(g.state, g.content, art.id))
    assert msgs == [bounties.NO_TAKE] and world.get_season().bounties[-1].takers == []


@pytest.mark.parametrize("field, value", [
    ("kinds", ["strike", "raid"]),
    ("give_kinds", ["art", "armor"]),
    ("give_kinds", ["art", "art"]),  # 照 kinds 的習慣寫兩次是想掛兩張，issue 卻只掛一張：擋下來
    ("give_attributes", []),
    ("give_attributes", ["剛", "土"]),
    ("give_attributes", ["剛", "剛", "柔"]),
    ("arms_silver", {"下品": 20, "中品": 35}),
    ("arms_tier", {"1": 1, "2": 2}),
])
def test_validate_checks_the_bounty_settings(content, field, value):
    """設計 4.1 末段：認不得的種類（以前 issue 默默跳過）、挑不到屬性、求兵的價錢少一個品質或一個階（交那一把會 KeyError），載入時就擋；
    give_kinds、give_attributes 重複也擋（審查補的）。"""
    setattr(content.config.bounties, field, value)
    with pytest.raises(ContentError, match=f"Config.bounties.{field}"):
        validate(content)


def test_what_fits_an_art_bounty_and_what_does_not(beta_setup):
    """設計 4.5 第 3～6 條各一個例子：只收合成出來的（內容武學、師門配方、查不到資料的不收）、身上正在練的與等著定名的先擋、
    屬性要對、別的陣營的與交過的不行。fit_problem 只看東西合不合這一張，不看人在哪裡。"""
    content, world = beta_setup
    good, worn, naming, wrong = (_fused(world, n, attribute=a) for n, a in (("烈焰掌", "剛"), ("鐵砂掌", "剛"), ("斷金拳", "剛"), ("流水掌", "柔")))
    preset = _fused(world, "開山拳", preset=True)  # 師門配方（content/preset_recipes.json）也是 fused：照「內容寫好的不收」擋

    def library_of(p):
        p.arts = [good.id, naming.id, wrong.id, preset.id, "sword"]
        p.member.wugong_id, p.naming = worn.id, naming.id

    _edit(world, "丙", library_of)
    assert world.claim_master(naming.id, "丙")  # 第一個練成絕學的人：不登記的話，Game 一建好就把取名權當作過期丟掉
    art = _art(world)
    scout = _post(world, kind="scout", faction="guan", silver=10, deeds=2, location="lake")
    done = _art(world, faction="huang", done_by=["丙"])
    ids = [good.id, worn.id, naming.id, wrong.id, preset.id, "sword", "不存在"]
    problems = _do(content, world, "丙", lambda g: [bounties.fit_problem(g.state, g.content, g.world, art, i) for i in ids])[0]
    assert problems == [
        None, bounties.WORN_ART, bounties.UNNAMED, bounties.WANT_ART.format(attribute="剛"), bounties.ONLY_FUSED, bounties.ONLY_FUSED,
        bounties.NO_ART,
    ]

    def ghost(g):  # 存檔記著、內容與全服登記都沒有的失效引用：讀檔時 _drop_stale_references 會丟掉，只會出現在一個動作的中途
        g.state.player.arts.append("幽靈拳")
        return bounties.fit_problem(g.state, g.content, g.world, art, "幽靈拳")

    assert _do(content, world, "丙", ghost)[0] == bounties.NO_DATA
    assert _do(content, world, "丙", lambda g: bounties.fitting(g.state, g.content, g.world, art))[0] == [good.id]
    assert _do(content, world, "丙", lambda g: bounties.fit_problem(g.state, g.content, g.world, scout, good.id))[0] == bounties.NOT_NOW
    assert _do(content, world, "丙", lambda g: bounties.fit_problem(g.state, g.content, g.world, done, good.id))[0] == bounties.GIVEN_BEFORE
    _edit(world, "甲", lambda p: p.arts.append(good.id))
    theirs = _art(world, faction="huang")
    assert _do(content, world, "甲", lambda g: bounties.fit_problem(g.state, g.content, g.world, theirs, good.id))[0] == bounties.NOT_YOURS


def test_what_fits_an_arms_bounty_including_the_one_in_hand(beta_setup):
    """設計 4.5 第 7 條：種類與屬性都要對、什麼品質都收；手上那把也收（企劃者 2026-10-10，14.1 丙），空手時交裝備庫裡的也行；
    最不值錢的排前面（品質、階、鋒利度）。兵器關著一律不收。"""
    content, world = beta_setup
    content.config.weapons.enabled = True
    arms = _arms(world)

    def armed(p):
        p.weapon = _blade("兵:1", quality="中品")
        p.rack = [_blade("兵:2", quality="上品", tier=2), _blade("兵:3", kind="刀"), _blade("兵:4", attribute="剛"), _blade("兵:5", edge=40)]

    _edit(world, "丙", armed)
    ids = ["兵:1", "兵:2", "兵:3", "兵:4", "兵:5", "兵:9"]
    problems = _do(content, world, "丙", lambda g: [bounties.fit_problem(g.state, g.content, g.world, arms, i) for i in ids])[0]
    wrong = bounties.WANT_ARMS.format(attribute="柔", noun="劍")
    assert problems == [None, None, wrong, wrong, None, bounties.NO_WEAPON]
    assert _do(content, world, "丙", lambda g: bounties.fitting(g.state, g.content, g.world, arms))[0] == ["兵:5", "兵:1", "兵:2"]
    _edit(world, "丙", lambda p: setattr(p, "weapon", None))
    assert _do(content, world, "丙", lambda g: bounties.fit_problem(g.state, g.content, g.world, arms, "兵:2"))[0] is None
    content.config.weapons.enabled = False
    assert _do(content, world, "丙", lambda g: bounties.fit_problem(g.state, g.content, g.world, arms, "兵:2"))[0] == bounties.NOT_NOW


def test_armor_is_never_offered_to_an_arms_bounty(beta_setup):
    """裝備一之後裝備庫裡武器、防具混放（state.Equipment 有 slot）：求兵只看武器那一欄。裝備庫裡的防具與身上穿著的防具，
    屬性再對也不收、不列，fit_problem 回「裝備庫裡沒有這一件」（不是「要屬…的劍」：防具根本不是這一張的候選）。"""
    content, world = beta_setup
    content.config.weapons.enabled = True
    arms = _arms(world)

    def geared(p):
        p.weapon = _blade("兵:1")
        p.armor = Equipment(slot="armor", id="甲:7", name="柔甲7", attribute="柔", tier=1, quality="下品")
        p.rack = [_blade("兵:2", quality="上品"), Equipment(slot="armor", id="甲:6", name="柔甲6", attribute="柔", tier=1, quality="下品")]

    _edit(world, "丙", geared)
    problems = _do(content, world, "丙", lambda g: [bounties.fit_problem(g.state, g.content, g.world, arms, i) for i in ("甲:6", "甲:7", "兵:2")])[0]
    assert problems == [bounties.NO_WEAPON, bounties.NO_WEAPON, None]
    assert _do(content, world, "丙", lambda g: bounties.fitting(g.state, g.content, g.world, arms))[0] == ["兵:1", "兵:2"]


def test_fitting_lists_the_art_that_melts_for_least_first(beta_setup):
    """設計 4.4：合用的照「最不值錢的先」排——求藝照熔煉值（library.melt_value）、再照名字。"""
    content, world = beta_setup
    high, low, mid = _fused(world, "烈焰掌"), _fused(world, "鐵砂掌"), _fused(world, "斷金拳")

    def library_of(p):
        p.arts = [high.id, low.id, mid.id]
        p.art_levels = {high.id: 7, low.id: 1, mid.id: 5}

    _edit(world, "丙", library_of)
    art = _art(world)
    order, values = _do(content, world, "丙", lambda g: (
        bounties.fitting(g.state, g.content, g.world, art),
        [library.melt_value(g.state, g.content, g.world, i) for i in (low.id, mid.id, high.id)],
    ))[0]
    assert order == [low.id, mid.id, high.id] and values == sorted(values) and values[0] < values[-1]


def test_arts_that_melt_for_the_same_give_the_lower_quality_one_first(beta_setup):
    """PM 2026-10-11：熔煉值一樣時，品質低的先（求藝照熔煉值、品質〔低的先〕、再照名字）。熔煉值只算自己修練上去的幾階，
    合成時就擲到上品的那門（art_rolled）跟下品的那門同成同值，名字又排在下品那門前面——只看熔煉值與名字的話，上品的會被排在前面交出去。"""
    content, world = beta_setup
    upper, lower = _fused(world, "烈焰掌"), _fused(world, "鐵砂掌")  # 「烈」排在「鐵」前面

    def library_of(p):
        p.arts = [upper.id, lower.id]
        p.art_quality[upper.id] = p.art_rolled[upper.id] = "上品"  # 合成時擲到上品：登記的是下品，自己這一份是上品，熔煉沒有加給

    _edit(world, "丙", library_of)
    art = _art(world)
    order, values, qualities = _do(content, world, "丙", lambda g: (
        bounties.fitting(g.state, g.content, g.world, art),
        [library.melt_value(g.state, g.content, g.world, i) for i in (upper.id, lower.id)],
        [g.state.player.art_quality.get(i, "下品") for i in (upper.id, lower.id)],
    ))[0]
    assert values[0] == values[1] and qualities == ["上品", "下品"]  # 前提：熔煉值打平、品質不同
    assert order == [lower.id, upper.id]


def test_giving_also_needs_the_board_here_and_the_bounty_still_up(beta_setup):
    """設計 4.5 第 1、2 條：give_problem 另看懸賞榜看不看得到、這一張還在不在榜上（過期、名額滿）；fit_problem 不看，所以城外的卡片照樣列。"""
    content, world = beta_setup
    good = _fused(world, "烈焰掌")
    _edit(world, "丙", lambda p: p.arts.append(good.id))
    art, full, late = _art(world), _art(world, quota=1, done_by=["乙"]), _art(world, expires=0.0)

    def check(g, b):
        return bounties.give_problem(g.state, g.content, g.world, b, good.id)

    assert _do(content, world, "丙", lambda g: [check(g, b) for b in (art, full, late)])[0] == [None, bounties.GONE, bounties.GONE]
    _edit(world, "丙", lambda p: setattr(p, "location", "lake"))
    assert _do(content, world, "丙", lambda g: check(g, art))[0] == bounties.NOT_NOW
    assert _do(content, world, "丙", lambda g: bounties.fitting(g.state, g.content, g.world, art))[0] == [good.id]


def _give(bounty_id, item_id):
    """交出（bounties.give，直接呼叫；選單那一條路在後面測）。"""
    return lambda g: bounties.give(g.state, g.content, g.world, bounty_id, item_id)


def test_handing_in_an_art_takes_it_and_its_records_but_the_recipe_stays(beta_setup):
    """設計 4.6：交出去就沒了——功法庫拿掉、四份私有紀錄（成、自己那一份的品質、熟練度、擲到的品質）清掉、不退心得；
    全服登記的那一門照舊，照同一個配方再合一次查表就有、不叫模型（設計 4.10：這不是漏洞）。"""
    content, world = beta_setup

    def forge(g):
        g.state.player.insights.append("feng")
        g.state.player.stats["xinde"] = 50
        return g.forge("fist", ["feng"], proposed=("疾風拳", "一句話。"))

    _do(content, world, "丙", forge)
    art_id = _load(world, "丙").player.arts[0]

    def records(p):
        p.art_levels[art_id], p.art_quality[art_id], p.art_mastery[art_id], p.art_rolled[art_id] = 3, "中品", 1, "中品"

    _edit(world, "丙", records)
    b = _art(world, attribute="快")
    before = _load(world, "丙").player.stats["xinde"]
    msgs, game = _direct(content, world, "丙", _give(b.id, art_id))
    p = game.state.player
    assert msgs[0] == bounties.GIVEN.format(name="疾風拳", issuer="官軍", title="求藝・快")
    assert art_id not in p.arts and all(art_id not in r for r in (p.art_levels, p.art_quality, p.art_mastery, p.art_rolled))
    assert p.stats["xinde"] == before + content.config.bounties.xinde["art"]  # 只有賞的心得，不退熔煉的
    assert world.get_skill(art_id).creator == "丙"  # 全服登記的那一門不受影響，你是首創者也一樣
    _do(content, world, "丙", lambda g: g.forge("fist", ["feng"]))  # 沒給 proposed：配方已經登記，查表、不叫模型
    assert art_id in _load(world, "丙").player.arts


def test_loners_and_faction_members_get_full_pay_and_only_loners_add_deeds(beta_setup):
    """設計 4.7：求藝陣營的人也拿全額（不打 faction_share 的五成），散人另記俠名；兩邊都不記貢獻。前三個交的有賞、一人一次。
    第 4 階的散人交求藝，銀兩也乘 1.25（14.1 乙；求兵那一半在下一支）。"""
    content, world = beta_setup
    good = _fused(world, "烈焰掌")
    for name in ("甲", "丙"):
        _edit(world, name, lambda p: p.arts.append(good.id))
    b = _art(world)
    loner = _direct(content, world, "丙", _give(b.id, good.id))[0]
    member = _direct(content, world, "甲", _give(b.id, good.id))[0]
    for msgs in (loner, member):
        assert {"銀兩 +20", "經驗 +30", "心得 +20"} <= set(msgs)
    assert "俠名 +2" in loner and not any("俠名" in m for m in member)
    assert _load(world, "丙").player.ranger_deeds == 2 and _load(world, "甲").player.contrib == 0
    assert _load(world, "甲").player.bounties_done == _load(world, "丙").player.bounties_done == 1
    board = next(x for x in world.get_season().bounties if x.id == b.id)
    assert board.done_by == ["丙", "甲"] and board.takers == []
    late = _fused(world, "鐵砂掌")

    def tier_four(p):
        p.arts.append(late.id)
        p.ranger_deeds = 50  # 遊俠名號第 4 階：懸賞銀兩 ×1.25

    _edit(world, "丙", tier_four)
    second = _art(world)
    assert "銀兩 +25" in _direct(content, world, "丙", _give(second.id, late.id))[0]  # 20 × 1.25：求藝也套（14.1 乙），只乘一次


def test_an_art_bounty_hands_out_materials_of_its_attribute(beta_setup):
    """設計 4.7：求藝另給這張屬性的一階素材 2 個，art_material2_chance 再一個同屬性二階（測試內容剛有一、二階；屬性挑不到時
    materials.by_tier 退回同階全部，所以素材測試用剛）。"""
    content, world = beta_setup
    content.config.bounties.art_material2_chance, content.config.bounties.art_weapon_chance = 1.0, 0.0
    good = _fused(world, "烈焰掌")
    _edit(world, "丙", lambda p: p.arts.append(good.id))
    b = _art(world)
    msgs, game = _direct(content, world, "丙", _give(b.id, good.id))
    assert "獲得 精鐵砂 ×2" in msgs and "獲得 玄鋼骨 ×1" in msgs
    assert game.state.player.materials == {"gang_1": 2, "gang_2": 1}


def test_the_gift_weapon_fits_the_worn_art_and_a_full_rack_turns_it_into_silver(beta_setup):
    """設計 4.7：送的兵器種類配身上那門武學（長拳是拳腳）、屬性同這張、一階；上品 art_weapon_top_chance、其餘中品。
    空手時直接拿在手上；裝備庫滿了改給同品質的 arms_silver（那把兵器照價折，不乘名號加成）。"""
    content, world = beta_setup
    content.config.weapons.enabled = True
    cfg = content.config.bounties
    cfg.art_material2_chance, cfg.art_weapon_chance, cfg.art_weapon_top_chance = 0.0, 1.0, 1.0
    good, spare = _fused(world, "烈焰掌"), _fused(world, "鐵砂掌")
    _edit(world, "丙", lambda p: p.arts.extend([good.id, spare.id]))
    first, second = _art(world), _art(world)
    msgs, game = _direct(content, world, "丙", _give(first.id, good.id))
    w = game.state.player.weapon
    assert "兵器【厚背拳套】" in msgs and (w.kind, w.attribute, w.tier, w.quality) == ("拳腳", "剛", 1, "上品")
    _edit(world, "丙", lambda p: setattr(p, "rack", [_blade("兵:9", kind="刀")]))
    content.config.weapons.rack_cap = 1  # 手上一把、裝備庫一把：放不下了
    msgs, game = _direct(content, world, "丙", _give(second.id, spare.id))
    assert bounties.RACK_FULL_SILVER.format(name="厚背拳套", silver=50) in msgs and "銀兩 +50" in msgs
    assert [x.id for x in game.state.player.rack] == ["兵:9"] and game.state.player.stats["silver"] == 200 + 20 + 20 + 50


def test_no_gift_weapon_and_no_silver_for_it_with_weapons_off(beta_setup):
    content, world = beta_setup
    content.config.bounties.art_weapon_chance = 1.0
    good = _fused(world, "烈焰掌")
    _edit(world, "丙", lambda p: p.arts.append(good.id))
    b = _art(world)
    msgs, game = _direct(content, world, "丙", _give(b.id, good.id))
    assert not any("兵器" in m or "折成" in m for m in msgs) and game.state.player.weapon is None
    assert game.state.player.stats["silver"] == 220


def test_the_gift_dice_hang_on_the_season_the_name_and_the_bounty(beta_setup, monkeypatch):
    """設計 4.7：求藝的擲骰用自己的亂數（季數＋名號＋懸賞 id），不碰 Game.rng；同一個人交同一張永遠同一個結果，
    換一季擲出來的不一樣——懸賞 id 每季從 b1 算起，少了季數，記下哪幾號送兵器，下一季就專挑那幾張。"""
    cfg = real_content().config.bounties
    one = [bounties.gift_rolls(1, "丙", f"b{i}", cfg) for i in range(1, 41)]
    assert one == [bounties.gift_rolls(1, "丙", f"b{i}", cfg) for i in range(1, 41)]
    assert one != [bounties.gift_rolls(2, "丙", f"b{i}", cfg) for i in range(1, 41)]
    assert any(r.armed for r in one) and not all(r.armed for r in one)
    content, world = beta_setup
    good = _fused(world, "烈焰掌")
    _edit(world, "丙", lambda p: p.arts.append(good.id))
    b = _art(world)
    seen, real = [], bounties.gift_rolls
    monkeypatch.setattr(bounties, "gift_rolls", lambda season, name, bid, c: seen.append((season, name, bid)) or real(season, name, bid, c))

    def give(g):
        before = g.rng.getstate()
        bounties.give(g.state, g.content, g.world, b.id, good.id)
        return g.rng.getstate() == before

    assert _direct(content, world, "丙", give)[0] and seen == [(world.get_season_number(), "丙", b.id)]


def test_arms_pay_by_quality_and_tier_once_with_the_tier_four_bonus(beta_setup):
    """設計 4.7：求兵的銀兩 arms_silver[品質] × arms_tier[階]（三階 ×4），淬煉不加錢；第 4 階散人的 ×1.25 只乘一次
    （give 把底數交給 _complete(silver=)，由 _silver 乘）。經驗 30、心得 10、散人俠名 2。陣營的人交求兵也拿全額、沒有俠名。"""
    content, world = beta_setup
    content.config.weapons.enabled = True

    def armed(p):
        p.rack = [_blade("兵:2", quality="上品", tier=3, tempers=2), _blade("兵:3", quality="中品", tier=2)]
        p.ranger_deeds = 50  # 遊俠名號第 4 階：懸賞銀兩 ×1.25

    _edit(world, "丙", armed)
    top, mid = _arms(world), _arms(world)
    msgs = _direct(content, world, "丙", _give(top.id, "兵:2"))[0]
    assert msgs[0] == bounties.GIVEN.format(name="柔劍2", issuer="官軍", title="求兵・屬柔的劍")
    assert {"銀兩 +250", "經驗 +30", "心得 +10", "俠名 +2"} <= set(msgs)  # 50 × 4 × 1.25，淬煉 2 次不加
    assert "銀兩 +88" in _direct(content, world, "丙", _give(mid.id, "兵:3"))[0]  # 35 × 2 × 1.25＝87.5
    assert _load(world, "丙").player.rack == []
    _edit(world, "甲", lambda p: p.rack.append(_blade("兵:7", quality="中品")))
    member = _arms(world)
    msgs = _direct(content, world, "甲", _give(member.id, "兵:7"))[0]
    assert "銀兩 +35" in msgs and not any("俠名" in m for m in msgs)  # 陣營的人交求兵也拿全額（不打 faction_share 的五成）、沒有俠名


def test_handing_in_the_weapon_in_hand_leaves_you_empty_handed(beta_setup):
    """企劃者 2026-10-10（14.1 丙）：手上那把准交，交完空手、鈍了的提醒重設，不自動從裝備庫換一把上手。"""
    content, world = beta_setup
    content.config.weapons.enabled = True

    def armed(p):
        p.weapon, p.edge_warned = _blade("兵:1"), True
        p.rack = [_blade("兵:2", kind="刀")]

    _edit(world, "丙", armed)
    b = _arms(world)
    msgs, game = _direct(content, world, "丙", _give(b.id, "兵:1"))
    p = game.state.player
    assert p.weapon is None and not p.edge_warned and [w.id for w in p.rack] == ["兵:2"]
    assert msgs[-1] == bounties.EMPTY_HANDS


def test_give_checks_everything_again(beta_setup):
    """確認只在網頁那一層，引擎、假人、腳本都不會先問：give 整個重驗（設計 4.4 末段）。"""
    content, world = beta_setup
    good = _fused(world, "烈焰掌")
    _edit(world, "丙", lambda p: p.arts.append(good.id))
    b = _art(world, quota=1)
    assert _direct(content, world, "丙", _give("b999", good.id))[0] == [bounties.GONE]
    _edit(world, "丙", lambda p: setattr(p, "location", "lake"))
    assert _direct(content, world, "丙", _give(b.id, good.id))[0] == [bounties.NOT_NOW]
    _edit(world, "丙", lambda p: setattr(p, "location", "town"))
    assert _direct(content, world, "丙", _give(b.id, good.id))[0][0].startswith(bounties.GIVEN_PREFIX)
    assert _direct(content, world, "丙", _give(b.id, good.id))[0] == [bounties.GONE]  # 名額 1：交滿了


def _open(content, world, name, *picks):
    """打開懸賞榜、照順序按 picks（例如 bounty:pick:b3），回最後的選單（id → Option，照選單的順序）。"""
    for option_id in ("act:bounties", *picks):
        _do(content, world, name, lambda g: g.choose(option_id))
    return _ids(content, world, name)


def test_the_board_lists_hand_ins_first_then_takes_then_one_greyed_line(beta_setup):
    """設計 4.3：交得出的求藝、求兵每張一顆「交出…」排最前面（寫賞、你有幾件合用、期限與名額），再來原本的揭下，交不出的收成一行灰掉的，
    最後「返回」。「懸賞榜（N 張）」的 N 等於列出的張數（灰掉那一行照它包含幾張算）；陣營的人只算自己陣營的，豪強也有自己的可做。"""
    content, world = beta_setup
    content.config.weapons.enabled = True
    good = _fused(world, "烈焰掌")
    _edit(world, "丙", lambda p: p.arts.append(good.id))
    scout = _post(world, kind="scout", faction="guan", silver=10, deeds=2, location="lake")
    art = _art(world)
    _art(world, attribute="柔", faction="huang")
    _arms(world, attribute="快", weapon_kind="槍", faction="haoqiang")
    assert _ids(content, world, "丙")["act:bounties"].label == "懸賞榜（4 張）"
    assert _ids(content, world, "甲")["act:bounties"].label == "懸賞榜（2 張）"
    assert _ids(content, world, "丁")["act:bounties"].label == "懸賞榜（1 張）"  # 地方豪強有自己的求兵（FB-121 第 3 件）
    menu = _open(content, world, "丙")
    assert list(menu) == [f"bounty:pick:{art.id}", f"bounty:take:{scout.id}", "bounty:none", "bounty:back"]
    assert menu[f"bounty:pick:{art.id}"].label == (
        "交出… 官軍・求藝・剛（賞銀 20・經驗 30・心得 20・俠名 +2・素材，偶有兵器；你有 1 門合用；期限 到季末・名額還剩 3）"
    )
    stuck = menu["bounty:none"]
    assert not stuck.enabled and "黃巾・求藝・柔" in stuck.label and "地方豪強・求兵・屬快的槍" in stuck.label
    assert list(_open(content, world, "丁")) == ["bounty:none", "bounty:back"]


def test_picking_lists_the_cheapest_first_with_a_confirm_and_a_way_back(beta_setup):
    """設計 4.4：第三層列合用的、熔掉最不值錢的 give_list 件，每顆先問一次（確認句的心得數就是 library.melt_value，確認層那一顆寫
    「交出」）；多的一行灰掉；身上正在練、對得上的那門灰掉寫原因；最後「回到懸賞榜」。"""
    content, world = beta_setup
    content.config.bounties.give_list = 2
    high, low, mid, worn = (_fused(world, n) for n in ("烈焰掌", "鐵砂掌", "斷金拳", "開碑拳"))

    def library_of(p):
        p.arts = [high.id, low.id, mid.id]
        p.art_levels = {high.id: 7, low.id: 1, mid.id: 5}
        p.member.wugong_id = worn.id

    _edit(world, "丙", library_of)
    art = _art(world)
    menu = _open(content, world, "丙", f"bounty:pick:{art.id}")
    assert list(menu) == [
        f"bounty:give:{art.id}:{low.id}", f"bounty:give:{art.id}:{mid.id}", "bounty:more", f"bounty:give:{art.id}:{worn.id}", "bounty:unpick",
    ]
    first = menu[f"bounty:give:{art.id}:{low.id}"]
    melt = _do(content, world, "丙", lambda g: library.melt_value(g.state, g.content, g.world, low.id))[0]
    assert first.label == f"交出【鐵砂掌】（武學・下品・第1成；熔掉能換 {melt} 心得）"
    assert first.confirm == f"把【鐵砂掌】（下品・第1成）交給官軍？交了就沒了；熔掉的話能換 {melt} 心得。" and first.confirm_yes == "交出"
    assert not menu["bounty:more"].enabled and menu["bounty:more"].label == bounties.MORE["art"].format(n=1)
    stuck = menu[f"bounty:give:{art.id}:{worn.id}"]
    assert not stuck.enabled and stuck.label == bounties.WORN_NOTE.format(name="開碑拳")
    assert menu["bounty:unpick"].label == bounties.UNPICK
    _do(content, world, "丙", lambda g: g.choose("bounty:unpick"))
    assert "bounty:back" in _ids(content, world, "丙") and _load(world, "丙").player.bounty_pick is None


def test_an_arms_id_with_a_colon_works_and_the_weapon_in_hand_can_go(beta_setup):
    """兵器 id「兵:1」帶冒號：交出的選項 id 照 partition 只切一次（設計 4.4）；手上那把列得出來、按得下去，標籤寫實拿的銀兩，
    確認句寫明淬煉不加錢、交了就空手（14.1 丙）。交完回到懸賞榜（第二層）。"""
    content, world = beta_setup
    content.config.weapons.enabled = True
    _edit(world, "丙", lambda p: setattr(p, "weapon", _blade("兵:1", quality="中品", tempers=2)))
    b = _arms(world)
    option = _open(content, world, "丙", f"bounty:pick:{b.id}")[f"bounty:give:{b.id}:兵:1"]
    assert option.label == "交出【柔劍1】（一階中品・鋒利度 100・在手上）→ 賞銀 35"
    assert bounties.TEMPERED_NOTE.format(n=2) in option.confirm and bounties.HELD_NOTE in option.confirm
    msgs, game = _do(content, world, "丙", lambda g: g.choose(f"bounty:give:{b.id}:兵:1"))
    assert msgs[0].startswith(bounties.GIVEN_PREFIX) and game.state.player.weapon is None
    assert game.state.player.bounty_pick is None and "bounty:back" in _ids(content, world, "丙")


def test_a_stale_pick_falls_back_to_the_board(beta_setup):
    """bounty_pick 指的那一張已經交不出了（那一門在修練頁熔掉了）、或下榜了（過了期限、別人先交滿最後一個名額）：當它不存在，
    照第二層畫（設計 4.4），不必另外收；第三層的鈕已經不在選單上，按了只回「（此刻無法這麼做。）」，東西還在（兩個分頁、兩個人搶名額）。"""
    content, world = beta_setup
    good = _fused(world, "烈焰掌")
    _edit(world, "丙", lambda p: p.arts.append(good.id))
    art, last = _art(world), _art(world, quota=1)
    assert "bounty:unpick" in _open(content, world, "丙", f"bounty:pick:{art.id}")
    _edit(world, "丙", lambda p: p.arts.remove(good.id))  # 在修練頁熔掉了
    assert list(_ids(content, world, "丙")) == ["bounty:none", "bounty:back"]
    _edit(world, "丙", lambda p: p.arts.append(good.id))
    world.mutate_season(lambda s: setattr(next(x for x in s.bounties if x.id == art.id), "expires", 0.0))  # 過了期限
    assert list(_ids(content, world, "丙")) == [f"bounty:pick:{last.id}", "bounty:back"]
    _do(content, world, "丙", lambda g: g.choose(f"bounty:pick:{last.id}"))
    world.mutate_season(lambda s: next(x for x in s.bounties if x.id == last.id).done_by.append("乙"))  # 別人先交滿最後一個名額
    assert _do(content, world, "丙", lambda g: g.choose(f"bounty:give:{last.id}:{good.id}"))[0] == ["（此刻無法這麼做。）"]
    assert list(_ids(content, world, "丙")) == ["bounty:empty", "bounty:back"] and good.id in _load(world, "丙").player.arts  # 榜被交光：返回上面多一行灰的說明（FB-156）


def test_opening_picking_and_giving_adds_two_journal_entries(beta_setup):
    """設計 4.8：打開榜一則（「懸賞榜・此地」），挑一件與交出併成一則（「懸賞榜」）；返回照舊一則；下一次再來另起一則，不併進上一次的。"""
    content, world = beta_setup
    good, other = _fused(world, "烈焰掌"), _fused(world, "鐵砂掌")
    _edit(world, "丙", lambda p: p.arts.extend([good.id, other.id]))
    first, second = _art(world), _art(world)
    start = len(_load(world, "丙").journal)
    for b, item in ((first, good.id), (second, other.id)):
        _open(content, world, "丙", f"bounty:pick:{b.id}", f"bounty:give:{b.id}:{item}", "bounty:back")
    journal = _load(world, "丙").journal
    assert len(journal) == start + 6  # 每次三則：打開、挑與交、返回
    handed = journal[1]
    assert handed.title == bounties.BOARD and handed.lines[0] == bounties.pick_line(content, second)
    assert any(line.startswith(bounties.GIVEN_PREFIX) for line in handed.lines)
    assert journal[2].title.startswith(f"{bounties.BOARD}・")


def test_the_card_lists_hand_ins_you_can_make_even_outside_town(beta_setup):
    """設計 4.9：江湖頁的懸賞卡在手上揭了的後面，多列身上有合用東西的求藝、求兵——不看人在哪裡（照 fitting，不照 give_problem）：
    人在城外也列，知道去城鎮交；每一列寫期限與名額、你身上合用的是哪幾件（最不值錢的先寫兩件；兵器寫階品、手上那把寫「在手上」）。
    交不出的、交過的不列。"""
    content, world = beta_setup
    arts = [_fused(world, n) for n in ("烈焰掌", "鐵砂掌", "斷金拳")]
    _edit(world, "丙", lambda p: p.arts.extend(a.id for a in arts))
    art = _art(world)
    _art(world, attribute="柔")
    scout = _post(world, kind="scout", faction="guan", silver=10, deeds=2, location="lake")
    _direct(content, world, "丙", lambda g: bounties.take(g.state, g.content, scout.id))
    _edit(world, "丙", lambda p: setattr(p, "location", "lake"))
    rows = _do(content, world, "丙", lambda g: g.status_data())[0]["bounties"]
    assert [r["id"] for r in rows] == [scout.id, art.id] and "have" not in rows[0]  # 揭了的在前；柔的交不出、不列
    assert rows[1]["title"] == "求藝・剛" and rows[1]["due"] == "期限 到季末・名額還剩 3"
    assert rows[1]["have"] == bounties.HAVE + "【斷金拳】、【烈焰掌】等 3 門"  # 熔煉值一樣，照名字
    assert "act:bounties" not in _ids(content, world, "丙")  # 人在城外：交出只在城鎮的懸賞榜上
    _edit(world, "丙", lambda p: setattr(p, "location", "town"))
    cheapest = _do(content, world, "丙", lambda g: bounties.fitting(g.state, g.content, g.world, art))[0][0]
    _open(content, world, "丙", f"bounty:pick:{art.id}", f"bounty:give:{art.id}:{cheapest}", "bounty:back")
    again = _art(world)
    rows = _do(content, world, "丙", lambda g: g.status_data())[0]["bounties"]
    assert [r["id"] for r in rows] == [scout.id, again.id]  # 交過的那一張不再列
    assert rows[1]["have"] == bounties.HAVE + "【烈焰掌】、【鐵砂掌】"
    content.config.weapons.enabled = True
    _edit(world, "丙", lambda p: setattr(p, "weapon", _blade("兵:1")))
    arms = _arms(world)
    rows = _do(content, world, "丙", lambda g: g.status_data())[0]["bounties"]
    assert [r["id"] for r in rows] == [scout.id, again.id, arms.id]
    assert rows[2]["have"] == bounties.HAVE + "【柔劍1】（一階下品・在手上）"  # 手上那把也算；同名的靠階品分辨


def test_give_choice_names_the_first_hand_in_and_its_cheapest_item_but_not_the_weapon_in_hand(beta_setup):
    """設計 9.1：整季機器人與伺服器假人共用的挑法——此地懸賞榜上第一張交得出的求藝、求兵，與第三層排第一的那一件（最不值錢的），
    不隨機。手上那把兵器不交（交了要空手、少一截威力；真人看得到確認句自己決定）。城外沒有榜：None。"""
    content, world = beta_setup
    content.config.weapons.enabled = True
    high, low = _fused(world, "烈焰掌"), _fused(world, "鐵砂掌")

    def kit(p):
        p.arts, p.art_levels, p.weapon = [high.id, low.id], {high.id: 7}, _blade("兵:1")

    _edit(world, "丙", kit)
    arms, art = _arms(world), _art(world)

    def choice():
        return _do(content, world, "丙", lambda g: bounties.give_choice(g.state, g.content, g.world))[0]

    assert choice() == (art.id, low.id)  # 求兵只對得上手上那把：跳過
    _edit(world, "丙", lambda p: p.rack.append(_blade("兵:2", quality="上品")))
    assert choice() == (arms.id, "兵:2")  # 榜上先掛的先交；手上那把下品更不值錢，照樣不交
    _edit(world, "丙", lambda p: setattr(p, "location", "lake"))
    assert choice() is None


def test_the_season_bot_hands_in_its_cheapest_art_and_never_takes_a_hand_in(beta_setup):
    """設計 9.2：整季機器人路過城鎮時，沒得揭、只有得交也會打開榜，照 give_choice 交最不值錢的那一門，最後收起懸賞榜；
    求藝、求兵不揭（take_problem 擋，不佔 max_taken 的格子）。"""
    content, world = beta_setup
    high, low = _fused(world, "烈焰掌"), _fused(world, "鐵砂掌")

    def kit(p):
        p.arts, p.art_levels = [high.id, low.id], {high.id: 7}

    _edit(world, "丙", kit)
    art = _art(world)
    game = _do(content, world, "丙", lambda g: g)[1]
    bot.take_bounties(game)
    p = game.state.player
    assert p.arts == [high.id] and not p.picking_bounty and p.bounty_pick is None
    board = next(x for x in game.state.world.bounties if x.id == art.id)
    assert board.done_by == ["丙"] and board.takers == []


def test_server_bots_score_only_the_pick_and_the_give_that_give_choice_names(beta_setup):
    """設計 9.3：假人在懸賞榜上只給 give_choice 指的那一張「交出…」與那一件「交出」打分（BOUNTY_SCORE），別的交出不選
    （同分隨機會把最好的那門交掉）；回到懸賞榜、返回是 0。_takeable 認得「交得出」：沒得揭、只有得交也會打開榜。"""
    content, world = beta_setup
    high, low = _fused(world, "烈焰掌"), _fused(world, "鐵砂掌")

    def kit(p):
        p.arts, p.art_levels = [high.id, low.id], {high.id: 7}

    _edit(world, "丙", kit)
    art, other = _art(world), _art(world, faction="huang")
    profile = BotProfile(personality="普通", seed=1, faction=None, season_number=1)
    game = _do(content, world, "丙", lambda g: g)[1]
    assert bot_policy._takeable(game)

    def scores():
        return {o.id: bot_policy.score(game, o, profile) for o in game.options(odds=False) if o.enabled}

    game.choose("act:bounties")
    assert scores() == {f"bounty:pick:{art.id}": bot_policy.BOUNTY_SCORE, f"bounty:pick:{other.id}": None, "bounty:back": 0.0}
    game.choose(f"bounty:pick:{art.id}")
    assert scores() == {
        f"bounty:give:{art.id}:{low.id}": bot_policy.BOUNTY_SCORE, f"bounty:give:{art.id}:{high.id}": None, "bounty:unpick": 0.0,
    }
