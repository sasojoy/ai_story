"""NPC 智能 2.0（Joy 2026-10-23「先做看看」；tianxia/parley.py、Game._parley_*；Config.parley）：
「自己說」那一句可以是求人做事。模型挑清單上的一件、給意願、要不要開條件；引擎驗清單、照情誼與份量夾意願、自己擲骰，
中了當場做、沒中有條件就讓玩家接不接、沒中沒條件就婉拒。開關關著一個字都不變。"""

from unittest import mock

import pytest

from tianxia import companion_agent, parley
from tianxia.companion_agent import CompanionTurn
from tianxia.engine import SAY_MAX
from tianxia.state import Bounty

OPEN = CompanionTurn(narrative="他點了點頭。", options=["閒聊幾句", "就此告辭"], option_tags=["尋常寒暄", "尋常寒暄"])


def _ask(ask, willing=100, condition="", narrative="他答應了。", terms="你先替我辦件事。", no="他搖頭。"):
    return CompanionTurn(narrative=narrative, options=["閒聊幾句", "就此告辭"], option_tags=["尋常寒暄", "尋常寒暄"],
                         ask=ask, willing=willing, condition=condition, narrative_terms=terms, narrative_no=no)


@pytest.fixture
def talking(content, game):
    """NPC 智能 2.0開著、韓鐵常去湖邊（帶路有地方去）、已經跟他談上了。"""
    content.config.parley.enabled = True
    content.characters["mate"].deep_interaction = True
    content.characters["mate"].haunts = ["lake"]
    with mock.patch.object(companion_agent, "_generate", return_value=OPEN):
        game.choose("act:socialize")
    assert game.state.player.pending_companion == "mate"
    return game


def _say(game, turn, text="韓兄幫我一個忙", dice=1):
    with mock.patch.object(companion_agent, "generate_turn", return_value=turn), \
            mock.patch.object(parley, "roll", return_value=dice):
        return game.choose("talk:say", text=text)


# ── 純規則 ────────────


def test_the_ceiling_follows_affinity_weight_and_enmity(content):
    assert parley.ceiling(content, 0, 1, False) == 50
    assert parley.ceiling(content, 0, 3, False) == 25
    assert parley.ceiling(content, 65, 1, False) == 90
    assert parley.ceiling(content, 65, 2, True) == 90 - 10 - 30
    assert parley.ceiling(content, 0, 3, True) == content.config.parley.floor


def test_decide_clamps_the_models_willingness_and_rolls_with_the_engines_dice(content):
    asks = [parley.Item("spar", "指點一招", 1)]
    conds = [parley.Item("silver", "交一筆銀兩")]
    d = parley.decide(content, asks, conds, "spar", 100, "", 0, False, 50)
    assert (d.kind, d.chance) == ("do", 50)  # 模型說 100，生疏那一檔的天花板 50
    d = parley.decide(content, asks, conds, "spar", 100, "silver", 0, False, 50, can_owe=True)
    assert (d.kind, d.condition.id) == ("owe", "silver")  # 擲中又開了條件：先做後付（第二批）
    assert parley.decide(content, asks, conds, "spar", 100, "silver", 0, False, 50).kind == "terms"  # 不能再欠他：先付後做
    d = parley.decide(content, asks, conds, "spar", 100, "silver", 0, False, 51)
    assert (d.kind, d.condition.id) == ("terms", "silver")
    assert parley.decide(content, asks, conds, "spar", 100, "", 0, False, 51).kind == "no"
    assert parley.decide(content, asks, conds, "spar", 100, "made-up", 0, False, 51).kind == "no"  # 清單外的條件當沒開


def test_off_list_asks_and_plain_chat_are_handled(content):
    asks = [parley.Item("spar", "指點一招", 1)]
    assert parley.decide(content, asks, [], "", 90, "", 0, False, 1).kind is None  # 只是閒聊
    assert parley.decide(content, asks, [], "refuse", 90, "", 0, False, 1).kind == "no"
    assert parley.decide(content, asks, [], "sortie", 90, "", 0, False, 1).kind == "no"  # 模型挑了清單外的事


# ── 開關關著 ────────────


@pytest.mark.smoke
def test_off_switch_changes_nothing(content, game):
    assert not content.config.parley.enabled
    assert game.say_max() == SAY_MAX
    assert game._parley_prompt("mate") == "" and game._parley_options("mate") == []
    content.characters["mate"].deep_interaction = True
    with mock.patch.object(companion_agent, "_generate", return_value=OPEN):
        game.choose("act:socialize")
    msgs = _say(game, _ask("spar"))
    assert not any(m.startswith("（你求") for m in msgs) and game.state.player.parley_days == {}
    assert game.state.player.stats.get("xinde", 0) == 0


