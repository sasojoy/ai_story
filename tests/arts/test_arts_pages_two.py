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

ROOT = Path(__file__).parents[2]
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
  // DEAL_RE、dealHtml：療傷鈕上的折扣原因包成不折行的小段（FB-297）
  ...["KINDS", "QUALITY_RANK", "esc", "pro", "attrNoteHtml", "DEAL_RE", "dealHtml"].map((n) => { try { return konst(n); } catch (e) { return ""; } }),
  ...input.consts.map(konst),
  // 卷軸卡的零件（品質印、十成格、療傷鈕、庫的篩選……）：「// ── 修練 ──」到 pagePractice 之間整段照抄（跟 test_arts_pages.py 同一個切法）
  src.slice(src.indexOf("\n  // ── 修練 ──"), src.indexOf("\n  function pagePractice(")),
  ...input.fns.map(fn),
  input.stubs || "",
  "return { " + [...input.fns, ...input.consts, "libFilter", "setLibFilter", "meltView", "meltShown", "meltPickShown"].join(", ") + " };",  // 後面這幾個在上面那一段裡
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
    src = webharness.app_source()
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
    """六個基本意境兩兩合併：預覽寫的屬性跟 fusion.merge 真的給的一樣——同一個函式算的，不是另寫一份。
    武學重構：自己合自己是揣摩（強度加深一級，不是新的意境），預覽寫「揣摩」與強度從幾到幾，合了真的加深那一級。"""
    import itertools

    from tianxia import arts

    ids = list(content.insights)
    for n, (a, b) in enumerate(itertools.combinations(ids, 2)):
        state = _merger(content, f"甲{n}", [a, b])
        line = skillview.forge_line(state, content, world, [a, b])
        shown = re.search(r"→ 一個新的意境（屬(.)・", line)
        assert shown, line
        made, _ = fusion.merge(state, content, world, _named(f"新意境{n}"), a, b)
        assert made is not None and made.attribute == shown.group(1), (a, b, line)
    for a in ids:  # 意境效果池：同一種的兩份是揣摩，預覽寫揉完的層數，合了真的到二重
        state = _merger(content, f"乙{a}", [a, f"{a}~2"])
        line = skillview.forge_line(state, content, world, [a, f"{a}~2"])
        assert line.startswith("**揣摩**") and "二重" in line, line
        fusion.merge(state, content, world, None, a, f"{a}~2")
        assert arts.strength_of(state, a) == 2


def test_the_merge_preview_says_nobody_has_merged_it_before_or_what_it_becomes(content, world):
    first = _merger(content, "甲", ["feng", "huo"])
    assert skillview.forge_line(first, content, world, ["feng", "huo"]).endswith("\n沒人合過。")
    made, _ = fusion.merge(first, content, world, _named("燎原"), "feng", "huo")
    again = skillview.forge_line(first, content, world, ["feng", "huo"])
    assert "沒人合過" not in again and "會合出" not in again
    assert "\n再合一份「燎原」，效果另擲。" in again and "⚠" not in again  # 意境效果池：合過的再合是另一份
    other = _merger(content, "乙", ["feng", "huo"])
    line = skillview.forge_line(other, content, world, ["huo", "feng"])  # 別人首創、你還沒有的：照樣能合，預覽寫它會是什麼
    assert f"\n會合出「燎原」（屬{made.attribute}）。" in line and "沒人合過" not in line


def test_the_merge_preview_says_the_attribute_the_recipe_and_the_cost(content, world, state):
    # 爐裡只合意境（Joy 2026-10-21）：合併寫屬性、有沒有人合過、花多少心得體力
    state.player.member.wugong_id = "basic_fist"
    state.player.insights = ["feng", "huo"]
    state.player.stats["xinde"] = 100
    merge = skillview.forge_line(state, content, world, ["feng", "huo"])
    assert re.search(r"（屬.・", merge) and merge.endswith("\n沒人合過。"), merge
    assert "花 5 點心得、5 點體力" in merge


def test_the_merge_preview_still_refuses_what_you_do_not_hold(content, world, state):
    state.player.insights = ["feng"]
    line = skillview.forge_line(state, content, world, ["feng", "shui"])
    assert line.startswith("⚠") and "屬" not in line and "→" not in line


