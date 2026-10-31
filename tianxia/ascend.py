"""破境（招式與絕學稿案第三節，Joy 2026-10-21 按建議）：自創的武學練成絕學的那一刻。

- 招升為絕招：會長的數再乘 Config.arts.ascend_scale，每回合會發的招發動率乘同一個數、最多 ascend_rate_cap，起手的照舊（moves.ascend）；八種照屬性配的絕招不丟，
  接在後面當「後勁」（traits.ultimate_of）。卡上私印換成金印「絕」，第五個玉環亮起來。
- 破境有過程：契機在仗裡（cultivation.seize 那一句寫「你的〔招〕忽然通了」），或服丹閉門衝關（cultivation._force）；
  收場後跳出破境卡（PlayerState.ascension）：左邊破境前的招、右邊絕招、中間模型照那一句意寫的一句、底下江湖史那一行。
- 江湖知道：江湖史記破境（自創不記）、傳聞、行狀記一筆。破境不取名（「全服第一個練成的人替武學定名」退掉）。

寫卡那一句是三段式：A Game.ascend_request（鎖內、只讀）→ B ascend.read 鎖外叫模型 → C Game.ascend_line 存回卡上；叫不動照套句。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import BaseModel

from . import annals, might, moves, tactics, team, traits, zh
from .martial_arts import MAX_LEVEL
from .models import Content
from .ollama_client import OllamaClient
from .rules import add_chronicle, add_rumor
from .state import Ascension, GameState
from .world_state import WorldStateStore

SEIZED_LINE = "打到緊處，你的〔{move}〕忽然通了——【{name}】破境，練成絕學！"  # 待 joy 潤
FORCED_LINE = "閉門衝關，〔{move}〕撞開了最後那一層——【{name}】破境，練成絕學！"  # 待 joy 潤
PLAIN_SEIZED = "這一戰打到最後，【{name}】忽然通了——從上品晉為絕學！"
PLAIN_FORCED = "【{name}】衝開了最後那一層，從上品晉為絕學！"
CHRONICLE_LINE = "{who}把【{name}】練到了絕處，一招〔{move}〕自此成了絕招。"  # 待 joy 潤
RUMOR_LINE = "聽說{who}把【{name}】練到了絕處，那一招〔{move}〕如今使出來，旁人連看都看不清。"  # 待 joy 潤
DEED_LINE = "【{name}】破境，〔{move}〕練成絕招。"  # 待 joy 潤
FALLBACK_SEIZED = "那一招在生死之間打磨了千百遍，這一刻終於不再是招，而是你自己。"  # 待 joy 潤
FALLBACK_PILL = "藥力化開，閉門苦思的那一句意忽然清清楚楚，招隨意走，再無滯礙。"  # 待 joy 潤
LINE_MIN, LINE_MAX = 8, 40
_LATIN = re.compile(r"[A-Za-z]")  # 破境那一句是中文：夾了英文（模型的開場白、亂回）就照套句
_BANNED = ("假人", "機器人", "遊戲", "系統", "玩家")
LINE_PREDICT = 120


def move_name(content: Content, art) -> str:
    move = moves.move_of(content, art)
    return move.name if move is not None else art.name


def _might(state: GameState, content: Content, world: WorldStateStore, art_id: str) -> int:
    """這一門在身上時的戰力：穿著的照此刻，躺在功法庫的照換上之後。"""
    return might.now(state, content, world) if art_id not in state.player.arts else might.with_art(state, content, world, art_id) or 0


def ascend(state: GameState, content: Content, world: WorldStateStore, art_id: str, via: str) -> list[str]:
    """把這一門升為絕學（呼叫端已擲中）：改品級、寫破境卡、江湖史、傳聞、行狀。回寫給玩家看的那幾句。
    不是自創的（合成的上品）照舊升品，只多一行江湖史，沒有破境卡。"""
    p = state.player
    before = team.player_art(state, content, world, art_id)
    was_might = _might(state, content, world, art_id)
    p.art_quality[art_id] = "絕學"
    p.art_mastery.pop(art_id, None)
    after = team.player_art(state, content, world, art_id)
    name = after.name
    own = moves.is_own(content, after)
    move = move_name(content, after) if own else name
    world.claim_master(art_id, p.name)  # 宗師榜照舊算（第一個練成的人）；不再拿到替全服定名的權利
    if not own:  # 合成的上品：照舊一句升品
        return [(PLAIN_SEIZED if via == "seize" else PLAIN_FORCED).format(name=name)]
    head = (SEIZED_LINE if via == "seize" else FORCED_LINE).format(move=move, name=name)
    chronicle = CHRONICLE_LINE.format(who=p.name, name=name, move=move)
    add_chronicle(state, chronicle)
    add_rumor(state, RUMOR_LINE.format(who=p.name, name=name, move=move), p.location, content=content)
    annals.note(state, content, annals.DEED, DEED_LINE.format(name=name, move=move), 4)
    was, now = moves.move_of(content, before, MAX_LEVEL), moves.move_of(content, after)
    tail = traits.ultimate_of(content, after)
    p.ascension = Ascension(
        art=art_id, name=name, via=via,
        before=tactics.card_text(was, tactics.title_of(was, before)) if was is not None else "",
        after=tactics.card_text(now, tactics.title_of(now, after)) if now is not None else "",
        after_tail=tactics.card_text(tail, traits.AFTER_TITLE) if tail is not None else "",
        power=[was_might, _might(state, content, world, art_id)],  # 全身的戰力（might），破境前後
        chronicle=chronicle, intent=after.note,
    )
    return [head]


# ── 破境卡那一句（三段式）────────────────────────────


@dataclass(frozen=True)
class LineRequest:
    art: str
    name: str
    move: str
    intent: str
    via: str


class LineReading(BaseModel):
    line: str = ""


SYSTEM_PROMPT = (
    "你是武俠小說的說書人。有人自創的一門功夫剛剛破境、練成絕學，那一招從此成了絕招。"
    "照他當初立下的那一句意，寫一句破境那一刻的描寫，十到三十字，第二人稱（用「你」），不寫數字、不寫別人的名字。只回 JSON。"
)


def request(state: GameState) -> LineRequest | None:
    card = state.player.ascension
    if card is None or card.line:
        return None
    move = card.after[card.after.find("〔") + 1: card.after.find("〕")] if "〔" in card.after else card.name
    return LineRequest(card.art, card.name, move, card.intent, card.via)


def fallback(req: LineRequest) -> str:
    return FALLBACK_SEIZED if req.via == "seize" else FALLBACK_PILL


def clean(text: str) -> str:
    text = zh.to_traditional(" ".join(str(text or "").split()).strip("「」\"' "))
    if (not (LINE_MIN <= len(text) <= LINE_MAX) or any(ch.isdigit() for ch in text) or "{" in text
            or _LATIN.search(text) or any(w in text for w in _BANNED)):
        return ""
    return text


def read(client: OllamaClient | None, req: LineRequest) -> str:
    """B 段（鎖外）：模型寫那一句；叫不動或寫壞了照套句。"""
    if client is None:
        return fallback(req)
    how = "在一場硬仗打到緊處時" if req.via == "seize" else "服下破境丹、閉門衝關時"
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"功夫：【{req.name}】，那一招〔{req.move}〕；當初立的意：「{req.intent}」；{how}破境。"},
    ]
    try:
        result = client.chat_structured(messages, LineReading, temperature=0.7, num_predict=LINE_PREDICT,
                                        required_fields=["line"], require_in_schema=True)
    except Exception:
        return fallback(req)
    return clean(result.line) or fallback(req)


def set_line(state: GameState, req: LineRequest, line: str) -> list[str]:
    """C 段：卡還是同一張、還沒寫過，才存回去（重驗）。"""
    card = state.player.ascension
    if card is None or card.art != req.art or card.line:
        return []
    card.line = clean(line) or fallback(req)
    return []


def dismiss(state: GameState) -> list[str]:
    state.player.ascension = None
    return []


def view(state: GameState) -> dict | None:
    card = state.player.ascension
    return card.model_dump() if card is not None else None
