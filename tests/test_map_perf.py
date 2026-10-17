"""輿圖效能（FB-321～324，joy 2026-10-17「地圖那邊現在開起來很 Lag」）。

FB-321：打開輿圖時疊層（/api/map/state）在行動鎖裡把每個地點的勝算重算一遍（team.estimate：40 場模擬，一次 110～140 ms）。
伺服器上的 Game（server.game_for）帶著一份勝算的記憶（team.OddsMemo）：記的是模擬（team.odds_word）的全部輸入——威力、對手強度、
功效換算、雙方戰法與條件、戰法的設定——一樣才拿記住的那一個字，輸入一樣答案一定一樣（模擬是固定種子的純函式），
所以氣血、隊伍、裝備一變就重算，拿不到過期的、也拿不到別人的。直接建的 Game（測試、腳本、假人程式）沒有記憶，照舊每次算。"""
from __future__ import annotations

import random
import re

import pytest
import test_prologue_web
from conftest import real_content
from test_map_web import _timeline_game

import server
import webharness
from tianxia import team
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

SQUAD = "shanzei"  # 山賊：練過的人穩勝、沒有武學的人必敗


@pytest.fixture
def counted(monkeypatch):
    """team.odds_word 被叫了幾次（真的模擬了幾次）。"""
    calls = []
    real = team.odds_word

    def spy(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(team, "odds_word", spy)
    return calls


def _game(name="沈浪", faction="guan", at="changshe"):
    c = real_content("weekend")
    c.config.auto_open_first_season = True
    game = Game.new(c, name, rng=random.Random(0), world=open_world())
    game.client = None
    game.state.player.faction, game.state.player.location = faction, at
    return game


def _fresh(game, squad=SQUAD):
    """沒有記憶時算出來的那一個字（對照）。"""
    return team.estimate(game.state, game.content, game.world, squad)


def test_the_same_question_is_answered_from_memory(counted):
    game = _game()
    game.odds_memo = team.OddsMemo()
    first = game.odds(SQUAD)
    assert len(counted) == 1
    assert game.odds(SQUAD) == first == _fresh(game)
    assert len(counted) == 2  # 第二次問沒有再模擬（第二筆是 _fresh 那一次對照）


def test_a_hurt_body_asks_again(counted):
    game = _game()
    game.odds_memo = team.OddsMemo()
    game.odds(SQUAD)
    member = game.state.player.member
    member.neili = team.member_neili(game.content, member)[1] * 0.3  # 氣血掉到三成：威力（氣血係數）變了
    hurt = game.odds(SQUAD)
    assert len(counted) == 2 and hurt == _fresh(game)


def test_a_changed_team_or_gear_asks_again(counted):
    game = _game()
    game.odds_memo = team.OddsMemo()
    game.odds(SQUAD)
    game.state.player.stats["str"] = 15  # 臂力配滿：本人的加成變了
    assert game.odds(SQUAD) == _fresh(game)
    n = len(counted)
    game.state.player.member.wugong_id = None  # 卸下武學
    assert game.odds(SQUAD) == _fresh(game)
    assert len(counted) == n + 2  # 換了一樣就重算一次（另一筆是對照）


def test_another_player_never_gets_someone_elses_odds(counted):
    memo = team.OddsMemo()
    strong, weak = _game("甲"), _game("乙")
    strong.state.player.stats.update(str=15, con=15)
    weak.state.player.member.wugong_id = None
    weak.state.player.member.neigong_id = None
    for g in (strong, weak):
        g.odds_memo = memo
    words = [strong.odds(SQUAD), weak.odds(SQUAD)]
    assert words == [_fresh(strong), _fresh(weak)]
    assert words[0] != words[1]  # 兩個人的勝算真的不一樣，記憶沒有把一個人的給另一個人


def test_the_memory_keeps_only_the_latest_questions():
    memo = team.OddsMemo(size=2)
    for key in (b"a", b"b", b"c"):
        memo.get(key, lambda k=key: k.decode())
    assert memo.get(b"b", lambda: "又算了") == "b"  # 還在
    assert memo.get(b"a", lambda: "又算了") == "又算了"  # 最舊的那一個被擠掉了


def test_games_on_the_server_carry_the_memory_and_plain_games_do_not(monkeypatch):
    monkeypatch.setattr(server, "GAMES", {})
    monkeypatch.setattr(server, "open_game", lambda name: Game.new(real_content("weekend"), name, rng=random.Random(0), world=open_world()))
    assert server.game_for("沈浪").odds_memo is server.ODDS_MEMO
    assert _game().odds_memo is None


# ── 網頁（node 跑整支 app.js，同 tests/test_map_web.py）──
NAMES = ["S", "pageMap", "marksSvg", "marksParts", "drawMarks", "mapReady", "setMapDrawer", "gripDown", "gripUp", "renderPage"]
DRIVER = re.sub(r"wholeApp\(\[.*?\]\)", "wholeApp(" + repr(NAMES).replace("'", '"') + ")", test_prologue_web.DRIVER, count=1, flags=re.S)
needs_node = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
NOW = "{ k: 1, far: false, layers: new Set(['control']), sel: null, week: H.S.mapState.now_week }"
# 假的地圖框：記下 classList 的每一次增減
FAKE_WRAP = """
  const calls = [];
  const wrap = { classes: new Set(), setPointerCapture() {}, releasePointerCapture() {}, addEventListener() {}, firstElementChild: null,
    querySelector: () => null,
    classList: { add: (...c) => { calls.push(['add', ...c]); c.forEach((x) => wrap.classes.add(x)); },
                 remove: (...c) => { calls.push(['remove', ...c]); c.forEach((x) => wrap.classes.delete(x)); },
                 contains: (c) => wrap.classes.has(c), toggle: (c, on) => { if (on) wrap.classes.add(c); else wrap.classes.delete(c); } } };
  const doc = T.ctx.document, byId = doc.getElementById;
"""


def _run(game, script, **S):
    payload = {"m": server.main_view(game), "script": script,
               "S": {"mapBase": game.map_base(), "mapState": game.map_state(), **S}, "menxia": None, "stored": {}, "responses": {}}
    return webharness.run(DRIVER, payload)


def _map_game():
    game = _game(at="yingchuan")
    return game


@needs_node
def test_fb322_a_touch_on_the_map_never_touches_the_grabbing_cursor():
    """觸控按下、放開不加不拿 .grabbing（游標是繼承屬性，換一次整棵地圖約 1,550 個元素重算樣式）；滑鼠拖的時候游標照舊。"""
    out = _run(_map_game(), FAKE_WRAP + """
  doc.getElementById = (id) => (id === 'map' ? wrap : byId(id));
  const target = { closest: () => null };
  const ev = (type, pointerType) => ({ type, pointerType, button: 0, pointerId: 1, clientX: 10, clientY: 10, currentTarget: wrap, target });
  H.gripDown(ev('pointerdown', 'touch')); H.gripUp(ev('pointerup', 'touch'));
  const touch = calls.splice(0);
  H.gripDown(ev('pointerdown', 'mouse')); const held = wrap.classes.has('grabbing'); H.gripUp(ev('pointerup', 'mouse'));
  return { touch, mouse: calls, held, after: [...wrap.classes] };""")
    assert not any("grabbing" in call for call in out["touch"]), out["touch"]
    assert out["held"] and ["remove", "grabbing"] in [c[:2] for c in out["mouse"]] and "grabbing" not in out["after"]


@needs_node
def test_fb322_the_drawer_height_variable_is_only_written_while_watching_the_timeline():
    """--md-h（抽屜的高度，自訂屬性會一路繼承下去）只有版圖變化用得到：點地點拉高抽屜時不寫，不逼整棵地圖重算樣式。"""
    out = _run(_map_game(), """
  const props = {}, box = { clientHeight: 700, style: { setProperty: (k, v) => { props[k] = v; } } }, drawer = { style: {} };
  const doc = T.ctx.document, byId = doc.getElementById;
  doc.getElementById = (id) => (id === 'mapx' ? box : id === 'mdrawer' ? drawer : byId(id));
  H.S.mapMode = 'place'; H.setMapDrawer('peek');
  const place = Object.assign({}, props), placeHeight = drawer.style.height;
  H.S.mapMode = 'timeline'; H.setMapDrawer('tl');
  return { place, placeHeight, tl: props, tlHeight: drawer.style.height };""")
    assert "--md-h" not in out["place"] and out["placeHeight"] == "240px"
    assert out["tl"]["--md-h"] == out["tlHeight"] == "320px"


@needs_node
def test_fb323_the_pulses_live_in_the_layer_above_the_map_not_in_its_svg():
    """「你在這裡」那一圈從底圖的 SVG（#mk）搬到上面那一層（#mkt）：記號照原本的先後畫，從第一個會跳的圈起整段放上去，
    看起來一樣；底圖那一張不再有會跳的東西。"""
    game = _map_game()
    out = _run(game, FAKE_WRAP + f"""
  const mk = {{ innerHTML: '' }}, mkt = {{ innerHTML: '' }};
  doc.getElementById = (id) => (id === 'mk' ? mk : id === 'mkt' ? mkt : id === 'map' ? wrap : byId(id));
  H.S.mapView = {{ s: 1, cx: 400, cy: 600 }}; H.S.mapLayers = ['control'];
  const [low, high] = H.marksParts(H.S.mapBase, H.S.mapState, {NOW});
  H.drawMarks();
  return {{ low, high, whole: H.marksSvg(H.S.mapBase, H.S.mapState, {NOW}), mk: mk.innerHTML, mkt: mkt.innerHTML, page: H.pageMap() }};""")
    assert 'class="pulse"' not in out["low"] and out["high"].count('class="pulse"') == 1
    assert out["low"] + out["high"] == out["whole"]  # 先後一個都沒動
    assert out["high"].startswith('<circle class="pulse"') and "（你）" in out["low"]  # 你的那一圈、旗子在最上面那一層；地點都還在底圖
    assert out["mk"] == out["low"] and out["mkt"] == out["high"]
    root = re.match(r"<svg\b([^>]*)>", game.map_base()["svg"]).group(1)
    assert f'<svg{root} class="mk-top" id="mkt"></svg></div>' in out["page"]  # 跟底圖同一個 viewBox、大小與字型，疊在它上面


@needs_node
def test_fb323_a_flashing_place_takes_everything_drawn_after_it_up_with_it():
    """版圖變化看以前的某一週：易手的地點閃一圈。那一圈之後畫的（它自己的圓盤、名字，之後的地點）照原本的先後一起放上去，
    圈不會蓋到它自己的名字；點擊區跟著走，點得到。"""
    game = _timeline_game()
    changed = next(x for x in game.map_state()["weeks"] if x["week"] == 2)["changed"]
    out = _run(game, "return H.marksParts(H.S.mapBase, H.S.mapState, { k: 1, far: false, layers: new Set(['control']), sel: null, week: 2 });")
    low, high = out
    assert 'class="pulse"' not in low and high.count('class="pulse"') == len(changed) + 1
    assert (low + high).count("data-loc=") == len(game.map_base()["places"])


@needs_node
def test_fb324_the_map_layer_stays_put_while_you_are_on_another_tab():
    """輿圖那一層常駐在 #map-host：切到別的分頁只藏起來（.away），回來、整頁重畫時同一張底圖（data-key 一樣）不再把 114 KB 的
    SVG 字串塞回去，只換外圍（找地點與濾鏡、右上角的鈕、抽屜）；底圖換了（劇情開了新地點）才整層重畫。"""
    out = _run(_map_game(), """
  const doc = T.ctx.document, byId = doc.getElementById;
  const fills = [], inserted = [], removed = [];
  const host = { id: 'map-host', classes: new Set(['away']), html: '',
    classList: { add: (c) => host.classes.add(c), remove: (c) => host.classes.delete(c), contains: (c) => host.classes.has(c) } };
  Object.defineProperty(host, 'innerHTML', { get: () => host.html, set: (v) => { host.html = v; fills.push(v); } });
  let box = null;
  const makeBox = (key) => {
    const kid = (id) => ({ id, remove: () => removed.push(id) });
    box = { parentNode: host, dataset: { key }, className: 'mapx', querySelector: (sel) => (sel === '.tx-world-map' ? {} : null),
      children: [kid('map'), kid('top'), kid('drawer')], insertAdjacentHTML: (pos, html) => inserted.push(html) };
  };
  doc.getElementById = (id) => (id === 'map-host' ? host : id === 'mapx' ? box : byId(id));
  H.S.tab = 'map'; H.renderPage();
  const first = { fills: fills.length, html: host.html, away: host.classes.has('away'), page: T.els.page.innerHTML };
  makeBox(String(H.S.mapBase.key));
  H.S.mapMode = 'timeline'; H.renderPage();
  const again = { fills: fills.length, removed: removed.slice(), inserted: inserted.slice(), cls: box.className };
  H.S.mapMode = 'overview';
  H.S.tab = 'jianghu'; H.renderPage();
  const away = { away: host.classes.has('away'), fills: fills.length, page: T.els.page.innerHTML.length };
  H.S.tab = 'map'; H.S.mapBase = Object.assign({}, H.S.mapBase, { key: 'another-key' }); H.renderPage();
  return { first, again, away, fresh: fills.length };""")
    assert out["first"]["fills"] == 1 and '<div class="tx-world-map"><svg viewBox="0 0 900 1340"' in out["first"]["html"]
    assert not out["first"]["away"] and out["first"]["page"] == ""
    assert out["again"]["fills"] == 1  # 同一張底圖：沒有再塞一次
    assert out["again"]["removed"] == ["top", "drawer"] and "map-chips" in out["again"]["inserted"][0] and 'id="mdrawer"' in out["again"]["inserted"][0]
    assert out["again"]["cls"] == "mapx tl-mode"
    assert out["away"]["away"] and out["away"]["fills"] == 1 and out["away"]["page"] > 0  # 江湖頁照畫在 #page，地圖藏起來、沒拆
    assert out["fresh"] == 2  # 底圖換了：整層重畫
