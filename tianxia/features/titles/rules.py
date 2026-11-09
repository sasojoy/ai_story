"""稱號與官職的規則（設計稿 v5，Joy 2026-11-08 定：不加屬性，靠稀有與顯示）。

三等：尋常（不能配戴、不印名帖）、官職（第 2 階起，墨印）、名號（金印或朱印，一週或一季只有幾個人）。
- 名次型的名號（擂台、各榜第一）每週結算一次（季曆換週那一刻之後第一個同步的人替全服結算，settle），頒給那一刻的名次，
  有效到下一次結算；中間被人超過也照戴。
- 一季的名號（破陣首功、受命於天、神器之主、上一季論功）拿到就整季有效。
- 拿過的名號收進名號簿（PlayerState.title_book，「第N季 名號」），往後都能印名帖。
- 一次戴一個：自己挑的（titles_pin）還在手上就戴它，不然自動戴最高檔的（金 > 朱 > 墨，一樣高照 DEFS 的順序）。
這個模組只 import 核心與共用規則層，不碰 engine。新寫給玩家看的字都待 joy 潤。
"""
from __future__ import annotations

from dataclasses import dataclass

from tianxia import ranks, renown
from tianxia.characters import name_key
from tianxia.core import arena_ranks
from tianxia.models import Content
from tianxia.rules import season_one
from tianxia.state import GameState, WorldState

GOLD, ZHU, INK = "gold", "zhu", "ink"
GRADE_ORDER = (GOLD, ZHU, INK)
WEEKLY, SEASON = "weekly", "season"


@dataclass(frozen=True)
class TitleDef:
    id: str
    name: str
    grade: str
    span: str  # WEEKLY（每週結算）、SEASON（拿到就整季）
    how: str  # 怎麼拿（換戴那一格寫給玩家看；待 joy 潤）


# 名號清單（設計稿 v5 第三節；字待 joy 潤）。順序就是一樣高時的先後
DEFS: tuple[TitleDef, ...] = (
    TitleDef("arena1", "天下第一", GOLD, WEEKLY, "每週結算時擂台第一名"),
    TitleDef("zongshi", "一代宗師", GOLD, WEEKLY, "每週結算時宗師榜第一"),
    TitleDef("fame", "名滿天下", GOLD, WEEKLY, "每週結算時名人榜第一，而且名望到天下聞名"),
    TitleDef("mandate", "受命於天", GOLD, SEASON, "天命之爭得天命的那一軍，手上有玉璽碎片的人"),
    TitleDef("arena3", "擂台三甲", ZHU, WEEKLY, "每週結算時擂台第二、三名"),
    TitleDef("wuxue", "武冠群倫", ZHU, WEEKLY, "每週結算時天下武學榜第一"),
    TitleDef("neigong", "內力通玄", ZHU, WEEKLY, "每週結算時內功榜第一"),
    TitleDef("xia", "天下名俠", ZHU, WEEKLY, "每週結算時善人榜第一，而且善名到天下名俠"),
    TitleDef("kou", "天下大盜", ZHU, WEEKLY, "每週結算時惡人榜第一，而且惡名到天下大盜"),
    TitleDef("merit", "破陣首功", ZHU, SEASON, "一場全服決戰自己那一軍戰功第一"),
    TitleDef("divine", "神器之主", ZHU, SEASON, "身上帶著自己打出的神器原品"),
)
BY_ID = {d.id: d for d in DEFS}
WEEKLY_IDS = tuple(d.id for d in DEFS if d.span == WEEKLY)
OFFICIAL = "official"  # 官職那一格的 id（名字照陣營與階：屯長、軍司馬、校尉……）
SEASON_TITLE = "season_title"  # 上一季論功那一格的 id（名字照 PlayerState.season_title）

# 名號換手的江湖傳聞（設計稿 v5「名號換人的江湖傳聞」；待 joy 潤）
RUMOR_NEW = "【名號結算】{name}接下「{title}」。"
RUMOR_KEPT = "【名號結算】{name}連守「{title}」。"
RUMOR_SEASON = "{name}得了名號「{title}」。"
# 給自己看的那一行（一週最多一次；待 joy 潤）
GOT_LINE = "你得了名號「{title}」，收進名號簿。"
LOST_LINE = "「{old}」易手了，{now}。"
NOW_WEAR = "改戴「{title}」"
NOW_NONE = "眼下沒有可戴的頭銜"
JOURNAL_TITLE = "名號"
PIN_OK = "你戴上了「{title}」。"
PIN_AUTO = "頭銜改成自動：戴手上最高檔的那一個。"
PIN_BAD = "（那個頭銜你眼下沒有。）"


def on(content: Content) -> bool:
    return content.config.titles.enabled


def week_of(content: Content, world: WorldState) -> int:
    from tianxia import calendar  # noqa: PLC0415  calendar 是核心；延後 import 免得測試換掉 calendar 時讀到舊的

    return calendar.point(world.time, content, world).week


def due(content: Content, world: WorldState) -> bool:
    """這一季該結算了嗎：開著、季還在跑、季曆已經跨進結算過的那一週之後（第 1 週不結算：大家剛起步）。"""
    return on(content) and not world.ended and week_of(content, world) > max(1, world.titles_week)


