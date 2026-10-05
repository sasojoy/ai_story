"""FB-064：戰況變化那一行（「（潁川汝南 -1）」）看不懂——沒寫這是戰線、也沒寫偏向誰。
第一季規則開著時改成一枚「數值標籤」，寫的是哪一方佔了上風的一句話（不寫數字），顏色照看畫面的人的陣營：
對自己陣營有利綠、對另一方有利紅、散人與豪強（戰線上沒有立場）不上色；豪強割據的漲落同一套寫法，只有豪強看了是有利的。
句子在 content/front_lines.json（照 check_lines 的做法：模型、載入、驗證、挑句都一樣）。開關關著時一個字都不變。"""
from __future__ import annotations

import json
import random
import re
import shutil
from pathlib import Path
from unittest import mock

import pytest

import server
from conftest import FIXTURE, FixedRandom
from tianxia import figures, front_lines, journal, rules, team, world
from tianxia.content import ContentError, load_content, validate
from tianxia.encounter import EncounterResult
from tianxia.engine import Game
from tianxia.models import FrontLines

CONTENT_DIR = Path(__file__).parent.parent / "content"
BAND_KEYS = ["1", "2-3", "4+"]


@pytest.fixture
def real():
    c = load_content(CONTENT_DIR)
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    c.config.train_stat_chance = 0.0
    return c


@pytest.fixture
def on(real):
    real.config.season_one = True
    return real


def make(content, faction=None, name="甲"):
    game = Game.new(content, name, rng=random.Random(0))
    game.state.player.faction = faction
    return game


CHIP = re.compile(r'<span class="([^"]*\btx-chg\b[^"]*)">([^<]*)</span>')


def chips(html: str) -> list[tuple[set[str], str]]:
    """畫面上的數值標籤：（class 集合, 文字）。"""
    return [(set(cls.split()), text) for cls, text in CHIP.findall(html)]


def push(game, delta, trend="yingru"):
    """推一下大勢、照引擎寫紀錄的方式寫成一則；回傳「剛剛」卡片上的標籤。"""
    game._write("測試", rules.change_trend(game.state, game.content, trend, delta))
    return chips(game.latest_entry_html())


def tone(classes: set[str]) -> str:
    return "up" if "tx-up" in classes else "down" if "tx-down" in classes else "flat"


def _win():
    return mock.patch.object(
        team, "fight", return_value=EncounterResult(tier="大勝", margin=50, our_power=100, difficulty=15),
    )


# ── 句子：依變動的大小分三段，句子由哪一方佔上風決定主詞 ─────────────────

# S1 的內容表（docs/superpowers/specs/2026-10-05-檢定選項的心裡話.md 第四節），每一段三句；官軍、黃巾共用，只換陣營名
SMALL = ["稍佔上風", "略有斬獲", "小有進展"]
MEDIUM = ["步步進逼", "穩穩推進", "連連得手"]
LARGE = ["大舉推進", "勢如破竹", "長驅直入"]
GEJU_UP = ["豪強趁亂坐大", "豪強勢力漸長", "豪強乘勢而起"]
GEJU_DOWN = ["豪強勢頭受挫", "豪強收斂了些", "豪強聲勢漸消"]


def texts(chip_list) -> list[str]:
    return [text for _, text in chip_list]


@pytest.mark.parametrize("size, pool", [(1, SMALL), (2, MEDIUM), (3, MEDIUM), (4, LARGE), (9, LARGE)])
@pytest.mark.parametrize("sign, side", [(-1, "官軍"), (1, "黃巾")])
def test_the_chip_names_the_front_the_side_and_one_phrase_of_the_band(on, size, pool, sign, side):
    """戰況 0 是官軍穩控、100 是黃巾控制：往下是官軍佔了便宜，往上是黃巾。方向從內容來（陣營的 goals），
    陣營名寫在句子裡（front_lines.json 的 sides）；「戰線：陣營＋句子」，句子是那一段三句裡的一句。"""
    ((classes, text),) = push(make(on), sign * size)
    assert text in {f"潁川汝南：{side}{phrase}" for phrase in pool}


def test_each_front_is_named_by_itself(on):
    on.front_lines.generic = {"1": ["稍佔上風"], "2-3": ["步步進逼"], "4+": ["大舉推進"]}
    assert texts(push(make(on), -1, "nanyang")) == ["南陽：官軍稍佔上風"]
    assert texts(push(make(on), 1, "jizhou")) == ["冀州：黃巾稍佔上風"]


