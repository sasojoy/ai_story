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
from .models import BattleDef, Content, SealTuning
from .state import Equipment, GameState, Rumor
from .world_state import SealEvent, SealRegistry, SealShard, WorldStateStore

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
    """登記記一筆（全服流水號 +1）。"""
    reg.seq += 1
    event = SealEvent(seq=reg.seq, season=season, kind=kind, **fields)
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


def on_muster(world: WorldStateStore, content: Content, definition: BattleDef, now: float) -> list[str]:
    """時刻表決戰剛開集結（world._open_claimed，不在任何 mutate 裡）：標 emerge 的擲現世、標了 seal 的擲璽動（Task 6）。
    一次 world.mutate 寫登記與天下大事，一次 mutate_battle 把結果快照進這一場；什麼都沒擲中就什麼都不寫。回傳集結公告要多的那幾句。"""
    mark = mark_of(content, definition) if on(content) else None
    if mark is None:
        return []
    got: dict[str, str | None] = {"emerge": None}
    msgs: list[str] = []

    def _apply(shared) -> None:
        reg = filled(shared.seal, content)
        if mark == "emerge":
            got["emerge"] = roll_emerge(reg, content, shared.season_number, shared.tianji)
            reg.force_emerge = None
        if got["emerge"] is not None:
            text = EMERGE_OMEN.format(battle=definition.name)
            rumor(shared.season, text)
            msgs.append(f"🏺 【天下大事】{text}")

    world.mutate(_apply)
    if got["emerge"] is None:
        return msgs

    def _snap(b) -> None:
        if b.battle_id == definition.id and b.phase == "muster":
            b.seal_emerge = got["emerge"]

    world.mutate_battle(_snap)
    return msgs
