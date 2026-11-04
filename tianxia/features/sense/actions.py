"""有所感包的動作（全部拆包第 24 批：原本 Game 上的 10 個方法，計畫 docs/superpowers/plans/2026-11-01-有所感包-第1批.md 1.1）。
Game 留 8 個一行委派（server、假人、測試、核心原位與探索包在叫的）；sense、sense_apply 只有這一包在叫。第一個參數 ctx 是 Game（手冊 3.3）；
叫回 Game 的只用 tianxia/core/services.py 那張清單上的；這一包互相叫直接叫函式。sense_draw、epiphany_names 掛核心的 outing_watch
（走一趟停在要選的事上時記那一下的得失；原本是 engine 模組層的 _outing_watch）。
最後兩段是 choose、scene 掛鉤的本體，與核心原位、探索包、引導包叫的服務的本體（Game._sense_missed……）。"""
from __future__ import annotations

import random
from collections.abc import Iterable
from typing import TYPE_CHECKING

from tianxia import insights, journal  # 共用規則層、核心
from tianxia import prologue as prologue_rules  # 共用規則層（序章草廬：必中）
from tianxia import story_base  # 共用規則層（一條線的底座：頓悟那一條開了之後的開場與第一題）
from tianxia.core.option import Option
from tianxia.core.services import PREPARING_REFUSAL, outing_watch
from tianxia.journal import Draft
from tianxia.models import Location
from tianxia.rules import add_marks

from . import epiphany, sensing

if TYPE_CHECKING:
    from tianxia.engine import Game

CANVAS = "（在畫布上一筆畫下心中的形。）"  # 「畫下來」只叫出畫布那一句（原本寫在 Game.choose）


# ── 有所感（悟意境設計第零節）────────────────────────────────


def sense(ctx: Game, arg: str) -> list[str]:
    """有所感選單上的選擇：做法（數字）或「順其自然」（不畫了，落回做法那個基本意境）。「畫下來」在 choose 開頭就回了（sense_canvas）。"""
    s, c = ctx.state, ctx.content
    if arg == "let":
        req = sensing.request(s, c, ctx.world, None)
        return [req] if isinstance(req, str) else sense_apply(ctx, req, None)
    got = sensing.current(s, c)
    prologue = got is not None and got[1].prologue
    rng = prologue_rules.SureRandom() if prologue else ctx.rng  # 序章草廬：必中（悟意境設計第七節）
    if not arg.isdecimal():
        return ["（此刻無法這麼做。）"]
    msgs = sensing.choose(s, c, int(arg), rng)
    sense_ = s.player.sensing
    if not prologue and sense_ is not None and sense_.stage == "draw" and epiphany.roll(s, c, ctx.rng, boost=ctx._rare_boost()):  # 特殊頓悟：不畫那一筆，開一條頓悟的線
        msgs += epiphany_begin(ctx, sense_.method or "", c.locations[sense_.location].name)
    return msgs


def sense_title(ctx: Game) -> str:
    """sense:* 那一下江湖紀錄的標題（choose 掛鉤的 Outcome.title；原本 Game._action_title 的 sense 那一支）：「有所感・場景」。"""
    s, c = ctx.state, ctx.content
    scene = c.insight_scenes.get(s.player.sensing.scene) if s.player.sensing else None
    return f"有所感・{scene.title}" if scene else "有所感"


def epiphany_begin(ctx: Game, method: str, place: str) -> list[str]:
    """特殊頓悟中了（epiphany.roll）：收掉那一份感悟、開線、直接端出第一題（心靈拷問）；江湖紀錄另起一則「頓悟」。"""
    s, c = ctx.state, ctx.content
    progress = epiphany.begin(s, c, method, place)
    if progress is None:
        return []
    s.player.sensing = None
    line = story_base.definition(c, progress)
    ctx._outcome(journal.event_marker(epiphany.TITLE, True), f"✦ {epiphany.TITLE}")
    return [f"✦ {epiphany.TITLE}", line.intro, f"【{line.title}】"] + story_base.open_quiz(s, c, progress)


def epiphany_name(ctx: Game, arg: str, text: str | None) -> list[str]:
    """特殊頓悟心魔過了之後取名（epiphany.choose）：挑三個候選之一，或自己寫（dunwu:own，名字在 text）。"""
    return epiphany.choose(ctx.state, ctx.content, ctx.world, arg, text)