def test_two_pushes_on_one_front_merge_before_the_phrase_is_chosen(on):
    """−1 與 −2 在同一則紀錄裡合起來是 −3，落在 2–3 那一段（不是兩枚標籤、不是小的那一段）。"""
    game = make(on)
    game._write("測試", rules.change_trend(game.state, on, "yingru", -1) + rules.change_trend(game.state, on, "yingru", -2))
    (text,) = texts(chips(game.latest_entry_html()))
    assert text in {f"潁川汝南：官軍{phrase}" for phrase in MEDIUM}


def test_pushes_that_cancel_out_show_nothing(on):
    game = make(on)
    game._write("測試", rules.change_trend(game.state, on, "yingru", 2) + rules.change_trend(game.state, on, "yingru", -2))
    assert chips(game.latest_entry_html()) == []


def test_different_fronts_keep_their_own_chips(on):
    game = make(on)
    game._write("測試", rules.change_trend(game.state, on, "yingru", -1) + rules.change_trend(game.state, on, "nanyang", 4))
    first, second = texts(chips(game.latest_entry_html()))
    assert first in {f"潁川汝南：官軍{p}" for p in SMALL} and second in {f"南陽：黃巾{p}" for p in LARGE}


def test_the_same_entry_draws_the_same_phrase_every_time(on):
    """挑句只看那一則紀錄（時間與戰線），不看畫面重畫了幾次、也不動遊戲的亂數：重整、再開一個分頁都是同一句。"""
    game = make(on)
    state = game.rng.getstate()
    game._write("測試", rules.change_trend(game.state, on, "yingru", -2))
    first = chips(game.latest_entry_html())
    assert chips(game.latest_entry_html()) == first == chips(game.now_entry_html())
    assert chips(game.journal_html(0, 5)) == first
    assert game.rng.getstate() == state


# ── 割據 ───────────────────────────────────────────────────────


def test_geju_rising_and_falling_have_their_own_phrases_without_a_number_or_a_second_haoqiang(on):
    """句子裡已經有「豪強」，不再把陣營名接在前面（不是「豪強豪強趁亂坐大」）；前面也不冠戰線名。"""
    (up,) = texts(push(make(on), 3, "geju"))
    (down,) = texts(push(make(on), -2, "geju"))
    assert up in GEJU_UP and down in GEJU_DOWN
    assert up.count("豪強") == down.count("豪強") == 1 and "：" not in up + down


# ── 顏色：看的人站在哪一邊 ───────────────────────────────────────


@pytest.mark.parametrize("faction, toward_guan, toward_huang", [
    (None, "flat", "flat"),  # 散人：兩邊都不偏
    ("guan", "up", "down"),
    ("huang", "down", "up"),
    ("haoqiang", "flat", "flat"),  # 豪強靠亂局吃飯，不站戰線的任何一邊
])
def test_the_colour_follows_the_viewers_faction(on, faction, toward_guan, toward_huang):
    assert tone(push(make(on, faction), -1)[0][0]) == toward_guan
    assert tone(push(make(on, faction), 2)[0][0]) == toward_huang


@pytest.mark.parametrize("faction, rising, falling", [
    ("haoqiang", "up", "down"),  # 豪強坐大是自己的好事；勢頭受挫對豪強是壞事
    ("guan", "flat", "flat"),
    ("huang", "flat", "flat"),
    (None, "flat", "flat"),
])
def test_geju_is_good_news_only_for_haoqiang(on, faction, rising, falling):
    assert tone(push(make(on, faction), 2, "geju")[0][0]) == rising
    assert tone(push(make(on, faction), -1, "geju")[0][0]) == falling


def test_the_colour_is_decided_when_the_journal_is_drawn(on):
    """同一則紀錄，換了陣營（投靠之後）再畫就換了顏色；紀錄裡存的東西不帶任何一方的立場。"""
    game = make(on)
    game._write("測試", rules.change_trend(game.state, on, "yingru", -2))
    stored = list(game.state.journal[0].changes)
    assert tone(chips(game.latest_entry_html())[0][0]) == "flat"
    game.state.player.faction = "guan"
    assert tone(chips(game.latest_entry_html())[0][0]) == "up"
    game.state.player.faction = "huang"
    assert tone(chips(game.latest_entry_html())[0][0]) == "down"
    assert game.state.journal[0].changes == stored


# ── 數字不外露 ─────────────────────────────────────────────────


