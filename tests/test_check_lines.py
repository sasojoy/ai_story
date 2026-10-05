"""檢定選項的「心裡話」（週末試玩 A，推翻 9/29 交鋒統一的「不顯示成功率」）：
選項標籤寫「（出手者・屬性 數值：一句心裡話）」，不寫成功率與難度；心裡話照成功率分五段，
用的是擲骰那一個函式算出來的成功率，所以標籤與擲骰不會對不起來。"""
import json
import shutil
from pathlib import Path

import pytest

from conftest import FIXTURE, FixedRandom
from tianxia import check_lines
from tianxia.content import ContentError, load_content
from tianxia.events import choice_label
from tianxia.models import Check, CheckLines, Choice
from tianxia.rules import check_chance, check_outlook, roll_check

REAL_CONTENT = Path(__file__).parent.parent / "content"
BUCKETS = ["80+", "60-79", "40-59", "20-39", "0-19"]


def one_line_each() -> CheckLines:
    return CheckLines(generic={b: [f"通用{b}"] for b in BUCKETS})


def self_choice(stat: str, difficulty: int) -> Choice:
    return Choice(text="試試", check=Check(stat=stat, difficulty=difficulty, by="self"))


# ── 五段分法 ──────────────────────────────────────────────


@pytest.mark.parametrize("chance, bucket", [
    (0.95, "80+"), (0.80, "80+"), (0.7999, "60-79"), (0.60, "60-79"), (0.5999, "40-59"),
    (0.40, "40-59"), (0.3999, "20-39"), (0.20, "20-39"), (0.1999, "0-19"), (0.05, "0-19"),
])
def test_the_five_buckets_and_their_boundaries(chance, bucket):
    assert check_lines.bucket_of(chance) == bucket


def test_a_rate_that_floating_point_leaves_a_hair_under_a_boundary_still_counts_as_on_it(state, content, world):
    """臂力 5 對難度 8：用浮點數算出 0.19999999999999996，它是整整 20%，不是 20% 以下。"""
    content.check_lines = one_line_each()
    choice = self_choice("str", 8)
    assert check_chance(choice.check, state, content, world) < 0.2
    assert choice_label(choice, state, content, world) == "試試（本人・臂力 5：通用20-39）"


@pytest.mark.parametrize("difficulty, bucket", [
    (2, "80+"), (3, "60-79"), (4, "60-79"), (5, "40-59"), (6, "40-59"), (7, "20-39"), (8, "20-39"), (9, "0-19"),
])
def test_the_label_line_follows_the_real_rate_of_the_roll(state, content, world, difficulty, bucket):
    content.check_lines = one_line_each()
    label = choice_label(self_choice("str", difficulty), state, content, world)
    assert label == f"試試（本人・臂力 5：通用{bucket}）"


# ── 誰出手、哪個屬性、多少 ─────────────────────────────────


def test_a_self_check_names_the_player_the_stat_and_its_value(state, content, world):
    insight = content.events["insight"]  # 根骨 5、本人檢定、難度 5：五成
    label = choice_label(insight.choices[0], state, content, world)
    line = content.check_lines.generic["40-59"][0]
    assert label == f"運氣衝關（本人・根骨 5：{line}）"


def test_a_team_check_shows_the_companion_who_would_act_and_his_own_value(state, content, world):
    drunk = content.events["drunk"]  # 臂力檢定、隊伍出手：韓鐵（臂力 6）比本人（5）高
    assert choice_label(drunk.choices[0], state, content, world).startswith("逼問（本人・臂力 5：")
    state.player.team.append("mate")
    label = choice_label(drunk.choices[0], state, content, world)
    assert label == f"逼問（韓鐵・臂力 6：{content.check_lines.generic['60-79'][0]}）"  # 難度 5，六成
    assert "%" not in label and "出手" not in label


def test_the_value_shown_is_the_value_of_the_actor_at_his_level(state, content, world):
    """同伴升級後屬性會長（成長 × (等級 − 1)）：標籤寫的是出手者「現在」的數值。"""
    state.player.team.append("mate")
    world.update_companion("mate", lambda p: setattr(p, "level", 3))  # 臂力 6 + 0.3 × 2 = 6.6
    label = choice_label(Choice(text="試", check=Check(stat="str", difficulty=5)), state, content, world)
    assert label.startswith("試（韓鐵・臂力 6.6：")


def test_the_label_and_the_roll_share_one_function(state, content, world):
    """標籤的出手者、數值與擲骰用的成功率，都出自 check_outlook 這一處。"""
    state.player.team.append("mate")
    check = Check(stat="str", difficulty=7)
    outlook = check_outlook(check, state, content, world)
    assert (outlook.actor, outlook.value) == ("mate", 6.0)
    assert outlook.chance == pytest.approx(0.4)
    assert check_chance(check, state, content, world) == outlook.chance
    assert roll_check(check, state, content, world, FixedRandom(outlook.chance - 0.001))
    assert not roll_check(check, state, content, world, FixedRandom(outlook.chance + 0.001))


