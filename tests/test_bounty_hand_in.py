"""懸賞榜的求兵（懸賞榜設計第四節、第九節；企劃者 2026-10-10）：官軍、黃巾、地方豪強每週各掛一張求兵，
不用揭、在城鎮的懸賞榜上直接交（交了就沒了），前三個交的有賞；散人三方都能交，陣營的人只交自己陣營的、拿全額。
求藝（交一門合成出來的武學）企劃者 2026-10-21 拿掉（「懸賞榜直接把武學拿掉」）；舊存檔榜上還掛著的求藝讀進來就丟掉（最後兩支）。

角色開在同一個資料庫，照伺服器的做法一個動作一次讀存（test_bounties 的 _do、_direct）。"""
from __future__ import annotations

import pytest

from conftest import real_content
from test_bounties import _direct, _do, _ids, _load, _post, beta_setup  # noqa: F401  （beta_setup 是 fixture）
from tianxia import bot, bot_policy, bounties, calendar
from tianxia.characters import CharacterStore
from tianxia.content import ContentError, validate
from tianxia.engine import Refused
from tianxia.models import WEAPON_KINDS
from tianxia.state import Bounty, BotProfile, Equipment, GameState, PlayerState, Weapon, WorldState
from tianxia.world_state import fresh_season


def _edit(world, name, fn):
    """讀一個角色的存檔、改玩家那一份（fn(player)）、存回去。"""
    state = CharacterStore(world.db).load(name)
    fn(state.player)
    CharacterStore(world.db).save(state)


def _blade(weapon_id, kind="劍", attribute="柔", tier=1, quality="下品", **kw) -> Weapon:
    return Weapon(id=weapon_id, name=f"{attribute}{kind}{weapon_id[-1]}", kind=kind, attribute=attribute, tier=tier, quality=quality, **kw)


def _arms(world, attribute="柔", weapon_kind="劍", faction="guan", quota=3, **kw):
    """貼一張求兵。"""
    return _post(world, kind="arms", faction=faction, silver=0, deeds=2, quota=quota, attribute=attribute, weapon_kind=weapon_kind, **kw)


def _armed(world, name, *rack, weapon=None):
    """兵器開著的測試：name 手上拿 weapon、裝備庫放 rack。"""
    def kit(p):
        p.weapon, p.rack = weapon, list(rack)

    _edit(world, name, kit)


def _issue(content, week=1) -> list:
    """照劇本掛第 week 週的那一批（bounties.issue；兩種季都是它），回整個榜。"""
    state = GameState(player=PlayerState(name="測", location="town", stats={}, stamina=0), world=fresh_season(content))
    state.world.time = calendar.week_start(week, content, state.world)
    bounties.issue(state, content, week)
    return state.world.bounties


def test_each_side_posts_one_arms_bounty_with_attributes_that_do_not_repeat():
    """設計 4.1：劇本的每個陣營（含地方豪強）每期各掛一張求兵；屬性從剛柔快慢挑，同一期三方不重複；另挑種類；
    名額 3、不掛地點，期限同其他懸賞。正式內容（兵器開著）一批 8＋3＝11 張；求藝 2026-10-21 拿掉，一張都不掛。"""
    content = real_content()
    board = _issue(content)
    sides = [f.id for f in content.scenario.factions]
    assert len(board) == 11 and sides == ["guan", "huang", "haoqiang"]
    assert not any(b.kind == "art" for b in board)
    asks = [b for b in board if b.kind == "arms"]
    assert [b.faction for b in asks] == sides
    assert len({b.attribute for b in asks}) == 3 and {b.attribute for b in asks} <= {"剛", "柔", "快", "慢"}
    assert all(b.quota == 3 and b.location is None and b.weapon_kind in WEAPON_KINDS for b in asks)
    assert len({b.expires for b in board}) == 1


def test_fewer_attributes_than_sides_still_posts_for_every_side():
    """give_attributes 比陣營少（只寫兩個）：三方照樣掛得出來（不丟 ValueError），先不重複、多的那一方可以重複（設計 4.1）。"""
    content = real_content()
    content.config.bounties.give_attributes = ["剛", "柔"]
    asks = [b for b in _issue(content) if b.kind == "arms"]
    assert len(asks) == 3 and {asks[0].attribute, asks[1].attribute} == {"剛", "柔"} and asks[2].attribute in ("剛", "柔")


def test_no_arms_bounties_with_weapons_off():
    content = real_content()
    content.config.weapons.enabled = False
    board = _issue(content)
    assert not any(b.kind in bounties.GIVE_KINDS for b in board) and len(board) == 8


def test_the_hand_in_bounties_draw_from_their_own_dice():
    """求兵另開一份亂數（設計 4.1）：同一週的討伐、打探、護送地點跟沒有求兵時一樣。"""
    content = real_content()
    spots = [(b.kind, b.faction, b.location, b.end) for b in _issue(content) if b.kind not in bounties.GIVE_KINDS]
    content.config.bounties.give_kinds = []
    assert [(b.kind, b.faction, b.location, b.end) for b in _issue(content)] == spots


