"""FB-093～095（QA 走 joy 版序章與入伍段，main 8d4d470，2026-10-06）。

joy 在 GitHub 上也做了 FB-092～095（PR #30、#31），併進 main 之後 PM 裁示 joy 的為準（chain-on-main，2026-10-07）：我們的重複做法
拿掉了（FB-092 整段都是 joy 的，這裡沒有測試）。留下的是我們加在 joy 的做法上、她沒有的東西（結語、一週保底、網頁的「在下面 ↓」），
以及跑在 joy 的程式上、她的測試沒蓋到的情況。用真實內容（conftest 的 real、on：這個測試自己的一份複本）。
新寫的句子都在待 joy 潤的清單上（見 fb-report.md）：這裡的測試只認事實（講了什麼、對不對得上規則），不鎖死字句。"""
from __future__ import annotations

import re

import pytest
from test_prologue_web import run
from tests.test_orders import _game, _order

import server
import webharness
from tianxia import guide
from tianxia.rules import front_of


# ── FB-093：入伍第 2 步沒說軍令怎麼出力 ─────────────────────────────────
# joy 的版本（2026-10-07 併進 main，PM 裁示 joy 的為準）：每一道沒達成的軍令卡寫怎麼做（atlas.order_how）；第 2 步的 order_hint 點名
# 守勢行動；伺服器在框上帶能完成這一步的選項 id（guide.glow，enlist.glow），網頁讓它們發光、「此地還能做」打開。
# 這裡留下的是 joy 的測試沒蓋到的：每一種軍令卡、黃巾的守勢行動名字；我們的結語（不再整段背五種軍令）；網頁上我們加在 joy 的發光上的
# 三樣——收著的摺疊改由標題列發光、「在下面 ↓」、摺疊在那一步開頭只自動打開一次（tests/test_fb087_here_fold.py）。

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


def test_fb093_the_ending_no_longer_recites_every_kind(on):
    """結語（做完之後）把「每一種怎麼做」整段背一遍的部分縮成一句誇獎：怎麼做改寫在軍令卡上。"""
    for faction, who in on.tutorial.enlist.recruiters.items():
        for gone in ("就到那條戰線遊歷", "就在戰線上", "先備好糧草", "到軍令說的地方遊歷", "當面挑戰"):
            assert gone not in who.done, (faction, gone)
        assert len(who.done) < 100, faction  # 以前約 200 字
        assert "陣營" in who.done  # 「陣營 幾／幾」是什麼意思還講：那是卡片上的另一件事


# ── FB-094：豪強入伍第 2 步這一週做不到 ─────────────────────────────────
# joy 選甲（Game._duty：守勢行動不在這週軍令裡也算第 2 步；tests/test_orders.py 三邊各一條）。這裡留下 joy 的測試沒蓋到的：
# 有守城軍令時巡哨照樣替它記一次又走完這一步、別的行動不算；豪強的結語（我們的）；一週（季曆）之後還沒做完，引薦人照樣說結語、
# 入伍段關起來（我們加的保底，joy 的版本沒有：enlist.expire、PlayerState.enlist_since）。


def _finished(game, on):
    assert enlist_done(game.state, on) and game.state.player.enlist_end
    box = game.guide_box()
    assert box["key"] == "enlist_end" and box["end"]
    return box


def enlist_done(state, content):
    from tianxia import enlist

    return enlist.done(state, content)


def test_fb094_patrolling_under_a_defence_order_credits_it_once_and_finishes_the_step(on):
    game = _enlisted(on, "guan")
    order = _order(game, "defend", "guan", front=front_of(on, "changshe"), quota=900)
    game.choose("act:duty")
    _finished(game, on)
    assert order.progress == {game.state.player.name: 1}  # 有守城軍令時，這一下照舊替它記了一次（軍令不動）


def test_fb094_other_actions_do_not_finish_it(on):
    game = _enlisted(on, "guan")
    game.choose("act:rest")
    assert not enlist_done(game.state, on)


