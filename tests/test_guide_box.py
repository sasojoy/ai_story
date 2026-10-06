"""引導小改版（新手引導重做設計第八節）：說書人的話放在行動列上方的對話框，「剛剛」只放這次行動的結果。

用測試夾具的內容：說書人三步（先探索一下〔獎勵銀兩 5〕→ 去湖邊 → 看看地圖），結語「去闖吧。」。開關照夾具（關著）——
這個小改版不看開關。"""
from __future__ import annotations

import pytest
import webharness
from conftest import walk_to
from tianxia import journal
from tianxia.models import ExploreMix

STEP_ONE, STEP_TWO, STEP_THREE, OUTRO = "先探索一下。", "去湖邊。", "看看地圖。", "去闖吧。"


STEP_KEYS = {STEP_ONE: "s1", STEP_TWO: "s2", STEP_THREE: "s3", OUTRO: "outro"}  # 框上的 key：步驟的 id（結語是 outro），不看那一句話


def _box(text, done=(), end=False, key=None, pending=False):
    return {
        "speaker": "說書人", "key": key or STEP_KEYS[text], "scene": "", "text": text, "line": "", "done": list(done), "end": end,
        "pending": pending,
    }  # pending：這一句是「先把眼前的「…」了結」（網頁預設把它收成一行，FB-076）


def pending_line(title):
    return f"先把眼前的「{title}」了結"


def _explore_event(game):
    game.content.config.explore_mix = [ExploreMix(kind="wild", tags=[], weights={"event": 1})]


def test_a_new_character_sees_the_first_step_in_the_box(game):
    """8.3：全新角色一進江湖頁就有對話框與第一步的話；開場那一則「剛剛」只有劇本的開場，說書人那一句記在 guide。"""
    assert game.guide_box() == _box(STEP_ONE)
    entry = game.state.journal[0]
    assert entry.lines == ["測試開始。"] and entry.guide == [f"【說書人】{STEP_ONE}"]
    assert "說書人" not in journal.card_html(entry)
    assert f"【說書人】{STEP_ONE}" in journal.rows_html([entry])  # 江湖紀錄照舊看得到


def test_finishing_a_step_goes_to_the_box_not_the_latest_card(game):
    """RF1：做完一步，「剛剛」只有這次行動的結果；獎勵照舊只套一次，「✔ 引導完成」與獎勵在對話框，接著是下一步的話；
    江湖紀錄的那一則把引導記在 guide。下一次行動清掉完成的那幾行。"""
    _explore_event(game)
    silver = game.state.player.stats["silver"]
    msgs = game.choose("act:explore")
    assert game.state.player.stats["silver"] == silver + 5
    assert "✔ 引導完成" not in msgs and f"【說書人】{STEP_TWO}" not in msgs
    entry = game.state.journal[0]
    assert (entry.lines, entry.changes) == ([], [])
    assert entry.guide == ["✔ 引導完成", "銀兩 +5", f"【說書人】{STEP_TWO}"]
    assert "引導完成" not in journal.card_html(entry) and "銀兩 +5" not in journal.card_html(entry)
    title = game.content.events[game.state.pending_event].title
    assert game.guide_box() == _box(pending_line(title), ["✔ 引導完成", "銀兩 +5"], key="s2", pending=True)  # 眼前還有事件：先了結它（FB-063）；key 還是這一步的
    game.choose("choice:1")
    assert game.guide_box() == _box(STEP_TWO)


def test_a_pending_event_replaces_the_step_text_until_it_is_settled(game):
    """FB-063：事件還沒了結時不推教學那一步（叫人往郊野走、事件卻擋著路），框上寫「先把眼前的「…」了結」；
    事件了結後是原來那一步，步驟本身沒有動。每一步都一樣，不只是叫人出發的那幾步。"""
    p = game.state.player
    for step, text in enumerate((STEP_ONE, STEP_TWO, STEP_THREE)):
        p.tutorial_step = step
        game.state.pending_event = "drunk"
        assert game.guide_box() == _box(pending_line("醉漢"), key=f"s{step + 1}", pending=True)  # 說書人還是說書人，key 還是這一步的
        assert p.tutorial_step == step
        game.state.pending_event = None
        assert game.guide_box() == _box(text)


