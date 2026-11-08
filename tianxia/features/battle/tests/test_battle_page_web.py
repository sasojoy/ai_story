"""battle 這一包的測試，從 tests/web/test_jianghu_page_web.py 拆來（全部拆包第 61 批，只搬位置、不改斷言）。"""
from __future__ import annotations
import re
import pytest
import server
import random
from tianxia.engine import Game
from test_prologue import _to_step
from tianxia.engine import Game
from test_prologue_web import run as run_prologue_web
from jianghu_kit import (  # noqa: F401
    CLICK, ROW_ATTRS, SHOWDOWN_BOX, _consts, _consts_fb105, _fight_round, _folded, _muster, _note_html, _page, _player,
    _round, _scene, _sided, _text, battle, node,
)

pytestmark = pytest.mark.whole_content


@node
def test_a_gamble_that_quotes_a_participants_line_does_not_unfold_it(battle):
    """審查 M1：放手一搏的原文與模型的故事照字寫進戰報（最近五段都在戰場那一塊）。有人寫「你已經倒下」「這回合不出手」，
    每個觀戰的人的戰場也不能因此整段攤開：參戰者的那一句只認戰場那一塊的最後一段（引擎寫看戰場的原因的地方）。"""
    watcher, fighter = battle
    fighter.submit_battle_custom_action("你已經倒下這回合不出手", 35, ("他大喊：你已經倒下了！", "他說這回合不出手，轉身就走。"))
    m = server.main_view(watcher)
    battle_part = m["scene"].split("<hr />", 1)[0]
    assert "你已經倒下這回合不出手" in battle_part and "這場決戰在南陽" in battle_part.rsplit("<p>", 1)[1]
    scene = _scene(run_prologue_web(m, "return H.pageJianghu();"))
    assert scene.startswith(_folded(m) + "\n<hr />")


@node
def test_tapping_opens_it_and_it_stays_open_while_the_rounds_go_on_until_folded(battle):
    watcher, fighter = battle
    first = server.main_view(watcher)
    _fight_round(fighter)
    second = server.main_view(watcher)
    assert _round(second) == _round(first) + 1
    script = CLICK + """return (async () => {
      H.S.tab = "jianghu"; H.renderPage(); const folded = T.els.page.innerHTML;
      const opened = await tap("battle-open"); const key = H.S.battleOpen;
      const was = H.S.main; H.setMain(H.S.next); await H.refreshPage(was); const polled = T.els.page.innerHTML;
      const shut = await tap("battle-shut");
      return { folded, opened, key, polled, shut, after: H.S.battleOpen };
    })();"""
    out = run_prologue_web(first, script, S={"next": second})
    shut_btn = (f'<p class="battle-shut"><button class="linkish" data-act="battle-shut" aria-expanded="true">'
                f'{_consts()["shut"]}</button></p>')
    assert _folded(first) in out["folded"]
    battle_first = first["scene"].split("<hr />", 1)[0]
    assert _sided(battle_first + shut_btn) in _text(_scene(out["opened"])) and out["key"] == "宛城之戰"  # 整段攤開，記的是戰場的名字
    battle_second = second["scene"].split("<hr />", 1)[0]
    assert _sided(battle_second + shut_btn) in _text(_scene(out["polled"]))  # 下一回合輪詢重畫：照舊攤開，寫的是新的回合
    assert _folded(second) in out["shut"] and out["after"] is None  # 按收起：收回一行（新的回合數）


# ── 參戰的人、集結時：照舊 ─────────────────────────────


@node
def test_a_participant_sees_the_whole_battle(battle):
    _, fighter = battle
    m = server.main_view(fighter)
    assert "<hr />" not in m["scene"] and "battle:act:" in "".join(o["id"] for o in m["options"])
    scene = _scene(run_prologue_web(m, "return H.pageJianghu();"))
    assert "battle-fold" not in scene and "這一回合" in scene


@node
def test_a_participant_who_walked_out_of_the_region_is_not_folded(battle):
    """參戰後離開了南陽（這回合不出手、回去就能再出手）：他是這一場的人，戰場照舊整段。"""
    _, fighter = battle
    fighter.state.player.location = "yingchuan"
    fighter._sync_battle_presence()  # noqa: SLF001  出發、抵達時引擎自己記；這裡直接把人放到潁川
    m = server.main_view(fighter)
    assert "<hr />" in m["scene"] and "這回合不出手" in m["scene"]
    scene = _scene(run_prologue_web(m, "return H.pageJianghu();"))
    assert "battle-fold" not in scene and "這一回合" in scene


