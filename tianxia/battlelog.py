"""戰鬥紀錄：把一場戰鬥存成 BattleRecord，並產生場景卡片、戰報列表與完整戰報的文字。

關鍵時刻取自戰鬥引擎回傳的結構化事件（battle.BattleEvent），不從戰報文字反推。
"""
from __future__ import annotations

from . import team
from .battle import BattleEvent, BattleResult
from .models import Content, Squad
from .state import BattleRecord, Fighter, GameState, Performance

MAX_RECORDS = 20  # 存檔保留最近幾場
MAX_MOMENTS = 3
MOMENT_ORDER = ("ultimate", "control", "knockout")  # 施展絕招 → 控制命中 → 有人倒下
CONTROL_PHRASES = {"點穴": "點住{}的穴道", "卸兵": "卸下{}的兵刃", "封脈": "封住{}的經脈"}
OUTCOME_WORDS = {"win": "勝", "draw": "平", "lose": "敗"}
KIND_WORDS = {"train": "歷練", "event": "劇情"}
NO_RECORD = "（還沒有戰報。）"
DAY = 86400
HOUR = 3600


# ── 建立紀錄 ──────────────────────────────────────────


def new_record(
    state: GameState, content: Content, squad: Squad, result: BattleResult, kind: str, event: str = ""
) -> BattleRecord:
    """剛打完、還沒發獎懲時呼叫：記下陣容（戰前的等級）、結果、關鍵時刻、戰報與我方表現。
    獲得與損失（exp、xinde、silver、notes）由 engine 發完獎懲後填入，再交給 add_record。"""
    p = state.player
    keys = team.team_keys(state)
    names = [team.member_name(state, content, key) for key in keys]
    return BattleRecord(
        id=state.battle_seq + 1,
        time=state.world.time,
        location=content.locations[p.location].name,
        kind=kind,
        event=event,
        opponent=squad.name,
        ours=[Fighter(name=name, level=p.members[key].level) for name, key in zip(names, keys)],
        theirs=[Fighter(name=content.characters[m.character].name, level=m.level) for m in squad.members],
        outcome=result.outcome,
        rounds=result.rounds,
        ending=result.report[-1],
        leader_ok=result.hp[0] > 0,
        moments=key_moments(result.events),
        report=list(result.report),
        performance=[
            Performance(name=name, damage=dealt, controls=controls)
            for name, dealt, controls in zip(names, result.dealt, result.controls)
        ],
    )


def add_record(state: GameState, record: BattleRecord) -> None:
    """最新的放最前面，只留最近 MAX_RECORDS 場。"""
    state.battle_seq = record.id
    state.battles.insert(0, record)
    del state.battles[MAX_RECORDS:]


def find(state: GameState, record_id: int | None) -> BattleRecord | None:
    return next((r for r in state.battles if r.id == record_id), None)


# ── 關鍵時刻 ──────────────────────────────────────────


def key_moments(events: list[BattleEvent]) -> list[str]:
    """最多 3 則。依「施展絕招 → 控制命中 → 有人倒下」輪流各挑一則（倒下的以隊長優先，其餘依發生先後），
    挑滿為止；挑好後依發生先後排列。"""
    order = {id(e): i for i, e in enumerate(events)}
    pools = {kind: [e for e in events if e.kind == kind] for kind in MOMENT_ORDER}
    pools["knockout"].sort(key=lambda e: not e.is_leader)
    picked: list[BattleEvent] = []
    while len(picked) < MAX_MOMENTS and any(pools.values()):
        for kind in MOMENT_ORDER:
            if pools[kind] and len(picked) < MAX_MOMENTS:
                picked.append(pools[kind].pop(0))
    picked.sort(key=lambda e: order[id(e)])
    return [moment_text(e) for e in picked]


def moment_text(e: BattleEvent) -> str:
    """一句話，例如「第4回合　小墨【亂針】封住劫道山賊的經脈」。"""
    head = "開戰前　" if e.round == 0 else f"第{e.round}回合　"
    if e.kind == "ultimate":
        return f"{head}{e.actor}施展【{e.art}】"
    if e.kind == "control":
        return f"{head}{e.actor}【{e.art}】{CONTROL_PHRASES[e.control].format(e.target)}"
    leader = ("敵方隊長" if e.actor_side == 0 else "我方隊長") if e.is_leader else ""
    return f"{head}{e.actor}擊倒{leader}{e.target}"


