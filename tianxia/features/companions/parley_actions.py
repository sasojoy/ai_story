"""NPC 智能 2.0（功能包；全部拆包第 20 批，計畫 docs/superpowers/plans/2026-11-04-人物情誼包-第2批.md）：原本 Game 上的 19 個方法
（開口求他做事的兩份清單與提示、C 段驗模型挑的事並擲骰、他答應的事真的去做、條件的接與還、食言、他主動開口求你、帶路、陪你出陣與商量打法），
名字去掉前導的 `_parley_`、第一個參數是 ctx（第一階就是 Game）。純規則在 parley.py（原本 tianxia/parley.py，舊名留成別名）。

Game 留一行的委派給測試與核心原位（談著的時候的選單、路上的選項、並肩出陣）；包裡互相叫直接叫函式。
`ctx._parley_decision` 是 Game 的暫存（這一輪「自己說」擲出來的結果：decide 記、talk_actions 的 talk 與 road_say 收尾時拿去做事），在服務清單的四、寄放。
"""
from __future__ import annotations

import random

from tianxia import atlas, figure_life  # 共用規則層（輿圖路線 atlas 第 50 批收進、人物活起來 figure_life）
from tianxia import materials, prologue as prologue_rules
from tianxia.core import travel_base  # 核心（跟著誰同行：跟著的人路上不跟帶路的人說話，core_seams）
from tianxia.core.option import Option
from tianxia.core.services import PLAN_OPTION, ROAD_SAY
from tianxia.rules import game_day
from tianxia.state import Journey, Letter, ParleyBacking, ParleyDebt, ParleyTerms

from . import companion_agent, parley


def settle_task(ctx, task_id: str, cid: str | None) -> bool:
    """一件委託辦成了（懸賞榜包 rules._complete_commission 經 ctx._parley_settle_task 問，全部拆包第 45 批；本體 parley.settle_task）。"""
    return parley.settle_task(ctx.state, ctx.content, task_id, cid)


def keep(ctx, cid: str, cond: str) -> None:
    """記一筆守約（同上；本體 parley.keep）。"""
    parley.keep(ctx.state, ctx.content, cid, cond)


def owed_line(name: str) -> str:
    """「下回見到他，他會兌現答應你的事」那一句（同上；parley.COMMISSION_OWED）。"""
    return parley.COMMISSION_OWED.format(name=name)


def ask_label(ctx, ask_id: str) -> str:
    """答應你的那一件寫給人看的字（懸賞榜包 rules.commission_reward 經 ctx._parley_ask_label 問；本體 parley.ask_label）。"""
    return parley.ask_label(ctx.content, ask_id)


def finish(ctx, cid: str, decision: parley.Decision | None) -> list[str]:
    """NPC 智能 2.0那一輪的收尾：結果那一句，答應了就當場做（帶路會在這裡動身）；先做後付另外記下你欠他的那一件。"""
    if decision is None or decision.kind is None:
        return []
    if decision.kind != "owe":
        msgs = [parley.result_line(ctx.content, cid, decision)]
        return msgs + (do(ctx, cid, decision.ask.id) if decision.kind == "do" else [])
    due = owe(ctx, cid, decision.condition, decision.ask)
    msgs = [parley.result_line(ctx.content, cid, decision, parley.due_text(ctx.state, ctx.content, due))]
    return msgs + do(ctx, cid, decision.ask.id)


def owe(ctx, cid: str, condition: parley.Item, ask: parley.Item, kind: str = "owe") -> float:
    """記下你欠他的一件（先做後付 owe、接了他的請託 plea）：打探、討伐掛成一件委託（書信小卡、懸賞卡上看得到），
    交銀、交素材等你見面「還他」。回期限（世界秒）。"""
    s, c = ctx.state, ctx.content
    p = s.player
    due = parley.due_of(s, c, ask.weight if kind == "owe" else condition.weight)
    task_id = None
    if condition.id.partition(":")[0] in ("scout", "strike"):
        p.letter_seq += 1
        task = parley.commission(s, c, cid, condition, ask if kind == "plea" else parley.Item("", ""), p.letter_seq)
        if task is not None:
            task.expires = due
            task.parley_ask = ask.id if kind == "plea" else None
            p.letters.append(Letter(id=p.letter_seq, kind="條件", sender=cid, at=s.world.time,
                                    text=c.characters[cid].name + "託你的事：" + condition.label, read=True, task=task))
            p.letters = p.letters[-c.config.figure_life.letters_keep:]
            task_id = task.id
    p.parley_debts[cid] = ParleyDebt(kind=kind, condition=condition.id, weight=condition.weight if kind == "plea" else ask.weight,
                                     due=due, task=task_id)
    parley.record(s, cid).promised += 1
    return due


