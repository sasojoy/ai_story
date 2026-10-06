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

from tianxia import fusion, journal, library, skillview
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


def test_the_record_is_a_player_field_and_the_schema_version_did_not_move(content):
    from tianxia import database
    from tianxia.state import PlayerState, new_game_state

    assert database.SCHEMA_VERSION == 2
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


PRACTICE_STUBS = 'const guideHtml = () => "", proGuide = () => "";'  # attrNoteHtml 不在這裡：有的話（arts-polish-1 之後）driver 自己會抓真的


def _menxia(**over):
    base = {
        "slot_cards": [{"kind": k, "card": f"<p>{k}卡</p>", "learned": True, "level": 1, "maxed": False, "blocked": None, "price": 1} for k in ("武學", "內功")],
        "owned_arts": [], "insights": [], "roster": [{"label": "本人", "key": "player"}], "person": None, "person_card": None,
        "on_team": False, "rules": "<p>規則。</p>", "holdings": {"count": 0, "cap": 50}, "player_card": "<p>本人</p>", "naming": None,
        "heal": {"label": "療傷（銀兩 18）", "ok": True, "why": None},
    }
    return {**base, **over}


def _art(art_id, kind, name, quality="下品", level=1, worn=False):
    return {
        "id": art_id, "kind": kind, "name": name, "quality": quality, "attribute": "快", "level": level, "worn": worn, "insight": None,
        "card": f"<p>{name}卡</p>", "cultivate": {"ok": False, "note": "沒有融過意境", "legend": None},
        "melt": {"ok": not worn, "note": "退回心得 3"}, "relearn": None,
    }


def _insight(insight_id, name):
    return {"id": insight_id, "name": name, "attribute": "快", "lean": "無", "note": "", "melt": 10}


LIBRARY = [
    _art("w1", "武學", "甲拳", "絕學", 4, worn=True), _art("n1", "內功", "乙功", "上品", 3, worn=True),
    _art("w2", "武學", "丙腿", "中品", 2), _art("n2", "內功", "丁訣", "下品", 5), _art("w3", "武學", "戊掌", "下品", 1),
]
INSIGHTS = [_insight("feng", "風"), _insight("huo", "火")]
FILTER_FNS = ["pagePractice", "pageCraft", "forgeBody", "forgeReady", "healButton", "artFilter", "setArtFilter", "filterChips", "showArts", "showInsights"]
FILTER_CONSTS = ["ART_FILTERS", "filterKey"]
CRAFT_STUBS = PRACTICE_STUBS + 'const furnaceSvg = () => "<svg></svg>", toast = () => {};'


def _page(which, filter_for=None, **S):
    """which：pagePractice 或 pageCraft；filter_for：先把這一頁的篩選設成它。回傳（html, 看得到的功法名, 看得到的意境名）。"""
    script = (
        (f"H.setArtFilter({json.dumps(which)}, {json.dumps(filter_for)});" if filter_for else "")
        + f"const html = H.{'pagePractice' if which == 'practice' else 'pageCraft'}(); return html;"
    )
    return run(
        script, S={"menxia": _menxia(owned_arts=LIBRARY, insights=INSIGHTS), "main": {"status": {"injury": 0}}, **S},
        fns=FILTER_FNS, consts=FILTER_CONSTS, stubs=CRAFT_STUBS,
    )


def _shown_names(html, which):
    if which == "practice":
        arts = re.findall(r'<button class="art [^"]*" data-act="art"[^>]*>(?:◆ )?(?:武學|內功)　(\S+?)（', html)
        insights = re.findall(r'<div class="insight"><div><b>「(.+?)」</b>', html)
    else:
        arts = re.findall(r'data-act="pick" data-type="art" data-id="[^"]*"[^>]*>\s*<b>(.+?)</b>', html)
        insights = re.findall(r'data-act="pick" data-type="ins" data-id="[^"]*"[^>]*>\s*<b>(.+?)</b>', html)
    return arts, insights


@needs_node
@pytest.mark.parametrize("which", ["practice", "craft"])
def test_each_filter_shows_only_its_kind_on_both_pages(which):
    everything = (["甲拳", "乙功", "丙腿", "丁訣", "戊掌"], ["風", "火"])
    assert _shown_names(_page(which), which) == everything  # 預設全部：照伺服器排好的順序，一個不少
    assert _shown_names(_page(which, "內功"), which) == (["乙功", "丁訣"], [])
    assert _shown_names(_page(which, "武學"), which) == (["甲拳", "丙腿", "戊掌"], [])
    assert _shown_names(_page(which, "意境"), which) == ([], ["風", "火"])


