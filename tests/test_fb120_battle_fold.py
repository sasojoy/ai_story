"""FB-120（QA 32efa2c6，2026-10-09，375×812）：全服決戰開打的那段時間，戰場那一塊把每個人的第一屏都佔掉。

Game.scene_text 有全服決戰時大家都看得到戰場：只能觀戰的人是戰場＋分隔線＋自己眼前的事。開打後每回合多一句開頭、放手一搏的原文與
模型的故事，最近 5 段都在；QA 量到宛城開打、官軍站在潁川時師父的框在 1130、行動列 1226～1324（分頁列頂 756）。

現在（只改網頁，web/app.js 的 battleScene）：沒在打這一場的人（人不在決戰的大區、沒加入、沒臨時投效），場景裡開打中的戰場收成一行
「宛城之戰　第 N 回合・點開看」（待 joy 潤，字在 app.js 的 BATTLE_PEEK），點了攤開、底下多一顆「收起戰場」（BATTLE_SHUT）；
攤開記的是戰場的名字（S.battleOpen），回合往下走、輪詢重畫都不收回去，自己按收起或這一場打完才算。參戰的人照舊。

認的是伺服器給的場景（Markdown 轉好的 HTML）：分隔線（<hr />）之前那一段有開打後的回合數（「（第 N／M 回合」）、而且不是參戰者的那一句
（離開大區的「這回合不出手」、倒下的「你已經倒下」）。兩個正規式（BATTLE_ROUND、BATTLE_MINE）寫在 app.js、這裡用真的戰場驗：
戰鬥那條線（FB-109、FB-113）改了 _battle_scene_text 的寫法，這裡就紅。

網頁用真實內容（週末設定）的宛城之戰、真的 /api/main，照 tests/test_prologue_web.py 的做法把整支 app.js 放進 node
（scripts/test_for.py 改到 app.js 時靠這個檔名挑到這裡）。"""
from __future__ import annotations

import random
import re

import pytest
from test_fb107_first_screen import run as fit_run
from test_prologue_web import run

import server
import webharness
from tianxia.engine import Game

node = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")

BATTLE = "wancheng_jia"  # 宛城之戰（南陽）


def _player(on, name, faction, place):
    game = Game.new(on, name, rng=random.Random(0))
    game.client = None
    game.set_hints_off(True)
    game.state.player.faction, game.state.player.location = faction, place
    return game


def _fight_round(fighter):
    """參戰的那一個送出這一回合（場上只有他，送出就結算）。對面沒人、一回合推滿 push_max（正式 20），戰局先拉回中線，免得兩回合就收場。"""
    fighter.world.mutate_battle(lambda b: setattr(b, "trend", 50))
    move = next(o.id for o in fighter.options(odds=False) if o.enabled and o.id.startswith("battle:act:"))
    fighter.choose(move)


@pytest.fixture
def battle(on):
    """宛城之戰開打、打過一回合：一個臨時投效官軍的散人在宛城打，一個官軍的人站在潁川（QA 那一場）。"""
    watcher = _player(on, "觀戰甲", "guan", "yingchuan")
    fighter = _player(on, "參戰乙", None, "wan_city")
    watcher.world.start_battle(on.battles[BATTLE], now=watcher.now)
    fighter.choose("battle:enlist:guan")
    fighter.world.mutate_battle(lambda b: setattr(b, "muster_deadline_real", -1.0))
    fighter.options()
    assert fighter.world.get_battle().phase == "active"
    _fight_round(fighter)
    return watcher, fighter


def _consts():
    driver = ('finish(new Function(konst("BATTLE_PEEK") + "\\n" + konst("BATTLE_SHUT") + '
              '"\\nreturn { peek: BATTLE_PEEK, shut: BATTLE_SHUT };")());')
    return webharness.run(driver, {})


def _scene(page):
    """場景卡的內容，拿掉戰局條（它自己的測試在 test_battle_gauge.py）：這裡比的是伺服器給的那一段文字。"""
    scene = re.search(r'<section class="card scene">(.*?)</section>', page, re.S).group(1)
    start = scene.find('<div class="gauge"')
    if start < 0:
        return scene
    depth = 0
    for tag in re.finditer(r"<(/?)div\b", scene[start:]):  # 戰局條裡還有好幾層 div：數到對應的那一個收尾
        depth += -1 if tag.group(1) else 1
        if depth == 0:
            end = scene.index(">", start + tag.start()) + 1
            return scene[:start] + scene[end:]
    return scene


def _round(m):
    return int(re.search(r"（第 (\d+)／\d+ 回合", m["scene"]).group(1))


