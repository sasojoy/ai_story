"""裝備的網頁那一半（兵器設計 3.6、裝備四欄設計 2.5）：修練頁的「裝備」塊——每一欄一段，身上那件、裝備庫每件一行與「換上」鈕；字都跳脫；沒東西就不畫。
餵真的引擎給的 /api/main 與 /api/menxia 給 app.js（tests/test_prologue_web.py 的假瀏覽器）。沒有 node 就略過。"""
from __future__ import annotations

import random

import pytest
from test_prologue_web import run

import server
import webharness
from tianxia.engine import Game

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


def _row(**over):
    return {"id": "兵:1", "name": "試刃", "kind": "劍", "attribute": "柔", "tier": 1, "quality": "下品",
            "edge": 80, "fits": True, "bonus": "+4.5%", **over}


def _gear(weapon=None, armor=None, cap=100, used=None):
    """修練頁「裝備」那一塊的資料（server.menxia_view 的 gear，skillview.gear_rows）：開著的欄位一段一段；used 沒給就是各段裝備庫的件數合計。"""
    slots = []
    if weapon is not None:
        slots.append({"slot": "weapon", "label": "武器", "empty": "手上沒有兵器。", "note": "城裡的鐵匠鋪打得出、買得到、修得好，也淬得了；用不上的拆了換素材。", **weapon})
    if armor is not None:
        slots.append({"slot": "armor", "label": "防具", "empty": "身上沒有防具。", "note": "城裡的鐵匠鋪買得到、修得好；用不上的拆了換素材。", **armor})
    return {"cap": cap, "used": sum(len(s["rack"]) for s in slots) if used is None else used, "slots": slots}


def _slot_block(page, slot):
    return page.split(f'data-slot="{slot}"')[1].split("</section>")[0]


def _armor_row(**over):
    return {"id": "甲:1", "name": "軟皮甲", "attribute": "柔", "tier": 1, "quality": "下品", "grade": "一階下品", "edge": 80,
            "wear_word": "耐久度", "cut": "8%", "fit": "跟你的內功同屬性", "tempers": 0, "confirm": "", **over}


@pytest.fixture
def views(hints_content, world):
    game = Game.new(hints_content, "沈浪", rng=random.Random(0), world=world)
    game.skip_tutorial()
    return server.main_view(game), server.menxia_view(game)


def test_the_practice_page_draws_the_worn_weapon_and_the_rack(views):
    m, x = views
    x["gear"] = _gear(weapon={"worn": _row(), "rack": [_row(id="兵:2", name="<b>厚背刀</b>", kind="刀", fits=False, bonus=None)]}, cap=6)
    page = run(m, "return H.pagePractice();", menxia=x)
    assert 'data-slot="weapon"' in page and "【試刃】" in page and "鋒利度 80" in page and "威力 +4.5%" in page
    assert page.count('data-act="wield"') == 1 and 'data-id="兵:2"' in page  # 身上那把不用換上
    assert "裝備庫 1/6" in page and "用不上" in page
    assert "<b>厚背刀</b>" not in page and "&lt;b&gt;厚背刀&lt;/b&gt;" in page  # 名字跳脫


def test_the_wield_button_sends_the_weapon_id(views):
    m, x = views
    x["gear"] = _gear(weapon={"worn": None, "rack": [_row(id="兵:2")]}, cap=6)
    page = run(m, "return H.pagePractice();", menxia=x)
    assert "手上沒有兵器" in page and 'data-act="wield"' in page


def test_nothing_is_drawn_without_gear(views):
    m, x = views
    assert 'class="gear"' not in run(m, "return H.pagePractice();", menxia=x)  # 測試內容把武器、防具都關著
    x["gear"] = _gear(weapon={"worn": None, "rack": []}, armor={"worn": None, "rack": []})
    assert 'class="gear"' not in run(m, "return H.pagePractice();", menxia=x)  # 開著但什麼都沒有
    del x["gear"]  # 舊的伺服器沒有這一欄
    assert 'class="gear"' not in run(m, "return H.pagePractice();", menxia=x)


