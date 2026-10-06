"""FB-092～095 與 h_lose（QA 走 joy 版序章與入伍段，main 8d4d470，2026-10-06；規劃者決定，專職開發做）。

用真實內容（conftest 的 real、on：這個測試自己的一份複本）。每一條是一個 commit，先寫測試。
新寫的句子都在待 joy 潤的清單上（見 fb-report.md）：這裡的測試只認事實（講了什麼、對不對得上規則），不鎖死字句。"""
from __future__ import annotations

import re

import pytest
from test_prologue_web import run
from tests.test_orders import _game, _order

import server
import webharness
from tianxia import guide, models, team
from tianxia.martial_arts import content_art
from tianxia.rules import front_of


def _step(content, step_id):
    return next(step for step in content.tutorial.steps if step.id == step_id)


def _art(skill_id, kind, attribute):
    return content_art(skill_id, skill_id, kind, attribute, "下品")


# ── FB-092：序章選「火」，新武學跟吐納相剋 ─────────────────────────────


def test_fb092_the_fire_method_says_the_fire_does_not_suit_the_breath(real):
    """四景的「灶裡那盆火」是屬剛的做法，師門配方給的是屬剛的【烈爐拳】，跟身上柔的基礎吐納相剋：選之前先說一句。"""
    scene = real.insight_scenes["prologue_hut"]
    fire = next(m for m in scene.methods if m.attribute == "剛")
    assert "灶裡那盆火" in fire.text and "火性剛烈" in fire.text and "吐納" in fire.text
    breath = real.skills[real.config.starter_skills[0]]
    assert (breath.kind, breath.attribute) == ("內功", "柔") and breath.name == "基礎吐納"  # 句子說的是真的：吐納屬柔
    others = [m.text for m in scene.methods if m.attribute != "剛"]
    assert not any("吐納" in text for text in others)  # 另外三個做法不相剋，不多說


def test_fb092_step_five_says_how_pairing_works_to_everyone(real):
    """第 5 步（改練）的話對每個人都多兩句：同一路加兩成、相剋的冤家少兩成，扯了後腿先練上去，之後內功也能融意境換路數。"""
    step = _step(real, "p5_level")
    text = step.text
    assert "講緣分" in text and "同一路" in text and "兩成" in text and "冤家" in text and "內功" in text and "融意境" in text
    assert "改練" in text and "功法庫" in text and "練到第三成" in text  # 原本的指示還在
    assert step.glow == ["tab:practice", "switch", "practice"]  # 發光不動


def test_fb092_what_the_master_says_about_pairing_is_what_the_rules_do(real):
    """師父說的三件事都是真的：同屬性 +20%、相剋的一對 −20%（team.pairing，照 Config）；內功能當合成的底、融了意境還是內功
    （tests/test_fusion.py::test_a_neigong_base_stays_a_neigong 釘住）。"""
    breath = _art("jichu_tuna", "內功", "柔")
    assert real.config.pairing_bonus == 0.2 and real.config.pairing_penalty == 0.2
    assert team.pairing(real, _art("a", "武學", "柔"), breath) == 1.2  # 同一路
    assert team.pairing(real, _art("b", "武學", "剛"), breath) == 0.8  # 剛配柔：冤家
    assert team.pairing(real, _art("c", "武學", "快"), breath) == 1.0  # 不相干的不加不減


# ── FB-093：入伍第 2 步沒說軍令怎麼出力 ─────────────────────────────────
# 軍令卡每一道都寫一行「做法」（打擊那道本來就有）；入伍第 2 步的框多一句，指出「你腳下這裡做得了的」；每位引薦人的結語不再
# 把五種軍令怎麼做整段背一遍；第 2 步發光的是自己陣營的守勢行動（巡哨、傳道、保境安民）。

DUTY = {"guan": "巡哨", "huang": "傳道", "haoqiang": "保境安民"}
JOIN_AT = {"guan": "changshe", "huang": "huangjin_camp", "haoqiang": "zhuo_militia_hall"}


def _enlisted(on, faction, place=None):
    """剛投靠、看過軍令卡：框停在「挑一道軍令，出一次力」那一步。提示關掉（長社站著大勢人物，真內容的提示表會先排一條）。"""
    game = _game(on, at=place or JOIN_AT[faction])
    game.state.player.tutorial_step = len(guide.steps(game.state, on))
    game.set_hints_off(True)
    game.choose(f"faction:{faction}")
    game.choose("faction:confirm")
    game.view_orders()
    assert game.guide_box()["key"] == "r3_first_order"
    return game


def test_fb093_every_order_card_says_how(on):
    game = _enlisted(on, "guan")
    on_front = front_of(on, "changshe")
    _order(game, "siege", "guan", front=on_front)
    _order(game, "defend", "guan", front=on_front)
    _order(game, "intercept", "guan", location="hilltop_wilds")
    _order(game, "escort", "guan", start="luoyang_road", end="changshe")
    _order(game, "strike", "guan", figure="zhangmancheng")
    cards = {card["title"].split("・")[0]: card for card in game.orders_view()}
    assert set(cards) == {"攻城", "守城", "截糧", "護糧", "打擊"}
    for kind, card in cards.items():
        assert card.get("how"), kind  # 每一道都有做法那一行
    name = lambda loc_id: on.locations[loc_id].name  # noqa: E731
    assert "遊歷" in cards["攻城"]["how"] and on.orders.duties["guan"].name in cards["守城"]["how"]
    assert name("hilltop_wilds") in cards["截糧"]["how"] and "遊歷" in cards["截糧"]["how"]
    assert name("luoyang_road") in cards["護糧"]["how"] and name("changshe") in cards["護糧"]["how"] and "糧車" in cards["護糧"]["how"]
    assert "挑戰" in cards["打擊"]["how"]  # 打擊那一行本來就有（FB-072）：不動


