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
    board = {"武學": [("強者", "九陰白骨爪", "絕學", 50.0)], "內功": []}
    lines = leaderboard.format_lines(board)
    assert "　1. 強者・【九陰白骨爪】（絕學，威力 50.0）" in lines
