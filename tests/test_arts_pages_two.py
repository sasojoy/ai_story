"""修練頁與煉製頁的第二批修整（arts-polish-2：QA 實機走一遍的 FB-081～085）。
一節一個 FB：引擎與伺服器的部分直接跑；web/app.js 沒有建置步驟、也沒有前端測試框架，網頁的部分把函式從原始碼切出來
交給 node 跑（不相干的畫法換成一行的假貨；node 由 tests/webharness.py 跑），沒有 node 就略過那幾個。"""
from __future__ import annotations

import json
import random
import re
from pathlib import Path

import pytest

import webharness
from tianxia import fusion, journal, library, skillview
from tianxia.content import load_content
from tianxia.engine import Game
from tianxia.martial_arts import generate_from_name

ROOT = Path(__file__).parent.parent
CONTENT_DIR = ROOT / "content"
needs_node = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")

DRIVER = r"""
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
  // 卷軸卡的零件（品質印、十成格、療傷鈕、庫的篩選……）：「// ── 修練 ──」到 pagePractice 之間整段照抄（跟 test_arts_pages.py 同一個切法）
  src.slice(src.indexOf("\n  // ── 修練 ──"), src.indexOf("\n  function pagePractice(")),
  ...input.fns.map(fn),
  input.stubs || "",
  "return { " + [...input.fns, ...input.consts, "libFilter", "setLibFilter", "healButton"].join(", ") + " };",  // 後三個在上面那一段裡
];
const H = new Function("S", "calls", parts.join("\n"))(S, calls);
H.S = S; H.calls = calls; H.store = store;
finish(new Function("H", "S", `return (async () => { ${input.script} })();`)(H, S));
"""


def run(script: str, *, S=None, consts=(), fns=(), stubs=""):
    return webharness.run(DRIVER, {"script": script, "S": S or {}, "consts": list(consts), "fns": list(fns), "stubs": stubs})


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


def test_the_melt_question_is_one_sentence_built_on_the_server_for_the_three_kinds_of_art(content, world, state):
    """熔煉的確認框（W9＋FB-081 合成一句，controller 裁決）：退 0 心得的直說只空出一格、沒有括號；開局送的基礎武學再接去哪裡重學，
    「免費重學」只說一次；有心得的寫退多少。"""
    content.config.starter_skills = ["basic_breath", "basic_fist"]
    state.player.member.wugong_id = "lake_kick"  # 欄位有人佔著，下面幾門才在功法庫裡
    _library(world, state, [("旋風腿", "下品", 5, "武學")])
    state.player.arts += ["basic_fist", "fist"]
    state.player.art_levels.update({"basic_fist": 1, "fist": 1})
    rows = {r["id"]: r for r in skillview.art_rows(state, content, world)}
    starter = rows["basic_fist"]["melt"]["confirm"]  # 零心得的基礎武學
    assert starter == (
        "把【粗淺拳腳】熔掉？這門熔了沒有心得，只空出一格。熔了還能免費重學：這裡就是城鎮，到江湖頁「此地還能做」找「學粗淺拳腳」。"
    )
    assert starter.count("免費重學") == 1 and "（" not in starter  # 只說一次、沒有括號
    assert rows["fist"]["melt"]["confirm"] == "把【長拳】熔掉？這門熔了沒有心得，只空出一格。"  # 零心得、沒有重學的地方（內容給的絕學）
    valued = rows["旋風腿"]["melt"]
    assert valued["note"] == "退回心得 8" and valued["confirm"] == "把【旋風腿】熔成心得？退回心得 8。熔掉就沒了。"  # 有心得：寫退多少
    assert rows["lake_kick"]["melt"]["confirm"] == ""  # 身上正在練的不能熔：沒有問句


def test_a_zero_value_art_taught_for_a_fee_names_the_fee_in_the_same_sentence(content, world, state):
    state.player.member.wugong_id = "basic_fist"
    state.player.arts = ["lake_kick"]  # 第一成：退 0；各地教、要學費
    (row,) = [r for r in skillview.art_rows(state, content, world) if r["id"] == "lake_kick"]
    assert row["melt"]["confirm"] == (
        "把【湖邊腿法】熔掉？這門熔了沒有心得，只空出一格。熔了想拿回來，到湖邊再學一次（學費 10 兩），在江湖頁「此地還能做」找「學湖邊腿法」。"
    )


def test_melting_a_starter_art_ends_the_result_with_where_to_learn_it_again(real):
    game = _real_game(real)
    game.state.player.arts = ["lishi_chui"]
    game.switch_art("lishi_chui")
    msgs = game.melt_art("jichu_quanjiao")
    assert msgs == [  # W9：退 0 心得的熔煉直說只空出一格（單獨一句，沒有「心得 +0」）；FB-081 的指路接在最後
        "你把【基礎拳腳】熔掉了，空出一格。",
        "熔了還能免費重學：這裡就是城鎮，到江湖頁「此地還能做」找「學基礎拳腳」。",
    ]
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
    # 卷軸卡的療傷鈕自己寫字（內傷與 heal_cost）；伺服器只說按不按得下去與原因，不再送 label（review-ap3 M4：沒有人讀它）
    assert skillview.heal_button(state, content) == {"ok": False, "why": "氣血無恙，不用療傷。"}
    member.injury, p.stats["silver"] = 35.0, 100
    assert skillview.heal_button(state, content) == {"ok": True, "why": None}
    assert team.heal_cost(content, member) == 18  # 每 2 點內傷 1 兩，進位：頁面上寫的價錢是 server 的 heal_cost
    team.heal(state, content, member)
    assert p.stats["silver"] == 100 - 18 and member.injury == 0  # 寫的價錢就是真的收的價錢


