"""玉璽碎片「讀」的那一小半（全部拆包第 27 批，PM 認定甲案；同第 34 批 omen_base、第 40 批 smith_base）：核心與決戰包不得不讀的純函式與字句
——開著沒有（on、revamp_on）、登記補齊（filled）、名號與持有者（key、holders）、天命之爭是哪一件哪一場、這一季是不是天命之季（mandate_event、
mandate_battle、is_mandate_battle、mandate_now）、保底收場（deserted）、天命未定的兩句、挑戰者門檻與「戰功居前」那一句（threshold、challenger_ok、
hint_names、merit_hint）、璽動那一句（stir_text）、天命之爭的起點偏移與那一句（lean_shift、lean_text、shift_text、MANDATE_SCENE、MANDATE_WEIGHT）、
江湖史七格（chronicle_block、sink_text 與 BOOK_*）。原本在 tianxia/seal.py，逐字搬來；玉璽包的 seal.py re-export 同一批函式物件與字句（名字一個不改），
所以經舊名 seal 讀的照舊拿得到。

誰讀：核心的 world.evaluate_ending（mandate_event）、world.end_season（MANDATE_UNSETTLED_END）、engine 的 admin_resolve_event（mandate_event、
mandate_battle）與 chronicle_text（on、chronicle_block、mandate_now）、決戰包的 view.py 與 progress.py。只讀，不寫（chronicle_block 先深拷貝再補齊）。
核心本體（tianxia/core/ 底下的檔），不進 MODULES。

測試或量表換掉的（scripts/measure_seal.py 換 seal.tier_for、seal.lean_shift，tests/acts/test_conquest_rules.py 換 seal.find）：tier_for、find
不搬來（只有玉璽包與第 28 批的 Game 方法讀，經舊名找得到換掉的那一份）；lean_shift 搬來了，玉璽包 seal._mandate_muster 照模組屬性找、換得到，
決戰包的畫面讀這裡的那一份（參數是集結那一刻的快照，算出來一樣）。
"""
from __future__ import annotations

from .. import treasures
from . import battle_base as battle_instance
from .battle_base import BattleInstance
from ..characters import name_key
from ..models import BattleDef, Content, SealTuning, TimetableEvent
from ..world_state import SealRegistry, SealShard


def on(content: Content) -> bool:
    """碎片開著：Config.seal.enabled，而且內容有 content/seal.json（測試內容沒有＝關著）。"""
    return content.config.seal.enabled and bool(content.seal)


def revamp_on(content: Content) -> bool:
    """改版第 1 批開著（docs/superpowers/specs/2026-10-21-玉璽碎片改版-design.md）：碎片開著、子開關 Config.seal.revamp.enabled 開著。
    常駐效果（戰力＋成長生活）與持有者平時藏起來都只問這一條（treasures.revamp_on 是同一條，treasures 不 import seal）。"""
    return on(content) and treasures.revamp_on(content)


def filled(reg: SealRegistry, content: Content) -> SealRegistry:
    """內容的七片在登記上都有一筆（登記沒有的用預設補上）；回傳同一份。"""
    for shard_id in content.seal:
        reg.shards.setdefault(shard_id, SealShard(id=shard_id))
    return reg


def key(name: str | None) -> str:
    return name_key(name or "")


def holders(reg: SealRegistry) -> set[str]:
    """手上有碎片的人（name_key）：挑人時擋「一人一片」。"""
    return {key(s.holder) for s in reg.shards.values() if s.state == "held" and s.holder}


def threshold(battle: BattleInstance, cfg: SealTuning) -> int:
    """現世得主與挑戰者要自己出手滿幾回合：min(3, 這一場實際打了幾回合)，至少 1（壓倒性收場 1～3 回合就打完，3.3）；
    參戰名單不到 small_battle 人時放寬到 1 回合（PM 癸）。"""
    if len(battle.participants) < cfg.small_battle:
        return 1
    return min(3, max(1, battle.round_number))


# ── 天命之季與天命之爭（玉璽二；設計第八節）──────────────────────

BOOK_ROUND = "### 傳國玉璽（第 {round} 輪）"  # 待 joy 潤：第二輪起江湖史七格的標題
BOOK_MANDATE = "這一季是天命之季。"  # 待 joy 潤


