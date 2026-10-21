from tianxia import leaderboard
from tianxia.martial_arts import generate_from_name
from tianxia.characters import open_characters
from tianxia.state import GameState, new_game_state


def _player(content, name: str, wugong_id: str | None = None, wugong_level: int = 1) -> GameState:
    state = new_game_state(content, name)
    state.player.member.wugong_id = wugong_id
    state.player.member.wugong_level = wugong_level
    return state


def test_compute_leaderboard_is_empty_without_any_saves(content, world):
    board = leaderboard.compute_leaderboard(content, world)
    assert board == {"內功": [], "武學": []}


def test_compute_leaderboard_ranks_players_by_power_and_resolves_created_skill_names(content, world):
    world.claim_skill_name(generate_from_name("九陰白骨爪", "武學", "九陰白骨爪"))
    strong = _player(content, "強者", wugong_id="九陰白骨爪", wugong_level=10)
    weak = _player(content, "弱者", wugong_id="九陰白骨爪", wugong_level=1)
    open_characters().save(strong)
    open_characters().save(weak)
    board = leaderboard.compute_leaderboard(content, world)
    names = [row[0] for row in board["武學"]]
    assert names == ["強者", "弱者"]  # 熟練度第十成排在第一成前面
    assert board["武學"][0][1] == "九陰白骨爪"


def test_compute_leaderboard_skips_players_with_no_skill_learned(content, world):
    open_characters().save(_player(content, "白丁"))
    board = leaderboard.compute_leaderboard(content, world)
    assert board == {"內功": [], "武學": []}


def test_compute_leaderboard_skips_unreadable_saves(content, world):
    characters = open_characters()
    with characters.db.transaction() as conn:
        conn.execute("INSERT INTO characters (key, name, is_bot, faction, data) VALUES ('壞', '壞', 0, NULL, 'not json')")
    characters.save(_player(content, "正常玩家", wugong_id="fist", wugong_level=3))
    board = leaderboard.compute_leaderboard(content, world)
    assert [row[0] for row in board["武學"]] == ["正常玩家"]


def test_leaderboard_skips_characters_from_earlier_seasons(content, world):
    """這一季沒上線的人，存檔裡還是上一季的武學，不能混進這一季的榜（換季重來的缺口之一）。"""
    world.seed_first_season(content)
    world.mutate_season(lambda season: setattr(season, "ended", True))
    assert world.next_season(content, now=0.0) and world.get_season_number() == 2
    stale = _player(content, "上一季的人", wugong_id="fist", wugong_level=10)
    stale.player.season_number = 1
    current = _player(content, "這一季的人", wugong_id="fist", wugong_level=1)
    current.player.season_number = 2
    open_characters().save(stale)
    open_characters().save(current)
    board = leaderboard.compute_leaderboard(content, world)
    assert [row[0] for row in board["武學"]] == ["這一季的人"]


def test_compute_leaderboard_caps_at_top_n(content, world):
    for i in range(leaderboard.TOP_N + 5):
        open_characters().save(_player(content, f"玩家{i}", wugong_id="fist", wugong_level=1 + i % 10))
    board = leaderboard.compute_leaderboard(content, world)
    assert len(board["武學"]) == leaderboard.TOP_N


def test_format_lines_shows_a_placeholder_when_nobody_has_a_skill():
    lines = leaderboard.format_lines({"內功": [], "武學": []})
    assert lines == ["【天下武學榜】", "　（尚無人留名）", "【內功榜】", "　（尚無人留名）"]


def test_format_lines_shows_ranked_entries_with_quality_and_power():
    board = {"武學": [("強者", "九陰白骨爪", "絕學", 50.0, 120)], "內功": []}
    lines = leaderboard.format_lines(board)
    assert "　1. 強者・【九陰白骨爪】（絕學，評 120，威力 50.0）" in lines


def test_the_board_shows_each_players_own_quality_and_power(content, world):
    """審查裁示 F11：榜上是玩家自己修練到的品質與威力，不是全服登記的那一份。"""
    from tianxia import martial_arts

    art = generate_from_name("旋風腿", "武學", "旋風腿", weights={"下品": 100, "中品": 0, "上品": 0, "絕學": 0})
    world.claim_skill_name(art)
    plain = _player(content, "平凡", wugong_id="旋風腿", wugong_level=5)
    trained = _player(content, "苦修", wugong_id="旋風腿", wugong_level=5)
    trained.player.art_quality["旋風腿"] = "上品"
    open_characters().save(plain)
    open_characters().save(trained)
    rows = {row[0]: row for row in leaderboard.compute_leaderboard(content, world)["武學"]}
    assert rows["平凡"][2] == "下品" and rows["苦修"][2] == "上品"
    assert rows["平凡"][3] == martial_arts.power_at(art, 5)
    assert rows["苦修"][3] == martial_arts.power_at(martial_arts.with_quality(art, "上品"), 5) > rows["平凡"][3]