def test_heal_button_is_greyed_out_with_the_reason_when_the_silver_is_short(content, state):
    state.player.member.injury, state.player.stats["silver"] = 35.0, 5
    assert skillview.heal_button(state, content) == {"ok": False, "why": "銀兩不足：療傷需要 18 兩。"}
    from tianxia import team

    assert team.heal(state, content, state.player.member) == ["銀兩不足：療傷需要 18 兩。"]  # 按下去（舊版畫面）回的是同一句


def test_heal_button_does_not_offer_to_heal_a_wound_the_status_bar_does_not_show(content, state):
    """狀態列的內傷是 int()：不到 1 點不寫；按鈕也不亮（以前就是這樣，改成伺服器給的之後不能變）。"""
    state.player.member.injury, state.player.stats["silver"] = 0.6, 100
    assert not skillview.heal_button(state, content)["ok"]


def test_the_menxia_view_carries_the_heal_button(real):
    import server

    game = _real_game(real)
    assert server.menxia_view(game)["heal"] == {"ok": False, "why": "氣血無恙，不用療傷。"} and server.menxia_view(game)["heal_cost"] == 0
    game.state.player.member.injury, game.state.player.stats["silver"] = 20.0, 50
    assert server.menxia_view(game)["heal"] == {"ok": True, "why": None} and server.menxia_view(game)["heal_cost"] == 10
    game.state.player.stats["silver"] = 4
    view = server.menxia_view(game)["heal"]
    assert not view["ok"] and "銀兩不足" in view["why"] and "label" not in view
    game.heal()  # 錢不夠：不收、不寫紀錄，內傷還在
    assert game.state.player.member.injury == 20.0 and game.state.player.stats["silver"] == 4


# ── FB-083：絕學被定名，手上有那一門的人下次同步補一則紀錄 ─────────────────


def _two_players(content, world, names=("甲", "乙")):
    """同一個全服狀態上的幾個玩家（每個人各自一個 Game，跟伺服器裡一人一份一樣）。"""
    from tianxia.engine import Game

    return [Game.new(content, name, world=world) for name in names]


def _registered_art(world, name, kind="武學"):
    art = generate_from_name(name, kind, name, weights={"下品": 100.0, "中品": 0.0, "上品": 0.0, "絕學": 0.0}).model_copy(
        update={"origin": "fused", "creator": "甲", "creator_shown": "甲"},
    )
    assert world.claim_skill_name(art)
    return art


def _name_it(master, art, new_name, shown=None):
    """甲是第一個練成絕學的人、替它定名：走真的 Game.name_mastered。"""
    assert master.world.claim_master(art.id, master.state.player.name, shown)
    master.state.player.arts = [art.id]
    master.state.player.naming = art.id
    return master.name_mastered(new_name)


def _notices(game):
    return [e for e in game.state.journal if e.title == journal.RENAMED]


def test_a_holder_is_told_once_on_the_next_sync_who_named_it_and_what_it_is_called_now(content, world):
    master, holder, stranger = _two_players(content, world, ("甲", "乙", "丙"))
    art = _registered_art(world, "疾風重拳")
    library.store_art(holder.state, art)  # 乙手上有它（功法庫）
    msgs = _name_it(master, art, "追風破陣拳")
    assert msgs == ["從今以後，江湖上這門武學就叫【追風破陣拳】。"]
    holder.sync(1000.0)
    (entry,) = _notices(holder)
    assert entry.tag == "你手上的【疾風重拳】已由甲定名為【追風破陣拳】。"
    holder.sync(1010.0)
    holder.sync(5000.0)
    assert len(_notices(holder)) == 1  # 一個人一次改名只通知一次
    stranger.sync(1000.0)
    assert _notices(stranger) == []  # 手上沒有那一門的人不吵


def test_the_namer_is_not_told_about_his_own_naming(content, world):
    master, _ = _two_players(content, world)
    art = _registered_art(world, "疾風重拳")
    _name_it(master, art, "追風破陣拳")
    master.sync(1000.0)
    assert _notices(master) == []


def test_keeping_the_old_name_is_not_a_rename_and_tells_nobody(content, world):
    master, holder = _two_players(content, world)
    art = _registered_art(world, "疾風重拳")
    library.store_art(holder.state, art)
    _name_it(master, art, "疾風重拳")  # 沿用原名也算定名，名字沒變
    holder.sync(1000.0)
    assert _notices(holder) == []


def test_someone_who_got_the_art_after_it_was_named_already_saw_the_new_name_and_is_not_told(content, world):
    master, late = _two_players(content, world)
    art = _registered_art(world, "疾風重拳")
    _name_it(master, art, "追風破陣拳")
    renamed = world.get_skill(art.id)
    assert renamed.name == "追風破陣拳" and renamed.id == "疾風重拳"
    library.store_art(late.state, renamed)  # 晚來的拿到的就是新名
    late.sync(1000.0)
    assert _notices(late) == []


