"""玩家之間的互動（企劃者 2026-10-08「假設 A 玩家在長社，B 玩家也過去的話，兩人可以做什麼互動」）。

第一層：看得到彼此。場景底下列「此地還有誰」（`here`），點名字打開一張玩家卡（`card`）：名號、門派・陣營・頭銜、等級、
身上兩門武學（只寫名字與品質），以及卡上的動作鈕。

卡上的動作是一張登記表（`ACTIONS`）：每一種互動寫一個 `CardAction`，用 `register` 登記，就會出現在每一張卡上——
`buttons` 決定這張卡上畫哪幾顆鈕（可以一顆都不畫），`run` 是按下去之後做的事。贈物、結伴同行、打招呼、切磋、論武都掛在這裡。
引擎的門面是 `Game.peers_here`、`Game.peer_card`、`Game.peer_act`（拒絕的話與對方不在這裡都在那裡擋）。

伺服器假人跟真人一模一樣（伺服器假人設計第五節）：名單、卡、按鈕、拒絕的話一律不看 `PlayerState.bot`。
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from . import prologue as prologue_rules
from . import ranks, team
from .characters import CharacterStore
from .state import GameState

if TYPE_CHECKING:
    from .engine import Game
    from .models import Content

GONE = "他已經不在這裡了。"  # 對方離開了、下線太久、或根本沒有這個人：一律這一句（不讓人試出名號在不在）


@dataclass
class CardButton:
    """玩家卡上的一顆鈕。id 是送回 /api/peer/act 的 action（同一種互動可以有好幾顆，例如每一種禮節一顆，用 arg 分開）。"""

    action: str  # CardAction.id
    label: str
    arg: str = ""  # 同一種互動的哪一個（禮節、送哪一樣）；run 收到的 params["arg"]
    note: str = ""  # 鈕上的小字（花多少、為什麼按不下去）
    enabled: bool = True
    confirm: str = ""  # 按下去之前先問一次的話；空的直接送
    amount: int = 0  # >0：按下去要先填一個數量（1～amount），送 params["amount"]
    choices: list[dict] = field(default_factory=list)  # 有的話先挑一樣（[{id, label, max}]），送 params["choice"]；數量上限照那一樣的 max

    def view(self) -> dict:
        return {
            "action": self.action, "label": self.label, "arg": self.arg, "note": self.note,
            "enabled": self.enabled, "confirm": self.confirm, "amount": self.amount, "choices": self.choices,
        }


@dataclass
class CardAction:
    """卡上的一種互動。buttons(game, other) 畫鈕；run(game, other, params) 做事、回給按的人看的訊息。
    other 是對方那一份 Game（不叫模型、沒有補算時間：替別人寫東西不能讓他看起來剛剛上過線）；run 改了 other.state，
    Game.peer_act 會存回去。數值一律由這裡的規則定，params 只是玩家挑的東西，要自己驗。"""

    id: str
    buttons: Callable[[Game, Game], list[CardButton]]
    run: Callable[[Game, Game, dict], list[str]]
    order: int = 100  # 卡上由上而下的順序（小的在前）


ACTIONS: dict[str, CardAction] = {}


def register(action: CardAction) -> CardAction:
    ACTIONS[action.id] = action
    return action


def visible(state: GameState, content: Content) -> bool:
    """這個人看得到別人、也被別人看得到：不在路上（人在兩地之間）、不在草廬序章裡（序章是一個人的）。"""
    return state.player.journey is None and not prologue_rules.active(state, content)


def here(game: Game) -> list[GameState]:
    """此地還有誰：跟你同一個地點、presence_seconds 之內同步過、不在路上也不在序章裡的人，照名號排序；你自己看不到人時是空的。"""
    s, c = game.state, game.content
    if not visible(s, c) or not hasattr(game.world, "db"):
        return []
    since = game.now - c.config.presence_seconds
    return [o for o in CharacterStore(game.world.db).present(s.player.location, since, s.player.name) if visible(o, c)]


def side(state: GameState, content: Content) -> str:
    """名單上名字後面括號裡那一個：陣營，沒有陣營是「散人」。"""
    return content.scenario.faction_name(state.player.faction) or "散人"


def affiliation(state: GameState, content: Content) -> str:
    """門派・陣營・頭銜（有哪幾樣寫哪幾樣），都沒有是散人——跟狀態列同一個寫法（Game.status_data）。"""
    p = state.player
    sect = content.sects[p.sect].name if p.sect else None
    faction = content.scenario.faction_name(p.faction)
    return "・".join(name for name in (sect, faction, ranks.title(content, state)) if name) or "散人"


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
        "arts": arts(other),
        "actions": buttons,
    }



# ── 第二層：贈物、打招呼、結伴同行（企劃者 2026-10-08「互動的兩層也可以派下去做了」）────────────
# 打招呼、結伴是「遞過去、等對方回」的事（state.Overture）：收的人在場景底下看到一行、按回應的鈕（Game.answer_overture），
# 過了 Config.invite_seconds 現實秒數沒回就作罷（對方下線、假人沒理，都是這樣）。只有固定的禮節與固定的回應，沒有自由文字：
# 假人不寫自由文字（伺服器假人設計），而真人假人要一模一樣。數值一律由這裡的規則定。


@dataclass(frozen=True)
class Gesture:
    """一種禮節。did 是送的人那一句（「你向{who}…」），got 是收的人看到的（「{who}…」），replies 是收的人能回的（id, 動作）：
    回了之後送的人看到「{回的人}{動作}。」，回的人自己的紀錄寫「你{動作}。」。文字待內容方改。"""

    label: str
    did: str
    got: str
    replies: tuple[tuple[str, str], ...]


GESTURES: dict[str, Gesture] = {
    "bow": Gesture("抱拳", "抱拳見禮", "向你抱拳見禮", (("bow", "抱拳還禮"), ("nod", "點頭致意"))),
    "ask": Gesture("請教", "拱手請教武學上的疑難", "拱手向你請教武學上的疑難", (("teach", "指點了一二"), ("demur", "謙辭不敢當"))),
    "taunt": Gesture("挑釁", "斜眼打量，出言挑釁", "斜眼打量你，出言挑釁", (("cold", "冷眼以對"), ("retort", "出言回敬"))),
    "toast": Gesture("敬酒", "舉杯敬酒", "舉杯向你敬酒", (("drink", "舉杯回敬"), ("decline", "婉言推辭了"))),
}
TRAVEL_REPLIES = (("yes", "答應"), ("no", "婉拒"))
GIFT_KINDS = ("silver", "pill", "material")


def _sent_to(state: GameState, kind: str, to: str) -> bool:
    return any(o.kind == kind and o.to == to for o in state.player.sent)


def send(game: Game, other: Game, kind: str, gesture: str = "") -> str | None:
    """遞一件事過去（打招呼、結伴邀請）：兩邊各記一份。不行時回一句拒絕的話（只回給按的人）。"""
    from .state import Overture

    me, them = game.state.player, other.state.player
    if _sent_to(game.state, kind, them.name):
        return f"（還在等{them.name}回應。）"
    if len(them.inbox) >= game.content.config.inbox_cap:
        return f"（{them.name}正忙著應付別人，等一下再說。）"
    me.overture_serial += 1
    overture = Overture(
        id=f"{me.name}｜{me.overture_serial}", kind=kind, sender=me.name, to=them.name, gesture=gesture,
        at=game.now, location=me.location,
    )
    me.sent.append(overture)
    them.inbox.append(overture.model_copy())
    return None


def calls(game: Game) -> list[dict]:
    """場景底下「別人遞給你的」：[{id, text, replies: [{id, label}]}]，舊的在前。"""
    rows = []
    for o in game.state.player.inbox:
        if o.kind == "greet" and o.gesture in GESTURES:
            g = GESTURES[o.gesture]
            rows.append({"id": o.id, "text": f"{o.sender}{g.got}。", "replies": [{"id": r, "label": label} for r, label in g.replies]})
        elif o.kind == "travel":
            rows.append({
                "id": o.id, "text": f"{o.sender}邀你結伴同行（答應了由他定去哪、怎麼走）。",
                "replies": [{"id": r, "label": label} for r, label in TRAVEL_REPLIES],
            })
    return rows


# ── 卡上的鈕 ──


def _gift_buttons(game: Game, other: Game) -> list[CardButton]:
    p, c = game.state.player, game.content
    silver = p.stats.get("silver", 0)
    buttons = [CardButton(
        action="gift", label="贈銀兩", arg="silver", amount=silver, enabled=silver > 0,
        note=f"身上 {silver} 兩" if silver > 0 else "身上沒有銀兩",
    )]
    if p.stamina_pills > 0:
        buttons.append(CardButton(
            action="gift", label=f"贈{c.config.stamina_pill_name}", arg="pill", amount=p.stamina_pills,
            note=f"身上 {p.stamina_pills} 顆",
        ))
    held = [(m, n) for m, n in sorted(p.materials.items()) if n > 0 and m in c.materials]
    if held:
        buttons.append(CardButton(
            action="gift", label="贈素材", arg="material", amount=max(n for _, n in held),
            choices=[{"id": m, "label": c.materials[m].name, "max": n} for m, n in held],
        ))
    return buttons


def _gift(game: Game, other: Game, params: dict) -> list[str]:
    """贈物：不必對方同意，給了就是他的；兩邊的江湖紀錄各記一則。數量照自己身上有的驗。"""
    from . import materials

    p, them, c = game.state.player, other.state.player, game.content
    what = params.get("arg")
    try:
        amount = int(params.get("amount") or 0)
    except (TypeError, ValueError):
        amount = 0
    if what not in GIFT_KINDS or amount <= 0:
        return ["（要送多少？）"]
    if what == "silver":
        if p.stats.get("silver", 0) < amount:
            return ["（身上的銀兩不夠。）"]
        p.stats["silver"] -= amount
        them.stats["silver"] = them.stats.get("silver", 0) + amount
        thing, mine, theirs = f"銀子 {amount} 兩", [f"銀兩 -{amount}"], [f"銀兩 +{amount}"]
    elif what == "pill":
        if p.stamina_pills < amount:
            return [f"（身上的{c.config.stamina_pill_name}不夠。）"]
        p.stamina_pills -= amount
        them.stamina_pills += amount
        thing = f"{c.config.stamina_pill_name} {amount} 顆"
        mine, theirs = [], []
    else:
        material = str(params.get("choice") or "")
        if material not in c.materials or not materials.take(game.state, material, amount):
            return ["（身上沒有那麼多。）"]
        materials.grant(other.state, c, material, amount)
        thing = materials.item_text(c, material, amount)
        mine, theirs = [], []
    game._write(f"贈物・{them.name}", [f"你把{thing}送給了{them.name}。", *mine])
    other._write(f"收禮・{p.name}", [f"{p.name}送了你{thing}。", *theirs])
    return [f"你把{thing}送給了{them.name}。", *mine]


def _greet_buttons(game: Game, other: Game) -> list[CardButton]:
    waiting = _sent_to(game.state, "greet", other.state.player.name)
    return [
        CardButton(action="greet", label=g.label, arg=key, enabled=not waiting, note="等他回禮" if waiting else "")
        for key, g in GESTURES.items()
    ]


def _greet(game: Game, other: Game, params: dict) -> list[str]:
    gesture = GESTURES.get(str(params.get("arg") or ""))
    if gesture is None:
        return ["（沒有這種禮數。）"]
    refusal = send(game, other, "greet", str(params["arg"]))
    return [refusal] if refusal else [f"你向{other.state.player.name}{gesture.did}。"]


def _travel_note(game: Game, other: Game) -> str | None:
    """邀不了的原因；邀得了是 None。"""
    me, them = game.state.player, other.state.player
    if them.tagalong is not None and them.tagalong.leader == me.name:
        return "已經結伴，出發時一起走"
    if me.tagalong is not None:
        return f"你正跟著{me.tagalong.leader}同行"
    if them.tagalong is not None:
        return "他已經跟別人結伴了"
    if _sent_to(game.state, "travel", them.name):
        return "等他回應"
    return None


def _travel_buttons(game: Game, other: Game) -> list[CardButton]:
    note = _travel_note(game, other)
    return [CardButton(
        action="travel", label="邀他結伴同行", enabled=note is None, note=note or "他答應了，由你定去哪、怎麼走",
    )]


def _travel(game: Game, other: Game, params: dict) -> list[str]:
    note = _travel_note(game, other)
    if note is not None:
        return [f"（{note}。）"]
    refusal = send(game, other, "travel")
    return [refusal] if refusal else [f"你邀{other.state.player.name}結伴同行，等他回應。"]


register(CardAction(id="greet", buttons=_greet_buttons, run=_greet, order=10))
register(CardAction(id="gift", buttons=_gift_buttons, run=_gift, order=20))
register(CardAction(id="travel", buttons=_travel_buttons, run=_travel, order=30))