def test_fb094_the_magnates_ending_says_what_the_peace_is_for(on):
    done = on.tutorial.enlist.recruiters["haoqiang"].done
    assert "保境安民是守自家地盤" in done and "家主吩咐的大事" in done and "夠格" in done
    assert "不守城" not in done and "牆在自己家裡" not in done  # 舊的說法（不攻城也不守城）跟現在對不上


def test_fb094_a_week_later_the_recruiter_says_the_ending_anyway(on):
    """一週（季曆）之後第一道軍令還沒做完：引薦人照樣說結語、入伍段關起來。從那一步開始算起，不看電腦時鐘（世界時間）。"""
    from tianxia import calendar

    game = _enlisted(on, "haoqiang", place="cao_manor")
    week = calendar.WEEK / calendar.cal_scale(on, game.state.world)
    game.advance(week - 60)
    game.sync(1.0)
    assert not enlist_done(game.state, on)  # 還差一分鐘
    assert game.guide_box()["key"] == "r3_first_order"
    game.advance(120)
    game.sync(2.0)
    box = _finished(game, on)
    assert box["speaker"] == "季伯平" and box["text"] == on.tutorial.enlist.recruiters["haoqiang"].done
    assert any(line.startswith("【季伯平】") and "保境安民" in line for e in game.state.journal for line in e.guide)  # 說的話記進江湖紀錄
    game.guide_ack()
    game.sync(3.0)
    assert game.guide_box() is None  # 關了就是關了：不會再開


def test_fb094_the_week_counts_from_when_the_step_started_not_from_joining(on):
    from tianxia import calendar

    # 投靠之後晾了 0.7 週才去看軍令卡：第一道軍令那一步從看卡的那一刻才開始，一週從那裡算（不是從投靠）。
    # 距投靠 1.3 週、距那一步開始 0.6 週時還不收；距那一步 1.1 週才收（審查 I-1：以前兩件事在同一刻做，算錯起點也看不出來）
    game = _game(on, at="cao_manor")
    game.state.player.tutorial_step = len(guide.steps(game.state, on))
    game.set_hints_off(True)
    game.choose("faction:haoqiang")
    game.choose("faction:confirm")
    week = calendar.WEEK / calendar.cal_scale(on, game.state.world)
    joined = game.state.player.enlist_since
    game.advance(week * 0.7)
    game.sync(1.0)
    assert game.guide_box()["key"] == "r2_briefing"
    game.view_orders()
    p = game.state.player
    assert game.guide_box()["key"] == "r3_first_order" and p.enlist_since == game.state.world.time > joined
    game.advance(week * 0.6)
    game.sync(2.0)
    assert game.guide_box()["key"] == "r3_first_order" and not enlist_done(game.state, on)
    game.advance(week * 0.5)
    game.sync(3.0)
    _finished(game, on)


def test_fb094_the_fallback_only_touches_the_order_step_and_old_saves_start_their_week_when_loaded(on):
    from tianxia import calendar, enlist

    game = _game(on, at="changshe")
    game.state.player.tutorial_step = len(guide.steps(game.state, on))
    game.set_hints_off(True)
    game.choose("faction:guan")
    game.choose("faction:confirm")
    week = calendar.WEEK / calendar.cal_scale(on, game.state.world)
    game.advance(week * 3)
    game.sync(1.0)
    assert game.guide_box()["key"] == "r2_briefing" and game.state.player.enlist_step == 0  # 看軍令卡那一步不被收掉
    game.view_orders()
    game.state.player.enlist_since = None  # 這一版之前存的角色：沒有記下那一步什麼時候開始
    assert enlist.expire(game.state, on) == [] and game.state.player.enlist_since == game.state.world.time  # 從現在算起的一週