def test_a_forge_that_lands_on_a_named_art_does_not_tell_the_forger_either(content, world):
    """真的走合成：甲先合出來、定名；乙後來合同一組，從配方表拿到的已經是定過名的那門。"""
    from tianxia import fusion
    from tianxia.state import new_game_state

    master, late = _two_players(content, world)
    for game in (master, late):
        game.state.player.insights = ["feng"]
        game.state.player.stats["xinde"] = 50
        game.state.player.member.wugong_id = "basic_fist"
    made, _ = fusion.fuse(master.state, content, world, _named("旋風腿"), "basic_fist", "feng")
    assert made.id == "旋風腿"
    _name_it(master, made, "旋風不歸腿")
    got, _ = fusion.fuse(late.state, content, world, _named("不會用到"), "basic_fist", "feng")
    assert got.id == "旋風腿" and "旋風腿" in late.state.player.arts
    late.sync(1000.0)
    assert _notices(late) == [] and new_game_state is not None


def test_two_namings_between_syncs_are_one_entry_with_a_line_each(content, world):
    first, second, holder = _two_players(content, world, ("甲", "乙", "丙"))
    a, b = _registered_art(world, "疾風重拳"), _registered_art(world, "沉雷掌")
    library.store_art(holder.state, a)
    library.store_art(holder.state, b)
    _name_it(first, a, "追風破陣拳")
    _name_it(second, b, "震嶽轟雷掌")
    holder.sync(1000.0)
    (entry,) = _notices(holder)
    assert entry.tag == "共 2 則" and entry.lines == [
        "你手上的【疾風重拳】已由甲定名為【追風破陣拳】。", "你手上的【沉雷掌】已由乙定名為【震嶽轟雷掌】。",
    ]


def test_the_namer_is_written_the_way_it_was_recorded(content, world):
    """登記時記下的 master_shown 怎麼寫就怎麼寫（匿名行走的人是「某位少俠」），不另外去查名號。"""
    master, holder = _two_players(content, world)
    art = _registered_art(world, "疾風重拳")
    library.store_art(holder.state, art)
    _name_it(master, art, "追風破陣拳", shown="某位少俠")
    holder.sync(1000.0)
    assert _notices(holder)[0].tag == "你手上的【疾風重拳】已由某位少俠定名為【追風破陣拳】。"


def test_a_worn_art_counts_as_held_and_a_melted_one_does_not(content, world):
    master, worn, melted = _two_players(content, world, ("甲", "乙", "丙"))
    art = _registered_art(world, "疾風重拳")
    worn.state.player.member.wugong_id = art.id
    melted.state.player.member.wugong_id = "basic_fist"  # 欄位有人佔著，新的才會進功法庫
    library.store_art(melted.state, art)
    assert library.melt_art(melted.state, content, world, art.id)[0].startswith("你把【疾風重拳】熔成了心得")
    _name_it(master, art, "追風破陣拳")
    worn.sync(1000.0)
    melted.sync(1000.0)
    assert len(_notices(worn)) == 1 and _notices(melted) == []


def test_the_record_is_a_player_field_and_needs_no_schema_change(content):
    from tianxia import database
    from tianxia.state import PlayerState, new_game_state

    assert database.SCHEMA_VERSION == 3  # 悟意境（PR #23）升到 3；renames_told 自己是 PlayerState 的欄位，沒有升版
    data = new_game_state(content, "舊檔").player.model_dump()
    assert data.pop("renames_told") == []
    assert PlayerState.model_validate(data).renames_told == []  # 沒有這個欄位的舊存檔照樣讀得進來


def test_a_sync_with_nothing_renamed_does_not_look_arts_up_one_by_one(content, world):
    """同步每 10 秒一次、每個玩家都有：改過名的 id 一次查完，沒有就一門武學都不必另外去查。"""
    from unittest import mock

    _, holder = _two_players(content, world)
    for name in ("疾風重拳", "沉雷掌", "斷水刀"):
        library.store_art(holder.state, _registered_art(world, name))
    assert world.renamed_skill_ids() == set()
    with mock.patch.object(type(world), "get_skill", side_effect=AssertionError("不該一門一門查")):
        holder.sync(1000.0)
    assert holder.state.player.renames_told == []  # 沒改過名的不記：之後被改了名還是通知得到


def test_a_new_season_starts_with_an_empty_record(content, world):
    master, holder = _two_players(content, world)
    art = _registered_art(world, "疾風重拳")
    library.store_art(holder.state, art)
    _name_it(master, art, "追風破陣拳")
    holder.sync(1000.0)
    assert holder.state.player.renames_told == ["疾風重拳"]
    holder._reset_player_for_new_season(2)  # 武學跟著季走，通知的記錄也跟著新角色重來
    assert holder.state.player.renames_told == []


# ── FB-085：功法庫多了要找得到——排序、篩選、不用瀏覽器的 confirm() ───────────


def _library(world, state, specs):
    """specs：[(id, 品質, 第幾成, 種類)]；全服登記的合成武學（名字就是 id），玩家自己那份的品質與成另外記。"""
    ids = []
    for art_id, quality, level, kind in specs:
        art = generate_from_name(art_id, kind, art_id, weights={"下品": 100.0, "中品": 0.0, "上品": 0.0, "絕學": 0.0}).model_copy(
            update={"origin": "fused"},
        )
        assert world.claim_skill_name(art)
        state.player.art_quality[art.id] = quality
        state.player.art_levels[art.id] = level
        ids.append(art.id)
    state.player.arts = ids


