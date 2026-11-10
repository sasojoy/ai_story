"""玩家之間的互動（企劃者 2026-10-08「假設 A 玩家在長社，B 玩家也過去的話，兩人可以做什麼互動」）。

第一層：看得到彼此。場景底下列「此地還有誰」（`here`），點名字打開一張玩家卡（`card`）：名號、門派・陣營・頭銜、等級、
身上兩門武學（只寫名字與品質），以及卡上的動作鈕。

卡上的動作是一張登記表（`ACTIONS`，在核心 `tianxia/core/cards.py`，第 45 批；這裡 re-export）：每一種互動寫一個 `CardAction`，用 `register` 登記，就會出現在每一張卡上——
`buttons` 決定這張卡上畫哪幾顆鈕（可以一顆都不畫），`run` 是按下去之後做的事。贈物、結伴同行、打招呼、切磋、論武都掛在這裡。
「此地還有」（`here`）與身分字（`affiliation`）在 `tianxia/core/presence.py`（核心的查詢服務，第 37 批），這裡 re-export。
引擎的門面是 `Game.peers_here`、`Game.peer_card`、`Game.peer_act`（拒絕的話與對方不在這裡都在那裡擋）。

伺服器假人跟真人一模一樣（伺服器假人設計第五節）：名單、卡、按鈕、拒絕的話一律不看 `PlayerState.bot`。
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from tianxia import four_tiers, gender, renown, team
from tianxia.characters import name_key
from tianxia.core import jieyi_base  # 名分（結義第一批）：玩家卡上的義名排行
from tianxia.core import identity_base  # 綁手機才能贈物（帳號與客服第 205 批；核心，phone_gate 預設關）
from tianxia.core import guard_base  # 親衛隊長第四批：玩家卡上那一行「親衛隊長小明（將軍）」
from tianxia.core.cards import ACTIONS, CardAction, CardButton, register  # noqa: F401  玩家卡的登記表搬進核心（第 45 批）：舊名照舊拿得到同一批物件
from tianxia.core.presence import GONE, affiliation, here, side, visible  # noqa: F401  「此地還有」的判斷與身分字搬進核心（第 37 批）：舊名照舊拿得到同一批函式物件
from tianxia.rules import day_turn
from tianxia.state import GameState

from . import invite_actions, invites, mingtie_actions, pair_actions

if TYPE_CHECKING:
    from tianxia.engine import Game
    from tianxia.models import Content

# 玩家卡動作回來時，網頁的卡已經關了或換了人（等論武取名的時候）：提示泡泡只講一句短的，完整的在江湖紀錄（FB-242；待 joy 潤）
DISCUSS_BRIEF = "論武有結果了：合出{thing}。詳見江湖紀錄。"
BRIEF_MAX = 40  # 沒有專門那一句時，泡泡寫回話的第一句，最多幾個字


def thing_label(thing) -> str:
    """合出來的那一樣寫給人看：武學【】、意境「」（意境沒有 kind 這一欄）。"""
    return f"【{thing.name}】" if hasattr(thing, "kind") else f"「{thing.name}」"


def brief(msgs: list[str] | None) -> str:
    """一串回話的第一句（第一則的第一行、到第一個句號或驚嘆號為止），太長截到 BRIEF_MAX 字加「……」：提示泡泡用（FB-242）。"""
    first = (msgs or [""])[0].strip().split("\n")[0]
    for mark in ("。", "！"):
        if mark in first:
            first = first[: first.index(mark) + 1]
    return first if len(first) <= BRIEF_MAX else first[:BRIEF_MAX] + "……"


# 玩家卡的動作登記表（CardButton、CardAction、ACTIONS、register）搬進核心 tianxia/core/cards.py（全部拆包第 45 批）：上面 import 回來，同一批物件
def arts(other: Game) -> list[dict]:
    """身上兩門（內功、武學）：名字（改過名的照改過的寫）與他自己那一份的品質。沒有的那一欄不寫。"""
    s, c = other.state, other.content
    rows = []
    for kind, skill_id in (("內功", s.player.member.neigong_id), ("武學", s.player.member.wugong_id)):
        art = team.resolve_art(skill_id, c, other.world)
        if art is not None:
            rows.append({"kind": kind, "name": art.name, "quality": team.art_quality(s, art)})
    return rows


def card(game: Game, other: Game) -> dict:
    """玩家卡（第一層）：給網頁畫的資料。動作鈕照登記表的順序，每一種互動自己決定畫不畫。"""
    o = other.state
    buttons = [
        b.view()
        for action in sorted(ACTIONS.values(), key=lambda a: (a.order, a.id))
        for b in action.buttons(game, other)
    ]
    return {
        "name": o.player.name,
        "affiliation": affiliation(o, other.content),
        "level": o.player.member.level,
        # 這一季的決戰戰績（Joy 2026-10-10 個人戰功）：沒打過是空字串
        "record": f"參戰 {o.player.showdowns} 場・首功 {o.player.top_merits} 次" if o.player.showdowns else "",
        "renown": renown.card(o, other.content),  # 名聲 3B：只寫稱號（名聲關著是 None）
        "yuedan": game._yuedan_line(other.content, o.player.name),  # 月旦評（大勢人物擴充第三批）：這一週許劭對他的那一句
        "arts": arts(other),
        "mingtie": mingtie_actions.face(game, other.state),  # 他的名帖（看不到的那一張只剩頭銜；還沒做是 None）
        "actions": buttons,
        # 稱號與官職（features/titles）開著：他此刻戴的那一個（{"id","name","grade"}，沒戴是 {}）；關著沒有這個鍵
        **({"title": dict(o.player.titles_worn)} if other.content.config.titles.enabled else {}),
        # 名分（結義第一批）：他的義名與排行（「潁川三義・行二」）；沒結義、開關關著沒有這個鍵
        **({"jieyi": tag} if (tag := jieyi_base.card_tag(game.content, game.world, o.player.name)) else {}),
        # 親衛隊長第四批（Joy 2026-11-10「全部做完一起上」；設計稿第六節）：「親衛隊長小明（將軍）」；沒投效、開關關著沒有這個鍵
        **({"guard": line} if (line := guard_base.card_line(o, other.content)) else {}),
    }



# ── 第二層：贈物、挑釁、名帖（企劃者 2026-10-08「互動的兩層也可以派下去做了」；Joy 2026-10-19 整理）────────────
# Joy 2026-10-19「玩家互動把那些沒什麼意義或是會被拿來當 bug 刷的拿掉或是優化」：拿掉互贈銀兩、結伴同行、請教（Joy 定），
# 贈回體丹與敬酒（PM 建議，Joy「照建議」）；抱拳換成互贈名帖（mingtie_card.py），挑釁可以附一句話（speech 擋髒話）。
# 挑釁與名帖是邀請（invites.py，跟切磋同一套：存在這一季的 WorldState.invites，invite_ttl_seconds 沒回就作廢——對方下線、
# 假人沒理都是這樣）。收到的列在閒著的選單上（invite:<回應>:<編號>，invite_actions.options），場景底下也畫一份（calls），
# 回應走 choose（Game._invite → answer_invite）。回應是固定的；挑釁附的那一句只有發的人寫（假人不寫自由文字，真人也多半不寫）。
# 結伴同行的引擎（移動包 party.join、lead，tagalong）還在，只是卡上沒有入口了：拿掉之前答應的那一趟照舊走完。


@dataclass(frozen=True)
class Gesture:
    """一種禮節。did 是送的人那一句（「你向{who}…」），got 是收的人看到的（「{who}…」），replies 是收的人能回的（id, 動作）：
    回了之後送的人看到「{回的人}{動作}。」，回的人自己的紀錄寫「你{動作}。」。文字待內容方改。"""

    label: str
    did: str
    got: str
    replies: tuple[tuple[str, str], ...]


GESTURES: dict[str, Gesture] = {
    "taunt": Gesture("挑釁", "斜眼打量，出言挑釁", "斜眼打量你，出言挑釁", (("cold", "冷眼以對"), ("retort", "出言回敬"))),
    # 拿掉的三種（Joy 2026-10-19）：卡上不再畫，只留著讓拿掉那一刻還沒回的那幾張回得了
    "bow": Gesture("抱拳", "抱拳見禮", "向你抱拳見禮", (("bow", "抱拳還禮"), ("nod", "點頭致意"))),
    "ask": Gesture("請教", "拱手請教武學上的疑難", "拱手向你請教武學上的疑難", (("teach", "指點了一二"), ("demur", "謙辭不敢當"))),
    "toast": Gesture("敬酒", "舉杯敬酒", "舉杯向你敬酒", (("drink", "舉杯回敬"), ("decline", "婉言推辭了"))),
}
CARD_GESTURES = ("taunt",)  # 卡上畫的禮節
GIFT_KINDS = ("material",)  # 贈物只剩素材（Joy 2026-10-19）
GIFT_TIER4 = "（四階的料不能送人。）"  # 待 joy 潤：素材四階（正式季整合 4.6）；gift_max_tier 最多 3，四階本來就不在清單上，這一句擋硬送的


def gesture_of(invite) -> Gesture | None:
    return GESTURES.get(invite.payload.get("gesture", "")) if invite.kind == "greet" else None


def taunt_line(invite, viewer: GameState | None) -> str:
    """挑釁附的那一句：收的人不再接他的挑釁話（taunt_muted）時是空的。"""
    line = str(invite.payload.get("line", "")) if invite.kind == "greet" else ""
    if not line or (viewer is not None and name_key(invite.sender) in viewer.player.taunt_muted):
        return ""
    return line


def invite_text(invite, viewer: GameState | None = None) -> str:
    """場景底下那一行：別人遞給你的是什麼。"""
    gesture = gesture_of(invite)
    if gesture is not None:
        line = taunt_line(invite, viewer)
        return f"{invite.sender}{gesture.got}：「{line}」" if line else f"{invite.sender}{gesture.got}。"
    if invite.kind == "travel":
        return f"{invite.sender}邀你結伴同行（答應了由對方定去哪、怎麼走）。"
    if invite.kind == "mingtie":
        return f"{invite.sender}遞上一張名帖，等你回帖。"
    return f"{invite.sender}邀你{invites.kind_name(invite.kind)}。"


def _short(option) -> str:
    """場景底下的回應鈕只寫動作：答應、婉拒、回禮的那幾個字（選單上的全名寫是誰的哪一種）。"""
    verb = option.id.split(":")[1]
    return {"yes": "答應", "no": "婉拒"}.get(verb) or option.label.split("：")[-1]


PICK_TO_ANSWER = "挑一樣答應"  # 場景底下論武那一列的答應鈕（FB-117；待 joy 潤）


def _call_option(option, inv) -> dict:
    """場景底下的一顆回應鈕。論武的答應要挑自己出哪一樣（在他的玩家卡上挑，discuss.buttons）：選單上那一顆引擎不收（灰的），
    以前場景這裡也畫成一顆沒說為什麼的灰鈕「答應」（FB-117）。現在帶 peer（他的名號）：網頁畫成按得下去的「挑一樣答應」，
    按了打開他的玩家卡、捲到答應那一格（純網頁動作，不送伺服器）。名帖的回帖寫「回帖」。"""
    if inv.kind == "discuss" and option.id.startswith("invite:yes:"):
        return {"id": option.id, "label": PICK_TO_ANSWER, "enabled": True, "peer": inv.sender}
    if inv.kind == "mingtie" and option.id.startswith("invite:yes:"):
        return {"id": option.id, "label": "回帖", "enabled": option.enabled}
    return {"id": option.id, "label": _short(option), "enabled": option.enabled}


def calls(game: Game) -> list[dict]:
    """場景底下「別人遞給你、還沒回的」：[{text, options: [{id, label, enabled, peer?}]}]，舊的在前。回應鈕就是選單上的那幾個選項
    （invite_actions.options，invite:<回應>:<編號>），所以只在選單上真的有時才畫（閒著、人在發邀請的那個地點）；
    論武的答應那一顆帶 peer，網頁打開他的玩家卡（_call_option）。"""
    menu = {o.id: o for o in game.options(odds=False, tick=False) if o.id.startswith("invite:")}
    rows = []
    for inv in invites.incoming(game.state.world, game.state.player.name):
        opts = [menu[i] for i in menu if i.endswith(f":{inv.id}") and not i.startswith("invite:cancel:")]
        if opts:
            rows.append({"text": invite_text(inv, game.state), "options": [_call_option(o, inv) for o in opts]})
    return rows


# ── 卡上的鈕 ──


# 同一對人每個遊戲日的上限滿了（FB-116 的切磋、贈物、論武三本帳）：照遊戲日換日（rules.game_day，跟著季長縮），所以不寫「今天／改天」，
# 寫換日的那一刻（FB-117，同談滿了的求見 Game._talked_out_note、day-scale）。（開頭, 再做什麼）；待 joy 潤
PAIR_FULL = {
    "gift": ("你們已經互贈過 {n} 回了", "送"),
    "discuss": ("你們已經論武過 {n} 回了", "論武"),
    "spar": ("你們已經切磋過 {n} 場了", "切磋"),
}
GIFT_DAY_FULL = "今天已送了 {n} 次，明日 00:00 後再送。"  # 一個人一天總共送幾次（Config.gift_per_day）；待 joy 潤


def pair_cap(content: Content, kind: str) -> int:
    """這一本帳一個遊戲日的上限（Config.gift_per_pair_day、discuss_per_pair_day、spar.per_pair_day）。"""
    cfg = content.config
    return {"gift": cfg.gift_per_pair_day, "discuss": cfg.discuss_per_pair_day, "spar": cfg.spar.per_pair_day}[kind]


def pair_full(game: Game, kind: str) -> str:
    """這一對人這個遊戲日的 kind（gift／discuss／spar）用滿了的那一句：寫下一次換日的那一刻（rules.day_turn：
    寫得出那一刻寫「…之後再X」；季末延長、季曆寫不出來寫「過一陣子再X」；這一季不會再換日寫「這一季之內不能再X了」）。"""
    head, verb = PAIR_FULL[kind]
    turn, moment = day_turn(game.content, game.state.world)
    when = f"{moment} 之後再{verb}" if moment else f"過一陣子再{verb}" if turn == "later" else f"這一季之內不能再{verb}了"
    return f"{head.format(n=pair_cap(game.content, kind))}，{when}。"


def giftable(game: Game) -> list[tuple[str, int]]:
    """送得出去的素材（Config.gift_max_tier 階以下、身上有的）：(素材 id, 幾個)。"""
    p, c = game.state.player, game.content
    top = c.config.gift_max_tier
    return [(m, n) for m, n in sorted(p.materials.items()) if n > 0 and m in c.materials and c.materials[m].tier <= top]


def _gift_buttons(game: Game, other: Game) -> list[CardButton]:
    held = giftable(game)
    if not held:
        return []
    button = CardButton(
        action="gift", label="贈素材", arg="material", amount=max(n for _, n in held),
        choices=[{"id": m, "label": game.content.materials[m].name, "max": n} for m, n in held],
    )
    full = (identity_base.PHONE_NEEDED if not identity_base.phone_ok(game, "gift")
            else (identity_base.hold_reason(game, "gift") or gift_refusal(game, other)))  # 扣押期（第 208 批）只問送的人
    return [replace(button, enabled=False, note=full) if full else button]


def gift_refusal(game: Game, other: Game) -> str | None:
    """這一下送不送得出去（數量以外）：這一對人這個遊戲日送滿了、你今天總共送滿了。"""
    if pair_actions.gifts_left(game, other.state.player.name) <= 0:
        return pair_full(game, "gift")
    if pair_actions.gift_day_left(game) <= 0:
        return GIFT_DAY_FULL.format(n=game.content.config.gift_per_day)
    return None


def _gift(game: Game, other: Game, params: dict) -> list[str]:
    """贈素材：不必對方同意，給了就是他的；兩邊的江湖紀錄各記一則，連著送同一個人併進同一則（FB-116）。數量照自己身上有的驗；
    只送得出 gift_max_tier 階以下的；同一對人每個遊戲日最多 Config.gift_per_pair_day 次（不分誰送誰，帳在 WorldState.gift_tally），
    一個人一天總共最多 Config.gift_per_day 次（PlayerState.gift_day／gifts_today）。"""
    if not identity_base.phone_ok(game, "gift"):  # 只問送的人（第 205 批）
        return [identity_base.PHONE_NEEDED]
    held = identity_base.hold_reason(game, "gift")  # 扣押期（第 208 批）：只問送的人
    if held:
        return [held]
    from tianxia import materials

    p, them, c = game.state.player, other.state.player, game.content
    full = gift_refusal(game, other)
    if full:
        return [full]
    try:
        amount = int(params.get("amount") or 0)
    except (TypeError, ValueError):
        amount = 0
    if params.get("arg") not in GIFT_KINDS or amount <= 0:
        return ["（要送多少？）"]
    material = str(params.get("choice") or "")
    if four_tiers.tier4_id(c, material):
        return [GIFT_TIER4]
    if material not in dict(giftable(game)):
        return ["（這一樣送不出去。）"]
    if not materials.take(game.state, material, amount):
        return ["（身上沒有那麼多。）"]
    materials.grant(other.state, c, material, amount)
    thing = materials.item_text(c, material, amount)
    game._pair_tick(game.state.world.gift_tally, them.name)
    pair_actions.gift_day_tick(game)
    game._save_season()
    game._write(f"贈物・{them.name}", [f"你把{thing}送給了{them.name}。"], merge=True)
    other._write(f"收禮・{p.name}", [f"{p.name}送了你{thing}。"], merge=True)
    return [f"你把{thing}送給了{them.name}。"]


def _waiting(game: Game, other: Game, kind: str):
    return invites.between(game.state.world, game.state.player.name, other.state.player.name, kind)


def _send(game: Game, other: Game, kind: str, payload: dict | None = None) -> None:
    s = game.state
    invites.expire(s.world)
    invites.send(s.world, game.content, kind, s.player.name, other.state.player.name, s.player.location, payload)
    game._save_season()


def _incoming(game: Game, inv) -> bool:
    """這一張是他發給你的（不是你發給他的）。"""
    return inv is not None and name_key(inv.target) == name_key(game.state.player.name)


def _answer(game: Game, other: Game, kind: str, verb: str) -> list[str]:
    """卡上回應他遞來的挑釁、名帖（FB-117）：跟場景底下那一顆同一個結果、同一則紀錄（Game.answer_on_card）。"""
    inv = _waiting(game, other, kind)
    if not _incoming(game, inv):
        return ["這份邀請已經不在了。"]
    return invite_actions.answer_on_card(game, inv, other, verb)


GREET_BACK = "{him}在等你回應"  # 他向你挑釁：卡上回應那幾顆的說明（FB-117；待 joy 潤）
MUTE_LABEL, UNMUTE_LABEL = "不再接{him}的挑釁話", "再接{him}的挑釁話"  # 待 joy 潤
MUTED = "之後{him}挑釁你，那一句你不會看到。"
UNMUTED = "之後{him}挑釁你附的那一句，你又看得到了。"


def _greet_buttons(game: Game, other: Game) -> list[CardButton]:
    him = gender.pronoun(other.state)
    muted = name_key(other.state.player.name) in game.state.player.taunt_muted
    mute = CardButton(action="greet", label=(UNMUTE_LABEL if muted else MUTE_LABEL).format(him=him), arg="unmute" if muted else "mute")
    inv = _waiting(game, other, "greet")
    gesture = gesture_of(inv) if _incoming(game, inv) else None
    if gesture is not None:  # 他向你挑釁：卡上換成回應的那幾顆（同場景底下），第一顆寫他在等你回應
        return [
            CardButton(action="greet", label=did, arg=f"reply:{reply}", note=GREET_BACK.format(him=him) if i == 0 else "")
            for i, (reply, did) in enumerate(gesture.replies)
        ] + [mute]
    waiting = inv is not None
    limit = game.content.config.mingtie.taunt_max
    buttons = [
        CardButton(action="greet", label=GESTURES[key].label, arg=key, enabled=not waiting,
                   note="等回應" if waiting else f"可以附一句話（{limit} 字內）", text=0 if waiting else limit)
        for key in CARD_GESTURES
    ]
    return buttons + ([mute] if muted else [])


def _greet_screen(game: Game, other: Game, params: dict) -> tuple[str, str] | None:
    from tianxia import speech

    text = speech.clean(params.get("text", ""))
    if params.get("arg") != "taunt" or not text:
        return None
    return text, speech.TAUNT


def _greet(game: Game, other: Game, params: dict) -> list[str]:
    from tianxia import speech

    key = str(params.get("arg") or "")
    him = gender.pronoun(other.state)
    if key.startswith("reply:"):
        return _answer(game, other, "greet", key.removeprefix("reply:"))
    if key in ("mute", "unmute"):
        muted, them = game.state.player.taunt_muted, name_key(other.state.player.name)
        if key == "mute" and them not in muted:
            muted.append(them)
        elif key == "unmute" and them in muted:
            muted.remove(them)
        return [(MUTED if key == "mute" else UNMUTED).format(him=him)]
    if key not in CARD_GESTURES:
        return ["（沒有這種禮數。）"]
    gesture = GESTURES[key]
    if _waiting(game, other, "greet") is not None:
        return [f"（{other.state.player.name}還沒回應。）"]
    line = speech.clean(params.get("text", ""))
    problem = speech.problem(line, game.content, speech.TAUNT, game.content.config.mingtie.taunt_max, str(params.get("verdict", "")))
    if problem:
        return [problem]
    _send(game, other, "greet", {"gesture": key, **({"line": line} if line else {})})
    said = f"：「{line}」" if line else "。"
    return [f"你向{other.state.player.name}{gesture.did}{said}"]


register(CardAction(id="greet", buttons=_greet_buttons, run=_greet, order=10, screen=_greet_screen))
register(CardAction(id="gift", buttons=_gift_buttons, run=_gift, order=20))
