"""輿圖四層（減法季整合設計第七章，企劃者 2026-10-24「滿意」；減法季批 3）：打開輿圖第一眼是第一層——你所在的區、以你為中心，只畫你、
走得到的地方（地名、分鐘數、「多半」）、到它們的路、本週要去的那一處（金路、紅旗、「本週」朱印），其餘淡墨小圖不寫名；點一處（第二層）
那一處放大、其餘退成四成、卡只佔三分之一（名字、誰的、幾分、步行與疾行在前，往上拉才有能悟、對手……）；「全區」是舊的區圖（第三層），
按過只這一次有效；「天下」是天下圖（第四層）。每一層都能拖能縮，拖遠了一顆「回到我這」。
在 node 裡跑整支 app.js（tests/webharness.py），餵伺服器真的會給的底圖與疊層；沒有 node 就略過。"""
from __future__ import annotations

import random
import re

import pytest
import test_prologue_web
from conftest import real_content
from jianfa_kit import no_jianfa

import server
import webharness
from tianxia.engine import Game
from tianxia.sqlite_world import open_world
from tianxia.state import Bounty

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
NAMES = ["S", "nearFit", "nearParts", "nearIds", "nearLineHtml", "regionTopHtml", "placeCard", "peekPx", "mapFirst", "drawerHtml",
         "homeFar", "mapxClass", "routeD"]
DRIVER = re.sub(r"wholeApp\(\[.*?\]\)", "wholeApp(" + repr(NAMES).replace("'", '"') + ")", test_prologue_web.DRIVER, count=1, flags=re.S)
NEAR = {"yingchuan", "yingshui", "changshe", "guan_camp"}  # 潁川郊野走得到的四處（正式內容）


def _game(at="yingchuan_wilds", closed=False):
    c = no_jianfa(real_content("season21")) if closed else real_content("season21")  # closed：減法季關著（名字旁還是雲端批 3 那一套）
    c.config.auto_open_first_season = True
    game = Game.new(c, "陸乙", rng=random.Random(0), world=open_world())
    game.client = None
    game.state.player.faction, game.state.player.location = "guan", at
    return game


def run(game, script, st=None, **S):
    payload = {"m": server.main_view(game), "script": script,
               "S": {"mapBase": game.map_base(), "mapState": st or game.map_state(), "mapLayer": "near", "mapRegion": "yingru", **S},
               "menxia": None, "stored": {}, "responses": {}}
    return webharness.run(DRIVER, payload)


def near_parts(game, st=None, sel="null", vw=375, vh=604):
    return run(game, f"const v = H.nearFit(H.S.mapBase, H.S.mapState, {vw}, {vh}); return {{ v, parts: H.nearParts(H.S.mapBase, H.S.mapState, {{ v, vw: {vw}, vh: {vh}, sel: {sel} }}) }};", st=st)


def test_the_first_layer_names_only_you_and_the_places_you_can_walk_to():
    """第一層第一眼只有五個名字（驗收第十四章）：你＋走得到的四處；其餘地點是淡淡的墨筆小圖、不寫名、點得到。"""
    out = near_parts(_game())
    low, high = out["parts"]
    named = set(re.findall(r'<g class="n-label" data-act="region-place" data-id="([^"]+)"', low))
    assert named == NEAR
    assert "你・潁川郊野" in high and high.count('class="r-you"') == 1
    faint = re.findall(r'<g class="n-faint" data-act="region-place" data-id="([^"]+)"[^>]*>(.*?)</g>', low)
    assert len(faint) > 10 and not any("<text" in body for _, body in faint) and not ({i for i, _ in faint} & NEAR)
    # 不畫框、悟字、寶印、鄰區箭頭（全區才有）
    for gone in ("r-frame", "r-ins", "r-seal", "r-exit", "r-bar"):
        assert gone not in low, gone
    assert low.count('class="n-road"') == 4  # 到走得到的四處的路