def test_a_long_rack_lists_eight_and_then_a_more_button(views):
    m, x = views
    rack = [_row(id=f"兵:{i + 2}", name=f"備刃{i}") for i in range(12)]
    x["gear"] = _gear(weapon={"worn": _row(), "rack": rack})
    page = run(m, "return H.pagePractice();", menxia=x)
    assert page.count('data-act="wield"') == 8 and "備刃7" in page and "備刃8" not in page
    assert 'data-act="rack-all"' in page and "再列 4 件" in page and "裝備庫 12/100" in page
    everything = run(m, "return H.pagePractice();", menxia=x, S={"rackAll": True})  # 按了「再列」之後全部攤開
    assert everything.count('data-act="wield"') == 12 and "rack-all" not in everything and "再列" not in everything
    x["gear"]["slots"][0]["rack"] = rack[:8]  # 剛好八把：不必多按一次
    short = run(m, "return H.pagePractice();", menxia=x)
    assert short.count('data-act="wield"') == 8 and "再列" not in short


def test_every_rack_row_has_a_dismantle_button_and_the_worn_one_does_not(views):
    m, x = views
    x["gear"] = _gear(weapon={"worn": _row(), "rack": [_row(id="兵:2", name="<i>厚背刀</i>"), _row(id="兵:3", name="備刃", fits=False, bonus=None)]})
    page = run(m, "return H.pagePractice();", menxia=x)
    assert page.count('data-act="dismantle"') == 2 and 'data-act="dismantle" data-id="兵:2"' in page and 'data-act="dismantle" data-id="兵:3"' in page
    assert page.count('data-act="wield"') == 2  # 換上照舊
    assert "<i>厚背刀</i>" not in page and "&lt;i&gt;厚背刀&lt;/i&gt;" in page
    x["gear"]["slots"][0]["rack"] = []
    assert 'data-act="dismantle"' not in run(m, "return H.pagePractice();", menxia=x)  # 身上那把不能拆


def _weapons_block(page):
    return _slot_block(page, "weapon")


def test_rack_rows_keep_both_buttons_together_and_show_the_grade(views):
    """FB-125：「換上」「拆解」包在同一個不折行的容器裡（不會折到下一把的名字上），每列寫階與品質，拆解帶著問句。"""
    m, x = views
    ask = "把【厚背刀】（二階中品）拆成玄鋼骨×1？拆掉就沒了。"
    x["gear"] = _gear(weapon={"worn": _row(grade="一階下品", confirm=""),
                              "rack": [_row(id="兵:2", name="厚背刀", grade="二階中品", confirm=ask)]})
    block = _weapons_block(run(m, "return H.pagePractice();", menxia=x))
    assert block.count('class="wbtns"') == 1  # 只有裝備庫那一列有鈕
    assert "二階中品" in block and "一階下品" in block
    assert f'data-confirm="{ask}"' in block


_DISMANTLE_CLICK = """return (async () => {
  const click = (dataset) => T.docListeners.click[0]({ target: { closest: () => ({ dataset, classList: { contains: () => false, add() {}, remove() {} } }) } });
  T.qs['.ask [data-act="ask-no"]'] = { focus() {} };
  await click({ act: "dismantle", id: "兵:2", confirm: "把【厚背刀】（一階下品）拆成精鐵砂×1？拆掉就沒了。" });
  const asked = T.bodyHtml.join("");
  const before = T.calls.map((c) => c[0]);
  %(then)s
  return { asked, before, calls: T.calls.map((c) => [c[0], c[1]]) };
})();"""


def test_dismantle_asks_first_and_sends_only_on_yes(views):
    m, x = views
    x["gear"] = _gear(weapon={"worn": None, "rack": [_row(id="兵:2", name="厚背刀", grade="一階下品", confirm="問")]})
    reply = {"/api/menxia/dismantle": {"menxia": x, "message": "", "main": m}}
    out = run(m, _DISMANTLE_CLICK % {"then": 'await click({ act: "ask-no" });'}, menxia=x, responses=reply)
    assert "拆成精鐵砂×1" in out["asked"] and "拆掉" in out["asked"]
    assert out["before"] == [] and out["calls"] == []  # 問了；取消之後什麼都沒送
    out = run(m, _DISMANTLE_CLICK % {"then": 'await click({ act: "ask-yes" });'}, menxia=x, responses=reply)
    assert [c[0] for c in out["calls"]] == ["/api/menxia/dismantle"] and out["calls"][0][1]["weapon"] == "兵:2"