# ── 沒有檢定的選項照舊 ──────────────────────────────────────


def test_choices_without_a_check_keep_their_text(state, content, world):
    drunk = content.events["drunk"]
    assert choice_label(drunk.choices[1], state, content, world) == "摸走鐵牌"


# ── 挑哪一句 ──────────────────────────────────────────────


def test_a_stat_line_beats_the_generic_one_and_the_generic_is_the_fallback(state, content, world):
    content.check_lines = CheckLines(
        generic={b: [f"通用{b}"] for b in BUCKETS},
        by_stat={"str": {"20-39": ["這弓八成拉不開"]}},
    )
    bow = self_choice("str", 7)  # 臂力 5、難度 7：三成
    assert choice_label(bow, state, content, world) == "試試（本人・臂力 5：這弓八成拉不開）"
    assert choice_label(self_choice("str", 5), state, content, world) == "試試（本人・臂力 5：通用40-59）"  # 臂力沒寫這一段
    assert choice_label(self_choice("agi", 7), state, content, world) == "試試（本人・身法 5：通用20-39）"  # 身法沒寫


def test_a_choice_with_several_lines_always_shows_the_same_one(state, content, world):
    lines = [f"句{i}" for i in range(8)]
    content.check_lines = CheckLines(generic={**{b: ["x"] for b in BUCKETS}, "40-59": lines})
    choice = self_choice("con", 5)
    shown = {choice_label(choice, state, content, world, key="event_a#0") for _ in range(30)}
    assert len(shown) == 1


def test_different_choices_spread_over_the_lines(state, content, world):
    lines = [f"句{i}" for i in range(4)]
    content.check_lines = CheckLines(generic={**{b: ["x"] for b in BUCKETS}, "40-59": lines})
    choice = self_choice("con", 5)
    shown = {choice_label(choice, state, content, world, key=f"event_{n}#{i}") for n in range(20) for i in range(3)}
    assert len(shown) > 1  # 不是全都挑同一句


def test_picking_a_line_does_not_touch_the_game_rng(game):
    game.content.check_lines = CheckLines(generic={**{b: ["x", "y", "z"] for b in BUCKETS}})
    game.state.pending_event = "insight"
    before = game.rng.getstate()
    first = [o.label for o in game.options()]
    again = [o.label for o in game.options()]
    assert first == again
    assert game.rng.getstate() == before


def test_the_game_option_label_uses_the_event_and_choice_index_and_keeps_its_id(game):
    game.state.pending_event = "drunk"
    options = game.options()
    assert [o.id for o in options] == ["choice:0", "choice:1"]
    assert options[0].label == f"逼問（本人・臂力 5：{game.content.check_lines.generic['40-59'][0]}）"
    assert options[1].label == "摸走鐵牌"


# ── 內容檔的驗證 ──────────────────────────────────────────


def copy_fixture(tmp_path) -> Path:
    dest = tmp_path / "content"
    shutil.copytree(FIXTURE, dest)
    return dest


def edit_lines(root: Path, fn) -> None:
    path = root / "check_lines.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    fn(data)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_the_fixture_lines_load(content):
    assert set(content.check_lines.generic) == set(BUCKETS)


def test_a_missing_bucket_is_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_lines(root, lambda d: d["generic"].pop("20-39"))
    with pytest.raises(ContentError, match="20-39"):
        load_content(root)


def test_an_unknown_bucket_is_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_lines(root, lambda d: d["generic"].update({"90+": ["很穩"]}))
    with pytest.raises(ContentError, match="90\\+"):
        load_content(root)


def test_a_per_stat_list_for_an_unknown_stat_is_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_lines(root, lambda d: d.update(by_stat={"luck": {"80+": ["運氣好"]}}))
    with pytest.raises(ContentError, match="luck"):
        load_content(root)


def test_a_per_stat_list_for_an_unknown_bucket_is_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_lines(root, lambda d: d.update(by_stat={"str": {"50": ["半半"]}}))
    with pytest.raises(ContentError, match="str.*50"):
        load_content(root)


def test_an_empty_or_blank_list_is_rejected(tmp_path):
    root = copy_fixture(tmp_path / "a")
    edit_lines(root, lambda d: d["generic"].update({"80+": []}))
    with pytest.raises(ContentError, match="80\\+"):
        load_content(root)
    root = copy_fixture(tmp_path / "b")
    edit_lines(root, lambda d: d.update(by_stat={"wis": {"0-19": ["  "]}}))
    with pytest.raises(ContentError, match="wis"):
        load_content(root)


def test_a_line_that_gives_the_number_away_is_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_lines(root, lambda d: d["generic"].update({"60-79": ["約有 70% 把握"]}))
    with pytest.raises(ContentError, match="數字"):
        load_content(root)