def test_titles_how_and_rewards_name_the_attribute_and_the_weapon_kind():
    """標題寫「求兵・屬柔的劍」（種類照兵器名的字，拳腳寫拳套、弓弩寫弩）；賞那一段照 reward_text：
    陣營的人全額、不寫俠名（設計 4.2、4.7）。"""
    content = real_content()
    arms = next(b for b in _issue(content) if b.kind == "arms")
    fist, crossbow = (arms.model_copy(update={"weapon_kind": k}) for k in ("拳腳", "弓弩"))
    assert bounties.title(content, fist) == f"求兵・屬{arms.attribute}的拳套"  # 種類照 weapons.NOUNS 寫（同兵器名；FB-133）
    assert f"一把屬{arms.attribute}的弩（" in bounties.how(content, crossbow) and "None" not in bounties.how(content, arms)
    loner = GameState(player=PlayerState(name="測", location="town", stats={}, stamina=0), world=WorldState())
    # 名聲（2026-10-15）：散人的功績照走的路記成善名或惡名（善名惡名一樣多算俠，寫善名）
    assert bounties.reward_text(loner, content, arms) == "賞銀 20～50（照品質，高階另加）・經驗 30・心得 10・善名 +2"
    loner.player.faction = arms.faction
    assert bounties.reward_text(loner, content, arms) == "賞銀 20～50（照品質，高階另加）・經驗 30・心得 10"


def test_hand_ins_are_not_taken(beta_setup):
    """求兵不用揭（設計 4.3）：揭了會佔掉 max_taken 的格子、擋掉討伐與打探，整季機器人與假人也會一直揭。"""
    content, world = beta_setup
    arms = _arms(world)
    msgs, _ = _direct(content, world, "丙", lambda g: bounties.take(g.state, g.content, arms.id))
    assert msgs == [bounties.NO_TAKE] and world.get_season().bounties[-1].takers == []


@pytest.mark.parametrize("field, value", [
    ("kinds", ["strike", "raid"]),
    ("give_kinds", ["arms", "armor"]),
    ("give_kinds", ["art", "arms"]),  # 求藝 2026-10-21 拿掉：設定覆寫檔還寫著 art 的，載入時就擋（不默默跳過）
    ("give_kinds", ["arms", "arms"]),  # 照 kinds 的習慣寫兩次是想掛兩張，issue 卻只掛一張：擋下來
    ("give_attributes", []),
    ("give_attributes", ["剛", "土"]),
    ("give_attributes", ["剛", "剛", "柔"]),
    ("arms_silver", {"下品": 20, "中品": 35}),
    ("arms_tier", {"1": 1, "2": 2}),
    # 設定覆寫檔寫 exp／deeds／xinde 是整張字典換掉：少寫 arms 的賞，掛得出來、交得了，領到的卻默默是 0（用 .get(kind, 0)）
    ("exp", {"strike": 15, "scout": 10, "escort": 12, "wanted": 15}),
    ("deeds", {"strike": 3, "scout": 2, "escort": 2, "wanted": 4}),
    ("xinde", {}),
])
def test_validate_checks_the_bounty_settings(content, field, value):
    """設計 4.1 末段：認不得的種類（以前 issue 默默跳過）、挑不到屬性、求兵的價錢少一個品質或一個階（交那一把會 KeyError），載入時就擋；
    give_kinds、give_attributes 重複也擋（審查補的）；give_kinds 裡的每一種，賞的字典（經驗、俠名、心得）都要寫它的那一項。"""
    setattr(content.config.bounties, field, value)
    with pytest.raises(ContentError, match=f"Config.bounties.{field}"):
        validate(content)


def test_validate_requires_the_hand_in_rewards_only_for_the_kinds_that_are_hung(content):
    """賞的字典缺哪一項，只看 give_kinds 有沒有掛那一種：預設的內容（測試內容與正式內容）照樣通過；
    不掛求兵（give_kinds 清空，同 measure_sanren 的 --no-give）時，缺求兵的賞不擋。
    銀兩是例外：求兵的銀兩走 arms_silver × arms_tier，silver 本來就沒有 arms 這一項。"""
    validate(content)
    validate(real_content())
    cfg = content.config.bounties
    assert cfg.give_kinds == ["arms"] and "arms" not in cfg.silver and "arms" in set(cfg.exp) & set(cfg.deeds) & set(cfg.xinde)
    assert not any("art" in d for d in (cfg.silver, cfg.exp, cfg.deeds, cfg.xinde))  # 求藝的賞跟著拿掉
    cfg.give_kinds = []
    cfg.exp, cfg.deeds = ({k: v for k, v in d.items() if k != "arms"} for d in (cfg.exp, cfg.deeds))
    cfg.silver, cfg.xinde = {}, {}
    validate(content)


def test_what_fits_an_arms_bounty_including_the_one_in_hand(beta_setup):
    """設計 4.5 第 3～7 條：種類與屬性都要對、什麼品質都收；手上那把也收（企劃者 2026-10-10，14.1 丙），空手時交裝備庫裡的也行；
    最不值錢的排前面（賞銀的底數、鋒利度；PM 2026-10-12，順序另有 test_arms_are_listed_by_payout_base…）；不是求兵的、別的陣營的、
    交過的不行。fit_problem 只看東西合不合這一張，不看人在哪裡。兵器關著一律不收。"""
    content, world = beta_setup
    content.config.weapons.enabled = True
    arms = _arms(world)
    _armed(world, "丙", _blade("兵:2", quality="上品", tier=2), _blade("兵:3", kind="刀"), _blade("兵:4", attribute="剛"),
           _blade("兵:5", edge=40), weapon=_blade("兵:1", quality="中品"))
    ids = ["兵:1", "兵:2", "兵:3", "兵:4", "兵:5", "兵:9"]
    problems = _do(content, world, "丙", lambda g: [bounties.fit_problem(g.state, g.content, g.world, arms, i) for i in ids])[0]
    wrong = bounties.WANT_ARMS.format(attribute="柔", noun="劍")
    assert problems == [None, None, wrong, wrong, None, bounties.NO_WEAPON]
    assert _do(content, world, "丙", lambda g: bounties.fitting(g.state, g.content, g.world, arms))[0] == ["兵:5", "兵:1", "兵:2"]
    scout = _post(world, kind="scout", faction="guan", silver=10, deeds=2, location="lake")
    done = _arms(world, faction="huang", done_by=["丙"])
    assert _do(content, world, "丙", lambda g: bounties.fit_problem(g.state, g.content, g.world, scout, "兵:1"))[0] == bounties.NOT_NOW
    assert _do(content, world, "丙", lambda g: bounties.fit_problem(g.state, g.content, g.world, done, "兵:1"))[0] == bounties.GIVEN_BEFORE
    _armed(world, "甲", _blade("兵:6"))
    theirs = _arms(world, faction="huang")
    assert _do(content, world, "甲", lambda g: bounties.fit_problem(g.state, g.content, g.world, theirs, "兵:6"))[0] == bounties.NOT_YOURS
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


