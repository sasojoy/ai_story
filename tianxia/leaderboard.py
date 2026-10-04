"""賽季榜單：天下武學榜／內功榜（設計文件 6.5），依威力排名，是玩家的具體終局目標
之一，寫進賽季結束的江湖史（見 world.py::end_season）。

掃描所有角色（資料庫的 characters 表），取每個人目前「自己練的」那一門內功／武學（玩家本人
的 Member.neigong_id/wugong_id，不是同伴自身的本命武學——榜單排的是玩家的成就，
不是歷史人物本來就有的固定威力，呼應設計文件原文「你（或你創的武學）在天下武學排名上
留下什麼紀錄」），依威力排名取前 TOP_N 名。小規模工作室試玩（十幾人以內，見設計文件
8.1），同步掃描所有存檔的成本可以忽略，不需要另外維護一份即時更新的排行榜快取。
"""
from __future__ import annotations

from . import martial_arts, team
from .characters import CharacterStore, open_characters
from .models import Content
from .world_state import WorldStateStore

TOP_N = 10

LeaderboardRow = tuple[str, str, str, float]  # (玩家名號, 功法名稱, 品質, 威力)


def compute_leaderboard(
    content: Content, world: WorldStateStore, characters: CharacterStore | None = None,
) -> dict[str, list[LeaderboardRow]]:
    """只算這一季的角色：換季時角色要等本人下次上線才重來，這一季沒上線的人存檔裡還是上一季的武學，
    混進榜裡就成了上一季的成就占這一季的名次，所以跳過 season_number 跟目前賽季對不上的存檔。"""
    board: dict[str, list[LeaderboardRow]] = {"內功": [], "武學": []}
    season_number = world.get_season_number()
    for state in (characters or open_characters()).all():  # 讀不懂的存檔 all() 已經跳過
        if state.player.season_number != season_number:
            continue
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