def test_heal_button_shows_the_price_and_matches_what_healing_really_charges(content, state):
    from tianxia import team

    member, p = state.player.member, state.player
    # 卷軸卡的療傷鈕自己寫字（內傷與 heal_cost）；伺服器只說按不按得下去與原因，不再送 label（review-ap3 M4：沒有人讀它）
    assert skillview.heal_button(state, content) == {"ok": False, "why": "氣血無恙，不用療傷。", "clinic": None, "note": None}
    member.injury, p.stats["silver"] = 35.0, 100
    assert skillview.heal_button(state, content) == {"ok": True, "why": None, "clinic": None, "note": "內傷 35・18 兩"}
    assert team.heal_cost(content, member) == 18  # 每 2 點內傷 1 兩，進位：頁面上寫的價錢是 server 的 heal_cost
    team.heal(state, content, member)
    assert p.stats["silver"] == 100 - 18 and member.injury == 0  # 寫的價錢就是真的收的價錢


def test_heal_button_is_greyed_out_with_the_reason_when_there_is_no_silver(content, state):
    """銀兩不夠全治時治一部分（team.heal_plan，PM 2026-10-12）；一兩都沒有才灰掉。"""
    state.player.member.injury, state.player.stats["silver"] = 35.0, 5
    assert skillview.heal_button(state, content) == {"ok": True, "why": None, "clinic": None, "note": "治 10 點・5 兩（還剩 25 點）"}
    state.player.stats["silver"] = 0
    assert skillview.heal_button(state, content) == {"ok": False, "why": "銀兩不足：療傷需要 18 兩。", "clinic": None, "note": None}
    from tianxia import team

    assert team.heal(state, content, state.player.member) == ["銀兩不足：療傷需要 18 兩。"]  # 按下去（舊版畫面）回的是同一句


def test_heal_button_does_not_offer_to_heal_a_wound_the_status_bar_does_not_show(content, state):
    """狀態列的內傷是 int()：不到 1 點不寫；按鈕也不亮（以前就是這樣，改成伺服器給的之後不能變）。"""
    state.player.member.injury, state.player.stats["silver"] = 0.6, 100
    assert not skillview.heal_button(state, content)["ok"]


def test_the_menxia_view_carries_the_heal_button(real):
    import server

    game = _real_game(real)
    assert server.menxia_view(game)["heal"] == {"ok": False, "why": "氣血無恙，不用療傷。", "clinic": None, "note": None} and server.menxia_view(game)["heal_cost"] == 0
    game.state.player.member.injury, game.state.player.stats["silver"] = 20.0, 50
    assert server.menxia_view(game)["heal"] == {"ok": True, "why": None, "clinic": None, "note": "內傷 20・10 兩"} and server.menxia_view(game)["heal_cost"] == 10
    game.state.player.stats["silver"] = 0
    view = server.menxia_view(game)["heal"]
    assert not view["ok"] and "銀兩不足" in view["why"] and "label" not in view
    game.heal()  # 一兩都沒有：不收、不寫紀錄，內傷還在
    assert game.state.player.member.injury == 20.0 and game.state.player.stats["silver"] == 0


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

    assert database.SCHEMA_VERSION == 7  # 兵器第二批（gear_recipes）升到 4、玩家傳（biographies）升到 5、商城升到 6、真人量表升到 7；renames_told 自己是 PlayerState 的欄位，沒有升版
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


PRACTICE_STUBS = 'const guideHtml = () => "", proGuide = () => "", createSub = () => "", shown = () => true, SELF_NEWS = [];'  # 自己頁底下的入口（自創、行狀）這裡不看
CRAFT_STUBS = PRACTICE_STUBS + 'const furnaceSvg = () => "<svg></svg>", toast = () => {}, spinAt = () => "";'  # 自創那一頁的入口（自創單獨一頁）這裡不看
CRAFT_FNS = ["pageCraft", "forgeBody", "forgeReady", "artFilter", "setArtFilter", "filterChips", "showArts",
             "pickMark", "craftView", "craftFilterRow", "craftChip", "kilnWarn", "kilnHtml", "madeCardHtml", "previewCardHtml", "forgeLineHtml", "craftSheetHtml", "craftSheetInner", "potGlow", "kilnPeek", "manualRows", "manualEntry", "bookIcon"]
