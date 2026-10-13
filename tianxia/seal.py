"""玉璽碎片的規則（docs/superpowers/specs/2026-10-11-玉璽碎片-design.md；計畫 docs/superpowers/plans/2026-10-12-玉璽-1-核心.md）：
現世、璽動、挑人、易手的機率、隱沒、抄本、集結那一刻的寫入、字句。

- 全服登記（SharedWorldState.seal）是正本、跨季保存；角色身上的 PlayerState.heirloom 是抄本，同步時照登記重抄（copy_heirloom）。
- 擲骰一律用 dice（密鹽｜天機｜用途｜…，設計 5.13 的種子表），不碰 Game.rng。密鹽只在伺服器與假人程式啟動時用 secrets 產生
  （ensure_salt，server.main／run_bots.main 叫；計畫「要 PM 定的」第 8 條），引擎裡只讀：測試與量表腳本沒有密鹽（空字串），
  同樣的種子跑出同樣的結果。密鹽不顯示、不進指紋。每一份亂數取數的順序寫在用它的函式說明裡。
- 只 import models、state、world_state、battle_instance、treasures、characters；engine、world、sqlite_world 反過來叫這裡。
  on_muster 會寫 store：呼叫端不在任何 mutate 裡（world._open_claimed）。
"""
from __future__ import annotations

import random
import secrets

from . import battle_instance, treasures
from .battle_instance import BattleInstance
from .characters import name_key
from .models import BattleDef, Content, SealTuning, TimetableEvent
from .state import Equipment, GameState, Rumor
from .world_state import SealEvent, SealRegistry, SealShard, SharedWorldState, WorldStateStore

HEIRLOOM_PREFIX = "璽:"  # 抄本的 id（固定，不吃 weapon_serial，重抄幾次都一樣；不會跟「寶:N」撞號）
HEIRLOOM_LABEL = treasures.HEIRLOOM_LABEL  # 寶物段裡那一列的小標、角色卡那一行的開頭（字在 treasures，treasures 不 import seal）


def on(content: Content) -> bool:
    """碎片開著：Config.seal.enabled，而且內容有 content/seal.json（測試內容沒有＝關著）。"""
    return content.config.seal.enabled and bool(content.seal)


def filled(reg: SealRegistry, content: Content) -> SealRegistry:
    """內容的七片在登記上都有一筆（登記沒有的用預設補上）；回傳同一份。"""
    for shard_id in content.seal:
        reg.shards.setdefault(shard_id, SealShard(id=shard_id))
    return reg


def ensure_salt(reg: SealRegistry) -> bool:
    """產生密鹽（5.13）；已經有就不動。回傳有沒有新產生。只有 server.main 與 run_bots.main 啟動時叫（引擎裡不叫，見模組說明）。"""
    if reg.salt:
        return False
    reg.salt = secrets.token_hex(16)
    return True


def dice(salt: str, tianji: int, *parts: object) -> random.Random:
    """碎片的一份亂數：random.Random("密鹽|天機|用途|…")。"""
    return random.Random("|".join([salt, str(tianji), *(str(p) for p in parts)]))


def key(name: str | None) -> str:
    return name_key(name or "")


def shard_of(reg: SealRegistry, name: str) -> SealShard | None:
    """這個名號手上的那一片（一人最多一片）；沒有是 None。名號比對不分大小寫。"""
    k = key(name)
    return next((s for s in reg.shards.values() if s.state == "held" and s.holder and key(s.holder) == k), None)


def holders(reg: SealRegistry) -> set[str]:
    """手上有碎片的人（name_key）：挑人時擋「一人一片」。"""
    return {key(s.holder) for s in reg.shards.values() if s.state == "held" and s.holder}


def log(reg: SealRegistry, season: int, kind: str, **fields) -> SealEvent:
    """登記記一筆（全服流水號 +1）；記上這一輪（round）。"""
    reg.seq += 1
    event = SealEvent(seq=reg.seq, season=season, kind=kind, round=reg.round, **fields)
    reg.history.append(event)
    return event


def effect_text(content: Content, effect: str) -> str:
    """「練成的心得 ×0.9」（字在 treasures.SEAL_EFFECT_TEXT：treasures 不 import seal，字只留一份）。"""
    return treasures.seal_effect_text(content, effect)