def test_each_walkable_place_says_minutes_and_what_it_mostly_holds():
    """名字底下一行：分鐘數＋「多半」兩字（城多事、野多敵、山多料、渡參半、營多敵、寺多悟）；接了討伐懸賞寫「有賞」。
    減法季探索一顆開著的季（這一局的正式內容 season21）2f 起兩個字是看的人站過去之後鈕上小字的最後兩個字：官軍自己的營寨是跟同袍比劃，寫「比劃」
    （以前這一句鎖「多敵」；逐處逐身分的對照在 tests/test_explore_one_2f.py）。"""
    game = _game()
    low = near_parts(game)["parts"][0]
    subs = dict(re.findall(r'data-id="([^"]+)"[^>]*>(?:(?!</g>).)*?<text class="n-sub"[^>]*>([^<]+)</text>', low))
    assert subs["yingchuan"].endswith("分・多事") and subs["yingshui"].endswith("分・參半") and subs["guan_camp"].endswith("分・比劃")
    st = game.map_state()
    st["week"] = None
    st["places"]["guan_camp"]["bounty"] = "討伐"  # 疊層寫了討伐也不另寫「有賞」：底圖帶 viewer_mostly，兩個字整個照伺服器給的（下面真的接了懸賞的兩條測）
    low = near_parts(game, st=st)["parts"][0]
    assert re.search(r'data-id="guan_camp"(?:(?!</g>).)*?分・比劃</text>', low) and "分・有賞" not in low


def test_a_closed_season_still_writes_has_reward_from_the_overlay_bounty():
    """減法季關著的季：底圖沒有 viewer_mostly（名字旁還是雲端批 3 的 MOSTLY，營多敵），網頁照舊——疊層的 bounty 含「討伐」就寫「有賞」，一個字不變。"""
    game = _game(closed=True)
    assert "viewer_mostly" not in game.map_base()
    low = near_parts(game)["parts"][0]
    subs = dict(re.findall(r'data-id="([^"]+)"[^>]*>(?:(?!</g>).)*?<text class="n-sub"[^>]*>([^<]+)</text>', low))
    assert subs["yingchuan"].endswith("分・多事") and subs["yingshui"].endswith("分・參半") and subs["guan_camp"].endswith("分・多敵")
    st = game.map_state()
    st["week"] = None
    st["places"]["guan_camp"]["bounty"] = "討伐"
    low = near_parts(game, st=st)["parts"][0]
    assert re.search(r'data-id="guan_camp"(?:(?!</g>).)*?分・有賞</text>', low)


def _held_strike(able: bool):
    """官軍站潁川郊野，揭了隔壁潁水的討伐懸賞（黃巾散兵）：able 裝起手拳腳（對它「難分勝負」，強制遭遇）、否則沒裝武學（威力 0，必敗放開）。"""
    game = _game()
    game.state.player.member.wugong_id = "jichu_quanjiao" if able else None
    game.state.world.bounties.append(Bounty(id="s1", kind="strike", faction="guan", week=1, expires=1e12, silver=10, deeds=1,
                                            location="yingshui", squad="shanzei", takers=[game.state.player.name]))
    return game


def _subs(game) -> dict[str, str]:
    """第一層每個名字旁那一行。揭著的懸賞會成為「本週要去的那一處」，那一處的那一行換成一句為什麼（「懸賞・討伐」），所以疊層的 week 先清掉。"""
    st = game.map_state()
    st["week"] = None
    low = near_parts(game, st=st)["parts"][0]
    return dict(re.findall(r'data-id="([^"]+)"[^>]*>(?:(?!</g>).)*?<text class="n-sub"[^>]*>([^<]+)</text>', low))


def test_a_held_bounty_that_is_not_hopeless_reads_has_reward_beside_the_name():
    """接了討伐、不是必敗：網頁畫「有賞」，跟走到那裡探索鈕的「野外有賞」「渡口有賞」同一個字。"""
    game = _held_strike(able=True)
    assert game.odds("shanzei", at="yingshui") != "必敗" and game.map_state()["places"]["yingshui"]["bounty"] == "討伐"
    assert _subs(game)["yingshui"].endswith("分・有賞")
    game.state.player.location = "yingshui"
    assert game.outing_plan().hint == "渡口有賞"