CRAFT_CONSTS = ["ART_FILTERS", "filterKey", "CRAFT_SORTS", "CRAFT_PAGE", "BOOKS"]


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
        S={"menxia": _menxia(owned_arts=_library_of_ten(), insights=INSIGHTS), "main": {"status": {"injury": 0}}, "craftPick": True, **S},  # 清單在抽屜裡（Joy 2026-10-19）
        fns=CRAFT_FNS, consts=CRAFT_CONSTS, stubs=CRAFT_STUBS,
    )


def _library_names(html):
    return re.findall(r'<button class="art libr[^"]*"[^>]*>.*?<span class="txt"><b>(.+?)</b>', html)


def _drawer(html):
    """修練頁底下那一個抽屜（招式與絕學稿案第四輪：點什麼，內容就從底下升起）"""
    return html.split('class="sheet pr-sheet"')[1]


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
    assert len(names) == 9 and "武Y" in names and "武X" not in names  # 照種類分兩段列（招式與絕學稿案第四輪），點開的那一門補在它那一段


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


# ── 煉製頁挑東西的抽屜（爐裡只合意境）──


@needs_node
def test_the_craft_page_lists_only_insights_whatever_filter_is_remembered():
    """爐裡只合意境（Joy 2026-10-21）：抽屜裡不列武學、不畫「功法」那四顆篩選；記著的「內功」「武學」「意境」篩選
    也不會把意境藏起來（review-ap2 的小毛病：意境整排不見又沒有提示）。"""
    both = ["風", "火"]
    for remembered in (None, "內功", "武學", "意境"):
        html = _craft(remembered)
        assert _craft_names(html) == ([], both), remembered
        assert "fchips" not in html and 'data-act="art-filter"' not in html, remembered


@needs_node
def test_the_craft_choice_is_remembered_in_the_browser_too():
    out = run(
        "H.setArtFilter('craft', '意境'); delete H.S.artFilter; return [H.artFilter('craft'), H.store];",
        fns=CRAFT_FNS, consts=CRAFT_CONSTS, stubs=CRAFT_STUBS,
    )
    assert out == ["意境", {"tx-arts-filter-craft": "意境"}]


def test_the_practice_poll_no_longer_watches_the_heal_fields():
    """療傷鈕 Joy 2026-10-25 從俠客頁拿掉了（療傷只在醫館，入口是江湖頁的「醫館療傷」）：輪詢重畫的欄位表（MENXIA_SHOWN）
    不再看 heal、heal_cost——內傷或銀兩變了不必重畫俠客頁。"""
    src = webharness.app_source().replace("\r\n", "\n")
    shown = {
        page: re.findall(r'"([a-z_]+)"', fields)
        for page, fields in re.findall(r"^\s+(practice|craft): \[(.*?)\],?(?:\s*//.*)?$", src[src.index("const MENXIA_SHOWN"):], re.M)
    }
    assert "heal" not in shown["practice"] and "heal_cost" not in shown["practice"] and "heal" not in shown["craft"]


# ── 俠客頁沒有療傷鈕、沒有閉關（Joy 2026-10-25）──


@needs_node
def test_the_self_page_has_no_heal_button_and_no_seclusion_form():
    """療傷只在醫館做得了，入口是江湖頁「此地還能做」的「醫館療傷」（act:heal）；閉關現在的玩法用不到。「去做」只剩煉製與自創。"""
    html = run(
        f"S.menxia = {json.dumps(_menxia(heal_cost=12))}; S.main.status.injury = 23; return H.pagePractice();",
        S={"main": {"status": {"injury": 23}}}, fns=["pagePractice"], stubs=PRACTICE_STUBS,
    )
    assert 'data-op="heal"' not in html and 'id="seclude"' not in html and "閉關" not in html
    assert re.search(r'<section class="self-sec" aria-label="去做">.*?data-tab="craft".*?</section>', html, re.S)


# ── 卷軸卡裡 W6、序章指路、閉關與意境的拒絕 ──


