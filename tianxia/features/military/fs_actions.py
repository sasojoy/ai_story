"""伏筆的動作（功能包 military；全部拆包第 34 批「軍情二」）：最後一步的按下去、每次花體力之後抽伏筆片段與機緣線索、管理者給片段，
加上核心原位要問伏筆的地方（答題中的選單與場景文字、閒著的選單上最後一步的選項、遊歷打贏的官銀、事件觸發的片段、管理者頁的片段選單、對話的片段選項）。
規則本體在 fs_rules.py（原本的 tianxia/foreshadow.py）。原本 Game 上的 foreshadow（_foreshadow）、hear_after_stamina（_hear_after_stamina）、
give_fragment（admin_give_fragment）；其餘 Game 留一行委派回答，第一個參數是 ctx。
「你這一步」的 foreshadow 那一格（全部拆包第 36 批；原本 weekcard._steps 經舊名 foreshadow 讀 next_step、step._target 讀 next_trip）：
step_items、step_place，只讀——讀伏筆就是這一格回答，核心不再讀（第 34 批 PM 認定第 1 條）。
"""
from __future__ import annotations

from tianxia import atlas  # 共用規則層（輿圖的大區 atlas.region_of，第 50 批收進：抽片段要知道所在地點的大區）
from tianxia import prologue as prologue_rules
from tianxia import step as step_rules  # 核心本體（第 36 批收進 MODULES）：「你這一步」的 REF、place
from tianxia.core.services import NO_SUCH_PLAYER

from . import fs_rules, opp_actions, opp_rules
from .opp_actions import HEARD_TITLE


def foreshadow(ctx, arg: str) -> list[str]:
    """伏筆的最後一步（計畫 T7）：fs:<鏈> 看題（沒有題的直接做）、fs:<鏈>:<選項> 答題、fs:leave 作罷。"""
    if arg == "leave":
        return fs_rules.leave(ctx.state)
    chain_id, _, option_id = arg.partition(":")
    return fs_rules.attempt(
        ctx.state, ctx.content, chain_id, option_id or None, ctx.state.world.time, ctx.rng, ctx.world,
    )


def hear_after_stamina(ctx, before: float) -> list[str]:
    """每次花體力的行動之後抽一次伏筆片段（計畫 T7）：選單的每一個行動（choose）與輿圖的安排前往（travel）都經過這裡，
    體力比行動前少了才抽（探索、遊歷、交友、求見、對話、招募、趕路、疾行；打坐、步行、生成不出對話退回體力的都不算）。
    抽的是行動後所在地點的大區；沒有伏筆在跑（開關關著、沒有鏈）就什麼都不做。
    伏筆先抽、天時地利型機緣的線索（正式版乙一）後抽：伏筆的擲骰順序不變。
    序章（新手引導計畫一）在草廬裡什麼都不抽：那是真實世界的事。"""
    s, c = ctx.state, ctx.content
    if s.player.stamina >= before or prologue_rules.active(s, c):
        return []
    region = atlas.region_of(c, s.player.location)
    region_id = region.id if region is not None else None
    msgs = fs_rules.hear_after_action(s, c, region_id, ctx.rng, ctx.world) if fs_rules.active(s, c) else []
    if opp_rules.active(s, c):  # 天時地利型機緣的線索（正式版乙一）
        msgs += opp_rules.hear_clues(s, c, region_id, ctx.rng, world=ctx.world)  # 內鬼的特徵要讀本季天機
    return msgs


def give_fragment(ctx, name: str, ref: str) -> list[str]:
    """給他一個伏筆片段（ref 是「鏈 id:片段序號」）：照效果給片段的同一條（foreshadow.grant_fragment：記進聽過的片段、
    江湖紀錄那一句「你聽到一件事：…」、不發傳聞）。不是他那一方的、已經聽過的、那條伏筆已經用不上的都拒絕。
    給管理者的那一句不寫片段的原文（天機的答案填在裡面，管理者自己也是玩家），也不提鎖定。"""
    refusal = ctx._admin_refusal("給伏筆片段")
    if refusal:
        return ctx._log(refusal)
    c = ctx.content
    if not fs_rules.active(ctx.state, c):
        return ctx._log(["（這一季沒有伏筆。）"])
    chain_id, _, index = ref.rpartition(":")
    chain = fs_rules.chain(c, chain_id)
    if chain is None or not index.isdecimal() or not 0 <= int(index) < len(chain.fragments):
        return ctx._log(["（沒有這一則伏筆片段。）"])
    i = int(index)
    target = ctx._admin_target(name)
    if target is None:
        return ctx._log([NO_SUCH_PLAYER.format(name=name.strip())])
    s = target.state
    why = fs_rules.grant_refusal(s, c, chain, i)
    if why is None:
        target._write(HEARD_TITLE, fs_rules.grant_fragment(s, c, chain.id, i, ctx.world))  # 不標管理者（審查 M-1）
    ctx._save_target(target)
    if why is not None:
        return ctx._log([why])
    event = ctx._timetable_event(chain.event)
    msg = f"已讓{s.player.name}聽到{event.title if event else chain.event}那條伏筆的第 {i + 1} 則片段。"
    ctx._write("給伏筆片段", [msg], tag="管理者")
    return ctx._log([msg])


