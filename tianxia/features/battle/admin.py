"""全服決戰「打」那一半之一：管理者的決戰工具（全部拆包第 6 批；計畫 docs/superpowers/plans/2026-11-01-決戰包-第2批.md）。原本 Game 上的
7 個方法，本體照抄、self 換成 ctx（第一階 ctx 就是 Game，開發規範手冊 3.3）。Game 留 6 個一行委派（server 的 ADMIN_ACTIONS、admin_choices、
timetable_choices 與測試在叫），showdown_refusal 只有這裡叫。

- admin_battles：管理者「立刻開戰」的選單（server.admin_choices 的 battles）
- admin_start_battle：立刻開戰（時刻表決戰跟時間到了一樣開：world.open_showdown；其餘 world.start_battle）
- admin_cancel_battle：取消決戰（不算勝負、天下大事一句；時刻表決戰記進 showdowns_cancelled，FB-563）
- admin_showdowns、showdown_refusal、cancelled_showdowns、admin_start_showdown：三場大戲那三顆鈕（管理者觸發鈕第 3 組；FB-099）

包裡叫測試直接叫的那幾個（admin_battles、admin_start_battle、cancelled_showdowns）經 ctx（Game 的委派）；時刻表（_timetable_event、
_timetable_refusal）、管理者外殼（_admin_refusal）也經 ctx（tianxia/core/services.py 的清單）；showdown_refusal 與第 8 批搬進 progress.py 的
shelve_unfinished_battle（第 6 批時還在 Game、經 ctx 叫）直接叫。
"""
from __future__ import annotations

from tianxia import timetable  # 共用規則層（時刻表）
from tianxia.models import BattleDef, TimetableEvent
from tianxia.rules import add_rumor, season_one, season_one_off
from tianxia.world import open_showdown, showdown_battle  # 核心本體：開時刻表決戰、照版本挑那一場

from . import progress  # 推進與結算（第 8 批：取消決戰收兵 shelve_unfinished_battle）


def admin_battles(ctx) -> list[BattleDef]:
    """管理者「立刻開戰」的選單，照內容的順序（計畫 T8）：
    - 第一季不觸發的 beta 決戰不列；
    - 時刻表決戰只在第一季列（開關關著時 beta 那一季沒有時刻表），而且只列還沒開過、還沒收場的，分版本的只列這一季
      該開的那一版（宛城照第 3 週的結果）——開出來跟時間到了自動開的一樣（見 admin_start_battle）。"""
    w = ctx.state.world
    off = season_one_off(ctx.content, w, "battles")
    showdowns = [
        showdown_battle(ctx.state, ctx.content, e) for e in timetable.events(w, ctx.content)
        if season_one(ctx.content, w) and e.kind == "showdown" and e.id not in w.timeline and e.id not in w.showdowns_opened
        and (e.version_from is None or e.version_from in w.timeline)  # 宛城：第 3 週結算前不知道是哪一版，不列（PM 2026-10-05）
    ]
    openable = {b.id for b in showdowns if b is not None}
    return [b for b in ctx.content.battles.values()  # 攻城範本（領地爭奪第二批）不列：照時程表開
            if b.id not in off and not b.siege and (b.timetable_event is None or b.id in openable)]


def admin_start_battle(ctx, battle_id: str, now: float) -> list[str]:
    """管理者直接開一場全服戰鬥（試玩時人少、大勢推不到門檻也能開戰）。選單上沒有的（第一季不觸發的 beta 決戰）開不了。"""
    refusal = ctx._admin_refusal("開戰")
    if refusal:
        return ctx._log(refusal)
    definition = next((b for b in ctx.admin_battles() if b.id == battle_id), None)
    if definition is None:
        return ctx._log(["（沒有這場戰鬥。）"])
    current = ctx.world.get_battle()
    if current is not None and current.phase != "ended":
        return ctx._log(["（已經有一場戰鬥在進行。）"])
    if definition.timetable_event is not None:  # 時刻表決戰：跟時間到了一樣開（起點照戰況、記下開過了，之後不再開）
        msgs = open_showdown(ctx.world, ctx.content, definition.timetable_event, now)
        ctx.state.world = ctx.world.get_season()
    else:
        ctx.world.start_battle(definition, now)
        msgs = [f"🛡️ 【全服戰報】{definition.name}的集結號角已經吹響！"]
    ctx._write(f"開戰・{definition.name}", msgs, tag="管理者")
    return ctx._log(msgs)


