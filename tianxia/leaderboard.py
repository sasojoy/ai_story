"""賽季榜單：天下武學榜／內功榜（設計文件 6.5），依威力排名，是玩家的具體終局目標
之一，寫進賽季結束的江湖史（見 world.py::end_season）。
企劃者 2026-10-14 加善人榜、惡人榜、名人榜、宗師榜（compute_boards），見聞的「榜單」分頁讀它（server.api_boards，
伺服器那邊快取一陣子：掃全部角色不便宜，二三十人在線時每個人點開都掃一次划不來；引擎不讀時鐘，快取不放這裡）。

掃描所有角色（資料庫的 characters 表），取每個人目前「自己練的」那一門內功／武學（玩家本人
的 Member.neigong_id/wugong_id，不是同伴自身的本命武學——榜單排的是玩家的成就，
不是歷史人物本來就有的固定威力，呼應設計文件原文「你（或你創的武學）在天下武學排名上
留下什麼紀錄」），依威力排名取前 TOP_N 名。小規模工作室試玩（十幾人以內，見設計文件
8.1），同步掃描所有存檔的成本可以忽略，不需要另外維護一份即時更新的排行榜快取。
"""
from __future__ import annotations

from . import arena, library, martial_arts, team
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
    boards = compute_boards(content, world, characters)
    return {"內功": boards["內功"], "武學": boards["武學"]}


# 善人、惡人、名人、宗師榜的一列：(名號, 排序用的鍵〔大的在前〕, 寫給人看的那一段)
RankRow = tuple[str, tuple[int, ...], str]

# 六張榜的順序、標題與一句說明（見聞「榜單」分頁照這個順序畫；江湖史也照它寫）
BOARDS: tuple[tuple[str, str, str], ...] = (
    ("善人", "善人榜", "這一季攢下的善名"),
    ("惡人", "惡人榜", "這一季攢下的惡名"),
    ("名人", "名人榜", "這一季的名望"),
    ("宗師", "宗師榜", "練成絕學的門數；一樣多時看首創的武學與意境"),
    ("武學", "天下武學榜", "身上那門武學的威力"),
    ("內功", "內功榜", "身上那門內功的威力"),
    ("擂台", "擂台榜", "擂台上的名次；前十名有稱號"),
)
STAT_BOARDS = {"善人": ("good", "善名"), "惡人": ("evil", "惡名"), "名人": ("fame", "名望")}
MASTERED = "絕學"


def compute_boards(
    content: Content, world: WorldStateStore, characters: CharacterStore | None = None, top: int | None = TOP_N,
) -> dict[str, list]:
    """七張榜一次掃完（企劃者 2026-10-14；擂台榜照 WorldState.arena 的名次，擂台關著是空的）：只算這一季的角色（同 compute_leaderboard）；真人與假人一樣列、看不出來，名字一律寫名號
    （排行榜不匿名，傳聞分層第七節）。善人、惡人、名人照 stats 的 good／evil／fame，0 的不上榜；宗師照自己練到絕學的門數
    （PlayerState.art_quality 是「絕學」的、手上還有的那幾門），一樣多時看這一季首創幾樣（WorldStateStore.season_firsts），
    兩樣都是 0 的不上榜。同分照名號排，每次看都一樣。top=None 回整張（伺服器拿來找「你排第幾」）。"""
    board: dict[str, list] = {kind: [] for kind, _, _ in BOARDS}
    season_number = world.get_season_number()
    firsts = world.season_firsts()
    for state in (characters or open_characters()).all():  # 讀不懂的存檔 all() 已經跳過
        p = state.player
        if p.season_number != season_number:
            continue
        member = p.member
        for slot, kind in (("neigong_id", "內功"), ("wugong_id", "武學")):
            skill_id = getattr(member, slot)
            if not skill_id:
                continue
            art = team.player_art(state, content, world, skill_id)
            if art is None:
                continue
            level = getattr(member, slot.replace("_id", "_level"))
            board[kind].append((p.name, art.name, art.quality, martial_arts.power_at(art, level)))
        for kind, (stat, label) in STAT_BOARDS.items():
            value = p.stats.get(stat, 0)
            if value > 0:
                board[kind].append((p.name, (value,), f"{label} {value}"))
        mastered = sum(1 for art_id in library.owned_arts(state) if p.art_quality.get(art_id) == MASTERED)
        made = firsts.get(p.name, 0)
        if mastered or made:
            board["宗師"].append((p.name, (mastered, made), f"絕學 {mastered} 門・首創 {made} 樣"))
    if arena.on(content):  # 擂台榜（tianxia/arena.py）：照名次，不掃角色；報了名就上榜，跟擂台那一頁的擂台榜一樣
        for e in arena.ladder(world.get_season()):
            title = arena.title_for(e.rank)
            board["擂台"].append((e.name, (-e.rank,), "・".join(t for t in (title, arena.record_text(e)) if t)))
    for kind, rows in board.items():
        if kind in ("武學", "內功"):
            rows.sort(key=lambda row: (-row[3], row[0]))
        else:
            rows.sort(key=lambda row: (tuple(-v for v in row[1]), row[0]))
        board[kind] = rows if top is None else rows[:top]
    return board