@needs_node
def test_w6_the_library_card_writes_the_comparison_above_its_buttons_but_the_worn_card_does_not():
    cmp = "比身上的【甲拳】：威力 +2.0（第一成）、多了〔化勁〕；換上後跟內功同屬，整體 +20%"
    rows = [_art("w1", "武學", "甲拳", worn=True), _art("w2", "武學", "乙拳", compare=cmp)]
    html = _practice(rows, "S.artOpen = 'w2';")
    body = _drawer(html)
    assert f'<p class="cmp">{cmp}</p>' in body and body.index('class="cmp"') < body.index('class="acts"')  # 鈕的上面，改練之前看得到
    assert 'class="cmp"' not in _drawer(_practice(rows, "S.pdrawer = {t: 'worn', key: '武學'};"))  # 身上那一門（沒有 compare）不寫
    opened = _practice(rows, "S.artOpen = 'w2'; S.artInfo = 'w2';")
    assert 'class="cmp"' not in opened  # 點開詳情時功法卡裡有，這裡不重複


@needs_node
def test_the_glow_lists_the_server_sends_decide_every_hook_on_the_cards():
    """序章的指路（T7 走查 W-A）：卡裡改練、修練、熔煉三顆鈕、收著的那一列，發不發光都看伺服器送的 glow，網頁不猜。
    m2：熔煉鈕上的 data-glow="melt" 在序章裡要在；序章外（沒有 glow 這個鍵）一個都不畫。"""
    rows = [_art("w1", "武學", "甲拳", worn=True, glow=["cultivate"]),
            _art("w2", "武學", "乙拳", glow=["switch", "melt"]), _art("w3", "武學", "丙拳", glow=["cultivate"])]
    html = _practice(rows, "S.artOpen = 'w2';")
    body = _drawer(html)
    assert re.search(r'<button class="linkish" data-act="melt" data-glow="melt" data-id="w2"', body)  # m2
    assert re.search(r'data-act="switch" data-glow="switch" data-id="w2"', body)
    assert 'data-act="cultivate"' not in body  # 下品、修練不在名單上：沒有「衝絕學」那一塊（只有上品與序章點名的才畫）
    worn = _drawer(_practice(rows, "S.pdrawer = {t: 'worn', key: '武學'};"))  # 點了身上那一門的光點（招式與絕學稿案第四輪的抽屜）
    assert re.search(r'data-act="cultivate" data-glow="cultivate" data-id="w1"', worn)  # 身上那一門讀它自己那一列的 glow
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
    lib = _drawer(_practice(rows, "S.artOpen = 'w2';"))
    worn_card = _drawer(_practice(rows, "S.pdrawer = {t: 'worn', key: '武學'};"))
    assert f'<span class="why">{worn_why}</span>' in worn_card  # 身上那張卡
    assert f'<span class="why">{hut_why}</span>' in lib  # 功法庫點開的那張
    assert re.search(r'<div class="more">\s*<span class="why">', lib)  # 在同一排的最前面（左邊的空位）
    ok = _drawer(_practice(rows, "S.artOpen = 'w3';"))
    assert 'class="why"' not in ok  # 熔得掉的：不寫
    assert f'title="{hut_why}"' in lib  # title 照舊留著（桌面滑鼠停著看得到）


@needs_node
def test_the_hut_greys_out_the_insight_melt_with_the_servers_reason():
    """閉關鈕 2026-10-25 拿掉了：伺服器還送 seclude_blocked，俠客頁不畫它。"""
    html = _practice([_art("w1", "武學", "甲拳", worn=True)], "S.insOpen = 'feng';",
                     seclude_blocked="草廬裡不能閉關。", insights=[{**_insight("feng", "風"), "blocked": "師父沒叫你熔意境。"}])
    assert "閉關" not in html
    assert re.search(r'data-act="melt-insight"[^>]*disabled>化成心得 10</button><small class="muted">師父沒叫你熔意境。</small>', html)


@needs_node
def test_the_library_keeps_its_title_and_the_chips_sit_under_it():
    html = _practice(_library_of_ten())
    # 俠客頁重排（Joy 2026-10-24）：功法庫是一個摺疊，批量熔煉那一顆在摺疊的第一行、篩選緊接在它底下
    assert re.search(
        r'<summary>功法庫 <small class="muted">武學與意境 0/50</small></summary><div class="fold-body">'
        r'<button class="linkish melt-mode" data-act="melt-mode">批量熔煉</button>\s*<div class="lib-filter">', html,
    )


# ── 批量熔煉（企劃者 2026-10-14「合成越來越多，需要能快速熔煉的機制」）──────────────────


def _melt_rows():
    rows = _library_of_ten()
    rows[2]["melt"]["value"] = 3
    rows[3].update(quality="中品", melt={"ok": True, "note": "退回心得 5", "confirm": "", "value": 5})
    rows[4]["melt"] = {"ok": False, "note": "先替它定名", "confirm": ""}
    return rows


