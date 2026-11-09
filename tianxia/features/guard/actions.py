"""親衛隊長的動作（ctx 是 Game；只叫 tianxia/core/services_list.md 清單上的）。第一批：遇見與成長。

- options：「此地還能做」——10 級起撞見那個孩子；救了沒收的回到那裡能回頭；有一件事在等你時那一顆。
- menu：遇見那一段（救不救、收不收）與攤開的那一件事（三個做法、先擱著）接管選單。
- on_sync：每天保底的家裡的事；after_action：帶他出門、花了體力的那一下有機會冒出一件。
  模型叫得到就排給背景寫字（routes 的 OutlockJob，鎖外生）；叫不到、假人、等太久都換固定事件（rules.fixed_event）。
- 自己寫的那一句走鎖外三段式（routes.guard_say：say_request → judge_say → apply_say）。
- rename、set_along：養成冊上的改名（一次）與出門帶不帶他。
- on_season_start：跟著帳號走，換季照帶（眼前那一件收掉、天的帳歸零）。"""
from __future__ import annotations

from tianxia import naming
from tianxia import rules as core_rules
from tianxia.core.option import Option
from tianxia.state import GuardBook

from . import rules

PREFIX = "guard"


def _t(ctx):
    return rules.tuning(ctx.content)


def _today(ctx) -> int:
    return core_rules.game_day(ctx.content, ctx.state.world)


def _season(ctx) -> int:
    return int(ctx.state.player.season_number or 0)


def _home_quota(ctx) -> int:
    from tianxia import calendar  # noqa: PLC0415

    t = _t(ctx)
    return t.week7_home_per_day if calendar.week7_on(ctx.state.world, ctx.content) else t.home_per_day


def _modelless(ctx) -> bool:
    """這個人不叫模型：假人（client=None，不寫自由文字）或這台伺服器沒有模型。"""
    return ctx.state.player.bot is not None or ctx.client is None


def _place_name(ctx, loc_id: str) -> str:
    loc = ctx.content.locations.get(loc_id)
    return loc.name if loc is not None else loc_id


def _free(ctx) -> bool:
    p = ctx.state.player
    return p.journey is None and ctx._idle()


# ── 選單 ───────────────────────────────────────────────────────────────

def options(ctx) -> list[Option]:
    if not _free(ctx):
        return []
    p, b, t = ctx.state.player, rules.book(ctx.state), _t(ctx)
    if b is None:
        if p.member.level < t.meet_level:
            return []
        return [Option(id=f"{PREFIX}:meet", label=rules.pick_opening(p.name, _season(ctx))["label"])]
    if b.stage == "left" and p.location == b.place:
        return [Option(id=f"{PREFIX}:back", label=rules.BACK_LABEL)]
    if b.stage == "grow" and b.event is not None and not b.event.shown:
        return [Option(id=f"{PREFIX}:open", label=rules.fill(rules.EVENT_LABEL, b).replace("{peek}", rules.peek(b.event)))]
    return []


def menu(ctx) -> list[Option] | None:
    b = rules.book(ctx.state)
    if b is None:
        return None
    if b.stage == "met":
        o = rules.opening(b.opening)
        return [Option(id=f"{PREFIX}:save", label=o["save"]), Option(id=f"{PREFIX}:leave", label=o["leave"])]
    if b.stage == "saved":
        return [Option(id=f"{PREFIX}:adopt:男", label=rules.ADOPT_BOY), Option(id=f"{PREFIX}:adopt:女", label=rules.ADOPT_GIRL),
                Option(id=f"{PREFIX}:part", label=rules.PART_LABEL)]
    if b.stage == "grow" and b.event is not None and b.event.shown:
        return [*(Option(id=f"{PREFIX}:pick:{i}", label=c.label) for i, c in enumerate(b.event.choices)),
                Option(id=f"{PREFIX}:later", label=rules.LATER)]
    return None


def title(ctx, arg: str) -> str:
    b = rules.book(ctx.state)
    return b.name if b is not None and b.stage == "grow" and b.name else rules.TITLE