def epiphany_request(ctx: Game) -> epiphany.NameAsk | None:
    """特殊頓悟取名的 A 段（行動鎖內、只讀）：按「靜心思名」時開請模型取三個名字的單（server.epiphany_think、假人程式）。
    不在等著取名、已經想過了、賽季籌備中是 None。"""
    if ctx._preparing():
        return None
    return epiphany.name_request(ctx.state, ctx.content)


@outing_watch
def epiphany_names(ctx: Game, ask: epiphany.NameAsk, names: list[str]) -> list[str]:
    """C 段（鎖內）：鎖外拿到的名字交回來，重驗、不夠三個用字表補（epiphany.fill）；單子對不上（已經想過、換了一條線）什麼都不做。"""
    msgs = epiphany.fill(ctx.state, ctx.content, ctx.world, ask, names)
    return ctx._log(msgs) if msgs else msgs


def sense_request(ctx: Game, points: list | None, png: str = "") -> sensing.SenseRequest | str:
    """畫完那一筆的 A 段（server.py 在行動鎖內、很快地呼叫）：還在感悟狀態才開單；讀不出那一筆回一句話（字串）。
    只讀、不改狀態。單子的 needs_name 是 True 才要在鎖外叫模型看圖取名（insight_llm.name）。"""
    if ctx._preparing():
        return PREPARING_REFUSAL
    return sensing.request(ctx.state, ctx.content, ctx.world, points, png)


@outing_watch
def sense_draw(ctx: Game, req: sensing.SenseRequest, proposed: tuple[str | None, str] | None = None) -> list[str]:
    """畫完那一筆的 C 段（鎖內）：重驗還是同一次感悟、同一筆讀出同一個屬性才套用（sensing.finish）。proposed 是鎖外取好的
    （名字, 說明）；沒給（整季機器人、腳本、測試）而且要取名，就在這裡用 _quick_client 只看文字特徵問一次，取不到走退路字表。
    悟成才寫江湖紀錄（標題「有所感・場景」，附上畫的那一筆）；對不上只回一句話。"""
    s, c = ctx.state, ctx.content
    got = sensing.current(s, c)
    if got is None or got[0].stage != "draw" or got[0].serial != req.serial:
        return ctx._log([sensing.STALE])
    ctx.state.battle_card = None
    ctx.state.player.guide_done = []
    ctx._draft = Draft(f"有所感・{got[1].title}")
    ctx._draft.glyph = list(req.points)
    try:
        msgs = sense_apply(ctx, req, proposed)
        ctx._check_hints()  # 畫完悟到意境（可能是第二個）：看一遍、排著的提示上框，記在這一則（新手引導計畫三；這條路不走 choose）
        journal.add_entry(s, ctx._draft.entry(s.world.time, msgs))
    finally:
        ctx._draft = None
    ctx._save_season()
    return ctx._log(msgs)


def sense_apply(ctx: Game, req: sensing.SenseRequest, proposed: tuple[str | None, str] | None) -> list[str]:
    """畫完（或順其自然）之後真的悟：sensing.finish 改狀態；悟成就在這一處留一筆痕跡（一人一個遊戲日只算一次）、序章那一段加旗標、
    記新手引導；悟到自己的新意境而且名字是模型取的，記全服的首悟紀錄（0.2b 第 5 點：第一個在這裡這樣悟到的人）。
    名字走退路字表的不記：伺服器假人不叫模型，記了就會露出「首悟者的名字都是字表風格」（同 2026-10-05 合成首創的決定）。"""
    s, c = ctx.state, ctx.content
    got = sensing.current(s, c)
    scene = got[1] if got is not None else None
    client = ctx._quick_client() if proposed is None else None
    msgs, own, by_model = sensing.finish(s, c, ctx.world, req, proposed, client)
    if msgs == [sensing.STALE]:
        return msgs
    add_marks({sensing.mark_key(req.location): 1}, s, c)
    if scene is not None and scene.flags_add:
        s.player.flags.update(scene.flags_add)
    if own is not None and by_model and ctx.world.claim_insight_first(
        sensing.first_key(req), own.name, s.player.name, c.locations[req.location].name, s.world.time,
    ):
        msgs.append(f"江湖上還沒有人在{c.locations[req.location].name}這樣悟過——你是第一個。")
    msgs += ctx._guide(ctx._note_action("sense"))
    return msgs


