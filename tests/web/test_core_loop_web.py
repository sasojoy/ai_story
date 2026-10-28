"""行動列：出陣那一格寫今日剩幾次、探索那一格點了展開三顆（出陣探索與地盤設計第七節）。沒有 node 就略過。
這一份先放出陣那一半（PM 2026-10-14：Task 4 另外平行做，探索展開的部分等它合進來再補）。"""
from __future__ import annotations

import random

import pytest
from test_prologue_web import run

import server
import webharness
from conftest import classic_rules, real_content
from jianfa_kit import classic_explore
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


def _game(faction, at, classic=False):
    c = real_content("week7")  # 出陣推線的舊規則（領地爭奪 PM 2026-10-22 起正式內容打開）
    classic_explore(c)  # 探索三選一（減法季探索一顆開著時只剩一顆）
    c.config.auto_open_first_season = True
    if classic:
        classic_rules(c)
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.faction, p.location, p.stamina = faction, at, float(c.config.stamina_max)
    return game


def _bar(game, **S):
    return run(server.main_view(game), "return H.actionBar(H.S.main);", S=S)


def test_the_explore_cell_unfolds_three_ways():
    game = _game(None, "yingshui")
    bar = _bar(game)
    assert 'data-act="wheel" data-key="explore"' in bar and "act-explore" not in bar
    assert 'data-id="explore:gather"' not in bar  # 收著時三顆不畫，也不掉進「此地還能做」（行動列底下那一行會提到「找素材」）
    bar = _bar(game, wheelSel="explore")
    assert 'class="card act-explore"' in bar
    assert all(f'data-id="explore:{m}"' in bar for m in ("gather", "seek", "sense"))


def test_a_tired_explorer_sees_the_cell_greyed():
    game = _game(None, "yingshui")
    game.state.player.stamina = 0
    bar = _bar(game, wheelSel="explore")
    assert 'data-key="explore"' in bar and "體力不夠" in bar and "act-explore" not in bar


# ── 出陣約戰（減法季批 3b；企劃者 2026-10-28 在對比圖裡選丙）──
# 約戰開著時出陣那一格（act:train）點了在行動列底下展開出陣前那張卡（main.sortie_card）、不送 act:train；灰著也點得開、卡底的鈕寫原因；
# 封好三招送 sortie_go；約戰卡（main.sorties）一張一行：應戰打開同一張封三招的卡、送 sortie_answer，同去送 sortie_join，別區的「前往」走現有的移動。
# 截糧的運糧隊經過時照舊送 act:train；沒有 sortie_card 時行動列一個字不變。資料是真的引擎給的（duel_kit 的兩個真人照伺服器的做法各自重讀）

CLICKS = """return (async () => {
  const target = (dataset) => ({ dataset, classList: { contains: () => false, add() {}, remove() {} } });
  const click = (dataset) => T.docListeners.click[0]({ target: { closest: () => target(dataset) } });
  const bars = [];
  for (const dataset of input.clicks) { await click(dataset); bars.push(H.S.tab === "jianghu" ? H.actionBar(H.S.main) : ""); }
  return { calls: T.calls.filter((c) => c[0] === "/api/choose" || c[0].startsWith("/api/do/sortie")).map((c) => [c[0], c[1]]),
           wheel: H.S.wheelSel, answer: H.S.sortieAnswer, pick: H.S.sortiePick, tab: H.S.tab, mapSel: H.S.mapSel, route: H.S.glowRoute, bars };
})();"""


def _clicks(m, clicks, *, S=None, responses=None):
    import json

    script = CLICKS.replace("input.clicks", json.dumps(clicks, ensure_ascii=False))
    return run(m, script, S=S or {}, responses=responses or {})


def _duel_cast():
    """官軍的甲、黃巾的乙站在汝南荒野（中立地），甲貼一張約戰之前的世界。"""
    from duel_kit import duel_content, duel_world, seat

    c = duel_content()
    world = duel_world(c)
    seat(c, world, "甲", "guan")
    seat(c, world, "乙", "huang")
    return c, world


