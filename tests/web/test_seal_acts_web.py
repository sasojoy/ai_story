"""玉璽碎片改版第 2 批的網頁（企劃者 2026-10-21 挑了乙；草圖 docs/superpowers/specs/2026-10-21-玉璽碎片改版-草圖/第2批/）：修練頁傳承那一列的鈕、
選目標的那一層（店面樣式：招牌、剩幾次、一人一列、灰掉寫原因、散人照店面頁籤挑一邊）、問句、送 /api/do/seal_use；江湖頁碎片卡那一行提醒。
餵真的引擎給的 /api/main（正式內容、21 天季）給 app.js（tests/test_prologue_web.py 的假瀏覽器）。沒有 node 就略過。
窄螢幕不橫捲要真的排版：假瀏覽器量不到，這裡守 CSS 原文，幾何在瀏覽器裡量（375／360／320，數字寫在草圖的 README）。"""
from __future__ import annotations

import json
import random
import re
import tempfile
from pathlib import Path

import pytest
from test_prologue_web import DRIVER as PROLOGUE_DRIVER
from test_seal_acts import _do, _holder, _person, _use

import server
import webharness
from conftest import real_content
from tianxia import seal
from tianxia.characters import CharacterStore
from tianxia.engine import Game
from tianxia.sqlite_world import open_world
from tianxia.state import BotProfile

