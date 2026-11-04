"""擂台的名次與稱號（查詢服務；全部拆包第 12 批 PM 定：擂台的稱號與名次會被酒肆、名帖、榜單讀，留在核心當查詢服務，總表第六節第 6 條）。

擂台本身（報名、挑擂、一場怎麼打、俸、季末前三名）在單挑包（tianxia/features/bout/）；這裡只有「此刻誰排第幾、掛什麼稱號、戰績怎麼寫、
歷屆擂主」這幾樣只讀的：擂台開著沒（on）、這個人的那一筆（entry_of）、照名次排（ladder）、稱號（title_of、title_for）、戰績（record_text）、
擂台榜（board）、江湖史底下的歷屆擂主（champions 與那幾句）。讀它的有酒肆包（名氣，person_fame）、狀態列與玩家卡（social）、名帖（mingtie）、
榜單（leaderboard）、事件分級（tiers）、江湖史（Game.chronicle_text）、本週卡的週解鎖（Game.week_unlock_names）、假人（bot_policy）。
原本寫在 tianxia/arena.py，函式照抄、名字不變；單挑包的 arena_rules（舊名 tianxia.arena）從這裡 re-export 同一批函式物件。
"""
from __future__ import annotations

from ..characters import name_key
from ..models import ArenaTuning, Content
from ..state import ArenaEntry, WorldState

TITLES = ((1, "天下第一"), (3, "擂台三甲"), (10, "擂台十傑"))  # （到第幾名, 稱號）：PM 2026-10-14 定，字句不必問 Joy

# 待 joy 潤
CHAMPION = "本季擂主：{name}。"  # 江湖史跨季保留；歷屆擂主照這個開頭找（champions）
CHAMPION_HEAD = "本季擂主："
CHAMPIONS_TITLE = "### 歷屆擂主"


def on(content: Content) -> bool:
    return content.config.arena.enabled


def entry_of(world: WorldState, name: str) -> ArenaEntry | None:
    return world.arena.get(name_key(name))


def ladder(world: WorldState) -> list[ArenaEntry]:
    """守擂的人照名次排（第一名在前）。"""
    return sorted(world.arena.values(), key=lambda e: (e.rank, e.joined, name_key(e.name)))


def title_of(world: WorldState, name: str) -> str | None:
    """此刻的稱號（TITLES）：沒報名、十名以外是 None。"""
    entry = entry_of(world, name)
    if entry is None:
        return None
    return next((title for last, title in TITLES if entry.rank <= last), None)


def title_for(rank: int) -> str | None:
    return next((title for last, title in TITLES if rank <= last), None)


def record_text(entry: ArenaEntry) -> str:
    if not entry.bouts:
        return "還沒打過"
    text = f"{entry.wins} 勝 {entry.losses} 負" + (f" {entry.draws} 和" if entry.draws else "")
    return text + (f"・連勝 {entry.streak}" if entry.streak >= 2 else "")


def board(world: WorldState, cfg: ArenaTuning) -> list[dict]:
    """擂台榜（擂台那一頁、見聞「榜單」分頁）：名次、名號、稱號、勝、負、和、連勝。"""
    return [
        {"rank": e.rank, "name": e.name, "title": title_for(e.rank), "wins": e.wins, "losses": e.losses, "draws": e.draws,
         "streak": e.streak}
        for e in ladder(world)[:cfg.board_size]
    ]


def champions(chronicles: list[tuple[int, list[str]]]) -> str:
    """歷屆擂主（江湖史底下一段，跨季）：各季江湖史裡「本季擂主：」那一句。chronicles 是（季, 那一季江湖史的句子），新的一季在前。"""
    rows = []
    for number, texts in chronicles:
        for text in texts:
            if text.startswith(CHAMPION_HEAD):
                rows.append(f"- 第 {number} 季：{text.removeprefix(CHAMPION_HEAD).rstrip('。')}")
    return f"{CHAMPIONS_TITLE}\n\n" + "\n".join(rows) if rows else ""