def act(ctx, arg: str) -> list[str]:
    s, t = ctx.state, _t(ctx)
    p, b = s.player, rules.book(s)
    head, _, rest = arg.partition(":")
    if head == "meet":
        if b is not None or p.member.level < t.meet_level or not _free(ctx):
            return [rules.NO_SUCH]
        o = rules.pick_opening(p.name, _season(ctx))
        p.guard = GuardBook(stage="met", opening=o["id"], place=p.location)
        return [o["text"]]
    if b is None:
        return [rules.NO_SUCH]
    if head == "save" and b.stage == "met":
        b.stage = "saved"
        return [rules.opening(b.opening)["saved"]]
    if head in ("leave", "part") and b.stage in ("met", "saved"):
        b.stage = "left"
        return [rules.LEFT_HIM if head == "leave" else rules.PARTED]
    if head == "back" and b.stage == "left" and p.location == b.place:
        b.stage = "saved"
        return [rules.BACK_TEXT.replace("{place}", _place_name(ctx, b.place))]
    if head == "adopt" and b.stage == "saved" and rest in ("男", "女"):
        b.stage, b.sex = "grow", rest
        b.name = rules.pick_name(rest, p.name)
        b.adopted_season = _season(ctx)
        b.home_day = _today(ctx)  # 收養那一天不再另生一件家裡的事
        b.home_n = _home_quota(ctx)
        rules.apply(t, b, rules.GuardChoice(label="", memo=rules.fill("你救下了{pron}，收養了{pron}。", b), qing=1), _today(ctx), ctx.stamp(s.world.time))
        return [rules.fill(rules.ADOPTED, b)]
    if b.stage != "grow" or b.event is None:
        return [rules.NO_SUCH]
    if head == "open":
        b.event.shown = True
        return [b.event.text]
    if head == "later":
        b.event.shown = False
        return [rules.fill(rules.LATER_TEXT, b)]
    if head == "pick" and rest.isdigit() and int(rest) < len(b.event.choices) and b.event.shown:
        return rules.apply(t, b, b.event.choices[int(rest)], _today(ctx), ctx.stamp(s.world.time))
    return [rules.NO_SUCH]


# ── 什麼時候冒出一件事 ─────────────────────────────────────────────────

def _waiting(b: GuardBook | None) -> bool:
    return b is not None and b.stage == "grow" and b.event is None


def _ask(ctx, b: GuardBook, kind: str) -> None:
    """要一件事：叫不到模型的當場給固定事件，叫得到的排給背景寫字。"""
    t = _t(ctx)
    if _modelless(ctx):
        _settle(ctx, b, kind, rules.fixed_event(t, b, kind, _today(ctx), ctx.state.player.name))
        return
    b.want, b.want_at = kind, ctx.state.world.time


def _settle(ctx, b: GuardBook, kind: str, event) -> None:
    today = _today(ctx)
    b.seq = event.seq
    b.event = event
    b.want, b.want_at = "", 0.0
    if kind == "road":
        b.road_n = b.road_n + 1 if b.road_day == today else 1
        b.road_day = today
    else:
        b.home_n = b.home_n + 1 if b.home_day == today else 1
        b.home_day = today


def on_sync(ctx, elapsed: float) -> None:
    b = rules.book(ctx.state)
    if b is not None:
        b.stamina_seen = ctx.state.player.stamina  # 這一下動作之前的體力（after_action 比）
    if not _waiting(b):
        return
    t = _t(ctx)
    if b.want:
        if ctx.state.world.time - b.want_at >= t.wait_seconds:  # 背景寫字一直沒回來：換固定事件
            _settle(ctx, b, b.want, rules.fixed_event(t, b, b.want, _today(ctx), ctx.state.player.name))
        return
    today = _today(ctx)
    done = b.home_n if b.home_day == today else 0
    if done < _home_quota(ctx):
        _ask(ctx, b, "home")


def after_action(ctx) -> list[str]:
    """帶他出門、花了體力的那一下（出陣、遊歷、探索、截殺……）：有機會冒出一件路上的事。"""
    b = rules.book(ctx.state)
    if b is None:
        return []
    p = ctx.state.player
    before, b.stamina_seen = b.stamina_seen, p.stamina
    if not _waiting(b) or b.want or not b.along or before is None or p.stamina >= before:
        return []
    t, today = _t(ctx), _today(ctx)
    if (b.road_n if b.road_day == today else 0) >= t.road_per_day:
        return []
    roll = rules.seed("路上", p.name, b.seq, today, round(ctx.state.world.time)) % 10000 / 10000
    if roll >= t.road_chance:
        return []
    _ask(ctx, b, "road")
    return [rules.fill("（{name}在一旁看著。）", b)] if b.event is not None else []


# ── 給模型的單子（A 段，鎖內只讀）與寫回（C 段）───────────────────────────

def _request(ctx, b: GuardBook, kind: str, seq: int, **extra) -> rules.EventRequest:
    t, p = _t(ctx), ctx.state.player
    return rules.EventRequest(
        seq=seq, kind=kind, day=_today(ctx), name=b.name, sex=b.sex, master=p.name, master_sex=getattr(p, "gender", "男"),
        place=_place_name(ctx, p.location), band=rules.band(t, b.qing), opening=rules.opening(b.opening)["text"][:80],
        memos=tuple(e.text for e in b.log[-t.prompt_memos:]),
        tags=tuple(k for k, _ in sorted(b.tags.items(), key=lambda kv: -kv[1])[:3]), tag_list=tuple(t.tags), **extra)


