"""賽季榜單：天下武學榜／內功榜（設計文件 6.5），依評分排名（Joy 2026-10-20「武學榜高的在上面」：arts.score，一樣高看威力），是玩家的具體終局目標
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

from . import arena, arts, library, martial_arts, team
from .characters import CharacterStore, open_characters
from .models import Content
from .world_state import WorldStateStore

TOP_N = 10

LeaderboardRow = tuple[str, str, str, float, int]  # (玩家名號, 功法名稱, 品質, 威力, 評分)


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
    ("武學", "天下武學榜", "身上那門武學的評分；一樣高看威力"),  # 待 joy 潤
    ("內功", "內功榜", "身上那門內功的評分；一樣高看威力"),  # 待 joy 潤
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
            board[kind].append((p.name, art.name, art.quality, martial_arts.power_at(art, level), arts.score(state, content, world, art)))
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
            rows.sort(key=lambda row: (-row[4], -row[3], row[0]))
        else:
            rows.sort(key=lambda row: (tuple(-v for v in row[1]), row[0]))
        board[kind] = rows if top is None else rows[:top]
    return board


def row_text(kind: str, row) -> tuple[str, str]:
    """一列寫給人看的兩段：(名號, 後面那一段)。"""
    if kind in ("武學", "內功"):
        owner, name, quality, power, score = row
        return owner, f"【{name}】（{quality}，評 {score}，威力 {power:.1f}）"
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
        owner, name, quality, power, score = row
        return {"rank": rank, "name": owner, "text": f"【{name}】", "sub": f"{quality}・評 {score}・威力 {power:.1f}", "you": owner == me}
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


# ── 榜單點開看卡（Joy 2026-10-22「上榜的武學其他玩家應該要可以點的開來看卡，才知道有多強，也讓知識流通」）──
# 只讀：照主人的存檔畫（server.api_board_card，不拿行動鎖）。只開得了榜上看得到的那幾列：武學榜、內功榜的前 TOP_N 名與你自己，
# 神器譜的每一筆。真人與假人畫法一樣、看不出來。


def art_card(
    content: Content, world: WorldStateStore, board: dict[str, list], kind: str, name: str,
    me: str | None = None, characters: CharacterStore | None = None, top: int = TOP_N,
) -> dict | None:
    """武學榜、內功榜那一列的唯讀功法卡（skillview.shown_art）：board 是整張（compute_boards(top=None)，伺服器的快取）。
    name 不在那張榜的前 top 名、也不是你自己，或主人換了季、身上那一欄空了，回 None。"""
    from . import skillview  # skillview 牽動的模組多，world 也 import 這裡：用到才 import，免得繞成圈

    if kind not in ("武學", "內功"):
        return None
    rows = board.get(kind, [])
    if not any(row[0] == name for row in rows[:top]) and not (me is not None and name == me and any(row[0] == me for row in rows)):
        return None
    state = (characters or open_characters()).load(name)
    if state is None or state.player.season_number != world.get_season_number():
        return None
    card = skillview.shown_art(state, content, world, kind)
    return None if card is None else {**card, "owner": state.player.name}


def gear_card(
    content: Content, world: WorldStateStore, season: int, ref: str, characters: CharacterStore | None = None,
) -> dict | None:
    """神器譜那一筆的唯讀裝備卡（skillview.shown_gear）：ref 是 Game.divine_book_view 那一筆的 ref。原品還在主人身上、裝備庫或寄放處
    就照那一件畫（淬煉、磨損照實）；不在了（換季、內容拿掉）照譜上記的種類、屬性、階畫。找不到那一筆回 None。"""
    from . import forge_secrets, signature_arms, skillview
    from .state import Equipment

    owner, item, name, live = None, None, "", True
    if ref.startswith(signature_arms.REF):
        cid = ref[len(signature_arms.REF):]
        claim = next((claims[cid] for s, claims in world.signature_records() if s == season and cid in claims), None)
        arm = next((a for a in content.gear.signature_arms if a.character == cid), None)
        if claim is None or arm is None:
            return None
        owner, name = claim.owner, f"【{arm.name}】"
        state = (characters or open_characters()).load(owner)
        item = next((i for i in forge_secrets.owned_gear(state.player) if i.signature == cid), None) if state is not None else None
        live = item is not None
        item = item or Equipment(slot="weapon", id="譜", name=arm.name, kind=arm.kind, attribute=arm.attribute, tier=3, quality="上品",
                                 original=True, signature=cid)
    else:
        find = next((f for s, f in world.divine_records() if s == season and f.id == ref), None)
        if find is None:
            return None
        owner = find.master_shown or find.owner
        name = next((n for s, n, _, r in forge_secrets.divine_entries([(season, find)]) if r == ref), find.name)
        state = (characters or open_characters()).load(find.owner) if find.owner else None
        item = next((i for i in forge_secrets.owned_gear(state.player) if i.original and i.secret == find.secret), None) if state is not None else None
        live = item is not None
        item = item or Equipment(slot=find.slot, id="譜", name=find.name, kind=find.kind, attribute=find.attribute, tier=find.tier,
                                 original=True, secret=find.secret)
    return {**skillview.shown_gear(content, item, live), "name": name, "owner": owner, "season": season}


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
