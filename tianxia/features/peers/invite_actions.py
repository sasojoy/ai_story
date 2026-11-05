"""邀請框：打招呼（挑釁）、名帖、切磋、論武、結伴同行共用的 invite:yes|no|cancel:<編號>（原本 Game 上的 _invite_options、_invite、answer_invite、
answer_on_card、_greet_back、_tell_sender、_invite_status；全部拆包第 37 批搬進來，行為一個字不變）。

這一包拿 invite: 前綴與 choose 掛鉤；答應時照邀請的種類分派：打招呼 greet_back、名帖 mingtie_actions.swap 在包裡，切磋 _spar、論武 _discuss
（第 38 批）、結伴同行 _join（移動包）留在 Game，經 ctx 叫。選單上怎麼排（Game._everyday_options 第 1295 行）不能動，所以 Game 留 _invite_options 的委派。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import journal
from tianxia.characters import CharacterStore
from tianxia.core.option import Option
from tianxia.journal import Draft

from . import actions, invites, mingtie_actions, social
from . import mingtie as mingtie_rules

if TYPE_CHECKING:
    from tianxia.engine import Game

# 玩家之間的邀請（FB-117；待 joy 潤）：答應了卻沒成、邀請作廢時，發邀請的那個人下次同步看到的一句（以前邀請悄悄不見）
INVITE_LAPSED = "{who}想答應你的{what}，沒能成局，這份邀請作廢了。"
INVITE_LAPSED_AWAY = "那時你已經不在場。"  # 答應的那一刻他不在這裡了（下線、走了）


def title(ctx, arg: str) -> str:
    """invite:<回應>:<編號> 這一下江湖紀錄的標題（原本 Game._action_title 的 invite 那一支）。"""
    inv = invites.find(ctx.state.world, arg.partition(":")[2])
    if inv is None:
        return "邀請"
    verb = arg.partition(":")[0]
    what = invites.kind_name(inv.kind)
    return {"yes": f"{what}・{inv.sender}", "no": f"婉拒{what}", "cancel": "收回邀請"}.get(verb, f"與{inv.sender}")


def options(ctx) -> list[Option]:
    """閒著的時候：別人發給你、而且就在你這個地點的邀請（答應、婉拒），你發出去還在等的（收回）。逾時的不列。"""
    s, c = ctx.state, ctx.content
    p = s.player
    opts: list[Option] = []
    for inv in invites.incoming(s.world, p.name):
        if inv.location != p.location:
            continue
        what = invites.kind_name(inv.kind)
        gesture = social.gesture_of(inv)
        if gesture is not None:  # 打招呼：固定的幾種回禮，不理就等它逾時（玩家互動第二層）
            opts += [Option(id=f"invite:{r}:{inv.id}", label=f"回{inv.sender}：{did}") for r, did in gesture.replies]
            continue
        if inv.kind == "travel":  # 結伴同行：答應不花體力（趕路、疾行的體力出發時各付各的）
            opts.append(Option(id=f"invite:yes:{inv.id}", label=f"答應{inv.sender}的{what}"))
        elif inv.kind == "mingtie":  # 回帖不花什麼；自己還沒做名帖回不了（灰的寫為什麼）
            opts.append(Option(id=f"invite:yes:{inv.id}", label=f"回{inv.sender}的名帖", enabled=p.mingtie is not None,
                               note="" if p.mingtie is not None else mingtie_rules.NO_CARD))
        elif inv.kind == "discuss":
            # 論武要挑自己出哪一樣：在他的玩家卡上答（discuss.buttons）；選單上這一顆引擎不收（灰的，整季機器人與假人不會按到），
            # 網頁把它畫成「打開他的玩家卡、捲到答應那一格」的鈕（social.calls 帶 peer，FB-117），字照舊寫去哪裡答
            opts.append(Option(id=f"invite:yes:{inv.id}", enabled=False, label=f"答應{inv.sender}的{what}（在對方的玩家卡上挑你要出的）"))
        else:
            opts.append(ctx._cost_option(f"invite:yes:{inv.id}", f"答應{inv.sender}的{what}", c.config.action_cost["train"]))
        opts.append(Option(id=f"invite:no:{inv.id}", label=f"婉拒{inv.sender}的{what}"))
    for inv in invites.outgoing(s.world, p.name):
        if inv.kind in ("greet", "mingtie"):
            continue  # 打招呼、名帖不用收回：等回禮、回帖，沒回就過去了
        opts.append(Option(id=f"invite:cancel:{inv.id}", label=f"收回給{inv.target}的{invites.kind_name(inv.kind)}邀請"))
    return opts


def invite(ctx, arg: str) -> list[str]:
    """選單上的邀請選項：invite:yes|no|cancel:<編號>。對方那一份照玩家卡的做法拿（_peer），做完存回去。"""
    verb, _, invite_id = arg.partition(":")
    inv = invites.find(ctx.state.world, invite_id)
    if inv is None:
        return ["這份邀請已經不在了。"]
    other = None if verb == "cancel" else actions.peer(ctx, inv.sender)
    msgs = answer_invite(ctx, inv, other, verb)
    if other is not None:
        CharacterStore(ctx.world.db).save(other.state)
    return msgs


def answer_invite(
    ctx, inv, other: Game | None, verb: str, item: str = "", proposed: tuple[str | None, str] | None = None,
) -> list[str]:
    """答應（yes）、婉拒（no）、收回（cancel）一張邀請。other 是另一個人那一份（_peer；他不在這裡了是 None）；
    呼叫端負責把 other 存回去（玩家卡走 peer_act，選單走 _invite）。論武答應時 item 是你出的那一樣，proposed 是鎖外取好的名字
    （discuss_request 的 C 段；沒給才在鎖裡叫模型，整季腳本與測試）。"""
    s = ctx.state
    what = invites.kind_name(inv.kind)
    if verb == "yes" and inv.kind == "discuss" and other is not None and ctx.discuss_invite_problem(inv, other) is None:
        problem = ctx.discuss_item_problem(inv, other, item)
        if problem is not None:  # 是你挑的那一樣不行（同一樣、合不成）：換一樣再答就好，邀請留著（FB-117）
            return [problem]
    invites.drop(s.world, inv.id)
    ctx._save_season()
    if verb == "cancel":
        ctx.touched.add(inv.target)  # 他畫面上那兩顆答應、婉拒要拿掉
        ctx._outcome("收回邀請", f"你收回了給{inv.target}的{what}邀請。")
        return [f"你收回了給{inv.target}的{what}邀請。"]
    if other is None:
        if verb == "yes":
            tell_sender(ctx, inv, None, INVITE_LAPSED_AWAY)
        return [social.GONE]
    ctx.touched.add(other.state.player.name)
    gesture = social.gesture_of(inv)
    if gesture is not None:
        return greet_back(ctx, inv, other, gesture, verb)
    if verb == "no":
        other._write(f"{s.player.name}婉拒了{what}", [f"{s.player.name}拱手婉拒了你的邀請。"])
        ctx._outcome("婉拒", f"你婉拒了{inv.sender}的{what}。")
        return [f"你婉拒了{inv.sender}的{what}。"]
    if inv.kind == "travel":
        return ctx._join(inv, other)
    if inv.kind == "mingtie":
        return mingtie_actions.swap(ctx, inv, other)
    if inv.kind == "discuss":
        return ctx._discuss(inv, other, item, proposed)
    return ctx._spar(inv, other)


def answer_on_card(ctx, inv, other: Game, verb: str) -> list[str]:
    """玩家卡上回應他遞來的打招呼、結伴（social 的回禮、答應、婉拒那幾顆，FB-117）：跟場景底下那一顆（選單的 invite: 選項，
    走 choose）同一個結果、同一則江湖紀錄（標題照 _action_title，草稿同 choose）。other 是 peer_act 那一份，由它存回去。"""
    ctx._draft = Draft(title(ctx, f"{verb}:{inv.id}"))
    try:
        msgs = answer_invite(ctx, inv, other, verb)
        journal.add_entry(ctx.state, ctx._draft.entry(ctx.state.world.time, msgs))
    finally:
        ctx._draft = None
    return msgs


def greet_back(ctx, inv, other: Game, gesture: social.Gesture, verb: str) -> list[str]:
    """回禮（打招呼）：兩邊各記一則。"""
    me = ctx.state.player.name
    did = dict(gesture.replies).get(verb)
    if did is None:
        return ["（沒有這種回禮。）"]
    line = social.taunt_line(inv, None)
    said = f"：「{line}」" if line else ""
    other._write(f"與{me}", [f"你向{me}{gesture.did}{said}，{me}{did}。"])
    heard = social.taunt_line(inv, ctx.state)  # 不接他的挑釁話的人，自己的紀錄也不寫那一句
    return [f"{inv.sender}{gesture.got}：「{heard}」" if heard else f"{inv.sender}{gesture.got}。", f"你{did}。"]


def tell_sender(ctx, inv, other: Game | None, why: str | None = None) -> None:
    """答應了卻沒成、邀請已經收掉：發邀請的那個人下次同步在江湖紀錄裡看到一句（FB-117：以前邀請悄悄不見）。why 是寫給他看的原因
    （「你」是他）；other 是 None（他不在這裡了）時從資料庫讀他那一份、寫完存回去。"""
    me, what = ctx.state.player.name, invites.kind_name(inv.kind)
    sender = other if other is not None else ctx._load_kin(inv.sender)
    if sender is None:
        return
    sender._write(f"{what}不成・{me}", [INVITE_LAPSED.format(who=me, what=what)] + ([why] if why else []))
    if other is None:
        ctx._save_kin(sender)
    ctx.touched.add(sender.state.player.name)


def status(ctx) -> dict:
    """玩家卡要的邀請（玩家互動第二層）：收到的（就在你這個地點的）與發出去還在等的，各一份；剩幾秒是現實秒。
    答應、婉拒、收回照選單上的 id 送（invite:yes|no|cancel:<編號>，走 choose），發邀請走 /api/do/invite。"""
    s, c = ctx.state, ctx.content
    p = s.player

    def row(inv, who: str) -> dict:
        return {
            "id": inv.id, "kind": inv.kind, "kind_name": invites.kind_name(inv.kind), "who": who,
            "seconds_left": max(0, round((inv.expires_at - s.world.time) / c.config.time_scale)),
        }

    return {
        "incoming": [row(i, i.sender) for i in invites.incoming(s.world, p.name) if i.location == p.location],
        "outgoing": [row(i, i.target) for i in invites.outgoing(s.world, p.name)],
    }