@needs_node
def test_batch_melt_mode_lists_every_art_with_a_tick_and_sums_what_is_ticked():
    html = _practice(_melt_rows(), "H.S.meltSel = { arts: ['w2', 'w3', 'w4', 'gone'], ins: ['feng'] };")
    assert html.count('data-act="melt-pick"') == 10  # 不分頁：十門都列，身上的兩門不在
    assert re.search(r'data-act="melt-pick" data-id="w4" disabled', html)  # 熔不掉的勾不了
    assert '<i class="why">先替它定名</i>' in html  # 原因寫在那一列
    assert "已勾 <b>3</b> 樣<small>心得 +18</small>" in html  # w2 3＋w3 5＋風 10；熔不掉的、已經不在的不算
    assert re.search(r'data-act="melt-pick-ins" data-id="feng"\s+aria-pressed="true"', html)  # 意境跟武學排在同一張清單
    assert 'data-act="melt-shown"' in html and "收起" in html
    assert 'data-act="melt-quality"' not in html  # 照品質一鍵全勾換成「勾選篩出來的全部」


def _judged_rows():
    """批量熔煉要判斷好壞的資料（skillview.melt_judge）：w2 比身上弱、帶兩種功效；w3 比身上強、絕招；n2 本命戰法。"""
    rows = _melt_rows()
    rows[2].update(gen="精進", judge={"power": 12.4, "worn_diff": -2.1, "traits": [{"name": "破甲", "layers": 2}, {"name": "借力", "layers": 1}],
                                     "special": None, "ultimate": None, "tactic": None}, compare="比身上的甲拳弱一些")
    rows[3].update(attribute="剛", judge={"power": 30.0, "worn_diff": 4.5, "traits": [], "special": None, "ultimate": "武1", "tactic": None})
    rows[8].update(judge={"power": 8.0, "worn_diff": 0.0, "traits": [], "special": None, "ultimate": None, "tactic": "長坂一喝"})
    return rows


DEEP = [dict(_insight("feng", "風"), rank=2, mood="圓融", depth="二重・圓融", lean="正"), _insight("huo", "火")]


@needs_node
def test_each_melt_row_says_enough_to_judge_it_and_opens_for_details():
    html = _practice(_judged_rows(), "H.S.meltSel = { arts: [], ins: [] }; H.S.meltOpen = 'arts:w2';", insights=DEEP)
    assert "<span>武學</span>・<span>屬快</span>・<span>精進</span>・<span>6成</span>・<span>威力 12.4</span>" in html
    assert '<i class="down">比身上弱 −2.1</i><i>破甲2</i><i>借力</i>' in html
    # 招前面蓋印（招式與絕學稿案第一節）：絕招金印「絕」、人物的本命朱印「本命」，後面是招名
    assert '<i class="up">比身上強 +4.5</i><i class="hi"><b class="tseal gold">絕</b>武1</i>' in html
    assert '<i>跟身上一樣</i><i class="hi"><b class="tseal red">本命</b>長坂一喝</i>' in html
    assert "<span>意境</span>・<span>屬快</span>・<span>二重</span>・<span>圓融</span>・<span>正</span>" in html and "心得<b>10</b>" in html
    detail = html[html.index('class="mdetail"'):]
    assert "功效：〔破甲〕2 層〔借力〕" in detail and "比身上的甲拳弱一些" in detail and "熔了退回心得 3" in detail
    assert html.count('class="mdetail"') == 1  # 只攤開點的那一列


