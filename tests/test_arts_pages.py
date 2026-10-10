"""修練頁與煉製頁的畫面（arts-polish-1：W2、W5、W7、W9）。
web/app.js 沒有建置步驟、也沒有前端測試框架：這裡把兩頁的函式從原始碼切出來交給 node 跑（不相干的畫法換成一行的假貨），
檢查出來的 HTML 與按鈕按下去之後的動作。node 由 tests/webharness.py 跑（切函式的 fn、konst 也在那裡）；沒有 node 就略過。"""
from __future__ import annotations

import json
import re

import pytest

import webharness

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")

DRIVER = r"""
const calls = [];
const scrolls = [];
globalThis.window = { scrollTo: (...a) => scrolls.push(["to", ...a]), scrollBy: (...a) => scrolls.push(["by", ...a]), scrollY: input.scrollY || 0 };
const dom = { buttons: [] }; // 修練鈕（假的）：腳本改它的位置，模擬重畫之後按鈕被推走
globalThis.document = { getElementById: () => null, querySelector: () => null, querySelectorAll: () => dom.buttons };
const S = { stage: "game", tab: "practice", kind: "武學", artOpen: null, legendTick: {}, forgeSel: [], forgeLine: "", busy: false,
  message: "", person: null, main: { status: { injury: 0 } }, ...input.S };
const parts = [
  ...["KINDS", "QUALITY_RANK", "esc", "pro", "attrNoteHtml", "ART_FILTERS", "filterKey", "CRAFT_SORTS", "CRAFT_PAGE"].map(konst),
  ...input.consts.map(konst),
  // 卷軸卡的零件（品質印、機率條、十成格、療傷鈕、庫的篩選……）：「// ── 修練 ──」到 pagePractice 之間整段照抄
  src.slice(src.indexOf("\n  // ── 修練 ──"), src.indexOf("\n  function pagePractice(")),
  // artFilter…：煉製頁挑東西那一排的篩選（arts-polish-2 FB-085），pageCraft 畫的時候要用
  ...["forgeBody", "forgeReady", "pagePractice", "pageCraft", "artFilter", "setArtFilter", "showArts", "filterChips",
    "pickMark", "craftView", "craftFilterRow", "craftChip", "manualHtml", ...input.fns].map(fn),
  `const guideHtml = () => "", furnaceSvg = () => '<div class="furnace"></div>', proGuide = () => "";`,
  input.stubs || "",
  "return { " + ["pagePractice", "pageCraft", ...input.fns, ...input.consts].join(", ") + " };",
];
const H = new Function("S", "calls", parts.join("\n"))(S, calls);
H.S = S; H.calls = calls; H.scrolls = scrolls; H.dom = dom;
finish(new Function("H", "S", `return (async () => { ${input.script} })();`)(H, S));
"""


def run(script: str, *, S=None, consts=(), fns=(), stubs=""):
    return webharness.run(DRIVER, {"script": script, "S": S or {}, "consts": list(consts), "fns": list(fns), "stubs": stubs})


def art(id="basic_fist", name="基礎拳腳", kind="武學", worn=True, **over):
    row = {
        "id": id, "name": name, "kind": kind, "quality": "下品", "attribute": "剛", "level": 1, "worn": worn, "insight": None,
        "card": f"<p>【{name}】CARD</p>",
        "cultivate": {"ok": False, "note": "沒有融意境", "legend": None}, "melt": {"ok": not worn, "note": "退回心得 0"},
    }
    row.update(over)
    return row


def menxia(**over):
    x = {
        "xinde": 20, "rules": "<p>RULESLINE</p>", "attribute_note": "ATTRNOTE", "player_card": "<p>PLAYERCARD</p>",
        "roster": [{"label": "本人", "key": "player"}], "person": None, "person_card": None, "on_team": False, "bag": "<p>BAG</p>",
        "clue_items": [], "forge_line": "<p>FORGELINE</p>", "holdings": {"count": 2, "cap": 50}, "insights": [], "naming": None,
        "owned_arts": [art(), art("lake_kick", "湖邊腿法", worn=False)],
        "slot_cards": [
            {"kind": "武學", "card": "<p>WUGONG</p>", "learned": True, "level": 1, "maxed": False, "blocked": None, "price": 1},
            {"kind": "內功", "card": "<p>NEIGONG</p>", "learned": True, "level": 1, "maxed": False, "blocked": None, "price": 1},
        ],
    }
    x.update(over)
    return x