def test_a_divine_original_is_never_offered_to_an_arms_bounty(beta_setup):
    """打造隱藏配方設計 5.4：神器原品不能交求兵（手上那把也不收：一季全服只有一把，交了就上不了神器譜）；仿品照一般兵器收。"""
    content, world = beta_setup
    content.config.weapons.enabled = True
    arms = _arms(world, attribute="剛")

    def armed(p):
        p.weapon = _blade("兵:1", attribute="剛", tier=3, quality="上品", original=True, secret="t_star")
        p.rack = [_blade("兵:2", attribute="剛", tier=3, quality="上品", copy_of="鑄|t_star", secret="t_star")]

    _edit(world, "丙", armed)
    problems = _do(content, world, "丙", lambda g: [bounties.fit_problem(g.state, g.content, g.world, arms, i) for i in ("兵:1", "兵:2")])[0]
    assert problems == [bounties.ORIGINAL_KEPT, None]
    assert _do(content, world, "丙", lambda g: bounties.fitting(g.state, g.content, g.world, arms))[0] == ["兵:2"]


def test_a_signature_arm_is_never_offered_to_an_arms_bounty(beta_setup):
    """打造第三批：名將本命兵器同神器原品，交不得求兵（手上那把也不收），原因寫它自己的。"""
    content, world = beta_setup
    content.config.weapons.enabled = True
    arms = _arms(world, attribute="快", weapon_kind="槍")
    _edit(world, "丙", lambda p: setattr(p, "weapon", _blade("兵:1", kind="槍", attribute="快", tier=3, quality="上品",
                                                              original=True, signature="sunjian")))
    problems = _do(content, world, "丙", lambda g: [bounties.fit_problem(g.state, g.content, g.world, arms, "兵:1")])[0]
    assert problems == [bounties.SIGNATURE_KEPT]


def test_giving_also_needs_the_board_here_and_the_bounty_still_up(beta_setup):
    """設計 4.5 第 1、2 條：give_problem 另看懸賞榜看不看得到、這一張還在不在榜上（過期、名額滿）；fit_problem 不看，所以城外的卡片照樣列。"""
    content, world = beta_setup
    content.config.weapons.enabled = True
    _armed(world, "丙", _blade("兵:2"))
    arms, full, late = _arms(world), _arms(world, quota=1, done_by=["乙"]), _arms(world, expires=0.0)

    def check(g, b):
        return bounties.give_problem(g.state, g.content, g.world, b, "兵:2")

    assert _do(content, world, "丙", lambda g: [check(g, b) for b in (arms, full, late)])[0] == [None, bounties.GONE, bounties.GONE]
    _edit(world, "丙", lambda p: setattr(p, "location", "lake"))
    assert _do(content, world, "丙", lambda g: check(g, arms))[0] == bounties.NOT_NOW
    assert _do(content, world, "丙", lambda g: bounties.fitting(g.state, g.content, g.world, arms))[0] == ["兵:2"]


def _give(bounty_id, item_id):
    """交出（bounties.give，直接呼叫；選單那一條路在後面測）。"""
    return lambda g: bounties.give(g.state, g.content, g.world, bounty_id, item_id)


def test_loners_and_faction_members_get_full_pay_and_only_loners_add_deeds(beta_setup):
    """設計 4.7：陣營的人也拿全額（不打 faction_share 的五成），散人另記俠名；兩邊都不記貢獻。前三個交的有賞、一人一次。"""
    content, world = beta_setup
    content.config.weapons.enabled = True
    _armed(world, "丙", _blade("兵:1"))
    _armed(world, "甲", _blade("兵:7"))
    b = _arms(world)
    loner = _direct(content, world, "丙", _give(b.id, "兵:1"))[0]
    member = _direct(content, world, "甲", _give(b.id, "兵:7"))[0]
    for msgs in (loner, member):
        assert {"銀兩 +20", "經驗 +30", "心得 +10"} <= set(msgs)
    assert "俠名 +2" in loner and not any("俠名" in m for m in member)
    assert _load(world, "丙").player.ranger_deeds == 2 and _load(world, "甲").player.contrib == 0
    assert _load(world, "甲").player.bounties_done == _load(world, "丙").player.bounties_done == 1
    board = next(x for x in world.get_season().bounties if x.id == b.id)
    assert board.done_by == ["丙", "甲"] and board.takers == []


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
    content.config.weapons.enabled = True
    _armed(world, "丙", _blade("兵:2"), _blade("兵:3"))
    b = _arms(world, quota=1)
    assert _direct(content, world, "丙", _give("b999", "兵:2"))[0] == [bounties.GONE]
    _edit(world, "丙", lambda p: setattr(p, "location", "lake"))
    assert _direct(content, world, "丙", _give(b.id, "兵:2"))[0] == [bounties.NOT_NOW]
    _edit(world, "丙", lambda p: setattr(p, "location", "town"))
    assert _direct(content, world, "丙", _give(b.id, "兵:2"))[0][0].startswith(bounties.GIVEN_PREFIX)
    assert _direct(content, world, "丙", _give(b.id, "兵:3"))[0] == [bounties.GONE]  # 名額 1：交滿了