@pytest.mark.parametrize("faction", [None, "guan", "huang", "haoqiang"])
def test_no_digit_reaches_the_player_on_any_screen_that_shows_the_line(on, faction):
    game = make(on, faction)
    for trend, delta in (("yingru", -1), ("yingru", 3), ("nanyang", 6), ("jizhou", -2), ("geju", 4), ("geju", -1)):
        game._write("測試", rules.change_trend(game.state, on, trend, delta))
    screens = [game.latest_entry_html(), game.now_entry_html(), game.journal_html(0, 20)]
    for html in screens:
        assert front_lines.MARK not in html
        shown = texts(chips(html))
        assert shown and not any(re.search(r"\d", t) for t in shown), shown


def test_no_digit_in_the_messages_an_action_hands_back(on):
    """管理者推戰況的回話（工具列的提示）與 GameState.log 也是玩家看得到的地方。"""
    admin = make(on, None, "Rayal")
    msgs = admin.admin_push_trend("yingru", -3)
    assert len(msgs) == 1 and msgs[0] in {f"潁川汝南：官軍{phrase}" for phrase in MEDIUM}
    assert not any(front_lines.MARK in m or re.search(r"\d", m) for m in msgs + admin.state.log)
    assert texts(chips(admin.latest_entry_html())) == msgs  # 回話與「剛剛」卡片上的標籤是同一句
    (msg,) = admin.admin_set_trend("nanyang", 60)  # 35 → 60，一次推 25
    assert msg in {f"南陽：黃巾{phrase}" for phrase in LARGE}


def test_the_stored_entry_keeps_a_machine_readable_change_so_merging_works(on):
    game = make(on)
    game._write("測試", rules.change_trend(game.state, on, "yingru", -1))
    assert game.state.journal[0].changes == [front_lines.mark("yingru", -1)]
    assert front_lines.unmark(front_lines.mark("yingru", -1)) == ("yingru", -1)
    assert front_lines.unmark("銀兩 -5") is None


def test_a_chip_the_renderer_cannot_draw_is_dropped_rather_than_shown_raw(on):
    """沒有交渲染函式的呼叫端（直接畫紀錄）：機器可讀的寫法一律不畫，也不外露。"""
    entry = journal.JournalEntry(time=1.0, title="測試", changes=["銀兩 +5", front_lines.mark("yingru", -2)])
    html = journal.card_html(entry)
    assert "銀兩 +5" in html and front_lines.MARK not in html and "yingru" not in html


# ── 戰鬥卡片與其他走過同一條路的地方 ─────────────────────────────────


def test_a_win_that_moves_the_front_shows_the_chip_under_the_battle_card(on):
    """遊歷打贏：戰鬥卡片的「獲得與損失」是不上色的字，戰況改放在卡片底下的補充，用標籤畫、照看的人上色；
    戰報（BattleRecord）不收機器可讀的寫法。"""
    game = make(on, "guan")
    game.state.player.location = "changshe"
    game._draft = journal.Draft("遊歷・長社")
    with _win():
        msgs = game._squad_encounter("louluo")
    journal.add_entry(game.state, game._draft.entry(game.state.world.time, msgs))
    game._draft = None
    record = game.state.battles[0]
    assert not any(front_lines.MARK in text for text in (*record.changes, *record.notes))
    assert not any(front_lines.MARK in text for text in (game.battle_card() or "",))
    game.state.battle_card = record.id
    extra = [(tone(c), t) for c, t in chips(game.battle_extra_html()) if "：" in t]
    assert [kind for kind, _ in extra] == ["up"]
    assert extra[0][1] in {f"潁川汝南：官軍{phrase}" for phrase in SMALL}


def test_the_home_page_payload_carries_the_chip_for_the_logged_in_viewer(on):
    game = make(on, "huang")
    game._write("測試", rules.change_trend(game.state, on, "yingru", -1))
    view = server.main_view(game)
    ((classes, text),) = chips(view["now"])
    assert tone(classes) == "down" and text in {f"潁川汝南：官軍{phrase}" for phrase in SMALL}
    assert chips(view["latest"]) == chips(view["now"])


# ── 開關關著與背景推動 ─────────────────────────────────────────


def test_with_the_switch_off_the_old_wording_stays_exactly(real):
    game = make(real, "guan")
    assert rules.change_trend(game.state, real, "huangjin", -2) == ["（黃巾聲勢 -2）"]
    assert rules.change_trend(game.state, real, "huangjin", 5) == ["（黃巾聲勢 +5）"]
    admin = make(real, None, "Rayal")
    assert admin.admin_push_trend("huangjin", 5) == ["（黃巾聲勢 +5）"]
    assert not any(front_lines.MARK in m for m in admin.state.log)


