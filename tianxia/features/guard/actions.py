"""親衛隊長的動作（ctx 是 Game；只叫 tianxia/core/services_list.md 清單上的）。第一批：遇見與成長；第二批：求學、出師、投效。

- options：「此地還能做」——10 級起撞見那個孩子；救了沒收的回到那裡能回頭；有一件事在等你時那一顆。
- menu：遇見那一段（救不救、收不收）與攤開的那一件事（三個做法、先擱著）接管選單。
- on_sync：每天保底的家裡的事；after_action：帶他出門、花了體力的那一下有機會冒出一件。
  模型叫得到就排給背景寫字（routes 的 OutlockJob，鎖外生）；叫不到、假人、等太久都換固定事件（rules.fixed_event）。
- 自己寫的那一句走鎖外三段式（routes.guard_say：say_request → judge_say → apply_say）。
- rename、set_along：親衛隊長那一頁上的改名（一次）與出門帶不帶他。
- 求學（20 級起，7 天季 15 級；之後看時間不看等級）：挑七處之一（花銀兩、推性向），這幾天寫信回來；期滿回來考驗（trial），
  答了就結算（settle：模型從前三條出路挑一條、取稱號、寫生平與立誓，鎖外；叫不到換固定的），然後跪誓（oath），答了就投效（sworn）。
- on_season_start：跟著帳號走，換季照帶（眼前那一件收掉、天的帳歸零、求學剩下的時間照帶）。"""
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


ADOPTED = ("grow", "study", "trial", "settle", "oath", "sworn")  # 收養以後的幾段（親衛隊長那一頁畫得出來）
EVENT_STAGES = ("grow", "study", "trial", "oath", "sworn")  # 會攤開一件事的幾段（投效之後照樣有家裡、路上的事與每季那一封）


def _adopted(b) -> bool:
    return b is not None and b.stage in ADOPTED


def _week7(ctx) -> bool:
    from tianxia import calendar  # noqa: PLC0415

    return calendar.week7_on(ctx.state.world, ctx.content)


def _study_level(ctx) -> int:
    t = _t(ctx)
    return t.week7_study_level if _week7(ctx) else t.study_level


def _study_seconds(ctx) -> float:
    t = _t(ctx)
    return (t.week7_study_days if _week7(ctx) else t.study_days) * core_rules.day_seconds(ctx.content, ctx.state.world)


def _silver(ctx) -> int:
    return int(ctx.state.player.stats.get("silver", 0))


def _can_study(ctx, b) -> bool:
    return b is not None and b.stage == "grow" and not b.picking and ctx.state.player.member.level >= _study_level(ctx) \
        and (b.event is None or not b.event.shown)


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
    out = []
    if b.stage in EVENT_STAGES and b.event is not None and not b.event.shown:
        head = rules.OPEN_LABELS.get(b.event.kind)
        label = rules.fill(head, b) if head else rules.fill(rules.EVENT_LABEL, b).replace("{peek}", rules.peek(b.event))
        out.append(Option(id=f"{PREFIX}:open", label=label))
    if _can_study(ctx, b):
        out.append(Option(id=f"{PREFIX}:study", label=rules.fill(rules.STUDY_LABEL, b)))
    return out


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
    if b.stage == "grow" and b.picking:
        t, silver = _t(ctx), _silver(ctx)
        out = []
        for key, info in rules.texts.SCHOOLS.items():
            cost = int(t.schools.get(key, {}).get("silver", 0))
            label = rules.fill(info["label"], b) + (f"（銀兩 {cost}）" if cost else "")
            out.append(Option(id=f"{PREFIX}:school:{key}", label=label, enabled=silver >= cost))
        return [*out, Option(id=f"{PREFIX}:stay", label=rules.STAY)]
    if b.stage in EVENT_STAGES and b.event is not None and b.event.shown:
        return [*(Option(id=f"{PREFIX}:pick:{i}", label=c.label) for i, c in enumerate(b.event.choices)),
                Option(id=f"{PREFIX}:later", label=rules.LATER)]
    return None


def title(ctx, arg: str) -> str:
    b = rules.book(ctx.state)
    return b.name if _adopted(b) and b.name else rules.TITLE


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
    if head == "study" and _can_study(ctx, b):
        b.picking = True
        return [rules.fill(rules.STUDY_TEXT, b)]
    if head == "stay" and b.stage == "grow" and b.picking:
        b.picking = False
        return [rules.fill(rules.STAY_TEXT, b)]
    if head == "school" and b.stage == "grow" and b.picking and rest in rules.texts.SCHOOLS:
        return _send_to_school(ctx, b, rest)
    if b.stage not in EVENT_STAGES or b.event is None:
        return [rules.NO_SUCH]
    if head == "open":
        b.event.shown = True
        return [b.event.text]
    if head == "later":
        b.event.shown = False
        return [rules.fill(rules.LATER_TEXT, b)]
    if head == "pick" and rest.isdigit() and int(rest) < len(b.event.choices) and b.event.shown:
        return _answer(ctx, b, b.event.choices[int(rest)])
    return [rules.NO_SUCH]


