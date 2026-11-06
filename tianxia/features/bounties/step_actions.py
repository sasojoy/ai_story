"""「你這一步」的委託與懸賞兩格（原本 tianxia/step.py 的 _STEP_CORE 與 _commission_items、_bounty_items、_bounty_place；全部拆包第 45 批）。
位置在核心的 STEP_ORDER：委託接在人物的託付後面、軍令前面，揭了的懸賞接在軍令後面、伏筆前面。REF、place 是核心本體 step 的。
規則照模組屬性叫（rules.open_commissions、rules.rallies：tests/core/test_contract_core.py 換這兩個，照樣打得到）。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import step

from . import rules

if TYPE_CHECKING:
    from tianxia.engine import Game


def commission_items(status: dict) -> list[dict]:
    """懸賞列裡的委託（書信附的、人物的求援；rules.status 組的 commission 列）：接在人物的託付後面、軍令前面。"""
    return [{"kind": "errand", "text": f"{b['title']}：{b['how']}", "who": b.get("issuer", ""), "reward": b.get("reward", ""),
             step.REF: ("errand", b.get("id"))} for b in status.get("bounties") or [] if b.get("commission")]


def bounty_items(status: dict) -> list[dict]:
    """手上揭了、還沒做完的懸賞（不是委託、沒有 have）：接在軍令後面、伏筆前面。"""
    return [{"kind": "bounty", "text": f"{b['title']}：{b['how']}", "reward": b.get("reward", ""), step.REF: ("bounty", b.get("id"))}
            for b in status.get("bounties") or [] if not b.get("commission") and not b.get("have")]


def bounty_place(game: Game, ref: tuple) -> tuple:
    """懸賞列上的那一張（懸賞榜的、人物的委託與求援）：(id, target, None)；找不到 (ref[1], None, None)。"""
    s, c = game.state, game.content
    pool = [*rules.open_commissions(s, c), *rules.rallies(s, c), *s.world.bounties]
    b = next((x for x in pool if x.id == ref[1]), None) if ref[1] else None
    if b is None:
        return ref[1], None, None
    return b.id, step.place(game, b.end if b.kind == "escort" else b.location if b.kind in ("strike", "scout") else None), None