_CHOOSE_CLICK = """return (async () => {
  const click = (act, id) => T.docListeners.click[0]({ target: { closest: () => ({ dataset: { act, id }, classList: { contains: () => false, add() {}, remove() {} } }) } });
  T.qs['.ask [data-act="ask-no"]'] = { focus() {} };
  await click("choose", "smith:dismantle:兵:2");
  return { asked: T.bodyHtml.join(""), calls: T.calls.map((c) => c[0]) };
})();"""


def test_a_smith_dismantle_option_asks_with_its_own_yes_word(views):
    m, _ = views
    m = {**m, "options": [{"id": "smith:dismantle:兵:2", "label": "拆解【厚背刀】→ 精鐵砂×1", "enabled": True, "wait": "",
                           "confirm": "把【厚背刀】（一階下品）拆成精鐵砂×1？拆掉就沒了。", "confirm_yes": "拆掉"}]}
    out = run(m, _CHOOSE_CLICK)
    assert "拆成精鐵砂×1" in out["asked"] and ">拆掉<" in out["asked"] and ">照打<" not in out["asked"]
    assert out["calls"] == []


def test_rack_rows_show_tempers_and_the_recipe(views):
    m, x = views
    x["gear"] = _gear(weapon={"worn": _row(confirm="", grade="一階中品", tempers=2, temper_max=5, recipe="精鐵砂＋驚羽"), "rack": []})
    block = _weapons_block(run(m, "return H.pagePractice();", menxia=x))
    assert "淬煉 2/5" in block and "配方 精鐵砂＋驚羽" in block and "一階中品" in block
    x["gear"]["slots"][0]["worn"] = _row(confirm="", grade="一階下品", tempers=0, temper_max=5, recipe=None)
    plain = _weapons_block(run(m, "return H.pagePractice();", menxia=x))
    assert "淬煉 0" not in plain and "配方 " not in plain


def test_the_armor_slot_draws_its_own_rows_with_durability_and_cut(views):
    m, x = views
    spare = _armor_row(id="甲:2", name="<i>鐵葉甲</i>", attribute="剛", cut="3%", fit="跟你的內功相剋",
                       confirm="把【鐵葉甲】（一階下品）拆成精鐵砂×1？拆掉就沒了。")
    x["gear"] = _gear(weapon={"worn": _row(), "rack": []}, armor={"worn": _armor_row(), "rack": [spare]})
    page = run(m, "return H.pagePractice();", menxia=x)
    block = _slot_block(page, "armor")
    assert "【軟皮甲】" in block and "耐久度 80" in block and "少扣 8% 氣血" in block and "跟你的內功同屬性" in block
    # 防具用自己的字（FB-127）、沒有配不上。「用不上」只看列裡的「・用不上」：段尾的說明（armor.RACK_NOTE「…用不上的拆了換素材。」）
    # 也在這個 <section> 裡，字歸 joy，不為了測試改字
    assert "鋒利度" not in block and "刀口" not in block and "・用不上" not in block
    other = _slot_block(run(m, "return H.pagePractice();", menxia={**x, "gear": _gear(armor={"worn": _armor_row(wear_word="護甲值"), "rack": []})}), "armor")
    assert "護甲值 80" in other and "耐久度" not in other  # 磨損的叫法照伺服器給的 wear_word 畫（equipment.WEAR_WORDS），網頁不寫死
    assert block.count('class="wbtns"') == 1 and 'data-act="dismantle" data-id="甲:2"' in block
    assert 'data-confirm="把【鐵葉甲】（一階下品）拆成精鐵砂×1？拆掉就沒了。"' in block
    assert "&lt;i&gt;鐵葉甲&lt;/i&gt;" in block and "<i>鐵葉甲</i>" not in block
    assert "裝備庫 1/100" in page and page.index('data-slot="weapon"') < page.index('data-slot="armor"')


