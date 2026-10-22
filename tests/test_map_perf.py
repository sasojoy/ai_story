"""輿圖效能（FB-321～324，joy 2026-10-17「地圖那邊現在開起來很 Lag」）。

FB-321：打開輿圖時疊層（/api/map/state）在行動鎖裡把每個地點的勝算重算一遍（team.estimate：40 場模擬，一次 110～140 ms）。
伺服器上的 Game（server.game_for）帶著一份勝算的記憶（team.OddsMemo）：記的是模擬（team.odds_word）的全部輸入——威力、對手強度、
功效換算、雙方戰法與條件、戰法的設定——一樣才拿記住的那一個字，輸入一樣答案一定一樣（模擬是固定種子的純函式），
所以氣血、隊伍、裝備一變就重算，拿不到過期的、也拿不到別人的。直接建的 Game（測試、腳本、假人程式）沒有記憶，照舊每次算。"""
from __future__ import annotations

import random
import re
from pathlib import Path

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
# 輿圖第三版第 4 批：兩張圖都是固定取景、手勢整套拿掉了（FB-322 的游標那一條跟著拿掉；企劃者 2026-10-22 手勢改回來，游標照舊不換），
# 區圖的記號是 regionParts、天下圖是 worldParts；
# 其餘幾條照新的函式守同一件事（記號分兩張、常駐那一層、藏起來不收點擊、登出清乾淨）
NAMES = ["S", "pageMap", "regionParts", "regionFit", "worldParts", "drawMarks", "mapReady", "setMapDrawer", "renderPage", "forgetMap", "enter"]
DRIVER = re.sub(r"wholeApp\(\[.*?\]\)", "wholeApp(" + repr(NAMES).replace("'", '"') + ")", test_prologue_web.DRIVER, count=1, flags=re.S)
needs_node = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
# 假的地圖框：記下 classList 的每一次增減
FAKE_WRAP = """
  const calls = [];
  const wrap = { classes: new Set(), dataset: {}, setPointerCapture() {}, releasePointerCapture() {}, addEventListener() {}, firstElementChild: null,
    querySelector: () => null, querySelectorAll: () => [],
    classList: { add: (...c) => { calls.push(['add', ...c]); c.forEach((x) => wrap.classes.add(x)); },
                 remove: (...c) => { calls.push(['remove', ...c]); c.forEach((x) => wrap.classes.delete(x)); },
                 contains: (c) => wrap.classes.has(c), toggle: (c, on) => { if (on) wrap.classes.add(c); else wrap.classes.delete(c); } } };
  const doc = T.ctx.document, byId = doc.getElementById;
"""


def _run(game, script, **S):
    # 停在區圖那一層（潁川汝南）：輿圖第三版第 3 批起打開輿圖第一眼是天下圖（S.mapLayer "world"）
    payload = {"m": server.main_view(game), "script": script,
               "S": {"mapBase": game.map_base(), "mapState": game.map_state(), "mapLayer": "region", "mapRegion": "yingru", **S},
               "menxia": None, "stored": {}, "responses": {}}
    return webharness.run(DRIVER, payload)


def _map_game():
    game = _game(at="yingchuan")
    return game