def copy_heirloom(state: GameState, content: Content, reg: SealRegistry | None) -> None:
    """抄本照登記重抄（7.4）：登記說是你的就寫上，不是（或碎片關著、reg 是 None）就清掉；重抄幾次結果都一樣。順便設本人氣血上限的
    倍數（螭首）。碎片關著時呼叫端傳 None、不讀資料庫（Game._copy_heirloom）。"""
    p = state.player
    shard = shard_of(reg, p.name) if reg is not None and on(content) else None
    if shard is None or shard.id not in content.seal:
        p.heirloom = None
    else:
        p.heirloom = Equipment(
            slot="treasure", id=HEIRLOOM_PREFIX + shard.id, name=content.seal[shard.id].name, template=shard.id, heirloom=True,
        )
    p.member.cap_scale = treasures.amount(state, content, "hp_cap")


# 待 joy 潤（第三節的公告）
EMERGE_OMEN = "{battle}將起，地底異光隱現，傳言太平道藏下的一片玉璽碎片，將在此役現世。"
EMERGE_GOT = "{name}在{battle}陣前拾得傳國玉璽的一角——『{shard}』。"
EMERGE_LOST = "{battle}的異光又沉入了地底。"
EMERGE_NOTE = "此役有一片玉璽碎片現世，落在{name}手上。"  # 戰報那一行（seal_notes）


def mark_of(content: Content, definition: BattleDef) -> str | None:
    """這一場決戰在時刻表上標的 seal（emerge／stir）；不是時刻表決戰、沒標是 None（8.5：不寫死黃巾之亂的 id）。"""
    event = next((e for e in content.timetable if e.id == definition.timetable_event), None)
    return event.seal if event is not None else None


def roll_emerge(reg: SealRegistry, content: Content, season: int, tianji: int) -> str | None:
    """標 emerge 的那一場開集結時擲現世（3.2）：這一輪還有沒現世過的、這一季還沒現世過才擲；管理者的強制現世（force_emerge）
    略過機率，指定的那一片還沒現世就用它。亂數 seal-emerge|季別：先取機率（強制時不取）、再取哪一片。"""
    hidden = sorted(s.id for s in reg.shards.values() if s.state == "hidden")
    if not hidden or reg.emerge_season == season:
        return None
    rng = dice(reg.salt, tianji, "seal-emerge", season)
    if reg.force_emerge:
        return reg.force_emerge if reg.force_emerge in hidden else rng.choice(hidden)
    if rng.random() >= content.config.seal.emerge_chance:
        return None
    return rng.choice(hidden)


def threshold(battle: BattleInstance, cfg: SealTuning) -> int:
    """現世得主與挑戰者要自己出手滿幾回合：min(3, 這一場實際打了幾回合)，至少 1（壓倒性收場 1～3 回合就打完，3.3）；
    參戰名單不到 small_battle 人時放寬到 1 回合（PM 癸）。"""
    if len(battle.participants) < cfg.small_battle:
        return 1
    return min(3, max(1, battle.round_number))


def weighted_pick(rows: list[tuple[str, int]], rng: random.Random, pool: int, prefer: str | None = None) -> str | None:
    """合格的人照戰功取前 pool 名（同分照名號），prefer（追璽：上一次從這一片被奪走的人）在裡面就直接挑他，否則照戰功加權抽一位；
    戰功都是 0 就平均抽（4.6、3.3）。亂數取一次。"""
    top = sorted(rows, key=lambda row: (-row[1], row[0]))[:pool]
    if not top:
        return None
    if prefer is not None:
        hit = next((name for name, _ in top if key(name) == key(prefer)), None)
        if hit is not None:
            return hit
    weights = [max(0, merit) for _, merit in top]
    return rng.choices([name for name, _ in top], weights=weights if any(weights) else None)[0]


def emerge_rows(battle: BattleInstance, content: Content, winner: str, need: int, held: set[str], picked: set[str]) -> list[tuple[str, int]]:
    """現世得主的候選（3.3）：勝方的參戰者、自己出手滿 need 回合、手上沒有碎片、不是這一場剛被挑去單挑的人；不看新手期、不看假人。
    序章裡的人上不了決戰（FB-113），acted_rounds 是 0，自然擋掉。決戰補位的機器人（BattleParticipant.is_bot）不是角色，不算；伺服器假人的
    is_bot 一律是 False，照樣能得（4.6 最後一條講的是「不能拿 is_bot 判斷伺服器假人」）。戰功照 Joy 的 battle_instance.merit。"""
    tuning = content.config.battle
    return [
        (p.name, battle_instance.merit(tuning, p)) for p in battle.participants.values()
        if p.faction == winner and p.acted_rounds >= need and not p.is_bot and key(p.name) not in held and key(p.name) not in picked
    ]


