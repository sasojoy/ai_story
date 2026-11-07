"""玩法說明兩包以上要用的那幾樣（全部拆包第 59 批「引導二」；計畫 docs/superpowers/plans/2026-11-06-玩法說明-第59批.md 第一節）：
一節的寫法（section）、「一成、兩成」（tenth）、會推戰況的陣營（order_pushers）、「有些地方」那一句（SOME_PLACES）。各節都在各包的 howto.py，
包不准 import 包，共用的只好放核心（同 battle_base）；各檔 `import ... as _tenth` 這樣，本體一個字不動。同 event_check 不進 MODULES。
"""
from __future__ import annotations

from collections.abc import Sequence

from .. import rules
from ..models import Content

# 推線的那一句只說「有些地方」（FB-112）：推不推看地點的 train_trend（Game.train_trend_push），很多有對手的地方不推（潁水河畔），
# 行動列底下那一行（train_line 的 PUSH_WORD）照這一處的實情寫
SOME_PLACES = "有些地方遊歷打贏、操練會推動戰況（行動列底下那一行寫著這裡推不推）"


def tenth(share: float) -> str:
    """0.1 → 一成、0.2 → 兩成（rules.count_word）；不是整成照寫百分比。"""
    tenths = round(share * 10, 6)
    return f"{'兩' if tenths == 2 else rules.count_word(int(tenths))}成" if tenths == int(tenths) else f"{share * 100:g}%"


def section(title: str, lines: Sequence[str]) -> list[str]:
    """一節：標題與每一行一個項目；沒有句子就整節不寫。"""
    return [f"#### {title}", *[f"- {line}" for line in lines], ""] if lines else []


def order_pushers(content: Content) -> list[str]:
    """軍令湊滿額度時會推戰況的陣營（orders.json 的範本裡有 effect.trend > 0 的）；豪強只有打擊（挫聲威，不推線）。"""
    return [f.id for f in content.scenario.factions if any(t.side == f.id and t.effect.trend > 0 for t in content.orders.templates)]
