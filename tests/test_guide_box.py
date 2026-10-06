"""引導小改版（新手引導重做設計第八節）：說書人的話放在行動列上方的對話框，「剛剛」只放這次行動的結果。

用測試夾具的內容：說書人三步（先探索一下〔獎勵銀兩 5〕→ 去湖邊 → 看看地圖），結語「去闖吧。」。開關照夾具（關著）——
這個小改版不看開關。"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import walk_to
from tianxia import journal
from tianxia.models import ExploreMix

STEP_ONE, STEP_TWO, STEP_THREE, OUTRO = "先探索一下。", "去湖邊。", "看看地圖。", "去闖吧。"


STEP_KEYS = {STEP_ONE: "s1", STEP_TWO: "s2", STEP_THREE: "s3", OUTRO: "outro"}  # 框上的 key：步驟的 id（結語是 outro），不看那一句話


def _box(text, done=(), end=False, key=None):
    return {"speaker": "說書人", "key": key or STEP_KEYS[text], "text": text, "done": list(done), "end": end}


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
    assert game.guide_box() == _box(pending_line(title), ["✔ 引導完成", "銀兩 +5"], key="s2")  # 眼前還有事件：先了結它（FB-063）；key 還是這一步的
    game.choose("choice:1")
    assert game.guide_box() == _box(STEP_TWO)


def test_a_pending_event_replaces_the_step_text_until_it_is_settled(game):
    """FB-063：事件還沒了結時不推教學那一步（叫人往郊野走、事件卻擋著路），框上寫「先把眼前的「…」了結」；
    事件了結後是原來那一步，步驟本身沒有動。每一步都一樣，不只是叫人出發的那幾步。"""
    p = game.state.player
    for step, text in enumerate((STEP_ONE, STEP_TWO, STEP_THREE)):
        p.tutorial_step = step
        game.state.pending_event = "drunk"
        assert game.guide_box() == _box(pending_line("醉漢"), key=f"s{step + 1}")  # 說書人還是說書人，key 還是這一步的
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
        for event in ("drunk", "chain_a"):
            game.state.pending_event = event
            pending = game.guide_box()
            assert pending["text"] != plain["text"]  # 句子換了
            keys.add(pending["key"])
        game.state.pending_event = None
        assert keys == {key}  # key 不跟著換
    p.tutorial_step, p.guide_outro = 3, True
    assert game.guide_box()["key"] == "outro"


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
    """畫面批次審查 I4：beta 那一季略過新手引導（停在第 6 步），換成第一季（8 步，多了軍令兩步）之後也不再出現對話框；
    步驟照 T6 的規則記著（做完照樣推進），只是不畫框。沒略過、做完六步的人照 T6 接著做，框照常出現。"""
    import random
    from pathlib import Path

    from tianxia.characters import open_characters
    from tianxia.content import load_content
    from tianxia.engine import Game
    from tianxia.sqlite_world import open_world

    root = Path(__file__).parent.parent / "content"
    beta = load_content(root)
    beta.config.auto_open_first_season, beta.config.admins = True, ["管"]
    chars = open_characters()
    admin = Game.new(beta, "管", rng=random.Random(1))
    skipper, finisher = Game.new(beta, "略過的", rng=random.Random(2)), Game.new(beta, "做完的", rng=random.Random(3))
    skipper.skip_tutorial()
    finisher.state.player.tutorial_step = 6
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
        assert game.state.player.tutorial_step == 6
    assert games["略過的"].guide_box() is None
    assert games["做完的"].guide_box()["text"] == on.tutorial.steps[6].text


# ── 網頁：收起記的是 key（FB-076）。把 web/app.js 裡說書人那一段切出來在 node 裡跑；沒有 node 就略過 ─────────────

NODE = shutil.which("node")
APP = Path(__file__).parent.parent / "web" / "app.js"
DRIVER = r"""
const fs = require("fs");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const src = fs.readFileSync(input.app, "utf8").replace(/\r\n/g, "\n");
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
const H = new Function("S", "esc", src.slice(a, b) + "\nreturn { guideHtml, guideShut, setGuideShut, guideKey: typeof guideKey === 'function' ? guideKey : (g) => g.text };")(S, esc);
const box = (key, text, end = false) => ({ speaker: "說書人", key, text, done: [], end });
const shown = (g, onRoad = false) => { const html = H.guideHtml(g, onRoad); return html.includes('class="guide-line"') ? "line" : html.includes("card guide") ? "card" : html ? "?" : ""; };
const out = new Function("H", "S", "box", "shown", input.script)(H, S, box, shown);
process.stdout.write(JSON.stringify(out === undefined ? null : out));
"""


def run_js(script, broken=False):
    if NODE is None:
        pytest.skip("沒有 node")
    done = subprocess.run(
        [NODE, "-e", DRIVER], input=json.dumps({"app": str(APP), "script": script, "broken": broken}),
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


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
        pending: shown(box("s2", "先把眼前的「掉落的書信」了結")),   // 打完一仗，接著冒出事件
        another: shown(box("s2", "先把眼前的「倒地的對手」了結")),   // 下一個事件、又換一句
        back: shown(step),                                           // 事件了結，回到原來那一步
        nextStep: shown(box("s3", "看看地圖。")),                    // 真的換到下一步：照舊展開
        outro: shown(box("outro", "去闖吧。", true)),                // 結語沒有收起這回事
      };
    """)
    assert got == {"before": "card", "same": "line", "pending": "line", "another": "line", "back": "line", "nextStep": "card", "outro": "card"}


def test_a_box_that_was_never_collapsed_is_open_for_a_pending_event_as_before():
    got = run_js("""return { plain: shown(box("s2", "去湖邊。")), pending: shown(box("s2", "先把眼前的「掉落的書信」了結")) };""")
    assert got == {"plain": "card", "pending": "card"}


def test_the_road_still_collapses_the_box_by_default_and_a_blocked_storage_does_not_break_it():
    got = run_js("""return { road: shown(box("s2", "去湖邊。"), true), open: shown(box("s2", "去湖邊。")) };""", broken=True)
    assert got == {"road": "line", "open": "card"}  # localStorage 讀不到：只在這一頁有效，不丟例外


def test_the_page_stores_the_key_when_the_player_shuts_the_box():
    js = APP.read_text(encoding="utf-8")
    shut = next(line for line in js.splitlines() if 'case "guide-shut":' in line)
    assert "setGuideShut(guideKey(S.main.guide))" in shut
    assert "guideShut() === guideKey(g)" in js[js.index("function guideHtml("):]
