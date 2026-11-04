"""月旦評三段式的 A、C 兩段（功能包 figure_acts；全部拆包第 31 批）：A 是鎖內拿單子（只讀）、C 是鎖內重驗同一批才換上並發出去、再存回共用賽季。
B 段（server.yuedan_once → yuedan.write，鎖外請模型）不在這裡。原本 Game 上的 2 個方法。
"""
from __future__ import annotations

from . import yuedan


def request(ctx) -> yuedan.YuedanNote | None:
    """A 段（只讀）：這一週還沒發、還沒寫過評語的那一批。"""
    return yuedan.request(ctx.state, ctx.content)


def apply(ctx, note: yuedan.YuedanNote, lines: dict[str, str]) -> bool:
    """C 段：同一批才換上評語並發出去（天下大事、江湖史），存回共用賽季。"""
    done = yuedan.apply(ctx.state, ctx.content, note, lines)
    if done:
        ctx._save_season()
    return done