def rumor(season, text: str) -> None:
    """天下大事（world 層、具名）。season 是 WorldState（mutate 裡的那一份）。"""
    season.rumors.append(Rumor(time=season.time, text=text, layer="world"))


def chronicle(season, text: str) -> None:
    season.chronicle.append(Rumor(time=season.time, text=text))


# ── 天命之季與天命之爭（玉璽二；設計第八節）──────────────────────

MANDATE_OPEN = "七片玉璽都已現世過了。天命之季到來：這一季的大戰都會牽動玉璽碎片，季末之前，{battle}要爭一個天命。"  # 待 joy 潤
SCATTER = "天命之季過去，七片玉璽再度散落天下。"  # 待 joy 潤：江湖史（8.4）
SCATTER_MINE = "你懷中的『{shard}』化光而去：七片玉璽再度散落天下。"  # 待 joy 潤：補送的紀錄
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


def mandate_due(reg: SealRegistry, content: Content) -> bool:
    """下一季該不該蓋天命之季的章（8.1；PM 己：七片這一輪都現世過——有主的、隱沒的都算）；上一次延後的、管理者「下一季」的
    （mandate_pending）也算。reg 要先 filled。"""
    if reg.mandate_pending:
        return True
    return bool(content.seal) and all(reg.shards[s].emerged_round == reg.round for s in content.seal if s in reg.shards)


def stamp_mandate(shared: SharedWorldState, content: Content, at: float) -> str:
    """把 shared.season 蓋成天命之季（8.1）：WorldState.mandate、天命之爭排在 at（世界秒；呼叫端照 timetable.default_time 算）、
    登記記下季別、清掉延後的記號；天下大事與江湖史各一句。只改傳進來的 shared（next_season 手動 _load／_save、管理者在 world.mutate 裡），
    呼叫端先確認 mandate_event 不是 None。回那一句。"""
    event, battle = mandate_event(content), mandate_battle(content)
    reg = filled(shared.seal, content)
    season = shared.season
    season.mandate, season.mandate_result = True, None
    season.schedule[event.id] = at
    reg.mandate_season, reg.mandate_pending = shared.season_number, False
    text = MANDATE_OPEN.format(battle=battle.name if battle is not None else event.title)
    rumor(season, text)
    chronicle(season, text)
    return text


def scatter(reg: SealRegistry, season: int) -> list[str]:
    """天命之季之後的換季：七片全部回到未現世（8.4）——持有者、新主保護、動過、現世過、追璽、缺席都清掉，round +1，強制現世／璽動
    與延後的記號也清掉。手上有碎片的人各記一筆 scatter（同步時補一句、抄本照登記清掉）。回原本的持有者。"""
    former = []
    for shard in sorted(reg.shards.values(), key=lambda s: s.id):
        if shard.state == "held" and shard.holder:
            former.append(shard.holder)
            log(reg, season, "scatter", shard=shard.id, other=shard.holder)
        shard.state, shard.holder, shard.since_season, shard.stirred_season = "hidden", None, None, None
        shard.emerged_round, shard.former, shard.absent = None, None, 0
    reg.round += 1
    reg.emerge_season, reg.force_emerge, reg.force_stir, reg.mandate_pending = None, None, None, False
    return former


STIR = "此役牽動{holder}懷中的『{shard}』。"  # 待 joy 潤：天下大事、集結公告（4.3）
STIR_SCENE = "此役牽動{holder}懷中的『{shard}』：懷璽之人那一方若沒能大勝，打完之後陣前單挑。"  # 待 joy 潤：決戰畫面
STIR_MINE = "此役牽動你懷中的『{shard}』。"  # 待 joy 潤：持有者的碎片卡（Task 10）
MERIT_HINT = "你此役戰功居前；懷璽之人那一方若沒能大勝，你可能被推上陣前。"  # 待 joy 潤（4.3）