def test_an_empty_armor_slot_says_so_and_an_unknown_slot_is_skipped(views):
    m, x = views
    x["gear"] = _gear(weapon={"worn": _row(), "rack": []}, armor={"worn": None, "rack": []})
    x["gear"]["slots"].append({"slot": "future", "label": "未來", "empty": "", "note": "", "worn": {"id": "騎:1"}, "rack": []})
    page = run(m, "return H.pagePractice();", menxia=x)
    assert "身上沒有防具。" in _slot_block(page, "armor")
    assert 'data-slot="future"' not in page  # 這一版畫不出的欄位（新伺服器多了一欄）整段略過


def _mount_gear(worn=None, rack=()):
    """修練頁「裝備」只有坐騎那一段（server.menxia_view 的 gear，skillview.gear_rows）。"""
    return {"cap": 100, "used": len(rack), "slots": [{
        "slot": "mount", "label": "坐騎", "empty": "身上沒有坐騎。", "note": "城裡的馬市買得到駑馬；一個一階素材就餵得飽。",
        "worn": worn, "rack": list(rack),
    }]}


def _mount_row(**over):
    return {"id": "騎:1", "name": "棗騮馬", "tier": 1, "quality": "下品", "grade": "駑馬・下品", "edge": 60, "wear_word": "飽足度",
            "save": "20%", "speed": "24%", "cavalry": "4%", "escape": "24%", "feed": True, "feed_note": "精鐵砂×1",
            "wield_ok": True, "wield_note": "", **over}


def _mount_block(page):
    return page.split('data-slot="mount"')[1].split("</section>")[0]


def test_the_mount_slot_draws_feed_on_the_worn_horse_and_only_wield_in_the_rack(views):
    """坐騎那一段（裝備四欄 2.5、5.4）：身上那匹一顆「餵」（寫用哪一種素材），裝備庫裡的只有「換上」，坐騎不能拆（4.8）。
    每一列寫省體力、路上快、決戰騎兵、落敗脫身（2.5：後三項寫在修練頁這一列，不擠進角色卡）。這一行的字待 joy 潤，只鎖伺服器給的數字。"""
    m, x = views
    spare = _mount_row(id="騎:2", name="<i>青驄駒</i>", grade="良駒・中品", save="43%", speed="48%", cavalry="10%", escape="50%",
                       feed=False, feed_note="")
    x["gear"] = _mount_gear(_mount_row(), [spare])
    block = _mount_block(run(m, "return H.pagePractice();", menxia=x))
    assert "【棗騮馬】" in block and "駑馬・下品" in block and "飽足度 60" in block and "20%" in block
    assert block.count("24%") == 2 and "+4%" in block  # 駑馬路上快、脫身都是三成×0.8；騎兵寫成「+4%」
    assert "43%" in block and "48%" in block and "+10%" in block and "50%" in block
    assert block.count('data-act="feed"') == 1 and "精鐵砂×1" in block
    assert 'data-act="wield" data-id="騎:2">' in block and 'data-act="dismantle"' not in block
    assert "&lt;i&gt;青驄駒&lt;/i&gt;" in block and "<i>青驄駒</i>" not in block
    other = _mount_block(run(m, "return H.pagePractice();", menxia={**x, "gear": _mount_gear(_mount_row(wear_word="草料"))}))
    assert "草料 60" in other  # 磨損的叫法照伺服器給的 wear_word（equipment.WEAR_WORDS），網頁不寫死


def test_a_feed_that_cannot_happen_is_greyed_with_the_reason(views):
    m, x = views
    x["gear"] = _mount_gear(_mount_row(feed=False, feed_note="還不餓"))
    block = _mount_block(run(m, "return H.pagePractice();", menxia=x))
    assert 'data-act="feed" disabled' in block and "還不餓" in block


