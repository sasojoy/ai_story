"""舊遊歷、序章雪恥、跟自家隊伍操練、守勢、遊歷推大勢（功能包 tianxia/features/sortie/；原本是 Game 上的 14 個方法，全部拆包第 17 批
「出陣三」，計畫 docs/superpowers/plans/2026-11-01-出陣包-第3批.md）。

ctx 是 Game（第一階）；只叫 tianxia/core/services.py 那張清單上的方法。本體照搬、一個字不改（self 換成 ctx、sortie 模組換成 rules）。
函式名＝原本的方法名去掉前導底線，一個例外：`_train_note` 是 `foes_note`（跟 actions.train_note〔行動列底下那一行〕分開）。另外兩個是從
Game 原位收來的：`train_fight`（`Game._act` 的 train 那一支：扣體力、並肩出陣、出陣或遊歷）、`train_squad`（`Game._fight_squad` 的
act:train 那一支）。Game 留 8 個一行委派（核心的單打服務 `_squad_encounter`、軍情的 `_order_options`、假人、測試、腳本還在叫）。
包裡互相叫直接叫這裡與 actions、duel_actions 的函式；測試、腳本換掉的經 ctx 叫，換掉的才打得到：`ctx._train()`、`ctx._sortie()`、
`ctx.train_trend_push(...)`、`ctx._train_push(...)`、`ctx._parley_backing_here()`、`ctx.sorties_left()`，與本來就在 Game 上的服務
（`ctx.odds`、`ctx._push_room`、`ctx.push_trend`、`ctx._present`、`ctx._order_credit`……）。
"""
from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from tianxia import calendar, team
from tianxia import howto  # 過渡：待搬（遊歷那一行的句子）
from tianxia import materials  # 共用規則層（素材：打贏會不會掉）
from tianxia import mounts  # 共用規則層（坐騎：必敗先問的那一句寫策馬脫身的機會）
from tianxia import opportunities  # 過渡：待搬（守勢之後的收容流民，正式版乙一）
from tianxia import orders  # 過渡：待搬（軍令：截糧時那一帶的敵方運糧隊）
from tianxia import precise  # 共用規則層（一類一顆：守勢再加跟守一樣的經驗心得）
from tianxia import prologue as prologue_rules  # 共用規則層（序章：雪恥那一步的對手與寫好的結果）
from tianxia import territory  # 共用規則層（地盤：站的照控制方）
from tianxia.core.option import Option
from tianxia.core.services import BACKED_LINE, BIG_FIGHT_WAIT, PLAN_MISS, drill_share  # 並肩出陣的兩句（第 20 批：原本 import parley）
from tianxia.events import pick_event  # 過渡：待搬（遊歷打完的戰後事件）
from tianxia.models import Location, Squad
from tianxia.rules import front_of, resolve_trend

from . import actions  # 出陣本體（第 1 批）：出陣開著時遊歷的對手池、守勢拿這一處自家那一路的數字
from . import duel_actions  # 出陣約戰（第 2 批）：約戰開著時守勢收進此地、一天記一點貢獻，出陣那一格不打仗
from . import rules
from .rules import TRAIN_CONFIRM, TRAIN_CONFIRM_RIDING

if TYPE_CHECKING:
    from tianxia.engine import Game


# ── act:train 打的那一場（原 Game._act 的 train 那一支、Game._fight_squad 的 act:train 那一支）──


def train_fight(ctx: Game, prepared) -> list[str]:
    """按出陣（遊歷）那一格、要打的那一場（Game._act 原本的 train 那一支；約戰開著時打開那張卡在 actions.train_run 前面接走）：扣這一下的體力，
    出陣（出陣探索與地盤設計第二節）；序章的雪恥與地盤關著的季照舊是遊歷。NPC 智能 2.0的並肩出陣：今天答應陪你的人在這一帶，這一仗本人威力
    多幾成（第二批：商量過打法，成了加倍、沒成打空）。prepared 不用（同原位）。"""
    ctx.state.player.stamina -= ctx._action_costs()["train"]  # 原位：不花體力的行動（上面那些）不必算（要翻武學的資料）
    backing = ctx._parley_backing_here()  # NPC 智能 2.0的並肩出陣：今天答應陪你的人在這一帶，這一仗本人威力多幾成
    share = ctx.content.config.parley.backing_share
    plan = ctx.state.player.parley_backing.plan if backing else None  # 第二批：商量過打法，成了加倍、沒成打空
    share = share * 2 if plan else 0.0 if plan is False else share
    with team.backed(1 + share if backing else 1.0):
        msgs = ctx._sortie() if rules.on(ctx.content) and not prologue_rules.active(ctx.state, ctx.content) else ctx._train()
    if backing:
        ctx.state.player.parley_backing = None
        name = ctx.content.characters[backing].name
        msgs.insert(0, BACKED_LINE.format(name=name, pct=round(share * 100)) if share else PLAN_MISS.format(name=name))
    return msgs


