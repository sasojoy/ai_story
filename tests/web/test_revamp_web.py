"""介面重整（2026-11-05，Joy「操作簡單 回饋直覺 畫面有質感」，挑「四塊一次做」）的網頁那一半：江湖頁閒著時是場景卡、要事一張卡、
四顆行動、此地可為一排圓章、此地人物一排；點大勢人物打開「點人物之後」（交談、護衛、往來紀錄）；跟人物說話整頁換成浮在最上層的對話框；
俠客頁四分頁、身上那一門的抽屜能當場換；管理頁四格狀態、分頁籤、危險區長按。真的引擎（正式內容 week7）給的 /api/main。"""
from __future__ import annotations

import random
from pathlib import Path

import pytest
from conftest import real_content
from test_prologue_web import run as run_classic

import server
import webharness
from tianxia.engine import Game

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


def run(m, script, *, S=None, menxia=None):
    return run_classic(m, script, S=S, menxia=menxia)


@pytest.fixture
def wan(world):
    """正式內容 week7、開了季、站在大將軍府（何進在）、投靠官軍、名望夠求見。"""
    content = real_content("week7")
    world.seed_first_season(content)
    world.open_season(content, now=0.0)
    game = Game.new(content, "沈浪", rng=random.Random(0), world=world, graduated=True)
    game.state.player.location = "dajiangjun_fu"
    game.state.player.faction = "guan"
    game.state.player.stats["fame"] = 200
    game.state.pending_event = None  # 開局那一則（opening_gate）先放下
    for _ in range(4):  # 開季準備（挑成長配比……）做完，回到閒著的選單
        ids = [o.id for o in game.options(odds=False) if o.enabled]
        if "act:explore" in ids:
            break
        game.choose(next(i for i in ids if i != "growth:custom"))
    return game


def test_the_idle_page_has_the_duty_card_the_seal_row_and_the_people_row(wan):
    m = server.main_view(wan)
    figs = {f["id"]: f for f in m["figures_here"]}
    assert figs["hejin"]["talk"]["via"] == ["act:call", "call:hejin"] and figs["hejin"]["side"] == "官軍"  # 兩位人物：先打開名單再指名
    page = run(m, "return H.pageJianghu();")
    assert 'class="card scene rv' in page and 'class="act-bar"' in page
    assert "此地還能做" not in page  # 摺疊換成了此地可為那一排
    assert 'class="here-row"' in page and 'class="people-row"' in page
    assert 'data-act="fig-open" data-id="hejin"' in page
    assert "hire:" not in page.split('class="here-row"')[1]  # 招募不在此地可為（搬去酒肆）
    assert "aid:guard:" not in page.split('class="here-row"')[1]  # 護衛在點了人物之後
    assert "/static/img/acts/explore.webp" in page


def test_tapping_a_figure_offers_talk_guard_and_the_log(wan):
    m = server.main_view(wan)
    page = run(m, 'H.S.fig = "hejin"; return H.pageJianghu();')
    pick = page.split('class="vn-layer pick"')[1]
    assert 'data-act="fig-talk" data-id="hejin"' in pick and 'data-act="fig-log" data-id="hejin"' in pick
    assert "護衛" in pick
    assert "/static/img/figures/full/hejin.webp" in pick


def test_talking_to_a_figure_draws_the_overlay_with_the_same_options(wan):
    m = server.main_view(wan)
    m["talk"] = {"id": "zhujun", "name": "朱儁", "side": "官軍", "affinity": 7, "face": "/static/img/figures/full/zhujun.webp"}
    m["options"] = [{"id": "talk:0", "label": "「請將軍指點。」", "enabled": True}, {"id": "talk:say", "label": "自己說…", "enabled": True},
                    {"id": "talk:leave", "label": "告辭", "enabled": True}]
    m["scene"] = "<p><strong>朱儁</strong>（情誼 7）</p>\n<p>「你來了。」</p>"
    m["art"] = None
    page = run(m, "return H.pageJianghu();")
    assert 'class="vn-layer talk"' in page
    assert 'data-id="talk:0"' in page and 'data-id="talk:leave"' in page
    assert "「你來了。」" in page and "（情誼 7）" not in page  # 名字在名牌上、情誼在框底，不寫第二次
    assert "情誼 7" in page


