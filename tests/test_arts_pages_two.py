"""修練頁與煉製頁的第二批修整（arts-polish-2：QA 實機走一遍的 FB-081～085）。
一節一個 FB：引擎與伺服器的部分直接跑；web/app.js 沒有建置步驟、也沒有前端測試框架，網頁的部分把函式從原始碼切出來
交給 node 跑（不相干的畫法換成一行的假貨），沒有 node 就略過那幾個。"""
from __future__ import annotations

import json
import random
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tianxia import fusion, library, skillview
from tianxia.content import load_content
from tianxia.engine import Game
from tianxia.martial_arts import generate_from_name

ROOT = Path(__file__).parent.parent
CONTENT_DIR = ROOT / "content"
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="沒有 node，前端畫面測試略過")

DRIVER = r"""
const fs = require("fs");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const src = fs.readFileSync(input.app, "utf8").replace(/\r\n/g, "\n"); // Windows 的 checkout 是 CRLF
// IIFE 裡兩格縮排的函式：從標頭到下一個兩格縮排的收尾（含 async）；一行寫完的 const 照名字抓
const fn = (name) => {
  let a = src.indexOf(`\n  function ${name}(`);
  if (a < 0) a = src.indexOf(`\n  async function ${name}(`);
  if (a < 0) throw new Error(`app.js 裡找不到 function ${name}`);
  return src.slice(a, src.indexOf("\n  }\n", a) + 4);
};
const konst = (name) => {
  const m = src.match(new RegExp(`^  const ${name} = .*;$`, "m"));
  if (!m) throw new Error(`app.js 裡找不到 const ${name}`);
  return m[0];
};
const calls = [];
const store = {};
globalThis.localStorage = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } };
globalThis.window = { scrollTo: () => {}, scrollBy: () => {}, scrollY: 0 };
globalThis.document = { getElementById: () => null, querySelector: () => null, querySelectorAll: () => [], body: { insertAdjacentHTML: (_, h) => calls.push(["ask-html", h]) } };
const S = { stage: "game", tab: "practice", kind: "武學", artOpen: null, legendTick: {}, forgeSel: [], forgeLine: "", busy: false,
  message: "", person: null, main: { status: { injury: 0 } }, ...input.S };
const parts = [
  ...["KINDS", "QUALITY_RANK", "esc", "pro", "attrNoteHtml"].map((n) => { try { return konst(n); } catch (e) { return ""; } }),
  ...input.consts.map(konst),
  ...input.fns.map(fn),
  input.stubs || "",
  "return { " + [...input.fns, ...input.consts].join(", ") + " };",
];
const H = new Function("S", "calls", parts.join("\n"))(S, calls);
H.S = S; H.calls = calls; H.store = store;
(async () => {
  const out = await new Function("H", "S", `return (async () => { ${input.script} })();`)(H, S);
  process.stdout.write(JSON.stringify(out === undefined ? null : out));
})().catch((e) => { process.stderr.write(String(e.stack || e)); process.exit(1); });
"""