def _open(content, world, name, *picks):
    """打開懸賞榜、照順序按 picks（例如 bounty:pick:b3），回最後的選單（id → Option，照選單的順序）。"""
    for option_id in ("act:bounties", *picks):
        _do(content, world, name, lambda g: g.choose(option_id))
    return _ids(content, world, name)


def test_the_greyed_line_says_when_only_a_divine_original_fits(beta_setup):
    """FB-145：身上只有神器原品對得上某張求兵時（拿在手上、放在裝備庫都一樣），灰掉那一行在那一張後面照實寫原品交不得，
    不是只有一句籠統的「求兵要種類與屬性都對得上的兵器」；別張照舊。打了一把仿品之後那一張就交得出、不在灰的那一行裡。"""
    content, world = beta_setup
    content.config.weapons.enabled = True
    arms = _arms(world, attribute="快", weapon_kind="弓弩", faction="haoqiang")
    other = _arms(world, attribute="柔", weapon_kind="槍", faction="haoqiang")
    original = _blade("兵:1", kind="弓弩", attribute="快", tier=3, quality="上品", original=True, secret="wd_chase_lightning")
    for place in ("rack", "weapon"):
        _edit(world, "丁", lambda p: (setattr(p, "weapon", original), setattr(p, "rack", [])) if place == "weapon"
              else (setattr(p, "weapon", None), setattr(p, "rack", [original])))
        label = _open(content, world, "丁")["bounty:none"].label
        kept = f"{bounties.issuer(content, arms)}・{bounties.title(content, arms)}{bounties.ONLY_ORIGINAL}"
        assert kept in label, label
        assert f"{bounties.issuer(content, other)}・{bounties.title(content, other)}{bounties.ONLY_ORIGINAL}" not in label
        _do(content, world, "丁", lambda g: g.choose("bounty:back"))
    _edit(world, "丁", lambda p: p.rack.append(_blade("兵:2", kind="弓弩", attribute="快", tier=3, quality="上品",
                                                       copy_of="鑄|wd_chase_lightning", secret="wd_chase_lightning")))
    menu = _open(content, world, "丁")
    assert f"bounty:pick:{arms.id}" in menu and bounties.ONLY_ORIGINAL not in menu["bounty:none"].label


def test_the_greyed_line_names_a_signature_arm_when_it_is_all_that_fits(beta_setup):
    """打造第三批：身上對得上某張求兵的只有名將的本命兵器時，灰掉那一行寫本命兵器交不得（不是神器原品那一句）；
    同時還有一把神器原品對得上，就說原品（兩樣都交不得，原品是比較常見的那一種原因）。"""
    content, world = beta_setup
    content.config.weapons.enabled = True
    arms = _arms(world, attribute="快", weapon_kind="槍", faction="haoqiang")
    signature = _blade("兵:1", kind="槍", attribute="快", tier=3, quality="上品", original=True, signature="sunjian")
    _edit(world, "丁", lambda p: (setattr(p, "weapon", signature), setattr(p, "rack", [])))
    tail = f"{bounties.issuer(content, arms)}・{bounties.title(content, arms)}"
    label = _open(content, world, "丁")["bounty:none"].label
    assert tail + bounties.ONLY_SIGNATURE in label and bounties.ONLY_ORIGINAL not in label
    assert _do(content, world, "丁", lambda g: [bounties.only_original(g.state, arms)])[0] == [bounties.ONLY_SIGNATURE]
    _do(content, world, "丁", lambda g: g.choose("bounty:back"))
    _edit(world, "丁", lambda p: p.rack.append(_blade("兵:2", kind="槍", attribute="快", tier=3, quality="上品",
                                                       original=True, secret="wd_chase_lightning")))
    label = _open(content, world, "丁")["bounty:none"].label
    assert tail + bounties.ONLY_ORIGINAL in label and bounties.ONLY_SIGNATURE not in label
    assert _do(content, world, "丁", lambda g: [bounties.only_original(g.state, arms)])[0] == [bounties.ONLY_ORIGINAL]
    _edit(world, "丁", lambda p: setattr(p, "weapon", _blade("兵:3", kind="劍", attribute="柔")))  # 手上換成配不上的，庫裡的神器原品還在
    assert _do(content, world, "丁", lambda g: [bounties.only_original(g.state, arms)])[0] == [bounties.ONLY_ORIGINAL]
    _edit(world, "丁", lambda p: setattr(p, "rack", []))
    assert _do(content, world, "丁", lambda g: [bounties.only_original(g.state, arms)])[0] == [""]  # 都沒有對得上的：不是這一種原因