def final_options(ctx, loc_id: str) -> list:
    """閒著的選單上伏筆最後一步的選項（計畫 T7）：做得了的人在那個地點才有。"""
    return fs_rules.final_options(ctx.state, ctx.content, loc_id)


def omen_options(ctx, loc_id: str) -> list:
    """閒著的選單上機緣與伏筆最後一步的選項（機緣先、伏筆後；MENU_ORDER["here"] 夾在 rank 與 errand 之間，順序算行為）。"""
    return opp_actions.place_options(ctx, loc_id) + final_options(ctx, loc_id)


def asking_options(ctx) -> list:
    """伏筆的最後一步正在答題：選單只有答案與「作罷」。核心原位在店面 shop_menu 之後、閉關 busy_until 之前問它。"""
    return fs_rules.asking_options(ctx.state, ctx.content)


def asking_text(ctx) -> str | None:
    """答題中的場景文字。核心原位 _own_scene_text 在拜入、投靠、叛投、求見的畫面之後、趕路的畫面之前問它。"""
    return fs_rules.asking_text(ctx.state, ctx.content, ctx.world)


def trip_label(ctx, chain_id: str) -> str:
    """這一下江湖紀錄的標題「<這一趟叫什麼>・<所在>」前半。"""
    return fs_rules.trip_label(ctx.state, ctx.content, chain_id)


def after_win(ctx, squad, region_id: str | None) -> list[str]:
    """遊歷打贏之後擲官銀（伏筆，濃縮版內容表 4.0）。"""
    return fs_rules.after_win(ctx.state, ctx.content, squad, ctx.rng, region_id)


def hear_from_event(ctx, event_id: str) -> list[str]:
    """事件觸發時聽到的伏筆片段（計畫 T7）：事件檢定（核心）寫完事件卡之後接在後面。"""
    return fs_rules.hear_from_event(ctx.state, ctx.content, event_id, ctx.world)


def talk_options(ctx, companion_id: str) -> list:
    """跟人物對話時伏筆的片段選項（計畫 T7）：固定文字、不花體力；後面接機緣的話題（opp_actions.talk_options）。"""
    return fs_rules.talk_options(ctx.state, ctx.content, companion_id) + opp_rules.talk_options(ctx.state, ctx.content, companion_id)


def hear_talk(ctx, companion_id: str, chain_id: str, index: int) -> list[str]:
    """按下伏筆的對話片段（talk:clue:<鏈>:<序號>）聽到的那幾句。"""
    return fs_rules.hear_talk(ctx.state, ctx.content, companion_id, chain_id, index, ctx.world)


def admin_choices(ctx, s) -> dict:
    """管理頁（/api/admin/player）上這個玩家可以給的機緣（opportunities）與伏筆片段（fragments）。s 是他的 GameState。"""
    c = ctx.content
    frags = [(ch, i) for ch in c.foreshadows.chains for i in range(len(ch.fragments))
             if fs_rules.grant_refusal(s, c, ch, i) is None] if fs_rules.active(s, c) else []
    return {
        "opportunities": opp_actions.admin_choices(ctx, s),
        "fragments": [{"id": f"{ch.id}:{i}", "label": fs_rules.grant_label(c, ch, i)} for ch, i in frags],
    }


# core_step（全部拆包第 36 批「你這一步」）：foreshadow 那一格（core/features.py 的 STEP_ORDER：揭了的懸賞之後、新手目標之前）。
# 照 fs_rules.next_step、fs_rules.next_trip 的模組屬性叫（tests/bots/test_step.py 換的是 tianxia.foreshadow.next_trip＝fs_rules 那一個）。
def step_items(ctx) -> list[dict]:
    """「你這一步」的伏筆那一件（原本 weekcard._steps 的伏筆那一段）：伏筆的下一步有才一件。"""
    step = fs_rules.next_step(ctx.state, ctx.content)
    return [{"kind": "foreshadow", "text": step, step_rules.REF: ("foreshadow",)}] if step else []


def step_place(ctx, ref: tuple) -> tuple:
    """伏筆那一件的 (id, target, None)（原本 step._target 的伏筆那一支）：下一趟那一條鏈與它的地點；沒有 (None, None, None)。"""
    found = fs_rules.next_trip(ctx.state, ctx.content)
    return (found[0].id, step_rules.place(ctx, found[1].location), None) if found is not None else (None, None, None)