def _answer(ctx, b: GuardBook, choice) -> list[str]:
    """答了眼前那一件（三個做法之一，或自己寫的那一句評回來的）：記帳，再照那一件是什麼往下一段走。"""
    kind = b.event.kind if b.event is not None else ""
    out = rules.apply(_t(ctx), b, choice, _today(ctx), ctx.stamp(ctx.state.world.time))
    if b.stage == "sworn" and b.season_qing is not None:  # 投效之後一季最多換一檔
        b.qing = rules.season_clamp(_t(ctx), b.season_qing, b.qing)
    if kind == "letter":
        b.letters += 1
    elif kind == "trial":
        b.stage = "settle"
        _ask(ctx, b, "settle")
        if b.stage == "settle":
            out.append(rules.fill(rules.SETTLING, b))
    elif kind == "oath":
        b.stage, b.sworn_season, b.season_qing = "sworn", _season(ctx), b.qing
        out.append(rules.fill(rules.SWORN, b).replace("{path}", b.path).replace("{title}", b.title))
    return out


def _send_to_school(ctx, b: GuardBook, key: str) -> list[str]:
    t, p = _t(ctx), ctx.state.player
    info = t.schools.get(key, {})
    cost = int(info.get("silver", 0))
    if _silver(ctx) < cost:
        return [rules.SILVER_SHORT.replace("{n}", str(cost - _silver(ctx)))]
    p.stats["silver"] = _silver(ctx) - cost
    for tag, n in dict(info.get("tags", {})).items():
        if tag in t.tags:
            b.tags[tag] = b.tags.get(tag, 0) + int(n)
    b.qing = max(-t.qing_cap, min(t.qing_cap, b.qing + int(info.get("qing", 0))))
    now = ctx.state.world.time
    b.picking, b.event, b.want, b.want_at = False, None, "", 0.0
    b.stage, b.school, b.letters = "study", key, 0
    b.study_from, b.study_until = now, now + _study_seconds(ctx)
    name = rules.school_name(key)
    b.log.append(rules.GuardEntry(day=_today(ctx), stamp=ctx.stamp(now), text=rules.fill(rules.SENT_MEMO.replace("{school}", name), b),
                                  qing=int(info.get("qing", 0))))
    del b.log[:-t.log_cap]
    out = [rules.fill(rules.texts.SCHOOLS[key]["text"], b)]
    return [*out, f"銀兩 -{cost}"] if cost else out


# ── 什麼時候冒出一件事 ─────────────────────────────────────────────────

def _waiting(b: GuardBook | None) -> bool:
    return b is not None and ((b.stage in EVENT_STAGES and b.event is None) or b.stage == "settle")


def _fallback(ctx, b: GuardBook, kind: str) -> None:
    """叫不到模型（假人、沒有模型、等太久）：當場給固定的。"""
    t = _t(ctx)
    if kind == "settle":
        _settled(ctx, b, rules.fixed_settle(t, b, ctx.state.player.name))
    else:
        _settle(ctx, b, kind, rules.fixed_event(t, b, kind, _today(ctx), ctx.state.player.name))


def _ask(ctx, b: GuardBook, kind: str) -> None:
    """要一件事（或出師結算）：叫不到模型的當場給固定的，叫得到的排給背景寫字。立誓那一段結算時寫好了，不另叫模型。"""
    if _modelless(ctx) or kind == "oath":
        _fallback(ctx, b, kind)
        return
    b.want, b.want_at = kind, ctx.state.world.time


def _settled(ctx, b: GuardBook, got) -> None:
    """出師結算寫回來：出路、稱號、生平、立誓那一段；紀事記一行，接著跪誓那一件。"""
    t = _t(ctx)
    b.path, b.title, b.bio, b.oath = got.path, got.title, got.bio, got.oath
    b.want, b.want_at = "", 0.0
    b.stage = "oath"
    now = ctx.state.world.time
    b.log.append(rules.GuardEntry(day=_today(ctx), stamp=ctx.stamp(now),
                                  text=rules.fill(rules.GRADUATED_MEMO, b).replace("{path}", b.path).replace("{title}", b.title)))
    del b.log[:-t.log_cap]
    _settle(ctx, b, "oath", rules.fixed_event(t, b, "oath", _today(ctx), ctx.state.player.name))


def _settle(ctx, b: GuardBook, kind: str, event) -> None:
    today = _today(ctx)
    b.seq = event.seq
    b.event = event
    b.want, b.want_at = "", 0.0
    if kind == "road":
        b.road_n = b.road_n + 1 if b.road_day == today else 1
        b.road_day = today
    elif kind == "home":
        b.home_n = b.home_n + 1 if b.home_day == today else 1
        b.home_day = today