def test_a_line_in_simplified_characters_is_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_lines(root, lambda d: d["generic"].update({"0-19": ["几乎没指望"]}))
    with pytest.raises(ContentError, match="繁體"):
        load_content(root)


# ── 正式內容 ──────────────────────────────────────────────


def test_the_real_content_has_a_line_for_every_bucket():
    content = load_content(REAL_CONTENT)
    assert set(content.check_lines.generic) == set(BUCKETS)
    assert all(content.check_lines.generic[b] for b in BUCKETS)


def test_the_real_content_has_s1s_forty_five_inner_voice_lines():
    """S1 的內容表（docs/superpowers/specs/2026-10-05-檢定選項的心裡話.md 第一、二節）：四項屬性各五段、每段兩句（40 句），
    加上不認得的屬性用的通用五句，共 45 句；通用的五句取代開發先放的（那幾句有「十」「九」「半」）。"""
    lines = load_content(REAL_CONTENT).check_lines
    assert lines.generic == {
        "80+": ["易如反掌"], "60-79": ["應該辦得到"], "40-59": ["成不成難說"], "20-39": ["恐怕不太容易"], "0-19": ["幾乎沒有指望"],
    }
    assert set(lines.by_stat) == {"str", "agi", "con", "wis"}
    for stat, buckets in lines.by_stat.items():
        assert set(buckets) == set(BUCKETS), stat
        assert all(len(pool) == 2 and len(set(pool)) == 2 for pool in buckets.values()), stat
    assert sum(len(p) for b in lines.by_stat.values() for p in b.values()) + sum(len(p) for p in lines.generic.values()) == 45
    assert lines.by_stat["str"]["20-39"] == ["這股力氣怕是不夠", "力有未逮，得碰運氣"]  # 老弓那一檔
    assert lines.by_stat["wis"]["40-59"] == ["似懂非懂，說不準", "得靠靈光乍現"]


def test_a_real_stat_line_shows_up_in_the_label_and_an_unknown_stat_falls_back_to_the_generic_one():
    from tianxia.sqlite_world import open_world
    from tianxia.state import new_game_state

    content = load_content(REAL_CONTENT)
    state, world = new_game_state(content, "沈浪"), open_world()
    label = choice_label(self_choice("agi", 7), state, content, world, key="事件#0")
    assert label.startswith("試試（本人・身法 5：") and label.removeprefix("試試（本人・身法 5：").removesuffix("）") in (
        content.check_lines.by_stat["agi"]["20-39"]  # 身法 5 對難度 7，三成
    )
    content.check_lines.by_stat.pop("agi")
    assert choice_label(self_choice("agi", 7), state, content, world) == "試試（本人・身法 5：恐怕不太容易）"


def test_the_old_bow_shows_a_twenty_to_thirty_nine_line_to_a_fresh_character():
    """去拉牆上那張老弓：臂力 5 對難度 7，成功率三成，落在 20–39 那一段。"""
    from tianxia.sqlite_world import open_world
    from tianxia.state import new_game_state

    content = load_content(REAL_CONTENT)
    state = new_game_state(content, "沈浪")
    world = open_world()
    event = content.events["yc_ac_archery"]
    index, bow = next((i, c) for i, c in enumerate(event.choices) if "老弓" in c.text)
    assert (bow.check.stat, bow.check.difficulty) == ("str", 7)
    label = choice_label(bow, state, content, world, key=f"{event.id}#{index}")
    pool = content.check_lines.by_stat.get("str", {}).get("20-39") or content.check_lines.generic["20-39"]
    assert any(label == f"{bow.text}（本人・臂力 5：{line}）" for line in pool), label


# ── 檔案本身壞掉時，錯誤要指到這個檔 ───────────────────────


def test_a_missing_file_is_a_content_error_that_names_the_file(tmp_path):
    root = copy_fixture(tmp_path)
    (root / "check_lines.json").unlink()
    with pytest.raises(ContentError, match="check_lines.json"):
        load_content(root)


def test_a_malformed_hand_edit_is_a_content_error_that_names_the_file(tmp_path):
    root = copy_fixture(tmp_path / "a")
    edit_lines(root, lambda d: d.update(by_stat={"str": ["不是各段的對照"]}))  # 欄位型別不對：pydantic 會擋
    with pytest.raises(ContentError, match="check_lines.json"):
        load_content(root)
    root = copy_fixture(tmp_path / "b")
    edit_lines(root, lambda d: d.update(by_strength={}))  # 拼錯的欄位
    with pytest.raises(ContentError, match="check_lines.json"):
        load_content(root)
    root = copy_fixture(tmp_path / "c")
    (root / "check_lines.json").write_text('{"generic": {"80+": ["穩"],', encoding="utf-8")  # 漏了括號：不是合法的 JSON
    with pytest.raises(ContentError, match="check_lines.json"):
        load_content(root)