def run(script: str, *, S=None, consts=(), fns=(), stubs=""):
    done = subprocess.run(
        [NODE, "-e", DRIVER],
        input=json.dumps({
            "app": str(ROOT / "web" / "app.js"), "script": script, "S": S or {}, "consts": list(consts), "fns": list(fns),
            "stubs": stubs,
        }),
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@pytest.fixture(scope="module")
def real():
    c = load_content(CONTENT_DIR)
    c.config.auto_open_first_season = True
    return c


def _real_game(real, name="驗武人"):
    game = Game.new(real, name, rng=random.Random(1))
    game.world.open_season(real, now=0.0)
    return game


def _melted_starter(game, art_id="jichu_quanjiao", worn="lishi_chui"):
    """玩家真的會走的路：身上換上另一門（這裡借內容裡的名將武學，等於合成出來再改練），開局那門被換進功法庫，再熔掉。"""
    game.state.player.arts = [worn]
    game.switch_art(worn)
    assert art_id in game.state.player.arts
    game.melt_art(art_id)
    return game


# ── FB-081：基礎武學熔了拿不拿得回來 ────────────────────────────


def test_a_melted_starter_art_is_offered_again_in_every_town_and_learning_it_puts_it_in_the_library(real):
    """QA 說熔了開局那門「這一季就拿不回來」：實際上每個城鎮都免費教（library._taught_here），選單上寫「學基礎拳腳（…）」。"""
    game = _real_game(real)
    _melted_starter(game)
    p, towns = game.state.player, [loc for loc in real.locations.values() if library.TOWN_TAG in loc.tags]
    assert len(towns) == 10 and "yingchuan" in {t.id for t in towns}
    assert "jichu_quanjiao" not in library.owned_arts(game.state)
    for town in towns:
        p.location = town.id
        option = next(o for o in game.options() if o.id == "learn:jichu_quanjiao")
        assert option.enabled and option.label.startswith("學基礎拳腳（") and option.label.endswith("免費）"), town.id
    p.location = "yingshui"  # 不是城鎮、也沒有人在這裡教它
    assert "learn:jichu_quanjiao" not in {o.id for o in game.options()}
    p.location, silver, stamina = "yingchuan", p.stats["silver"], p.stamina
    game.choose("learn:jichu_quanjiao")
    assert "jichu_quanjiao" in p.arts and p.member.wugong_id == "lishi_chui"  # 身上那門的位子有人，進功法庫
    assert (p.stats["silver"], p.stamina) == (silver, stamina)  # 不收錢、不花體力
    assert "learn:jichu_quanjiao" not in {o.id for o in game.options()}


def test_the_lesson_lands_in_the_collapsed_here_fold_not_in_the_action_bar():
    """網頁怎麼擺：行動列只認探索、遊歷、打坐、交友、移動；「學…」不在裡面，掉進「此地還能做 N 件事」摺疊。
    （QA 沒找到它的原因之一：摺疊預設是收著的。）"""
    src = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    cells = re.search(r"const ACT_CELLS = \[(.*?)\n  \];", src, re.S).group(1)
    assert "learn:" not in cells
    assert "此地還能做 ${extras.length} 件事" in src and "const extras = m.options.filter((o) => !used.has(o.id))" in src


def test_the_melt_row_and_result_say_where_a_starter_art_can_be_learned_again(content, world, state):
    content.config.starter_skills = ["basic_breath", "basic_fist"]
    state.player.member.wugong_id = "fist"
    state.player.arts = ["basic_fist"]
    (row,) = [r for r in skillview.art_rows(state, content, world) if r["id"] == "basic_fist"]
    assert state.player.location == "town"  # 站在城鎮裡
    assert row["relearn"] == "熔了還能免費重學：這裡就是城鎮，到江湖頁「此地還能做」找「學粗淺拳腳」。"
    state.player.location = "lake"  # 離開城鎮：寫離你最近的那一座
    (row,) = [r for r in skillview.art_rows(state, content, world) if r["id"] == "basic_fist"]
    assert row["relearn"] == "熔了還能免費重學：到任何城鎮（離你最近的是小鎮），在江湖頁「此地還能做」找「學粗淺拳腳」。"
    worn = [r for r in skillview.art_rows(state, content, world) if r["worn"]]
    assert all(r["relearn"] is None for r in worn)  # 身上正在練的不能熔，不寫


def test_an_art_taught_for_a_fee_names_the_place_and_the_fee(content, world, state):
    state.player.arts = ["lake_kick"]
    (row,) = skillview.art_rows(state, content, world)
    assert row["relearn"] == "熔了想拿回來，到湖邊再學一次（學費 10 兩），在江湖頁「此地還能做」找「學湖邊腿法」。"


def test_an_art_you_forged_or_were_given_has_no_relearn_note(content, world, state):
    art = generate_from_name("旋風腿", "武學", "旋風腿", weights={"下品": 100.0, "中品": 0.0, "上品": 0.0, "絕學": 0.0})
    assert world.claim_skill_name(art)
    state.player.arts = ["旋風腿", "fist"]  # 合成出來的、內容直接給的絕學（沒有學得到的地方）
    assert [r["relearn"] for r in skillview.art_rows(state, content, world)] == [None, None]


def test_melting_a_starter_art_ends_the_result_with_where_to_learn_it_again(real):
    game = _real_game(real)
    game.state.player.arts = ["lishi_chui"]
    game.switch_art("lishi_chui")
    msgs = game.melt_art("jichu_quanjiao")
    assert msgs[:2] == ["你把【基礎拳腳】熔成了心得。", "心得 +0"]
    assert msgs[2] == "熔了還能免費重學：這裡就是城鎮，到江湖頁「此地還能做」找「學基礎拳腳」。"
    assert game.state.journal[0].tag == msgs[0]  # 江湖紀錄的標題照舊是第一句
    refused = game.melt_art("jichu_quanjiao")  # 已經熔掉了：只回一句拒絕，不接那句
    assert refused == ["你的功法庫裡沒有這一門。"]


# ── FB-082：意境＋意境的預覽要跟另外兩種一樣；療傷鈕寫價錢 ──────────────


def _named(name):
    from unittest import mock

    from tianxia import naming

    client = mock.Mock()
    client.chat_structured.return_value = naming.NameReply(name=name, description="一句話說明。")
    return client


def _merger(content, name, ids):
    from tianxia.state import new_game_state

    state = new_game_state(content, name)
    state.player.insights = list(dict.fromkeys(ids))
    state.player.stats["xinde"] = 100
    return state


def test_the_merge_preview_names_the_attribute_the_merge_really_gives(content, world):
    """六個基本意境兩兩合併（含自己合自己）：預覽寫的屬性跟 fusion.merge 真的給的一樣——同一個函式算的，不是另寫一份。"""
    import itertools

    ids = list(content.insights)
    for n, (a, b) in enumerate(itertools.combinations_with_replacement(ids, 2)):
        state = _merger(content, f"甲{n}", [a, b])
        line = skillview.forge_line(state, content, world, None, [a, b])
        shown = re.search(r"→ 一個新的意境（屬(.)），", line)
        assert shown, line
        made, _ = fusion.merge(state, content, world, _named(f"新意境{n}"), a, b)
        assert made is not None and made.attribute == shown.group(1), (a, b, line)


def test_the_merge_preview_says_nobody_has_merged_it_before_or_what_it_becomes(content, world):
    first = _merger(content, "甲", ["feng", "huo"])
    assert skillview.forge_line(first, content, world, None, ["feng", "huo"]).endswith("\n沒人合過。")
    made, _ = fusion.merge(first, content, world, _named("燎原"), "feng", "huo")
    again = skillview.forge_line(first, content, world, None, ["feng", "huo"])
    assert "沒人合過" not in again and "會合出" not in again  # 你自己已經悟得了：下面的 ⚠ 本來就說「你已經悟得了」
    assert "⚠ 這兩個合起來還是「燎原」" in again
    other = _merger(content, "乙", ["feng", "huo"])
    line = skillview.forge_line(other, content, world, None, ["huo", "feng"])  # 別人首創、你還沒有的：照樣能合，預覽寫它會是什麼
    assert f"\n會合出「燎原」（屬{made.attribute}）。" in line and "沒人合過" not in line


def test_the_merge_preview_matches_the_other_two_kinds_in_shape(content, world, state):
    state.player.member.wugong_id = "basic_fist"
    state.player.arts = ["lake_kick"]
    state.player.insights = ["feng", "huo"]
    state.player.stats["xinde"] = 100
    fuse = skillview.forge_line(state, content, world, "basic_fist", ["feng"])
    blend = skillview.forge_line(state, content, world, "basic_fist", [], other_art="lake_kick")
    merge = skillview.forge_line(state, content, world, None, ["feng", "huo"])
    for line in (fuse, blend, merge):
        assert re.search(r"（屬.[，）]", line) and line.endswith("\n沒人合過。"), line  # 屬性、花費、沒人合過，三種都有


def test_the_merge_preview_still_refuses_what_you_do_not_hold(content, world, state):
    state.player.insights = ["feng"]
    line = skillview.forge_line(state, content, world, None, ["feng", "shui"])
    assert line.startswith("⚠") and "屬" not in line and "→" not in line


def test_heal_button_shows_the_price_and_matches_what_healing_really_charges(content, state):
    from tianxia import team

    member, p = state.player.member, state.player
    assert skillview.heal_button(state, content) == {
        "label": "療傷（沒有內傷）", "ok": False, "why": "氣血無恙，不用療傷。",
    }
    member.injury, p.stats["silver"] = 35.0, 100
    assert skillview.heal_button(state, content) == {"label": "療傷（銀兩 18）", "ok": True, "why": None}  # 每 2 點內傷 1 兩，進位
    team.heal(state, content, member)
    assert p.stats["silver"] == 100 - 18 and member.injury == 0  # 按鈕寫的價錢就是真的收的價錢


def test_heal_button_is_greyed_out_with_the_reason_when_the_silver_is_short(content, state):
    state.player.member.injury, state.player.stats["silver"] = 35.0, 5
    assert skillview.heal_button(state, content) == {"label": "療傷（要 18 兩）", "ok": False, "why": "銀兩不足：療傷需要 18 兩。"}
    from tianxia import team

    assert team.heal(state, content, state.player.member) == ["銀兩不足：療傷需要 18 兩。"]  # 按下去（舊版畫面）回的是同一句


def test_heal_button_does_not_offer_to_heal_a_wound_the_status_bar_does_not_show(content, state):
    """狀態列的內傷是 int()：不到 1 點不寫；按鈕也不亮（以前就是這樣，改成伺服器給的之後不能變）。"""
    state.player.member.injury, state.player.stats["silver"] = 0.6, 100
    assert not skillview.heal_button(state, content)["ok"]


def test_the_menxia_view_carries_the_heal_button(real):
    import server

    game = _real_game(real)
    assert server.menxia_view(game)["heal"]["label"] == "療傷（沒有內傷）"
    game.state.player.member.injury, game.state.player.stats["silver"] = 20.0, 50
    assert server.menxia_view(game)["heal"] == {"label": "療傷（銀兩 10）", "ok": True, "why": None}
    game.state.player.stats["silver"] = 4
    view = server.menxia_view(game)["heal"]
    assert view["label"] == "療傷（要 10 兩）" and not view["ok"] and "銀兩不足" in view["why"]
    game.heal()  # 錢不夠：不收、不寫紀錄，內傷還在
    assert game.state.player.member.injury == 20.0 and game.state.player.stats["silver"] == 4


PRACTICE_STUBS = 'const guideHtml = () => "", proGuide = () => "", attrNoteHtml = () => "";'


def _menxia(**over):
    base = {
        "slot_cards": [{"kind": k, "card": f"<p>{k}卡</p>", "learned": True, "level": 1, "maxed": False, "blocked": None, "price": 1} for k in ("武學", "內功")],
        "owned_arts": [], "insights": [], "roster": [{"label": "本人", "key": "player"}], "person": None, "person_card": None,
        "on_team": False, "rules": "<p>規則。</p>", "holdings": {"count": 0, "cap": 50}, "player_card": "<p>本人</p>", "naming": None,
        "heal": {"label": "療傷（銀兩 18）", "ok": True, "why": None},
    }
    return {**base, **over}


@needs_node
def test_the_heal_button_draws_what_the_server_says_in_one_short_line():
    out = run(
        "return [H.healButton({label:'療傷（銀兩 18）',ok:true,why:null}, true), H.healButton({label:'療傷（要 18 兩）',ok:false,why:'銀兩不足：療傷需要 18 兩。'}, true),"
        " H.healButton({label:'療傷（沒有內傷）',ok:false,why:'氣血無恙，不用療傷。'}, false), H.healButton(undefined, true), H.healButton(undefined, false)];",
        fns=["healButton"],
    )
    assert out[0] == '<button class="btn" data-act="mx" data-op="heal" >療傷（銀兩 18）</button>'
    assert out[1].startswith('<button class="btn" data-act="mx" data-op="heal" disabled title="銀兩不足：療傷需要 18 兩。"') and ">療傷（要 18 兩）<" in out[1]
    assert "disabled" in out[2] and ">療傷（沒有內傷）<" in out[2]
    assert out[3] == '<button class="btn" data-act="mx" data-op="heal" >療傷</button>' and "disabled" in out[4]  # 舊版伺服器沒給：照舊


@needs_node
def test_the_practice_page_puts_the_heal_price_on_the_button_next_to_the_practice_button():
    html = run(
        "return H.pagePractice();", S={"menxia": _menxia(), "main": {"status": {"injury": 35}}},
        fns=["pagePractice", "healButton"], stubs=PRACTICE_STUBS,
    )
    row = re.search(r'<div class="row practice-actions">(.*?)</div>', html, re.S).group(1)
    assert row.count("<button") == 2 and "療傷（銀兩 18）" in row and "練成武學（心得 1）" in row


@needs_node
def test_the_melt_question_names_where_a_starter_art_can_be_learned_again():
    out = run(
        "return [H.meltAskText('基礎拳腳', '熔了還能免費重學：到任何城鎮，在江湖頁「此地還能做」找「學基礎拳腳」。'), H.meltAskText('旋風腿', null)];",
        consts=["meltAskText"],
    )
    assert out[0] == "把【基礎拳腳】熔成心得？熔了還能免費重學：到任何城鎮，在江湖頁「此地還能做」找「學基礎拳腳」。"
    assert out[1] == "把【旋風腿】熔成心得？熔掉就沒了。"
