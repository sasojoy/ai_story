"""賽季榜單：天下武學榜／內功榜（設計文件 6.5），依威力排名，是玩家的具體終局目標
之一，寫進賽季結束的江湖史（見 world.py::end_season）。

掃描所有玩家存檔（saves/*.json），取每個人目前「自己練的」那一門內功／武學（玩家本人
的 Member.neigong_id/wugong_id，不是同伴自身的本命武學——榜單排的是玩家的成就，
不是歷史人物本來就有的固定威力，呼應設計文件原文「你（或你創的武學）在天下武學排名上
留下什麼紀錄」），依威力排名取前 TOP_N 名。小規模工作室試玩（十幾人以內，見設計文件
8.1），同步掃描所有存檔的成本可以忽略，不需要另外維護一份即時更新的排行榜快取。
"""
from __future__ import annotations

from pathlib import Path

from . import martial_arts, team
from .models import Content
from .save import load_game
from .world_state import WorldStateStore

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SAVES_DIR = ROOT / "saves"
TOP_N = 10

LeaderboardRow = tuple[str, str, str, float]  # (玩家名號, 功法名稱, 品質, 威力)


def compute_leaderboard(
    content: Content, world: WorldStateStore, saves_dir: Path | None = None,
) -> dict[str, list[LeaderboardRow]]:
    board: dict[str, list[LeaderboardRow]] = {"內功": [], "武學": []}
    saves_dir = Path(saves_dir) if saves_dir else DEFAULT_SAVES_DIR
    if not saves_dir.is_dir():
        return board
    for path in sorted(saves_dir.glob("*.json")):
        try:
            state = load_game(path)
        except Exception:
            continue  # 損毀/格式不相容的存檔跳過，不讓一份壞檔拖垮整個榜單
        member = state.player.member
        for slot, kind in (("neigong_id", "內功"), ("wugong_id", "武學")):
            skill_id = getattr(member, slot)
            if not skill_id:
                continue
            art = team.resolve_art(skill_id, content, world)
            if art is None:
                continue
            level = getattr(member, slot.replace("_id", "_level"))
            power = martial_arts.power_at(art, level)
            board[kind].append((state.player.name, art.name, art.quality, power))
    for kind, rows in board.items():
        rows.sort(key=lambda row: row[3], reverse=True)
        board[kind] = rows[:TOP_N]
    return board


def format_lines(board: dict[str, list[LeaderboardRow]]) -> list[str]:
    lines: list[str] = []
    for kind, label in (("武學", "天下武學榜"), ("內功", "內功榜")):
        lines.append(f"【{label}】")
        rows = board.get(kind, [])
        if not rows:
            lines.append("　（尚無人留名）")
            continue
        for i, (owner, name, quality, power) in enumerate(rows, 1):
            lines.append(f"　{i}. {owner}・【{name}】（{quality}，威力 {power:.1f}）")
    return lines