def _view(c, world, name, now=None):
    from duel_kit import NOW, game_of

    return server.main_view(game_of(c, world, name, NOW if now is None else now))


def _cell(bar):
    start = bar.index('data-key="train"')
    return bar[bar.rindex("<button", 0, start):bar.index("</button>", start)]


@pytest.mark.slow
def test_the_sortie_cell_opens_the_card_and_never_sends_act_train():
    c, world = _duel_cast()
    m = _view(c, world, "甲")
    assert m["sortie_card"] and not m["sortie_card"]["why_not"]
    cell = _cell(_bar_of(m))
    assert 'data-act="sortie-open" aria-expanded="false"' in cell and 'data-id="act:train"' not in cell and "今日 2 次" in cell
    out = _clicks(m, [{"act": "sortie-open"}, {"act": "sortie-open"}])
    assert out["calls"] == []  # 不送 act:train（伺服器只會回一句「封好三招再出陣」）
    opened, closed = out["bars"]
    assert 'class="card act-sortie" id="sortie-panel"' in opened and "<b>出陣・汝南荒野</b>" in opened
    assert 'aria-expanded="true"' in _cell(opened) and " on" in _cell(opened)
    assert "<b>這一塊</b>" in opened and "<b>贏了</b>" in opened and "<b>封三招</b>" in opened
    assert "中立・官 0／黃 0・還差 100 易手" in opened  # 陣營名照卡上的 sides（劇本），不寫死
    assert opened.count('data-act="sortie-move"') == 12 and "第三回合" in opened  # 三排各四招
    cfg = c.config.sortie
    assert f"{cfg.window_minutes:g} 分鐘後開打" in opened  # 窗幾分鐘照卡上的 window_minutes
    assert ('<button class="btn primary sx-go" data-act="sortie-send" disabled><b>還要挑 3 招</b>'
            f"<small>體力 {cfg.jianfa_stamina}・今日還能 {cfg.jianfa_per_day} 次</small>") in opened
    assert "act-sortie" not in closed and out["wheel"] is None  # 再點一次收起


@pytest.mark.slow
def test_sealing_three_moves_posts_sortie_go_and_folds_the_card():
    c, world = _duel_cast()
    m = _view(c, world, "甲")
    picks = [{"act": "sortie-move", "round": "0", "move": "強攻"}, {"act": "sortie-move", "round": "1", "move": "奇襲"}]
    out = _clicks(m, [{"act": "sortie-open"}, *picks, {"act": "sortie-send"}])  # 兩招就按：鈕是灰的，假瀏覽器照樣按得到，也不送
    assert out["calls"] == [] and "還要挑 1 招" in out["bars"][-1]
    done = {"main": m, "message": "你在汝南荒野替官軍貼出約戰"}
    out = _clicks(m, [{"act": "sortie-open"}, *picks, {"act": "sortie-move", "round": "2", "move": "固守"}, {"act": "sortie-send"}],
                  responses={"/api/do/sortie_go": done})
    sealed = out["bars"][-2]
    assert "<b>封好三招，出陣</b><small>強攻・奇襲・固守・體力 12・今日還能 2 次</small>" in sealed
    assert 'data-act="sortie-send">' in sealed  # 亮了
    assert out["calls"] == [["/api/do/sortie_go", {"moves": ["強攻", "奇襲", "固守"]}]]
    assert out["wheel"] is None and out["pick"] == [] and "act-sortie" not in out["bars"][-1]  # 回來之後卡收起