@needs_node
def test_melt_filters_and_sorts_and_ticks_only_what_is_shown():
    out = run(
        "H.S.meltSel = { arts: ['n3'], ins: [] };"
        "H.meltView().weak = true; const weak = H.meltShown(H.S.menxia).map((it) => it.id);"
        "H.meltView().weak = false; H.meltView().kind = '意境'; const ins = H.meltShown(H.S.menxia).map((it) => it.id);"
        "H.meltView().kind = ''; H.meltView().rank = '2'; const two = H.meltShown(H.S.menxia).map((it) => it.id);"
        "H.meltView().rank = ''; H.meltView().attr = '剛'; const hard = H.meltShown(H.S.menxia).map((it) => it.id);"
        "H.meltView().attr = ''; H.meltView().gen = '精進'; const gen = H.meltShown(H.S.menxia).map((it) => it.id);"
        "H.meltView().gen = ''; H.meltView().sort = 'power'; const byPower = H.meltShown(H.S.menxia).map((it) => it.id);"
        "H.meltView().sort = 'value'; const byValue = H.meltShown(H.S.menxia).map((it) => it.id);"
        "H.meltView().sort = ''; H.meltView().kind = '內功'; H.meltPickShown(); const ticked = H.S.meltSel.arts;"
        "H.meltPickShown(); const unticked = H.S.meltSel.arts;"
        "H.meltView().kind = ''; const page = H.pagePractice();"
        "return { weak, ins, two, hard, gen, byPower, byValue, ticked, unticked, page };",
        S={"menxia": _menxia(owned_arts=_judged_rows(), insights=DEEP), "main": {"status": {"injury": 0}}, "meltSel": None},
        fns=["pagePractice"], stubs=PRACTICE_STUBS + "const renderPage = () => {};",
    )
    assert out["weak"] == ["w2"]  # 只看比身上弱的：沒有比較的（意境、沒給 judge 的）不算
    assert out["ins"] == ["feng", "huo"] and out["two"] == ["feng"] and out["hard"] == ["w3"] and out["gen"] == ["w2"]
    assert out["byPower"][:3] == ["n2", "w2", "w3"]  # 威力低的在前，沒有威力的排在後面
    assert out["byValue"][:3] == ["feng", "huo", "w3"]  # 心得多的在前
    assert out["ticked"] == ["n3", "n2", "n4", "n5"]  # 內功、熔得掉的全勾（原本勾的留著）
    assert out["unticked"] == []  # 都勾了再按一次全部取消
    assert 'data-key="kind"' in out["page"] and 'data-key="sort"' in out["page"] and 'data-act="melt-weak"' in out["page"]


@needs_node
def test_batch_melt_is_not_offered_in_the_hut():
    rows = _library_of_ten()
    rows[2]["glow"] = ["melt"]
    assert 'data-act="melt-mode"' not in _practice(rows)


@needs_node
def test_batch_melt_asks_before_melting_what_is_ticked():
    out = run(
        "H.S.menxia = { owned_arts: input_rows, insights: [] }; H.S.meltSel = { arts: ['w2', 'w5'], ins: ['huo'] };"
        "H.askMeltMany({ dataset: { v: '42' } }); const asked = H.calls[0].ask; await H.calls[0].go();"
        "return { asked, sent: H.calls.filter((c) => c.mx), sel: H.S.meltSel };".replace("input_rows", json.dumps(_melt_rows())),
        fns=["askMeltMany", "pagePractice"], stubs=MELT_STUBS + "const renderPage = () => {};",
    )
    assert out["asked"].startswith("把勾的 2 門武學、1 個意境一起熔掉？心得 +42。") and "不能再修練" in out["asked"]
    assert out["sent"] == [{"mx": "melt_many", "body": {"arts": ["w2", "w5"], "insights": ["huo"]}}] and out["sel"] is None


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
    src = webharness.app_source()
    assert not re.search(r"\bconfirm\(", src) and "window.confirm" not in src


def test_the_melt_buttons_go_through_the_pages_own_layer():
    src = webharness.app_source().replace("\r\n", "\n")
    assert 'case "melt": askMelt(el); break;' in src and 'case "melt-insight": askMeltInsight(el); break;' in src
    assert 'case "art-filter":' in src


@needs_node
def test_the_melt_question_is_the_servers_sentence_and_an_old_server_gets_the_old_question():
    out = run(
        "return [H.meltAskText({ dataset: { name: '旋風腿', confirm: 'SERVER' } }), H.meltAskText({ dataset: { name: '旋風腿', confirm: '' } })];",
        consts=["meltAskText"],
    )
    assert out == ["SERVER", "把【旋風腿】熔成心得？熔掉就沒了。"]