def test_the_library_is_sorted_worn_first_then_quality_then_level_then_name(content, world, state):
    state.player.member.neigong_id, state.player.member.neigong_level = "basic_breath", 3
    state.player.member.wugong_id, state.player.member.wugong_level = "basic_fist", 3
    _library(world, state, [
        ("丙丙拳", "下品", 9, "武學"), ("乙乙拳", "上品", 2, "武學"), ("甲甲拳", "中品", 5, "武學"), ("丁丁功", "絕學", 1, "內功"),
        ("戊戊拳", "中品", 7, "武學"), ("己己拳", "中品", 7, "武學"), ("庚庚拳", "下品", 9, "武學"),
    ])
    rows = skillview.art_rows(state, content, world)
    assert [r["worn"] for r in rows] == [True, True] + [False] * 7  # 身上的先
    rest = [(r["name"], r["quality"], r["level"]) for r in rows if not r["worn"]]  # 品質是玩家自己那一份（art_quality）
    assert rest == [
        ("丁丁功", "絕學", 1), ("乙乙拳", "上品", 2),  # 絕學 > 上品
        ("己己拳", "中品", 7), ("戊戊拳", "中品", 7), ("甲甲拳", "中品", 5),  # 同品質：成多的先，再比名字（照字碼：己 U+5DF1 < 戊 U+620A）
        ("丙丙拳", "下品", 9), ("庚庚拳", "下品", 9),
    ]


def test_the_worn_arts_follow_the_same_order_among_themselves(content, world, state):
    state.player.member.neigong_id, state.player.member.neigong_level = "basic_breath", 2
    state.player.member.wugong_id, state.player.member.wugong_level = "basic_fist", 5
    state.player.art_quality["basic_breath"] = "中品"
    rows = skillview.art_rows(state, content, world)
    assert [r["id"] for r in rows] == ["basic_breath", "basic_fist"]  # 中品的內功排在下品的武學前面


def test_the_same_order_reaches_the_page_data(real):
    import server

    game = _real_game(real)
    game.state.player.arts = ["lishi_chui", "zhuifeng", "taiping_gun"]
    game.state.player.art_levels.update({"lishi_chui": 2, "zhuifeng": 6, "taiping_gun": 4})
    page = [r["id"] for r in server.menxia_view(game)["owned_arts"]]
    assert page == [r["id"] for r in skillview.art_rows(game.state, game.content, game.world)]  # 兩頁畫的是同一份順序
    assert page[:2] == ["jichu_tuna", "jichu_quanjiao"] and len(page) == 5  # 身上兩門同品質同成，照名字（吐 < 拳）


PRACTICE_STUBS = 'const guideHtml = () => "", proGuide = () => "";'
CRAFT_STUBS = PRACTICE_STUBS + 'const furnaceSvg = () => "<svg></svg>", toast = () => {};'
CRAFT_FNS = ["pageCraft", "forgeBody", "forgeReady", "artFilter", "setArtFilter", "filterChips", "showArts",
             "pickMark", "craftView", "craftFilterRow", "craftChip", "manualHtml"]
CRAFT_CONSTS = ["ART_FILTERS", "filterKey", "CRAFT_SORTS", "CRAFT_PAGE"]


def _menxia(**over):
    base = {
        "slot_cards": [{"kind": k, "card": f"<p>{k}卡</p>", "learned": True, "level": 1, "maxed": False, "blocked": None, "price": 1} for k in ("武學", "內功")],
        "owned_arts": [], "insights": [], "roster": [{"label": "本人", "key": "player"}], "person": None, "person_card": None,
        "on_team": False, "rules": "<p>規則。</p>", "holdings": {"count": 0, "cap": 50}, "player_card": "<p>本人</p>", "naming": None,
        "heal_cost": 18, "heal": {"ok": True, "why": None},
    }
    return {**base, **over}


def _art(art_id, kind, name, quality="下品", level=1, worn=False, **over):
    row = {
        "id": art_id, "kind": kind, "name": name, "quality": quality, "attribute": "快", "level": level, "worn": worn, "insight": None,
        "card": f"<p>{name}卡</p>", "cultivate": {"ok": False, "note": "沒有融過意境", "legend": None},
        "melt": {"ok": not worn, "note": "退回心得 3", "confirm": f"把【{name}】熔成心得？退回心得 3。熔掉就沒了。"}, "relearn": None, "compare": "",
    }
    row.update(over)
    return row


def _insight(insight_id, name):
    return {"id": insight_id, "name": name, "attribute": "快", "lean": "無", "note": "", "melt": 10}


def _library_of_ten():
    """身上兩門（武學甲拳、內功乙功）加功法庫十門：六門武學（武0 可修練）、四門內功（內0 可修練）；順序是伺服器排好的。"""
    rows = [_art("w1", "武學", "甲拳", "絕學", 4, worn=True), _art("n1", "內功", "乙功", "上品", 3, worn=True)]
    rows += [_art(f"w{i + 2}", "武學", f"武{i}", level=6 - i, cultivate={"ok": i == 0, "note": "10% 晉為上品・體力 10", "legend": None}) for i in range(6)]
    rows += [_art(f"n{i + 2}", "內功", f"內{i}", level=4 - i, cultivate={"ok": i == 0, "note": "10% 晉為上品・體力 10", "legend": None}) for i in range(4)]
    return rows


INSIGHTS = [_insight("feng", "風"), _insight("huo", "火")]