@node
def test_a_scene_with_enlist_buttons_on_the_name_line_is_not_folded(battle, on):
    """審查 M5：名字那一行有加入或臨時投效的鈕（musterJoins）時不收——收了的話那幾顆鈕就沒地方畫。開打後人在決戰的大區、
    還沒投效的散人就是這一種：引擎在戰場底下接自己眼前的事（FB-109），網頁照舊整段、鈕排在名字那一行。"""
    drifter = server.main_view(_player(on, "散人丙", None, "wan_city"))
    assert [o["id"] for o in drifter["options"] if o["id"].startswith("battle:")] == ["battle:enlist:guan", "battle:enlist:huang"]
    assert "<hr />" in drifter["scene"] and "回合" in drifter["scene"].split("<hr />", 1)[0]
    scene = _scene(run_prologue_web(drifter, "return H.pageJianghu();"))
    assert "battle-fold" not in scene and "這一回合" in scene
    assert scene.startswith('<div class="muster-head"><p><strong>宛城之戰</strong></p>')
    assert re.findall(r'data-id="(battle:enlist:\w+)"', scene) == ["battle:enlist:guan", "battle:enlist:huang"]


def _start_fighting(game):
    """集結時間撥到過去，再讀一次選單：options() 把全服戰鬥追到現在，這一場就開打。main_view 先讀場景（不推進戰鬥）、
    最後才讀選單，所以要在它之前先推進，不然場景還寫著集結、選單已經是開打的。"""
    game.world.mutate_battle(lambda b: setattr(b, "muster_deadline_real", -1.0))
    game.options()
    assert game.world.get_battle().phase == "active"


def _fold(page):
    """此地可為的「全部」清單（舊的「此地還能做」摺疊；入伍段有發光的鈕時照舊是摺疊）。"""
    hit = re.search(r'<div class="sheet here-all"[^>]*>(.*?)</div></div>$', page, re.S) or re.search(r'<details class="fold here"[^>]*>(.*?)</details>', page, re.S)
    return hit.group(1) if hit else ""


# ── 加入的鈕在場景卡戰場名字那一行，不在摺疊裡 ───────────────────────


@node
def test_the_join_button_sits_by_the_battles_name_and_leaves_the_fold(on):
    m = server.main_view(_muster(on, "guan"))
    assert any(o["id"] == "battle:join:guan" and o["enabled"] for o in m["options"]) and "act:explore" in [o["id"] for o in m["options"]]
    page = _page(m)
    scene = _scene(page)
    head = re.search(r'<div class="muster-head">(.*?</div>)</div>', scene, re.S).group(1)
    # 同一行：戰場名字、說在這裡報名的那一小句（箭頭指向右邊的鈕）、加入的鈕
    assert head == ('<p><strong>廣宗決戰</strong></p>' + _note_html("join")
                    + f'<div class="options muster-join" {ROW_ATTRS}><button class="btn small primary" data-act="choose" '
                    'data-id="battle:join:guan"><span>加入【官軍】</span></button></div>')
    assert _consts_fb105()["arrow"]["join"] == "→"  # 鈕在右邊
    assert "battle:join:guan" not in _fold(page) and page.count('data-id="battle:join:guan"') == 1
    assert 'class="here-row"' in page  # 此地可為照樣在（求見、拜師、巡哨），只是少了加入那一顆
    # 集結那一句（戰鬥引擎寫的）照伺服器給的原樣跟在名字那一行後面：網頁只換掉第一段（名字），其餘一個字不動
    rest = m["scene"].split("</p>\n", 1)[1]
    assert "集結中，還剩現實" in rest and scene.startswith('<div class="muster-head">') and rest in scene