@pytest.mark.slow
def test_a_grey_cell_still_opens_and_the_button_says_why():
    from duel_kit import NOW, do, seat

    from tianxia import conquest

    c, world = _duel_cast()
    season = world.get_season()
    own = next(b for b in conquest.blocks(c) if conquest.capturable(c, b) and conquest.holder(season, c, b) == "guan")
    seat(c, world, "丙", "guan", own)  # 官軍自家的地方：等對面來約
    m = _view(c, world, "丙")
    assert not next(o for o in m["options"] if o["id"] == "act:train")["enabled"]
    bar = _bar_of(m, wheelSel="sortie")
    assert 'data-act="sortie-open" aria-expanded="true"' in _cell(bar) and "等對面約" in _cell(bar)
    assert "官軍的地方・黃巾軍推到 0／100" in bar and "<b>贏了</b>" not in bar and "這裡不貼約戰" in bar
    assert "黃巾軍推滿 100 才翻走這裡・還差 100" in bar
    assert '<button class="btn primary sx-go" data-act="sortie-send" disabled><b>等對面來約</b>' in bar
    do(c, world, "甲", lambda g: g.choose("sortie:go:強攻,固守,奇襲"))  # 甲貼過一張：冷卻 60 分、今天還剩一次
    m = _view(c, world, "甲", NOW + 18 * 60)
    bar = _bar_of(m, wheelSel="sortie")
    assert "冷卻中" in _cell(bar) and "<b>冷卻中・還要 42 分</b><small>體力 12・今日還能 1 次</small>" in bar
    assert 'class="sx-sec sx-dim"' in bar and bar.count('aria-pressed="false" disabled>') == 12  # 招淡掉、按不下去


@pytest.mark.slow
def test_the_three_duel_cards_answer_join_and_walk():
    from duel_kit import FAR, LOC, do, seat

    c, world = _duel_cast()
    seat(c, world, "丙", "guan")  # 同袍
    seat(c, world, "丁", "huang", FAR)  # 對面、別區
    do(c, world, "甲", lambda g: g.choose("sortie:go:強攻,固守,奇襲"))
    duel_id = next(iter(world.sortie_duels()))
    mine = _bar_of(_view(c, world, "甲", 1_792_000_060.0))
    assert "<b>約戰</b><span>1 張・窗滿就開打</span>" in mine and "等人應戰・剩 9 分" in mine and ">自己</span>" in mine
    # 對面、同一區：應戰 → 同一張封三招的卡，卡頂寫應戰；挑滿三招送 sortie_answer
    m = _view(c, world, "乙", 1_792_000_060.0)
    bar = _bar_of(m)
    assert '>官軍</span><span class="sx-dt"><b>甲</b>約戰<span class="sx-pl">汝南荒野</span></span><span class="sx-left">9 分</span>' in bar
    assert f'data-act="sortie-answer" data-id="{duel_id}">應戰</button>' in bar
    out = _clicks(m, [{"act": "sortie-answer", "id": duel_id}, *[{"act": "sortie-move", "round": str(i), "move": "固守"} for i in range(3)],
                      {"act": "sortie-send"}], responses={"/api/do/sortie_answer": {"main": m, "message": ""}})
    answering = out["bars"][0]
    assert "<b>應戰・汝南荒野</b><span>甲約戰・還有 9 分</span>" in answering and "sx-duels" not in answering  # 應戰時約戰卡收起
    assert "<b>守住了</b>" in answering and "<b>贏了</b>" not in answering and "9 分後開打" in answering
    assert "<b>封好三招，應戰</b><small>固守・固守・固守・體力 12・今日還能應戰 3 次</small>" in out["bars"][-2]
    assert out["calls"] == [["/api/do/sortie_answer", {"id": duel_id, "moves": ["固守", "固守", "固守"]}]]
    assert out["answer"] is None
    # 同袍：同去
    m = _view(c, world, "丙", 1_792_000_060.0)
    bar = _bar_of(m)
    assert f'data-act="sortie-join" data-id="{duel_id}">同去</button>' in bar and ">同袍</span>" in bar
    out = _clicks(m, [{"act": "sortie-join", "id": duel_id}], responses={"/api/do/sortie_join": {"main": m, "message": ""}})
    assert out["calls"] == [["/api/do/sortie_join", {"id": duel_id}]]
    # 對面、別區：應戰按不下去，鈕寫「前往 N 分」，按了照現有的移動（不相鄰：開輿圖那一處的卡）
    m = _view(c, world, "丁", 1_792_000_060.0)
    card = m["sorties"][0]
    assert not card["can_answer"] and not card["same_region"]
    bar = _bar_of(m)
    assert f'data-act="sortie-far" data-id="{LOC}">前往 {card["travel_minutes"]} 分</button>' in bar and "sx-far" in bar
    assert "1 張在別區" in bar and 'data-act="sortie-answer"' not in bar
    out = _clicks(m, [{"act": "sortie-far", "id": LOC}], responses={"/api/do/view_map": {"main": m}})
    assert out["tab"] == "map" and out["mapSel"] == LOC and out["calls"] == []