def test_the_box_key_is_the_step_not_the_sentence(game):
    """FB-076：網頁記「收起」記的是 key，不是那一句話：「先把眼前的「…」了結」每遇到新事件就換一句，記句子的話每個新事件都把收起的框
    又展開（選項底到 903、分頁列頂 755）。key 是這一步的 id（結語是 outro）：同一步不管有沒有事件、事件叫什麼，都是同一個 key；
    換到下一步才換。"""
    p = game.state.player
    for step, key in enumerate(("s1", "s2", "s3")):
        p.tutorial_step = step
        plain = game.guide_box()
        keys = {plain["key"]}
        assert plain["pending"] is False
        for event in ("drunk", "chain_a"):
            game.state.pending_event = event
            pending = game.guide_box()
            assert pending["text"] != plain["text"]  # 句子換了
            assert pending["pending"] is True  # 網頁認這個旗標，不去讀句子的字
            keys.add(pending["key"])
        game.state.pending_event = None
        assert keys == {key}  # key 不跟著換
    p.tutorial_step, p.guide_outro = 3, True
    assert game.guide_box()["key"] == "outro"
    game.state.pending_event = "drunk"
    assert game.guide_box()["pending"] is False  # 結語照舊：事件擋不了它


def test_a_pending_event_blanks_the_steps_short_line_so_the_collapsed_box_shows_the_pending_sentence(game, monkeypatch):
    """FB-076：序章之外的步驟也可能寫了收起來那一行（TutorialStep.line，例：「師父：回『江湖』按『探索』」）。事件待處理時框上的話換成
    「先把眼前的「…」了結」，收起來那一行也得跟著換——不然收著的框寫著這一步的短提示、跟事件擋著路互相矛盾。所以待處理時 line 送空字串
    （網頁收起來那一行是 `line || text`），了結之後原樣回來。序章自己在事件出現時整個框都不畫（tests/test_prologue.py），不歸這裡。"""
    monkeypatch.setattr(game.content.tutorial.steps[1], "line", "說書人：去湖邊")
    game.state.player.tutorial_step = 1
    assert game.guide_box()["line"] == "說書人：去湖邊" and game.guide_box()["text"] == STEP_TWO
    game.state.pending_event = "drunk"
    box = game.guide_box()
    assert box["pending"] is True and box["text"] == pending_line("醉漢") and box["line"] == ""
    game.state.pending_event = None
    assert game.guide_box() == _box(STEP_TWO) | {"line": "說書人：去湖邊"}


def test_a_chained_event_names_the_step_that_is_pending_now_in_the_box(game):
    """next_event 接下去的下一段：框上寫現在待處理的那一則。"""
    game._present(game.content.events["chain_a"])
    assert game.guide_box()["text"] == pending_line("跟蹤")
    game.choose("choice:0")
    assert game.state.pending_event == "chain_b"
    assert game.guide_box()["text"] == pending_line("倉庫")
    game.choose("choice:0")
    assert game.guide_box()["text"] == STEP_ONE


def test_the_outro_is_shown_even_while_an_event_is_pending(game):
    """結語（end）照舊：全部做完了，沒有「下一步」可以擋。"""
    game.state.player.tutorial_step = 3
    game.state.player.guide_outro = True
    game.state.pending_event = "drunk"
    assert game.guide_box() == _box(OUTRO, end=True)


def test_finishing_the_last_step_shows_the_outro_until_acknowledged(game):
    """全部做完：對話框是結語，按「知道了」之後不再出現。"""
    game.state.player.tutorial_step = 1
    walk_to(game, "lake")
    assert game.guide_box() == _box(STEP_THREE, ["✔ 引導完成"])
    game.view_map()
    assert game.guide_box() == _box(OUTRO, ["✔ 引導完成"], end=True)
    assert game.state.journal[0].guide[-1] == f"【說書人】{OUTRO}"
    assert game.guide_ack() == []
    assert game.guide_box() is None


def test_finished_before_the_box_shows_nothing(game):
    """RF4：舊存檔裡早就做完引導的角色，沒有結語要看，對話框不出現。"""
    game.state.player.tutorial_step = 3
    assert game.guide_box() is None


def test_skipping_hides_the_box(game):
    game.skip_tutorial()
    assert game.guide_box() is None