def test_the_board_lists_hand_ins_first_then_takes_then_one_greyed_line(beta_setup):
    """設計 4.3：交得出的求兵每張一顆「交出…」排最前面（寫賞、你有幾件合用、期限與名額），再來原本的揭下，交不出的收成一行灰掉的，
    最後「返回」。「懸賞榜（N 張）」的 N 等於列出的張數（灰掉那一行照它包含幾張算）；陣營的人只算自己陣營的，豪強也有自己的可做。"""
    content, world = beta_setup
    content.config.weapons.enabled = True
    _armed(world, "丙", _blade("兵:2"))
    scout = _post(world, kind="scout", faction="guan", silver=10, deeds=2, location="lake")
    arms = _arms(world)
    _arms(world, attribute="剛", faction="huang")
    _arms(world, attribute="快", weapon_kind="槍", faction="haoqiang")
    assert _ids(content, world, "丙")["act:bounties"].label == "懸賞榜（4 張）"
    assert _ids(content, world, "甲")["act:bounties"].label == "懸賞榜（2 張）"
    assert _ids(content, world, "丁")["act:bounties"].label == "懸賞榜（1 張）"  # 地方豪強有自己的求兵（FB-121 第 3 件）
    menu = _open(content, world, "丙")
    assert list(menu) == [f"bounty:pick:{arms.id}", f"bounty:take:{scout.id}", "bounty:none", "bounty:back"]
    assert menu[f"bounty:pick:{arms.id}"].label == (
        "交出… 官軍・求兵・屬柔的劍（賞銀 20～50（照品質，高階另加）・經驗 30・心得 10・俠名 +2；你有 1 把合用；期限 到季末・名額還剩 3）"
    )
    stuck = menu["bounty:none"]
    assert not stuck.enabled and "黃巾・求兵・屬剛的劍" in stuck.label and "地方豪強・求兵・屬快的槍" in stuck.label
    assert "求藝" not in stuck.label
    assert list(_open(content, world, "丁")) == ["bounty:none", "bounty:back"]


def test_picking_lists_the_cheapest_first_with_a_confirm_and_a_way_back(beta_setup):
    """設計 4.4：第三層列合用的、最不值錢的 give_list 件，每顆先問一次（確認層那一顆寫「交出」）；多的一行灰掉；
    最後「回到懸賞榜」。"""
    content, world = beta_setup
    content.config.weapons.enabled = True
    content.config.bounties.give_list = 2
    _armed(world, "丙", _blade("兵:2", tier=3), _blade("兵:3", quality="中品"), _blade("兵:4", quality="中品", edge=40))
    b = _arms(world)
    menu = _open(content, world, "丙", f"bounty:pick:{b.id}")
    assert list(menu) == [f"bounty:give:{b.id}:兵:4", f"bounty:give:{b.id}:兵:3", "bounty:more", "bounty:unpick"]
    first = menu[f"bounty:give:{b.id}:兵:4"]
    assert first.label == "交出【柔劍4】（一階中品・鋒利度 40）→ 賞銀 35"
    assert first.confirm == "把【柔劍4】（一階中品）交給官軍？交了就沒了。" and first.confirm_yes == "交出"
    assert not menu["bounty:more"].enabled and menu["bounty:more"].label == bounties.MORE.format(n=1, unit="把")
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
    assert bounties.TEMPERED_NOTE.format(n=2) in option.confirm and bounties.HELD_NOTE.format(unit="把") in option.confirm
    msgs, game = _do(content, world, "丙", lambda g: g.choose(f"bounty:give:{b.id}:兵:1"))
    assert msgs[0].startswith(bounties.GIVEN_PREFIX) and game.state.player.weapon is None
    assert game.state.player.bounty_pick is None and "bounty:back" in _ids(content, world, "丙")


def test_arms_are_listed_by_payout_base_so_a_tier_one_mid_goes_before_a_tier_three_low(beta_setup):
    """PM 2026-10-12：求兵「最不值錢的先」照賞銀的底數（arms_silver[品質] × arms_tier[階]）、鋒利度、id，不照品質優先——
    三階下品（20×4＝80）比一階中品（35×1＝35）值錢，不能排在前面先被交掉。fitting、第三層的交出鈕、give_choice（整季機器人與
    假人共用）排的是同一個順序；底數一樣時鋒利度低的先。"""
    content, world = beta_setup
    content.config.weapons.enabled = True

    def armed(p):
        p.rack = [_blade("兵:2", tier=3, quality="下品"), _blade("兵:3", quality="中品"), _blade("兵:4", quality="中品", edge=40)]

    _edit(world, "丙", armed)
    b = _arms(world)
    assert _do(content, world, "丙", lambda g: bounties.fitting(g.state, g.content, g.world, b))[0] == ["兵:4", "兵:3", "兵:2"]
    menu = _open(content, world, "丙", f"bounty:pick:{b.id}")
    gives = [o for o in menu.values() if o.id.startswith("bounty:give:")]
    assert [o.id for o in gives] == [f"bounty:give:{b.id}:{i}" for i in ("兵:4", "兵:3", "兵:2")]
    assert [o.label for o in gives] == [
        "交出【柔劍4】（一階中品・鋒利度 40）→ 賞銀 35",
        "交出【柔劍3】（一階中品・鋒利度 100）→ 賞銀 35",
        "交出【柔劍2】（三階下品・鋒利度 100）→ 賞銀 80",
    ]
    assert _do(content, world, "丙", lambda g: bounties.give_choice(g.state, g.content, g.world))[0] == (b.id, "兵:4")


def test_a_stale_pick_falls_back_to_the_board(beta_setup):
    """bounty_pick 指的那一張已經交不出了（那一把在鐵匠鋪拆掉了）、或下榜了（過了期限、別人先交滿最後一個名額）：當它不存在，
    照第二層畫（設計 4.4），不必另外收；第三層的鈕已經不在選單上，按了回為什麼不成，東西還在（兩個分頁、兩個人搶名額）。"""
    content, world = beta_setup
    content.config.weapons.enabled = True
    blade = _blade("兵:2")
    _armed(world, "丙", blade)
    arms, last = _arms(world), _arms(world, quota=1)
    assert "bounty:unpick" in _open(content, world, "丙", f"bounty:pick:{arms.id}")
    _edit(world, "丙", lambda p: setattr(p, "rack", []))  # 在鐵匠鋪拆掉了
    assert list(_ids(content, world, "丙")) == ["bounty:none", "bounty:back"]
    _armed(world, "丙", blade)
    world.mutate_season(lambda s: setattr(next(x for x in s.bounties if x.id == arms.id), "expires", 0.0))  # 過了期限
    assert list(_ids(content, world, "丙")) == [f"bounty:pick:{last.id}", "bounty:back"]
    _do(content, world, "丙", lambda g: g.choose(f"bounty:pick:{last.id}"))
    world.mutate_season(lambda s: next(x for x in s.bounties if x.id == last.id).done_by.append("乙"))  # 別人先交滿最後一個名額
    # FB-162：慢的那一頁不再只得到一句「（此刻無法這麼做。）」，而是這一張為什麼交不了（下榜了）
    assert _do(content, world, "丙", lambda g: g.choose(f"bounty:give:{last.id}:兵:2"))[0] == [bounties.GONE]
    # 榜被交光：返回上面多一行灰的說明（FB-156）
    assert list(_ids(content, world, "丙")) == ["bounty:empty", "bounty:back"] and [w.id for w in _load(world, "丙").player.rack] == ["兵:2"]