def lists(ctx, cid: str, road: bool = False) -> tuple[list[parley.Item], list[parley.Item]]:
    """他此刻做得到的事、他可以開的條件（A 段放進提示、C 段拿來驗，兩次要一樣：條件的亂數只看名號、人物、今天）。
    road：帶路的路上，只列沿路做得到的事（parley.road_items）。"""
    s, c = ctx.state, ctx.content
    asks = parley.ask_items(s, c, cid, ctx._side(), can_sortie=not prologue_rules.active(s, c))
    rng = random.Random(f"條件|{s.player.name}|{cid}|{game_day(c, s.world)}")
    return (parley.road_items(asks) if road else asks), parley.condition_items(s, c, cid, rng)


def prompt(ctx, cid: str, road: bool = False) -> str:
    """「自己說」那一輪接在玩家原話後面的一段（NPC 智能 2.0）：關著、今天求滿了是空的，模型就只是談話。"""
    s, c = ctx.state, ctx.content
    if not parley.on(c) or parley.asks_left(s, c, cid) <= 0:
        return ""
    if not road and ctx._talk_idle(cid):  # 心神開著、今天長情誼的那幾輪用完了：只是閒聊，不開條件
        return ""
    asks, conditions = lists(ctx, cid, road)
    hostile = parley.enemy(s, c, cid, ctx._side())
    gift = parley.gift_text(parley.gift_of(s, c, cid)) if any(a.id == "gift" for a in asks) else ""
    return parley.prompt_block(c, cid, asks, conditions, s.player.affinities.get(cid, 0), hostile, gift)


def decide(ctx, cid: str, turn: companion_agent.CompanionTurn, road: bool = False, said: str = "") -> companion_agent.CompanionTurn:
    """C 段：驗模型挑的那一件、夾意願、擲骰，記今天求了幾件／婉拒了哪件／開了什麼條件，換上那一版回話。
    關著、今天求滿了、模型沒挑事（只是閒聊）時原樣回去。贈物那一版話跟他真的給的對不上（parley.gift_slip）換固定句；said 是玩家那一句。"""
    s, c = ctx.state, ctx.content
    if not parley.on(c) or parley.asks_left(s, c, cid) <= 0 or not (turn.ask or "").strip():
        return turn
    asks, conditions = lists(ctx, cid, road)
    hostile = parley.enemy(s, c, cid, ctx._side())
    decision = parley.decide(c, asks, conditions, turn.ask.strip(), turn.willing, (turn.condition or "").strip(),
                             s.player.affinities.get(cid, 0), hostile, parley.roll(s, cid),
                             broken=parley.broken_of(s, cid), can_owe=parley.can_owe(s, c, cid))
    record = parley.touch(s, c, cid)
    record.asks += 1
    ctx._parley_decision = decision
    name = c.characters[cid].name
    if decision.kind == "owe":  # 先做後付：他答應了、也說了要你之後做什麼——給玩家看開條件那一版（說得出條件）
        text = gift_check(ctx, cid, decision, said, (turn.narrative_terms or "").strip() or turn.narrative)
        return turn.model_copy(update={"narrative": text})
    if decision.kind == "terms":
        cond = parley.condition_text(c, decision.condition, decision.ask.weight)
        text = (turn.narrative_terms or "").strip() or parley.TERMS_FALLBACK.format(name=name, cond=cond)
        text = gift_check(ctx, cid, decision, said, text)
        s.player.parley_terms[cid] = ParleyTerms(ask=decision.ask.id, condition=decision.condition.id, text=text, at=s.world.time)
        return turn.model_copy(update={"narrative": text})
    if decision.kind == "no":
        if decision.ask.id not in record.refused:
            record.refused.append(decision.ask.id)
        text = (turn.narrative_no or "").strip() or parley.NO_FALLBACK.format(name=name)
        return turn.model_copy(update={"narrative": text})
    text = gift_check(ctx, cid, decision, said, turn.narrative)
    return turn if text == turn.narrative else turn.model_copy(update={"narrative": text})


