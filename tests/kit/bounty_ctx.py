"""沒有 Game 的測試叫懸賞榜交差用的 ctx（全部拆包第 45 批：_done、on_*、_complete_rally、_complete_commission、commission_reward、status 第一個參數改 ctx）。
只有那幾個函式讀的：state、content、world，與人物情誼包的五個委派，接真的 letters、parley 函式。不開 Game：建構子會 open_world()、_drop_stale_references，那些測試要的是這一份 state 原樣。"""
from __future__ import annotations

from types import SimpleNamespace

from tianxia.features.companions import letters, parley


def bounty_ctx(state, content, world=None) -> SimpleNamespace:
    return SimpleNamespace(
        state=state, content=content, world=world,
        _letter_thank=lambda task: letters.thank(state, content, task),
        _parley_settle_task=lambda task_id, cid: parley.settle_task(state, content, task_id, cid),
        _parley_keep=lambda cid, cond: parley.keep(state, content, cid, cond),
        _parley_owed_line=lambda name: parley.COMMISSION_OWED.format(name=name),
        _parley_ask_label=lambda ask_id: parley.ask_label(content, ask_id),
    )