def _practice(rows, script_before="", insights=None, **extra):
    """畫修練頁（卷軸卡）：script_before 是畫之前要在頁面上做的事（例：選篩選）。"""
    return run(
        f"{script_before} return H.pagePractice();",
        S={"menxia": _menxia(owned_arts=rows, insights=INSIGHTS if insights is None else insights, **extra), "main": {"status": {"injury": 0}}},
        fns=["pagePractice"], stubs=PRACTICE_STUBS,
    )


def _craft(filter_for=None, **S):
    return run(
        (f"H.setArtFilter('craft', {json.dumps(filter_for)});" if filter_for else "") + " return H.pageCraft();",
        S={"menxia": _menxia(owned_arts=_library_of_ten(), insights=INSIGHTS), "main": {"status": {"injury": 0}}, **S},
        fns=CRAFT_FNS, consts=CRAFT_CONSTS, stubs=CRAFT_STUBS,
    )


def _library_names(html):
    return re.findall(r'<button class="art libr[^"]*"[^>]*><span class="qseal[^"]*">.</span><span class="txt"><b>(.+?)</b>', html)


def _craft_names(html):
    arts = re.findall(r'data-act="pick" data-type="art"[^>]*>\s*<b>(.+?)</b>', html)
    insights = re.findall(r'data-act="pick" data-type="ins"[^>]*>\s*<b>(.+?)</b>', html)
    return arts, insights


# ── 修練頁（卷軸卡）的功法庫篩選：joy 的四顆（全部／武學／內功／可修練）為底，加上記在這個瀏覽器（FB-085）──


@needs_node
@pytest.mark.parametrize("chosen, expected", [
    (None, ["武0", "武1", "武2", "武3", "武4", "武5", "內0", "內1", "內2", "內3"]),  # 預設全部：伺服器排好的順序，一個不少
    ("武學", ["武0", "武1", "武2", "武3", "武4", "武5"]),
    ("內功", ["內0", "內1", "內2", "內3"]),
    ("ready", ["武0", "內0"]),  # 可修練：修練鈕按得下去的
])
def test_the_library_filter_lists_only_what_it_says_in_the_servers_order(chosen, expected):
    before = f"H.setLibFilter({json.dumps(chosen)});" if chosen else ""
    assert _library_names(_practice(_library_of_ten(), before)) == expected


@needs_node
@pytest.mark.parametrize("stored", ["內功", "ready", "武學"])
def test_a_remembered_filter_is_not_applied_while_its_chips_are_not_drawn(stored):
    """review-ap3 I1：篩選鈕只在庫超過 8 門時才畫。庫縮到 8 門以下（熔掉、改練）之後，記著的篩選若還在套，武學被藏起來又沒有鈕改回來。"""
    short = [_art("w1", "武學", "甲拳", worn=True)] + [_art(f"w{i + 2}", "武學", f"武{i}") for i in range(8)]  # 庫剛好 8 門
    html = _practice(short, f"H.store['tx-arts-filter-practice'] = {json.dumps(stored)};")
    assert 'class="lib-filter"' not in html and len(_library_names(html)) == 8 and "這一類沒有功法" not in html
    long = short + [_art("w10", "武學", "武8")]  # 第 9 門：鈕出現，記著的篩選才套
    html = _practice(long, f"H.store['tx-arts-filter-practice'] = {json.dumps(stored)};")
    assert 'class="lib-filter"' in html and (stored == "武學") == (len(_library_names(html)) == 9)


@needs_node
def test_the_open_card_stays_in_the_list_even_when_it_no_longer_fits_the_filter():
    """W7 的小邊角（review-ap3 M4）：照「可修練」篩選時，最後一次修練讓它不能再修（體力不夠、練成絕學）就不合篩選；展開著的那一門
    留在清單裡，它卡裡的結果才看得到、頁面也不會因為鈕不見了而跳到頂。"""
    rows = _library_of_ten()
    rows[2] = {**rows[2], "cultivate": {"ok": False, "note": "體力不足：修練一次要 10。", "legend": None}}  # 武0 剛被修練到不能再修
    names = _library_names(_practice(rows, "H.setLibFilter('ready'); S.artOpen = 'w2';"))
    assert names == ["武0", "內0"]  # 展開著的武0 還在（照伺服器的順序），其他不能修練的照篩選藏起來
    assert _library_names(_practice(rows, "H.setLibFilter('ready');")) == ["內0"]  # 沒展開的：不合就藏起來


@needs_node
def test_the_open_card_is_listed_even_when_it_sits_past_the_first_page():
    rows = _library_of_ten()
    html = _practice(rows, "S.artOpen = 'n5';")  # 十門的最後一門（第 10 個）：第一頁只列 8 門，十門 = 8 + 2 直接列完
    assert "內3" in _library_names(html)
    twelve = rows + [_art("w20", "武學", "武X"), _art("w21", "武學", "武Y")]  # 十二門：第一頁 8 門，按「再列 N 門」才全
    names = _library_names(_practice(twelve, "S.artOpen = 'w21';"))
    assert len(names) == 9 and names[-1] == "武Y"


@needs_node
def test_a_filter_with_nothing_in_it_says_so_instead_of_leaving_a_hole():
    rows = [_art("w1", "武學", "甲拳", worn=True)] + [_art(f"w{i + 2}", "武學", f"武{i}") for i in range(9)]  # 九門武學、沒有內功
    html = _practice(rows, "H.setLibFilter('內功');")
    assert "這一類沒有功法。" in html and _library_names(html) == []