def test_a_long_reply_never_hides_the_leave_button(wan):
    """Joy 2026-11-07「跟人物對話時會因為句子長被卡到沒辦法按告辭離開」：告辭釘在右上角、不跟選項擠，
    選項自己捲、對話框有上限自己捲。"""
    m = server.main_view(wan)
    m["talk"] = {"id": "zhujun", "name": "朱儁", "side": "官軍", "affinity": 7, "face": None}
    m["options"] = [{"id": f"talk:{i}", "label": "「" + "將軍所言甚是，" * 6 + "」", "enabled": True} for i in range(4)]
    m["options"] += [{"id": "talk:say", "label": "自己說…", "enabled": True}, {"id": "talk:leave", "label": "告辭", "enabled": True}]
    m["scene"] = "<p>「" + "黃巾賊勢正盛，宛城一線吃緊，你我須得從長計議。" * 20 + "」</p>"
    m["art"] = None
    page = run(m, "return H.pageJianghu();")
    pinned = page.split('class="vn-leave"')[1].split("</div>")[0]
    assert 'data-id="talk:leave"' in pinned
    menu = page.split('class="vn-menu"')[1].split('class="vn-box')[0]
    assert 'data-id="talk:leave"' not in menu and 'data-id="talk:3"' in menu
    css = (Path(server.__file__).parent / "web" / "style.css").read_text(encoding="utf-8")
    assert ".vn-layer.talk .vn-paper { max-height:" in css and ".vn-leave {" in css


def test_the_log_groups_by_day_and_shows_affinity_gains(wan):
    m = server.main_view(wan)
    log = {"id": "zhujun", "name": "朱儁", "face": None, "affinity": 9, "meets": 1, "more": False, "season": "now", "lines": [
        {"id": 2, "stamp": "第 3 天 08:10", "place": "宛城", "role": "assistant", "text": "「坐。」", "gain": 5},
        {"id": 1, "stamp": "第 3 天 08:10", "place": "宛城", "role": "user", "text": "「將軍。」", "gain": 0},
    ]}
    page = run(m, f"H.S.figLog = {__import__('json').dumps(log, ensure_ascii=False)}; return H.pageJianghu();")
    body = page.split('class="vn-layer log"')[1]
    assert "第 3 天・宛城" in body and "情誼 +5" in body
    assert body.index("「將軍。」") < body.index("「坐。」")  # 同一天照說話的先後


def test_the_hero_page_has_four_tabs_and_the_worn_drawer_lists_swaps(wan):
    m, x = server.main_view(wan), server.menxia_view(wan)
    page = run(m, "return H.pagePractice();", menxia=x)
    for key in ("arts", "gear", "mates", "attrs"):
        assert f'data-act="hero-tab" data-tab="{key}"' in page
    worn = next(a for a in x["owned_arts"] if a["worn"])
    drawer = run(m, f'H.S.pdrawer = {{ t: "worn", key: "{worn["kind"]}" }}; return H.pagePractice();', menxia=x)
    assert "換一門" in drawer or "功法庫裡沒有別的" in drawer
    attrs = run(m, 'H.S.heroTab = "attrs"; return H.pagePractice();', menxia=x)
    assert "經驗與成長" in attrs


def test_the_attrs_tab_shows_each_number_once_and_folds_every_explanation(wan):
    """Joy 2026-11-06「這一定要預設展開那麼多說明？而且上面已經有屬性了下面還有文字版」：屬性一份、名望善惡一份，
    說明（五項各管什麼、名聲的階梯與來源）點「？」「怎麼來」才開，心得提示一行，同伴不在這裡重複（門下那一頁有）。"""
    m, x = server.main_view(wan), server.menxia_view(wan)
    m["status"]["hint"] = "你已攢下 24 點心得，去「煉製」把兩個意境合成新的。"
    s = m["status"]
    page = run(m, 'H.S.heroTab = "attrs"; return H.pagePractice();', menxia=x)
    for name, value, _ in s["attrs"]:
        assert page.count(f"{name} {value}") == 0  # 文字版那一行拿掉了：只剩上面那一格一欄
    assert page.count("<em>名望</em>") == 1 and "rn-strip" not in page and "rn-src" not in page
    assert 'data-act="attr-help"' in page and 'class="stat-uses"' not in page
    assert 'class="xinde-tip"' in page and "🧍" not in page
    # Joy 11/6「屬性那邊還有放態勢」：只放自己的成長——態勢在江湖頁、修練的規矩在武學那一頁、等級與氣血在人像卡與狀態列
    assert "態勢" not in page and "修練的規矩" not in page and "第 " + str(s["level"]) + " 級" not in page.split('class="hero-tabs"')[1]
    assert "氣血 " not in page.split('class="hero-tabs"')[0].split('class="hero-sub"')[1].split("</div></div>")[0]
    arts = run(m, 'H.S.heroTab = "arts"; return H.pagePractice();', menxia=x)
    assert "修練的規矩" in arts
    opened = run(m, 'H.S.heroTab = "attrs"; return H.pagePractice();', menxia=x, S={"attrHelp": True, "renownOpen": True, "xindeOpen": True})
    assert 'class="stat-uses"' in opened and 'class="rn-strip"' in opened and 'class="xinde-tip open"' in opened