def test_skipping_stays_skipped_into_the_next_season():
    """畫面批次審查 I4：beta 那一季略過新手引導，換成第一季之後也不再出現對話框（第一季的軍令兩步已經由入伍段取代，新手引導計畫二：
    引導的步驟兩種季一樣多）。略過的人入伍段也算走完（設計 7.3），帶到下一季；沒略過、做完序章十一步的人換季後沒有框
    （沒有第一季才有的步驟了），入伍段等他投靠才開始。"""
    import random
    from pathlib import Path

    from tianxia.characters import open_characters
    from tianxia.content import load_content
    from tianxia.engine import Game
    from tianxia.guide import base_step_count
    from tianxia.sqlite_world import open_world

    root = Path(__file__).parent.parent / "content"
    beta = load_content(root)
    beta.config.auto_open_first_season, beta.config.admins = True, ["管"]
    chars = open_characters()
    admin = Game.new(beta, "管", rng=random.Random(1))
    # 略過的人是在草廬裡按了「略過序章」的真人（走完序章、站在起點的人再按略過什麼都不做：引導已經做完了）
    skipper, finisher = Game.new(beta, "略過的", rng=random.Random(2), prologue=True), Game.new(beta, "做完的", rng=random.Random(3))
    skipper.skip_tutorial()
    base = base_step_count(beta)  # 序章十一步；第一季也只有這些
    assert len(beta.tutorial.steps) == base
    finisher.state.player.tutorial_step = base
    for game in (admin, skipper, finisher):
        chars.save(game.state)
    admin.admin_end_season(now=100.0)
    on = load_content(root)
    on.config.admins, on.config.season_one, on.config.season_days = ["管"], True, 2.5
    admin = Game(on, chars.load("管"), rng=random.Random(1), world=open_world())
    admin.admin_next_season(now=200.0)
    games = {name: Game(on, chars.load(name), rng=random.Random(4), world=open_world()) for name in ("略過的", "做完的")}
    for game in games.values():
        game.sync(300.0)
        assert game.state.player.tutorial_step == base
    # 沒有引導的步驟、沒有結語了。只剩碰到才說（新手引導計畫三）：開季一同步就補上這一季已經揭曉的大事，所以兩個人都聽到那一條（略過的人
    # 照樣有提示）；做完的人另外多開季師父送行那一句，略過的人沒有要誰帶、師父不送
    assert [n.id for n in games["做完的"].state.player.hint_queue][:1] == ["s_return"]
    assert games["做完的"].guide_box()["key"] == "s_return" and games["做完的"].guide_box()["end"] is True
    assert "s_return" not in [n.id for n in games["略過的"].state.player.hint_queue]
    assert games["略過的"].guide_box()["hint"] is True  # 說書人與入伍段的框沒有，只有提示
    for game in games.values():
        game.set_hints_off(True)  # 之後看的是引導與入伍段的框：提示排著的清掉、不再排
        assert game.guide_box() is None
    assert games["略過的"].state.player.guide_skipped and not games["做完的"].state.player.guide_skipped  # 略過照帶
    assert games["略過的"].state.player.enlist_step == len(on.tutorial.enlist.steps)  # 略過的人入伍段算走完，換季照帶
    assert games["做完的"].state.player.enlist_step is None  # 還沒投靠：投靠時才開始
    for game in games.values():  # 兩個人到長社投靠：略過的沒有框、沒略過的由引薦人帶（框只在投靠之後才分得出兩個人）
        game.state.player.location = "changshe"
        game.choose("faction:guan")
        game.choose("faction:confirm")
    assert games["略過的"].guide_box() is None
    assert games["做完的"].guide_box()["speaker"] == "老石"


# ── 網頁：收起記的是 key（FB-076）。把 web/app.js 裡說書人那一段切出來在 node 裡跑；沒有 node 就略過 ─────────────

APP = webharness.APP
DRIVER = r"""
const a = src.indexOf("\n  const GUIDE_KEY");
const b = src.indexOf("\n  }\n", src.indexOf("\n  function guideHtml(")) + 4;
if (a < 0 || b < 4) throw new Error("app.js 裡找不到說書人的那一段");
const store = {};
globalThis.localStorage = input.broken
  ? { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); }, removeItem() { throw new Error("blocked"); } }
  : { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: (k) => { delete store[k]; } };
const S = { guideRoad: null, guideFull: null };
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
// guideKey 是網頁拿來認「這一步」的函式；沒有它（舊版）就退回認句子，好讓舊版在這裡是斷言失敗、不是找不到函式
// openGuide、shutGuide 是「展開」「收起」兩顆鈕做的事（點擊的 switch 只是呼叫它們）；沒有它們（舊版）就是 null
const pro = () => null; // guideHtml 問序章（pro()）：這裡的框不在序章裡
const H = new Function("S", "esc", "pro", src.slice(a, b) + "\nreturn { guideHtml, guideShut, setGuideShut, guideKey: typeof guideKey === 'function' ? guideKey : (g) => g.text, openGuide: typeof openGuide === 'function' ? openGuide : null, shutGuide: typeof shutGuide === 'function' ? shutGuide : null };")(S, esc, pro);
const box = (key, text, end = false, pending = false, done = []) => ({ speaker: "說書人", key, text, done, end, pending });
const shown = (g, onRoad = false) => { const html = H.guideHtml(g, onRoad); return html.includes('class="guide-line"') ? "line" : html.includes("card guide") ? "card" : html ? "?" : ""; };
finish(new Function("H", "S", "box", "shown", input.script)(H, S, box, shown));
"""