# ── FB-095：剛出師的新角色去黃巾別部營寨遊歷，挨了三場打 ───────────────────────────
# joy 的版本：遊歷的標籤寫「必敗」時選項帶 confirm（engine.TRAIN_CONFIRM），網頁用自己的 ask() 問一次、按「照打」才送；師父出師那句
# 多一句別去營寨惹事（她的測試：tests/test_orders.py::test_hopeless_training_asks_first_and_fair_training_does_not）。這裡留下她的測試沒蓋到的：真的算出來的必敗、勝算表上每一個字、不算勝算的
# 選單（機器人）不問也不擲骰、伺服器照常打、網頁上問與取消（同一個 Option.confirm、同一個 ask()，PM 裁示用到同一件東西的測試留著）。


def _train(game):
    return next(o for o in game.options() if o.id == "act:train")


@pytest.mark.parametrize("word, asks", [("必敗", True), ("凶險", False), ("難分勝負", False), ("五五波", False), ("有把握", False), ("穩勝", False)])
def test_fb095_only_a_losing_fight_asks_first(on, monkeypatch, word, asks):
    """問不問看遊歷按鈕上的勝算那一個字（Game.odds，標籤用的就是它）：只有「必敗」問；勝算表上其他每一個字都不問。"""
    from tianxia.engine import TRAIN_CONFIRM, Game

    game = _game(on, at="huangjin_camp")  # 散人在黃巾的營寨：對手是黃巾的人
    monkeypatch.setattr(Game, "odds", lambda self, squad_id: word)
    option = _train(game)
    assert word in option.label
    assert (option.confirm == TRAIN_CONFIRM) is asks and (option.confirm != "") is asks


def test_fb095_a_real_newcomer_at_the_yellow_turban_camp_is_asked(on):
    """真的算出來的（不是換掉 odds）：新角色威力 0，在黃巾別部營寨遊歷寫必敗，按鈕帶著問句。"""
    game = _game(on, at="huangjin_camp")
    game.state.player.member.wugong_id = None
    option = _train(game)
    assert "必敗" in option.label and option.confirm


def test_fb095_options_without_odds_never_ask_and_listing_them_rolls_nothing(on):
    """假人與整季機器人（bot.pick、bot_policy）看的是不算勝算的選單：沒有問句；列出選單也不碰 game.rng（算勝算用固定種子）。"""
    game = _game(on, at="huangjin_camp")
    game.state.player.member.wugong_id = None
    state = game.rng.getstate()
    plain = {o.id: o for o in game.options(odds=False)}
    assert plain["act:train"].confirm == "" and "必敗" not in plain["act:train"].label
    game.options()
    assert game.rng.getstate() == state
    assert all(o.confirm == "" for o in game.options(odds=False))


def test_fb095_asking_is_the_pages_job_the_server_never_refuses_or_rolls(on):
    """問一次是網頁的事：伺服器收到 act:train 就照常打（機器人、腳本都這樣走），取消的人根本沒有送出；所以取消不花體力、不擲骰。"""
    game = _game(on, at="huangjin_camp")
    game.state.player.member.wugong_id = None
    before = game.state.player.stamina
    state = game.rng.getstate()
    assert _train(game).confirm and game.state.player.stamina == before and game.rng.getstate() == state  # 看選單什麼都沒花
    game.choose("act:train")
    assert game.state.player.stamina < before and game.rng.getstate() != state  # 送出了才花、才擲


