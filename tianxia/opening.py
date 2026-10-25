"""開局第一分鐘（減法季整合設計 6.7【定：方向】，批 7 前半；content/opening.json）。

減法季的新角色不進草廬：站在起點（潁川）看一段旁白、三選一定起手的屬性（事件 Opening.event 的三顆選項，各加兩點、各帶一個旗標），
選了之後照旗標由一位人物開口——做成他派人送來的一封信（Letter，kind「託付」）附一件護送委託（把信送到 Opening.end，到了就算；
bounties.on_arrive → _complete_commission：銀兩與他的情誼照 Config.figure_life 的委託數字），信先寫固定句、伺服器鎖外請模型照他的口氣
重寫（letters.write，寫不出來照固定句）。三方卡本來就在江湖頁最上面；信收起來本週卡才出現，「你這一步」第一件就是這一封信
（weekcard._steps 的 errand）。新手八步（newbie.GOALS）照舊只在本週卡與「為什麼」裡。草廬序章（prologue.py）與老周的初入江湖
（tutorial.json 的 e 步）一律略過。丹的福利照舊寫在江湖紀錄開場那一則（Game._note_gift），不另起一張卡。

開關：Config.jianfa.opening 加上這一季開季時蓋的章（rules.jianfa(content, world, "opening")）；關著、或內容沒有 opening.json，
新角色照舊走草廬。假人（Game.new(graduated=True)）走同一條：一樣站在城門口挑一顆、收到信（看不出誰是假人）；腳本與測試不帶任何
旗標建的角色照舊直接站在起點、什麼都不端出。只有 engine、weekcard、content 與測試 import 它。"""
from __future__ import annotations

from . import bounties, calendar, gender, prologue, rules
from .calendar import DAY
from .models import Content, OpeningSender
from .state import Bounty, GameState, Letter

KIND = "託付"  # 開局那一封信的種類（Letter.kind；信卡左上的小籤）
GATE = "先聽完城門口這一段、挑了路，再領今天的份。"  # 三選一還沒選就按簽到（同草廬的 checkin.HUT）


def on(content: Content, world) -> bool:
    """這一季的新角色走不走開局第一分鐘：內容有 opening.json，而且減法季的 opening 子開關在這一季開著。"""
    return content.opening is not None and rules.jianfa(content, world, "opening")


def begin(state: GameState, content: Content) -> None:
    """把新角色放到起點、端出開局那一則事件；草廬與初入江湖的步驟全部略過（不是走完、是跳過：沒有出師的盤纏，體力滿的）。"""
    o, p, t = content.opening, state.player, content.tutorial
    if o is None:
        return
    p.location = content.scenario.start_location
    p.journey = None
    p.visited.add(p.location)
    if t.location is not None and p.tutorial_step < t.prologue_steps:
        p.tutorial_step = t.prologue_steps
    prologue.skip_onboarding(state, content)
    p.stamina = float(content.config.stamina_max)
    state.pending_event = o.event


def pending(state: GameState, content: Content) -> bool:
    """還停在開局那一則事件上（三選一還沒選）：本週卡、三方卡先不畫。"""
    return content.opening is not None and state.pending_event == content.opening.event


def sender(state: GameState, content: Content) -> OpeningSender | None:
    """選了哪一顆：照身上的旗標找對到的那位人物；還沒選、或旗標對不上是 None。"""
    if content.opening is None:
        return None
    return next((x for x in content.opening.senders if x.flag in state.player.flags), None)


def letter_of(state: GameState, content: Content) -> Letter | None:
    return next((x for x in state.player.letters if x.kind == KIND), None)


def deliver(state: GameState, content: Content) -> list[str]:
    """三選一選完那一下（Game.choose）：那位人物的信到了、附一件把信送到 Opening.end 的護送委託。已經有這一封就不再送。
    回傳江湖紀錄的那一句（寫在這一下的紀錄裡）。"""
    o, p, w = content.opening, state.player, state.world
    who = sender(state, content)
    if o is None or who is None or letter_of(state, content) is not None:
        return []
    tuning = content.config.figure_life
    p.letter_seq += 1
    task = Bounty(
        id=f"c{p.letter_seq}", kind="escort", faction=None, week=calendar.point(w.time, content, w).week,
        expires=w.time + o.days * DAY, silver=tuning.commission_silver, deeds=0,
        figure=who.figure, motive="委託", location=p.location, end=o.end,
    )
    end = content.locations[o.end].name
    text = who.text.format(hero=gender.hero(p), end=end)
    p.letters.append(Letter(id=p.letter_seq, kind=KIND, sender=who.figure, at=w.time, text=text, task=task))
    return [o.arrived.format(who=bounties.issuer(content, task), end=end)]


def errand_live(state: GameState, content: Content) -> bool:
    """開局那一封信的委託還在身上（還沒送到、沒過期、沒婉拒）。"""
    letter = letter_of(state, content)
    t = letter.task if letter is not None else None
    return t is not None and not letter.lapsed and not t.done_by and t.expires > state.world.time