# ── 開著：當場做 ────────────


def test_the_prompt_lists_what_he_can_do_and_the_say_box_is_longer(talking):
    prompt = talking._parley_prompt("mate")
    assert "escort:lake" in prompt and "spar" in prompt and "silver" in prompt and "生疏" in prompt
    assert talking.say_max() == talking.content.config.parley.say_max
    assert "0" not in prompt.split("【你們的情誼】")[1].split("。")[0]  # 情誼只給一個詞


def test_a_granted_spar_gives_xinde_once_a_day(talking):
    msgs = _say(talking, _ask("spar"))
    assert "（你求韓鐵指點一招，他答應了。）" in msgs and f"心得 +{talking.content.config.parley.spar_xinde}" in msgs
    assert "spar" not in {a.id for a in talking._parley_lists("mate")[0]}


def test_escort_moves_the_player_for_free(talking):
    p = talking.state.player
    before = p.stamina
    msgs = _say(talking, _ask("escort:lake"), text="帶我去湖邊")
    assert any("親自帶你抄近路往湖邊" in m for m in msgs)
    assert p.pending_companion is None
    assert p.journey is not None and p.journey.path[-1] == "lake" and p.parley_escort == "mate"  # 照他的腳程走，路上能跟他說話
    assert p.stamina == before - talking.content.config.talk_stamina  # 只扣了這一輪對話的體力


def test_a_refusal_is_remembered_for_the_day(talking):
    msgs = _say(talking, _ask("spar", willing=0, no="他擺擺手。"), dice=100)
    assert "（你求韓鐵指點一招，他沒有答應。）" in msgs and "他擺擺手。" in msgs
    assert "spar" not in {a.id for a in talking._parley_lists("mate")[0]}


def test_asks_per_day_are_capped(talking):
    for _ in range(talking.content.config.parley.asks_per_day):
        _say(talking, _ask("gift"))
    assert talking._parley_prompt("mate") == ""
    msgs = _say(talking, _ask("gift"))
    assert not any("他答應了。）" in m for m in msgs)


# ── 贈物：話跟真的給的要一樣（2026-10-27 正式站：求天池露，他「取出一小瓶晶瑩剔透的液體」，實際給精鐵砂）──


def _gift(game):
    return parley.gift_of(game.state, game.content, "mate")


def test_the_prompt_names_the_one_thing_he_can_give(talking):
    gift = parley.gift_text(_gift(talking))
    prompt = talking._parley_prompt("mate")
    assert f"手頭只給得出{gift}" in prompt and f"把手頭的{gift}給玩家" in prompt


def test_a_gift_he_cannot_give_is_not_promised(talking):
    """玩家指名要隕鐵膽，模型寫他答應了、拿出來了，話裡卻沒說他真的給的那樣：換固定句，給的照引擎定的。"""
    gift = _gift(talking)
    msgs = _say(talking, _ask("gift", narrative="他從懷中取出一小塊沉甸甸的東西：「此物便歸你所有。」"), text="可以把隕鐵膽給我嗎")
    assert "他從懷中取出一小塊沉甸甸的東西：「此物便歸你所有。」" not in msgs
    assert parley.GIFT_SWAP.format(name="韓鐵", wanted="隕鐵膽", gift=parley.gift_text(gift)) in msgs
    assert parley.GIFT_LINE.format(name="韓鐵", gift=parley.gift_text(gift)) in msgs
    if gift.material:
        assert talking.state.player.materials.get(gift.material) == 1 and "gang_3" not in talking.state.player.materials


def test_a_gift_line_naming_another_item_is_replaced(talking):
    gift = _gift(talking)
    other = next(m.name for m in talking.content.materials.values() if m.name != gift.name)
    msgs = _say(talking, _ask("gift", narrative=f"他遞來一份{other}。"), text="送我點東西吧")
    assert f"他遞來一份{other}。" not in msgs
    assert parley.GIFT_PLAIN.format(name="韓鐵", gift=parley.gift_text(gift)) in msgs


def test_a_gift_line_that_says_no_to_the_wanted_item_and_names_the_real_one_stays(talking):
    gift = _gift(talking)
    mine = gift.name if gift.material else "二十兩銀子"
    line = f"他搖頭：「隕鐵膽我沒有，這{mine}你拿去。」"
    msgs = _say(talking, _ask("gift", narrative=line), text="給我隕鐵膽")
    assert line in msgs