def sense_here(ctx: Game, loc: Location, rng: random.Random) -> list[str]:
    """靜心感悟（設計 3.3）：就是有所感（sensing.start）；沒有場景的內容照舊直接悟（同舊探索的悟意境那一支）。"""
    s, c = ctx.state, ctx.content
    if sensing.can_sense(s, c, loc):
        return sensing.start(s, c, sensing.pick_scene(loc, c, rng), rng)
    found = insights.roll_explore(loc, c, rng)
    return [f"你在{loc.name}靜下心來，看了好一陣。"] + insights.learn(s, c, ctx.world, found, at=loc)


def method_help(ctx: Game, option_ids: Iterable[str]) -> dict | None:
    """有所感選做法那一步，網頁畫在做法鈕底下的兩行小字（explain-2，sensing.method_help；鈕上的心意審查 I1 起預設不給）；
    選單上沒有做法（不在選做法、戰場蓋過了畫面）是 None。不讀這一處悟得到什麼：哪一個做法是對的看不出來。"""
    got = sensing.method_help(ctx.state, ctx.content)
    if got is None or not any(sensing.is_method(i) for i in option_ids):
        return None
    return got


# ── 接縫掛鉤的本體（scene：原本 Game._own_scene_text 宴客那一行之後的兩支）──


def scene(ctx: Game) -> str | None:
    """自己眼前的場景卡：有所感的卡（標題、場景、選錯的代價；感悟狀態叫人畫下來），沒有卡（作廢的也算）而且心魔過了等著取名是
    取名那一張；都不是是 None（核心接著往下問一條線的答題……）。"""
    s, c = ctx.state, ctx.content
    sense_card = sensing.scene_text(s, c) if s.player.sensing is not None else ""
    if sense_card:
        return sense_card
    if s.player.god_naming is not None:  # 特殊頓悟心魔過了：取名（同選單的順序）
        return epiphany.scene_text(s, c)
    return None


# ── 核心原位、探索包、引導包叫的服務（Game 上一行的委派；計畫 1.4）──


def sense_missed(ctx: Game, loc: Location) -> bool:
    """這個遊戲日在這一處選錯過做法（sensing.missed_today）：探索包算這一處感悟的比重、三選一的灰鈕、舊探索那一行與比重。"""
    return sensing.missed_today(ctx.state, ctx.content, loc)


def sense_drop_stale(ctx: Game) -> None:
    """清失效參照（Game._drop_stale_references 中段，收店之前）：作廢的感悟拿掉。"""
    sensing.drop_stale(ctx.state, ctx.content)


def sense_menu(ctx: Game) -> list[Option] | None:
    """選單（Game._everyday_options 擂台之後、一條線的答題之前）：有所感的卡上的做法，或感悟狀態的「畫下來／順其自然」（作廢的卡
    沒有選項就往下）；特殊頓悟心魔過了先取名（三個候選＋自己寫），取了才收進意境。都不是是 None。"""
    s, c = ctx.state, ctx.content
    if s.player.sensing is not None:
        menu = sensing.menu(s, c)
        if menu:
            return [Option(id=option_id, label=label) for option_id, label in menu]
    if s.player.god_naming is not None:
        return [Option(id=option_id, label=label) for option_id, label in epiphany.menu(s)]
    return None


def sense_start(ctx: Game, scene_id: str, rng: random.Random) -> list[str]:
    """序章第 3 步的有所感版（舊探索 Game._explore_outcome）：草廬四景那一張卡。"""
    return sensing.start(ctx.state, ctx.content, ctx.content.insight_scenes[scene_id], rng)


def sense_canvas(ctx: Game, option_id: str) -> list[str] | None:
    """「畫下來」（sensing.DRAW）只叫出畫布、不寫紀錄（Game.choose 建紀錄之前那一格）；別的選項是 None。"""
    return [CANVAS] if option_id == sensing.DRAW else None


def epiphany_title(ctx: Game) -> str:
    """dunwu:* 那一下江湖紀錄的標題（Game._action_title；取名留在 choose 原位，choose 掛鉤不帶 text）。"""
    return epiphany.TITLE


def prologue_choice(ctx: Game) -> str:
    """序章草廬的有所感這一下按哪一顆（引導包的假人走序章）：還沒選做法挑一個（做法都對，照 ctx.rng）、進了感悟狀態順其自然。"""
    s, c = ctx.state, ctx.content
    if s.player.sensing.stage == "choose":
        return f"{sensing.PREFIX}{ctx.rng.randrange(len(sensing.current(s, c)[1].methods))}"
    return sensing.LET_GO