def train_squad(ctx: Game) -> Squad | None:
    """出陣（遊歷）那一格按下去會打哪一路（Game._fight_squad 原本的 act:train 那一支；大場面判讀問）：約戰開著時是貼約戰（或截糧，
    不判大場面），不打；遇上自己人是操練，不打架；其餘是 train_pick 那一路。"""
    if duel_actions.duel_on(ctx):
        return None  # 約戰開著：出陣那一格是貼約戰（或截糧，不判大場面）
    pick = train_pick(ctx, ctx.content.locations[ctx.state.player.location])
    return None if pick is None or ctx._drills_with(pick) else pick  # 遇上自己人是操練，不打架


# ── 舊遊歷：鈕、那一行、對手池、大場面挑哪一路、打一場（原 Game._train_option、_train_note、_train_line、_train_squad_ids、_big_trip、
# _train_pick、_train）──


def train_option(ctx: Game, loc: Location, cost: int, odds: bool, name: str = "遊歷", tail: str = "") -> Option:
    """遊歷的按鈕（name：出陣的攻寫「出陣・攻」、序章寫「雪恥」；tail：出陣的「今日還能 N 次」，接在體力後面）。遇上自己陣營的隊伍是操練、不會輸（見 drill），所以只有自己人的地盤寫成「操練・零風險」，
    不拿自己人去算勝算「必敗」（試玩回饋 FB-008）；自己人與外人都有的地方，勝算只看真的會打的那幾路。
    這一趟會是大場面（備料挑到的那一路，見 train_pick）時，按下去要等模型判讀：wait 寫「兩人對峙……」。"""
    squads = [ctx.content.squads[sid] for sid in train_squad_ids(ctx, loc)]
    foes = [squad for squad in squads if not ctx._drills_with(squad)]
    if not foes:
        return ctx._cost_option("act:train", "操練", cost, note="零風險")
    note = foes_note(ctx, foes, odds and prologue_rules.fight_tier(ctx.state, ctx.content) is None)  # 序章的勝負寫好了，不標勝算
    if len(foes) < len(squads):
        note += "・或與自己人操練"
    option = ctx._cost_option("act:train", name, cost, note=f"{tail}・{note}" if tail else note)
    if "必敗" in note.split("・"):  # FB-095：剛出師的人疾行到敵營按遊歷，三場就掉三分之一的銀兩
        ride = mounts.escape(ctx.state, ctx.content)  # 騎著馬策馬脫身的機會（5.11）：_lose_silver 擲的就是它
        option.confirm = TRAIN_CONFIRM_RIDING.format(odds=mounts.odds_text(ride)) if ride > 0 else TRAIN_CONFIRM
    pick = train_pick(ctx, loc)
    if (pick is not None and not ctx._drills_with(pick) and ctx.is_big(pick)
            and prologue_rules.fight_tier(ctx.state, ctx.content) is None):  # 寫好的那一場不等模型
        option.wait = BIG_FIGHT_WAIT
    return option


def foes_note(ctx: Game, squads: list[Squad], odds: bool) -> str:
    """遊歷按鈕上的補充說明（原 Game._train_note）：對手是誰、勝算多少（勝算的計算比較貴，所以照既有慣例吃 odds 旗標）。"""
    who = squads[0].name if len(squads) == 1 else f"{len(squads)} 路對手"
    if not odds:
        return who
    # 多路對手時以**最強的**那個當參考（真的開打平常是用 Game.rng 隨機挑；池子裡有大場面對手的地方照 train_pick 挑，
    # 見 train）：這個標籤的用途是警告玩家，寧可低估也不要給出過度樂觀的承諾。
    hardest = max(squads, key=lambda s: s.difficulty)
    return f"{who}・{ctx.odds(hardest.id)}"