def test_gift_terms_that_promise_the_wanted_item_are_replaced(talking):
    gift = _gift(talking)
    msgs = _say(talking, _ask("gift", willing=0, condition="silver", terms="拿二十兩來，隕鐵膽就是你的。"), text="給我隕鐵膽", dice=100)
    want = parley.GIFT_SWAP_TERMS.format(name="韓鐵", wanted="隕鐵膽", gift=parley.gift_text(gift), cond="交 20 兩銀子")
    assert want in msgs and talking.state.player.parley_terms["mate"].text == want


def test_gift_slip_ignores_names_inside_longer_names(content):
    gift = parley.Gift("gang_1", "精鐵砂")
    assert parley.gift_slip(content, gift, "送我點東西", "他給了你一把精鐵砂。") is None
    assert parley.gift_slip(content, gift, "送我點東西", "他給了你一包東西。") is None  # 沒指名、也沒寫別的：照引擎給
    assert parley.gift_slip(content, gift, "給我驚羽", "他把東西塞給你。") == "驚羽"
    assert parley.gift_slip(content, gift, "給我驚羽", "他說驚羽沒有，給你精鐵砂。") is None
    assert parley.gift_slip(content, gift, "送我點東西", "他給了你玄鋼骨和精鐵砂。") == ""


# ── 開條件 ────────────


def test_silver_terms_are_paid_on_accept(talking):
    p = talking.state.player
    p.stats["silver"] = 100
    msgs = _say(talking, _ask("spar", willing=0, condition="silver", terms="拿二十兩來。"), dice=100)
    assert "拿二十兩來。" in msgs and "（你求韓鐵指點一招。他開了條件：交 20 兩銀子。）" in msgs
    labels = {o.id: o.label for o in talking.options(odds=False)}
    assert labels["talk:terms:yes"] == "答應他：交 20 兩銀子" and "talk:terms:no" in labels
    msgs = talking.choose("talk:terms:yes")
    assert "銀兩 -20" in msgs and p.stats["silver"] == 80 and "心得 +15" in msgs
    assert "mate" not in p.parley_terms


def test_declining_terms_drops_the_ask(talking):
    _say(talking, _ask("spar", willing=0, condition="silver"), dice=100)
    msgs = talking.choose("talk:terms:no")
    assert msgs == ["你沒有接下韓鐵的條件，這件事就此作罷。"]
    assert "talk:terms:yes" not in {o.id for o in talking.options(odds=False)}


def test_short_on_silver_keeps_the_terms_open(talking):
    talking.state.player.stats["silver"] = 0
    _say(talking, _ask("spar", willing=0, condition="silver"), dice=100)
    assert talking.choose("talk:terms:yes") == [parley.TERMS_SHORT]
    assert "mate" in talking.state.player.parley_terms


def test_a_scout_condition_becomes_a_commission_and_he_pays_back(talking):
    p = talking.state.player
    _say(talking, _ask("spar", willing=0, condition="scout:lake"), dice=100)
    msgs = talking.choose("talk:terms:yes")
    assert msgs[0].startswith("你答應了韓鐵：替他打探湖邊")
    letter = p.letters[-1]
    assert letter.kind == "條件" and letter.task.kind == "scout" and letter.task.parley_ask == "spar"
    from tianxia import bounties

    done = bounties._complete_commission(talking.state, talking.content, letter.task)
    assert "下回見到韓鐵，他會兌現答應你的事。" in done and p.parley_owed["mate"] == "spar"
    button = next(o for o in talking.options(odds=False) if o.id == "talk:owed")
    assert button.label == "請韓鐵兌現：指點一招"
    msgs = talking.choose("talk:owed")
    assert msgs[0] == "韓鐵記得答應過你的事。" and "心得 +15" in msgs and "mate" not in p.parley_owed


def test_parley_fields_start_over_with_the_season(game):
    p = game.state.player
    p.parley_owed["mate"] = "spar"
    game._reset_player_for_new_season(p.season_number + 1)
    assert game.state.player.parley_owed == {} and game.state.player.parley_days == {}


def test_generated_terms_are_converted_to_traditional():
    class Client:
        def chat_structured(self, *a, **k):
            return _ask("spar", terms="你先替我办件事", no="他摇头")

    turn = companion_agent.generate_turn(Client(), [])
    assert (turn.narrative_terms, turn.narrative_no) == ("你先替我辦件事", "他搖頭")


def test_bounty_default_has_no_parley_ask():
    assert Bounty(id="c1", faction=None, week=1, kind="scout", location="lake", expires=0, silver=0, deeds=0).parley_ask is None