def test_wield_is_greyed_on_the_road_with_the_reason(views):
    """設計 2.3：路上不能換坐騎——裝備庫那一列的「換上」灰掉、寫伺服器給的原因（mounts.ON_ROAD），同「餵」的灰掉做法。"""
    m, x = views
    x["gear"] = _mount_gear(_mount_row(), [_mount_row(id="騎:2", feed=False, feed_note="", wield_ok=False, wield_note="在路上")])
    block = _mount_block(run(m, "return H.pagePractice();", menxia=x))
    assert 'data-act="wield" data-id="騎:2" disabled' in block and "在路上" in block


_FEED_CLICK = """return (async () => {
  const click = (dataset) => T.docListeners.click[0]({ target: { closest: () => ({ dataset, classList: { contains: () => false, add() {}, remove() {} } }) } });
  await click({ act: "feed" });
  return T.calls.map((c) => c[0]);
})();"""


def test_the_feed_button_calls_the_feed_action(views):
    m, x = views
    x["gear"] = _mount_gear(_mount_row())
    reply = {"/api/menxia/feed": {"menxia": x, "message": "", "main": m}}
    assert run(m, _FEED_CLICK, menxia=x, responses=reply) == ["/api/menxia/feed"]


def _treasure_gear(worn=None, rack=(), held_note=""):
    """修練頁「裝備」只有寶物那一段（server.menxia_view 的 gear，skillview.gear_rows）。"""
    return {"cap": 100, "used": len(rack), "held_note": held_note, "slots": [{
        "slot": "treasure", "label": "寶物", "empty": "身上沒有寶物。", "note": "寶物買不到、打不出。",
        "worn": worn, "rack": list(rack),
    }]}


def _treasure_row(**over):
    return {"id": "寶:1", "name": "烏木名刺", "effect": "audience", "effect_text": "求見門檻 −3", **over}


def test_the_treasure_slot_draws_the_effect_and_only_wield(views):
    """寶物那一段（裝備四欄 2.5、第六節）：身上那件寫效果，裝備庫裡的只有「換上」，而且永遠按得下（寶物隨時能換，2.3【定】）；
    寶物不能拆（4.8）。字都跳脫。"""
    m, x = views
    spare = _treasure_row(id="寶:2", name="<i>拾遺囊</i>", effect="win_material", effect_text="打贏時有 25% 的機會多掉一個素材")
    x["gear"] = _treasure_gear(_treasure_row(), [spare])
    block = _slot_block(run(m, "return H.pagePractice();", menxia=x), "treasure")
    assert "【烏木名刺】" in block and "求見門檻 −3" in block and "打贏時有 25% 的機會多掉一個素材" in block
    assert 'data-act="wield" data-id="寶:2">' in block and block.count('data-act="wield"') == 1
    assert 'data-act="dismantle"' not in block and " disabled" not in block
    assert "&lt;i&gt;拾遺囊&lt;/i&gt;" in block and "<i>拾遺囊</i>" not in block


def test_held_gear_is_mentioned_under_the_gear_block(views):
    m, x = views
    x["gear"] = _treasure_gear(None, [], held_note="寄放著：【叩關玉】")
    page = run(m, "return H.pagePractice();", menxia=x)
    assert "寄放著：【叩關玉】" in page  # 身上與裝備庫都空著，寄放的那一行照樣畫（不然玩家以為東西作廢了）

def test_armor_rows_show_tempers_and_the_recipe(views):
    """防具打造：防具列跟武器列一樣，淬過的寫「淬煉 N/M」，自己打的寫配方；沒淬過、買的不寫。"""
    m, x = views
    x["gear"] = _gear(armor={"worn": _armor_row(grade="一階中品", tempers=2, temper_max=5, recipe="精鐵砂＋驚羽"), "rack": []})
    block = _slot_block(run(m, "return H.pagePractice();", menxia=x), "armor")
    assert "淬煉 2/5" in block and "配方 精鐵砂＋驚羽" in block and "一階中品" in block
    x["gear"]["slots"][0]["worn"] = _armor_row(tempers=0, temper_max=5, recipe=None)
    plain = _slot_block(run(m, "return H.pagePractice();", menxia=x), "armor")
    assert "淬煉 0" not in plain and "配方 " not in plain