def test_fb322_dragging_never_swaps_the_cursor():
    """輿圖第三版第 4 批拿掉了手勢；企劃者 2026-10-22 改回兩張都能拖、能捏合縮放（tests/test_map_pan_web.py）。FB-322 照舊守：
    拖的時候不換游標（cursor 會一路繼承、換一次整棵約 1,550 個元素重算樣式）——游標寫死 grab，沒有 grabbing 那一套。"""
    src = (Path(server.WEB) / "app.js").read_text(encoding="utf-8")
    css = (Path(server.WEB) / "style.css").read_text(encoding="utf-8")
    assert "function panDown(" in src and '"grabbing"' not in src and ".map-wrap.grabbing" not in css


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
    """「你在這裡」那一圈與旗子畫在上面那一層（#mkt）：底圖那一張（#mk）沒有會跳的東西；兩張同一個 viewBox、大小與字型。"""
    game = _map_game()
    out = _run(game, FAKE_WRAP + """
  const mk = { innerHTML: '' }, mkt = { innerHTML: '' };
  doc.getElementById = (id) => (id === 'mk' ? mk : id === 'mkt' ? mkt : id === 'map' ? wrap : byId(id));
  const v = H.S.regionView = H.regionFit(H.S.mapBase, 'yingru', 375, 600);
  const [low, high] = H.regionParts(H.S.mapBase, H.S.mapState, { v, vw: 375, vh: 600, rid: 'yingru', wash: false });
  H.drawMarks();
  return { low, high, mk: mk.innerHTML, mkt: mkt.innerHTML, page: H.pageMap() };""")
    assert 'class="pulse"' not in out["low"] and out["high"].count('class="pulse"') == 1 and 'class="r-you"' in out["high"]
    assert out["high"].startswith('<circle class="pulse"') and 'data-id="yingchuan"' in out["low"]  # 你的那一圈、旗子在最上面那一層；地點都還在底圖
    assert out["mk"] == out["low"] and out["mkt"] == out["high"] + '<g id="msel" pointer-events="none"></g>'  # 最後是選了的那一圈（drawSel）
    root = re.match(r"<svg\b([^>]*)>", game.map_base()["svg"]).group(1)
    assert f'<svg{root} class="mk-top" id="mkt"></svg></div>' in out["page"]  # 跟底圖同一個 viewBox、大小與字型，疊在它上面


@needs_node
def test_fb323_a_flashing_place_lives_in_the_layer_above():
    """版圖變化看以前的某一週（在天下圖上播）：易手的地點閃一圈，圈都在上面那一張，底圖那一張沒有。"""
    game = _timeline_game()
    changed = next(x for x in game.map_state()["weeks"] if x["week"] == 2)["changed"]
    low, high = _run(game, "return H.worldParts(H.S.mapBase, H.S.mapState, { k: 2.5, week: 2, tl: true, sel: null });", mapLayer="world")
    assert 'class="pulse"' not in low and high.count('class="pulse"') == len(changed) + 1


def test_fb323_the_pulse_grows_by_transform_and_fades_by_opacity():
    """FB-323（企劃者 10/17 從對比圖選丙）：圈的跳法改成整個圈放大（transform）、淡出（opacity），合成器自己跑、閒置不吃主執行緒；
    從半徑 16 放到 36（2.25 倍），線跟著變粗（企劃者接受）。不再改 r（那要主執行緒每一幀重畫）。"""
    css = (Path(server.WEB) / "style.css").read_text(encoding="utf-8")
    frames = css[css.index("@keyframes mk-pulse"):]
    frames = frames[: frames.index("} }") + 3]
    assert "transform: scale(1)" in frames and "transform: scale(2.25)" in frames and "opacity: 0.9" in frames and "opacity: 0" in frames
    assert "r:" not in frames
    rule = css[css.index(".mapx .pulse {"):]
    rule = rule[: rule.index("}") + 1]
    assert "transform-box: fill-box" in rule and "transform-origin: center" in rule and "mk-pulse 1.6s ease-out infinite" in rule


def _away_rules() -> dict[str, str]:
    """style.css 裡 #map-host.away 開頭的每一條規則：選擇器 → 大括號裡那一段。"""
    css = re.sub(r"/\*.*?\*/", "", (Path(server.WEB) / "style.css").read_text(encoding="utf-8"), flags=re.S)
    return {sel.strip(): body.strip() for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css) if sel.strip().startswith("#map-host.away")}


def test_fb326_nothing_in_the_hidden_map_takes_a_tap():
    """藏起來的輿圖那一層（FB-324）蓋在另外四頁上：裡面不能有任何東西收點擊。點擊區（透明的 rect）用 visible（照 visibility 走，透明的照樣點得到），
    不用 all（all 不管 visibility，藏起來也照收，FB-326）；藏起來時整層再一律 pointer-events: none。"""
    css = re.sub(r"/\*.*?\*/", "", (Path(server.WEB) / "style.css").read_text(encoding="utf-8"), flags=re.S)
    assert not re.search(r"pointer-events:\s*(all|painted|fill|stroke)\b", css)  # 這幾個值都不管 visibility
    hit = css[css.index('.map-wrap [data-act] > rect[fill-opacity="0"]'):]
    assert "pointer-events: visible;" in hit[: hit.index("}")]
    assert _away_rules()["#map-host.away *"] == "pointer-events: none !important;"