def on_sync(ctx, elapsed: float) -> None:
    b = rules.book(ctx.state)
    if b is not None:
        b.stamina_seen = ctx.state.player.stamina  # 這一下動作之前的體力（after_action 比）
        if b.stage == "sworn":
            b.hp_seen = _hp_ratio(ctx)  # 這一下動作之前的氣血（after_action 比：重傷時他說一句）
    if b is not None and b.stage == "study" and b.event is None and not b.want and ctx.state.world.time >= b.study_until:
        b.stage = "trial"  # 學成回來（看時間不看等級）
    if not _waiting(b):
        return
    t = _t(ctx)
    if b.want:
        if ctx.state.world.time - b.want_at >= t.wait_seconds:  # 背景寫字一直沒回來：換固定的
            _fallback(ctx, b, b.want)
        return
    if b.stage in ("grow", "sworn"):
        today = _today(ctx)
        done = b.home_n if b.home_day == today else 0
        if done < _home_quota(ctx):
            _ask(ctx, b, "home")
    elif b.stage == "study":
        span = max(1.0, b.study_until - b.study_from)
        if b.letters < t.letters and ctx.state.world.time >= b.study_from + span * (b.letters + 1) / (t.letters + 1):
            _ask(ctx, b, "letter")
    else:  # trial、settle、oath：每一段只有一件，等著
        _ask(ctx, b, b.stage)


def on_day(ctx) -> None:
    """換日（回體丹那一天換了）：親衛隊長是農夫的，每天替你回幾點體力（Config.guard.perks 農夫 stamina_day，預設 0；core/guard_base.perk 問開關、投效、帶在身邊）。"""
    from tianxia.core import guard_base  # noqa: PLC0415

    n = guard_base.perk(ctx.state, ctx.content, "stamina_day")
    if n:
        p = ctx.state.player
        p.stamina = min(float(ctx.content.config.stamina_max), p.stamina + n)


def _hp_ratio(ctx) -> float:
    from tianxia import team  # noqa: PLC0415

    s, c = ctx.state, ctx.content
    now, cap = team.member_neili(c, s.player.member, team.con_of(s, c, ctx.world, team.PLAYER), season=s.world)
    return now / cap if cap > 0 else 1.0


def after_action(ctx) -> list[str]:
    """帶他出門、花了體力的那一下（出陣、遊歷、探索、截殺……）：有機會冒出一件路上的事。"""
    b = rules.book(ctx.state)
    if b is None:
        return []
    p = ctx.state.player
    before, b.stamina_seen = b.stamina_seen, p.stamina
    said = _hurt(ctx, b)
    if b.stage not in ("grow", "sworn") or not _waiting(b) or b.want or not b.along or before is None or p.stamina >= before:
        return said
    t, today = _t(ctx), _today(ctx)
    if (b.road_n if b.road_day == today else 0) >= t.road_per_day:
        return []
    roll = rules.seed("路上", p.name, b.seq, today, round(ctx.state.world.time)) % 10000 / 10000
    if roll >= t.road_chance:
        return []
    _ask(ctx, b, "road")
    return said + ([rules.fill("（{name}在一旁看著。）", b)] if b.event is not None and b.stage == "grow" else [])


def _hurt(ctx, b: GuardBook) -> list[str]:
    """投效之後，做完一件事氣血掉到 hurt_ratio 以下、而且比做之前少（打輸、重傷）：他照心性說一句，一天一次（恩的擔心，恨的在等）。"""
    if b.stage != "sworn" or not b.along:
        return []
    before, now = b.hp_seen, _hp_ratio(ctx)
    b.hp_seen = now
    today = _today(ctx)
    if before is None or now >= before or now >= _t(ctx).hurt_ratio or b.hurt_day == today:
        return []
    b.hurt_day = today
    return [rules.hurt_line(_t(ctx), b, today)]


# ── 給模型的單子（A 段，鎖內只讀）與寫回（C 段）───────────────────────────

def _request(ctx, b: GuardBook, kind: str, seq: int, **extra) -> rules.EventRequest:
    t, p = _t(ctx), ctx.state.player
    return rules.EventRequest(
        seq=seq, kind=kind, day=_today(ctx), name=b.name, sex=b.sex, master=p.name, master_sex=getattr(p, "gender", "男"),
        place=_place_name(ctx, p.location), band=rules.band(t, b.qing), opening=rules.opening(b.opening)["text"][:80],
        memos=tuple(e.text for e in b.log[-t.prompt_memos:]),
        tags=tuple(k for k, _ in sorted(b.tags.items(), key=lambda kv: -kv[1])[:3]), tag_list=tuple(t.tags),
        school=rules.school_name(b.school) if b.stage != "grow" else "", path=b.path if b.stage == "sworn" else "", title=b.title if b.stage == "sworn" else "",
        paths=tuple(rules.top_paths(t, b)) if kind in ("trial", "settle") else (), **extra)