def test_the_arts_board_ranks_by_score_before_power(content, world):
    """Joy 2026-10-20「武學榜高的在上面」：評分高的排前面，就算威力低一些；評分一樣高才看威力。"""
    from tianxia.state import InsightFx

    art = generate_from_name("旋風腿", "武學", "旋風腿", weights={"下品": 0, "中品": 0, "上品": 100, "絕學": 0})
    world.claim_skill_name(art)
    skilled = _player(content, "巧手", wugong_id="旋風腿", wugong_level=2)
    skilled.player.art_quality["旋風腿"] = "上品"
    skilled.player.insights.append("feng")
    skilled.player.insight_fx["feng"] = InsightFx(quality="上品", general={"快": 3})
    skilled.player.art_slots["旋風腿"] = ["feng", None, None, None]
    brute = _player(content, "苦練", wugong_id="旋風腿", wugong_level=10)
    brute.player.art_quality["旋風腿"] = "上品"
    open_characters().save(skilled)
    open_characters().save(brute)
    rows = leaderboard.compute_leaderboard(content, world)["武學"]
    assert [r[0] for r in rows] == ["巧手", "苦練"]
    assert rows[0][4] > rows[1][4] == 0 and rows[0][3] < rows[1][3]
    sub = next(b for b in leaderboard.view({"武學": rows}) if b["id"] == "武學")["rows"][0]["sub"]
    assert sub.startswith("上品・評 ") and "威力" in sub

# ── 善人、惡人、名人、宗師榜（企劃者 2026-10-14）──


def _registered(world, name: str, creator: str, co: str | None = None):
    art = generate_from_name(name, "武學", name)
    art.creator, art.co_creator = creator, co
    world.claim_recipe(f"融|{name}", art)


def test_stat_boards_rank_by_good_evil_and_fame_and_leave_out_zero(content, world):
    a, b, c = (_player(content, n) for n in ("甲", "乙", "丙"))
    a.player.stats.update(good=30, evil=0, fame=5)
    b.player.stats.update(good=12, evil=40, fame=5)
    c.player.stats.update(good=0, evil=3, fame=0)
    for s in (a, b, c):
        open_characters().save(s)
    board = leaderboard.compute_boards(content, world)
    assert [r[0] for r in board["善人"]] == ["甲", "乙"]
    assert [r[0] for r in board["惡人"]] == ["乙", "丙"]
    assert [r[0] for r in board["名人"]] == ["乙", "甲"]  # 同分照名號排
    assert board["善人"][0][2] == "善名 30"


def test_season_firsts_count_arts_and_insights_and_both_discussion_partners(content, world):
    from tianxia.martial_arts import Insight

    _registered(world, "甲一", "甲")
    _registered(world, "共二", "甲", co="乙")
    world.claim_insight_recipe("合|x", Insight(id="雲意", name="雲意", attribute="快", creator="乙"))
    assert world.season_firsts() == {"甲": 2, "乙": 2}


def test_master_board_ranks_mastered_arts_first_then_firsts(content, world):
    _registered(world, "甲一", "甲")
    _registered(world, "甲二", "甲")
    many = _player(content, "甲")  # 首創兩樣、沒有絕學
    master = _player(content, "丁", wugong_id="fist")
    master.player.art_quality["fist"] = "絕學"
    nobody = _player(content, "戊")
    for s in (many, master, nobody):
        open_characters().save(s)
    rows = leaderboard.compute_boards(content, world)["宗師"]
    assert [r[0] for r in rows] == ["丁", "甲"]
    assert rows[0][2] == "絕學 1 門・首創 0 樣" and rows[1][2] == "絕學 0 門・首創 2 樣"


def test_view_marks_you_and_says_your_rank_below_the_top(content, world):
    for i in range(leaderboard.TOP_N + 2):
        s = _player(content, f"人{i:02d}")
        s.player.stats["fame"] = 100 - i
        open_characters().save(s)
    full = leaderboard.compute_boards(content, world, top=None)
    boards = {b["id"]: b for b in leaderboard.view(full, me="人11")}
    fame = boards["名人"]
    assert len(fame["rows"]) == leaderboard.TOP_N and fame["mine"] == {"rank": 12, "text": "名望 89"}
    top = {b["id"]: b for b in leaderboard.view(full, me="人00")}["名人"]
    assert top["rows"][0]["you"] and "mine" not in top
    assert [b["title"] for b in leaderboard.view(full)][:4] == ["善人榜", "惡人榜", "名人榜", "宗師榜"]


def test_chronicle_lines_write_the_top_three_of_each_board_that_has_anyone():
    board = {
        "善人": [("甲", (30,), "善名 30"), ("乙", (20,), "善名 20"), ("丙", (10,), "善名 10"), ("丁", (5,), "善名 5")],
        "惡人": [],
        "武學": [("強者", "長拳", "上品", 50.0, 64)],
    }
    assert leaderboard.chronicle_lines(board, 3) == [
        "第 3 季善人榜：甲（善名 30）、乙（善名 20）、丙（善名 10）",
        "第 3 季天下武學榜：強者【長拳】（上品，評 64，威力 50.0）",
    ]
