"""機緣的動作（功能包 military；全部拆包第 34 批「軍情二」）：集體密謀的結算、管理者給機緣、閒著的選單上機緣的選項、遊歷打贏記密謀一處、
第 2 階行動的名字、管理者頁的機緣選單、對話的機緣話題、第 2 階與守勢行動之後記次數。規則本體在 opp_rules.py（原本的 tianxia/opportunities.py）。
原本 Game 上的 settle_plots（_settle_plots）、give_opportunity（admin_give_opportunity）；其餘是核心原位要問機緣的地方（選單位置、標題、打贏之後、
管理者頁、別的包），Game 留一行委派回答，第一個參數是 ctx。
"""
from __future__ import annotations

from tianxia.core.services import NO_SUCH_PLAYER

from . import opp_rules

# 管理者給的伏筆片段、機緣線索在那個玩家江湖紀錄裡那一則的標題（自然聽到的時候句子也不說是哪一個機緣、不說是管理者給的，審查 M-1）。
# 玩家看得到：新寫，待 joy 潤（原本寫在 engine.py；管理者給片段的 fs_actions 也用它）
HEARD_TITLE = "聽聞"


def settle_plots(ctx) -> list[str]:
    """集體密謀的結算（正式版乙二；opportunities.settle）：賽季時鐘暫停中不結算。暫停時畫面照常可看、計時器的同步照常走
    （sync 不經 _refuse_while_paused），動作被擋；結算會記貢獻、完成機緣，那是動作的結果，所以也等繼續之後的第一次同步。"""
    if ctx.world.paused_at() is not None:
        return []
    return opp_rules.settle(ctx.state, ctx.content)


def give_opportunity(ctx, name: str, opp_id: str) -> list[str]:
    """給他一個機緣：放到這一種機緣自然送上門那一刻之後的樣子（opportunities.offer，每一種用自然那條路的同一個函式；
    集體密謀型沒有那一刻，拒絕）。別的陣營的、完成過的、階不夠的、已經給過的都拒絕。"""
    refusal = ctx._admin_refusal("給機緣")
    if refusal:
        return ctx._log(refusal)
    if not opp_rules.active(ctx.state, ctx.content):
        return ctx._log(["（這一季沒有機緣。）"])
    o = next((x for x in ctx.content.opportunities if x.id == opp_id), None)
    if o is None:
        return ctx._log(["（沒有這個機緣。）"])
    target = ctx._admin_target(name)
    if target is None:
        return ctx._log([NO_SUCH_PLAYER.format(name=name.strip())])
    s = target.state
    why = opp_rules.offer_refusal(s, ctx.content, o, ctx.world)
    if why is None:
        lines, done = opp_rules.offer(s, ctx.content, o, ctx.world)
        # 聽到的（線索、內鬼的特徵）照自然聽到的樣子，不說是哪一個機緣；其他照機緣的寫法。都不標管理者（審查 M-1）
        heard = o.kind in opp_rules.HEARD_KINDS
        target._write(HEARD_TITLE if heard else opp_rules.title(s, ctx.content, f"offer:{o.id}"), lines)
    ctx._save_target(target)
    if why is not None:
        return ctx._log([why])
    msg = f"已給{s.player.name}機緣「{o.name}」：{done}。"
    ctx._write("給機緣", [msg], tag="管理者")
    return ctx._log([msg])


def place_options(ctx, loc_id: str) -> list:
    """閒著的選單上機緣的選項：交東西、天時地利、拼圖、推理、密謀（正式版乙一）。核心原位夾在 _rank_action_options 與伏筆最後一步、託付之間。"""
    return opp_rules.place_options(ctx.state, ctx.content, loc_id)


def on_win(ctx, front, faction) -> list[str]:
    """遊歷打贏之後記密謀的一處（三路並進，正式版乙二）：核心 _squad_encounter 夾在軍令記功與懸賞討伐之間。"""
    return opp_rules.on_win(ctx.state, ctx.content, front, faction)


def rank2_action(ctx):
    """第 2 階行動的名字（招降黃巾散兵、施符水收人心）：江湖紀錄標題 _action_title 讀。"""
    return opp_rules.rank2_action(ctx.state, ctx.content)


def admin_choices(ctx, s) -> list[dict]:
    """管理頁（/api/admin/player）上這個玩家可以給的機緣：id、標籤、確認框多問的那一句。s 是他的 GameState。"""
    c = ctx.content
    opps = [o for o in c.opportunities if opp_rules.offer_refusal(s, c, o, ctx.world) is None] \
        if opp_rules.active(s, c) else []
    return [{"id": o.id, "label": opp_rules.offer_label(c, o), "note": opp_rules.offer_note(s, c, o)} for o in opps]


def hear_topic(ctx, companion_id: str, topic: str) -> list[str]:
    """按下機緣話題（talk:opp:<話題>）聽到的那幾句。"""
    return opp_rules.hear_topic(ctx.state, ctx.content, companion_id, topic)


def after_success(ctx, kind: str, loc_id: str) -> list[str]:
    """第 2 階行動成功、守勢行動之後替累積型機緣記一次（kind 是 rank2 或 duty）。"""
    return opp_rules.after_success(ctx.state, ctx.content, kind, loc_id, ctx.rng)