# FB-901（QA 2026-10-28）：「前往 N 分」展開移動後往那一處的那一條光只亮 24 毫秒（重插的摺疊 toggle、下一次輪詢重畫都把 .glow 清掉）。
# 現在要發光的那一條記在 S.glowRoute，畫移動卡時直接寫進 class、applyGlow 清掉之後也補回；按了選項、收起移動卡、換分頁、走了就熄


def _far_view():
    """官軍的甲在白馬津貼約戰，黃巾的乙站長社（隔著大區、相鄰）：乙的約戰卡別區那一行「前往」，移動清單上有往白馬津的路。"""
    from duel_kit import NOW, do, seat

    c, world = _duel_cast()
    seat(c, world, "甲", "guan", "baima_ford")
    seat(c, world, "乙", "huang", "changshe")
    do(c, world, "甲", lambda g: g.choose("sortie:go:強攻,固守,奇襲"))
    m = _view(c, world, "乙", NOW + 60)
    assert any(o["id"] == "move:baima_ford" for o in m["options"]) and m["sorties"][0]["block"] == "baima_ford"
    return m


@pytest.mark.slow
def test_far_travel_keeps_the_route_glow_in_the_state_and_the_class():
    m = _far_view()
    out = _clicks(m, [{"act": "sortie-far", "id": "baima_ford"}])
    assert out["wheel"] == "move" and out["route"] == "move:baima_ford"
    bar = out["bars"][0]
    assert 'class="btn go glow" data-act="choose" data-id="move:baima_ford"' in bar and bar.count(" glow") == 1  # 只有那一條
    # 輪詢重畫：S 還在，畫出來照樣帶光（以前加在畫好的元素上，一重畫就沒了）
    assert 'class="btn go glow" data-act="choose" data-id="move:baima_ford"' in _bar_of(m, wheelSel="move", glowRoute="move:baima_ford")
    assert " glow" not in _bar_of(m, wheelSel="move")


@pytest.mark.slow
def test_apply_glow_puts_the_route_glow_back_after_it_clears_everything():
    """摺疊 toggle 之後跑的 applyGlow 第一行清掉所有 .glow：路的光要在它後面補回來。"""
    m = _far_view()
    script = """
      const here = T.button("move:baima_ford"), other = T.button("move:runan_wilds");
      H.S.wheelSel = "move"; H.S.glowRoute = "move:baima_ford";
      H.applyGlow(); H.applyGlow();  // toggle 一次又一次
      const kept = [here.classes.has("glow"), other.classes.has("glow")];
      H.S.wheelSel = null; H.applyGlow();  // 移動卡收起：光熄、記的也清掉
      return { kept, closed: [here.classes.has("glow"), H.S.glowRoute] };"""
    out = run(m, script)
    assert out["kept"] == [True, False] and out["closed"] == [False, None]