def _folded(m):
    return (f'<p class="battle-fold" data-act="battle-open" role="button" tabindex="0" aria-expanded="false">'
            f'宛城之戰　第 {_round(m)} 回合・{_consts()["peek"]}</p>')


CLICK = """const tap = async (act) => { const el = { dataset: { act }, classList: { contains: () => false } };
  await T.docListeners.click[0]({ target: { closest: () => el } }); return T.els.page.innerHTML; };"""


# ── 只能觀戰的人：收成一行，點了攤開 ─────────────────────────────


@node
def test_a_spectator_sees_the_running_battle_as_one_line(battle):
    watcher, _ = battle
    m = server.main_view(watcher)
    battle_part, own = m["scene"].split("<hr />", 1)
    assert "回合" in battle_part and "這場決戰在南陽" in battle_part and "act:rest" in [o["id"] for o in m["options"]]
    scene = _scene(run(m, "return H.pageJianghu();"))
    assert scene.startswith(_folded(m) + "\n<hr />")  # 戰場那一塊只剩一行，分隔線之後照舊
    assert own in scene  # 自己眼前的事（所在地）一個字不動
    assert "這一回合" not in scene and "這場決戰在南陽" not in scene  # 戰報與觀戰的原因都收起來了
    assert _consts()["shut"] not in scene


@node
def test_a_gamble_that_quotes_a_participants_line_does_not_unfold_it(battle):
    """審查 M1：放手一搏的原文與模型的故事照字寫進戰報（最近五段都在戰場那一塊）。有人寫「你已經倒下」「這回合不出手」，
    每個觀戰的人的戰場也不能因此整段攤開：參戰者的那一句只認戰場那一塊的最後一段（引擎寫看戰場的原因的地方）。"""
    watcher, fighter = battle
    fighter.submit_battle_custom_action("你已經倒下這回合不出手", 35, ("他大喊：你已經倒下了！", "他說這回合不出手，轉身就走。"))
    m = server.main_view(watcher)
    battle_part = m["scene"].split("<hr />", 1)[0]
    assert "你已經倒下這回合不出手" in battle_part and "這場決戰在南陽" in battle_part.rsplit("<p>", 1)[1]
    scene = _scene(run(m, "return H.pageJianghu();"))
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
    out = run(first, script, S={"next": second})
    shut_btn = (f'<p class="battle-shut"><button class="linkish" data-act="battle-shut" aria-expanded="true">'
                f'{_consts()["shut"]}</button></p>')
    assert _folded(first) in out["folded"]
    battle_first = first["scene"].split("<hr />", 1)[0]
    assert battle_first + shut_btn in _scene(out["opened"]) and out["key"] == "宛城之戰"  # 整段攤開，記的是戰場的名字
    battle_second = second["scene"].split("<hr />", 1)[0]
    assert battle_second + shut_btn in _scene(out["polled"])  # 下一回合輪詢重畫：照舊攤開，寫的是新的回合
    assert _folded(second) in out["shut"] and out["after"] is None  # 按收起：收回一行（新的回合數）


@node
def test_the_keyboard_opens_the_folded_line(battle):
    watcher, _ = battle
    m = server.main_view(watcher)
    script = """
      H.S.tab = "jianghu"; H.renderPage();
      const target = Object.assign(Object.create(T.Element.prototype), { matches: (sel) => sel === '.battle-fold[data-act="battle-open"]' });
      let prevented = false;
      for (const fn of T.docListeners.keydown) fn({ key: "Enter", target, preventDefault: () => { prevented = true; } });
      return { prevented, open: H.S.battleOpen, page: T.els.page.innerHTML };"""
    out = run(m, script)
    assert out["prevented"] and out["open"] == "宛城之戰" and m["scene"].split("<hr />", 1)[0] in _scene(out["page"])


@node
def test_focus_goes_back_to_the_toggle_after_opening_and_folding(battle):
    """審查 M4：攤開、收起都整頁重畫，原本有焦點的那一行（那一顆）不見了：焦點放回新畫出來的開關（同戰況圖卡的做法），
    鍵盤再按一次就能收起、再攤開。"""
    watcher, _ = battle
    m = server.main_view(watcher)
    script = CLICK + """return (async () => {
      H.S.tab = "jianghu"; H.renderPage();
      const focused = [];
      T.qs['#page .battle-shut button'] = { focus: () => focused.push("shut") };
      T.qs['#page .battle-fold'] = { focus: () => focused.push("fold") };
      const target = Object.assign(Object.create(T.Element.prototype), { matches: (sel) => sel === '.battle-fold[data-act="battle-open"]' });
      for (const fn of T.docListeners.keydown) fn({ key: "Enter", target, preventDefault: () => {} });
      const afterOpen = focused.slice();
      await tap("battle-shut");
      return { afterOpen, afterShut: focused.slice(afterOpen.length), open: H.S.battleOpen };
    })();"""
    out = run(m, script)
    assert out["afterOpen"] == ["shut"] and out["afterShut"] == ["fold"] and out["open"] is None