def _two_tabs(content, world):
    """兩個分頁搶同一張（FB-162）：丙有兩把合用的兵器，同一張求兵，兩個分頁都停在第三層。回（懸賞, 甲兵器 id, 乙兵器 id）。"""
    content.config.weapons.enabled = True
    _armed(world, "丙", _blade("兵:2"), _blade("兵:3"))
    b = _arms(world)
    _open(content, world, "丙", f"bounty:pick:{b.id}")
    return b, "兵:2", "兵:3"


def test_the_slower_tab_hears_why_it_cannot_hand_in_anymore_and_nothing_is_written_fb162(beta_setup):
    """FB-162：分頁 A 先交掉，分頁 B 再按「交出」（B 的畫面還停在第三層，選項已經不在選單上）：引擎回這一步為什麼不成的那一句
    （bounties.give_problem 的原因：這一張你已經交過了），回傳值是 Refused（伺服器照它把同一句傳去網頁）；不扣不給、不寫江湖紀錄。"""
    content, world = beta_setup
    b, good, other = _two_tabs(content, world)
    assert _do(content, world, "丙", lambda g: g.choose(f"bounty:give:{b.id}:{good}"))[0][0].startswith(bounties.GIVEN_PREFIX)
    after = _load(world, "丙")
    start, silver = len(after.journal), after.player.stats["silver"]
    for item in (good, other):  # 交掉的那一把、還在庫裡的另一把都一樣：這一張你已經交過了
        msgs, game = _do(content, world, "丙", lambda g, item=item: g.choose(f"bounty:give:{b.id}:{item}"))
        assert msgs == [bounties.GIVEN_BEFORE] and isinstance(msgs, Refused)
    again = _load(world, "丙")
    assert len(again.journal) == start and again.player.stats["silver"] == silver and [w.id for w in again.player.rack] == [other]
    assert [x.takers for x in world.get_season().bounties if x.id == b.id] == [[]]


def test_a_hand_in_whose_item_is_gone_says_the_item_is_gone_fb162(beta_setup):
    """另一個分頁在鐵匠鋪把那一把拆掉了（榜還開著、這一張還在）：說裝備庫裡沒有這一件，不是籠統的一句。"""
    content, world = beta_setup
    b, good, other = _two_tabs(content, world)
    _edit(world, "丙", lambda p: setattr(p, "rack", [w for w in p.rack if w.id != good]))
    msgs, game = _do(content, world, "丙", lambda g: g.choose(f"bounty:give:{b.id}:{good}"))
    assert msgs == [bounties.NO_WEAPON] and isinstance(msgs, Refused)


def test_a_stale_option_with_no_reason_of_its_own_gets_the_general_line_fb162(beta_setup):
    """分頁 A 按了「回到懸賞榜」，分頁 B 還停在第三層按「交出」：東西沒問題、這一張也還在，只是選項不在選單上——沒有別的原因可說，
    回 bounties.STALE（榜上的情形變了）；擠不進選單的 take／pick／drop 也一樣，找不到那一張的說下榜了。"""
    content, world = beta_setup
    b, good, _ = _two_tabs(content, world)
    _do(content, world, "丙", lambda g: g.choose("bounty:unpick"))
    for option_id in (f"bounty:give:{b.id}:{good}", f"bounty:drop:{b.id}", f"bounty:take:{b.id}"):
        msgs, game = _do(content, world, "丙", lambda g, option_id=option_id: g.choose(option_id))
        assert msgs == [bounties.STALE] and isinstance(msgs, Refused), option_id
    for option_id in ("bounty:pick:b999", "bounty:give:b999:x"):
        assert _do(content, world, "丙", lambda g, option_id=option_id: g.choose(option_id))[0] == [bounties.GONE]


def test_only_a_missing_bounty_option_gets_the_new_line_fb162(beta_setup):
    """範圍：不是懸賞的選項不在選單上，照舊「（此刻無法這麼做。）」、不是 Refused；在選單上、只是灰著的懸賞選項（bounty:empty）也照舊
    （tests/test_bounties.py）；在選單上的真選項回一般的清單。"""
    content, world = beta_setup
    b, good, _ = _two_tabs(content, world)
    _do(content, world, "丙", lambda g: g.choose("bounty:unpick"))
    msgs, game = _do(content, world, "丙", lambda g: g.choose("act:nonsense"))
    assert msgs == [bounties.NOT_NOW] and not isinstance(msgs, Refused)

    def twice(g):
        first = g.choose(f"bounty:give:{b.id}:{good}")
        second = g.choose("bounty:back")  # 這一下是真的、在選單上：回話不是拒絕
        return first, second

    (first, second), _ = _do(content, world, "丙", twice)
    assert first == [bounties.STALE] and isinstance(first, Refused) and second == ["你離開了懸賞榜。"] and not isinstance(second, Refused)