@needs_node
def test_the_person_card_has_chuangong_buttons_with_price_effect_and_reason():
    """傳功門下：名冊點一位同伴，人物卡底下一排傳功鈕；按不下去的灰掉、原因寫在第二行（Config.chuangong）。"""
    lessons = [
        {"what": "wugong", "label": "練武學・20 心得", "effect": "【掌法】第1成→第2成，威力 +7.8", "problem": None},
        {"what": "neigong", "label": "練內功", "effect": "", "problem": "他還沒有內功，沒東西可練。"},
    ]
    html = run(
        "return H.pagePractice();",
        S={"menxia": _menxia(roster=[{"label": "本人", "key": "player"}, {"label": "同伴", "key": "mate"}], person="mate",
                             person_card="<p>同伴卡</p>", lessons=lessons), "main": {"status": {"injury": 0}}},
        fns=["pagePractice", "lessonsHtml"], stubs=PRACTICE_STUBS,
    )
    assert 'data-act="teach" data-what="wugong" >練武學・20 心得<small>【掌法】第1成→第2成，威力 +7.8</small>' in html
    assert 'data-what="neigong" disabled title="他還沒有內功，沒東西可練。">練內功<small>他還沒有內功，沒東西可練。</small>' in html
    none = run("return H.pagePractice();", S={"menxia": _menxia(roster=[{"label": "本人", "key": "player"}, {"label": "同伴", "key": "mate"}],
               person="player", person_card="<p>本人</p>", lessons=[]), "main": {"status": {"injury": 0}}},
               fns=["pagePractice", "lessonsHtml"], stubs=PRACTICE_STUBS)
    assert "傳功" not in none


# ── 批量熔煉判斷好壞的資料（企劃者 2026-10-16）────────────────────


def test_each_library_row_carries_what_batch_melting_needs_to_judge_it(real):
    from tianxia import team, traits
    from tianxia.martial_arts import power_at
    game = _real_game(real)
    game.state.player.arts = ["caocao_wugong", "jichu_quanjiao"]
    rows = {r["id"]: r for r in skillview.art_rows(game.state, real, game.world)}
    worn = game.state.player.member.wugong_id
    sig = rows["caocao_wugong"]["judge"]
    mine = team.player_art(game.state, real, game.world, "caocao_wugong")
    assert sig["power"] == round(power_at(mine, rows["caocao_wugong"]["level"]), 1)
    assert sig["worn_diff"] == round(power_at(mine, 1) - power_at(team.player_art(game.state, real, game.world, worn), 1), 1)
    assert sig["worn_diff"] > 0 and sig["tactic"]  # 本命武學：比開局那門強、帶本命戰法
    assert sig["traits"] == [{"name": traits.general(real, a).name, "layers": traits.traits_of(mine).count(a), "tier": 1} for a in dict.fromkeys(traits.traits_of(mine))]
    assert rows[worn]["judge"]["worn_diff"] is None  # 身上那門自己沒得比
    game.state.player.insights = ["feng"]
    ins = skillview.insight_rows(game.state, real, game.world)[0]
    assert ins["rank"] == 1 and ins["mood"] is None and ins["melt"] == real.config.melt_insight_xinde


def test_the_practice_poll_ignores_the_hit_points_ticking_up_on_the_card():
    """修練頁輪詢只在 MENXIA_SHOWN 列的欄位變了才重畫，而 player_card／person_card 上寫著
    「氣血 520/639」——氣血每分鐘都在回，照原樣比的話每一輪都重畫：畫面閃一下、捲軸彈回最上面
    （Joy 2026-10-22 在選意境那頁停久了遇到）。比之前要先把氣血的數字抹掉；等級、武學真的變了照樣重畫。
    氣血的即時顯示靠狀態列（renderTop 另外畫），不靠這一頁重畫。"""
    card = "### 司馬\n第 16 級\u3000氣血 {hp}/639\n內功　混元"
    out = webharness.run(r"""
      const m = src.match(/^\s+const steady = .*$/m);
      if (!m) throw new Error("refreshPage 少了抹掉氣血數字的 steady()");
      const steady = eval("(" + m[0].trim().replace(/^const steady = /, "").replace(/;\s*$/, "") + ")");
      console.log(JSON.stringify([
        steady(input.hurt) === steady(input.whole),   // 只有氣血不同：不該算「變了」
        steady(input.hurt) === steady(input.levelled), // 等級不同：該算「變了」
        steady(7) === 7, steady(null) === null,
      ]));
    """, {"hurt": card.format(hp=520), "whole": card.format(hp=639),
          "levelled": card.format(hp=520).replace("16 級", "17 級")})
    same_hp, same_level, keeps_number, keeps_null = out
    assert same_hp, "氣血回了一點就判定成「變了」：修練頁每一輪都會整頁重畫"
    assert not same_level, "等級變了卻判定成「沒變」：真的該重畫的時候不重畫了"
    assert keeps_number and keeps_null, "不是字串的欄位不能被動到"