@node
def test_a_drifters_two_enlist_buttons_get_their_own_row_under_the_name(on):
    m = server.main_view(_muster(on, None))
    page = _page(m)
    scene = _scene(page)
    title, note, row = re.search(
        r'<div class="muster-head"><p>(.*?)</p>(<span class="muster-note".*?</span></span>)'
        rf'<div class="options muster-join wide" {ROW_ATTRS}>(.*?)</div></div>', scene, re.S).groups()
    assert title == "<strong>廣宗決戰</strong>"
    assert note == _note_html("enlist") and _consts_fb105()["arrow"]["enlist"] == "↓"  # 在名字右邊、往下指那兩顆
    assert re.findall(r'data-id="(battle:enlist:\w+)"', row) == ["battle:enlist:guan", "battle:enlist:huang"]
    # 鈕上只寫括號前那一段（「只算這一場」在那一小句裡）
    labels = {o["id"]: o["label"] for o in m["options"]}
    assert re.findall(r"<span>(.*?)</span>", row) == [labels[i].split("（")[0] for i in ("battle:enlist:guan", "battle:enlist:huang")]
    assert all("（" in labels[i] for i in ("battle:enlist:guan", "battle:enlist:huang"))
    assert "battle:enlist" not in _fold(page)
    assert scene.endswith(m["scene"].split("</p>\n", 1)[1])  # 集結那一句照伺服器給的原樣


@node
def test_a_drifter_who_arrives_after_the_fighting_started_still_gets_the_row(on):
    """開打了還沒投效的散人（臨時投效照樣按得下去，試玩回饋 2026-10-08）：那兩顆一樣畫在名字底下，不收進摺疊。"""
    game = _muster(on, None)
    _start_fighting(game)
    m = server.main_view(game)
    assert "集結中" not in m["scene"] and "回合" in m["scene"]  # 場景是開打之後的戰場
    assert [o["id"] for o in m["options"] if o["id"].startswith("battle:")] == ["battle:enlist:guan", "battle:enlist:huang"]
    page = _page(m)
    assert re.search(rf'<div class="options muster-join wide" {ROW_ATTRS}>', _scene(page))
    assert "battle:enlist" not in _fold(page) and page.count('data-id="battle:enlist:guan"') == 1


@node
def test_a_late_comer_on_your_own_side_keeps_the_ordinary_join_late_button(on):
    """開打了才到的自己人：選單只有一顆「加入戰局」（battle:join_late），本來就看得到，照舊畫成一般的鈕；不搬到名字那一行。"""
    game = _muster(on, "guan")
    _start_fighting(game)
    m = server.main_view(game)
    assert "集結中" not in m["scene"]
    assert [o["id"] for o in m["options"]] == ["battle:join_late"]
    page = _page(m)
    assert "muster-" not in page and _scene(page) == m["scene"]
    assert re.search(r'<button class="btn " data-act="choose" data-id="battle:join_late" >', page)


@node
def test_once_you_joined_the_page_is_what_it_was(on):
    """已經加入（或投效過）：「已加入」是灰的那一顆，照舊收在摺疊裡，場景卡就是伺服器給的那一段，一個字不多。"""
    for who, first in (("guan", "battle:join:guan"), (None, "battle:enlist:guan")):
        game = _muster(on, who)
        game.choose(first)
        m = server.main_view(game)
        page = _page(m)
        assert "muster-" not in page, who
        # 大決戰優化（Joy 2026-11-06，方案甲）：戰場的名字寫在最上面的戰場面板（web/battle.js），場景卡不再寫第二次
        name = f'<p><strong>{m["battle_panel"]["name"]}</strong></p>\n'
        assert m["scene"].startswith(name) and _scene(page) == m["scene"].removeprefix(name), who
        assert first in _fold(page), who  # 灰的「已加入」／「已臨時投效」還在摺疊裡


@node
def test_someone_who_cannot_join_sees_no_change(on):
    """不在決戰的大區：選單上沒有加入，場景卡照伺服器給的。（豪強以前在這裡一旁觀戰；Joy 2026-10-13 起跟散人一樣臨時投效。）"""
    elsewhere = _muster(on, "guan", place="luzhi_camp", battle=None, name="乙")  # 黃巾決戰在潁川汝南，人在冀州
    for game in (elsewhere,):
        m = server.main_view(game)
        assert not any(o["id"].startswith("battle:") for o in m["options"])
        m["art"] = None  # 站在地點時場景卡上面有圖、地名那一段疊到圖上（減法季批 8，test_scene_art.py）：這裡比的是沒圖那一份文字
        page = _page(m)
        assert "muster-" not in page and _scene(page) == m["scene"]