def test_opening_picking_and_giving_adds_two_journal_entries(beta_setup):
    """設計 4.8（FB-161 改過）：打開榜一則（「懸賞榜・此地」），挑一件不寫紀錄、交出一則（「懸賞榜」）；返回照舊一則；
    下一次再來另起一則，不併進上一次的。"""
    content, world = beta_setup
    content.config.weapons.enabled = True
    _armed(world, "丙", _blade("兵:2"), _blade("兵:3"))
    first, second = _arms(world), _arms(world)
    start = len(_load(world, "丙").journal)
    for b, item in ((first, "兵:2"), (second, "兵:3")):
        _open(content, world, "丙", f"bounty:pick:{b.id}", f"bounty:give:{b.id}:{item}", "bounty:back")
    journal = _load(world, "丙").journal
    assert len(journal) == start + 6  # 每次三則：打開、交出、返回（挑一件不寫）
    handed = journal[1]
    assert handed.title == bounties.BOARD and handed.lines[0].startswith(bounties.GIVEN_PREFIX)
    assert bounties.pick_line(content, second) not in handed.lines
    assert journal[2].title.startswith(f"{bounties.BOARD}・")


def test_each_hand_in_gets_its_own_entry_and_browsing_writes_none(beta_setup):
    """FB-161：同一次逛榜連交兩張，各一則、各寫各的得失（以前挑了又回的句子全留著，兩張的賞加總成一筆，分不出哪一張給了多少）；
    挑一件、回到懸賞榜只是翻頁，不寫紀錄。"""
    content, world = beta_setup
    content.config.weapons.enabled = True
    _armed(world, "丙", _blade("兵:2"), _blade("兵:3"))
    first, second = _arms(world), _arms(world)
    start = len(_load(world, "丙").journal)
    _open(content, world, "丙", f"bounty:pick:{first.id}", "bounty:unpick", f"bounty:pick:{second.id}", "bounty:unpick",
          f"bounty:pick:{first.id}", f"bounty:give:{first.id}:兵:2", f"bounty:pick:{second.id}", f"bounty:give:{second.id}:兵:3")
    journal = _load(world, "丙").journal
    assert len(journal) == start + 3  # 打開、交第一張、交第二張
    second_in, first_in, opened = journal[0], journal[1], journal[2]
    assert opened.title.startswith(f"{bounties.BOARD}・")
    for entry in (first_in, second_in):
        assert entry.title == bounties.BOARD and entry.lines[0].startswith(bounties.GIVEN_PREFIX)
        assert not any(bounties.is_browse_line(line) for line in entry.lines)
        assert "銀兩 +20" in entry.changes  # 一張的賞，不是兩張加總


def test_the_card_lists_hand_ins_you_can_make_even_outside_town(beta_setup):
    """設計 4.9：江湖頁的懸賞卡在手上揭了的後面，多列身上有合用兵器的求兵——不看人在哪裡（照 fitting，不照 give_problem）：
    人在城外也列，知道去城鎮交；每一列寫期限與名額、你身上合用的是哪幾件（最不值錢的先寫兩件；寫階品、手上那把寫「在手上」）。
    交不出的、交過的不列。"""
    content, world = beta_setup
    content.config.weapons.enabled = True
    _armed(world, "丙", _blade("兵:2"), _blade("兵:3", quality="中品"), _blade("兵:4", quality="上品"))
    arms = _arms(world)
    _arms(world, attribute="剛")
    scout = _post(world, kind="scout", faction="guan", silver=10, deeds=2, location="lake")
    _direct(content, world, "丙", lambda g: bounties.take(g.state, g.content, scout.id))
    _edit(world, "丙", lambda p: setattr(p, "location", "lake"))
    rows = _do(content, world, "丙", lambda g: g.status_data())[0]["bounties"]
    assert [r["id"] for r in rows] == [scout.id, arms.id] and "have" not in rows[0]  # 揭了的在前；剛的交不出、不列
    assert rows[1]["title"] == "求兵・屬柔的劍" and rows[1]["due"] == "期限 到季末・名額還剩 3"
    assert rows[1]["have"] == bounties.HAVE + "【柔劍2】（一階下品）、【柔劍3】（一階中品）等 3 把"
    assert "act:bounties" not in _ids(content, world, "丙")  # 人在城外：交出只在城鎮的懸賞榜上
    _edit(world, "丙", lambda p: setattr(p, "location", "town"))
    _open(content, world, "丙", f"bounty:pick:{arms.id}", f"bounty:give:{arms.id}:兵:2", "bounty:back")
    again = _arms(world)
    rows = _do(content, world, "丙", lambda g: g.status_data())[0]["bounties"]
    assert [r["id"] for r in rows] == [scout.id, again.id]  # 交過的那一張不再列
    assert rows[1]["have"] == bounties.HAVE + "【柔劍3】（一階中品）、【柔劍4】（一階上品）"
    _edit(world, "丙", lambda p: setattr(p, "weapon", _blade("兵:1")))
    rows = _do(content, world, "丙", lambda g: g.status_data())[0]["bounties"]
    assert rows[1]["have"] == bounties.HAVE + "【柔劍1】（一階下品・在手上）、【柔劍3】（一階中品）等 3 把"  # 手上那把也算；同名的靠階品分辨


