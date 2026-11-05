"""管理者救回人物（功能包 figure_acts；全部拆包第 31 批）：叫回選單、把一位退場或重創的大勢人物叫回來。原本 Game 上的 2 個方法，名字去掉前導底線、
第一個參數是 ctx。會改狀態。路由（/api/do/revive_figure、/api/admin 的 fallen）照舊在 server.py 叫 Game 的委派。
"""
from __future__ import annotations

from tianxia import figures  # 共用規則層（大勢人物 figures，第 40 批收進）


def fallen(ctx) -> list[str]:
    """管理者「叫回人物」的選單：這一季退場、重創的大勢人物（人物表的順序）。"""
    s, c = ctx.state, ctx.content
    return [fid for fid in c.figures if figures.is_out(s, fid)]


def revive_figure(ctx, fid: str) -> list[str]:
    """叫回人物（PM 2026-10-16，救二十人試玩被打光的官軍）：一位退場、重創的大勢人物現在就以 figure_return_share × 開季聲威
    回到他原本的戰線與所在（同 figures.revive：接位的人交還戰線），天下大事一句；公告不寫管理者。時刻表寫死的也叫得回來。"""
    refusal = ctx._admin_refusal("叫回人物")
    if refusal:
        return ctx._log(refusal)
    s, c = ctx.state, ctx.content
    if fid not in c.figures or not figures.is_out(s, fid):
        return ctx._log(["（這位人物此刻沒有退場。）"])
    now = s.world.figures[fid]
    now.back_at, now.back_front = s.world.time, now.back_front or now.front
    msgs = figures.revive(s, c)
    ctx._write("叫回人物", msgs, tag="管理者")
    ctx._save_season()
    return ctx._log(msgs)