def gift_check(ctx, cid: str, decision: parley.Decision, said: str, text: str) -> str:
    """贈物答應了（當場、先做後付、開條件）：話裡給的要是他真的給得出的那一樣，對不上換固定句。別的事原樣回去。"""
    if decision.ask is None or decision.ask.id != "gift":
        return text
    gift = parley.gift_of(ctx.state, ctx.content, cid)
    wanted = parley.gift_slip(ctx.content, gift, said, text)
    if wanted is None:
        return text
    cond = parley.condition_text(ctx.content, decision.condition, decision.ask.weight) if decision.condition is not None else ""
    return parley.gift_fix(ctx.content, cid, gift, wanted, decision.kind, cond)


def do(ctx, cid: str, ask_id: str) -> list[str]:
    """他答應的那一件，引擎真的去做（模型只說了話，這裡才動數字與位置）。"""
    s, c = ctx.state, ctx.content
    name = c.characters[cid].name
    kind, _, rest = ask_id.partition(":")
    tuning = c.config.parley
    if kind == "escort":
        route = atlas.way_to(s, c, rest)
        if route is None or not parley.can_leave(s, c):
            return [parley.OWED_LATER.format(name=name)]
        s.player.pending_companion = None  # 跟他上路了：這段交談到此為止
        cost = atlas.route_stamina(s, c, route, "walk")
        msgs = [parley.ESCORT_LINE.format(name=name, place=c.locations[rest].name)] + ctx._depart(route, "walk", pace=tuning.escort_pace)
        s.player.stamina += cost  # 他帶的路：照他的腳程走（比步行快），體力一分不扣
        if ctx._draft is not None and f"體力 -{cost}" in ctx._draft.changes:
            ctx._draft.changes.remove(f"體力 -{cost}")
        if s.player.journey is not None:  # 第二批：路上每到一站可以跟他說一句（road_option，road/parley 那一格）
            s.player.parley_escort, s.player.parley_road_leg = cid, -1
        return msgs
    if kind == "sortie":
        region = parley.region_of(s, c, cid)
        s.player.parley_backing = ParleyBacking(figure=cid, region=region, day=game_day(c, s.world))
        return [parley.BACKING_LINE.format(name=name, region=parley._region_name(c, region))]
    if kind == "spar":
        parley.touch(s, c, cid).spar = True
        s.player.stats["xinde"] = s.player.stats.get("xinde", 0) + tuning.spar_xinde
        return [parley.SPAR_LINE.format(name=name), f"心得 +{tuning.spar_xinde}"]
    if kind == "intel":
        facts = parley.intel_facts(s, c, cid)
        return [parley.INTEL_HEAD.format(name=name, facts="；".join(facts))] if facts else []
    if kind == "gift":  # 給的就是提示裡寫給模型的那一樣（parley.gift_of）
        gift = parley.gift_of(s, c, cid)
        line = materials.grant(s, c, gift.material, gift.count) if gift.material else None
        if line:
            return [parley.GIFT_LINE.format(name=name, gift=parley.gift_text(gift)), line]
        s.player.stats["silver"] = s.player.stats.get("silver", 0) + tuning.gift_silver
        return [parley.GIFT_LINE.format(name=name, gift=f"{tuning.gift_silver} 兩銀子"), f"銀兩 +{tuning.gift_silver}"]
    return []


