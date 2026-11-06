"""人物對話（功能包；全部拆包第 20 批，計畫 docs/superpowers/plans/2026-11-04-人物情誼包-第2批.md）：原本 Game 上的 9 個方法（對話的 A 段 dialogue_request、
C 段進鎖後重驗 checked_prepared、開口 open_dialogue、一輪 talk、帶路的路上說一句 road_say……），名字去掉前導底線、第一個參數是 ctx（第一階就是 Game）。
Game 留一行的委派給 server（dialogue_request、say_max）、核心原位（choose 前段、交友與求見開口、場景文字）與測試；談著的時候的選單（Game._everyday_options
裡 pending_companion 那一段）也搬進來（talk_options）。

鎖外三段式：A（鎖內很快）dialogue_request 開單、B（鎖外慢）server.prepare_dialogue 叫 companion_agent.prepare_turn 請模型、C（鎖內）Game.choose 的
checked_prepared 重驗再套用；模型不在鎖裡，server 留的殼不動。NPC 智能 2.0 的部分在 parley_actions。

包裡叫回 Game 的都在服務清單（tianxia/core/services_list.md）。這一批互相叫直接叫函式（沒有測試換掉這幾個）。
"""
from __future__ import annotations

from tianxia.core import annal_base as annals  # 核心（行狀記一筆，第 29 批之二）
from tianxia import ranks  # 共用規則層（階級 ranks，第 40 批收進）
from tianxia import figures, precise, roster
from tianxia.core.option import Option
from tianxia.core.travel_base import TravelBlock  # 核心（動身被擋那一句的型別，core_seams）
from tianxia.core.services import PLAN_OPTION, ROAD_SAY, SAY_MAX, SAY_OPTION, say_text

from . import actions, companion_agent, parley, parley_actions


