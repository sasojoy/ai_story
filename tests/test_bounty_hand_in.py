"""懸賞榜的求藝、求兵（懸賞榜設計第四節、第九節；企劃者 2026-10-10）：官軍、黃巾、地方豪強每週各掛一張求藝、一張求兵，
不用揭、在城鎮的懸賞榜上直接交（交了就沒了），前三個交的有賞；散人三方都能交，陣營的人只交自己陣營的、拿全額。

角色開在同一個資料庫，照伺服器的做法一個動作一次讀存（test_bounties 的 _do、_direct）。"""
from __future__ import annotations

import pytest

from conftest import real_content
from test_bounties import _direct, _do, _load, _post, beta_setup  # noqa: F401  （beta_setup 是 fixture）
from tianxia import bounties, calendar, library
from tianxia.characters import CharacterStore
from tianxia.content import ContentError, validate
from tianxia.martial_arts import generate_from_name
from tianxia.models import WEAPON_KINDS
from tianxia.state import Equipment, GameState, PlayerState, Weapon, WorldState
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