def admin_cancel_battle(ctx) -> list[str]:
    """取消決戰：正在集結或開打的那一場收起來、不算結果（參戰者各補一則「不算勝負」，同收季，FB-035），發一則天下大事。
    時刻表決戰取消後不會自己再開（開過的記號留著）；要收尾用「定結果」。"""
    refusal = ctx._admin_refusal("取消決戰")
    if refusal:
        return ctx._log(refusal)
    battle = ctx.world.get_battle()
    if battle is None or battle.phase == "ended":
        return ctx._log(["（沒有進行中的決戰。）"])
    definition = ctx.content.battles.get(battle.battle_id)
    name = definition.name if definition else battle.battle_id
    line = f"{name}臨時取消，這一仗沒有打成。"
    ctx.state.world = ctx.world.get_season()  # 收場時間記此刻的季時間（同 admin_end_season）
    progress.shelve_unfinished_battle(ctx, f"{name}臨時取消，這一仗沒有打成，不算勝負。")
    event_id = definition.timetable_event if definition else None
    w = ctx.state.world
    if event_id and event_id in w.showdowns_opened and event_id not in w.timeline and event_id not in w.showdowns_cancelled:
        w.showdowns_cancelled.append(event_id)  # 取消的時刻表決戰：輿圖不列（FB-563；之後「定結果」了才照有結果的寫法列）
    add_rumor(ctx.state, line, content=ctx.content, layer="world")
    ctx._save_season()
    ctx._write("取消決戰", [line], tag="管理者")
    return ctx._log([line])


def admin_showdowns(ctx) -> list[tuple[TimetableEvent, str | None]]:
    """三場大戲那三顆鈕：時刻表上的每一件決戰，與此刻按下去會被拒絕的原因（開得了是 None）。這一季沒有時刻表時是空的。"""
    if not season_one(ctx.content, ctx.state.world):
        return []
    return [(e, showdown_refusal(ctx, e)) for e in timetable.events(ctx.state.world, ctx.content) if e.kind == "showdown"]


def showdown_refusal(ctx, event: TimetableEvent) -> str | None:
    """這一件決戰此刻開不開得了：已經結算、已經開過（時刻表那一份記號，開過就不再開）、要看別的大事定版本而那件還沒結算
    （宛城，PM 2026-10-05）、另一場還在集結或開打，都開不了。"""
    w = ctx.state.world
    if event.id in w.timeline:
        return f"（{event.title}已經結算了。）"
    if event.id in ctx.cancelled_showdowns():  # FB-099：開過、被取消、還沒有結果——照舊開不了，說清楚怎麼收尾
        return f"（{event.title}開打後被取消，還沒有結果；要收尾請用「定結果」。）"
    if event.id in w.showdowns_opened:
        return f"（{event.title}已經開打過了。）"
    if event.version_from is not None and event.version_from not in w.timeline:
        source = ctx._timetable_event(event.version_from)
        return f"（{event.title}要等{source.title if source else event.version_from}結算了才知道是哪一版。）"
    battle = ctx.world.get_battle()
    if battle is not None and battle.phase != "ended":
        return "（已經有一場戰鬥在進行。）"
    if showdown_battle(ctx.state, ctx.content, event) is None:
        return f"（內容裡沒有{event.title}這一場的戰鬥。）"
    return None


def cancelled_showdowns(ctx) -> set[str]:
    """開打後被取消、時間軸上還沒有結果的時刻表決戰（FB-099；管理者工具的三場大戲與時刻表那兩列照它寫）：開過集結
    （showdowns_opened，記號照舊留著、不會再開），時間軸上沒有它，此刻也不是在打的那一場（取消決戰把它從共用狀態拿掉了）。
    真的打完的時間軸上有結果，不算；還在集結、開打或剛收場的那一場是此刻的那一場，也不算。"""
    w = ctx.state.world
    battle = ctx.world.get_battle()
    live = battle.battle_id if battle is not None else None
    return {eid for eid, battle_id in w.showdowns_opened.items() if eid not in w.timeline and battle_id != live}


def admin_start_showdown(ctx, event_id: str, now: float) -> list[str]:
    """立刻開時刻表上這一場決戰：照時刻表開（admin_start_battle → world.open_showdown，跟時間到了一樣：同一個函式、同一句集結
    號角），開過就記在 showdowns_opened，排定的時間到了不再開。版本照此刻的規則（宛城看第 3 週的結果）。"""
    refusal = ctx._timetable_refusal("開這一場決戰")
    if refusal:
        return ctx._log(refusal)
    event = ctx._timetable_event(event_id)
    if event is None or event.kind != "showdown":
        return ctx._log(["（時刻表上沒有這一場決戰。）"])
    why = showdown_refusal(ctx, event)
    if why:
        return ctx._log([why])
    return ctx.admin_start_battle(showdown_battle(ctx.state, ctx.content, event).id, now)