def test_give_choice_names_the_first_hand_in_and_its_cheapest_item_but_not_the_weapon_in_hand(beta_setup):
    """設計 9.1：整季機器人與伺服器假人共用的挑法——此地懸賞榜上第一張交得出的求兵，與第三層排第一的那一件（最不值錢的），
    不隨機。手上那把兵器不交（交了要空手、少一截威力；真人看得到確認句自己決定）。城外沒有榜：None。"""
    content, world = beta_setup
    content.config.weapons.enabled = True
    _armed(world, "丙", weapon=_blade("兵:1"))
    arms = _arms(world)
    _arms(world, faction="huang")

    def choice():
        return _do(content, world, "丙", lambda g: bounties.give_choice(g.state, g.content, g.world))[0]

    assert choice() is None  # 只對得上手上那把：跳過
    _edit(world, "丙", lambda p: p.rack.append(_blade("兵:2", quality="上品")))
    assert choice() == (arms.id, "兵:2")  # 榜上先掛的先交；手上那把下品更不值錢，照樣不交
    _edit(world, "丙", lambda p: setattr(p, "location", "lake"))
    assert choice() is None


def test_the_season_bot_hands_in_its_cheapest_weapon_and_never_takes_a_hand_in(beta_setup):
    """設計 9.2：整季機器人路過城鎮時，沒得揭、只有得交也會打開榜，照 give_choice 交最不值錢的那一把，最後收起懸賞榜；
    求兵不揭（take_problem 擋，不佔 max_taken 的格子）。"""
    content, world = beta_setup
    content.config.weapons.enabled = True
    _armed(world, "丙", _blade("兵:2"), _blade("兵:3", quality="上品"))
    arms = _arms(world)
    game = _do(content, world, "丙", lambda g: g)[1]
    bot.take_bounties(game)
    p = game.state.player
    assert [w.id for w in p.rack] == ["兵:3"] and not p.picking_bounty and p.bounty_pick is None
    board = next(x for x in game.state.world.bounties if x.id == arms.id)
    assert board.done_by == ["丙"] and board.takers == []


def test_server_bots_score_only_the_pick_and_the_give_that_give_choice_names(beta_setup):
    """設計 9.3：假人在懸賞榜上只給 give_choice 指的那一張「交出…」與那一件「交出」打分（BOUNTY_SCORE），別的交出不選
    （同分隨機會把最好的那把交掉）；回到懸賞榜、返回是 0。_takeable 認得「交得出」：沒得揭、只有得交也會打開榜。"""
    content, world = beta_setup
    content.config.weapons.enabled = True
    _armed(world, "丙", _blade("兵:2"), _blade("兵:3", quality="上品"))
    arms, other = _arms(world), _arms(world, faction="huang")
    profile = BotProfile(personality="普通", seed=1, faction=None, season_number=1)
    game = _do(content, world, "丙", lambda g: g)[1]
    assert bot_policy._takeable(game)

    def scores():
        return {o.id: bot_policy.score(game, o, profile) for o in game.options(odds=False) if o.enabled}

    game.choose("act:bounties")
    assert scores() == {f"bounty:pick:{arms.id}": bot_policy.BOUNTY_SCORE, f"bounty:pick:{other.id}": None, "bounty:back": 0.0}
    game.choose(f"bounty:pick:{arms.id}")
    assert scores() == {
        f"bounty:give:{arms.id}:兵:2": bot_policy.BOUNTY_SCORE, f"bounty:give:{arms.id}:兵:3": None, "bounty:unpick": 0.0,
    }


def _old_art_bounty(bounty_id: str) -> dict:
    """2026-10-21 之前的存檔裡掛著的一張求藝（kind "art"），照當時寫進資料庫的樣子。"""
    return {"id": bounty_id, "kind": "art", "faction": "guan", "week": 1, "expires": 1e12, "silver": 20, "deeds": 2,
            "quota": 3, "attribute": "剛", "done_by": ["乙"]}


def test_an_old_season_with_art_bounties_reads_without_them():
    """求藝企劃者 2026-10-21 拿掉：舊存檔的季裡還掛著的求藝，讀進來就丟掉（state.WorldState._drop_retired_bounties），別的單照舊。"""
    scout = {"id": "b1", "kind": "scout", "faction": "guan", "week": 1, "expires": 1e12, "silver": 10, "deeds": 2, "location": "lake"}
    season = WorldState.model_validate({"bounties": [scout, _old_art_bounty("b2")], "bounty_seq": 2})
    assert [b.id for b in season.bounties] == ["b1"] and season.bounty_seq == 2
    again = WorldState.model_validate_json(WorldState(bounties=[Bounty(**scout), Bounty(**_old_art_bounty("b2"))]).model_dump_json())
    assert [b.kind for b in again.bounties] == ["scout"]


def test_a_player_stuck_on_an_old_art_bounty_still_sees_the_board(beta_setup):
    """存檔裡的季掛著求藝、玩家的 bounty_pick 還指著它（停在第三層下線）：讀出來那一張已經不在了，選單照第二層畫，
    按舊的交出鈕說下榜了；狀態（江湖頁的懸賞卡）、店面都不炸。"""
    content, world = beta_setup
    content.config.weapons.enabled = True
    _armed(world, "丙", _blade("兵:2"))
    arms = _arms(world)
    world.mutate_season(lambda s: (s.bounties.append(Bounty(**_old_art_bounty("b90"))), setattr(s, "bounty_seq", 90)))
    assert [b.id for b in world.get_season().bounties] == [arms.id]  # 寫進去的求藝，讀回來就沒了
    _edit(world, "丙", lambda p: (setattr(p, "picking_bounty", True), setattr(p, "bounty_pick", "b90")))
    assert list(_ids(content, world, "丙")) == [f"bounty:pick:{arms.id}", "bounty:back"]
    assert _do(content, world, "丙", lambda g: g.choose("bounty:give:b90:烈焰掌"))[0] == [bounties.GONE]
    rows = _do(content, world, "丙", lambda g: g.status_data())[0]["bounties"]
    assert [r["id"] for r in rows] == [arms.id]
