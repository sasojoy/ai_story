"""結伴同行（功能包 tianxia/features/travel/；原本是 Game._join、join_refusal、_party_expires、_party、party_view、leave_party、_part_ways、_lead、
_partners、_share_road，全部拆包第 48 批）。ctx 是 Game（第一階）。
答應結伴（join、join_refusal）是玩家互動包 invite_actions.answer_invite 經 ctx._join 叫的；帶頭的人出發、改道、喊停（departure.depart、go_actions.halt）
叫 lead，路上小事收穫分給同行（road_actions.road）叫 share_road。跟著的人與帶頭的人各自一份 Game（ctx._kin 包起來），存回去由這裡的函式負責。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import atlas  # 過渡：待搬（輿圖：路程、結伴的體力與手上有事的檢查，第 50 批）
from tianxia import gender, materials, mounts
from tianxia.characters import CharacterStore, name_key
from tianxia.core import presence
from tianxia.core.services import ROAD_TASKS
from tianxia.state import Tagalong

from . import road_actions

if TYPE_CHECKING:
    from tianxia.engine import Game


def join(ctx: Game, inv, other: Game) -> list[str]:
    """答應結伴同行：重驗（還在發邀請的那個地點、兩個人都沒在跟別人、你身後也沒有人跟著你），記下跟著誰；兩邊各記一則。"""
    p = ctx.state.player
    refusal = ctx.join_refusal(inv.sender) if inv.location == p.location else presence.GONE.rstrip("。")
    if refusal is not None:
        ctx._tell_sender(inv, other)
        return [f"（{refusal}。）"]
    p.tagalong = Tagalong(leader=inv.sender, since=ctx.now)
    other._write(f"結伴同行・{p.name}", [f"{p.name}答應與你結伴同行：由你定去哪、怎麼走，出發時{gender.pronoun(p)}跟著走。"])
    return [f"你答應與{inv.sender}結伴同行，等{gender.pronoun(other.state)}動身。"]


def join_refusal(ctx: Game, leader: str) -> str | None:
    """答應跟 leader 結伴同行，不行的原因：他得還在這裡、兩個人都沒在跟別人、你身後也沒有人跟著你、你人不在路上。"""
    p = ctx.state.player
    if p.journey is not None:
        return "你在路上"
    if p.tagalong is not None:
        return f"你已經跟著{p.tagalong.leader}了"
    if party(ctx):
        return "已經有人跟著你走"
    other = ctx._peer(leader)
    if other is None:
        return presence.GONE.rstrip("。")
    if other.state.player.tagalong is not None:
        return f"{leader}已經跟著別人走了"
    return None


def party_expires(ctx: Game) -> None:
    """答應結伴之後，帶頭的人 party_wait_seconds（現實秒）之內沒動身，各走各的。"""
    p = ctx.state.player
    tag = p.tagalong
    if tag is not None and p.journey is None and tag.since < ctx.now - ctx.content.config.party_wait_seconds:
        p.tagalong = None
        ctx._write(f"結伴同行・{tag.leader}", [f"{tag.leader}遲遲沒有動身，你們各走各的。"])


def party(ctx: Game, catch_up: bool = False) -> list[Game]:
    """跟著你結伴同行、還算數的人（各自那一份 Game）：還在等你動身的（跟你同一個地點、沒過期），或已經跟著你在路上的。
    catch_up：先替他們補算路上的抵達（抵達終點就散了），帶他們出發、改道之前要用。"""
    if not hasattr(ctx.world, "db"):
        return []
    me = ctx.state.player
    out = []
    for state in CharacterStore(ctx.world.db).tagging(me.name):
        other = ctx._kin(state)
        if catch_up:
            other._arrivals()
        o = other.state.player
        if o.tagalong is None or o.tagalong.leader != me.name:
            if catch_up:
                ctx._save_kin(other)
            continue
        # 帶頭的人剛動身（lead）時 location 還是出發的那一站，所以還在等的人照樣認得出來
        waiting = o.journey is None and o.location == me.location \
            and o.tagalong.since >= ctx.now - ctx.content.config.party_wait_seconds
        if waiting or (o.journey is not None and me.journey is not None):
            out.append(other)
        elif catch_up:
            ctx._save_kin(other)
    return out


def party_view(ctx: Game) -> dict | None:
    """場景底下結伴同行的那一行：跟著誰（可以分道揚鑣），或誰跟著你。都沒有是 None。"""
    p = ctx.state.player
    if p.tagalong is not None:
        return {"lead": False, "names": [p.tagalong.leader], "text": f"你跟著{p.tagalong.leader}結伴同行，由對方定去哪、怎麼走。"}
    names = [g.state.player.name for g in party(ctx)]
    if not names:
        return None
    when = "一路同行" if p.journey is not None else "你動身時跟著走"
    return {"lead": True, "names": names, "text": f"{'、'.join(names)}與你結伴同行，{when}。"}


def leave_party(ctx: Game) -> list[str]:
    """場景底下的「分道揚鑣」（還在等帶頭的人動身時）：見 part_ways。在路上時走選單的 act:part。"""
    if ctx.state.player.tagalong is None:
        return ctx._log(["（你沒有跟著誰。）"])
    leader = ctx.state.player.tagalong.leader
    msgs = part_ways(ctx)
    ctx._write(f"結伴同行・{leader}", msgs)
    return ctx._log(msgs)


def part_ways(ctx: Game) -> list[str]:
    """不再跟著帶頭的人（他的紀錄記一句）。在路上的話照原本那一趟自己走下去（之後可以自己折返、改道）。"""
    p = ctx.state.player
    tag, p.tagalong = p.tagalong, None
    if tag is None:
        return []
    leader = ctx._load_kin(tag.leader)
    if leader is not None:
        leader._write(f"結伴同行・{p.name}", [f"{p.name}與你分道揚鑣。"])
        ctx._save_kin(leader)
        ctx.touched.add(tag.leader)
    return [f"你與{tag.leader}分道揚鑣。"]


def lead(ctx: Game, start: str | None, foot: int, told: str) -> list[str]:
    """結伴同行：帶頭的你出發、改道、喊停之後，跟著的人照抄這一趟（同樣的路、同樣的抵達時間，連步調 Journey.pace 一起抄：
    整隊照帶頭的人的坐騎走，partners 才認得出同行）。趕路、疾行的體力各付各的（裝備四欄 5.8）：foot 是不算坐騎的體力
    （atlas.route_foot_stamina；喊停是 0），每個跟著的人照自己的坐騎再省（atlas.ride_stamina、mounts.saving）。
    start 是你動身的地點（從路上改道、喊停時是 None）。跟不上的人（體力不夠、手上有事、已經不在這裡）就散了，兩邊各記一句。
    回傳寫給你的幾句。told 是寫進跟著的人紀錄的那一句。"""
    me = ctx.state.player
    j = me.journey
    lines: list[str] = []
    for other in party(ctx, catch_up=True):
        o = other.state.player
        cost = atlas.ride_stamina(foot, mounts.saving(other.state, ctx.content))  # 這個人自己騎的馬省下之後要付的
        # 路是帶頭的人認得的路，跟著的人不必自己認得（所以不問 travel_refusal），只看他手上有沒有事、體力夠不夠
        block = atlas.travel_block(other.state, ctx.content)
        if start is not None and (o.journey is not None or o.location != start):
            problem = presence.GONE.rstrip("。")
        elif start is not None and block is not None:
            problem = block.reason
        else:
            problem = None if o.stamina >= cost else f"體力不足，要 {cost} 體力"
        if problem is not None:
            o.tagalong = None
            other._write(f"結伴同行・{me.name}", [f"{me.name}{told.split('，')[0]}，你沒能跟上（{problem}）。"])
            lines.append(f"{o.name}沒能跟上，你們就此分開。")
        else:
            o.stamina -= cost
            o.journey = j.model_copy(deep=True)
            o.leg_actions = o.leg_actions | me.leg_actions
            other._write(f"結伴同行・{me.name}", [told] + ([f"體力 -{cost}"] if cost else []))
            if j.mode == "dash":
                other._arrivals()
            lines.append(f"{o.name}跟著你。")
        ctx._save_kin(other)
        ctx.touched.add(o.name)
    return lines


def partners(ctx: Game) -> list[Game]:
    """同一趟路上結伴的其他人（帶頭的與其他跟著的；路上小事的收穫分給他們）：補算過抵達，跟你走在同一段路上的。"""
    p, j = ctx.state.player, ctx.state.player.journey
    if j is None or not hasattr(ctx.world, "db"):
        return []
    leader = p.tagalong.leader if p.tagalong is not None else p.name
    states = CharacterStore(ctx.world.db).tagging(leader)
    if leader != p.name:
        head = CharacterStore(ctx.world.db).load(leader)
        states = ([head] if head is not None else []) + states
    out = []
    for state in states:
        if name_key(state.player.name) == name_key(p.name):
            continue
        other = ctx._kin(state)
        other._arrivals()
        oj = other.state.player.journey
        if oj is not None and oj.path == j.path and oj.reached == j.reached and oj.arrive_at == j.arrive_at:
            out.append(other)
        else:
            ctx._save_kin(other)
    return out


def share_road(ctx: Game, what: str, gain: tuple | None) -> list[str]:
    """路上小事的收穫分給同行的人（企劃者：每一樣收穫兩個人都有）：這一段路上這件事也算他做過了。
    有收穫上限的（心得、素材）照他自己這個遊戲日的上限給。回傳寫給你的幾句。"""
    lines: list[str] = []
    me = ctx.state.player.name
    name = ROAD_TASKS[what][0]
    for other in partners(ctx):
        o = other.state.player
        o.leg_actions.add(what)
        got: list[str] = []
        if gain is not None:
            kind, value = gain
            capped = kind in ("xinde", "material") and not road_actions.reward_due(other, "task")
            if capped:
                got = ["（這陣子的收穫拿滿了。）"]
            elif kind == "xinde":
                o.stats["xinde"] = o.stats.get("xinde", 0) + value
                road_actions.count_reward(other, "task")
                got = [f"心得 +{value}"]
            elif kind == "material":
                got = [materials.grant(other.state, ctx.content, value)]
                road_actions.count_reward(other, "task")
            elif kind == "rumor":
                got = [f"聽說：{value}"]
        if got:
            other._write(f"結伴同行・{me}", [f"同行的{me}{name}，你也有一份。", *got])
            lines.append(f"（同行的{o.name}也有一份。）")
            ctx.touched.add(o.name)
        ctx._save_kin(other)
    return lines