@pytest.mark.slow
def test_the_route_glow_goes_out_when_nothing_is_left_to_point_at():
    m = _far_view()
    stale = {**m, "options": [o for o in m["options"] if not o["id"].startswith("move:baima_ford")]}  # 走了、換了地方：清單上沒有那一條
    script = "H.S.wheelSel = 'move'; H.S.glowRoute = 'move:baima_ford'; const bar = H.actionBar(H.S.main); return { glow: bar.includes(' glow'), route: H.S.glowRoute };"
    assert run(stale, script) == {"glow": False, "route": None}
    on_map = "H.S.tab = 'map'; H.S.wheelSel = 'move'; H.S.glowRoute = 'move:baima_ford'; H.applyGlow(); return H.S.glowRoute;"
    assert run(m, on_map) is None  # 換分頁
    out = _clicks(m, [{"act": "sortie-far", "id": "baima_ford"}, {"act": "choose", "id": "move:baima_ford"}],
                  responses={"/api/choose": {"main": m}})
    assert out["route"] is None  # 按了選項


@pytest.mark.slow
def test_the_newbie_go_button_keeps_its_route_glow_the_same_way():
    m = _far_view()
    m["status"]["newbie"] = {"title": "新手目標", "done": 0, "total": 1, "rows": [
        {"text": "走一趟", "reward": "回體丹", "go": {"move": "baima_ford", "place": "白馬津"}, "drifter": False}]}
    out = _clicks(m, [{"act": "newbie-go", "i": "0"}])
    assert out["wheel"] == "move" and out["route"] == "move:baima_ford"
    assert 'class="btn go glow" data-act="choose" data-id="move:baima_ford"' in out["bars"][0]


# FB-902（QA 2026-10-28）：320 寬別區那一行只剩約 103 px 放「某某約戰某地」，三字名號加四字地名被收成「…」。窄寬時那一段准兩行、
# 地名整個不拆（.sx-pl）；360、375 不加任何規則。真正的幾何在瀏覽器裡量（CSS 在 node 裡排不了版）


def test_a_narrow_phone_lets_the_duel_text_wrap_and_keeps_the_place_whole():
    import re
    from pathlib import Path

    css = (Path(__file__).parents[2] / "web" / "style.css").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert re.search(r"(?m)^\.sx-drow \.sx-dt \{[^}]*white-space: nowrap;[^}]*text-overflow: ellipsis", css)  # 平常（360、375）照舊一行
    narrow = re.search(r"@media \(max-width: 340px\) \{\n((?:  [^\n]*\n)+)\}", css)
    assert narrow and ".sx-drow .sx-dt { white-space: normal; overflow: visible; text-overflow: clip; }" in narrow.group(1)
    assert ".sx-drow .sx-dt .sx-pl { display: inline-block; white-space: nowrap; }" in narrow.group(1)
    assert css.count(".sx-pl {") == 1  # 只有那一條規則認它，寬的畫面沒有任何東西跟著變
    row = {"id": "d", "block": "yingchuan_wilds", "place": "潁川郊野", "attacker": "鄧七郎", "attacker_side": "guan", "defender": None,
           "expires_in": 300, "answers_left": 3, "same_region": False, "travel_minutes": 15, "result": None, "why_not": "在汝南才應得了戰",
           "can_answer": False, "can_join": False, "status": "open", "role": "answer"}
    bar = run({"options": [], "sorties": [row], "status": {}}, "return H.actionBar(H.S.main);")
    assert '<span class="sx-dt"><b>鄧七郎</b>約戰<span class="sx-pl">潁川郊野</span></span>' in bar  # 地名自己一段，換行只換在「約戰」與它之間


# FB-903（QA 2026-10-28）：站在不是區塊的地方應戰（南華觀、豪族塢堡……）沒有出陣卡，陣營名都寫「對面」、底鈕少了「體力 12」，按下去照樣扣。
# 現在約戰卡自己帶 sides 與 answer_stamina，網頁先讀它