def event_request(ctx) -> rules.EventRequest | None:
    """背景寫字要生的那一件（want 設了、還沒有事件）；沒有是 None。"""
    b = rules.book(ctx.state)
    if not _waiting(b) or not b.want:
        return None
    return _request(ctx, b, b.want, b.seq + 1)


def apply_event(ctx, req: rules.EventRequest, event) -> bool:
    """C 段：重驗還在等同一件才收；寫不出來（None）換固定事件。收了回 True。"""
    b = rules.book(ctx.state)
    if not _waiting(b) or b.want != req.kind or b.seq + 1 != req.seq:
        return False
    if event is None:
        event = rules.fixed_event(_t(ctx), b, req.kind, _today(ctx), ctx.state.player.name)
    _settle(ctx, b, req.kind, event)
    return True


def say_request(ctx, text: str):
    """自己寫的那一句（A 段）：眼前有攤開的那一件、字數對，回單子；不行回那一句話（list）。"""
    b, t = rules.book(ctx.state), _t(ctx)
    text = str(text or "").strip()
    if b is None or b.stage != "grow" or b.event is None:
        return [rules.NO_SUCH]
    if not 1 <= len(text) <= t.say_max:
        return [rules.SAID_TOO_LONG.replace("{n}", str(t.say_max))]
    return _request(ctx, b, b.event.kind, b.event.seq, say=text, event=b.event.text)


def apply_say(ctx, req: rules.EventRequest, judged) -> list[str]:
    """C 段：重驗還是同一件；模型評不到（None）不算這一次；看不懂（空的 label）回「沒聽懂」；評到了照評的記。"""
    b = rules.book(ctx.state)
    if b is None or b.event is None or b.event.seq != req.seq:
        return [rules.NO_SUCH]
    if judged is None or not judged.label:
        return [rules.fill(rules.NOT_UNDERSTOOD, b)]
    return [f"你：「{req.say}」", *rules.apply(_t(ctx), b, judged, _today(ctx), ctx.stamp(ctx.state.world.time))]


# ── 養成冊上的 ────────────────────────────────────────────────────────

def rename(ctx, name: str) -> list[str]:
    b = rules.book(ctx.state)
    name = str(name or "").strip()
    if b is None or b.stage != "grow":
        return [rules.NO_SUCH]
    if b.renamed:
        return [rules.RENAME_ONCE]
    problem = naming.name_problem(name, ctx.content)
    if problem:
        return [problem]
    b.name, b.renamed = name, True
    return [rules.fill(rules.RENAMED, b)]


def set_along(ctx, on: bool) -> list[str]:
    b = rules.book(ctx.state)
    if b is None or b.stage != "grow":
        return [rules.NO_SUCH]
    b.along = bool(on)
    return [rules.fill(rules.ALONG_ON if b.along else rules.ALONG_OFF, b)]


def status(ctx) -> dict:
    """養成冊那一份（main.guard）：收養了才有。情分不露數字，只給心性那一檔與墨線的位置（0～1）。"""
    b = rules.book(ctx.state)
    if b is None or b.stage != "grow":
        return {}
    t = _t(ctx)
    ev = b.event
    return {"guard": {
        "name": b.name, "sex": b.sex, "pron": rules.pron(b), "stage": b.stage, "band": rules.band(t, b.qing),
        "meter": round((b.qing + t.qing_cap) / (2 * t.qing_cap), 3), "can_rename": not b.renamed, "along": b.along,
        "say_max": t.say_max,
        "event": None if ev is None else {"text": ev.text, "shown": ev.shown, "choices": [c.label for c in ev.choices]},
        "log": [{"stamp": e.stamp, "text": e.text, "tone": (e.qing > 0) - (e.qing < 0)} for e in reversed(b.log[-12:])],
        "count": len(b.log),
    }}


def on_season_start(ctx, old) -> None:
    """跟著帳號走（Joy 2026-11-09 照推薦）：整份由 season.carry 那一格照帶過來了；這裡收掉眼前那一件與天的帳（季的天重新數）。"""
    b = ctx.state.player.guard
    if b is None:
        return
    b.event, b.want, b.want_at, b.stamina_seen = None, "", 0.0, None
    b.home_day = b.home_n = b.road_day = b.road_n = 0
    if b.stage in ("met", "saved"):  # 還沒救下、還沒決定收不收的那一段：新的一季重新遇見
        ctx.state.player.guard = None