def train_line(ctx: Game, loc: Location) -> str:
    """遊歷那一行：這裡會打的對手打贏給什麼（Game._battle_rewards：銀兩、心得、經驗、掉素材），遇上自己人是操練
    （drill：對手的 drill_reward_share、不給銀兩素材），打贏或操練推不推大勢：train_trend_push 會推的線裡，有一條今天
    還推得動（_push_room，跟 push_trend 同一個上限的算法；審查 M1：推滿了那一行就不說推動戰局）。第一季的規則沒開時沒有上限。"""
    c = ctx.content
    squads = [c.squads[sid] for sid in train_squad_ids(ctx, loc)]
    foes = [squad for squad in squads if not ctx._drills_with(squad)]
    own = [squad for squad in squads if ctx._drills_with(squad)]
    share = c.config.drill_reward_share
    gains = [word for word, on in (
        ("銀兩", any(q.reward_silver for q in foes)), ("心得", any(q.reward_xinde for q in foes)), ("經驗", any(q.exp for q in foes)),
    ) if on]
    drill_gains = [word for word, on in (
        ("心得", any(drill_share(q.reward_xinde, share) for q in own)), ("經驗", any(drill_share(q.exp, share) for q in own)),
    ) if on]
    drops = any(materials.may_drop(q, c) for q in foes)
    push = any(delta and ctx._push_room(line) > 0 for line, delta in ctx.train_trend_push(loc.id).items())
    return howto.train_line(bool(foes), gains, drops, push, drill_gains, bool(own))


def big_trip(ctx: Game, loc: Location) -> bool:
    """這裡遊歷可能撞上大場面：池子（train_squad_ids）裡有不是自己人的大場面對手。這種地點的遊歷一律照 train_pick 挑對手
    （Task 2 審查修正 3）；正式內容目前沒有這種地點，所以每一處遊歷照舊用 Game.rng 挑。"""
    squads = (ctx.content.squads[sid] for sid in train_squad_ids(ctx, loc))
    return any(ctx.is_big(squad) and not ctx._drills_with(squad) for squad in squads)


def train_pick(ctx: Game, loc: Location) -> Squad | None:
    """池子裡有大場面對手（big_trip）的地點，這一趟遊歷遇上哪一路（計畫三 G1、Task 2 審查修正 3）：照（名號、地點、戰報流水號）
    雜湊，從 train_squad_ids 挑一路；沒有對手是 None。按鈕的「兩人對峙」、備料（A 段）、套用（C 段）、判讀失敗照平常打，
    看的都是它：A、C 之間流水號不動（模型那一分鐘裡沒有打別的仗），兩邊挑到同一路；打過一場流水號就變，對手照樣輪替。
    池子裡沒有大場面對手的地點不用它，照舊用 Game.rng 隨機挑（亂數序列、整季模擬與好玩度量表的對手組成都不變）。"""
    ids = train_squad_ids(ctx, loc)
    if not ids:
        return None
    key = f"{ctx.state.player.name}|{loc.id}|{ctx.state.battle_seq}".encode()
    return ctx.content.squads[ids[int.from_bytes(hashlib.sha256(key).digest()[:4], "big") % len(ids)]]


def train(ctx: Game) -> list[str]:
    """遊歷：找這個地點的敵人打一場，**必定開打**；打完有機率接一段戰後的餘韻事件。

    這個行動在 sanguo-companions 合併時被整個移除，後果是整條隨機遭遇戰的路斷掉：
    `pick_event()` 只在「完全沒有合格候選」時才回 None，而有三個事件是「任何地點、
    可重複、探索觸發」，所以實測 22 個地點探索都是 100% 撞到事件，掛在 explore 後面的
    遭遇戰分支一次都沒執行過（整季只有劇情事件的 combat 選項那 3 場）。

    打完之後的 `train_event_chance` 機率是給 `actions: ["train"]` 的事件用的——「拆招頓悟」
    與「錦衣少年」的文字本來就是戰後餘韻（「一番苦戰之後…」「打鬥剛歇…」），合併時被改掛
    到 explore，於是在集市散步也會冒出來。現在它們回到正確的位置。
    """
    loc = ctx.content.locations[ctx.state.player.location]
    # 池子裡有大場面的對手：照 train_pick 挑，跟按鈕、備料、套用、判讀失敗的退路都是同一路（鎖外判讀過的單子就是它，
    # _squad_encounter 照對手對上判讀）；沒有就照舊用 Game.rng 隨機挑——正式內容每一處都是這樣（Task 2 審查修正 3）
    if big_trip(ctx, loc):
        squad = train_pick(ctx, loc)
    else:
        squad = ctx.content.squads[ctx.rng.choice(train_squad_ids(ctx, loc))]
    msgs = ctx._squad_encounter(squad.id)
    if prologue_rules.active(ctx.state, ctx.content):
        return msgs  # 序章裡打完不接戰後事件（新手引導計畫一）
    if ctx._drills_with(squad):
        return msgs  # 操練沒有打架，不接「一番苦戰之後」這類戰後事件（試玩回饋 FB-001）
    if ctx.rng.random() < ctx.content.config.train_event_chance:
        event = pick_event(ctx.state, ctx.content, "train", ctx.rng)
        if event is not None:
            msgs += ctx._present(event, "train")
    return msgs