_ASK_SCRIPT = """return (async () => {
  const click = (act, id) => T.docListeners.click[0]({ target: { closest: () => ({ dataset: { act, id }, classList: { contains: () => false, add() {}, remove() {} } }) } });
  T.qs['.ask [data-act="ask-no"]'] = { focus() {} };
  const seen = [];
  await click("choose", "act:train");
  seen.push({ asked: T.bodyHtml.join("").includes("%(ask)s"), calls: T.calls.map((c) => c[0]) });
  %(then)s
  return { seen, calls: T.calls.map((c) => [c[0], c[1]]) };
})();"""


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_fb095_the_page_asks_with_its_own_dialog_then_fights_only_on_yes(on):
    from tianxia.engine import TRAIN_CONFIRM

    game = _game(on, at="huangjin_camp")
    game.state.player.member.wugong_id = None
    m = server.main_view(game)
    train = next(o for o in m["options"] if o["id"] == "act:train")
    assert train["confirm"] == TRAIN_CONFIRM
    after = {"main": m, "message": ""}
    cancel = _ASK_SCRIPT % {"ask": TRAIN_CONFIRM, "then": 'await click("ask-no");'}
    out = run(m, cancel, responses={"/api/choose": after})
    assert out["seen"] == [{"asked": True, "calls": []}] and out["calls"] == []  # 問了；取消之後什麼都沒送
    yes = _ASK_SCRIPT % {"ask": TRAIN_CONFIRM, "then": 'await click("ask-yes");'}
    out = run(m, yes, responses={"/api/choose": after})
    assert out["seen"][0]["calls"] == [] and out["calls"] == [["/api/choose", {"id": "act:train"}]]  # 按「照打」才送
    m_safe = {**m, "options": [{**o, "confirm": ""} if o["id"] == "act:train" else o for o in m["options"]]}
    out = run(m_safe, _ASK_SCRIPT % {"ask": TRAIN_CONFIRM, "then": ""}, responses={"/api/choose": {"main": m_safe, "message": ""}})
    assert out["seen"][0]["asked"] is False and out["calls"] == [["/api/choose", {"id": "act:train"}]]  # 不必敗的：不問、直接打


def _enlist_main(on, faction="guan"):
    """第 2 步的 /api/main：這週只有一道守城軍令（清掉開季的軍令，伺服器帶的 guide.glow 才只有守勢行動那一顆，見 enlist.glow）。"""
    game = _enlisted(on, faction)
    game.state.world.orders = []
    _order(game, "defend", faction, front=front_of(on, JOIN_AT[faction]))
    return server.main_view(game)


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_fb093_the_glow_lands_on_the_defence_button_in_the_page(on):
    """網頁：框上帶 glow（伺服器照 joy 的 enlist.glow 給的選項 id）時，「此地還能做」摺疊打開、applyGlow 給巡哨那顆（data-id）加 glow；
    沒有 glow 的框一個也不加。"""
    m = _enlist_main(on)
    assert m["guide"]["glow"] == ["act:duty"] and any(o["id"] == "act:duty" for o in m["options"])
    html = run(m, "return H.actionBar(m);")
    assert re.search(r'<details class="fold here" open>', html)  # 收著的話按鈕看不到，發光就沒有意義：發光的這一步先打開
    assert re.search(r'data-act="choose" data-id="act:duty" >', html) and "data-glow=\"act:duty\"" not in html  # 認 id，不另寫 data-glow
    script = "const e = T.button('act:duty'); const other = T.button('act:rest'); H.applyGlow(); return [[...e.classes], [...other.classes]];"
    assert run(m, script) == [["glow"], []]
    quiet = {**m, "guide": {k: v for k, v in m["guide"].items() if k != "glow"}}
    assert run(quiet, script) == [[], []]  # 沒有 glow 的框：什麼都不亮（跟序章之外一向一樣）
    assert not re.search(r'<details class="fold here" open>', run(quiet, "return H.actionBar(m);"))