def test_doable_unfinished_business_goes_first_and_not_yet_goes_last(wan):
    """Joy 2026-11-06「未了之事如果是可以做的時候優先級應該做高，如果時機未到可以放在後面」：此地可為與「全部」那一串都照這個排。"""
    m = server.main_view(wan)
    opt = lambda i, label, on: {"id": i, "label": label, "enabled": on, "note": ""}  # noqa: E731
    extras = [opt("act:shop", "鐵匠鋪", True), opt("story:a", "未了之事：去山裡找藥", True), opt("act:arena", "擂台（今天沒開）", False),
              opt("story:b", "未了之事：等三更（時機未到）", False), opt("act:mounts", "馬市", True)]
    order = run(m, f"return H.hereSort({__import__('json').dumps(extras, ensure_ascii=False)}, [], {{}}).map((o) => o.id).join(',');")
    assert order == "story:a,act:shop,act:mounts,act:arena,story:b"


def test_the_duty_card_leads_with_what_can_be_done_now(wan):
    m = server.main_view(wan)
    blocks = {"orderCard": '<section><h3>軍令</h3><button class="btn" disabled data-act="choose" data-id="x">還不能交</button></section>',
              "bountyCard": '<section><h3>懸賞</h3><button class="btn" data-act="choose" data-id="y">接</button></section>'}
    keys = run(m, f"return H.dutyParts(H.S.main, {__import__('json').dumps(blocks)}).filter((p) => p.html).map((p) => p.key).join(',');")
    assert keys == "bounty,orders"


def test_the_admin_page_has_tiles_tabs_and_a_hold_to_confirm_danger_zone(wan):
    wan.state.player.name = "Rayal"
    m = server.main_view(wan)
    page = run(m, "return H.adminHtml();", S={"admin": server.admin_choices(wan)})
    assert len(__import__("re").findall(r'class="ad-tile( hot)?"', page)) == 4 and 'data-act="ad-tab"' in page
    assert 'data-act="ad-hold" data-op="end_season"' in page and 'data-act="ad-hold" data-op="next_season"' in page
    assert 'data-act="admin" data-op="end_season"' not in page  # 收季只在危險區、要長按


def test_tapping_a_figure_shows_who_they_are_for_players_new_to_the_era(wan):
    """Joy 11/6「不是所有玩家都那麼了解三國裡面的角色」：點人物那一層寫身分、是誰、本性（content/figure_intros.json）；
    性子隨互動變了（另一串做）時多「如今」與變化紀錄。每一位大勢人物都有一份。"""
    import json

    figures = json.loads((server.ROOT / "content" / "figures.json").read_text(encoding="utf-8"))
    assert all(server.figure_intro(f["id"]) and server.figure_intro(f["id"])["nature"] for f in figures)
    m = server.main_view(wan)
    hejin = next(f for f in m["figures_here"] if f["id"] == "hejin")
    assert hejin["intro"]["role"] and hejin["intro"]["now"] is None and hejin["intro"]["history"] == []
    pick = run(m, 'H.S.fig = "hejin"; return H.pageJianghu();').split('class="vn-layer pick"')[1]
    assert 'class="vn-intro"' in pick and hejin["intro"]["who"] in pick and "<b>本性</b>" in pick and "vi-now" not in pick and "vi-hist" not in pick
    # 每樣只寫一次（PM 11/6）：陣營只在名牌旁的籤（身分行是「大將軍」不是「官軍・大將軍」），情誼只在「交談」鈕底下
    assert pick.count("官軍") == 1 and '<p class="vi-role">大將軍</p>' in pick and pick.count(f"情誼 {hejin['affinity']}") == 1 and "vn-foot" not in pick
    hejin["intro"].update(now="如今的樣子", history=["第 1 週・週五 起，沒那麼優柔了"])
    pick = run(m, 'H.S.fig = "hejin"; return H.pageJianghu();').split('class="vn-layer pick"')[1]
    assert '<p class="vi-now"><b>如今</b><span>如今的樣子</span></p>' in pick and "<li>第 1 週・週五 起，沒那麼優柔了</li>" in pick