# ── 文字 ──────────────────────────────────────────────


def clock_text(time: float) -> str:
    """遊戲時間，例如「第2天 14:05」。"""
    return f"第{int(time // DAY) + 1}天 {int(time % DAY // HOUR):02d}:{int(time % HOUR // 60):02d}"


def summary_line(record: BattleRecord) -> str:
    """紀錄裡的一行摘要，例如「⚔ 揚州城郊：擊退劫道山賊（4 回合）」。"""
    where, foe, rounds = record.location, record.opponent, f"（{record.rounds} 回合）"
    if record.outcome == "win":
        return f"⚔ {where}：擊退{foe}{rounds}"
    if record.outcome == "lose":
        return f"⚔ {where}：不敵{foe}，敗退{rounds}"
    return f"⚔ {where}：與{foe}不分勝負{rounds}"


def list_label(record: BattleRecord) -> str:
    """戰報列表的一列：「勝　第1天 08:30　揚州城郊　vs 劫道山賊　4 回合」。"""
    return (
        f"{OUTCOME_WORDS[record.outcome]}　{clock_text(record.time)}　{record.location}"
        f"　vs {record.opponent}　{record.rounds} 回合"
    )


def _title(record: BattleRecord) -> str:
    foes = "、".join(dict.fromkeys(f.name for f in record.theirs))
    return f"### ⚔ {record.location}・對陣 {foes}"


def _when(record: BattleRecord) -> str:
    kind = KIND_WORDS[record.kind] + (f"：{record.event}" if record.event else "")
    return f"{clock_text(record.time)}　{kind}"


def _result_line(record: BattleRecord) -> str:
    word = {"win": "勝", "draw": "平手", "lose": "敗"}[record.outcome]
    leader = record.ours[0].name if record.ours else "隊長"
    health = "無恙" if record.leader_ok else "倒下"
    return f"**{word}**・{record.rounds} 回合・隊長{leader}{health}"


def gains_text(record: BattleRecord) -> str:
    """獲得與損失，例如「經驗 +15（每人）　心得 +12　銀兩 +10　臂力 +1」；什麼都沒有時寫「無」。"""
    parts = []
    if record.exp:
        parts.append(f"經驗 +{record.exp}（每人）")
    if record.xinde:
        parts.append(f"心得 +{record.xinde}")
    if record.silver:
        parts.append(f"銀兩 {record.silver:+d}")
    return "　".join(parts + record.notes) or "無"


def _moments_block(record: BattleRecord) -> str:
    return "\n".join(f"- {m}" for m in record.moments) or "（沒有特別的一刻。）"


def card_text(record: BattleRecord) -> str:
    """場景裡的戰鬥卡片（Markdown）：標題、時間與類型、結果、關鍵時刻、獲得與損失。"""
    return "\n\n".join([
        _title(record),
        _when(record),
        _result_line(record),
        _moments_block(record),
        f"**獲得與損失**　{gains_text(record)}",
    ])


def detail_text(record: BattleRecord) -> str:
    """戰報分頁下方的完整內容（Markdown）：陣容、結果、關鍵時刻、得失、我方表現、逐回合戰報。"""
    ours = "、".join(f"{f.name} Lv{f.level}" for f in record.ours)
    theirs = "、".join(f"{f.name} Lv{f.level}" for f in record.theirs)
    rows = ["| 人物 | 造成傷害 | 控制命中 |", "|---|---|---|"]
    rows += [f"| {p.name} | {p.damage} | {p.controls} |" for p in record.performance]
    return "\n\n".join([
        _title(record),
        f"{_when(record)}　第 {record.id} 場",
        f"**我方**　{ours}",
        f"**對方**　{record.opponent}：{theirs}",
        f"{_result_line(record)}　（{record.ending}）",
        "**關鍵時刻**",
        _moments_block(record),
        f"**獲得與損失**　{gains_text(record)}",
        "**我方表現**",
        "\n".join(rows),
        "**逐回合戰報**",
        "\n\n".join(record.report),
    ])
