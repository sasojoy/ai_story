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

from .characters import name_key
from .models import Content
from .world_state import SealEvent, SealRegistry, SealShard


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