def mandate_event(content: Content) -> TimetableEvent | None:
    """這個劇本的天命之爭（時刻表上標 mandate_only 的那一件，8.5）；沒有是 None。"""
    return content.mandate_timetable[0] if content.mandate_timetable else None


def mandate_battle(content: Content) -> BattleDef | None:
    """天命之爭那一場決戰（battles.json 裡 timetable_event 指到它的那一筆）；沒有是 None。"""
    event = mandate_event(content)
    return next((b for b in content.battles.values() if event is not None and b.timetable_event == event.id), None)


def is_mandate_battle(content: Content, definition: BattleDef | None) -> bool:
    event = mandate_event(content)
    return event is not None and definition is not None and definition.timetable_event == event.id


def mandate_now(reg: SealRegistry, season: int) -> bool:
    """這一季是不是天命之季（登記那一份；季的規則看 WorldState.mandate，兩個由 stamp_mandate 一起蓋）。"""
    return reg.mandate_season is not None and reg.mandate_season == season


STIR = "此役牽動{holder}懷中的『{shard}』。"  # 待 joy 潤：天下大事、集結公告（4.3）
STIR_SCENE = "此役牽動{holder}懷中的『{shard}』：懷璽之人那一方若沒能大勝，打完之後陣前單挑。"  # 待 joy 潤：決戰畫面
MERIT_HINT = "你此役戰功居前；懷璽之人那一方若沒能大勝，你可能被推上陣前。"  # 待 joy 潤（4.3）
# 改版（持有者平時藏起來，企劃者 10/21）：璽動不點名（設計第三章「此役牽動〈X〉之主」）；字待 joy 潤
STIR_HIDDEN = "此役牽動『{shard}』之主。"  # 天下大事、集結公告
STIR_SCENE_HIDDEN = "此役牽動『{shard}』之主：懷璽之人那一方若沒能大勝，打完之後陣前單挑。"  # 決戰畫面
# 「戰功居前」兩軍都給（只給持有者對面那一軍的話，誰收到就看得出持有者站哪一軍）：對每個收到的人都是真話
MERIT_HINT_BOTH = "你此役戰功居前；若懷璽之人不在你這一方、而那一方沒能大勝，你可能被推上陣前。"


def stir_text(content: Content, holder: str, shard: str, scene: bool = False) -> str:
    """璽動那一句（scene：決戰畫面那一版）：改版開著不點名，關著照舊。"""
    if revamp_on(content):
        return (STIR_SCENE_HIDDEN if scene else STIR_HIDDEN).format(shard=shard)
    return (STIR_SCENE if scene else STIR).format(holder=holder, shard=shard)


def merit_hint(content: Content) -> str:
    """「戰功居前」那一句：改版開著兩軍都給（MERIT_HINT_BOTH），關著照舊（MERIT_HINT）。"""
    return MERIT_HINT_BOTH if revamp_on(content) else MERIT_HINT


def challenger_ok(p, need: int, held: set[str], holder: str | None) -> bool:
    """挑戰者與畫面那一句共用的條件（4.6；FB-177：挑人與畫面照同一條）：自己出手滿 need 回合、這一季沒叛投過、不在新手期
    （加入時的快照）、不是決戰補位的機器人、不是持有者本人、手上沒有碎片。倒下的不擋（挑人本來就不看倒下）。"""
    return (p.acted_rounds >= need and not p.turncoat and not p.newbie and not p.is_bot
            and key(p.name) not in held and key(p.name) != key(holder))