def _first(rows: list) -> str | None:
    return rows[0][0] if rows else None


def holders_from(content: Content, season: WorldState, board: dict[str, list]) -> dict[str, list[str]]:
    """照這一刻的榜單與擂台名次算每一個週名號頒給誰（board 是 leaderboard.compute_boards 的整張）。
    名人、善人、惡人榜第一還要過名聲第 4 段的門檻（名聲關著就沒有這三個）。"""
    out: dict[str, list[str]] = {}
    if arena_ranks.on(content):
        ladder = arena_ranks.ladder(season)
        out["arena1"] = [e.name for e in ladder if e.rank == 1][:1]
        out["arena3"] = [e.name for e in ladder if e.rank in (2, 3)][:2]
    for tid, kind in (("zongshi", "宗師"), ("wuxue", "武學"), ("neigong", "內功")):
        top = _first(board.get(kind) or [])
        out[tid] = [top] if top else []
    if renown.on(content):
        fame_bar = renown.fame_bars(content, season)[-1]
        virtue_bar = renown.virtue_bars(content, season)[-1]
        for tid, kind, bar in (("fame", "名人", fame_bar), ("xia", "善人", virtue_bar), ("kou", "惡人", virtue_bar)):
            rows = board.get(kind) or []
            out[tid] = [rows[0][0]] if rows and rows[0][1][0] >= bar else []
    return {k: v for k, v in out.items() if v}


def rumors(old: dict[str, list[str]], new: dict[str, list[str]]) -> list[str]:
    """結算的江湖傳聞：每個有人拿的週名號一則（接下或連守）。"""
    lines = []
    for d in DEFS:
        if d.span != WEEKLY:
            continue
        before = {name_key(n) for n in old.get(d.id, [])}
        for name in new.get(d.id, []):
            text = RUMOR_KEPT if name_key(name) in before else RUMOR_NEW
            lines.append(text.format(name=name, title=d.name))
    return lines


def _mine(names: list[str], me: str) -> bool:
    k = name_key(me)
    return any(name_key(n) == k for n in names)


def season_grade(content: Content, title: str) -> str | None:
    """上一季論功的稱號是哪一檔：照 Config.jianfa.tiers.titles 找它是第幾階，第 1、2 階朱印、第 3 階墨印，第 4 階（隨軍、附從）是尋常。"""
    for key, name in content.config.jianfa.tiers.titles.items():
        if name == title:
            tier = int(key.split(":")[0])
            return ZHU if tier <= 2 else INK if tier == 3 else None
    return None


def divine_owner(state: GameState) -> bool:
    """身上（兵器、防具）帶著自己打出的神器原品（同名帖「神器【】之主」的認法）。"""
    p = state.player
    return any(item is not None and item.original and item.secret and "無名" not in item.name for item in (p.weapon, p.armor))


def available(state: GameState, content: Content, mandate: list[str] | None = None) -> list[dict]:
    """此刻手上能戴的（照檔次排，一樣高照 DEFS）：每一個 {"id", "name", "grade", "how"}。mandate 是受命於天的那幾個名號。"""
    p, w = state.player, state.world
    out: list[dict] = []
    for d in DEFS:
        if d.span == WEEKLY:
            got = _mine(w.titles_holders.get(d.id, []), p.name)
        elif d.id == "merit":
            got = p.top_merits > 0
        elif d.id == "mandate":
            got = _mine(mandate or [], p.name)
        else:  # divine
            got = divine_owner(state)
        if got:
            out.append({"id": d.id, "name": d.name, "grade": d.grade, "how": d.how})
    grade = season_grade(content, p.season_title) if p.season_title else None
    if grade is not None:
        out.append({"id": SEASON_TITLE, "name": p.season_title, "grade": grade, "how": "上一季論功"})
    if season_one(content, w) and ranks.rank_of(state) >= 2:
        office = ranks.title(content, state)
        if office:
            out.append({"id": OFFICIAL, "name": office, "grade": INK, "how": "陣營裡的官職"})
    return sorted(out, key=lambda t: GRADE_ORDER.index(t["grade"]))


def pick_worn(choices: list[dict], pin: str) -> dict:
    """戴哪一個：自己挑的還在手上就是它，不然最高檔的那一個；手上什麼都沒有是 {}。"""
    for t in choices:
        if pin and t["id"] == pin:
            return t
    return choices[0] if choices else {}


def book_entry(season: int, title: str) -> str:
    return f"第{season}季 {title}"


def view(state: GameState, choices: list[dict]) -> dict:
    """換戴那一格的資料（main.titles）：戴著的、自己挑的、手上有的，加上還沒拿到的名號（灰的，當目標）。"""
    p = state.player
    worn = p.titles_worn.get("id", "")
    held = {t["id"] for t in choices}
    rows = [{**t, "mine": True, "worn": t["id"] == worn} for t in choices]
    rows += [{"id": d.id, "name": d.name, "grade": d.grade, "how": d.how, "mine": False, "worn": False}
             for d in DEFS if d.id not in held and d.id != "divine"]
    return {"worn": dict(p.titles_worn), "pin": p.titles_pin, "rows": rows}