def dialogue_request(ctx, option_id: str, text: str | None = None) -> companion_agent.DialogueRequest | None:
    """鎖外生成的階段 A（server.py 在行動鎖內、很快地呼叫）：現在選這個選項，會不會生成一輪對話？
    會就回傳要送給模型的單子（選項、人物、玩家這一步、messages），不會就是 None。只讀、不改狀態。
    - `talk:N`：N 是上一輪提供的選項、手上有對話、選項沒停用；`talk:leave` 不生成。
    - `act:socialize`：選項沒停用、福緣還沒到（福緣先發，見 _act）、這裡只有一位大勢人物而且見得到
      （兩位以上的地點交友不開口，見 _socialize_figure）；玩家這一步固定是 GENERIC_OPENING。
    - `call:<人物>`：求見選單上按得下去、而且見得到（名望或階級夠、或結識過）的那位人物（這個遊戲日還沒談滿、體力夠）；
      名望不夠的求見也按得下去，但那是被打發、不生成。玩家這一步固定是 GENERIC_OPENING。`call:back` 不生成。
    - `talk:say`（SAY_OPTION，「自己說」）：手上有對話、選項沒停用、text 過得了 say_text；玩家這一步就是那句話。
    其他選項都不呼叫對話模型。
    只讀：選單用 tick=False 取，不推進戰鬥（推進可能結算一回合並呼叫 LLM 潤色，而且備料與
    進鎖重驗各會呼叫這個方法一次；一次請求的那一次推進留給 choose() 開頭）。"""
    option = {o.id: o for o in ctx.options(odds=False, tick=False)}.get(option_id)
    if option is None or not option.enabled:
        return None
    kind, _, arg = option_id.partition(":")
    if option_id in (SAY_OPTION, PLAN_OPTION):
        companion_id, said = ctx.state.player.pending_companion, say_text(text, say_max(ctx))
        if companion_id is None or said is None:
            return None
        extra = parley_actions.prompt(ctx, companion_id) if option_id == SAY_OPTION else parley_actions.plan_prompt(ctx, companion_id)
        fields = parley.ASK_FIELDS if option_id == SAY_OPTION else parley.PLAN_FIELDS
        return companion_agent.build_request(ctx.state, ctx.content, ctx.world, companion_id, option_id, said, free=True,
                                             extra=extra, required=fields if extra else ())
    if option_id == ROAD_SAY:  # NPC 智能 2.1：他帶路的路上跟他說一句（可以是閒談，也可以求他沿路做得到的事）
        companion_id, said = ctx.state.player.parley_escort, say_text(text, say_max(ctx))
        if companion_id is None or said is None:
            return None
        extra = parley_actions.prompt(ctx, companion_id, road=True)
        return companion_agent.build_request(ctx.state, ctx.content, ctx.world, companion_id, option_id, said, free=True,
                                             extra=extra, required=parley.ASK_FIELDS if extra else ())
    if kind == "talk":
        companion_id = ctx.state.player.pending_companion
        if companion_id is None or not arg.isdecimal():
            return None
        shown, _ = companion_agent.offered(ctx.state, companion_id)
        if int(arg) >= len(shown):
            return None
        player_action = shown[int(arg)]
    elif option_id == "act:socialize" and precise.on(ctx.content, ctx.state.world):
        companion_id = ctx._socialize_figure()  # 一類一顆：只有 _social_plan 是 talk 才開口
        if companion_id is None:
            return None
        player_action = companion_agent.GENERIC_OPENING
    elif option_id == "act:socialize":
        if roster.fortune_due(ctx.state, ctx.content) or ranks.summons_event(ctx.state, ctx.content) is not None:
            return None  # 福緣先發；在召見的地點交友端出晉升奇遇（計畫 T5，審查 I1）——都不開口對話
        companion_id = ctx._socialize_figure()
        if companion_id is None:
            return None
        player_action = companion_agent.GENERIC_OPENING
    elif kind == "call" and arg != "back":
        if not ctx._can_meet(arg):
            return None  # 門檻不夠：被打發，不叫模型（見 _call、_brush_off）
        companion_id, player_action = arg, companion_agent.GENERIC_OPENING
    else:
        return None
    extra = parley_actions.plea_prompt(ctx, companion_id) if player_action == companion_agent.GENERIC_OPENING else ""
    return companion_agent.build_request(
        ctx.state, ctx.content, ctx.world, companion_id, option_id, player_action,
        extra=extra, required=parley.PLEA_FIELDS if extra else (),
    )


def checked_prepared(
    ctx, option_id: str, prepared: companion_agent.PreparedTurn | None, text: str | None = None,
) -> companion_agent.PreparedTurn | None:
    """進鎖後重驗鎖外生成的結果：選項、人物、玩家這一步都要跟「現在」重算出來的單子一致才採用；
    對不上（連點兩下、選項清單已換）就當沒給，走一般路徑在鎖內生成——很少發生，慢一點可以接受。
    對不上時連它的失敗（turn=None）一起丟掉，不能讓別張單子的失敗結束現在這段對話。"""
    if prepared is None:
        return None
    request = dialogue_request(ctx, option_id, text)
    if request is None:
        return None
    same = (prepared.option_id, prepared.companion_id, prepared.player_action) == (
        request.option_id, request.companion_id, request.player_action,
    )
    return prepared if same else None


def open_dialogue(ctx, companion_id: str, prepared: companion_agent.PreparedTurn | None) -> list[str]:
    """跟一位大勢人物開口對話（呼叫端已經扣了交友的體力）：生成不出對話時退回那份體力，對話不開始。"""
    extra = parley_actions.plea_prompt(ctx, companion_id)
    try:
        msgs = companion_agent.start_dialogue(
            ctx._quick_client(), ctx.state, ctx.content, ctx.world, companion_id, ctx.rng,
            turn=companion_agent.prepared_turn(prepared), extra=extra,
            decide=lambda turn: parley_actions.plea(ctx, companion_id, turn), required=parley.PLEA_FIELDS if extra else (),
        )
    except companion_agent.DialogueUnavailable:
        ctx.state.player.stamina += ctx.content.config.action_cost["socialize"]  # 生成不出對話：這次不花體力
        return dialogue_unavailable(ctx, companion_id)
    ctx._hint("h_bond")  # 第一次跟人物談話（求見也算）：情誼有什麼用（explain-1）；對話還開著，框等告辭之後才上（features/guide/actions.hint_box）
    return msgs + ctx._overhear(companion_id, msgs)