def roll_stir(reg: SealRegistry, content: Content, season: int, tianji: int, event_id: str, mandate: bool = False) -> str | None:
    """標了 seal 的決戰開集結時擲璽動（4.1、4.2）：有主、不是這一季才到手、這一季還沒動過的每一片各擲 stir_chance
    （seal-stir|event_id|片，各取一次）；全服這一季已經動了 season_stir_cap 次就不擲；擲中好幾片時用 seal-stir|event_id 挑一片。
    管理者的強制璽動（force_stir）略過機率、新主保護與次數上限（那一片要有主）。mandate：天命之季，見下（玉璽二）。"""
    cfg = content.config.seal
    forced = reg.shards.get(reg.force_stir or "")
    if forced is not None and forced.state == "held":
        return forced.id
    if mandate:  # 天命之季（8.2；PM 丙）：每場必定牽動一片——不擲 stir_chance、沒有新主保護、沒有全服上限；每片每季照舊最多一次
        pool = sorted(s.id for s in reg.shards.values() if s.state == "held" and s.stirred_season != season)
        return dice(reg.salt, tianji, "seal-mandate", event_id).choice(pool) if pool else None
    if sum(1 for e in reg.history if e.kind == "stir" and e.season == season) >= cfg.season_stir_cap:
        return None
    hit = [
        s.id for s in sorted(reg.shards.values(), key=lambda s: s.id)
        if s.state == "held" and s.since_season != season and s.stirred_season != season
        and dice(reg.salt, tianji, "seal-stir", event_id, s.id).random() < cfg.stir_chance
    ]
    if len(hit) <= 1:
        return hit[0] if hit else None
    return dice(reg.salt, tianji, "seal-stir", event_id).choice(hit)


def tier_for(holder_side: str | None, winner: str, margin: str) -> str:
    """持有者那一方打得怎樣（4.5）：自己這方贏是大勝或險勝，對方贏是險敗（對方險勝）或大敗（對方大勝）；快照不在交戰兩方是旁觀。"""
    if holder_side is None:
        return "旁觀"
    if winner == holder_side:
        return "大勝" if margin == "大勝" else "險勝"
    return "大敗" if margin == "大勝" else "險敗"


def challenger_ok(p, need: int, held: set[str], holder: str | None) -> bool:
    """挑戰者與畫面那一句共用的條件（4.6；FB-177：挑人與畫面照同一條）：自己出手滿 need 回合、這一季沒叛投過、不在新手期
    （加入時的快照）、不是決戰補位的機器人、不是持有者本人、手上沒有碎片。倒下的不擋（挑人本來就不看倒下）。"""
    return (p.acted_rounds >= need and not p.turncoat and not p.newbie and not p.is_bot
            and key(p.name) not in held and key(p.name) != key(holder))


def hint_names(battle: BattleInstance, content: Content, held: set[str]) -> set[str]:
    """被璽動的那一場打到一半：交戰兩軍各自合格的人裡戰功前 challenger_pool 名（4.3）——合格照 challenger_ok（同挑挑戰者），
    陣營不跟持有者的快照相同（快照是 None 就不擋）。只給畫面那一句用，不決定誰上陣（那要看收場時誰贏）。"""
    definition = content.battles.get(battle.battle_id)
    if battle.seal_shard is None or definition is None:
        return set()
    tuning, cfg = content.config.battle, content.config.seal
    need = threshold(battle, cfg)
    out: set[str] = set()
    for side in (f.id for f in definition.factions):
        if battle.seal_holder_faction is not None and side == battle.seal_holder_faction:
            continue
        rows = [
            (p.name, battle_instance.merit(tuning, p)) for p in battle.participants.values()
            if p.faction == side and challenger_ok(p, need, held, battle.seal_holder)
        ]
        out |= {name for name, _ in sorted(rows, key=lambda r: (-r[1], r[0]))[: cfg.challenger_pool]}
    return out


DUEL_NOTE = "璽動：{challenger}將與懷璽的{holder}陣前單挑。"  # 決戰的戰報那一行（5.9 最後一條）
NO_DUEL = "{holder}懷中的『{shard}』安然無恙，懷璽不失。"  # 大勝不打、對面無人能上前、保底收場（只寫天下大事，5.9）


MANDATE_MUSTER = "{battle}集結：{lean}。"  # 待 joy 潤：天下大事、集結公告（8.3）
MANDATE_SCENE = "天命之爭：{lean}；懷璽的人到場，份量加重。"  # 待 joy 潤：決戰畫面
LEAN_PART = "{side}握著{n}片"  # 待 joy 潤
LEAN_NONE = "玉璽碎片不在交戰的任何一方手上"  # 待 joy 潤


