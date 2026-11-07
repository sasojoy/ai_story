"""玉璽包：玩法說明別節中間的兩處插句（全部拆包第 59 批；原 tianxia/howto.py，字一個不動；核心 HOWTO_INSERTS）：名聲的來源裡奪璽單挑那幾句（fame_seal）、
地盤那一節碎片的來源（land_seal）。"""
from __future__ import annotations

from tianxia.models import Content

from . import seal


def fame_seal(content: Content) -> list[str]:
    """名望、名聲的來源裡奪璽單挑那幾句（HOWTO_INSERTS 的 fame_seal；原本寫在 _fame_sources 中間）。"""
    cfg = content.config
    lines: list[str] = []
    if seal.on(content):  # 奪璽單挑（Game._file_seal，玉璽碎片設計 5.9）；待 joy 潤
        fame = cfg.seal.fame
        lines.append(f"奪璽單挑：懷璽的人守住了 +{fame['keep']}、被奪走 +{fame['lose']}；挑戰的人打贏了單挑、碎片卻沒易手 +{fame['near']}。")
        if seal.mandate_event(content) is not None and cfg.seal.mandate.fame > 0:  # 得天命的那一軍（Game._showdown_pay，玉璽二）
            lines.append(seal.MANDATE_FAME.format(fame=cfg.seal.mandate.fame))
    return lines


def land_seal(content: Content) -> list[str]:
    """地盤那一節倒數第二句：碎片的來源（HOWTO_INSERTS 的 land_seal；原本寫在 conquest_lines 中間）。"""
    lines: list[str] = []
    if seal.on(content):  # 第三批 B（設計 3.9）：碎片的來源；只說「在哪一類地方」，藏在哪一塊不公開；待 joy 潤
        lines.append("傳說傳國玉璽的碎片就藏在這些中立地的某一處：一季最多一片，到那裡探索（四種探索都算）才有極小的機會撿到，"
                     "藏在哪一處沒人知道；那一塊此刻若歸你的陣營，機會再高一點；剛易手、還在冷卻的地方撿不到。")
    return lines
