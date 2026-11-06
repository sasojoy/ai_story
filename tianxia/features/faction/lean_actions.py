"""豪強改幫（三陣營四勝利，設計 3.2；全部拆包第 35 批；原本是 Game 上的 _lean_options、_lean_anytime、_lean_step，本體一字沒改，self 換成 ctx）。
Game 留一行委派的：_lean_options（選單原位在叫）、_lean_anytime（choose 查選單之前不在選單上的「改幫…」）；_lean_step 只有投靠那一串叫（join_actions.faction_step）。
"""
from __future__ import annotations

from tianxia import wins
from tianxia.core import bounty_base
from tianxia.core.option import Option
from .ending_actions import four_wins


def lean_options(ctx) -> list[Option]:
    """本週卡「改幫…」（三陣營四勝利，設計 3.2）：豪強能幫、此刻沒在幫的那幾軍各一顆，不花體力、隨時換、不算叛投。
    按不下去（wins.lean_problem）灰著寫原因。開關關著、不是豪強是空的。"""
    s, c = ctx.state, ctx.content
    if not four_wins(ctx) or not wins.is_gentry(s.player, c):
        return []
    opts = []
    for side in wins.lean_sides(s.player, c):
        label = wins.LEAN_BUTTON.format(side=c.scenario.faction_name(side, side))
        problem = wins.lean_problem(s.player, c, side)
        opts.append(Option(id=f"{wins.LEAN_PREFIX}{side}", label=f"{label}（{problem}）" if problem else label, enabled=not problem))
    return opts


def lean_anytime(ctx, option_id: str) -> Option | None:
    """「改幫…」不看此地的選單（設計 3.2「隨時換」，FB-812）：選單上沒有它的時候（在路上、人站在正在打決戰的大區，
    選單只剩那些事）照樣收（有事件待選是例外，choose 擋：FB-820），條件跟選單上的那一顆一樣（lean_options：豪強、四勝利開著，按不下去的原因照 wins.lean_problem）。
    只有賽季不在跑（籌備中、休季、時鐘暫停，這幾種選單本來就只剩一顆灰的）才不收；開關關著、不是豪強、本來就幫它、
    不是它能幫的那一軍，都找不到那一顆，照舊「此刻無法這麼做」。決戰那一場的戰功照舊記參戰那一軍，開打了這一場照舊站原來那一邊
    （lean_step 的 _ally_follows_battle）。"""
    if ctx.world.paused_at() is not None or ctx._preparing() or ctx.state.world.ended:
        return None
    return next((o for o in lean_options(ctx) if o.id == option_id), None)


def lean_step(ctx, side: str) -> list[str]:
    """豪強改幫 side（wins.set_lean：寫 ally、換邊次數 +1，不算叛投、帳不清）。跟著換的：活躍名單搬到新的那一邊（人數緩衝照新的
    那一邊算），決戰集結中參戰名單跟著換、開打了這一場照舊（_ally_follows_battle，FB-273），手上揭著、新的那一邊接不了的
    懸賞作廢、每張一句（不扣東西，PM 2026-10-25 第 4 件）。投靠名冊由 choose() 結尾的 _record_faction 改記。不發傳聞；
    江湖紀錄就是這一下的那一則（choose 寫）。"""
    s, c = ctx.state, ctx.content
    p, w = s.player, s.world
    old = p.ally
    if not four_wins(ctx) or not wins.set_lean(p, c, side):
        return ["（此刻無法這麼做。）"]
    names = w.active_pushers.get(old or "")
    if names is not None and p.name in names:
        w.active_pushers.setdefault(side, {})[p.name] = names.pop(p.name)
        if not names:
            del w.active_pushers[old]
    new_name = c.scenario.faction_name(side, side)
    msgs = [wins.LEAN_DONE.format(side=new_name, old=c.scenario.faction_name(old, old) if old else new_name)]
    return msgs + bounty_base.drop_stranded(s, c, side, lean=True) + ctx._ally_follows_battle()  # 作廢那一句寫「改幫」，不是投靠、叛投的「改投」（FB-811）