@pytest.mark.slow
def test_answering_off_a_block_still_names_the_armies_and_shows_the_stamina():
    from duel_kit import do, seat

    c, world = _duel_cast()
    seat(c, world, "乙", "huang", "jade_cave")  # 南華觀：潁川汝南的地方、不是區塊
    do(c, world, "甲", lambda g: g.choose("sortie:go:強攻,固守,奇襲"))
    duel_id = next(iter(world.sortie_duels()))
    m = _view(c, world, "乙", 1_792_000_060.0)
    assert "sortie_card" not in m and m["sorties"][0]["can_answer"]
    bar = _bar_of(m)
    assert ">官軍</span><span" in bar and ">對面</span>" not in bar  # 約戰卡上的小章寫陣營名
    picks = [{"act": "sortie-move", "round": str(i), "move": "固守"} for i in range(3)]
    out = _clicks(m, [{"act": "sortie-answer", "id": duel_id}, *picks])
    opened, sealed = out["bars"][0], out["bars"][-1]
    assert "官軍的進度被拉回" in opened and "對面的進度被拉回" not in opened  # 「守住了」那一段也寫陣營名
    assert "<b>還要挑 3 招</b><small>體力 12・今日還能應戰 3 次</small>" in opened
    assert "<b>封好三招，應戰</b><small>固守・固守・固守・體力 12・今日還能應戰 3 次</small>" in sealed


# FB-904（PM 照 QA 驗收順帶開，2026-10-28）：守方應戰卡「這一塊」那一行的小籤寫的是看的人自己推這一塊（「推滿 100 易手・還差 75」「同袍還沒人來」），
# 跟這一場應戰無關。現在寫這一場牽動什麼：約戰那一軍推到幾、離翻走（沒人佔的拿下）還差多少，守住了拉回它；資料是約戰卡自己帶的，站在哪裡都一樣


@pytest.mark.slow
@pytest.mark.parametrize("where", ["runan_wilds", "jade_cave"])  # 站在約戰的那一塊上／站在同一區不是區塊的地方
def test_the_answer_card_says_what_this_fight_touches_not_my_own_push(where):
    from duel_kit import do, seat

    from tianxia import conquest

    c, world = _duel_cast()
    seat(c, world, "乙", "huang", where)
    do(c, world, "甲", lambda g: g.choose("sortie:go:強攻,固守,奇襲"))

    def push(g):  # 官軍在汝南荒野推到 30
        conquest._fight(g.state.world, c, "runan_wilds").bars.setdefault("guan", conquest.Bar()).value = 30.0

    do(c, world, "甲", push)
    duel_id = next(iter(world.sortie_duels()))
    m = _view(c, world, "乙", 1_792_000_060.0)
    out = _clicks(m, [{"act": "sortie-answer", "id": duel_id}])
    card = out["bars"][0]
    assert '<summary><b>這一塊</b><span>官軍 30／100・還差 70 拿下</span></summary>' in card  # 沒人佔的地方寫「拿下」
    assert ">官軍</span>" in card and '<span class="sf-num">30</span>' in card and '<span class="sf-num">0</span>' in card  # 兩條：對面 30、自己這一邊 0
    assert "官軍推滿 100 才拿下・還差 70" in card and "對面沒人在推" in card and "守住了能拉回它的進度" in card
    assert "推滿 100 易手" not in card and "同袍還沒人來" not in card and "集火" not in card  # 看的人自己推這一塊的小籤不在應戰卡上


def test_a_held_block_says_flip_and_a_card_without_numbers_only_names_the_place():
    base = {"id": "d", "block": "b", "place": "某地", "attacker": "甲", "attacker_side": "huang", "defender": None, "expires_in": 300, "answers_left": 3,
            "same_region": True, "travel_minutes": None, "result": None, "why_not": "", "can_answer": True, "can_join": False, "status": "open",
            "role": "answer", "sides": {"guan": "官軍", "huang": "黃巾軍"}, "answer_stamina": 12}
    held = {**base, "holder": "guan", "bars": {"mine": 60, "theirs": 25}, "to_flip": 75, "foe_pushing": 2}
    for row, line in ((held, "黃巾軍 25／100・還差 75 翻走"), (base, None)):
        m = {"options": [], "sorties": [row], "status": {}}
        card = run(m, "H.S.sortieAnswer = 'd'; return H.actionBar(H.S.main);")
        if line:
            assert f"<span>{line}</span>" in card and "黃巾軍推滿 100 才翻走・還差 75" in card and "對面 2 人在推" in card
            assert '<span class="sf-name">官軍</span>' in card and '<span class="sf-num">60</span>' in card
        else:
            assert '<p class="sx-flat"><b>這一塊</b><span>某地</span></p>' in card  # 舊資料沒有那幾個鍵：只寫地名