def mandate_lean(world: WorldStateStore, content: Content, definition: BattleDef) -> dict[str, int]:
    """天命之爭開集結那一刻：能站的每一方各握幾片（持有者照這一季的投靠名冊，不讀存檔；散人、隱沒的不算）。第三方也數（畫面與
    之後的「群雄得璽」用；起點只看兩軍，lean_shift）。"""
    sides = battle_instance.sides(definition)
    out: dict[str, int] = {}
    for shard in world.seal_state().registry.shards.values():
        if shard.state == "held" and shard.holder and shard.id in content.seal:
            side = world.faction_of(shard.holder)
            if side in sides:
                out[side] = out.get(side, 0) + 1
    return out


def lean_shift(lean: dict[str, int], definition: BattleDef, cfg: SealTuning) -> int:
    """起點往握碎片的那一軍偏（8.3；PM 戊）：（第一軍 − 第二軍）× start_shift，夾在 ±start_shift_cap；第一軍（官軍）是正向
    （同 BattleDef.factions[0] 的約定）；豪強不推。"""
    first, second = definition.factions[0].id, definition.factions[1].id
    raw = (lean.get(first, 0) - lean.get(second, 0)) * cfg.mandate.start_shift
    return max(-cfg.mandate.start_shift_cap, min(cfg.mandate.start_shift_cap, raw))


def lean_text(lean: dict[str, int], definition: BattleDef) -> str:
    """「官軍握著2片、黃巾軍握著1片」（只寫兩軍，照 BattleDef 的名字）；都沒有寫 LEAN_NONE。"""
    parts = [LEAN_PART.format(side=f.name, n=lean[f.id]) for f in definition.factions if lean.get(f.id)]
    return "、".join(parts) or LEAN_NONE


def _mandate_muster(world: WorldStateStore, content: Content, definition: BattleDef) -> list[str]:
    """天命之爭剛開集結：數兩軍各握幾片、照它把起點（trend 與 trend_start）偏過去、快照進這一場（seal_lean），天下大事一句。
    天命之爭本身不璽動、不現世（8.3）。"""
    lean = mandate_lean(world, content, definition)
    shift = lean_shift(lean, definition, content.config.seal)
    text = MANDATE_MUSTER.format(battle=definition.name, lean=lean_text(lean, definition))
    world.mutate(lambda shared: rumor(shared.season, text))

    def _snap(b) -> None:
        if b.battle_id == definition.id and b.phase == "muster":
            b.seal_lean = dict(lean)
            b.trend = b.trend_start = max(0, min(100, b.trend + shift))

    world.mutate_battle(_snap)
    return [f"🏺 【天下大事】{text}"]


def on_muster(world: WorldStateStore, content: Content, definition: BattleDef, now: float) -> list[str]:
    """時刻表決戰剛開集結（world._open_claimed，不在任何 mutate 裡）：標 emerge 的擲現世、標了 seal 的擲璽動（Task 6）。
    一次 world.mutate 寫登記與天下大事，一次 mutate_battle 把結果快照進這一場；什麼都沒擲中就什麼都不寫。回傳集結公告要多的那幾句。
    天命之爭（玉璽二）另走 _mandate_muster。"""
    if not on(content):
        return []
    if is_mandate_battle(content, definition):  # 天命之爭（8.3）
        return _mandate_muster(world, content, definition)
    mark = mark_of(content, definition)
    if mark is None:
        return []
    got: dict[str, str | None] = {"emerge": None, "stir": None, "holder": None, "faction": None}
    msgs: list[str] = []

    def _apply(shared) -> None:
        reg = filled(shared.seal, content)
        mandate = shared.season.mandate
        if mark == "emerge" and not mandate:  # 天命之季不擲現世（8.2、3.2），管理者的強制現世記號留到下一個一般季
            got["emerge"] = roll_emerge(reg, content, shared.season_number, shared.tianji)
            reg.force_emerge = None
        if got["emerge"] is not None:
            text = EMERGE_OMEN.format(battle=definition.name)
            rumor(shared.season, text)
            msgs.append(f"🏺 【天下大事】{text}")
        stir = roll_stir(reg, content, shared.season_number, shared.tianji, definition.timetable_event, mandate=mandate)
        if stir is not None and stir == reg.force_stir:
            reg.force_stir = None
        if stir is not None:
            shard = reg.shards[stir]
            shard.stirred_season = shared.season_number
            holder = shard.holder or ""
            faction = world.faction_of(holder)  # 投靠名冊（這一季），不讀存檔裡的 p.faction（4.3）；mutate 裡也讀得到（同 faction_counts）
            got.update(stir=stir, holder=holder, faction=faction)
            log(reg, shared.season_number, "stir", shard=stir, holder=holder)
            text = STIR.format(holder=holder, shard=content.seal[stir].name)
            rumor(shared.season, text)
            msgs.append(f"🏺 【天下大事】{text}")

    world.mutate(_apply)
    if got["emerge"] is None and got["stir"] is None:
        return msgs

    def _snap(b) -> None:
        if b.battle_id == definition.id and b.phase == "muster":
            b.seal_emerge = got["emerge"]
            if got["stir"] is not None:
                armies = {f.id for f in definition.factions}
                b.seal_shard, b.seal_holder, b.seal_holder_faction = got["stir"], got["holder"], got["faction"]
                b.seal_holder_side = got["faction"] if got["faction"] in armies else None

    world.mutate_battle(_snap)
    return msgs