@node
def test_the_open_state_is_forgotten_when_the_battle_is_over(battle):
    """打完了（場景裡沒有開打中的回合）：記著的攤開清掉，下一場開打照舊先收著。"""
    watcher, _ = battle
    m = server.main_view(watcher)
    calm = {**m, "scene": m["scene"].split("<hr />\n", 1)[1]}
    script = """
      H.S.battleOpen = "宛城之戰"; H.S.main = H.S.calm; H.pageJianghu(); const cleared = H.S.battleOpen;
      H.S.main = m; return { cleared, page: H.pageJianghu() };"""
    out = run(m, script, S={"calm": calm})
    assert out["cleared"] is None and _folded(m) in out["page"]


# ── 參戰的人、集結時：照舊 ─────────────────────────────


@node
def test_a_participant_sees_the_whole_battle(battle):
    _, fighter = battle
    m = server.main_view(fighter)
    assert "<hr />" not in m["scene"] and "battle:act:" in "".join(o["id"] for o in m["options"])
    scene = _scene(run(m, "return H.pageJianghu();"))
    assert "battle-fold" not in scene and "這一回合" in scene


@node
def test_a_participant_who_walked_out_of_the_region_is_not_folded(battle):
    """參戰後離開了南陽（這回合不出手、回去就能再出手）：他是這一場的人，戰場照舊整段。"""
    _, fighter = battle
    fighter.state.player.location = "yingchuan"
    fighter._sync_battle_presence()  # noqa: SLF001  出發、抵達時引擎自己記；這裡直接把人放到潁川
    m = server.main_view(fighter)
    assert "<hr />" in m["scene"] and "這回合不出手" in m["scene"]
    scene = _scene(run(m, "return H.pageJianghu();"))
    assert "battle-fold" not in scene and "這一回合" in scene


@node
def test_a_scene_with_enlist_buttons_on_the_name_line_is_not_folded(battle, on):
    """審查 M5：名字那一行有加入或臨時投效的鈕（musterJoins）時不收——收了的話那幾顆鈕就沒地方畫。開打後人在決戰的大區、
    還沒投效的散人就是這一種：引擎在戰場底下接自己眼前的事（FB-109），網頁照舊整段、鈕排在名字那一行。"""
    drifter = server.main_view(_player(on, "散人丙", None, "wan_city"))
    assert [o["id"] for o in drifter["options"] if o["id"].startswith("battle:")] == ["battle:enlist:guan", "battle:enlist:huang"]
    assert "<hr />" in drifter["scene"] and "回合" in drifter["scene"].split("<hr />", 1)[0]
    scene = _scene(run(drifter, "return H.pageJianghu();"))
    assert "battle-fold" not in scene and "這一回合" in scene
    assert scene.startswith('<div class="muster-head"><p><strong>宛城之戰</strong></p>')
    assert re.findall(r'data-id="(battle:enlist:\w+)"', scene) == ["battle:enlist:guan", "battle:enlist:huang"]


@node
def test_a_muster_is_left_to_the_first_screen_fit(on):
    """還在集結（沒有回合數）：不歸這裡收，照舊是 FB-107 收集結那一句。"""
    watcher = _player(on, "觀戰甲", "guan", "yingchuan")
    watcher.world.start_battle(on.battles[BATTLE], now=watcher.now)
    m = server.main_view(watcher)
    assert "集結中" in m["scene"] and "<hr />" in m["scene"]
    assert "battle-fold" not in _scene(run(m, "return H.pageJianghu();"))


# ── 第一屏收合（FB-107）不收攤開了的戰場 ─────────────────────────────


@node
def test_the_fit_does_not_clip_a_battle_the_player_opened():
    """攤開的戰場（場景卡裡有「收起戰場」那一行）：第一屏放不下時，第 8 步不把它的每一段收成一行（玩家自己攤開的不收）。"""
    layout = {"bottom": 800, "actbar": True, "scene": True, "muster": 3, "join": False, "hr": True, "own": 2}
    plain = fit_run(layout)
    assert "muster" in plain["fitted"]
    opened = fit_run({**layout, "battleShut": True})
    assert "muster" not in opened["fitted"] and opened["musterClip"] == [False, False, False]
