"""論武的動作（功能包 tianxia/features/peers/；原本是 Game 上的 discusses_left、discuss_items、_discuss_cost、discuss_refusal、discuss_invite、
_discuss_partner、discuss_request、_discuss_forge、discuss_problem、discuss_invite_problem、discuss_item_problem、_discuss；全部拆包第 38 批搬進來，行為一個字不變）。
ctx 是 Game；只叫 tianxia/core/services_list.md 那張清單上的方法。

論武（玩家互動第二層）：兩個人各出一個意境合成一個新的，兩人都拿到；首創算兩人共有，價錢各付一半。走 fusion.merge（fusion.Partner：對方出的那一個不必是你的、
不佔你的持有）；持有上限、「已經有了」照舊各自擋。武學不再拿來合（Joy 2026-10-21），論武跟著只剩意境。
開爐的是答應的那一方：request 是 A 段（鎖內、只讀）、discuss 是 C 段，B 段（鎖外取名）的殼接線 server.prepare_peer、screen_peer 留在 server.py（手冊 G10）；
發邀請的那一方接著照配方合出同一門（forge 的 ctx 是開爐的那一份 Game：對方那一份是 other）。
naming.generate 一律用模組屬性叫（tianxia/features/peers/tests/test_discuss.py 換掉它）。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import gender, insights, naming
from tianxia import fusion  # 過渡：待搬（合成與揣摩 fusion，SHARED_LATER）
from tianxia.core import presence
from tianxia.rules import season_one

from . import invite_actions, invites, pair_actions, social, spar_actions

if TYPE_CHECKING:
    from tianxia.engine import Game

DISCUSS_SAME = "兩個人出的是同一樣，論不出新東西。"
# 答應論武時對方那邊合不成：照他那一句的兩三個字（fusion.Refusal.short）換成從你這邊看的說法——他那一句原話是寫給他看的，
# 「你已經有了」的「你」是他（FB-243；待 joy 潤）。沒列到的只寫「某某那邊合不成。」
THEIR_SIDE = {
    "已經有了": "合出來的那一樣{him}已經有了",
    "持有滿了": "{him}的武學與意境已經滿了",
    "心得不足": "{him}的心得不夠",
    "體力不足": "{him}的體力不夠",
    "不能當料": "那一門的路數是寫死的，不能拿來合成",
}


def _refusal(text: str, short: str) -> str:
    """一句拒絕的話，帶兩三個字的 short（fusion.Refusal：論武答應的下拉清單上，合不成的那一項後面寫它，FB-117）。"""
    out = fusion.Refusal(text)
    out.short = short
    return out


def left(ctx, other: str) -> int:
    """這一對人這個遊戲日還能論武幾回（Config.discuss_per_pair_day；FB-116）。"""
    return pair_actions.pair_left(ctx, ctx.state.world.discuss_tally, ctx.content.config.discuss_per_pair_day, other)


def items(ctx) -> list[tuple[str, str]]:
    """論武時你出得了的：悟得的全服意境（「insight:<id>」；自己畫圖悟的私有意境不行）。回傳（鍵, 寫給人看的名字）。"""
    s, c = ctx.state, ctx.content
    out: list[tuple[str, str]] = []
    for insight_id in s.player.insights:
        insight = None if insights.is_own(insight_id) else insights.resolve(insight_id, c, ctx.world, s)
        if insight is not None:
            out.append((f"insight:{insight_id}", f"「{insight.name}」"))
    return out


def cost_of(ctx) -> tuple[int, int]:
    """論武這一邊付的（心得, 體力）：一爐意境合成的一半（fusion.half_price）。"""
    cfg = ctx.content.config
    return fusion.half_price(cfg.merge_xinde, cfg.merge_stamina)


def refusal(ctx, other: Game) -> str | None:
    """玩家卡上「論武」按不按得下去：規則開著、兩個人都閒著、付得起一半的體力、之間沒有一張還在等的論武邀請。
    休季（這一季收了）卡上不畫，直接打 API 也是這一句（FB-169）。"""
    s, c = ctx.state, ctx.content
    if not season_one(c, s.world) or s.world.ended:
        return "（此刻無法這麼做。）"
    cost = cost_of(ctx)[1]
    for who, me in ((ctx, True), (other, False)):
        problem = spar_actions.who_problem(ctx, who, me=me, what="論武", cost=cost)
        if problem is not None:
            return problem
    if left(ctx, other.state.player.name) <= 0:
        return social.pair_full(ctx, "discuss")
    if invites.between(s.world, s.player.name, other.state.player.name, "discuss") is not None:
        return "已經有一張論武的邀請在等回覆了。"
    return None


def send(ctx, other: Game, item: str) -> list[str]:
    """玩家卡上的「論武・以 X」：帶著你要出的那一樣發一張邀請，對方在卡上挑他出的那一樣答應才開爐。"""
    s = ctx.state
    problem = refusal(ctx, other)
    if problem is not None:
        return [problem]
    label = dict(items(ctx)).get(item)
    if label is None:
        return ["你身上沒有這一樣。"]
    name = other.state.player.name
    invites.expire(s.world)
    invites.send(s.world, ctx.content, "discuss", s.player.name, name, s.player.location, {"item": item})
    ctx._save_season()
    ctx.touched.add(name)
    return [f"你拿出{label}，邀{name}一起論武；等{gender.pronoun(other.state)}回覆。"]


def forge_pair(ctx, mine: str, theirs: str, other_name: str, fresh: bool = False):
    """兩樣東西排成一爐意境合成：（兩個意境的 id, 借來的那一份）。舊邀請上的「art:」交給 discuss_problem 擋。"""
    mid, tid = mine.partition(":")[2], theirs.partition(":")[2]
    return [mid, tid], fusion.Partner(lent=tid, name=other_name, price=cost_of(ctx), fresh=fresh)


def request(ctx, inv, other: Game, item: str) -> naming.NamingRequest | None:
    """論武的 A 段（鎖內、只讀）：答應的那一方出 item、發邀請的那一方出邀請上那一樣，這一爐要不要模型取名或挑？
    要就回單子（伺服器在鎖外交給 naming.generate，假人程式交給 bot_runner），不要是 None。
    C 段（_discuss）一定會擋的先問（discuss_invite_problem、discuss_item_problem：他正忙、論滿了、你挑的那一樣合不成……）：
    成不了就不開單、不叫模型，呼叫端照「不必取名」直接走 C 段，回的話、邀請作廢與通知都同以前，只是不等模型（FB-245）。
    C 段照樣重驗（A 到 C 之間狀態可能變）。"""
    if inv is None or inv.kind != "discuss":
        return None
    if invite_problem(ctx, inv, other) is not None or item_problem(ctx, inv, other, item) is not None:
        return None
    insight_ids, partner = forge_pair(ctx, item, inv.payload.get("item", ""), other.state.player.name)
    return fusion.forge_request(ctx.state, ctx.content, ctx.world, None, insight_ids, partner=partner)


def forge(ctx, mine: str, theirs: str, other_name: str, proposed, fresh: bool = False):
    """這一邊開一爐（意境合成，對方那一個當作借來的）：（合出來的那個意境, 訊息）；沒合成是 None。
    fresh：對方剛剛在這一次論武裡首創了這個配方（發邀請的那一方接著合，FB-243）。"""
    problem = ctx.discuss_problem(mine, theirs, other_name)
    if problem is not None:
        return None, [problem]
    insight_ids, partner = forge_pair(ctx, mine, theirs, other_name, fresh)
    return fusion.merge(ctx.state, ctx.content, ctx.world, ctx._quick_client(), *insight_ids, proposed, partner)


def merge_problem(ctx, mine: str, theirs: str, other_name: str) -> str | None:
    """這一邊合不合得成（拒絕的話；fusion.merge_problem，對方那一個當作借來的、價錢是一半）。只讀；假人挑要出哪一樣也問它。"""
    if not (mine.startswith("insight:") and theirs.startswith("insight:")):
        return fusion.DISCUSS_ARTS_GONE
    insight_ids, partner = forge_pair(ctx, mine, theirs, other_name)
    return fusion.merge_problem(ctx.state, ctx.content, ctx.world, *insight_ids, partner)


def invite_problem(ctx, inv, other: Game, *, for_sender: bool = False) -> str | None:
    """答應論武時，這一張邀請本身還成不成（不看你挑哪一樣）：還在發邀請的那個地點、兩個人都閒著付得起一半的體力、
    這一對這個遊戲日還沒論滿（FB-116）、他要出的那一樣還在他身上。不成就作廢：answer_invite 收掉、發邀請的人收到一句（FB-117）。
    for_sender：寫給發邀請的那個人看（「你」是他，_tell_sender 用）。"""
    them = other.state.player
    if inv.location != ctx.state.player.location:
        return presence.GONE
    cost = cost_of(ctx)[1]
    for who in (ctx, other):
        problem = spar_actions.who_problem(ctx, who, me=(who is ctx) != for_sender, what="論武", cost=cost)
        if problem is not None:
            return problem
    if left(ctx, them.name) <= 0:  # 邀請在等的時候，這一對人今天的帳被別處用滿了（FB-116）
        return social.pair_full(ctx, "discuss")
    if inv.payload.get("item", "") not in dict(items(other)):
        return "你身上已經沒有要出的那一樣了。" if for_sender else f"{them.name}身上已經沒有{gender.pronoun(them)}要出的那一樣了。"
    return None


def item_problem(ctx, inv, other: Game, item: str) -> str | None:
    """答應論武時你出 item 這一樣合不合得成：身上還有沒有、是不是跟他出的同一樣、兩邊各自合不合得成（fusion 的 *_problem）；
    合得成是 None。這一種不成是你挑的那一樣不行，換一樣再答就好，邀請留著（FB-117）。回的話帶 short（兩三個字），
    玩家卡上答應的下拉清單在合不成的那一項後面寫它（discuss.buttons）。先問過 discuss_invite_problem 才準。"""
    them = other.state.player
    theirs = inv.payload.get("item", "")
    if item not in dict(items(ctx)):
        return _refusal("你身上沒有這一樣。", "身上沒有")
    if item == theirs:
        return _refusal(DISCUSS_SAME, "同一樣")
    problem = ctx.discuss_problem(item, theirs, them.name)
    if problem is not None:
        return problem
    theirs_problem = other.discuss_problem(theirs, item, ctx.state.player.name)
    if theirs_problem is None:
        return None
    short, him = getattr(theirs_problem, "short", "") or "合不成", gender.pronoun(them)
    side = THEIR_SIDE.get(short)
    text = f"{them.name}那邊合不成：{side.format(him=him)}。" if side else f"{them.name}那邊合不成。"
    return _refusal(text, f"{him}那邊{short}")


def discuss(ctx, inv, other: Game, item: str, proposed) -> list[str]:
    """答應論武（C 段）：重驗（discuss_invite_problem、discuss_item_problem：還在發邀請的那個地點、兩個人都閒著、兩樣東西都還在
    各自手上、兩邊各自合得成），你先開爐（新配方的名字照 proposed），他接著照配方合出同一門；各付一半，各記一則江湖紀錄。
    驗不過就說一句為什麼（邀請已經收了），發邀請的那個人也收到一句（FB-117）。"""
    me, them = ctx.state.player, other.state.player
    theirs = inv.payload.get("item", "")
    problem = invite_problem(ctx, inv, other) or item_problem(ctx, inv, other, item)
    if problem is not None:
        invite_actions.tell_sender(ctx, inv, other, invite_problem(ctx, inv, other, for_sender=True))
        return [problem]
    made, msgs = forge(ctx, item, theirs, them.name, proposed)
    if made is None:
        invite_actions.tell_sender(ctx, inv, other)
        return msgs
    ctx.peer_brief = social.DISCUSS_BRIEF.format(thing=social.thing_label(made))
    # 配方剛登記：他照查表合出同一門，不取名；這一爐首創了的話，他那一句寫跟你一起首創（FB-243）
    _, their_msgs = forge(other, theirs, item, me.name, (None, ""), fresh=fusion.made_first(msgs))
    pair_actions.pair_tick(ctx, ctx.state.world.discuss_tally, them.name)
    ctx._save_season()
    other._write(f"論武・{me.name}", their_msgs)
    if ctx._draft is None:
        ctx._write(f"論武・{them.name}", msgs)
    else:
        ctx._outcome("論武", msgs[0])
    return msgs