def train_squad_ids(ctx: Game, loc: Location) -> list[str]:
    """遊歷可能遇上的對手：地點的敵人，加上軍令帶來的（截糧時那一帶的敵方運糧隊，計畫 T6）。
    開關關著、沒有截糧軍令時就是 loc.enemies 本身，亂數的抽法跟以前一樣。
    序章（新手引導計畫一）：只有這一步寫的對手（雪恥那一步才有斷眉），草廬自己沒有敵人。"""
    if prologue_rules.active(ctx.state, ctx.content):
        return prologue_rules.enemies(ctx.state, ctx.content)
    if rules.on(ctx.content):  # 出陣：只有攻才打，對手是 sortie_foes；守、散人沒有對手
        loc_mode = actions.sortie_mode_of(ctx, loc)
        return actions.sortie_foes(ctx, loc) if loc_mode == "attack" else []
    base = territory.squads_at(ctx.state.world, ctx.content, loc.id)  # 地盤易手：站的照控制方（關著時就是 loc.enemies）
    extra = orders.extra_enemies(ctx.state, ctx.content, loc.id, ctx._side())
    return base + [sid for sid in extra if sid not in base] if extra else base


# ── 跟自家隊伍操練（原 Game._drill、_drill_push、drill_scale）──


def drill_scale(ctx: Game) -> float:
    """操練推大勢的倍數：季長倍數；季長倍數小於 1 時再乘 Config.drill_long_season_share（0.5，PM 2026-10-12：操練給的聲勢
    不該佔那麼大）——14 天的季約 0.09；週末設定照舊 1。"""
    scale = ctx.season_scale()
    return scale * ctx.content.config.drill_long_season_share if scale < 1 else scale


def drill_push(ctx: Game, trend_id: str, delta: int) -> list[str]:
    """操練推一條線：照 drill_scale 縮放。倍數是 1（週末設定）時照舊交給 push_trend，一個字都不變；
    第一季的規則開著時縮放後的量照舊經過 push_trend 的人數緩衝、每人每曆日上限與零頭累積；規則關著的季零頭記在這一季的
    trend_accum（_carry），滿一點才真的推、才回推動那一行，沒推到整點的這一下什麼都不寫。"""
    scale = drill_scale(ctx)
    if scale >= 1:
        return ctx.push_trend(trend_id, delta, source="drill")
    amount = delta * scale
    if calendar.season_one_on(ctx.state.world, ctx.content):
        return ctx.push_trend(trend_id, amount, source="drill")
    whole = ctx._carry(trend_id, amount)
    return ctx.push_trend(trend_id, whole, source="drill") if whole else []


def drill(ctx: Game, squad: Squad) -> list[str]:
    """在自己陣營的地方遊歷：不打自己人，一起操軍擺陣（企劃者 2026-10-02 決定）。不會輸、不扣氣血；
    給經驗與心得，但只給對手的三成（Config.drill_reward_share，戰鬥系統第八節）；不給銀兩、不掉素材（不搶自己人）；
    地點的大勢推動往自己陣營有利的方向推，推的量照季長縮放（drill_push，FB-165）。"""
    s, c = ctx.state, ctx.content
    p = s.player
    loc = c.locations[p.location]
    msgs = [f"你與{squad.name}一同操軍擺陣，軍心為之一振。"]
    ctx._outcome("操練", msgs[0])
    msgs += ctx._drill_gains(squad)
    for trend_id, delta in ctx.train_trend_push(loc.id).items():
        msgs += drill_push(ctx, trend_id, delta)
    return msgs


# ── 遊歷推大勢（原 Game._train_push、train_trend_push）──


def train_push(ctx: Game, trend_id: str, delta: int) -> int:
    """遊歷（打贏或操練）推大勢：量照地點設定；自己陣營對這條線有目標就往目標方向推，散人和
    沒有這條線目標的陣營照地點原本的方向（企劃者 2026-10-02 決定）。trend_id 是換算過、真的會動的那條線。"""
    goal = ctx._goals().get(trend_id, 0)
    return abs(delta) * goal if goal else delta