def last_talk_line(ctx, companion_id: str) -> str:
    """談話畫面名字底下的「上回」那一行（人物記得上次談了什麼，Joy 2026-10-23）：時刻、地點、談了什麼；第一次見面是空的。待 joy 潤"""
    memo = companion_agent.last_talk(ctx.state, companion_id)
    if memo is None:
        return ""
    loc = ctx.content.locations.get(memo.place)
    where = f"・{loc.name}" if loc is not None else ""
    return f"*上回（{ctx.stamp(memo.at)}{where}）：{memo.text}*\n\n"


def dialogue_unavailable(ctx, companion_id: str) -> list[str]:
    """這一輪生成不出對話（模型叫不動）：這輪不算數、對話結束（企劃者決定：不要卡在同一句
    保底反應裡白扣體力）。"""
    ctx.state.player.pending_companion = None
    return [f"{ctx.content.characters[companion_id].name}似乎無心多談，你只好先行告辭。"]


def talk(ctx, arg: str, prepared: companion_agent.PreparedTurn | None = None, said: str | None = None) -> list[str]:
    companion_id = ctx.state.player.pending_companion
    if companion_id is None:
        return ["（此刻無法這麼做。）"]
    if arg == "leave":
        return companion_agent.leave_dialogue(ctx.state)
    if arg.startswith("clue:"):  # 伏筆的片段：固定文字，不經模型、不扣體力、不算對話輪數（計畫 T7）
        chain_id, _, index = arg.removeprefix("clue:").rpartition(":")
        heard = ctx._fs_hear_talk(companion_id, chain_id, int(index))
        return heard or ["（此刻無法這麼做。）"]
    if arg.startswith("opp:"):  # 機緣的話題：固定文字，不經模型、不扣體力、不算對話輪數（正式版乙一）
        heard = ctx._opp_hear_topic(companion_id, arg.removeprefix("opp:"))
        return heard or ["（此刻無法這麼做。）"]
    if arg in ("terms:yes", "terms:no", "owed", "repay"):  # NPC 智能 2.0：接不接他的條件、請他兌現、還他（固定文字，不經模型、不扣體力、不算輪數）
        return parley_actions.answer(ctx, companion_id, arg)
    if arg == "plan":  # NPC 智能 2.1：出陣前跟他商量打法（模型評成功率，不扣體力、不算輪數）
        return parley_actions.plan(ctx, companion_id, prepared, said)
    affinity = ctx.state.player.affinities.get(companion_id, 0)
    heard = actions.stance_before(ctx, companion_id)
    ctx._parley_decision = None
    try:
        if arg == "say":  # 自己說：said 是 choose 驗過、轉過繁體的那一句；江湖紀錄先寫你說了什麼（同隨口應對的「你：「…」」）
            extra = parley_actions.prompt(ctx, companion_id)
            msgs = [f"你：「{said}」"] + companion_agent.say_dialogue(
                ctx._quick_client(), ctx.state, ctx.content, ctx.world, companion_id, said,
                turn=companion_agent.prepared_turn(prepared), extra=extra, required=parley.ASK_FIELDS if extra else (),
                decide=lambda turn: parley_actions.decide(ctx, companion_id, turn, said=said or ""),
            )
        else:
            msgs = companion_agent.continue_dialogue(
                ctx._quick_client(), ctx.state, ctx.content, ctx.world, companion_id, int(arg), ctx.rng,
                turn=companion_agent.prepared_turn(prepared),
            )
    except companion_agent.DialogueUnavailable:
        return dialogue_unavailable(ctx, companion_id)
    actions.stance_credit(ctx, companion_id, heard)
    annal_talk(ctx, companion_id, ctx.state.player.affinities.get(companion_id, 0) - affinity, said)
    msgs += ctx._overhear(companion_id, msgs)
    ctx.state.player.stamina -= ctx.content.config.talk_stamina  # 每一輪對話都要花體力（伺服器假人設計第八節第 4 項）；生成不出來的那輪不算
    msgs += ctx._count_talk(companion_id)
    decision, ctx._parley_decision = ctx._parley_decision, None
    return msgs + parley_actions.finish(ctx, companion_id, decision)