def test_a_held_bounty_that_is_hopeless_reads_the_table_not_has_reward():
    """接了討伐、必敗放開（2e）：鈕上照表寫「渡口參半」，名字旁網頁以前自己因為疊層有討伐就寫「有賞」，現在照伺服器給的、跟鈕一致。"""
    game = _held_strike(able=False)
    assert game.odds("shanzei", at="yingshui") == "必敗" and game.map_state()["places"]["yingshui"]["bounty"] == "討伐"  # 疊層照舊標討伐
    sub = _subs(game)["yingshui"]
    assert sub.endswith("分・參半") and "有賞" not in sub
    game.state.player.location = "yingshui"
    plan = game.outing_plan()
    assert plan.how != "bounty" and plan.hint == "渡口參半" and sub.endswith(plan.hint[-2:])


def test_the_name_line_beside_a_dangerous_ford_reads_like_the_button_there():
    """FB-886 的實機證據：站在白馬寺，隔壁孟津渡（渡口 2★）名字旁以前寫「參半」，走到那裡探索鈕寫「渡口多敵」；現在網頁畫出來的就是「多敵」。"""
    game = _game(at="baima_temple")
    low = near_parts(game)["parts"][0]
    subs = dict(re.findall(r'data-id="([^"]+)"[^>]*>(?:(?!</g>).)*?<text class="n-sub"[^>]*>([^<]+)</text>', low))
    assert subs["mengjin_ford"].endswith("分・多敵") and subs["luoyang_palace"].endswith("分・多事"), subs
    game.state.player.location = "mengjin_ford"
    assert game.outing_plan().hint == "渡口多敵"


def test_this_weeks_place_has_the_gold_road_the_flag_and_the_seal():
    """本週要去的那一處：金路（照疊層的 path）、紅旗、「本週」朱印與一句為什麼；疊層沒有就都不畫。"""
    game = _game()
    st = game.map_state()
    st["week"] = {"id": "changshe", "why": "軍令・守城・潁川汝南", "minutes": st["places"]["changshe"]["minutes"]}
    low, high = near_parts(game, st=st)["parts"]
    assert low.count('class="n-gold"') == 1 and high.count('class="n-flag"') == 1
    assert re.search(r'data-id="changshe"(?:(?!</g>).)*?<g class="n-week">', low) and "軍令・守城・潁川汝南" in low
    st["week"] = None
    low, high = near_parts(game, st=st)["parts"]
    assert "n-gold" not in low and "n-flag" not in high and "n-week" not in low


def test_a_far_week_place_is_named_too_and_its_road_follows_the_route():
    """本週那一處不是走得到的（隔了幾站）也寫名字，金路沿著路線一站一站描。"""
    game = _game()
    st = game.map_state()
    far = next(i for i, q in st["places"].items() if len(q["path"]) >= 2)
    st["week"] = {"id": far, "why": "主線的目標", "minutes": st["places"][far]["minutes"]}
    out = near_parts(game, st=st)
    low = out["parts"][0]
    assert f'data-id="{far}"' in re.sub(r'<g class="n-faint".*?</g>|<rect class="n-hit"[^>]*/>', "", low)  # 點擊區（FB-877）每一處都有，不算
    d = re.search(r'class="n-gold" d="([^"]+)"', low).group(1)
    assert d.count("Q") + d.count("L") == len(st["places"][far]["path"])


def test_the_first_layer_is_centred_on_you_and_fits_the_walkable_places():
    """取景：你在露出來的那一塊正中，走得到的地方都在地圖框裡（左右留給名字）。"""
    game = _game()
    out = near_parts(game)
    v, base = out["v"], game.map_base()
    at = {p["id"]: p for p in base["places"]}
    me = at["yingchuan_wilds"]
    assert v["cx"] == me["x"]
    for pid in NEAR:
        x = 375 / 2 + (at[pid]["x"] - v["cx"]) * v["s"]
        y = 604 / 2 + (at[pid]["y"] - v["cy"]) * v["s"]
        assert 40 <= x <= 335 and 58 <= y <= 604 - 54, pid