def test_an_empty_library_says_whose_slots_the_count_is_and_not_that_it_is_empty():
    """U-14（手機介面自檢 2026-10-31）：標題寫「功法庫 3/50」（身上兩門＋意境一份也佔格），點開不能說「功法庫是空的」。"""
    rows = [_art("w1", "武學", "甲拳", worn=True), _art("n1", "內功", "乙功", worn=True)]
    html = _practice(rows, insights=[_insight("feng", "風")], holdings={"count": 3, "cap": 50})
    assert "功法庫 3/50" in html and "功法庫是空的" not in html
    assert "庫裡還沒有閒置的武學。上面的 3/50 是身上練的 2 門、意境 1 份佔的。" in html
    bare = _practice([], insights=[], holdings={"count": 0, "cap": 50})
    assert "庫裡還沒有閒置的武學。合成出來的" in bare  # 什麼都沒有：不多那一句


def _create_views(xinde: int):
    """正式內容 week7 的一局，心得 xinde：/api/main 與 /api/menxia 那兩份（自創那一頁畫的是 main.status.create）。"""
    import server
    from jianfa_kit import jianfa_game, ready

    game = ready(jianfa_game("week7"), side="guan", loc="changshe", level=20)
    game.state.player.stats["xinde"] = xinde
    return server.main_view(game), server.menxia_view(game)


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_create_short_of_xinde_greys_the_entry_and_the_button_and_says_how_much_is_missing():
    """U-04（手機介面自檢 2026-10-31）：心得不夠開始自創時，俠客頁的入口與自創頁的鈕都灰掉、原地寫「還差 N 心得」，
    說明不再讀成「走到立意才要心得」；被擋下的執器不把自創頁關掉，原因寫在自創頁頂上。"""
    from test_prologue_web import run

    m, x = _create_views(24)
    c = m["status"]["create"]
    need = c["price"] - 24
    assert c["on"] and c["problem"] is None and need > 0
    hero = run(m, "return H.pagePractice();", menxia=x)
    entry = re.search(r'<button class="btn self-go" data-act="create-open"[^>]*>自創武學<small>([^<]*)</small>', hero)
    assert entry and " disabled" in entry.group(0) and entry.group(1) == f"還差 {need} 心得"
    page = run(m, "return H.pagePractice();", menxia=x, S={"createOpen": True, "createPick": {"kind": "武學", "form": "拳腳"}})
    assert f"開始自創要先有 {c['price']} 心得，你有 24，還差 {need} 心得（立意那一刻才收）" in page
    assert re.search(rf'data-act="create-begin" disabled>還差 {need} 心得<small>', page)
    assert page.index("mc-cost") < page.index("cr-forms")  # 先說要多少心得，再讓人挑
    # 伺服器擋下執器（例：剛好在別處花掉了心得）：留在自創頁，原因寫在頁首
    refused = run(m, """return (async () => {
      H.S.createOpen = true; H.S.tab = "practice"; H.S.createPick = { kind: "武學", form: "拳腳" };
      T.qs['.ask [data-act="ask-no"]'] = { focus() {} };
      const target = { dataset: { act: "create-begin" }, classList: { contains: () => false, add() {}, remove() {} } };
      await T.docListeners.click[0]({ target: { closest: () => target } });
      return { open: H.S.createOpen, message: H.S.message, calls: T.calls.map((c) => c[0]) };
    })();""", menxia=x, responses={"/api/menxia/create_begin": {"menxia": x, "main": m, "message": "<p>心得不足：自創一門要 100（你有 24）。</p>"}})
    assert "/api/menxia/create_begin" in refused["calls"]
    assert refused["open"] is True and "心得不足" in refused["message"]
    m2, x2 = _create_views(c["price"] + 5)  # 夠了：照舊按得下去，說明寫「立意那一刻才收」
    ok = run(m2, "return H.pagePractice();", menxia=x2, S={"createOpen": True, "createPick": {"kind": "武學", "form": "拳腳"}})
    assert 'data-act="create-begin" >握起拳腳' in ok and "立意那一刻才收，之後擱下不退" in ok