def run_js(script, broken=False):
    if webharness.NODE is None:
        pytest.skip("沒有 node")
    return webharness.run(DRIVER, {"script": script, "broken": broken})


def test_a_collapsed_box_stays_collapsed_when_a_pending_event_changes_the_sentence():
    """FB-076：玩家把框收起之後，同一步的話換成「先把眼前的「…」了結」（每個新事件換一句）不能把它又展開；換到下一步才展開。
    收起的那一下記的是 key（網頁的 guideKey），不是那一句話。"""
    got = run_js("""
      const step = box("s2", "去湖邊。");
      const before = shown(step);                                   // 還沒收起：展開著
      H.setGuideShut(H.guideKey(step));                             // 玩家按「收起」
      return {
        before,
        same: shown(step),
        pending: shown(box("s2", "先把眼前的「掉落的書信」了結", false, true)),   // 打完一仗，接著冒出事件
        another: shown(box("s2", "先把眼前的「倒地的對手」了結", false, true)),   // 下一個事件、又換一句
        back: shown(step),                                           // 事件了結，回到原來那一步
        nextStep: shown(box("s3", "看看地圖。")),                    // 真的換到下一步：照舊展開
        outro: shown(box("outro", "去闖吧。", true)),                // 結語沒有收起這回事
      };
    """)
    assert got == {"before": "card", "same": "line", "pending": "line", "another": "line", "back": "line", "nextStep": "card", "outro": "card"}


def test_the_pending_event_sentence_starts_collapsed_even_if_the_player_never_collapsed_the_box():
    """FB-076（控制者裁示）：「先把眼前的「…」了結」只是重複底下事件卡片已經寫的話，展開時事件的選項被擠到 903 px——這一句預設收成一行，
    不管玩家有沒有按過「收起」。只有這一句：真的新的一步照舊展開；玩家還是可以點開。"""
    got = run_js("""
      const pending = box("s2", "先把眼前的「掉落的書信」了結", false, true);
      return {
        plain: shown(box("s2", "去湖邊。")),          // 一般的一步：沒收起過就是展開的
        pending: shown(pending),                     // 事件的句子：預設收成一行
        nextPending: shown(box("s2", "先把眼前的「倒地的對手」了結", false, true)),  // 下一個事件、又換一句：照樣收著
        newStep: shown(box("s3", "看看地圖。")),      // 了結之後又是新的一步：展開
        outro: shown(box("outro", "去闖吧。", true)), // 結語：展開
        remembered: H.guideShut(),                   // 預設收起不動玩家記的東西
      };
    """)
    assert got == {"plain": "card", "pending": "line", "nextPending": "line", "newStep": "card", "outro": "card", "remembered": None}


def test_a_pending_sentence_with_something_to_acknowledge_opens_as_before():
    """審查 I1：新角色的第一次探索常常做完 t1_explore 又留下一個事件（量到 200 個新角色裡 163 個）：框上有「✔ 引導完成」與獎勵
    （done）。收成一行的話那一列就看不到了（「剛剛」卡片依設計不放引導），所以 done 不是空的時候這一句照舊展開；
    done 是空的（FB-076 量的那一場：遊歷打完接事件）才預設收著。玩家按過「收起」的照舊收著。"""
    got = run_js("""
      const done = ["✔ 引導完成", "銀兩 +10"];
      const withDone = box("s2", "先把眼前的「酒樓鬥毆」了結", false, true, done);
      const html = H.guideHtml(withDone, false);
      const out = {
        open: shown(withDone),
        showsDone: html.includes("✔ 完成") && html.includes("銀兩 +10"),
        emptyDone: shown(box("s2", "先把眼前的「酒樓鬥毆」了結", false, true, [])),
      };
      H.shutGuide(withDone);                       // 玩家自己收起：照舊收著，不管有沒有 done
      out.afterShut = shown(withDone);
      return out;
    """)
    assert got == {"open": "card", "showsDone": True, "emptyDone": "line", "afterShut": "line"}