def test_background_pushes_stay_silent(on):
    """大勢人物每曆時的推動（figures.tick）、割據的自然漲落（geju_tick）都不回訊息、不寫紀錄（同虛擬玩家）。"""
    game = make(on)
    game.state.world.trends["yingru"] = 50  # 亂局，割據會漲
    journal_before = [e.model_dump() for e in game.state.journal]
    log_before = list(game.state.log)
    for _ in range(48):
        rules.geju_tick(game.state, on, 1)
    figures.tick(game.state, on, 24)
    assert game.state.world.trends["geju"] > 10  # 真的推了，只是沒出聲
    assert [e.model_dump() for e in game.state.journal] == journal_before and game.state.log == log_before
    msgs = world.sim_tick(game.state, on, 3, FixedRandom(0.0))
    assert not any(front_lines.MARK in m for m in msgs)
    msgs = game.advance(24 * 3600)
    assert not any(front_lines.MARK in m for m in msgs)
    assert all(front_lines.MARK not in c for e in game.state.journal for c in e.changes)


def test_with_the_switch_off_sim_tick_still_says_nothing(real):
    game = make(real)
    msgs = world.sim_tick(game.state, real, 5, FixedRandom(0.0))
    assert not any("黃巾聲勢" in m for m in msgs)


# ── 挑句：確定性，不動引擎的亂數 ─────────────────────────────────────


def test_variants_are_picked_by_hash_and_never_touch_the_rng(on):
    on.front_lines.generic["1"] = [f"句{i}" for i in range(6)]
    on.front_lines.geju = {"up": [f"豪強起{i}" for i in range(6)], "down": ["豪強落"]}
    game = make(on)
    state = game.rng.getstate()
    game._write("測試", rules.change_trend(game.state, on, "yingru", -1) + rules.change_trend(game.state, on, "geju", 1))
    first = chips(game.latest_entry_html())
    assert chips(game.latest_entry_html()) == first  # 同一則永遠同一句
    seen, seen_geju = set(), set()
    for n in range(40):
        game.state.journal[0] = game.state.journal[0].model_copy(update={"time": float(n * 977)})
        front, geju = texts(chips(game.latest_entry_html()))
        seen.add(front)
        seen_geju.add(geju)
    assert len(seen) > 1 and all(s.startswith("潁川汝南：官軍句") for s in seen)
    assert len(seen_geju) > 1 and all(s.startswith("豪強起") for s in seen_geju)
    assert game.rng.getstate() == state


def test_a_side_with_its_own_phrase_beats_the_generic_one_and_the_generic_is_the_fallback(on):
    on.front_lines.generic = {"1": ["稍佔上風"], "2-3": ["步步進逼"], "4+": ["大舉推進"]}
    on.front_lines.by_side = {"huang": {"4+": ["旌旗漫天"]}}
    game = make(on)
    assert texts(push(game, 5)) == ["潁川汝南：黃巾旌旗漫天"]
    assert texts(push(game, 1)) == ["潁川汝南：黃巾稍佔上風"]  # 這一段他沒寫，退回通用
    assert texts(push(game, -5)) == ["潁川汝南：官軍大舉推進"]  # 官軍沒寫


def test_the_side_name_in_the_chip_comes_from_the_table_and_falls_back_to_the_faction_name(on):
    """句子裡的陣營名寫在 front_lines.json 的 sides（黃巾軍的簡稱「黃巾」）；沒寫的陣營用劇本裡的陣營名。"""
    on.front_lines.generic = {"1": ["稍佔上風"], "2-3": ["步步進逼"], "4+": ["大舉推進"]}
    on.front_lines.sides = {"guan": "朝廷大軍"}
    game = make(on)
    assert texts(push(game, -1)) == ["潁川汝南：朝廷大軍稍佔上風"]
    assert texts(push(game, 1)) == ["潁川汝南：黃巾軍稍佔上風"]


# ── 內容檔：模型、載入、驗證 ───────────────────────────────────────────


def test_the_real_content_ships_the_s1_phrase_tables(real):
    """每一段三句、兩個陣營共用一份（陣營名另外寫在 sides）；「推進一程」因為有「一」被 S1 換掉了。"""
    lines = real.front_lines
    assert lines.sides == {"guan": "官軍", "huang": "黃巾"}
    assert lines.generic == {"1": SMALL, "2-3": MEDIUM, "4+": LARGE}
    assert lines.by_side == {}
    assert lines.geju == {"up": GEJU_UP, "down": GEJU_DOWN}
    assert "推進一程" not in json.dumps(lines.model_dump(), ensure_ascii=False)