@node
def test_with_an_event_open_the_join_button_still_sits_by_the_name_and_only_once(on):
    """集結時碰上事件（選單是一排選項、不是行動列）：加入照樣在名字那一行，不在選項裡再列一次；事件的選項照舊。"""
    game = _muster(on, "guan")
    game.state.pending_event = "jz_gz_forge"
    m = server.main_view(game)
    assert [o["id"] for o in m["options"]][0] == "battle:join:guan" and "act:explore" not in [o["id"] for o in m["options"]]
    page = _page(m)
    assert page.count('data-id="battle:join:guan"') == 1 and "muster-join" in _scene(page)
    assert 'data-id="choice:0"' in page


# ── 場景卡沒畫的時候，鈕照舊留在選單上 ─────────────────────────────


@node
def test_on_the_road_a_join_option_stays_in_the_menu(on):
    """在路上加入不了（引擎在路上不給這幾顆）；萬一選單上有，路上的場景卡收成兩行、不畫名字那一行：鈕照舊畫在選項裡，不搬、不見。"""
    m = server.main_view(_muster(on, "guan"))
    road = {**m, "on_road": True, "options": [o for o in m["options"] if o["id"] == "battle:join:guan"]}
    page = _page(road)
    assert "muster-" not in page
    assert re.search(r'<div class="options">\s*<button class="btn " data-act="choose" data-id="battle:join:guan" >', page)


@node
def test_while_the_master_talks_in_the_hut_the_enlist_buttons_stay_in_the_menu(on):
    """序章：草廬在潁川汝南，長社火攻集結時新角色在序章第 2 步以前就有投效兩顆（審查 M2 的情形）；現在序章裡引擎不給投效、
    場景也不畫戰場（FB-113），頁面上沒有參戰那一列。
    畫面這一層守的照舊：師父在說話（框在、眼前沒有事件）時草廬那張場景卡不畫（masterTalks），選單上萬一有投效鈕也不搬
    （搬了就沒地方畫、整個不見），照舊收在「此地還能做」的摺疊裡。"""
    game = Game.new(on, "沈浪", rng=random.Random(0), prologue=True)
    game.client = None
    _to_step(game, 1)
    game.world.start_battle(on.battles["changshe_fire"], now=game.now)
    m = server.main_view(game)
    assert m["prologue"] is not None and m["guide"] is not None
    assert not any(o["id"].startswith("battle:") for o in m["options"]) and "長社火攻" not in m["scene"]  # FB-113
    assert "muster-" not in _page(m)
    enlist = [{"id": f"battle:enlist:{side}", "label": f"臨時投效【{name}】（只算這一場）", "enabled": True, "wait": "", "confirm": ""}
              for side, name in (("guan", "官軍"), ("huang", "黃巾軍"))]
    stray = {**m, "options": enlist + m["options"]}
    assert not any(o["id"].startswith("choice:") for o in stray["options"]) and not stray["on_road"]
    page = _page(stray)
    assert '<section class="card scene">' not in page and "muster-" not in page  # 場景卡沒畫
    for o in enlist:
        assert page.count(f'data-id="{o["id"]}"') == 1 and o["id"] in _fold(page)


@node
def test_the_button_label_is_escaped(on):
    m = server.main_view(_muster(on, "guan"))
    odd = {**m, "options": [{**o, "label": "加入【<b>官軍</b>】"} if o["id"] == "battle:join:guan" else o for o in m["options"]]}
    scene = _scene(_page(odd))
    assert "<span>加入【&lt;b&gt;官軍&lt;/b&gt;】</span>" in scene and "<b>官軍" not in scene


# ── 原 test_fb360_escort_pick.py（整檔搬進來） ──
# FB-360（歷史武將同行 QA，2026-10-19，375×812）：名下有同伴的人按場景卡上的「加入」之後，挑同伴的四顆（battle:escort:*）
# 收在「此地還能做」的摺疊裡，第一屏看起來什麼都沒變——還沒加入，卻以為報名了（FB-105 那個坑換了一個地方）。
#
# 現在 web/app.js 的 musterJoins 也認 battle:escort:，挑同伴那一步畫在場景卡戰場名字那一行底下（跟加入同一個位置），一顆一行
# （鈕上寫份量與氣血，四顆擠一排放不下），旁邊那一小句說挑了才算加入（MUSTER_NOTE.escort，待 joy 潤）；摺疊裡不再列。
# 晚到（battle:join_late）挑同伴也一樣。網頁照 tests/web/test_jianghu_page_web.py 的做法用真實內容、真的 /api/main。

PICK = re.compile(r'data-id="(battle:escort:\w+)"')