def test_fb327_fb328_the_hidden_map_stops_its_pulse_and_its_paper_grain():
    """藏起來時紅圈不跳（不然另外四頁閒著也每一幀在算，FB-327），底圖紙紋的 filter 關掉（feTurbulence 不看本體，visibility: hidden
    照樣畫出一層淡淡的紙紋，FB-328；區圖的塗層也是 filter）。回到輿圖時記號照舊重畫、圈從頭跳。"""
    rules = _away_rules()
    assert rules["#map-host.away .pulse"] == "animation: none;"
    assert rules["#map-host.away [filter]"] == "filter: none;"


@needs_node
def test_fb329_logging_out_or_in_forgets_the_last_players_map():
    """同一個分頁登出、換帳號登入（不重新整理）：上一個人的底圖、疊層、哪一層哪一區、選的地點、抽屜都清回開頭，常駐那一層整個清掉（FB-329）；
    登入之後停在輿圖分頁就重抓這個人的疊層。"""
    game = _map_game()
    st = game.map_state()
    # 登入（enter）那一段要等重抓回來，所以整段包成 async；fetch 是假的，照網址開頭回 responses 裡的那一份
    out = webharness.run(DRIVER, {
        "m": server.main_view(game), "S": {"mapBase": game.map_base(), "mapState": st}, "menxia": None, "stored": {},
        "responses": {"/api/map/state": st, "/api/map/base": game.map_base()},
        "script": """return (async () => {
  const doc = T.ctx.document, byId = doc.getElementById;
  const host = { id: 'map-host', classes: new Set(), html: 'OLD', classList: { add: (c) => host.classes.add(c), remove: (c) => host.classes.delete(c) } };
  Object.defineProperty(host, 'innerHTML', { get: () => host.html, set: (v) => { host.html = v; } });
  doc.getElementById = (id) => (id === 'map-host' ? host : byId(id));
  Object.assign(H.S, { mapLayer: 'region', mapRegion: 'yingru', regionView: { s: 2, cx: 1, cy: 2 }, mapSel: 'changshe', mapMode: 'place', mapDrawer: 'half', mapWeek: 3, mapQuery: '長', mapStateAt: 99 });
  H.forgetMap();
  const after = { base: H.S.mapBase, state: H.S.mapState, layer: H.S.mapLayer, region: H.S.mapRegion, view: H.S.regionView, sel: H.S.mapSel, mode: H.S.mapMode,
    drawer: H.S.mapDrawer, week: H.S.mapWeek, query: H.S.mapQuery, at: H.S.mapStateAt, host: host.html, away: host.classes.has('away') };
  Object.assign(H.S, { mapSel: 'changshe', tab: 'map' });
  H.enter({ stage: 'game', main: m });
  await new Promise((r) => setTimeout(r, 30));
  return { after, sel: H.S.mapSel, asked: T.calls.map((c) => c[0]), here: H.S.mapState && H.S.mapState.here };
})();"""})
    assert out["after"] == {"base": None, "state": None, "layer": "world", "region": None, "view": None, "sel": None, "mode": "overview",
                            "drawer": "min", "week": None, "query": "", "at": 0, "host": "", "away": True}
    assert out["sel"] is None and "/api/map/state" in out["asked"] and out["here"] == st["here"]


@needs_node
def test_fb324_the_map_layer_stays_put_while_you_are_on_another_tab():
    """輿圖那一層常駐在 #map-host：切到別的分頁只藏起來（.away），回來、整頁重畫時同一張底圖（data-key 一樣）不再把 114 KB 的
    SVG 字串塞回去，只換外圍（上面那一排、抽屜）；底圖換了（劇情開了新地點）才整層重畫。"""
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
    assert out["again"]["removed"] == ["top", "drawer"] and 'class="r-top"' in out["again"]["inserted"][0] and 'id="mdrawer"' in out["again"]["inserted"][0]
    assert out["again"]["cls"] == "mapx region tl-mode"
    assert out["away"]["away"] and out["away"]["fills"] == 1 and out["away"]["page"] > 0  # 江湖頁照畫在 #page，地圖藏起來、沒拆
    assert out["fresh"] == 2  # 底圖換了：整層重畫