def test_the_bands_are_one_two_to_three_and_four_up():
    assert [front_lines.band_of(n) for n in (1, 2, 3, 4, 5, 40)] == ["1", "2-3", "2-3", "4+", "4+", "4+"]
    assert front_lines.band_of(-3) == "2-3"  # 看的是變動的大小


def copy_fixture(tmp_path) -> Path:
    dest = tmp_path / "content"
    shutil.copytree(FIXTURE, dest)
    return dest


def edit(root: Path, fn) -> None:
    path = root / "front_lines.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    fn(data)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_the_fixture_phrases_load(tmp_path):
    assert set(load_content(copy_fixture(tmp_path)).front_lines.generic) == set(BAND_KEYS)


def test_a_missing_file_is_a_content_error_that_names_the_file(tmp_path):
    root = copy_fixture(tmp_path)
    (root / "front_lines.json").unlink()
    with pytest.raises(ContentError, match="front_lines.json"):
        load_content(root)


@pytest.mark.parametrize("where, change, match", [
    ("generic 缺一段", lambda d: d["generic"].pop("2-3"), "2-3"),
    ("generic 多了不認得的段", lambda d: d["generic"].update({"9+": ["很大"]}), "9\\+"),
    ("generic 空串列", lambda d: d["generic"].update({"1": []}), "不能是空的"),
    ("generic 空字串", lambda d: d["generic"].update({"1": ["稍佔上風", "  "]}), "空白"),
    ("generic 寫了數字", lambda d: d["generic"].update({"1": ["佔了 1 點便宜"]}), "數字"),
    ("generic 寫了全形數字", lambda d: d["generic"].update({"4+": ["推進２０點"]}), "數字"),
    ("generic 寫了百分比", lambda d: d["generic"].update({"4+": ["大舉推進一成%"]}), "數字"),
    ("generic 簡體字", lambda d: d["generic"].update({"1": ["稍占上风"]}), "繁體"),
    ("by_side 寫了數字", lambda d: d["by_side"].update({"guan": {"1": ["稍佔 1 分"]}}), "數字"),
    ("by_side 空字串", lambda d: d["by_side"].update({"huang": {"2-3": [""]}}), "空白"),
    ("by_side 不認得的段", lambda d: d["by_side"].update({"guan": {"7": ["x"]}}), "guan.*7"),
    ("by_side 不存在的陣營", lambda d: d["by_side"].update({"ghost": {"1": ["鬼影"]}}), "ghost"),
    ("sides 不存在的陣營", lambda d: d["sides"].update({"ghost": "鬼"}), "ghost"),
    ("sides 空的陣營名", lambda d: d["sides"].update({"guan": " "}), "空白"),
    ("sides 陣營名寫了數字", lambda d: d["sides"].update({"huang": "黃巾2軍"}), "數字"),
    ("sides 簡體字", lambda d: d["sides"].update({"guan": "官军"}), "繁體"),
    ("geju 缺 down", lambda d: d["geju"].pop("down"), "down"),
    ("geju 多了別的鍵", lambda d: d["geju"].update({"sideways": ["橫著走"]}), "sideways"),
    ("geju 寫了數字", lambda d: d["geju"].update({"up": ["豪強坐大 3 成"]}), "數字"),
    ("geju 空串列", lambda d: d["geju"].update({"down": []}), "不能是空的"),
])
def test_validation_rejects_bad_phrases(where, change, match):
    content = load_content(CONTENT_DIR)
    lines = json.loads(content.front_lines.model_dump_json())
    change(lines)
    content.front_lines = FrontLines(**lines)
    with pytest.raises(ContentError, match=match):
        validate(content)


def test_chinese_numerals_are_not_digits_to_the_number_check():
    """只攔阿拉伯數字（半形、全形）與百分號；一、十、半這類字在成語裡很自然（略勝一籌、十拿九穩），不攔。"""
    content = load_content(CONTENT_DIR)
    content.front_lines.generic["1"] = ["略勝一籌", "半步先機"]
    content.check_lines.generic["80+"] = ["十拿九穩"]
    validate(content)


def test_a_malformed_hand_edit_is_a_content_error_that_names_the_file(tmp_path):
    root = copy_fixture(tmp_path)
    (root / "front_lines.json").write_text("{ nope", encoding="utf-8")
    with pytest.raises(ContentError, match="front_lines.json"):
        load_content(root)
    root = copy_fixture(tmp_path / "again")
    edit(root, lambda d: d.update(surprise=1))
    with pytest.raises(ContentError, match="front_lines.json"):
        load_content(root)