@needs_node
@pytest.mark.parametrize("which", ["practice", "craft"])
def test_the_four_chips_sit_in_one_row_and_mark_the_current_one(which):
    html = _page(which, "武學")
    group = re.search(r'<span class="fchips"[^>]*>(.*?)</span>', html, re.S).group(1)
    chips = re.findall(r'<button[^>]*data-filter="([^"]+)"[^>]*aria-pressed="(true|false)"', group)
    assert chips == [("全部", "false"), ("內功", "false"), ("武學", "true"), ("意境", "false")]
    assert html.count('class="fchips"') == 1 and f'data-page="{which}"' in group


@needs_node
def test_the_craft_page_filter_sits_in_the_label_row_so_the_first_screen_does_not_grow():
    """煉製頁的第一屏：篩選鈕併進「功法」那一行標籤（跟以前的「武學」標籤同一行），不另外多一行。"""
    html = _page("craft")
    label = re.search(r'<div class="label[^"]*">(.*?)</div>', html[html.index('id="forge"'):], re.S).group(0)
    assert "fchips" in label and "data-filter" in label


@needs_node
def test_a_filter_with_nothing_in_it_says_so_instead_of_leaving_a_hole():
    out = run(
        "H.setArtFilter('practice', '內功'); return H.pagePractice();",
        S={"menxia": _menxia(owned_arts=[_art("w1", "武學", "甲拳", "下品", 1, worn=True)]), "main": {"status": {"injury": 0}}},
        fns=FILTER_FNS, consts=FILTER_CONSTS, stubs=CRAFT_STUBS,
    )
    assert "沒有符合的功法" in out


@needs_node
def test_the_choice_is_remembered_per_page_in_local_storage():
    out = run(
        "H.setArtFilter('practice', '內功'); H.setArtFilter('craft', '意境');"
        "delete H.S.artFilter;"  # 重新整理：記憶體裡的沒了，從 localStorage 讀回來
        "return [H.artFilter('practice'), H.artFilter('craft'), H.store];",
        fns=FILTER_FNS, consts=FILTER_CONSTS, stubs=CRAFT_STUBS,
    )
    assert out[:2] == ["內功", "意境"] and out[2] == {"tx-arts-filter-practice": "內功", "tx-arts-filter-craft": "意境"}


@needs_node
def test_a_broken_or_foreign_stored_value_falls_back_to_all():
    out = run(
        "H.store['tx-arts-filter-practice'] = '亂寫的'; return [H.artFilter('practice'), H.artFilter('craft')];",
        fns=FILTER_FNS, consts=FILTER_CONSTS, stubs=CRAFT_STUBS,
    )
    assert out == ["全部", "全部"]


@needs_node
def test_a_browser_without_storage_still_filters_for_this_page_view():
    """localStorage 取不到（私密視窗、封鎖網站資料）會丟例外：讀不到當沒選過、存不了就只在這一頁有效，畫面照樣畫。"""
    out = run(
        "globalThis.localStorage = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); } };"
        "const first = H.artFilter('practice'); H.setArtFilter('practice', '武學'); return [first, H.artFilter('practice')];",
        fns=FILTER_FNS, consts=FILTER_CONSTS, stubs=CRAFT_STUBS,
    )
    assert out == ["全部", "武學"]


@needs_node
def test_a_filter_name_the_page_does_not_know_is_ignored():
    out = run("H.setArtFilter('practice', '亂寫'); return H.artFilter('practice');", fns=FILTER_FNS, consts=FILTER_CONSTS, stubs=CRAFT_STUBS)
    assert out == "全部"


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
        fns=FILTER_FNS, consts=FILTER_CONSTS, stubs=PRACTICE_STUBS,
    )
    row = re.search(r'<div class="row practice-actions">(.*?)</div>', html, re.S).group(1)
    assert row.count("<button") == 2 and "療傷（銀兩 18）" in row and "練成武學（心得 1）" in row


@needs_node
def test_the_melt_question_is_the_servers_sentence_and_an_old_server_gets_the_old_question():
    out = run(
        "return [H.meltAskText({ dataset: { name: '旋風腿', confirm: 'SERVER' } }), H.meltAskText({ dataset: { name: '旋風腿', confirm: '' } })];",
        consts=["meltAskText"],
    )
    assert out == ["SERVER", "把【旋風腿】熔成心得？熔掉就沒了。"]
