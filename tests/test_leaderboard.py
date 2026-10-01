from tianxia import leaderboard
from tianxia.martial_arts import generate_from_name
from tianxia.save import save_game
from tianxia.state import GameState, new_game_state


def _player(content, name: str, wugong_id: str | None = None, wugong_level: int = 1) -> GameState:
    state = new_game_state(content, name)
    state.player.member.wugong_id = wugong_id
    state.player.member.wugong_level = wugong_level
    return state


def test_compute_leaderboard_is_empty_without_any_saves(content, world, tmp_path):
    board = leaderboard.compute_leaderboard(content, world, saves_dir=tmp_path)
    assert board == {"內功": [], "武學": []}


def test_compute_leaderboard_ranks_players_by_power_and_resolves_created_skill_names(content, world, tmp_path):
    world.claim_skill_name(generate_from_name("九陰白骨爪", "武學", "九陰白骨爪"))
    strong = _player(content, "強者", wugong_id="九陰白骨爪", wugong_level=10)
    weak = _player(content, "弱者", wugong_id="九陰白骨爪", wugong_level=1)
    save_game(strong, tmp_path / "strong.json")
    save_game(weak, tmp_path / "弱者.json")
    board = leaderboard.compute_leaderboard(content, world, saves_dir=tmp_path)
    names = [row[0] for row in board["武學"]]
    assert names == ["強者", "弱者"]  # 熟練度第十成排在第一成前面
    assert board["武學"][0][1] == "九陰白骨爪"


def test_compute_leaderboard_skips_players_with_no_skill_learned(content, world, tmp_path):
    save_game(_player(content, "白丁"), tmp_path / "白丁.json")
    board = leaderboard.compute_leaderboard(content, world, saves_dir=tmp_path)
    assert board == {"內功": [], "武學": []}


def test_compute_leaderboard_skips_unreadable_save_files(content, world, tmp_path):
    (tmp_path / "corrupt.json").write_text("not json", encoding="utf-8")
    save_game(_player(content, "正常玩家", wugong_id="fist", wugong_level=3), tmp_path / "ok.json")
    board = leaderboard.compute_leaderboard(content, world, saves_dir=tmp_path)
    assert [row[0] for row in board["武學"]] == ["正常玩家"]


def test_compute_leaderboard_caps_at_top_n(content, world, tmp_path):
    for i in range(leaderboard.TOP_N + 5):
        save_game(_player(content, f"玩家{i}", wugong_id="fist", wugong_level=1 + i % 10), tmp_path / f"p{i}.json")
    board = leaderboard.compute_leaderboard(content, world, saves_dir=tmp_path)
    assert len(board["武學"]) == leaderboard.TOP_N


def test_format_lines_shows_a_placeholder_when_nobody_has_a_skill():
    lines = leaderboard.format_lines({"內功": [], "武學": []})
    assert lines == ["【天下武學榜】", "　（尚無人留名）", "【內功榜】", "　（尚無人留名）"]


def test_format_lines_shows_ranked_entries_with_quality_and_power():
    board = {"武學": [("強者", "九陰白骨爪", "絕學", 50.0)], "內功": []}
    lines = leaderboard.format_lines(board)
    assert "　1. 強者・【九陰白骨爪】（絕學，威力 50.0）" in lines