def options(ctx, cid: str) -> list[Option]:
    """對話選單上NPC 智能 2.0的鈕：他開了條件、還沒答覆（接、不接）；辦成委託之後他欠你的那一件（請他兌現）。"""
    s, c = ctx.state, ctx.content
    if not parley.on(c):
        return []
    opts: list[Option] = []
    terms = s.player.parley_terms.get(cid)
    if terms is not None and terms.plea:  # 他主動開口求你（第二批）：接不接
        opts.append(Option(id="talk:terms:yes", label=parley.PLEA_ACCEPT.format(
            cond=cond_label(ctx, terms.condition), what=parley.ask_label(c, terms.ask))))
        opts.append(Option(id="talk:terms:no", label=parley.PLEA_DECLINE))
    elif terms is not None:
        weight = next((a.weight for a in lists(ctx, cid)[0] if a.id == terms.ask), 1)
        cond = parley.condition_text(c, parley.Item(terms.condition, cond_label(ctx, terms.condition)), weight)
        opts.append(Option(id="talk:terms:yes", label=parley.TERMS_ACCEPT.format(cond=cond)))
        opts.append(Option(id="talk:terms:no", label=parley.TERMS_DECLINE))
    debt = s.player.parley_debts.get(cid)
    if debt is not None and debt.task is None:  # 欠他銀兩、素材（第二批）：見面還
        opts.append(Option(id="talk:repay", label=parley.REPAY_BUTTON.format(name=c.characters[cid].name, cond=parley.debt_text(c, debt))))
    if plan_open(ctx, cid):  # 答應陪你出陣了（第二批）：出陣前跟他商量打法
        opts.append(Option(id=PLAN_OPTION, label=parley.PLAN_BUTTON.format(name=c.characters[cid].name)))
    owed = s.player.parley_owed.get(cid)
    if owed:
        opts.append(Option(id="talk:owed", label=parley.OWED_BUTTON.format(name=c.characters[cid].name, what=parley.ask_label(c, owed))))
    return opts


def cond_label(ctx, condition_id: str) -> str:
    """條件 id 給玩家看的字（存檔裡只存 id；清單換了也寫得出來）。"""
    kind, _, rest = condition_id.partition(":")
    c = ctx.content
    if kind == "material":
        return f"交三份{c.materials[rest].name}" if rest in c.materials else "交三份素材"
    if kind in ("scout", "strike"):
        loc = rest.partition(":")[0]
        place = c.locations[loc].name if loc in c.locations else loc
        return f"替他{'打探' if kind == 'scout' else '討伐'}{place}"
    return "交一筆銀兩"


def answer(ctx, cid: str, arg: str) -> list[str]:
    """接不接他的條件（terms:yes／terms:no）、請他兌現欠你的那一件（owed）、還他欠著的銀兩素材（repay，第二批）。
    你求他、他開條件：交銀、交素材當場付、當場做；打探、討伐掛成一件委託（同書信的委託），辦成了他欠你那一件
    （bounties._complete_commission 記 parley_owed）。他主動開口求你（plea）：接了是一件委託、記成你欠他的（到期沒做是食言）。"""
    s, c = ctx.state, ctx.content
    p = s.player
    name = c.characters[cid].name
    if arg == "owed":
        owed = p.parley_owed.get(cid)
        if not owed:
            return ["（此刻無法這麼做。）"]
        asks = {a.id for a in parley.ask_items(s, c, cid, ctx._side(), can_sortie=not prologue_rules.active(s, c))}
        if owed not in asks:
            return [parley.OWED_LATER.format(name=name)]
        p.parley_owed.pop(cid)
        return [parley.OWED_DONE.format(name=name)] + do(ctx, cid, owed)
    if arg == "repay":
        debt = p.parley_debts.get(cid)
        if debt is None or debt.task is not None:
            return ["（此刻無法這麼做。）"]
        paid = pay(ctx, debt.condition, debt.weight)
        if paid is None:
            return [parley.TERMS_SHORT]
        del p.parley_debts[cid]
        text = parley.debt_text(c, debt)
        parley.keep(s, c, cid, text)
        return paid + [parley.REPAID.format(name=name, cond=text)]
    terms = p.parley_terms.pop(cid, None)
    if terms is None:
        return ["（此刻無法這麼做。）"]
    if arg == "terms:no":
        return [(parley.PLEA_DECLINED if terms.plea else parley.TERMS_DECLINED).format(name=name)]
    if terms.plea:
        want = parley.Item(terms.condition, cond_label(ctx, terms.condition),
                           2 if terms.condition.startswith("strike:") else 1)
        due = owe(ctx, cid, want, parley.Item(terms.ask, parley.ask_label(c, terms.ask)), kind="plea")
        return [parley.PLEA_TAKEN.format(name=name, cond=want.label, due=parley.due_text(s, c, due),
                                         what=parley.ask_label(c, terms.ask))]
    weight = next((a.weight for a in lists(ctx, cid)[0] if a.id == terms.ask), 1)
    kind = terms.condition.partition(":")[0]
    if kind in ("silver", "material"):
        paid = pay(ctx, terms.condition, weight)
        if paid is None:
            p.parley_terms[cid] = terms
            return [parley.TERMS_SHORT]
        found = parley.record(s, cid)
        found.promised += 1
        parley.keep(s, c, cid, parley.debt_text(c, ParleyDebt(kind="terms", condition=terms.condition, weight=weight, due=0)))
        return paid + do(ctx, cid, terms.ask)
    item = parley.Item(terms.condition, cond_label(ctx, terms.condition))
    p.letter_seq += 1
    task = parley.commission(s, c, cid, item, parley.Item(terms.ask, parley.ask_label(c, terms.ask), weight), p.letter_seq)
    if task is None:
        return ["（此刻無法這麼做。）"]
    p.letters.append(Letter(id=p.letter_seq, kind="條件", sender=cid, at=s.world.time, text=terms.text, read=True, task=task))
    p.letters = p.letters[-c.config.figure_life.letters_keep:]
    parley.record(s, cid).promised += 1
    return [f"你答應了{name}：{item.label}。辦成了，下回見到他，他兌現答應你的事。"]