def test_picking_a_place_dims_the_rest_and_enlarges_it():
    """第二層：點的那一處放大、其餘退成四成。"""
    low = near_parts(_game(), sel='"yingchuan"')["parts"][0]
    assert re.search(r'<g class="n-icon" data-act="region-place" data-id="yingchuan"[^>]*scale\(([\d.]+)\)', low)
    big = float(re.search(r'data-id="yingchuan" transform="[^"]*scale\(([\d.]+)\)', low).group(1))
    small = float(re.search(r'data-id="yingshui" transform="[^"]*scale\(([\d.]+)\)', low).group(1))
    assert big > small * 1.3
    assert re.search(r'<g class="n-label" data-act="region-place" data-id="yingshui"[^>]*opacity="0.4"', low)
    assert not re.search(r'<g class="n-label" data-act="region-place" data-id="yingchuan"[^>]*opacity', low)


def test_the_card_puts_name_owner_minutes_and_the_two_walks_first():
    """卡只佔三分之一：名字、誰的、幾分、步行與疾行在前；往上拉才有能悟、對手、人物、今日產出。"""
    game = _game()
    out = run(game, 'return [H.placeCard(H.S.mapBase, H.S.mapState, "yingchuan"), H.peekPx(600)];', mapMode="place", mapSel="yingchuan")
    card, peek = out
    assert card.index('class="m-line"') < card.index('data-mode="walk"') < card.index("往上拉") < card.index("此地的對手")
    assert peek == 200  # 三分之一


def test_the_top_row_is_region_name_full_and_world():
    """上面一排只剩大區名、「全區」、「天下」；塗層只在全區那一排、版圖在天下圖那一排。"""
    game = _game()
    near = run(game, "return H.regionTopHtml();")
    assert 'data-act="map-full"' in near and 'data-act="map-world"' in near and "region-pick" in near
    assert "map-wash" not in near and "map-timeline" not in near and 'aria-pressed="false"' in near
    full = run(game, "return H.regionTopHtml();", mapLayer="region")
    assert 'class="r-full on"' in full and "map-wash" in full


def test_opening_the_map_starts_at_the_first_layer_again():
    """「全區」按過只這一次有效：每一次打開輿圖都回第一層、1 倍、沒點地點；江湖頁小地圖點了遠處，開那一處所在的全區。"""
    game = _game()
    out = run(game, "H.mapFirst(); const a = [H.S.mapLayer, H.S.mapRegion, H.S.mapSel, H.S.mapPan, H.mapxClass()];"
              " H.mapFirst('yingshui'); const b = [H.S.mapLayer, H.S.mapSel, H.S.mapDrawer];"
              " H.mapFirst('wan_city'); const c = [H.S.mapLayer, H.S.mapRegion]; return [a, b, c];",
              mapLayer="region", mapRegion="nanyang", mapPan={"z": 2, "x": 5, "y": 5})
    assert out[0] == ["near", "yingru", None, None, "mapx region near"]
    assert out[1] == ["near", "yingshui", "peek"]
    assert out[2] == ["region", "nanyang"]


def test_the_closed_drawer_counts_the_roads_out():
    out = run(_game(), "return H.drawerHtml();", mapMode="overview", mapDrawer="min")
    assert "四條路，點一處出發。" in out and "其餘地點按「全區」" in out


def test_go_home_shows_only_after_dragging_away():
    """「回到我這」：第一層拖離原本的位置 80px 以上才出；全區看別區時也出。"""
    game = _game()
    js = ("const v = H.S.nearView = H.nearFit(H.S.mapBase, H.S.mapState, 375, 604); H.S.panFrom = { vw: 375, vh: 604 };"
          " const r = []; for (const p of [null, { z: 1, x: 30, y: 30 }, { z: 1, x: 120, y: 0 }]) { H.S.mapPan = p; r.push(H.homeFar()); } return r;")
    assert run(game, js) == [False, False, True]
    js2 = ("H.S.regionView = { s: 1, cx: 300, cy: 900, frame: [0, 0, 900, 1340] }; H.S.panFrom = { vw: 375, vh: 604 }; return H.homeFar();")
    assert run(game, js2, mapLayer="region", mapRegion="nanyang") is True