def page(name: str, x: dict, **S) -> str:
    return run(f"S.menxia = {json.dumps(x)}; return H.{name}();", S=S)


# ── W7：修練之後頁面留在原地，結果寫在那一門的卡片裡 ─────────────────────────

MX_STUBS = """
const busy = async (fn) => { await fn(); };
const api = async (url, body) => { calls.push([url, body]); return S.reply; };
const trimPot = () => {}, setMain = () => {}, renderTop = () => {};
const renderPage = () => { S.rendered = (S.rendered || 0) + 1; if (S.afterRender) S.afterRender(); };
"""


def press(op, extra, *, reply_menxia=None, moved_by=0, art_open="lake_kick", guide=(None, None), prologue=False):
    """在 node 裡按一次修練頁的鈕（mx）：伺服器回 reply_menxia，重畫之後那一門的「修練」鈕被推下去 moved_by px。
    guide 是（按之前, 按之後）說書人那一步（{key, text} 或 None）；prologue 是按之前在不在序章。
    回 S 裡我們關心的、捲動的動作（["by", …] 是相對捲動，["to", …] 是捲到某處）。"""
    before, after = guide
    script = f"""
      const pos = {{ v: 400 }};
      H.dom.buttons = [{{ dataset: {{ id: "lake_kick" }}, getBoundingClientRect: () => ({{ top: pos.v }}) }}];
      S.artOpen = {json.dumps(art_open)};
      S.main = {{ status: {{ injury: 0 }}, guide: {json.dumps(before)}, prologue: {json.dumps({"reveal": ["all"]} if prologue else None)} }};
      S.reply = {{ menxia: {json.dumps(reply_menxia or menxia())}, main: {{ guide: {json.dumps(after)} }}, message: "<p>RESULT</p>" }};
      S.afterRender = () => {{ pos.v += {moved_by}; }};
      await H.mx({json.dumps(op)}, {json.dumps(extra)});
      return {{ note: S.artNote || null, message: S.message, artOpen: S.artOpen, scrolls: H.scrolls, rendered: S.rendered, calls: H.calls }};
    """
    return run(script, fns=["mx", "cultivateTop", "guideKey"], stubs=MX_STUBS)


def test_cultivating_keeps_the_page_where_it_is_and_the_card_open():
    out = press("cultivate", {"art": "lake_kick", "use_legend": False}, moved_by=0)
    assert out["rendered"] == 1 and out["artOpen"] == "lake_kick"  # 那一門的卡片沒收
    assert not any(s[0] == "to" for s in out["scrolls"])  # 不再捲回頁首
    assert out["calls"][0][0] == "/api/menxia/cultivate"


def test_cultivating_holds_the_button_where_the_thumb_is_even_when_the_page_above_grows():
    """重畫整頁會讓頂上的訊息、卡片的高度變動：按鈕被推下去 60px，就往下捲 60px 補回來，玩家的拇指底下還是修練鈕。"""
    out = press("cultivate", {"art": "lake_kick"}, moved_by=60)
    assert [s for s in out["scrolls"] if s[0] == "by"] == [["by", {"top": 60, "left": 0, "behavior": "instant"}]]
    assert not any(s[0] == "to" for s in out["scrolls"])
    up = press("cultivate", {"art": "lake_kick"}, moved_by=-45)  # 頂上的訊息變短：反方向補
    assert [s for s in up["scrolls"] if s[0] == "by"] == [["by", {"top": -45, "left": 0, "behavior": "instant"}]]