pytestmark = [pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過"), pytest.mark.slow]

NAMES_START = 'wholeApp(["S", '
assert PROLOGUE_DRIVER.count(NAMES_START) == 1
DRIVER = PROLOGUE_DRIVER.replace(
    NAMES_START, 'wholeApp(["S", "heirloomRow", "sealActHtml", "sealActLine", "sealActNow", "sealHtml", "sealActPolled", ')
CSS = (Path(__file__).resolve().parents[2] / "web" / "style.css").read_text(encoding="utf-8")

# 一顆一顆點（同 test_admin_triggers_web.CLICK）：點完記下 #app 畫了什麼與跳出來的問句；ask-yes 只在 input.yes 為真時按
CLICK = """return (async () => {
  T.qs['.ask [data-act="ask-no"]'] = { focus() {} };
  const target = (dataset) => ({ dataset, classList: { contains: () => false, add() {}, remove() {} } });
  const click = (dataset) => T.docListeners.click[0]({ target: { closest: () => target(dataset) } });
  const out = [];
  for (const dataset of input.clicks) {
    const asked = T.bodyHtml.length;
    await click(dataset);
    out.push({ app: T.els.app.innerHTML, asked: T.bodyHtml.length > asked ? T.bodyHtml[T.bodyHtml.length - 1] : "", open: H.S.sealAct });
  }
  return { out, calls: T.calls.filter((c) => c[0].startsWith("/api/do/")).map((c) => [c[0], c[1]]) };
})();"""


def run(m, script, S=None, responses=None):
    return webharness.run(DRIVER, {"m": m, "script": script, "S": S or {"tab": "jianghu"}, "menxia": None, "stored": {},
                                   "responses": responses or {}})


def click(m, clicks, S=None):
    script = CLICK.replace("input.clicks", json.dumps(clicks, ensure_ascii=False))
    return run(m, script, S=S, responses={"/api/do/": {"main": m, "message": "好了"}})


def _view(shard="xuanniu", *, side="huang", at="changshe", on=True, profile="season21", conquest_on=True):
    c, w, g = _holder(shard, side=side, at=at, on=on, profile=profile, conquest_on=conquest_on)
    return c, w, server.main_view(g)


def _layer(m, S=None):
    return run(m, "return H.sealActHtml(H.sealActNow());", S={"tab": "jianghu", "sealAct": True, **(S or {})})


def _rows(html):
    """每一列（名字, 鈕的 data-id, 灰了沒, 原因那一格）。"""
    rows = []
    for block in html.split('<div class="shop-row seal-row">')[1:]:
        name = re.search(r"<b>(.*?)</b>", block).group(1)
        why = re.search(r'<span class="seal-why">(.*?)</span>', block)
        btn = re.search(r'<button class="btn small[^"]*" data-act="seal-pick" data-id="([^"]+)"([^>]*)>', block)
        rows.append((name, btn.group(1), "disabled" in btn.group(2), why.group(1) if why else ""))
    return rows


def test_the_heirloom_row_gets_a_button_and_the_card_a_line():
    """修練頁傳承那一列：「引將・剩 2 次」一顆（data-act="seal-act"）；江湖頁碎片卡多一行「獨門行動・引將：這一季還能起用 2 次」（按了跳修練頁）。"""
    c, w, m = _view()
    row = run(m, 'return H.heirloomRow({name: "玄紐", effect_text: "戰力 ×1.1"}, H.sealActNow());')
    assert 'data-act="seal-act"' in row and "引將・剩 2 次" in row and "disabled" not in row
    page = run(m, "return H.pageJianghu();")
    assert "獨門行動・引將：這一季還能起用 2 次" in page and 'data-act="seal-act-go"' in page


def test_the_practice_page_draws_the_button_in_the_heirloom_row():
    """修練頁裝備塊（真的 /api/menxia）：傳承那一列帶著那一顆鈕。"""
    c, w, g = _holder("xuanniu", at="changshe")
    page = webharness.run(DRIVER, {"m": server.main_view(g), "script": "return H.pagePractice();", "S": {"tab": "practice", "pdrawer": {"t": "gear", "key": "treasure"}},
                                   "menxia": server.menxia_view(g), "stored": {}, "responses": {}})
    row = page[page.index('class="wrow heirloom"'):]
    assert row.index('data-act="seal-act"') < row.index("</section>") and "引將・剩 2 次" in row


def test_a_used_up_or_cooling_act_greys_the_button_and_says_why():
    c, w, m = _view("yunzhuan")
    _use(c, w)
    m = _do(c, w, "懷璽", server.main_view, now=20.0)
    act = m["status"]["seal"]["act"]
    assert not act["ok"] and "之後才能再起用" in act["why"] and "生效中" in act["live"]
    row = run(m, 'return H.heirloomRow({name: "雲篆", effect_text: "x"}, H.sealActNow());')
    assert re.search(r'data-act="seal-act" disabled title="[^"]*之後才能再起用', row)
    assert row.count('<small class="rwhy">') == 2 and "生效中" in row  # 原因與生效中的那一句寫在這一列底下（手機沒有 title 可看）
    page = run(m, "return H.pageJianghu();")
    assert "獨門行動・頒詔：這一季還能起用 1 次" in page


def test_the_layer_lists_every_figure_with_where_he_is_and_greys_the_ones_here():
    """選目標那一層：招牌寫行動名、右上剩幾次、一人一列寫此刻在哪；長社的皇甫嵩、朱儁灰掉寫「已經在這裡」；還沒出場的彭脫不列。"""
    c, w, m = _view(at="changshe")
    html = _layer(m)
    assert '<span class="shop-sign">引將</span>' in html and "剩 2 次" in html and 'data-act="seal-act-close"' in html
    rows = {name: (tid, off, why) for name, tid, off, why in _rows(html)}
    assert rows["波才"] == ("bocai", False, "") and "此刻在黃巾別部營寨" in html
    assert rows["皇甫嵩"] == ("huangfusong", True, "已經在這裡") and rows["朱儁"][1:] == (True, "已經在這裡")
    assert "彭脫" not in rows
    assert html.count("<b>") == len(m["status"]["seal"]["act"]["targets"])


def test_a_pick_asks_first_then_posts_seal_use():
    """點一列：先問（伺服器的問句，{target} 換成名字），按「起用」才送 /api/do/seal_use {target, side}；送出時那一層收起。"""
    c, w, m = _view(at="changshe")
    out = click(m, [{"act": "seal-act"}, {"act": "seal-pick", "id": "bocai"}, {"act": "ask-yes"}])
    opened, asked, sent = out["out"]
    assert 'class="shop-layer shop-seal"' in opened["app"] and opened["open"] is True
    assert "起用『玄紐』，把波才引到長社坐鎮一日？" in asked["asked"] and "還剩 1 次" in asked["asked"]
    assert out["calls"] == [["/api/do/seal_use", {"target": "bocai", "side": ""}]]
    assert sent["open"] is False and "shop-seal" not in sent["app"]


def test_a_greyed_row_cannot_be_picked():
    c, w, m = _view(at="changshe")
    out = click(m, [{"act": "seal-act"}, {"act": "seal-pick", "id": "nobody"}])
    assert out["out"][1]["asked"] == "" and out["calls"] == []


def test_banzhao_and_chenglu_ask_straight_away():
    """頒詔、承露不用目標：按了鈕直接問，不開那一層。"""
    for shard, line in (("yunzhuan", "頒詔天下一日"), ("chenglu", "讓甘露降在潁川汝南一日")):
        c, w, m = _view(shard, at="yingchuan_wilds")
        out = click(m, [{"act": "seal-act"}, {"act": "ask-yes"}])
        first = out["out"][0]
        assert first["open"] is False and "shop-seal" not in first["app"] and line in first["asked"], (shard, first["asked"])
        assert out["calls"] == [["/api/do/seal_use", {"target": "", "side": ""}]]


def test_a_ranger_picks_a_side_like_a_shop_tab_before_any_line():
    """散人起用傳檄：最上面兩顆店面頁籤「這一次算官軍／黃巾軍」；還沒挑時每一列都灰著、寫要先挑；挑了才按得下去，問句與送出都帶那一軍。"""
    c, w, m = _view("chizhang", side=None)
    html = _layer(m)
    assert html.count('data-act="seal-side"') == 2 and "這一次算官軍" in html and "這一次算黃巾軍" in html
    assert all(off for _, _, off, _ in _rows(html)) and "先挑這一次照哪一軍算" in html
    picked = _layer(m, {"sealSide": "guan"})
    assert not any(off for _, _, off, _ in _rows(picked)) and 'class="shop-page on" data-act="seal-side" data-side="guan"' in picked
    out = click(m, [{"act": "seal-act"}, {"act": "seal-side", "side": "guan"}, {"act": "seal-pick", "id": "yingru"}, {"act": "ask-yes"}])
    assert "替官軍傳檄潁川汝南一日" in out["out"][2]["asked"]
    assert out["calls"] == [["/api/do/seal_use", {"target": "yingru", "side": "guan"}]]


def test_a_faction_member_sees_no_side_tabs():
    c, w, m = _view("chizhang", side="guan")
    html = _layer(m)
    assert 'data-act="seal-side"' not in html and not any(off for _, _, off, _ in _rows(html))


def test_switched_off_there_is_no_button_no_line_and_no_layer():
    c, w, m = _view(on=False)
    assert "act" not in m["status"]["seal"]
    row = run(m, 'return H.heirloomRow({name: "玄紐", effect_text: "x"}, H.sealActNow());')
    assert "data-act" not in row and "wbtns" not in row
    page = run(m, "return H.pageJianghu();")
    assert "獨門行動" not in page and "seal-act-go" not in page
    out = click(m, [{"act": "seal-act"}])
    assert out["out"][0]["open"] is False and "shop-seal" not in out["out"][0]["app"] and out["calls"] == []


def test_a_shard_without_an_act_draws_nothing_extra():
    c, w, g = _holder("chishou", at="changshe")
    c.seal["chishou"].act = None  # 第 3 批起七片都有行動：沒有行動的那一條路（測試內容、改版關著還走它）拿掉這一片的行動來測
    m = server.main_view(g)
    assert m["status"]["seal"]["act"] is None
    assert "獨門行動" not in run(m, "return H.pageJianghu();")
    assert "seal-act" not in run(m, 'return H.heirloomRow({name: "螭首", effect_text: "x"}, H.sealActNow());')


def test_a_poll_redraws_only_on_change_and_closes_the_layer_when_the_shard_is_gone():
    """輪詢：資料沒變不動那一層；少了一個名額（剩的次數變了）只換那一層；碎片沒了（被搶走）就收起。"""
    c, w, m = _view(at="changshe")
    fewer = json.loads(json.dumps(m))
    fewer["status"]["seal"]["act"]["left"] = 1
    gone = {**m, "status": {**m["status"], "seal": None}}
    script = """
      let removed = false;
      const layer = { outerHTML: "OLD", remove() { removed = true; }, querySelector: () => ({ scrollTop: 0 }) };
      T.qs[".shop-seal"] = layer;
      H.sealActPolled(H.S.main);
      const same = layer.outerHTML;
      const was = H.S.main; H.S.main = FEWER; H.sealActPolled(was);
      const changed = layer.outerHTML.includes("剩 1 次");
      const before = H.S.main; H.S.main = GONE; H.sealActPolled(before);
      return [same, changed, removed, H.S.sealAct];
    """.replace("FEWER", json.dumps(fewer, ensure_ascii=False)).replace("GONE", json.dumps(gone, ensure_ascii=False))
    assert run(m, script, S={"tab": "jianghu", "sealAct": True}) == ["OLD", True, True, False]


def test_the_text_is_escaped():
    c, w, m = _view(at="changshe")
    act = m["status"]["seal"]["act"]
    act["targets"][0]["name"], act["text"] = "<b>壞</b>", "<i>說明</i>"
    html = _layer(m)
    assert "<b><b>壞</b></b>" not in html and "&lt;b&gt;壞&lt;/b&gt;" in html and "&lt;i&gt;說明&lt;/i&gt;" in html


def test_the_layer_css_follows_the_shop_and_the_640_column():
    """窄螢幕不橫捲靠店面那一層既有的排法（.shop-row 是 flex、名字那一格可以縮、鈕不折），電腦寬照遊戲那一欄 640px（FB-225）；
    自己寫的字級一律 em（店面那一段不必補電腦寬的雙胞胎，tests/test_desktop_type.py）。"""
    assert ".shop-seal .seal-row .winfo { min-width: 0; }" in CSS
    seal_rules = [line for line in CSS.splitlines() if ".shop-seal" in line]
    assert seal_rules and not any(re.search(r"font(-size)?:[^;]*\d+px", line) for line in seal_rules if "shop-layer.shop-seal" not in line)
    desk = CSS[CSS.rindex("@media (min-width: 641px)"):]
    assert ".shop-layer.shop-seal { font-size: 17px; background-color: var(--paper); background-size: min(100%, 640px) 100%" in desk
    first = CSS.index("@media (min-width: 641px)")
    assert CSS.index(".shop-layer.shop-seal {") > first  # 電腦寬那一段以後（test_bounty_tags 照第一個 641px 切手機那一半）


# ── 第 3 批：鎮地、補缺（領地爭奪打開的 21 天季；tests/test_seal_acts3.py 的建法）──

def _land(shard, *, side, at):
    from test_seal_acts3 import _holder as land_holder

    return land_holder(shard, side=side, at=at)


def test_zhendi_lists_blocks_with_a_line_under_each():
    """鎮地那一層：一塊地一列、鈕寫「鎮住」，底下那一小行寫對面推到多少；問句帶自家。"""
    from tianxia import conquest as cq
    from test_seal_acts3 import _season

    c, w, g = _land("chishou", side="guan", at="zhuo_county")
    _season(c, w, lambda wd: cq.push(wd, c, "zhuo_county", "huang", "巾甲", 30, "attack"))
    m = _do(c, w, "懷璽", server.main_view, now=20.0)
    html = _layer(m)
    rows = {name: (tid, off) for name, tid, off, _ in _rows(html)}
    assert rows["涿郡"] == ("zhuo_county", False) and "汝南" not in rows
    assert "黃巾軍推到 30" in html and ">鎮住</button>" in html and "指定一塊此刻佔著的地" in html
    out = click(m, [{"act": "seal-act"}, {"act": "seal-pick", "id": "zhuo_county"}])
    assert "起用『螭首』，替官軍鎮住涿郡半日？" in out["out"][1]["asked"]


def test_a_ranger_sees_only_the_blocks_of_the_army_picked():
    """散人鎮地：還沒挑邊不列地、寫要先挑；挑了哪一軍只列那一軍的地，送出帶那一軍。"""
    c, w, g = _land("chishou", side=None, at="yingchuan")
    m = server.main_view(g)
    html = _layer(m)
    assert _rows(html) == [] and "先挑這一次照哪一軍算" in html and html.count('data-act="seal-side"') == 2
    huang = {name for name, *_ in _rows(_layer(m, {"sealSide": "huang"}))}
    guan = {name for name, *_ in _rows(_layer(m, {"sealSide": "guan"}))}
    assert "汝南" in huang and "汝南" not in guan and "涿郡" in guan and not huang & guan
    out = click(m, [{"act": "seal-act"}, {"act": "seal-side", "side": "huang"}, {"act": "seal-pick", "id": "runan"}, {"act": "ask-yes"}])
    assert "替黃巾軍鎮住汝南半日" in out["out"][2]["asked"]
    assert out["calls"] == [["/api/do/seal_use", {"target": "runan", "side": "huang"}]]


def test_a_ranger_picking_an_army_with_nothing_to_mend_is_told_so():
    from tianxia import conquest as cq
    from test_seal_acts3 import _season

    c, w, g = _land("jinjiao", side=None, at="yingchuan")
    _season(c, w, lambda wd: cq.push(wd, c, "runan", "guan", "官甲", 100, "attack"), now=100.0)
    m = _do(c, w, "懷璽", server.main_view, now=200.0)
    guan = _layer(m, {"sealSide": "guan"})
    assert _rows(guan) == [] and "這一邊此刻沒有能指定的地方。" in guan
    huang = _layer(m, {"sealSide": "huang"})
    assert [(name, tid) for name, tid, _, _ in _rows(huang)] == [("汝南", "runan")] and "被官軍翻走・" in huang and ">補回</button>" in huang


def test_fb645_every_block_greyed_still_opens_the_layer_and_lists_them():
    """FB-645：剛被翻走的地全都補不了時，鈕照樣打得開那一層（不是 primary）、那幾塊灰著各寫原因、上面寫整顆的原因；灰的那一列按了不問。
    一塊都沒有、或在間隔裡（targets 是空的）照舊灰掉不開。"""
    from tianxia import conquest as cq
    from tianxia.state import SealAct
    from test_seal_acts3 import _season

    c, w, g = _land("jinjiao", side="huang", at="runan")
    _season(c, w, lambda wd: cq.push(wd, c, "runan", "guan", "官甲", 100, "attack"), now=100.0)
    _season(c, w, lambda wd: wd.seal_acts.append(SealAct(kind="bujue", shard="jinjiao", start=50.0, until=50.0, target="runan",
                                                         side="huang")), now=110.0)
    m = _do(c, w, "懷璽", server.main_view, now=200.0)
    act = m["status"]["seal"]["act"]
    row = run(m, 'return H.heirloomRow({name: "金角", effect_text: "x"}, H.sealActNow());')
    assert re.search(r'<button class="btn small" data-act="seal-act">補缺・剩 2 次</button>', row)
    assert f'<small class="rwhy">{act["why"]}</small>' in row
    out = click(m, [{"act": "seal-act"}, {"act": "seal-pick", "id": "runan"}])
    opened, picked = out["out"]
    assert opened["open"] is True and f'<p class="shop-warn">{act["why"]}</p>' in opened["app"]
    assert _rows(opened["app"]) == [("汝南", "runan", True, "這一季已經補過一次")] and "被官軍翻走・" in opened["app"]
    assert picked["asked"] == "" and out["calls"] == []
    c, w, g = _land("jinjiao", side="huang", at="runan")  # 還沒丟過地：照舊灰掉、不開
    m = server.main_view(g)
    assert re.search(r'data-act="seal-act" disabled', run(m, 'return H.heirloomRow({name: "金角", effect_text: "x"}, H.sealActNow());'))
    out = click(m, [{"act": "seal-act"}])
    assert out["out"][0]["open"] is not True and "shop-seal" not in out["out"][0]["app"]


def test_without_conquest_the_card_line_says_why_not_how_many():
    """領地爭奪關著的季（PM 2026-10-22 打開之前正式內容的三種季；現在要明講關掉）：鎮地的鈕灰著、碎片卡那一行寫原因（不寫「還能起用 2 次」，
    FB-626 那種一句說能用一句說不能）。"""
    c, w, m = _view("chishou", at="changshe", conquest_on=False)
    act = m["status"]["seal"]["act"]
    assert act["idle"] and not act["ok"]
    assert "獨門行動・鎮地：這一季沒有領地爭奪，起用不了。" in run(m, "return H.pageJianghu();")
    row = run(m, 'return H.heirloomRow({name: "螭首", effect_text: "x"}, H.sealActNow());')
    assert re.search(r'data-act="seal-act" disabled title="這一季沒有領地爭奪', row)
    c, w, m = _view("xuanniu", at="changshe", conquest_on=False)
    assert "獨門行動・引將：這一季還能起用 2 次" in run(m, "return H.pageJianghu();")  # 別的照舊


def _bot_world(bot: bool):
    """甲客懷著玄紐（伺服器假人或真人），一個旁觀客在別處；回旁觀客的 /api/main。"""
    c = real_content("season21")
    c.config.auto_open_first_season = True
    w = open_world(Path(tempfile.mkdtemp(prefix="seal2w-")) / "t.db")

    def _give(st):
        s = seal.filled(st.seal, c).shards["xuanniu"]
        s.state, s.holder, s.since_season = "held", "甲客", 0

    w.mutate(_give)
    holder = _person(c, w, "甲客", side="huang", at="changshe")
    if bot:
        holder.state.player.bot = BotProfile(personality="普通", seed=1, faction="huang", season_number=1)
        CharacterStore(w.db).save(holder.state)
    _person(c, w, "旁觀客", side="huang", at="yingchuan")
    viewer = Game(c, CharacterStore(w.db).load("旁觀客"), random.Random(0), w)
    viewer.client = None
    viewer.sync(10.0)
    return server.main_view(viewer)


def test_nobody_can_tell_a_bot_holder_from_a_human_one():
    """假人看不出來：懷璽的是假人或真人，旁觀客的江湖頁（含碎片卡那一格）一個字不差；旁觀客沒有碎片，沒有鈕也沒有那一行。"""
    bot, human = _bot_world(True), _bot_world(False)
    assert bot["status"]["seal"] is None and human["status"]["seal"] is None
    a, b = run(bot, "return H.pageJianghu();"), run(human, "return H.pageJianghu();")
    assert a == b and "獨門行動" not in a