@needs_node
def test_the_library_chips_show_up_only_when_the_library_is_long_and_count_each_kind():
    html = _practice(_library_of_ten(), "H.setLibFilter('內功');")
    chips = re.findall(r'<button class="(on)?" data-act="lib-filter" data-filter="([^"]+)">(\S+) (\d+)</button>', html)
    assert [(f, label, n) for _, f, label, n in chips] == [("all", "全部", "10"), ("武學", "武學", "6"), ("內功", "內功", "4"), ("ready", "可修練", "2")]
    assert [f for on, f, _, _ in chips if on] == ["內功"]  # 現在選的那一顆亮著
    short = _practice(_library_of_ten()[:7])  # 功法庫不到九門：不畫篩選
    assert "lib-filter" not in short and len(_library_names(short)) == 5


@needs_node
def test_the_library_filter_is_remembered_in_the_browser_and_survives_a_reload():
    out = run(
        "H.setLibFilter('內功'); delete H.S.libFilter; H.S.libFilter = null;"  # 重新整理：記憶體裡的沒了，從 localStorage 讀回來
        "return [H.libFilter(), H.store];",
        S={"menxia": _menxia()},
        fns=["pagePractice"], stubs=PRACTICE_STUBS,
    )
    assert out == ["內功", {"tx-arts-filter-practice": "內功"}]


@needs_node
@pytest.mark.parametrize("stored", ["亂寫的", "意境", "全部"])
def test_a_broken_or_old_stored_value_falls_back_to_all(stored):
    """舊版的記法（全部／內功／武學／意境）裡，現在認不得的（全部、意境）也一律回到全部。"""
    out = run(
        f"H.store['tx-arts-filter-practice'] = {json.dumps(stored)}; H.S.libFilter = null; return H.libFilter();",
        S={"menxia": _menxia()}, fns=["pagePractice"], stubs=PRACTICE_STUBS,
    )
    assert out == "all"


@needs_node
def test_a_browser_without_storage_still_filters_for_this_page_view():
    """localStorage 取不到（私密視窗、封鎖網站資料）會丟例外：讀不到當沒選過、存不了就只在這一頁有效。"""
    out = run(
        "globalThis.localStorage = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); } };"
        "H.S.libFilter = null; const first = H.libFilter(); H.setLibFilter('武學'); return [first, H.libFilter()];",
        S={"menxia": _menxia()}, fns=["pagePractice"], stubs=PRACTICE_STUBS,
    )
    assert out == ["all", "武學"]


@needs_node
def test_a_filter_the_page_does_not_know_is_ignored_and_a_new_filter_restarts_the_listing():
    out = run(
        "H.setLibFilter('武學'); H.S.libAll = true; H.setLibFilter('亂寫'); const kept = [H.libFilter(), H.S.libAll];"
        "H.setLibFilter('內功'); return [kept, H.S.libAll];",
        S={"menxia": _menxia()}, fns=["pagePractice"], stubs=PRACTICE_STUBS,
    )
    assert out == [["武學", True], False]


# ── 煉製頁挑東西那一排的篩選（四顆：全部／內功／武學／意境）──


@needs_node
def test_the_craft_page_filter_narrows_the_arts_but_never_hides_the_insights():
    """煉製頁是拿「一門武學＋一個意境」合成的地方：記著的「內功」「武學」篩選把意境整排藏起來、又沒有任何提示，會讓人以為意境不見了
    （review-ap2 的小毛病）。最簡單的做法是煉製頁的意境清單不理會這個篩選；「意境」那一顆則是只看意境、把武學藏起來。"""
    both = ["風", "火"]
    every = ["甲拳", "乙功", "武0", "武1", "武2", "武3", "武4", "武5", "內0", "內1", "內2", "內3"]
    assert _craft_names(_craft()) == (every, both)
    assert _craft_names(_craft("內功")) == (["乙功", "內0", "內1", "內2", "內3"], both)
    assert _craft_names(_craft("武學")) == (["甲拳", "武0", "武1", "武2", "武3", "武4", "武5"], both)
    assert _craft_names(_craft("意境")) == ([], both)


@needs_node
def test_the_craft_chips_sit_in_one_row_and_mark_the_current_one():
    html = _craft("武學")
    group = re.search(r'<span class="fchips"[^>]*>(.*?)</span>', html, re.S).group(1)
    chips = re.findall(r'<button[^>]*data-filter="([^"]+)"[^>]*aria-pressed="(true|false)"', group)
    assert chips == [("全部", "false"), ("內功", "false"), ("武學", "true"), ("意境", "false")]
    assert html.count('class="fchips"') == 1 and 'data-page="craft"' in group


@needs_node
def test_the_craft_page_filter_sits_in_the_label_row_so_the_first_screen_does_not_grow():
    """煉製頁的第一屏：篩選鈕併進「功法」那一行標籤（跟以前的「武學」標籤同一行），不另外多一行。"""
    html = _craft()
    label = re.search(r'<div class="label[^"]*">(.*?)</div>', html[html.index('id="forge"'):], re.S).group(0)
    assert "fchips" in label and "data-filter" in label


@needs_node
def test_the_craft_choice_is_remembered_in_the_browser_too():
    out = run(
        "H.setArtFilter('craft', '意境'); delete H.S.artFilter; return [H.artFilter('craft'), H.store];",
        fns=CRAFT_FNS, consts=CRAFT_CONSTS, stubs=CRAFT_STUBS,
    )
    assert out == ["意境", {"tx-arts-filter-craft": "意境"}]