def annal_talk(ctx, companion_id: str, delta: int, said: str | None) -> None:
    """對話的一輪寫進行狀（玩家傳）：自己說的那一句一律記（原句與他回的頭一兩句）；挑選項的只在情誼動得多時記。"""
    c, p = ctx.content, ctx.state.player
    history = p.dialogue_history.get(companion_id, [])
    reply = history[-1]["content"] if history and history[-1].get("role") == "assistant" else ""
    asked = history[-2]["content"] if len(history) >= 2 and history[-2].get("role") == "user" else ""
    name = annals.figure_name(c, companion_id)
    mood = f"，情誼 {delta:+d}" if delta else ""
    if said is not None:
        weight = 3 if abs(delta) >= c.config.biography.talk_swing else 2
        annals.note(ctx.state, c, annals.FIGURE, f"對{name}說了一句自己的話{mood}。", weight,
                    figure=companion_id, quote=said, reply=annals.first_sentence(reply))
    elif abs(delta) >= c.config.biography.talk_swing:
        how = "談得投機" if delta > 0 else "話不投機"
        annals.note(ctx.state, c, annals.FIGURE, f"跟{name}{how}{mood}。", 2,
                    figure=companion_id, quote=asked, reply=annals.first_sentence(reply))


def say_max(ctx) -> int:
    """「自己說」最多幾個字：NPC 智能 2.0開著時照 Config.parley.say_max（要講得清楚一點），關著照舊 SAY_MAX。"""
    return ctx.content.config.parley.say_max if parley.on(ctx.content) else SAY_MAX


def road_say(ctx, prepared: companion_agent.PreparedTurn | None, said: str | None) -> list[str]:
    """帶路的路上跟他說一句（第二批）：一輪不花體力的對話；也可以求他沿路做得到的事（parley.road_items），走同一套夾、擲。"""
    s, c = ctx.state, ctx.content
    cid, j = s.player.parley_escort, s.player.journey
    if cid is None or j is None or said is None or s.player.parley_road_leg == j.reached:
        return ["（此刻無法這麼做。）"]
    affinity = s.player.affinities.get(cid, 0)
    heard = actions.stance_before(ctx, cid)
    ctx._parley_decision = None
    extra = parley_actions.prompt(ctx, cid, road=True)
    try:
        msgs = [f"你：「{said}」"] + companion_agent.say_dialogue(
            ctx._quick_client(), s, c, ctx.world, cid, said, turn=companion_agent.prepared_turn(prepared),
            extra=extra, decide=lambda turn: parley_actions.decide(ctx, cid, turn, road=True, said=said or ""),
            required=parley.ASK_FIELDS if extra else (),
        )
    except companion_agent.DialogueUnavailable:
        return [f"{c.characters[cid].name}沉吟不語。"]
    actions.stance_credit(ctx, cid, heard)
    s.player.parley_road_leg = j.reached
    annal_talk(ctx, cid, s.player.affinities.get(cid, 0) - affinity, said)
    decision, ctx._parley_decision = ctx._parley_decision, None
    return msgs + parley_actions.finish(ctx, cid, decision)