# FB-W1（走查 375×812）：第一道軍令那一步發光的鈕在「此地還能做」摺疊裡，底邊 802、在分頁列（756）底下，框上卻沒有「在下面 ↓」——
# 以前只有序章的框有（pro()）。任何帶 glow 的框（入伍段）發光的東西沒整個露在第一屏裡，都要有；提示框不發光，沒有目標就沒有。
_CUE = """
  const inserted = [];
  T.qs[".card.guide .guide-head"] = { firstElementChild: { insertAdjacentHTML: (pos, html) => inserted.push([pos, html]) }, querySelector: () => null };
  T.qs[".tabs"] = { getBoundingClientRect: () => ({ top: 756 }) };
  const at = (top, bottom, via = "cue") => {
    T.qs["#page .glow"] = { getBoundingClientRect: () => ({ top, bottom }) };
    inserted.length = 0;
    if (via === "cue") H.guideCue(); else { T.button("act:duty"); H.applyGlow(); }
    return inserted.length;
  };
  %s"""


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_fbw1_an_enlistment_box_points_below_when_its_glowing_button_is_cut_off(on):
    m = _enlist_main(on)
    assert m["guide"]["glow"] == ["act:duty"]
    script = _CUE % """return {
      below: at(740, 802), peeking: at(747, 813), onScreen: at(500, 560), touching: at(696, 756),
      viaApplyGlow: at(740, 802, "glow"), html: (at(740, 802), inserted[0]),
      none: (delete T.qs["#page .glow"], inserted.length = 0, H.guideCue(), inserted.length) };"""
    out = run(m, script)
    assert out["below"] == 1 and out["peeking"] == 1 and out["viaApplyGlow"] == 1  # 底邊在分頁列（756）底下：要有
    assert out["onScreen"] == 0 and out["touching"] == 0 and out["none"] == 0  # 整個看得到、或沒有發光的東西：不要
    assert out["html"][0] == "afterend" and 'data-act="guide-below"' in out["html"][1] and "在下面 ↓" in out["html"][1]


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_fbw1_a_box_without_a_glow_never_gets_the_cue(on):
    """提示框、沒有 glow 的入伍框：頁面上就算有別的東西在發光，也不是它們指的。"""
    m = _enlist_main(on)
    quiet = {**m, "guide": {k: v for k, v in m["guide"].items() if k != "glow"}}
    out = run(quiet, _CUE % "return { below: at(740, 802), viaApplyGlow: at(740, 802, 'glow') };")
    assert out == {"below": 0, "viaApplyGlow": 0}
    hint = {**m, "guide": {"key": "h_lose", "speaker": "想起師父說過", "text": "…", "line": "…", "hint": True, "full": True}}
    assert run(hint, _CUE % "return at(740, 802);") == 0
    assert run({**m, "guide": None}, _CUE % "return at(740, 802);") == 0  # 沒有框就沒有地方放


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_fbw1_the_cue_for_an_enlistment_box_is_worked_out_again_on_resize(on):
    m = _enlist_main(on)
    script = """return (async () => {
      const inserted = [];
      T.qs[".card.guide .guide-head"] = { firstElementChild: { insertAdjacentHTML: (pos, html) => inserted.push(html) }, querySelector: () => null };
      T.qs[".tabs"] = { getBoundingClientRect: () => ({ top: 756 }) };
      T.qs["#page .glow"] = { getBoundingClientRect: () => ({ top: 740, bottom: 802 }) };
      (T.listeners.resize || []).forEach((fn) => fn());
      await new Promise((resolve) => setTimeout(resolve, 400));
      return inserted.length;
    })();"""
    assert run(m, script) == 1


# ── 審查之後的最後一輪（review-fb.md、fb-fix-brief.md）──────────────────────────────────────────────
# 老石結語不說沒發生的事。（第 2 步多的那一句與「做得了」的判斷跟著 FB-093 拿掉了：joy 的版本由引薦人的 order_hint 點名守勢
# 行動、軍令卡寫怎麼做；火的提醒跟著 FB-092 拿掉了；「守勢行動只記一次」釘的是我們的 or_actions，跟著 FB-094 換成 joy 的 _duty。）


def test_fbx_the_ending_does_not_claim_a_last_action_was_counted(on):
    """老石的結語寫過「你剛剛那一下，也算在裡頭」，可是守勢行動沒有軍令可記、或一週到了什麼都沒做就收段時，沒有什麼被記進去
    （審查 Minor 2）。三位的結語都不說這種事。"""
    for faction, who in on.tutorial.enlist.recruiters.items():
        assert "剛剛" not in who.done and "也算在裡頭" not in who.done, faction
        assert "陣營" in who.done, faction  # 卡片上「陣營 幾／幾」是什麼意思還講
    game = _enlisted(on, "guan")
    game.choose("act:duty")  # 這一週沒有守城軍令：巡哨替誰都沒記
    box = _finished(game, on)
    assert "也算在裡頭" not in box["text"]