def test_the_collapsed_line_is_the_steps_short_line_unless_an_event_is_pending():
    """收起來那一行是 `line || text`：一般的一步用它自己的短提示；事件待處理時伺服器把 line 送空，那一行就是「先把眼前的…了結」。"""
    got = run_js("""
      const step = { ...box("s2", "去湖邊。"), line: "說書人：去湖邊" };
      H.setGuideShut("s2");
      const pending = { ...box("s2", "先把眼前的「掉落的書信」了結", false, true), line: "" };
      return { step: H.guideHtml(step, false).includes("說書人</b>：說書人：去湖邊"), pending: H.guideHtml(pending, false).includes("說書人</b>：先把眼前的「掉落的書信」了結") };
    """)
    assert got == {"step": True, "pending": True}


def test_a_player_can_expand_the_pending_sentence_and_it_stays_open_for_that_sentence_only():
    got = run_js("""
      const first = box("s2", "先把眼前的「掉落的書信」了結", false, true);
      const second = box("s2", "先把眼前的「倒地的對手」了結", false, true);
      const before = shown(first);                  // 收著
      H.openGuide(first);                           // 玩家點開
      const opened = shown(first), redrawn = shown(first);  // 輪詢重畫不會又收起來
      const nextEvent = shown(second);              // 換了一個事件（新的一句）：又是預設收著
      H.openGuide(second);
      const settled = shown(box("s2", "去湖邊。")); // 事件了結、回到原來那一步：一般的一步，展開著
      const afterLeaving = shown(second);           // 離開之後記的展開清掉了：同一句再冒出來又收著
      H.shutGuide(second);                          // 玩家收起（記的是這一步的 key）
      return { before, opened, redrawn, nextEvent, settled, afterLeaving, step: shown(box("s2", "去湖邊。")), shut: H.guideShut() };
    """)
    assert got == {
        "before": "line", "opened": "card", "redrawn": "card", "nextEvent": "line", "settled": "card", "afterLeaving": "line",
        "step": "line", "shut": "s2",
    }


def test_expanding_a_pending_sentence_clears_the_remembered_collapse_like_any_other_step():
    got = run_js("""
      const pending = box("s2", "先把眼前的「掉落的書信」了結", false, true);
      H.setGuideShut("s2");                         // 玩家先前收起過這一步
      const shut = shown(pending);                  // 照舊收著
      H.openGuide(pending);                         // 玩家點開：展開、同時清掉「收起」的記憶（跟一般的一步一樣）
      return { shut, opened: shown(pending), plainAfter: shown(box("s2", "去湖邊。")), remembered: H.guideShut() };
    """)
    assert got == {"shut": "line", "opened": "card", "plainAfter": "card", "remembered": None}


def test_the_road_still_collapses_the_box_by_default_and_a_blocked_storage_does_not_break_it():
    got = run_js("""return { road: shown(box("s2", "去湖邊。"), true), open: shown(box("s2", "去湖邊。")) };""", broken=True)
    assert got == {"road": "line", "open": "card"}  # localStorage 讀不到：只在這一頁有效，不丟例外


def test_the_page_stores_the_key_when_the_player_shuts_the_box():
    js = APP.read_text(encoding="utf-8")
    shut = next(line for line in js.splitlines() if 'case "guide-shut":' in line)
    assert "shutGuide(S.main.guide)" in shut
    assert "setGuideShut(guideKey(g))" in js[js.index("function shutGuide("):js.index("function guideHtml(")]
    assert "guideShut() === guideKey(g)" in js[js.index("function guideHtml("):]
    assert "openGuide(S.main.guide)" in next(line for line in js.splitlines() if 'case "guide-open":' in line)


def test_box_hidden_while_preparing(prologue_content, world, monkeypatch):
    """籌備中選單照舊只有「賽季籌備中」，序章也不例外：對話框不出現（新手引導計畫一 Review Focus 5）。"""
    from tianxia.engine import Game

    game = Game.new(prologue_content, "沈浪", world=world, prologue=True)
    game.choose("choice:0")
    game.choose("choice:0")
    assert game.guide_box() is not None
    monkeypatch.setattr(game, "_preparing", lambda: True)
    assert game.guide_box() is None