def pay(ctx, condition: str, weight: int) -> list[str] | None:
    """當場交銀、交素材（條件、還債共用）：手頭不夠回 None、什麼都不動；夠就扣掉，回那幾行變化。"""
    s, c = ctx.state, ctx.content
    p = s.player
    kind, _, rest = condition.partition(":")
    if kind == "silver":
        price = parley.silver_of(c, weight)
        if p.stats.get("silver", 0) < price:
            return None
        p.stats["silver"] -= price
        return [f"銀兩 -{price}"]
    need = c.config.parley.material_terms
    if rest not in c.materials or materials.held(s, rest) < need:
        return None
    materials.take(s, rest, need)
    return [f"{c.materials[rest].name} -{need}"]


def plea_lists(ctx, cid: str) -> tuple[list[parley.Item], list[parley.Item]]:
    """他主動開口時的兩份清單：他想請你做的事、他可以回報的事（A、C 兩次要一樣：亂數只看名號、人物、今天）。"""
    s, c = ctx.state, ctx.content
    rng = random.Random(f"請託|{s.player.name}|{cid}|{game_day(c, s.world)}")
    rewards = [a for a in lists(ctx, cid)[0] if a.id != "sortie"]  # 陪你出陣要你先開口，回報不給它
    return parley.wants(s, c, cid, rng), rewards


def plea_prompt(ctx, cid: str) -> str:
    """求見開場那一輪接在提示後面的一段（他主動開口求你）：他此刻沒心事、今天開口過、你跟他還有沒了的事是空的。
    假人（client 是 None）不叫模型，這段放了也用不到。"""
    s, c = ctx.state, ctx.content
    if cid not in c.characters or prologue_rules.active(s, c):
        return ""
    mood = parley.pleading(s, c, cid)
    if mood is None:
        return ""
    wanted, rewards = plea_lists(ctx, cid)
    if not wanted or not rewards:
        return ""
    return parley.plea_prompt(c, cid, mood, wanted, rewards)


def plea(ctx, cid: str, turn: companion_agent.CompanionTurn) -> companion_agent.CompanionTurn:
    """C 段：開場那一輪模型挑了請託與回報，驗過了記成他開的條件（plea），對話選單上多「接下／不接」。今天開口過了就不再開。"""
    s, c = ctx.state, ctx.content
    if not plea_prompt(ctx, cid):
        return turn
    wanted, rewards = plea_lists(ctx, cid)
    picked = parley.plea_pick(wanted, rewards, turn.want, turn.reward)
    parley.touch(s, c, cid).plea = True
    if picked is None:
        return turn
    want, reward = picked
    s.player.parley_terms[cid] = ParleyTerms(ask=reward.id, condition=want.id, text=turn.narrative, at=s.world.time, plea=True)
    return turn