def event_request(ctx) -> rules.EventRequest | None:
    """背景寫字要生的那一件（want 設了、還沒有事件）；沒有是 None。"""
    b = rules.book(ctx.state)
    if not _waiting(b) or not b.want:
        return None
    return _request(ctx, b, b.want, b.seq + 1)


def apply_event(ctx, req: rules.EventRequest, event) -> bool:
    """C 段：重驗還在等同一件才收；寫不出來（None）換固定的。出師結算（settle）夾過再寫回（出路只能是交出去的那幾條、稱號過名字規則）。收了回 True。"""
    b = rules.book(ctx.state)
    if not _waiting(b) or b.want != req.kind or b.seq + 1 != req.seq:
        return False
    if event is None:
        _fallback(ctx, b, req.kind)
    elif req.kind == "settle":
        _settled(ctx, b, rules.clamp_settled(_t(ctx), b, event, req.paths, ctx.state.player.name,
                                             lambda n: naming.name_problem(n, ctx.content)))
    else:
        _settle(ctx, b, req.kind, event)
    return True


def say_request(ctx, text: str):
    """自己寫的那一句（A 段）：眼前有攤開的那一件、字數對，回單子；不行回那一句話（list）。"""
    b, t = rules.book(ctx.state), _t(ctx)
    text = str(text or "").strip()
    if b is None or b.stage not in EVENT_STAGES or b.event is None:
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
    return [f"你：「{req.say}」", *_answer(ctx, b, judged)]


# ── 親衛隊長那一頁上的 ────────────────────────────────────────────────────────

def rename(ctx, name: str) -> list[str]:
    b = rules.book(ctx.state)
    name = str(name or "").strip()
    if not _adopted(b):
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
    if b is None or b.stage not in ("grow", "sworn"):
        return [rules.NO_SUCH]
    b.along = bool(on)
    return [rules.fill(rules.ALONG_ON if b.along else rules.ALONG_OFF, b)]


def status(ctx) -> dict:
    """親衛隊長那一頁那一份（main.guard）：收養了才有。情分不露數字，只給心性那一檔與墨線的位置（0～1）。"""
    b = rules.book(ctx.state)
    if not _adopted(b):
        return {}
    t = _t(ctx)
    ev = b.event
    return {"guard": {
        "name": b.name, "sex": b.sex, "pron": rules.pron(b), "stage": b.stage, "stage_text": rules.fill(rules.STAGE_TEXT[b.stage], b),
        "band": rules.band(t, b.qing), "school": rules.school_name(b.school) if b.school else "",
        "study_until": ctx.stamp(b.study_until) if b.stage == "study" else "", "path": b.path, "title": b.title,
        "bio": b.bio if b.stage == "sworn" else "",
        "meter": round((b.qing + t.qing_cap) / (2 * t.qing_cap), 3), "can_rename": not b.renamed, "along": b.along,
        "can_study": _can_study(ctx, b) and _free(ctx),
        "say_max": t.say_max,
        "art": rules.art(t, b),
        "event": None if ev is None else {"text": ev.text, "shown": ev.shown, "kind": ev.kind, "choices": [c.label for c in ev.choices]},
        "log": [{"stamp": e.stamp, "text": e.text, "tone": (e.qing > 0) - (e.qing < 0)} for e in reversed(b.log[-12:])],
        "count": len(b.log),
    }}


def on_season_start(ctx, old) -> None:
    """跟著帳號走（Joy 2026-11-09 照推薦）：整份由 season.carry 那一格照帶過來了；這裡收掉眼前那一件與天的帳（季的天重新數）。"""
    b = ctx.state.player.guard
    if b is None:
        return
    if b.stage == "study":  # 求學剩下的時間照帶（世界秒換季重數）
        then, now = (old.world.time if old is not None else ctx.state.world.time), ctx.state.world.time
        b.study_from, b.study_until = now - max(0.0, then - b.study_from), now + max(0.0, b.study_until - then)
    b.event, b.want, b.want_at, b.stamina_seen, b.picking, b.hp_seen = None, "", 0.0, None, False, None
    b.home_day = b.home_n = b.road_day = b.road_n = b.hurt_day = 0
    if b.stage == "sworn":  # 投效了：這一季從這裡算心性能換幾檔；開季那一天先來一封（這一季的他）
        b.season_qing = b.qing
        b.home_day, b.home_n = _today(ctx), _home_quota(ctx)
        _ask(ctx, b, "season")
    if b.stage in ("met", "saved"):  # 還沒救下、還沒決定收不收的那一段：新的一季重新遇見
        ctx.state.player.guard = None