def hint_names(battle: BattleInstance, content: Content, held: set[str]) -> set[str]:
    """被璽動的那一場打到一半：交戰兩軍各自合格的人裡戰功前 challenger_pool 名（4.3）——合格照 challenger_ok（同挑挑戰者），
    陣營不跟持有者的快照相同（快照是 None 就不擋）。只給畫面那一句用，不決定誰上陣（那要看收場時誰贏）。
    改版開著（持有者平時藏起來）時不看持有者的陣營、兩軍都給（誰收到就看得出持有者站哪一軍），字換成有條件的 MERIT_HINT_BOTH；
    實際挑人不變，所以「被挑上的人一定收到過」照樣成立（FB-177）。"""
    definition = content.battles.get(battle.battle_id)
    if battle.seal_shard is None or definition is None:
        return set()
    tuning, cfg = content.config.battle, content.config.seal
    need = threshold(battle, cfg)
    hidden = revamp_on(content)
    out: set[str] = set()
    for side in (f.id for f in definition.factions):
        if not hidden and battle.seal_holder_faction is not None and side == battle.seal_holder_faction:
            continue
        rows = [
            (p.name, battle_instance.merit(tuning, p)) for p in battle.participants.values()
            if p.faction == side and challenger_ok(p, need, held, battle.seal_holder)
        ]
        out |= {name for name, _ in sorted(rows, key=lambda r: (-r[1], r[0]))[: cfg.challenger_pool]}
    return out


MANDATE_SCENE = "天命之爭：{lean}，{shift}{weight}。"  # 待 joy 潤：決戰畫面；weight 是 MANDATE_WEIGHT 或空字串
MANDATE_WEIGHT = "；懷璽的人到場，份量加重"  # 待 joy 潤：全服有人持有碎片才寫（FB-189：七片都沒人持有的天命之季不寫）
LEAN_PART = "{side}握著{n}片"  # 待 joy 潤
LEAN_NONE = "玉璽碎片不在交戰的任何一方手上"  # 待 joy 潤
LEAN_SHIFT = "戰局起點往{side}偏了 {n} 點"  # 待 joy 潤（FB-186）
LEAN_EVEN = "兩軍持璽相當，戰局起點不偏"  # 待 joy 潤：兩軍各有碎片、片數一樣
LEAN_STILL = "戰局起點不偏"  # 待 joy 潤：兩軍手上都沒有碎片
# FB-687（PM 2026-10-22）：領地爭奪開著的季，開集結那一刻先寫了「起點照戰況偏幾點」（conquest.front_rumor／front_scene），這裡講的是碎片
# 另外加的那一份，寫成「再」「不再另偏」，不跟前一句讀成矛盾。決戰那一列有 front_note 才換；關著的季照上面三句。待 joy 潤
LEAN_SHIFT_EXTRA = "起點再往{side}偏 {n} 點"
LEAN_EVEN_EXTRA = "兩軍持璽相當，起點不再另偏"
LEAN_STILL_EXTRA = "起點不再另偏"


def lean_shift(lean: dict[str, int], definition: BattleDef, cfg: SealTuning) -> int:
    """起點往握碎片的那一軍偏（8.3；PM 戊）：（第一軍 − 第二軍）× start_shift，夾在 ±start_shift_cap；第一軍（官軍）是正向
    （同 BattleDef.factions[0] 的約定）。"""
    first, second = definition.factions[0].id, definition.factions[1].id
    raw = (lean.get(first, 0) - lean.get(second, 0)) * cfg.mandate.start_shift
    return max(-cfg.mandate.start_shift_cap, min(cfg.mandate.start_shift_cap, raw))


def lean_text(lean: dict[str, int], definition: BattleDef) -> str:
    """「官軍握著2片、黃巾軍握著1片」（只寫兩軍，照 BattleDef 的名字）；都沒有寫 LEAN_NONE。"""
    parts = [LEAN_PART.format(side=f.name, n=lean[f.id]) for f in definition.factions if lean.get(f.id)]
    return "、".join(parts) or LEAN_NONE


def shift_text(shift: int, lean: dict[str, int], definition: BattleDef, extra: bool = False) -> str:
    """起點偏了幾點、往哪一軍偏（FB-186：以前只寫各握幾片，看不出戰局條動了沒）：正的往第一軍、負的往第二軍（同 lean_shift）。
    偏 0 時兩軍各有碎片寫 LEAN_EVEN，都沒有寫 LEAN_STILL；不寫「從正中開打」——偏移之前的起點照戰況，不一定在正中。
    extra：前面已經寫了「起點照戰況偏幾點」（決戰那一列有 front_note，領地爭奪開著的季），改寫成碎片「再」偏的那一份（FB-687）。"""
    first, second = definition.factions[0], definition.factions[1]
    moved, even, still = (LEAN_SHIFT_EXTRA, LEAN_EVEN_EXTRA, LEAN_STILL_EXTRA) if extra else (LEAN_SHIFT, LEAN_EVEN, LEAN_STILL)
    if shift:
        return moved.format(side=(first if shift > 0 else second).name, n=abs(shift))
    return even if lean.get(first.id) or lean.get(second.id) else still