SINK = "{holder}懷中的『{shard}』不知所蹤。"  # 待 joy 潤（7.6：不寫原因，真人假人一樣）
BOOK_TITLE = "### 傳國玉璽"  # 待 joy 潤：見聞→江湖史最上面（第十節）
BOOK_STATES = {"hidden": "未現世", "held": "{holder}懷中", "sunk": "不知所蹤"}
BOOK_EVENTS = "這一輪的大事："
BOOK_BEFORE = "前史：{text}"
SEAL_TITLE = "玉璽碎片"  # 待 joy 潤：補送的江湖紀錄標題
GOT = "你得到了傳國玉璽的一角——『{shard}』（{effect}）。"
LOST = "你懷中的『{shard}』被{other}奪走了。"
WON = "你從{other}懷中奪得了『{shard}』。"
KEPT = "你擋下了{other}，『{shard}』還在你懷中。"
MISSED = "你力挫{other}，『{shard}』卻終究落回他懷中。"
FAILED = "你沒能從{other}懷中奪下『{shard}』。"
UNSETTLED_MINE = "你與{other}爭『{shard}』的單挑沒有打完，不分勝負。"
SUNK_MINE = "你懷中的『{shard}』不知所蹤了。"
PROXY_LINE = "你未及趕到，由你平日的路數應對。"
FRESH_LINE = "你這一季還沒現身江湖，身手生疏。"
RECALL = "{name}在{battle}陣前尋回了不知所蹤的『{shard}』。"  # 待 joy 潤：天下大事、江湖史（8.2）
RECALLED_MINE = "你在{where}陣前尋回了『{shard}』（{effect}）。"  # 待 joy 潤：補送的紀錄
CARD_MANDATE = "天命之季：此季每場大戰都可能牽動碎片"  # 待 joy 潤：持有者的碎片卡


def deserted(battle: BattleInstance, definition: BattleDef) -> bool:
    """保底收場（end_without_fighters：兩軍都沒人還能打）：不打單挑、現世與喚回落空（4.5 邊界 3、3.3）；天命之爭是天命未定（8.3）。"""
    armies = {f.id for f in definition.factions}
    return not any(p.faction in armies and not p.eliminated and not p.away for p in battle.participants.values())


def recall_events(content: Content) -> list[str]:
    """喚回的那幾場（8.2、8.5）：時刻表上標了 seal 的決戰照順序取前 recall_battles 場（不寫死 id；天命之爭本身沒標 seal）。"""
    return [e.id for e in content.timetable if e.seal is not None][: content.config.seal.mandate.recall_battles]


def roll_recall(reg: SealRegistry, tianji: int, event_id: str, rows: list[tuple[str, int]], pool: int) -> tuple[str, str] | None:
    """喚回哪一片、給誰（8.2）：隱沒的照 id 排序挑一片，再照現世的抽法（weighted_pick）從 rows 抽一人；亂數 seal-recall|event_id，
    先挑片、再抽人。沒有隱沒的、或沒有合格的人是 None（留著隱沒）。"""
    sunk = sorted(s.id for s in reg.shards.values() if s.state == "sunk")
    if not sunk:
        return None
    rng = dice(reg.salt, tianji, "seal-recall", event_id)
    shard = rng.choice(sunk)
    name = weighted_pick(rows, rng, pool)
    return (shard, name) if name is not None else None