def talk_options(ctx) -> list[Option]:
    """跟人物談著的時候的整個選單（Game._everyday_options 裡 pending_companion 那一段，位置算行為，第 56 批起是 take/talk 那一格）：
    上一輪給的選項（花體力）、自己說、伏筆的片段與機緣的話題（固定文字、不花體力）、NPC 智能 2.0 的條件與欠的事，最後一定有「告辭」。"""
    s, c = ctx.state, ctx.content
    dialogue_options, _ = companion_agent.offered(s, s.player.pending_companion)
    talk_cost = c.config.talk_stamina
    opts = [ctx._cost_option(f"talk:{i}", text, talk_cost) for i, text in enumerate(dialogue_options)]
    if dialogue_options:  # 模型寫的選項之外，自己打一句話（企劃者 2026-10-08）：價錢、輪數跟按選項一樣
        opts.append(ctx._cost_option(SAY_OPTION, "自己說…", talk_cost))
    opts += ctx._omen_talk_options(s.player.pending_companion)  # 伏筆的片段（計畫 T7）、機緣的話題（正式版乙一）：固定文字、不花體力（軍情，第 34 批查詢服務）
    opts += parley_actions.options(ctx, s.player.pending_companion)  # NPC 智能 2.0：他開的條件、欠你的那一件（不花體力）
    opts.append(Option(id="talk:leave", label="告辭"))
    return opts


def affinity_text(ctx, companion_id: str) -> str:
    """「情誼 N」：你跟這位人物的情誼（PlayerState.affinities，0～100）。談話畫面、求見名單、輿圖的人物都寫這個詞（explain-1：
    玩家看得到的只叫「情誼」，程式裡照舊叫 affinity）。深交不限人數（企劃者 2026-10-28「不要限制深交名額」），不再接「已深交三位」。
    （總表附錄甲點名第 20 批；第 20 批審查補搬。）"""
    return f"情誼 {ctx.state.player.affinities.get(companion_id, 0)}"


def talk_view(ctx) -> dict | None:
    """正在跟誰說話（介面重整的對話框）：{id, name, side, affinity}；沒在對話是 None。（主幹合回第 2 段 D 從 Game 搬來）"""
    s, c = ctx.state, ctx.content
    cid = s.player.pending_companion
    if not cid or cid not in c.characters:
        return None
    side = figures.side_name(c, figures.of_character(c, cid))
    return {"id": cid, "name": c.characters[cid].name, "side": side, "affinity": s.player.affinities.get(cid, 0)}


def talk_title(ctx) -> str:
    """談話那一下江湖紀錄的標題：「交談・盧植」（動作之前拿，原本 Game._action_title 的 talk 那一支）。"""
    who = ctx.state.player.pending_companion
    return f"交談・{ctx.content.characters[who].name}" if who in ctx.content.characters else "交談"


def road_title(ctx) -> str:
    """帶路的路上跟他說一句的標題：「同行・盧植」（原本 Game._action_title 的 parley 那一支；帶路的人不在人物表時選單上不會有這一顆，寫「同行」）。"""
    escort = ctx.state.player.parley_escort
    return f"同行・{ctx.content.characters[escort].name}" if escort in ctx.content.characters else "同行"


def travel_block(state, content) -> TravelBlock | None:
    """block/talk 那一格（core_seams，全部拆包第 56 批；原本在 atlas.travel_block，字一字不動）：跟人物談著。"""
    return TravelBlock("交談中，先告辭才能安排前往", to_jianghu=True) if state.player.pending_companion else None


def main_slot(ctx, frame) -> dict:
    """main 表的 companions 那一格（全部拆包第 66 批）：鍵照 talk、figure、errands 的先後，沒有就沒有那個鍵。像在 web/img/figures/full/<id>.webp 才給 face（server.figure_face）。"""
    out: dict = {}
    talk_now = talk_view(ctx)  # 正在說話的那一位（浮在最上層的對話框）
    if talk_now is not None:
        out["talk"] = {**talk_now, "face": frame.shell.figure_face(talk_now["id"])}
    talking = ctx.state.player.pending_companion  # 人物頁（減法季批 6）：正在跟他談的那一位的心意條；關著、他沒有心意沒有這個鍵
    figure = actions.figure_view(ctx, talking) if talking else None
    if figure is not None:
        out["figure"] = figure
    errands_now = actions.errands_view(ctx)  # 託付清單（減法季批 6，主機側計畫 1.3 的 main.errands）；託付關著沒有這個鍵
    if errands_now is not None:
        out["errands"] = errands_now
    return out