def test_the_result_goes_into_that_arts_card_and_the_top_message_stays_too():
    out = press("cultivate", {"art": "lake_kick"})
    assert out["note"] == {"id": "lake_kick", "html": "<p>RESULT</p>"} and out["message"] == "<p>RESULT</p>"
    html = page("pagePractice", menxia(), artOpen="lake_kick", artNote={"id": "lake_kick", "html": "<p>RESULT</p>"})
    body = html.split('<div class="art-body')[1]
    assert body.index('class="acts"') < body.index('class="msg art-result"><p>RESULT</p>')  # 鈕的底下：結果就在按的那顆旁邊
    other = page("pagePractice", menxia(), artOpen="lake_kick", artNote={"id": "basic_fist", "html": "<p>RESULT</p>"})
    assert "art-result" not in other.split('<div class="art-body')[1]  # 別門（身上那張卡）的結果不寫在這一門裡


P6 = {"key": "p6_refine", "text": "師父：到「修練」修練【鎮風手】，衝一衝品質"}
P7 = {"key": "p7_rest", "text": "師父：體力見底了，按「打坐」歇一歇"}
TO_TOP = [["to", {"top": 0, "behavior": "smooth"}]]


def test_a_cultivate_that_moves_the_guide_to_the_next_step_scrolls_to_the_top():
    """I1：序章 p6_refine 的修練做完，師父的下一句（p7_rest）只在修練頁最上面與江湖頁看得到——不捲上去，新人就停在功法卡上看不到。
    不只序章：比的是說書人的步驟（key），任何一個被這次修練做完的引導步驟都一樣，所以這裡沒有特別認序章的草廬。"""
    out = press("cultivate", {"art": "lake_kick"}, moved_by=60, guide=(P6, P7), prologue=True)
    assert out["scrolls"] == TO_TOP
    outside = press("cultivate", {"art": "lake_kick"}, moved_by=60, guide=(P6, P7), prologue=False)
    assert outside["scrolls"] == TO_TOP  # 序章外的引導一樣
    assert out["note"] == {"id": "lake_kick", "html": "<p>RESULT</p>"} and out["message"] == "<p>RESULT</p>"  # 結果照舊寫在卡片裡與頁首


def test_a_cultivate_that_finishes_the_guide_scrolls_to_the_top_too():
    """引導在這次修練做完（說書人的框變成沒有）：框上的「✔ 完成」在頁首，也捲上去。"""
    assert press("cultivate", {"art": "lake_kick"}, moved_by=60, guide=(P6, None))["scrolls"] == TO_TOP


def test_a_cultivate_that_leaves_the_guide_on_the_same_step_keeps_the_position():
    out = press("cultivate", {"art": "lake_kick"}, moved_by=60, guide=(P6, dict(P6)), prologue=True)
    assert out["scrolls"] == [["by", {"top": 60, "left": 0, "behavior": "instant"}]]  # 步驟沒變：留在原地，只補高度的差
    none = press("cultivate", {"art": "lake_kick"}, moved_by=0, guide=(None, None))
    assert none["scrolls"] == []  # 沒有引導（或根本沒有說書人）：照 W7，一動也不動


def test_the_guide_step_is_told_apart_by_its_key_and_falls_back_to_the_sentence_without_one():
    same_key = press("cultivate", {"art": "lake_kick"}, guide=({"key": "p6", "text": "甲"}, {"key": "p6", "text": "乙"}))
    assert same_key["scrolls"] == []  # 同一步的話換了（例：眼前有事件時換成「先了結…」）不算換步
    old_server = press("cultivate", {"art": "lake_kick"}, guide=({"text": "甲"}, {"text": "乙"}))
    assert old_server["scrolls"] == TO_TOP  # 舊版伺服器沒有 key：認句子（跟 app.js 的 guideKey 一樣）


def test_a_new_mastery_that_needs_a_name_scrolls_up_to_the_naming_form():
    """練成絕學的那一次：定名的表單在頁首（修練頁最上面），不捲上去玩家看不到——這一次照舊捲到頂。"""
    out = press("cultivate", {"art": "lake_kick"}, reply_menxia=menxia(naming={"id": "lake_kick", "name": "湖邊腿法"}), moved_by=60)
    assert out["scrolls"] == [["to", {"top": 0, "behavior": "smooth"}]]


def test_switching_and_melting_still_scroll_to_the_top_and_clear_the_card_note():
    for op, extra in (("switch", {"art": "lake_kick"}), ("melt", {"art": "lake_kick"}), ("practice", {}), ("heal", {})):
        out = press(op, extra, moved_by=60)
        assert out["scrolls"] == [["to", {"top": 0, "behavior": "smooth"}]], op  # 列表結構變了：照舊回頁首
        assert out["note"] is None, op