SINK = "{holder}懷中的『{shard}』不知所蹤。"  # 待 joy 潤（7.6：不寫原因，真人假人一樣）
SINK_HIDDEN = "『{shard}』不知所蹤。"  # 待 joy 潤：改版（持有者平時藏起來）的江湖史；管理者的「隱沒判斷」照舊點名（SINK）
BOOK_TITLE = "### 傳國玉璽"  # 待 joy 潤：見聞→江湖史最上面（第十節）
BOOK_STATES = {"hidden": "未現世", "held": "{holder}懷中", "sunk": "不知所蹤"}
BOOK_HELD_HIDDEN = "已現世"  # 待 joy 潤：改版的七格（企劃者「平時藏起來」：只寫已現世，不寫誰持有）


def sink_text(content: Content, holder: str | None, shard: str) -> str:
    """隱沒那一句（江湖史）：改版開著不點名（SINK_HIDDEN；那一刻已經不在他手上，點名等於公開他一直拿到現在），關著照舊（SINK）。"""
    return (SINK_HIDDEN if revamp_on(content) else SINK).format(holder=holder, shard=shard)
BOOK_EVENTS = "這一輪的大事："
BOOK_BEFORE = "前史：{text}"


def deserted(battle: BattleInstance, definition: BattleDef) -> bool:
    """保底收場（end_without_fighters：兩軍都沒人還能打）：不打單挑、現世與喚回落空（4.5 邊界 3、3.3）；天命之爭是天命未定（8.3）。"""
    armies = {f.id for f in definition.factions}
    return not any(p.faction in armies and not p.eliminated and not p.away for p in battle.participants.values())


MANDATE_UNSETTLED_END = "天命未定：天命之爭沒有打成，這一季沒有分出天命。"  # 待 joy 潤：沒開成、取消，季末那一句
MANDATE_UNSETTLED_TITLE = "天命未定"  # 待 joy 潤：戰報標題


def chronicle_block(content: Content, reg: SealRegistry, before: str = "", mandate: bool = False) -> str:
    """見聞→江湖史最上面那一段（第十節）：七格玉璽（未現世、某某懷中、不知所蹤），這一輪的大事（現世、易主、守住、喚回、天命、隱沒，
    照登記的 text；舊資料沒有 round 當第 1 輪），最後一行前史（舊的 jade_seal_fragments，11.5；沒有就不寫）。第二輪起標題寫第幾輪；
    天命之季多一句（mandate）。Markdown。改版開著（revamp_on，企劃者「平時藏起來」）：有主的那一格只寫「已現世」、隱沒那一句不點名；
    現世、易主、守住、喚回、天命照舊（公開的大事與奪璽單挑那一場本身）。"""
    reg = filled(reg.model_copy(deep=True), content)
    now = [e for e in reg.history if (e.round or 1) == reg.round]
    states = dict(BOOK_STATES, held=BOOK_HELD_HIDDEN) if revamp_on(content) else BOOK_STATES
    cells = [f"- {content.seal[s].name}：{states[reg.shards[s].state].format(holder=reg.shards[s].holder or '')}" for s in content.seal]
    events = [e.text for e in now if e.text and e.kind in ("emerge", "take", "keep", "recall", "mandate")][-10:]
    sunk = [sink_text(content, e.other, content.seal[e.shard].name) for e in now if e.kind == "sink" and e.shard in content.seal]
    parts = [BOOK_TITLE if reg.round == 1 else BOOK_ROUND.format(round=reg.round)] + ([BOOK_MANDATE] if mandate else [])
    parts.append("\n".join(cells))
    if events or sunk:
        parts.append(BOOK_EVENTS + "\n" + "\n".join(f"- {t}" for t in events + sunk))
    if before:
        parts.append(BOOK_BEFORE.format(text=before))
    return "\n\n".join(parts)