def row_text(kind: str, row) -> tuple[str, str]:
    """一列寫給人看的兩段：(名號, 後面那一段)。"""
    if kind in ("武學", "內功"):
        owner, name, quality, power = row
        return owner, f"【{name}】（{quality}，威力 {power:.1f}）"
    return row[0], row[2]


def format_lines(board: dict[str, list]) -> list[str]:
    """季末附在結局後面的榜單：board 有哪幾張寫哪幾張（照 BOARDS 的順序）。"""
    lines: list[str] = []
    for kind, label, _ in BOARDS:
        if kind not in board:
            continue
        lines.append(f"【{label}】")
        rows = board[kind]
        if not rows:
            lines.append("　（尚無人留名）")
            continue
        for i, row in enumerate(rows, 1):
            owner, rest = row_text(kind, row)
            lines.append(f"　{i}. {owner}・{rest}")
    return lines


CHRONICLE_TOP = 3  # 江湖史每張榜寫前幾名（跨季保留，一張一行）


def chronicle_lines(board: dict[str, list], season: int) -> list[str]:
    """寫進江湖史的榜單：一張榜一行、前三名；沒人上榜的那張不寫。"""
    lines = []
    for kind, label, _ in BOARDS:
        rows = board.get(kind, [])[:CHRONICLE_TOP]
        if rows:
            pairs = (row_text(kind, row) for row in rows)
            names = "、".join(f"{owner}{rest}" if kind in ("武學", "內功") else f"{owner}（{rest}）" for owner, rest in pairs)
            lines.append(f"第 {season} 季{label}：{names}")
    return lines


def _view_row(kind: str, row, rank: int, me: str | None) -> dict:
    """畫面上的一列：名號、後面那一段；武學榜、內功榜的那一段拆成功法名（text）與品質威力（sub），375 寬才排得下。"""
    if kind in ("武學", "內功"):
        owner, name, quality, power = row
        return {"rank": rank, "name": owner, "text": f"【{name}】", "sub": f"{quality}・威力 {power:.1f}", "you": owner == me}
    return {"rank": rank, "name": row[0], "text": row[2], "you": row[0] == me}


def view(board: dict[str, list], me: str | None = None, top: int = TOP_N) -> list[dict]:
    """見聞「榜單」分頁的資料：一張榜一筆（id、標題、說明、前 top 名），board 是整張（compute_boards(top=None)）。
    me 不在前 top 名、但在榜上時多一筆 mine（你排第幾、那一段）。"""
    out = []
    for kind, label, note in BOARDS:
        rows = board.get(kind, [])
        entry = {"id": kind, "title": label, "note": note, "rows": [_view_row(kind, row, i, me) for i, row in enumerate(rows[:top], 1)]}
        if me is not None:
            at = next((i for i, row in enumerate(rows, 1) if row[0] == me), None)
            if at is not None and at > top:
                entry["mine"] = {"rank": at, "text": row_text(kind, rows[at - 1])[1]}
        out.append(entry)
    return out


TOP_CONTRIB = 5  # 結算畫面每個陣營列幾名（第一季設計 13.3：各陣營貢獻最高的前幾名）


def contribution_rankings(
    content: Content, world: WorldStateStore, characters: CharacterStore | None = None,
) -> dict[str, list[tuple[str, int]]]:
    """第一季結算畫面的各陣營出力前五（計畫 T9）：這一季的角色、有陣營、貢獻大於 0，照貢獻排（同分照存檔順序）。
    名字一律寫名號（排行榜不能匿名，傳聞分層第七節）；真人與假人一樣列、看不出來。劇本的每個陣營都有一格，沒人出力是空的。"""
    season_number = world.get_season_number()
    ranks: dict[str, list[tuple[str, int]]] = {f.id: [] for f in content.scenario.factions}
    for state in (characters or open_characters()).all():
        p = state.player
        if p.season_number != season_number or p.faction not in ranks or p.contrib <= 0:
            continue
        ranks[p.faction].append((p.name, p.contrib))
    for faction, rows in ranks.items():
        rows.sort(key=lambda row: row[1], reverse=True)
        ranks[faction] = rows[:TOP_CONTRIB]
    return ranks
