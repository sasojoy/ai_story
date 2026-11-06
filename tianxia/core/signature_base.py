"""本命兵器「清失效參照」那一小半（core_seams，全部拆包第 55 批：裝備包 features/gear/signature_arms.py 的 owned、refresh_names 原樣搬來，包 re-export 同一批，
照第 40 批 smith_base 的前例）：核心的 _drop_stale_references（stale.mid 的 signature 那一格）讀它，不經舊名 signature_arms。原位不看開關（四欄都關著時 GearFeature.enabled
是 False，接 on_drop_stale 就不跑了），所以放這裡。核心本體（tianxia/core/ 底下的檔），不進 MODULES。

反方向（第 36 批認定第 1 條）：解 base、head 比過 test_for.pick（features/gear/signature_arms.py、seats、treasures、forge_secrets、plans、ranks、equipment、mounts），
一個都沒少挑；改這一檔 test_for 照舊挑到 tests/gear/test_signature_arms.py 與核心測試。
"""
from __future__ import annotations

from ..models import Content
from ..state import Equipment, PlayerState


def owned(p: PlayerState) -> list[Equipment]:
    """身上、裝備庫、寄放的本命兵器。"""
    return [item for item in (p.weapon, *p.rack, *p.held_gear) if item is not None and item.signature is not None]


def refresh_names(p: PlayerState, content: Content) -> None:
    """讀檔時照內容重寫本命兵器的名字（name 只當備份；同 treasures.refresh_names）：joy 改了名字，手上的跟著改；內容拿掉了那一把
    留著舊名字（加成照神器原品，不看內容）。Game._drop_stale_references 每次建 Game 都叫。"""
    table = {arm.character: arm for arm in content.gear.signature_arms}
    for item in owned(p):
        arm = table.get(item.signature)
        if arm is not None:
            item.name = arm.name