def _owner(on, game):
    p = game.state.player
    for cid in ("liubei", "guanyu"):
        assert game.world.try_recruit(cid, p.name, cap=3)
    return p


def _row(scene):
    return re.search(rf'<div class="options muster-join pick" {ROW_ATTRS}>(.*?)</div></div>', scene, re.S)


@node
def test_after_join_the_escort_pick_sits_by_the_battles_name(on):
    game = _muster(on, "guan")
    _owner(on, game)
    game.choose("battle:join:guan")
    m = server.main_view(game)
    picks = [o["id"] for o in m["options"] if o["id"].startswith("battle:escort:")]
    assert set(picks) == {"battle:escort:liubei", "battle:escort:guanyu", "battle:escort:none", "battle:escort:back"}
    page = _page(m)
    scene = _scene(page)
    assert _note_html("escort") in scene  # 那一小句說挑了才算加入
    row = _row(scene)
    assert row is not None and PICK.findall(row.group(1)) == picks  # 照選單的順序，一顆都不少
    labels = {o["id"]: o["label"] for o in m["options"]}
    assert all(f"<span>{labels[i]}</span>" in row.group(1) for i in picks)  # 份量與氣血照寫（挑誰要看）
    assert "battle:escort" not in _fold(page) and all(page.count(f'data-id="{i}"') == 1 for i in picks)


@node
def test_a_late_comer_picks_by_the_name_too(on):
    game = _muster(on, "guan")
    _owner(on, game)
    _start_fighting(game)
    game.choose("battle:join_late")
    m = server.main_view(game)
    picks = [o["id"] for o in m["options"] if o["id"].startswith("battle:escort:")]
    assert len(picks) == 4
    page = _page(m)
    row = _row(_scene(page))
    assert row is not None and PICK.findall(row.group(1)) == picks
    assert all(page.count(f'data-id="{i}"') == 1 for i in picks)


@node
def test_fb136_in_a_battle_round_the_three_moves_come_right_after_the_scene(battle):
    _, fighter = battle
    m = {**server.main_view(fighter), "guide": SHOWDOWN_BOX}
    assert m["free_text"] is not None and [o["id"] for o in m["options"] if o["id"].startswith("battle:act:")]
    page = run_prologue_web(m, "return H.pageJianghu();")
    # 大決戰優化（Joy 2026-11-06，方案甲）起：三招與輸入框排進最上面的戰場面板（web/battle.js），場景卡在面板底下
    panel, moves = page.index('<section class="bp"'), page.index('<div class="bp-moves"')
    free, scene, box = page.index('<form class="free"'), page.index('<section class="card scene">'), page.index('<section class="card guide"')
    assert panel < moves < free < scene < box
    assert page.index('data-id="battle:act:') < free  # 三招都在輸入框前面（面板裡）


@node
def test_a_broken_face_is_removed():
    """CSP（帳號與客服第 213 批）擋 inline 的 onerror：決戰的頭像抓不到時改由頂層一個 capture 的 error 監聽（bpFaceGone）把那張圖拿掉，
    只認 .bp-face、.bp-duo、.bp-solo 裡的 img；別處的 img、不是 img 的不動。畫出來的標記少了 onerror 屬性，其餘一樣。"""
    import webharness

    driver = r"""
const src2 = src;
eval(fn("bpFaceGone"));
const hit = (tag, inside) => { const t = { tagName: tag, gone: false, closest: (sel) => (inside && sel === ".bp-face, .bp-duo, .bp-solo" ? {} : null), remove() { t.gone = true; } }; return t; };
const out = {};
for (const [name, tag, inside] of [["face", "IMG", true], ["other", "IMG", false], ["span", "SPAN", true]]) {
  const t = hit(tag, inside); bpFaceGone({ target: t }); out[name] = t.gone;
}
out.nullTarget = (() => { try { bpFaceGone({ target: null }); return "ok"; } catch (e) { return String(e); } })();
out.registered = /\n  document\.addEventListener\("error", bpFaceGone, true\);/.test(src2);
finish(out);
"""
    out = webharness.run(driver, {})
    assert out == {"face": True, "other": False, "span": False, "nullTarget": "ok", "registered": True}
    battle = (webharness.WEB / "battle.js").read_text(encoding="utf-8")
    assert 'onerror="' not in battle  # 五個 inline 的都拿掉了