def test_the_practice_poll_redraws_when_the_heal_button_changes():
    """療傷鈕能不能按、寫什麼，看內傷與銀兩：輪詢只在 MENXIA_SHOWN 列的欄位變了才重畫，heal 不在裡面的話，
    銀兩夠不夠變了鈕還是舊的（review-ap2 的小毛病）。煉製頁沒畫療傷鈕，不必。"""
    src = (ROOT / "web" / "app.js").read_text(encoding="utf-8").replace("\r\n", "\n")
    shown = {
        page: re.findall(r'"([a-z_]+)"', fields)
        for page, fields in re.findall(r"^\s+(practice|craft): \[(.*?)\],?(?:\s*//.*)?$", src[src.index("const MENXIA_SHOWN"):], re.M)
    }
    assert "heal" in shown["practice"] and "heal_cost" in shown["practice"] and "heal" not in shown["craft"]


# ── 卷軸卡上的療傷鈕：joy 的兩行（內傷與價錢）為底，加上伺服器說的「按不下去」──


def _heal_button(x, injury, **kw):
    html = run(
        f"S.menxia = {json.dumps(x)}; S.main.status.injury = {injury}; return H.pagePractice();",
        S={"main": {"status": {"injury": injury}}}, fns=["pagePractice"], stubs=PRACTICE_STUBS,
    )
    return re.search(r'<button class="btn" data-act="mx" data-op="heal"[^>]*>.*?</button>', html, re.S).group(0)


@needs_node
def test_the_heal_button_says_the_wound_and_the_price_and_is_greyed_out_when_it_cannot_be_pressed():
    ok = _heal_button(_menxia(heal_cost=12), 23)
    assert ">療傷<small>內傷 23・銀 12</small>" in ok and "disabled" not in ok
    none = _heal_button(_menxia(heal_cost=0, heal={"ok": False, "why": "氣血無恙，不用療傷。"}), 0)
    assert ">療傷<small>沒有內傷</small>" in none and "disabled" in none
    poor = _heal_button(_menxia(heal_cost=12, heal={"ok": False, "why": "銀兩不足：療傷需要 12 兩。"}), 23)
    assert "內傷 23・銀 12 不夠" in poor and "disabled" in poor and 'title="銀兩不足：療傷需要 12 兩。"' in poor


@needs_node
def test_an_old_server_without_the_heal_field_still_gets_the_wound_based_button():
    old = _menxia(heal_cost=12)
    del old["heal"]
    assert "disabled" not in _heal_button(old, 23) and "disabled" in _heal_button(old, 0)


# ── 卷軸卡裡 W6、序章指路、閉關與意境的拒絕 ──


@needs_node
def test_w6_the_library_card_writes_the_comparison_above_its_buttons_but_the_worn_card_does_not():
    cmp = "比身上的【甲拳】：威力 +2.0（第一成）、多了〔化勁〕；換上後跟內功同屬，整體 +20%"
    rows = [_art("w1", "武學", "甲拳", worn=True), _art("w2", "武學", "乙拳", compare=cmp)]
    html = _practice(rows, "S.artOpen = 'w2';")
    body = html.split('<div class="art-body')[1]
    assert f'<p class="cmp">{cmp}</p>' in body and body.index('class="cmp"') < body.index('class="acts"')  # 鈕的上面，改練之前看得到
    assert 'class="cmp"' not in html.split('<div class="art-body')[0]  # 身上那張卡（沒有 compare）不寫
    opened = _practice(rows, "S.artOpen = 'w2'; S.artInfo = 'w2';")
    assert 'class="cmp"' not in opened  # 點開詳情時功法卡裡有，這裡不重複


@needs_node
def test_the_glow_lists_the_server_sends_decide_every_hook_on_the_cards():
    """序章的指路（T7 走查 W-A）：卡裡改練、修練、熔煉三顆鈕、收著的那一列，發不發光都看伺服器送的 glow，網頁不猜。
    m2：熔煉鈕上的 data-glow="melt" 在序章裡要在；序章外（沒有 glow 這個鍵）一個都不畫。"""
    rows = [_art("w1", "武學", "甲拳", worn=True, glow=["cultivate"]),
            _art("w2", "武學", "乙拳", glow=["switch", "melt"]), _art("w3", "武學", "丙拳", glow=["cultivate"])]
    html = _practice(rows, "S.artOpen = 'w2';")
    body = html.split('<div class="art-body')[1].split("</div></div>")[0]
    assert re.search(r'<button class="linkish" data-act="melt" data-glow="melt" data-id="w2"', body)  # m2
    assert re.search(r'data-act="switch" data-glow="switch" data-id="w2"', body)
    assert re.search(r'data-act="cultivate" data-id="w2"', body) and 'data-act="cultivate" data-glow' not in body  # 這一門的修練不在名單上
    worn = html.split('<div class="art-body')[0]
    assert re.search(r'data-act="cultivate" data-glow="cultivate" data-id="w1"', worn)  # 身上那張卡讀它自己那一列的 glow
    assert re.search(r'<button class="art libr "[^>]*data-id="w3" data-glow="cultivate">', html)  # 收著的那一列只亮名單上的
    outside = _practice([_art("w1", "武學", "甲拳", worn=True), _art("w2", "武學", "乙拳")], "S.artOpen = 'w2';")
    assert 'data-glow="melt"' not in outside and 'data-glow="switch"' not in outside and 'data-glow="cultivate"' not in outside