def plan_open(ctx, cid: str) -> bool:
    """對話選單上「跟他商量打法…」：今天答應陪你出陣的就是他、這一仗還沒打、還沒商量過。"""
    b = ctx.state.player.parley_backing
    return (parley.on(ctx.content) and b is not None and b.figure == cid and b.plan is None
            and b.day == game_day(ctx.content, ctx.state.world))


def plan_prompt(ctx, cid: str) -> str:
    b = ctx.state.player.parley_backing
    return parley.plan_prompt(ctx.content, cid, b.region if b is not None else None) if plan_open(ctx, cid) else ""


def plan(ctx, cid: str, prepared: companion_agent.PreparedTurn | None, said: str | None) -> list[str]:
    """出陣前跟他商量打法（同放手一搏）：模型只評成功率、寫成敗兩版，引擎夾在 plan_floor～plan_cap、自己擲。
    成了這一仗他的部曲出力加倍、沒成這一仗他幫不上忙（Game._act 的 train 那一支照 parley_backing.plan 算）。不扣體力、不算輪數。"""
    s, c = ctx.state, ctx.content
    if not plan_open(ctx, cid) or said is None:
        return ["（此刻無法這麼做。）"]
    try:
        turn = companion_agent.prepared_turn(prepared)
        if turn is None:
            request = companion_agent.build_request(s, c, ctx.world, cid, PLAN_OPTION, said, free=True,
                                                    extra=plan_prompt(ctx, cid), required=parley.PLAN_FIELDS)
            turn = companion_agent.generate_turn(ctx._quick_client(), request.messages, request.required)
    except companion_agent.DialogueUnavailable:
        return [f"{c.characters[cid].name}沉吟不語。"]
    if turn.willing is None:  # 模型沒評（schema 已經不准，以防萬一）：當這一輪沒談成、打法照舊可以再商量，不默默夾到 plan_floor
        return [f"{c.characters[cid].name}沉吟不語。"]
    cfg = c.config.parley
    chance = max(cfg.plan_floor, min(cfg.plan_cap, int(turn.willing)))
    hit = parley.plan_roll(s, cid) <= chance
    s.player.parley_backing.plan = hit
    name = c.characters[cid].name
    text = turn.narrative if hit else ((turn.narrative_no or "").strip() or f"{name}搖了搖頭，沒有照你說的布置。")
    companion_agent._record_turn(s, cid, said, turn.model_copy(update={"narrative": text}))  # 談話畫面寫他這一句、下一輪記得談過打法
    return [f"你：「{said}」", text, (parley.PLAN_HIT if hit else parley.PLAN_MISS).format(name=name)]


def road_option(ctx, j: Journey) -> Option | None:
    """他帶你走的這一趟（parley_escort）：每到一站一次，「跟他說…」。"""
    s, c = ctx.state, ctx.content
    cid = s.player.parley_escort
    if not parley.on(c) or cid is None or cid not in c.characters or s.player.parley_road_leg == j.reached:
        return None
    return Option(id=ROAD_SAY, label=parley.ROAD_BUTTON.format(name=c.characters[cid].name))


def backing_here(ctx) -> str | None:
    """今天答應陪你出陣、而且你此刻就在他那一帶：回那位人物的 id。"""
    s, c = ctx.state, ctx.content
    b = s.player.parley_backing
    if b is None or b.day != game_day(c, s.world):
        return None
    here = figure_life._region(c, s.player.location)
    return b.figure if b.region is None or here == b.region else None


def forsake_all(ctx) -> list[str]:
    """叛投之後欠著的都算食言（Game._defect_step 在 defection.defect 之後接這一句；原本直接叫 parley.forsake_all）。"""
    return parley.forsake_all(ctx.state, ctx.content)


def road_cell(ctx, j: Journey) -> list[Option]:
    """road/parley 那一格（core_seams，全部拆包第 56 批）：NPC 智能 2.1，他帶你走的這一趟，每到一站跟他說一句。跟著人結伴同行時路線由帶頭的人定，這一格沒有（原本那一支早一步 return）。"""
    if travel_base.following(ctx.state) is not None:
        return []
    road = road_option(ctx, j)
    return [] if road is None else [road]