# ── W10：開爐等結果的那一句不誇大等多久 ─────────────────────────────────


def test_the_forge_wait_text_does_not_promise_a_minute():
    """取名實際約 3～5 秒（模型關著走字表更快），「要花上一分鐘」會讓人以為壞了。句子待 joy 潤。"""
    wait = run("return H.FORGE_WAIT;", consts=["FORGE_WAIT"], stubs="")
    assert wait == "爐火正旺。若這是江湖上第一次合出來，要等它取名，請稍候。"
    assert "一分鐘" not in webharness.APP.read_text(encoding="utf-8")


# ── W9：熔煉的確認框問什麼，由伺服器寫好、放在按鈕上 ─────────────────────────


def test_the_melt_button_carries_the_servers_confirm_question_escaped():
    rows = [art(), art("lake_kick", "湖邊腿法", worn=False, melt={"ok": True, "note": "沒有心得，只空出一格", "confirm": "把【湖邊腿法】熔掉？這門熔了沒有心得，只空出一格。"})]
    html = page("pagePractice", menxia(owned_arts=rows), artOpen="lake_kick")
    button = re.search(r'<button[^>]*data-act="melt"[^>]*data-id="lake_kick"[^>]*>', html).group(0)
    assert 'data-confirm="把【湖邊腿法】熔掉？這門熔了沒有心得，只空出一格。"' in button
    assert "熔煉（只空出一格）" in html  # 卷軸卡上熔煉是一個小字鈕，退 0 心得照實寫只空出一格
    evil = art("lake_kick", "湖邊腿法", worn=False, melt={"ok": True, "note": "x", "confirm": '"><script>'})
    assert "<script>" not in page("pagePractice", menxia(owned_arts=[evil]), artOpen="lake_kick")


# ── W5：修練頁的武學清單叫「功法庫」 ───────────────────────────────────


def test_the_practice_pages_list_of_arts_is_titled_the_art_library_with_its_count():
    html = page("pagePractice", menxia(holdings={"count": 7, "cap": 56}))
    assert re.search(r'<div class="label">功法庫 <small class="muted">武學與意境 7/56</small></div>', html)
    assert '<div class="label">武學 <small' not in html  # 舊的標題（跟煉製頁的「武學」挑選區同名）不在了
    assert "湖邊腿法" in html.split("功法庫")[1]  # 清單就在這個標題底下


# ── W2：屬性有什麼用，收在一個摺起來的說明裡 ───────────────────────────


def test_the_practice_page_has_a_closed_attribute_fold_right_under_the_rules_line():
    html = page("pagePractice", menxia())
    fold = re.search(r"<details class=\"attr-note\"( open)?><summary>([^<]*)</summary>(.*?)</details>", html, re.S)
    assert fold and fold.group(1) is None  # 收著：第一屏只多一行字
    assert fold.group(2) == "武學屬性有什麼用" and "ATTRNOTE" in fold.group(3)  # FB-089：標題冠上「武學」，別跟升級配點的屬性混
    assert html.index('id="seclude"') < html.index("attr-note") < html.index("身上的兩門")  # 療傷閉關那一排底下、第一張卷軸卡之前


def test_the_craft_page_has_the_same_fold_right_under_the_open_furnace_button():
    html = page("pageCraft", menxia(), tab="craft")
    assert html.count('<details class="attr-note">') == 1 and "ATTRNOTE" in html
    assert html.index("FORGELINE") < html.index('id="forge"') < html.index("attr-note") < html.index("<div class=\"label\">功法")  # 挑東西的標題併了篩選鈕（arts-polish-2 FB-085），摺疊還是在它前面


def test_the_attribute_note_is_escaped_and_a_missing_one_draws_nothing():
    html = page("pagePractice", menxia(attribute_note="<b>x</b>"))
    assert "<b>x</b>" not in html and "&lt;b&gt;x&lt;/b&gt;" in html
    assert "attr-note" not in page("pagePractice", menxia(attribute_note=""))  # 伺服器沒給（舊版）：不畫空的摺疊