@needs_node
def test_a_greyed_melt_says_why_in_the_card_where_a_phone_player_can_read_it():
    """review-ap3 M1：灰掉的熔煉只把原因放在 title（手機不顯示）。原因寫在同一排（.more）的左邊空位，不多佔高度；熔得掉的不寫。"""
    worn_why, hut_why = "身上正在練的不能熔，先改練別的。", "師父沒叫你熔這一門。"
    rows = [
        _art("w1", "武學", "甲拳", worn=True, melt={"ok": False, "note": worn_why, "confirm": ""}),
        _art("w2", "武學", "乙拳", melt={"ok": False, "note": hut_why, "confirm": ""}),
        _art("w3", "武學", "丙拳"),
    ]
    html = _practice(rows, "S.artOpen = 'w2';")
    worn_card, lib = html.split('<div class="art-body')[0], html.split('<div class="art-body')[1]
    assert f'<span class="why">{worn_why}</span>' in worn_card  # 身上那張卡
    assert f'<span class="why">{hut_why}</span>' in lib  # 功法庫點開的那張
    assert re.search(r'<div class="more">\s*<span class="why">', lib)  # 在同一排的最前面（左邊的空位）
    ok = _practice(rows, "S.artOpen = 'w3';").split('<div class="art-body')[1]
    assert 'class="why"' not in ok  # 熔得掉的：不寫
    assert f'title="{hut_why}"' in lib  # title 照舊留著（桌面滑鼠停著看得到）


@needs_node
def test_the_hut_greys_out_seclusion_and_the_insight_melt_with_the_servers_reason():
    html = _practice([_art("w1", "武學", "甲拳", worn=True)], "S.insOpen = 'feng';",
                     seclude_blocked="草廬裡不能閉關。", insights=[{**_insight("feng", "風"), "blocked": "師父沒叫你熔意境。"}])
    assert re.search(r'<button class="btn" type="submit" disabled>閉關', html) and "草廬裡不能閉關。" in html
    assert re.search(r'data-act="melt-insight"[^>]*disabled>化成心得 10</button><small class="muted">師父沒叫你熔意境。</small>', html)


@needs_node
def test_the_library_keeps_its_title_and_the_chips_sit_under_it():
    html = _practice(_library_of_ten())
    assert re.search(r'<div class="label">功法庫 <small class="muted">武學與意境 0/50</small></div>\s*<div class="lib-filter">', html)


MELT_STUBS = (
    "const ask = (text, yes, go) => calls.push({ ask: text, yes, go });"
    "const mx = async (op, body) => { calls.push({ mx: op, body }); };"
)


@needs_node
def test_melting_asks_with_the_pages_own_layer_and_only_then_melts():
    out = run(
        "const el = { dataset: { id: 'a1', name: '基礎拳腳', confirm: '把【基礎拳腳】熔掉？這門熔了沒有心得，只空出一格。熔了還能免費重學：到任何城鎮，在江湖頁「此地還能做」找「學基礎拳腳」。' } };"
        "H.askMelt(el); const asked = H.calls.map((c) => ({ ask: c.ask, yes: c.yes })); const before = H.calls.filter((c) => c.mx).length;"
        "await H.calls[0].go(); return { asked, before, after: H.calls.filter((c) => c.mx) };",
        fns=["askMelt", "askMeltInsight"], consts=["meltAskText"], stubs=MELT_STUBS,
    )
    assert out["asked"] == [{
        "ask": "把【基礎拳腳】熔掉？這門熔了沒有心得，只空出一格。熔了還能免費重學：到任何城鎮，在江湖頁「此地還能做」找「學基礎拳腳」。",
        "yes": "熔掉",
    }]  # 問句整句是伺服器寫好的（data-confirm），網頁照放
    assert out["before"] == 0 and out["after"] == [{"mx": "melt", "body": {"art": "a1"}}]  # 按「熔掉」之前什麼都沒送


@needs_node
def test_melting_an_insight_asks_the_same_way():
    out = run(
        "H.askMeltInsight({ dataset: { id: 'feng', name: '風' } }); await H.calls[0].go(); return H.calls;",
        fns=["askMelt", "askMeltInsight"], consts=["meltAskText"], stubs=MELT_STUBS,
    )
    assert out[0]["ask"] == "把「風」化成心得？靠它的武學從此不能修練。" and out[0]["yes"] == "化成心得"
    assert out[1] == {"mx": "melt_insight", "body": {"insight": "feng"}}


def test_the_page_no_longer_uses_the_browsers_confirm_box():
    src = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    assert not re.search(r"\bconfirm\(", src) and "window.confirm" not in src


def test_the_melt_buttons_go_through_the_pages_own_layer():
    src = (ROOT / "web" / "app.js").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert 'case "melt": askMelt(el); break;' in src and 'case "melt-insight": askMeltInsight(el); break;' in src
    assert 'case "art-filter":' in src


@needs_node
def test_the_melt_question_is_the_servers_sentence_and_an_old_server_gets_the_old_question():
    out = run(
        "return [H.meltAskText({ dataset: { name: '旋風腿', confirm: 'SERVER' } }), H.meltAskText({ dataset: { name: '旋風腿', confirm: '' } })];",
        consts=["meltAskText"],
    )
    assert out == ["SERVER", "把【旋風腿】熔成心得？熔掉就沒了。"]
