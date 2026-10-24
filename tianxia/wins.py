"""三陣營四勝利（減法季整合設計第三章；計畫第五節，批 3c）：豪強兩本帳、此刻幫誰、季末四階。

- 「此刻幫誰」就是 PlayerState.ally（豪強分屬兩軍的季投靠時挑的那一軍；敵我、出陣、軍令、決戰本來就照它）：lean_of 讀它、
  set_lean 寫它，換邊不算叛投、帳不清（計畫 5.0 第 8 條）。
- 兩本帳 PlayerState.ledgers：豪強替哪一軍出的力記哪一本，contrib 照樣加總數（軍階、席次、榜照舊讀 contrib）。

純規則：只 import models、state、allied、push，不碰引擎與全服狀態。批 0（Config.jianfa、jianfa.on）還沒到，引擎現在沒有人叫這裡；
接線時 credit 的第一行補開關（關著照舊 push.add_contribution），rules_of 改讀 content.config.jianfa。"""
from __future__ import annotations

from . import allied, push
from .models import Content, WinsRules
from .state import PlayerState, WorldState

# 改幫另一軍按不下去的原因（lean_problem；待 joy 潤）
LEAN_NOT_GENTRY = "只有地方豪強能改幫另一軍。"
LEAN_BAD = "豪強只能幫官軍或黃巾其中一邊。"
LEAN_SAME = "你此刻就在幫{side}。"


def rules_of(content: Content) -> WinsRules:
    """這一季四階與傾向的數字：批 0 之前是預設的那一份（models.WinsRules）；批 0 到了改成 content.config.jianfa（同名欄位）。"""
    return WinsRules()


def is_gentry(p: PlayerState, content: Content) -> bool:
    """投靠的是要依附一軍的陣營（地方豪強，劇本寫了 allies）。散人、兩軍的人是 False。"""
    return bool(allied.allies_of(content, p.faction))


def _allies(p: PlayerState, content: Content) -> list[str]:
    return [f.id for f in allied.allies_of(content, p.faction)]


def lean_of(p: PlayerState, content: Content) -> str | None:
    """豪強此刻幫哪一軍（就是 ally）；兩軍的人、散人、還沒有傾向的豪強是 None。"""
    return p.ally if is_gentry(p, content) else None


def lean_default(content: Content, location: str, rules: WinsRules | None = None) -> str | None:
    """在 location 投靠豪強時預設幫哪一軍（企劃者 2026-10-24：照投靠點）；不是豪強的投靠點、沒寫是 None。"""
    side = (rules or rules_of(content)).lean_default_by_join.get(location)
    return side if side is not None and any(location in f.join_at and side in f.allies for f in content.scenario.factions) else None


def lean_problem(p: PlayerState, content: Content, side: str) -> str:
    """改幫 side 按不下去的原因；按得下去是空字串。兩軍的人、散人不能改；豪強只能幫劇本 allies 裡的那幾軍；本來就幫它也不算換。"""
    if not is_gentry(p, content):
        return LEAN_NOT_GENTRY
    if side not in _allies(p, content):
        return LEAN_BAD
    if side == p.ally:
        return LEAN_SAME.format(side=content.scenario.faction_name(side, side))
    return ""


def set_lean(p: PlayerState, content: Content, side: str) -> bool:
    """豪強改幫 side：寫 ally、這一季換邊的次數 +1（本來沒有傾向的第一次不算）；不算叛投（defected 不動）、兩本帳與 contrib 不清。
    按不下去（lean_problem）什麼都不動、回 False。名冊、活躍名單、決戰的那一邊由接線的人跟著改（計畫 5.0 第 8 條）。"""
    if lean_problem(p, content, side):
        return False
    if p.ally is not None:
        p.lean_changed += 1
    p.ally = side
    return True


def credit(p: PlayerState, content: Content, world: WorldState, week: int, points: int, *, side: str | None = None) -> None:
    """記貢獻：contrib 與那一週的帳照舊（push.add_contribution）；豪強另記一本——side（決戰照參戰那一刻那一邊）沒給就是此刻的傾向，
    不是它能幫的那一軍就不記帳。0 點什麼都不記。world 留給批 0 的開關（jianfa.on(content, world, "four_wins")，關著只記 contrib）。"""
    if not points:
        return
    push.add_contribution(p, week, points)
    if not is_gentry(p, content):
        return
    to = side or p.ally
    if to in _allies(p, content):
        p.ledgers[to] = p.ledgers.get(to, 0) + points


def ledger_view(p: PlayerState, content: Content) -> dict[str, int] | None:
    """三方卡、本週卡的兩本帳（欄位表 main.sides.ledger）：豪強每一軍一個數（沒記過是 0，照劇本 allies 的順序）；不是豪強是 None。"""
    if not is_gentry(p, content):
        return None
    return {side: p.ledgers.get(side, 0) for side in _allies(p, content)}


def check(content: Content, rules: WinsRules) -> list[str]:
    """數字對得上劇本嗎（content.validate 接線後叫）：豪強每個投靠點都有預設、預設是那個豪強能幫的那一軍、沒有寫到別的地點。"""
    problems: list[str] = []
    gentry = [f for f in content.scenario.factions if f.allies]
    joins = {loc: f for f in gentry for loc in f.join_at}
    for loc, side in rules.lean_default_by_join.items():
        if loc not in joins:
            problems.append(f"lean_default_by_join：{loc} 不是豪強的投靠點")
        elif side not in joins[loc].allies:
            problems.append(f"lean_default_by_join：{loc} 預設幫 {side}，{joins[loc].id} 只能幫 {'、'.join(joins[loc].allies)}")
    missing = [loc for loc in joins if loc not in rules.lean_default_by_join]
    if missing:
        problems.append(f"lean_default_by_join：豪強的投靠點 {'、'.join(missing)} 沒寫預設")
    return problems