def train_trend_push(ctx: Game, loc_id: str | None = None) -> dict[str, int]:
    """在這個地點（預設所在地）遊歷打贏或操練時，各條大勢線會被推多少（照自己的陣營，見 train_push）。
    鍵是真的會動的那條線：內容寫的戰線或 front 先照 rules.resolve_trend 換過（開關關著時一律是黃巾聲勢）。
    豪強照依附那一軍（_goals）；推割據 2026-10-31 連豪強第三方一起拿掉。"""
    loc = ctx.content.locations[loc_id or ctx.state.player.location]
    pushes: dict[str, int] = {}
    for key, delta in loc.train_trend.items():
        target = resolve_trend(ctx.content, ctx.state.world, key, loc.id)
        if target is not None:
            pushes[target] = pushes.get(target, 0) + ctx._train_push(target, delta)
    return pushes


# ── 守勢（原 Game._duty_option、_duty；act:duty）──


def duty_option(ctx: Game, name: str) -> Option:
    """守勢行動的鈕。出陣開著時每用一次扣一次出陣次數（PM 2026-10-14：跟攻、守共用每日的次數），鈕上寫今天還能幾次、
    用完灰掉、寫跟出陣同一句；關著照舊。領地爭奪在這一季生效時，站在不是自家的區塊（別人的、沒佔下的中立地）灰掉寫原因，
    按下去不扣體力與次數、不推線、不記守城（裁決 24；choose 照選單驗，灰的按不下去）。"""
    c = ctx.content
    cost = c.config.duty_stamina
    problem = rules.duty_problem(c, ctx.state.world, ctx._side(), ctx.state.player.location)
    if problem:
        return Option(id="act:duty", label=f"{name}（{problem}）", enabled=False)
    if not rules.on(c) or duel_actions.duel_on(ctx):  # 約戰開著（減法季批 3b）：收進此地、不佔出陣的次數
        return ctx._cost_option("act:duty", name, cost)
    left = ctx.sorties_left()
    if left <= 0:
        return Option(id="act:duty", label=f"{name}（{rules.USED_UP.format(n=c.config.sortie.per_day)}）", enabled=False)
    return ctx._cost_option("act:duty", name, cost, note=rules.LEFT_NOTE.format(n=left))


def duty(ctx: Game) -> list[str]:
    """第 1 階守勢行動（官軍巡哨、黃巾傳道、豪強保境安民；軍令文件 3.2、濃縮版內容表 2.6）：體力 duty_stamina，
    往己方推所在戰線 1 點（豪強照依附那一軍），算守城的個人部分。推力走 push_trend
    （緩衝、上限、貢獻）。"""
    s, c = ctx.state, ctx.content
    p = s.player
    loc = c.locations[p.location]
    duty = c.orders.duties[p.faction]  # 原位的名字照留（蓋過這個函式的名字：函式裡不再叫自己）
    front = front_of(c, loc.id)
    p.stamina -= c.config.duty_stamina
    duel = duel_actions.duel_on(ctx)  # 約戰開著（減法季批 3b；企劃者 2026-10-24 第 2 件）：收進此地——不佔出陣、不推線、不算守城，一天記一點貢獻
    if rules.on(c) and not duel:  # 出陣開著：守勢行動算一次出陣（PM 2026-10-14，duty_option）
        rules.spend(p, ctx._pill_day())
    text = duty.text.replace("{地點}", loc.name)
    msgs = [text]
    goals = {} if duel else ctx._goals()  # 約戰開著：線只在約戰結算、軍令、大勢人物、事件的痕跡這幾處動（設計 4.3）
    if goals.get(front):
        msgs += ctx.push_trend(front, goals[front], source="duty")
    msgs += opportunities.after_success(s, c, "duty", loc.id, ctx.rng)  # 收容流民（正式版乙一）
    if precise.on(c, s.world):  # 一類一顆（正式季整合 2.6）：再加跟守一樣的經驗心得（這裡自家那一路的全額；沒有自家隊伍不給，只推線）
        host = actions.sortie_host(ctx, loc)
        if host is not None:
            msgs += ctx._drill_gains(host, 1.0)
    if duel:  # 守城軍令改成應戰守住才記（計畫 4.0 之三第 17 條）；入伍段「出一次力」照舊認它
        return msgs + duel_actions.duty_credit(ctx) + ctx._guide(ctx._note_action("order"))
    credit = ctx._order_credit(kind="duty", location=loc.id, front=front)  # 地點：領地爭奪的守城認自家被推得最高的那一塊（裁決 11、翻地與爭搶）
    # 入伍段第 2 步「出一次力」：守勢行動不在這週軍令裡也算（FB-094：豪強第一週只有打擊，新人打不過；FB-093：巡哨、傳道就在營裡）
    return msgs + (credit or ctx._guide(ctx._note_action("order")))
