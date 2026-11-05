"""第 2 階與第 3、4 階的行動（功能包 military；全部拆包第 33 批；正式版乙一、戊一）：選單（做得了才出現、做滿就灰掉）、做一次（扣體力、記次數、過檢定才推大勢）。
原本 Game 上的 6 個方法（_rank2_options、_check_cost_note、_rank2、_rank_action_options、_rank_action_line、_rank_action）；名字去掉前導底線。第一個參數是 ctx。
rank2、rank_action 會改狀態。第 3、4 階的規則（誰做得了、在哪裡做得了、這週還剩幾次）在 rank_rules.py。
"""
from __future__ import annotations

from tianxia import calendar
from tianxia import events as event_rules  # 過渡：待搬（事件 events 的 check_note；events 還在 SHARED_LATER〔讀伏筆〕，第 34 批 PM 認定第 1 條：第 36、40 批收進共用規則層時改查詢服務）
from tianxia.core.option import Option
from tianxia.core.services import RANK_ACTION_PREFIX
from tianxia.models import Check, Location
from tianxia.rules import front_of, roll_check

from . import opp_rules as opportunities  # 同一包的機緣規則（原本 import 舊名 opportunities）
from . import rank_rules


def rank2_options(ctx, loc: Location) -> list[Option]:
    """第 2 階行動（設計 5.5；正式版乙一）：第 2 階以上、在有戰線的地方；今天做滿了就變灰、寫明。"""
    s, c = ctx.state, ctx.content
    action = opportunities.rank2_action(s, c)
    if action is None or front_of(c, loc.id) is None:
        return []
    if opportunities.rank2_left(s, c) <= 0:
        return [Option(id="act:rank2", enabled=False, label=f"{action.name}（今天已經做滿 {c.config.rank2_daily} 次）")]
    note = check_cost_note(ctx, action.check, c.config.rank2_stamina)
    return [ctx._cost_option("act:rank2", action.name, c.config.rank2_stamina, note=note)]


def check_cost_note(ctx, check: Check | None, cost: int) -> str:
    """有檢定的行動（第 2 階行動、第 3 階煽動起事）括號裡體力後面接的那一段：照事件選項的寫法寫檢定（企劃者裁決 E5.3：
    「{行動}（體力 N・{屬性名} {數值}：{心裡話}）」，標籤的樣子待 joy 潤）。體力不夠時不寫（審查 I1）：這些行動在「此地還能做」
    裡，網頁照原文印灰掉的標籤，帶著心裡話會讀成是屬性不夠才灰的，所以照舊只寫「{行動}（體力 N）」。沒有檢定是空字串。"""
    if check is None or ctx.state.player.stamina < cost:
        return ""
    return event_rules.check_note(check, ctx.state, ctx.content, ctx.world)


def rank2(ctx) -> list[str]:
    """做一次第 2 階行動：扣體力、記今天一次；過檢定才成功——成功往己方推所在戰線 rank2_push 點（push_trend），
    再替累積型的機緣記一次。軍令的記功是計畫戊的事。"""
    s, c = ctx.state, ctx.content
    p = s.player
    action = opportunities.rank2_action(s, c)
    loc = c.locations[p.location]
    front = front_of(c, loc.id)
    p.stamina -= c.config.rank2_stamina
    opportunities.count_rank2(s, c)
    if not roll_check(action.check, s, c, ctx.world, ctx.rng):
        return [action.fail.replace("{地點}", loc.name)]
    msgs = [action.ok.replace("{地點}", loc.name)]
    goal = ctx._goals().get(front)
    if goal:
        msgs += ctx.push_trend(front, goal * c.config.rank2_push, source="rank2")
    return msgs + opportunities.after_success(s, c, "rank2", loc.id, ctx.rng)


def rank_action_options(ctx, loc: Location) -> list[Option]:
    """第 3、4 階的行動（正式版戊一）：做得了（陣營、階；第 4 階是這一週在任）、這裡做得了（戰線、標籤、亂局）才出現，
    不是按了才說不行；這週做滿就灰掉、寫明。這個行動推的那條線今天已經推滿（每人每曆日上限，按下去只會推 +0）也灰掉、
    寫明（企劃者裁決 E1）；一次只寫一個原因，這週做滿先寫。還推得動一點的照常按、照常付。choose 照這份選單重驗，
    所以推滿之前拿到的舊選單按下去也一樣被拒絕、不扣體力、不記次數。"""
    s, c = ctx.state, ctx.content
    opts: list[Option] = []
    line = rank_action_line(ctx, loc.id)
    for action in rank_rules.mine(s, c):
        if not rank_rules.where_ok(s, c, action, loc.id):
            continue
        option_id = f"{RANK_ACTION_PREFIX}{action.id}"
        if rank_rules.left(s, c, action) <= 0:  # 7 天濃縮季照段記、寫「這一段」（calendar.week_word，FB-503）
            this = calendar.week_word("this_short", c, s.world)
            opts.append(Option(id=option_id, enabled=False, label=f"{action.name}（{this}已經做滿 {action.weekly} 次）"))
        elif line is not None and ctx._push_room(line) <= 0:
            opts.append(Option(id=option_id, enabled=False, label=f"{action.name}（今天這條線已經推滿）"))  # 新寫，待 joy 潤
        else:  # 有檢定的（煽動起事）照事件選項的寫法接在體力後面，體力不夠時不寫（裁決 E5.3、審查 I1，同 rank2_options）
            note = check_cost_note(ctx, action.check, action.stamina)
            opts.append(ctx._cost_option(option_id, action.name, action.stamina, note=note))
    return opts


def rank_action_line(ctx, loc_id: str) -> str | None:
    """第 3、4 階行動在這裡推哪一條線：所在的戰線（照 _goals：豪強分屬兩軍，照依附那一軍的目標）；沒有目標是 None（不推）。
    選單看推滿了沒、rank_action 真的推，都照這一個判斷（推割據 2026-10-31 連豪強第三方一起拿掉）。"""
    goals = ctx._goals()
    front = front_of(ctx.content, loc_id)
    return front if front is not None and goals.get(front) else None


def rank_action(ctx, action_id: str) -> list[str]:
    """做一次第 3、4 階的行動：扣體力、記這週一次（不論成敗）；有檢定的過了才算——推動走 push_trend（推所在戰線往己方，
    乘自己那一邊的目標），再替軍令記功（第 3 階 5 次、第 4 階 10 次；收哪幾種由計畫戊二定，現在沒有軍令收，記不到）。
    choose 已經驗過選項在選單上，所以 mine 裡一定找得到。"""
    s, c = ctx.state, ctx.content
    p = s.player
    action = next(a for a in rank_rules.mine(s, c) if a.id == action_id)
    loc = c.locations[p.location]
    front = front_of(c, loc.id)
    p.stamina -= action.stamina
    rank_rules.count(s, c, action)
    if action.check is not None and not roll_check(action.check, s, c, ctx.world, ctx.rng):
        return [action.fail.replace("{地點}", loc.name)]
    msgs = [action.ok.replace("{地點}", loc.name)]
    line = rank_action_line(ctx, loc.id)
    if line is not None:
        msgs += ctx.push_trend(line, ctx._goals()[line] * action.push, source="rank")
    return msgs + ctx._order_credit(kind=action.id, location=loc.id, front=front, weight=rank_rules.weight(action))