MANDATE_WON = "天命歸於{side}。"  # 待 joy 潤：天下大事、江湖史（8.3）
MANDATE_NAMES = "合璽之人：{names}。"  # 待 joy 潤：接在上一句後面（那一刻手上有碎片的人，照 content/seal.json 的順序）
MANDATE_UNSETTLED = "天命未定：{battle}沒有分出天命。"  # 待 joy 潤：保底收場
MANDATE_UNSETTLED_END = "天命未定：天命之爭沒有打成，這一季沒有分出天命。"  # 待 joy 潤：沒開成、取消，季末那一句
MANDATE_UNSETTLED_TITLE = "天命未定"  # 待 joy 潤：戰報標題
MANDATE_MINE = "天命之爭那一刻，『{shard}』在你懷中：你以合璽之人留名。"  # 待 joy 潤：補送的紀錄
MANDATE_FAME = "天命之爭：得天命的那一軍出陣的人 +{fame}。"  # 待 joy 潤：玩法說明「名望」那一節（howto）
CARD_NEW, CARD_STIRRED, CARD_CALM = "新得之季，此季不動", "此季已動過", "此季可能被牽動"


def sink(reg: SealRegistry, season: int, seen: dict[str, float | None], now: float, cfg: SealTuning) -> list[tuple[SealShard, str]]:
    """換季那一刻判隱沒（7.6；PM 庚：連續 sink_seasons 季沒上線、而且距上次上線滿 sink_days 天）。seen：持有者名號 → 最後一次自己上線的
    現實秒（seen_real，舊存檔退回 last_real；查不到那一列是 None，當成沒上線而且已滿）。剛結束那一季持有者沒上線就 absent +1、上線了歸零；
    opened_real 是 None（判斷不了）不動。回這一次沉下去的（那一片, 原本的持有者），登記已經改好、各記一筆 sink。"""
    if reg.opened_real is None:
        return []
    out = []
    for shard in sorted((s for s in reg.shards.values() if s.state == "held" and s.holder), key=lambda s: s.id):
        last = seen.get(shard.holder)
        shard.absent = shard.absent + 1 if last is None or last < reg.opened_real else 0
        if shard.absent >= cfg.sink_seasons and (last is None or now - last >= cfg.sink_days * 86400):
            name = shard.holder
            shard.state, shard.holder, shard.absent = "sunk", None, 0
            log(reg, season, "sink", shard=shard.id, other=name)
            out.append((shard, name))
    return out


def chronicle_block(content: Content, reg: SealRegistry, before: str = "", mandate: bool = False) -> str:
    """見聞→江湖史最上面那一段（第十節）：七格玉璽（未現世、某某懷中、不知所蹤），這一輪的大事（現世、易主、守住、喚回、天命、隱沒，
    照登記的 text；舊資料沒有 round 當第 1 輪），最後一行前史（舊的 jade_seal_fragments，11.5；沒有就不寫）。第二輪起標題寫第幾輪；
    天命之季多一句（mandate）。Markdown。"""
    reg = filled(reg.model_copy(deep=True), content)
    now = [e for e in reg.history if (e.round or 1) == reg.round]
    cells = [f"- {content.seal[s].name}：{BOOK_STATES[reg.shards[s].state].format(holder=reg.shards[s].holder or '')}" for s in content.seal]
    events = [e.text for e in now if e.text and e.kind in ("emerge", "take", "keep", "recall", "mandate")][-10:]
    sunk = [SINK.format(holder=e.other, shard=content.seal[e.shard].name) for e in now if e.kind == "sink" and e.shard in content.seal]
    parts = [BOOK_TITLE if reg.round == 1 else BOOK_ROUND.format(round=reg.round)] + ([BOOK_MANDATE] if mandate else [])
    parts.append("\n".join(cells))
    if events or sunk:
        parts.append(BOOK_EVENTS + "\n" + "\n".join(f"- {t}" for t in events + sunk))
    if before:
        parts.append(BOOK_BEFORE.format(text=before))
    return "\n\n".join(parts)