def test_duel_rows_sort_and_settled_ones_say_how_it_went():
    base = {"block": "b", "place": "某地", "attacker_side": "huang", "defender": None, "expires_in": 300, "answers_left": 3,
            "same_region": True, "travel_minutes": None, "result": None, "why_not": "", "can_answer": False, "can_join": False}
    rows = [
        {**base, "id": "done", "attacker": "戊", "status": "settled", "role": "mine", "result": "險勝", "expires_in": 0},
        {**base, "id": "void", "attacker": "己", "status": "void", "role": "answer", "expires_in": 0},
        {**base, "id": "grey", "attacker": "庚", "status": "open", "role": "answer", "why_not": "今日應戰 3 次已用完"},
        {**base, "id": "mine", "attacker": "辛", "status": "answered", "role": "mine", "defender": "守軍", "attacker_side": "guan"},
        {**base, "id": "join", "attacker": "壬", "status": "open", "role": "join", "can_join": True, "attacker_side": "guan"},
        {**base, "id": "go", "attacker": "癸", "status": "open", "role": "answer", "can_answer": True},
    ]
    m = {"options": [], "sorties": rows, "status": {}}
    out = run(m, "return H.actionBar(H.S.main);")
    order = [out.index(f"<b>{who}</b>") for who in ("癸", "壬", "辛", "庚", "戊", "己")]
    assert order == sorted(order)  # 應得了、同去得了、自己的、其他還沒打的、結算完的
    assert "守軍應戰・剩 5 分" in out and ">險勝</span>" in out and ">沒打成</span>" in out
    assert '<button class="btn small" disabled>應戰</button></div><p class="sx-why">今日應戰 3 次已用完</p>' in out  # 灰的原因寫在那一行底下
    assert ">對面</span>" in out  # 沒有出陣卡（不知道陣營名）：對面的小章寫「對面」


@pytest.mark.slow
def test_a_passing_convoy_keeps_act_train_and_no_card_keeps_the_bar():
    c, world = _duel_cast()
    m = _view(c, world, "甲")
    m["sortie_card"]["convoy_at"] = "黃巾運糧隊"  # 截糧的運糧隊正經過：出陣那一格照舊直接打
    assert 'data-act="choose" data-id="act:train"' in _cell(_bar_of(m))
    out = _clicks(m, [{"act": "map-jianghu", "key": "sortie"}], S={"tab": "map"}, responses={"/api/choose": {"main": m}})
    assert out["calls"] == [["/api/choose", {"id": "act:train"}]]
    plain = {k: v for k, v in _view(c, world, "甲").items() if k not in ("sortie_card", "sorties")}
    bar = _bar_of(plain, wheelSel="sortie")
    assert 'data-act="choose" data-id="act:train"' in _cell(bar)
    assert all(x not in bar for x in ("sortie-open", "act-sortie", "sx-duels", "sx-"))  # 沒有 sortie_card：行動列一個字不變


@pytest.mark.slow
def test_the_map_cards_sortie_button_opens_the_card_on_the_jianghu_page():
    c, world = _duel_cast()
    m = _view(c, world, "甲")
    out = _clicks(m, [{"act": "map-jianghu", "key": "sortie"}], S={"tab": "map"})
    assert out["tab"] == "jianghu" and out["wheel"] == "sortie" and out["calls"] == []
    assert 'class="card act-sortie"' in out["bars"][0]


def _bar_of(m, **S):
    return run(m, "return H.actionBar(H.S.main);", S=S)