def test_fb093_the_defence_action_is_named_from_the_content_for_each_side(on):
    """守城的行動名字照內容（orders.json 的 duties），三邊各自的：不是三處各寫一份。"""
    for faction, name in DUTY.items():
        assert on.orders.duties[faction].name == name
    for faction in ("guan", "huang"):
        game = _enlisted(on, faction)
        _order(game, "defend", faction, front=front_of(on, JOIN_AT[faction]))
        [card] = [c for c in game.orders_view() if c["title"].startswith("守城")]
        assert DUTY[faction] in card["how"], faction
        assert not any(other in card["how"] for f, other in DUTY.items() if f != faction), faction


def test_fb093_a_finished_order_has_no_how_line(on):
    game = _enlisted(on, "guan")
    order = _order(game, "siege", "guan", front=front_of(on, "changshe"))
    order.done = True
    assert "how" not in game.orders_view()[0]


def test_fb093_the_step_two_box_names_what_you_can_do_where_you_stand(on):
    """第 2 步的框多一句：你腳下這裡做得了的，是〇〇——在長社（官軍）是巡哨，在黃巾別部營寨（黃巾）是傳道。"""
    for faction in ("guan", "huang"):
        game = _enlisted(on, faction)
        place = JOIN_AT[faction]
        _order(game, "defend", faction, front=front_of(on, place))
        box = game.guide_box()
        assert DUTY[faction] in box["text"] and box["text"].startswith(on.tutorial.enlist.recruiters[faction].order_hint), faction
        assert box["line"] == "挑一道軍令，出一次力" and not box.get("paged")  # 收起來那一行不動、也不分頁


def test_fb093_the_sentence_has_a_fallback_when_nothing_can_be_done_here(on):
    game = _enlisted(on, "guan")
    _order(game, "defend", "guan", front=front_of(on, "changshe"))
    quiet = next(  # 一處不在任何戰線上的地方：這週的軍令沒有一道在這裡做得了
        loc_id for loc_id, loc in on.locations.items() if front_of(on, loc_id) is None and not loc.prologue_only and not loc.enemies
    )
    game.state.player.location = quiet
    text = game.guide_box()["text"]
    assert on.tutorial.enlist.how_none in text and DUTY["guan"] not in text


def test_fb093_the_ending_no_longer_recites_every_kind(on):
    """結語（做完之後）把「每一種怎麼做」整段背一遍的部分縮成一句誇獎：怎麼做改寫在軍令卡上。"""
    for faction, who in on.tutorial.enlist.recruiters.items():
        for gone in ("就到那條戰線遊歷", "就在戰線上", "先備好糧草", "到軍令說的地方遊歷", "當面挑戰"):
            assert gone not in who.done, (faction, gone)
        assert len(who.done) < 100, faction  # 以前約 200 字
        assert "陣營" in who.done  # 「陣營 幾／幾」是什麼意思還講：那是卡片上的另一件事


def _enlist_main(on, faction="guan"):
    game = _enlisted(on, faction)
    _order(game, "defend", faction, front=front_of(on, JOIN_AT[faction]))
    return server.main_view(game)


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_fb093_the_glow_lands_on_the_defence_button_in_the_page(on):
    """網頁：框上帶 glow（act:duty）時，「此地還能做」摺疊打開、巡哨那顆帶著 data-glow，applyGlow 給它加 glow；沒有 glow 的框一個也不加。"""
    m = _enlist_main(on)
    assert m["guide"]["glow"] == ["act:duty"] and any(o["id"] == "act:duty" for o in m["options"])
    html = run(m, "return H.actionBar(m);")
    assert re.search(r'<details class="fold here" open>', html)  # 收著的話按鈕看不到，發光就沒有意義：發光的這一步先打開
    assert re.search(r'data-act="choose" data-id="act:duty" data-glow="act:duty"', html)
    script = "const e = T.el(['act:duty']); const other = T.el(['act:rest']); H.applyGlow(); return [[...e.classes], [...other.classes]];"
    assert run(m, script) == [["glow"], []]
    quiet = {**m, "guide": {k: v for k, v in m["guide"].items() if k != "glow"}}
    assert run(quiet, script) == [[], []]  # 沒有 glow 的框：什麼都不亮（跟序章之外一向一樣）
    assert not re.search(r'<details class="fold here" open>', run(quiet, "return H.actionBar(m);"))


def test_fb093_the_step_glows_the_sides_defence_button(on):
    from tianxia.content import ContentError, validate

    assert "act:duty" in models.GLOW_KEYS
    for faction in ("guan", "huang", "haoqiang"):
        box = _enlisted(on, faction).guide_box()
        assert box["glow"] == ["act:duty"], faction
    game = _game(on, at="changshe")
    game.state.player.tutorial_step = len(guide.steps(game.state, on))
    game.set_hints_off(True)
    game.choose("faction:guan")
    game.choose("faction:confirm")
    assert "glow" not in game.guide_box()  # 第一步（看軍令卡）沒有東西要按
    bad = on.model_copy(deep=True)
    bad.tutorial.enlist.steps[1].glow = ["act:nonsense"]
    with pytest.raises(ContentError, match="act:nonsense"):
        validate(bad)
