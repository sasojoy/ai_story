"""人物情誼的動作（功能包；全部拆包第 19 批，計畫 docs/superpowers/plans/2026-11-04-人物情誼包-第1批.md）：原本 Game 上的 29 個方法，名字去掉前導底線、
第一個參數是 ctx（第一階就是 Game）。Game 留一行的委派給 server、核心原位、假人與測試；招募那一段選單、同步的書信那一格、`errand` 的標題原本寫在
Game._everyday_options、sync、_action_title，也搬進來。

包裡叫回 Game 的都在服務清單（tianxia/core/services.py）。這一批互相叫直接叫函式（沒有測試換掉這幾個；手冊第十五節「包裡叫回 Game 的方法經不經 ctx」）。
"""
from __future__ import annotations

from tianxia import annals, figures  # 過渡：待搬（行狀 annals 第 29 批拆兩半；人物表 figures 第 40 批進共用規則層）
from tianxia import roster, team, zh
from tianxia.core.option import Option
from tianxia.core.services import PAUSED_TEXT
from tianxia.models import Effect
from tianxia.rules import rate_words
from tianxia.state import PLAYER

from . import errands as errand_rules
from . import letters, parley
from . import stances as stance_rules

# 名冊第一列是本人（PLAYER）：本人永遠出戰，加入、移出都只回一句話，隊伍裡不會多出一個 "player"
SELF_IN_TEAM = "本人一直都在隊伍裡，不用加入，也不能移出。"
FOLLOWER_IN_TEAM = "部下一直跟著你出戰，不用加入，也不能移出。"  # 計畫 T5


# ── 招募 ────────────────────────────────────────────────


def recruit_target(ctx) -> str | None:
    """這個地點目前能嘗試招募的人（自由之身、recruit_at 是這裡、情誼到門檻 roster.affinity_ok）；沒有就是 None。"""
    s, c = ctx.state, ctx.content
    for cid, ch in c.characters.items():
        if (ch.kind == "recruitable" and ch.recruit_at == s.player.location and roster.owned_by(ctx.world, cid) is None
                and roster.affinity_ok(s, c, cid)):
            return cid
    return None


def recruit_targets(ctx) -> list[str]:
    """歷史武將同行（Config.companions）：此地此刻站著（_figures_here，照人物此刻的所在）、標了 recruitable、還沒有主、
    情誼到門檻（roster.affinity_ok，沒到的不畫鈕）的人。關著是空的（舊的 recruit_at 那一條照舊走 recruit_target）。"""
    if not roster.on(ctx.content):
        return []
    return [
        cid for cid in ctx._figures_here()
        if ctx.content.characters[cid].recruitable and roster.owned_by(ctx.world, cid) is None
        and roster.affinity_ok(ctx.state, ctx.content, cid)
    ]


def recruitable_here(ctx) -> bool:
    """此地有人招得了你（recruit_targets 裡陣營對、名下沒滿的）：h_recruit 照它說，灰掉的鈕不算（黃巾的人在涿郡不說）。"""
    s, c = ctx.state, ctx.content
    return any(roster.recruit_problem(s, c, ctx.world, cid) is None for cid in recruit_targets(ctx))


def recruit_options(ctx) -> list[Option]:
    """選單上招募那一段（Game._everyday_options 裡求見之後、前往之前，位置算行為）：舊的 recruit_at 那一顆，與歷史武將同行此地此刻站著、
    還沒有主的每一位一顆；招不了的灰掉寫原因。"""
    s, c = ctx.state, ctx.content
    opts: list[Option] = []
    target = recruit_target(ctx)
    if target is not None:
        cfg = c.config
        chance = roster.recruit_chance(c, s, target)
        opts.append(ctx._cost_option(
            "act:recruit", f"招募【{c.characters[target].name}】", cfg.recruit_stamina,
            note=f"成功率約 {chance * 100:.0f}%",
        ))
    for cid in recruit_targets(ctx):
        problem = roster.recruit_problem(s, c, ctx.world, cid)
        name = c.characters[cid].name
        if problem is not None:
            opts.append(Option(id=f"act:recruit:{cid}", label=f"招募【{name}】（{problem}）", enabled=False))
        else:
            chance = roster.recruit_chance(c, s, cid)
            opts.append(ctx._cost_option(
                f"act:recruit:{cid}", f"招募【{name}】", c.config.recruit_stamina, note=f"成功率約 {chance * 100:.0f}%",
            ))
    return opts


def recruit(ctx) -> list[str]:
    target = recruit_target(ctx)
    if target is None:
        return ["（此地此刻沒有能招募的人。）"]
    return roster.attempt_recruit(ctx.state, ctx.content, ctx.world, target, ctx.rng)


def recruit_one(ctx, cid: str) -> list[str]:
    """歷史武將同行：招這一位（第三節，照現在的成功率；失敗照舊可能被要求決鬥）。選單上那一顆按得下去才會走到這裡，
    這裡再驗一次：人還在這裡、沒有主、陣營對、名下沒滿。"""
    if cid not in recruit_targets(ctx):
        return ["（此刻無法這麼做。）"]
    ctx._settle_partings()  # 9.6：原主人不會因為比別人先上線就用舊情誼搶回來
    problem = roster.recruit_problem(ctx.state, ctx.content, ctx.world, cid)
    if problem is not None:
        return [f"（{problem}。）"]
    return roster.attempt_recruit(ctx.state, ctx.content, ctx.world, cid, ctx.rng)


# ── 門下與隊伍 ────────────────────────────────────────


def roster_lines(ctx) -> list[tuple[str, str]]:
    return roster.roster_lines(ctx.state, ctx.content, ctx.world)


def owned_companions(ctx) -> list[str]:
    return roster.owned_companions(ctx.world, ctx.state.player.name)


def add_to_team(ctx, companion_id: str) -> list[str]:
    if companion_id == PLAYER:
        return ctx._log([SELF_IN_TEAM])
    if companion_id.startswith(team.FOLLOWER_KEY):
        return ctx._log([FOLLOWER_IN_TEAM])
    return ctx._log(team.add_to_team(ctx.state, companion_id))


def remove_from_team(ctx, companion_id: str) -> list[str]:
    if companion_id == PLAYER:
        return ctx._log([SELF_IN_TEAM])
    if companion_id.startswith(team.FOLLOWER_KEY):
        return ctx._log([FOLLOWER_IN_TEAM])
    return ctx._log(team.remove_from_team(ctx.state, companion_id))


def release_companion(ctx, companion_id: str) -> list[str]:
    """放他回江湖（歷史武將同行第四節【PM】）：修練頁名冊上那一顆（網頁先問一次）。全服放掉 owner、拿出出戰隊伍、
    江湖紀錄一則；情誼、他的進度都不動。開關關著、不是你名下的只回一句話。"""
    c, cid = ctx.content, str(companion_id)
    if not roster.on(c) or cid not in c.characters or not roster.owns(roster.owned_by(ctx.world, cid), ctx.state.player.name):
        return ctx._log([roster.RELEASE_NOT_YOURS])
    ctx.world.release_companion(cid)
    team.remove_from_team(ctx.state, cid)
    name = c.characters[cid].name
    msgs = [roster.RELEASE_DONE.format(name=name)]
    ctx._write(roster.RELEASE_TITLE.format(name=name), msgs)
    return ctx._log(msgs)


def release_view(ctx, companion_id: str | None) -> dict | None:
    """修練頁人物卡的「放他回江湖」：開關開著、這個人在你名下才有（問句照 roster.RELEASE_CONFIRM），否則 None。"""
    c = ctx.content
    if not roster.on(c) or companion_id not in c.characters:
        return None
    if not roster.owns(roster.owned_by(ctx.world, companion_id), ctx.state.player.name):
        return None
    return {"confirm": roster.RELEASE_CONFIRM.format(name=c.characters[companion_id].name)}


# ── 人物心意（減法季批 6；stances.py、共用規則層 stance_world）────────────


def stance_before(ctx, cid: str) -> str | None:
    """這一輪對話之前，你今天跟這位人物記過的那一筆（沒有心意、關著是 None）：跟之後比，看這一輪有沒有記到。"""
    fid = stance_rules.figure_of(ctx.content, cid)
    return stance_rules.heard_today(ctx.state, ctx.content, fid) if fid is not None else None


def stance_credit(ctx, cid: str, before: str | None) -> None:
    """這一輪對話記到一筆心意（之前今天沒記過、之後有了）：記 Config.jianfa.stance_contribution 點貢獻（整合設計 5.3，跟分岔同一本上限）。"""
    fid = stance_rules.figure_of(ctx.content, cid)
    if fid is not None and before is None and stance_rules.heard_today(ctx.state, ctx.content, fid) is not None:
        ctx._deed_points(ctx.content.config.jianfa.stance_contribution)


def voice_stance(ctx, fid: str, sid: str) -> bool:
    """不說話、直接記一筆心意（只有伺服器假人叫：bot_policy 照 stances.bot_pick，企劃者 2026-10-24 第 5 件）：一人一天一筆的規則、
    到門檻、貢獻都跟真人說話那一輪一樣，只是沒有那一輪對話、不寫江湖紀錄。記到了存季，回有沒有記。"""
    if ctx.world.paused_at() is not None or ctx.state.world.ended:
        return False
    if not stance_rules.record(ctx.state, ctx.content, fid, sid):
        return False
    ctx._deed_points(ctx.content.config.jianfa.stance_contribution)
    ctx._save_season()
    return True


def stance_annals(ctx) -> None:
    """同步時：這一週你勸過的心意到了門檻，記一則行狀（annals.STANCE：只寫他改做什麼，不列名字、不寫你說的話）。"""
    s, c = ctx.state, ctx.content
    for fid, d in stance_rules.annals_due(s, c):
        cid = c.figures[fid].character or fid
        annals.note(s, c, annals.STANCE, stance_rules.ANNAL.format(name=c.figures[fid].name, stance=d.name, rumor=d.rumor), 2,
                    figure=cid, time=s.world.stance_active[fid].at)


def figure_view(ctx, cid: str) -> dict | None:
    """人物頁的資料（主機側計畫 1.3 的 figure.stances、figure.errands）：{"id", "name", "stances", "my_stance_today", "errands"}；
    心意關著（或他沒有心意）沒有前兩個鍵、託付關著（或他沒有託付池）沒有 errands。兩樣都沒有是 None。"""
    s, c = ctx.state, ctx.content
    fid = figures.of_character(c, cid)
    if fid is None:
        return None
    mind = stance_rules.view(s, c, fid)
    jobs = errand_rules.view(s, c, fid=fid) if errand_rules.on(c, s.world) and c.figures[fid].errands else None
    if mind is None and jobs is None:
        return None
    out: dict = {"id": cid, "name": c.figures[fid].name, **(mind or {})}
    if jobs is not None:
        out["errands"] = jobs
    return out


# ── 託付與勸降（減法季批 6；errands.py）────────────


def errands_view(ctx) -> list[dict] | None:
    """江湖畫面的 main.errands（主機側計畫 1.3）：這一季人物託你的事；託付關著是 None（畫面沒有這個鍵）。"""
    s, c = ctx.state, ctx.content
    return errand_rules.view(s, c) if errand_rules.on(c, s.world) else None


def errand_options(ctx) -> list[Option]:
    """人在託付的地點：交信（不花體力）、探營、勸降（花 errand_stamina）。勸降按下去只叫出輸入框（choose 的早退，errand_ask）。"""
    s, c = ctx.state, ctx.content
    opts = []
    for e in errand_rules.here(s, c):
        option_id = f"errand:{errand_rules.VERBS[e.kind]}:{e.id}"
        label = f"{errand_rules.LABELS[e.kind]}（替{errand_rules.who(c, e)}{errand_rules.task_text(c, e)}）"
        if e.kind == "letter":
            opts.append(Option(id=option_id, label=label))
        else:
            opts.append(ctx._cost_option(option_id, label, c.config.jianfa.errand_stamina))
    return opts


def errand_ask(ctx, arg: str) -> list[str] | None:
    """勸降（減法季批 6）：選項本身只叫出輸入框，送出走 persuade_request／persuade（Game.choose 建紀錄之前問，所以不寫江湖紀錄）；
    C 段（_persuade_said 擺好了）與別的種類是 None，照 choose 掛鉤走 errand_act。"""
    if arg.startswith("persuade:") and ctx._persuade_said is None:
        return [errand_rules.PERSUADE_ASK]
    return None


def errand_title(ctx, arg: str) -> str:
    """託付那一下江湖紀錄的標題：「交信・盧植」。"""
    s, c = ctx.state, ctx.content
    e = errand_rules.find(s, arg.partition(":")[2])
    return f"{errand_rules.LABELS[e.kind]}・{errand_rules.who(c, e)}" if e is not None else "託付"


def errand_act(ctx, arg: str) -> list[str]:
    """交信（errand:deliver:<id>）、探營（errand:scout:<id>）、勸降（errand:persuade:<id>，只從 persuade 的 C 段進來）：重驗那一件
    還在辦、人在那裡、是那一種，照種類做完、給獎勵。"""
    s, c = ctx.state, ctx.content
    verb, _, eid = arg.partition(":")
    e = errand_rules.find(s, eid)
    if e is None or e not in errand_rules.here(s, c) or errand_rules.VERBS[e.kind] != verb:
        return [errand_rules.NOT_HERE]
    if e.kind == "letter":
        d = errand_rules.find_def(c, e.figure, e.errand)
        msgs = [errand_rules.DELIVERED.format(to=d.to or errand_rules.place(c, e.target))]
        msgs += errand_reward(ctx, e)
        errand_rules.thank(s, c, e)
        return msgs
    s.player.stamina -= c.config.jianfa.errand_stamina
    if e.kind == "scout":
        lines = errand_rules.scout_lines(s, c, e)
        errand_rules.note_scout(s, c, e, lines)
        return [errand_rules.SCOUT_TITLE.format(place=errand_rules.place(c, e.target)), *lines, *errand_reward(ctx, e)]
    return errand_persuade(ctx, e)


def errand_reward(ctx, e) -> list[str]:
    """辦成了（整合設計 5.5）：他的情誼 +affinity（照寫的數字給、不照 affinity_gain_scale 放慢，夾在 0～100；PM 2026-10-26）、
    貢獻 +contribution（不吃每天的貢獻上限、也不佔那一本，PM 2026-10-26）、他的那個心意 +1、行狀一則（annals.ERRAND）。回紀錄的句子。"""
    s, c = ctx.state, ctx.content
    d = errand_rules.find_def(c, e.figure, e.errand)
    errand_rules.done(s, e)
    cid = errand_rules.cid_of(c, e)
    msgs = [errand_rules.DONE.format(who=errand_rules.who(c, e))]
    if d is not None:
        msgs += errand_rules.warm(s, c, cid, d.affinity)
        ctx._deed_points(d.contribution, capped=False)
        stance_rules.bump(s, c, e.figure, d.stance)
    annals.note(s, c, annals.ERRAND, f"替{errand_rules.who(c, e)}{errand_rules.task_text(c, e)}，辦成了。", 3, figure=cid)
    return msgs


def errand_persuade(ctx, e) -> list[str]:
    """勸降的結果（choose 的這一下，_persuade_said 是單子與模型的分數）：引擎加情誼名望的修正、夾、自己擲骰；成了立痕跡 band_turned
    （Effect.marks 走 _apply：一人一天一筆、恤民這類心意的倍數照算）、推那一條線（errands.turn_band：一次性的推法，照寫的量、不打事件五折、
    不另記推線的貢獻；FB-827）、給獎勵；敗了打一場遭遇（_squad_encounter，同探索撞上的野怪），那一件沒談成。"""
    s, c = ctx.state, ctx.content
    request, rate = ctx._persuade_said
    d = errand_rules.find_def(c, e.figure, e.errand)
    who = d.persuade.who if d is not None and d.persuade is not None else ""
    final = errand_rules.persuade_rate(s, c, e, rate)
    msgs = [f"你：「{request.text}」（{rate_words(final)}）"]
    if errand_rules.persuade_roll(s, e) < final:
        msgs.append(errand_rules.PERSUADE_WON.format(who=who))
        if d is not None and d.persuade is not None:
            msgs += ctx._apply(Effect(marks=dict(d.persuade.marks)))
            msgs += errand_rules.turn_band(s, c, d, e.target)
        return msgs + errand_reward(ctx, e)
    msgs.append(errand_rules.PERSUADE_LOST.format(who=who))
    errand_rules.done(s, e, "failed")
    if d is not None and d.persuade is not None and d.persuade.foe in c.squads:
        msgs += ctx._squad_encounter(d.persuade.foe, wild=True)
    return msgs


def persuade_request(ctx, errand_id: str, text: str) -> errand_rules.PersuadeRequest | list[str]:
    """勸降的 A 段（server.persuade_text 在行動鎖內、很快地呼叫；只讀）：那一件按得下去（勸降、人在那裡、體力夠）、字是 1～20 字，
    就開單；不行回拒絕的話。"""
    if ctx.world.paused_at() is not None:
        return [f"（{PAUSED_TEXT}。）"]
    s, c = ctx.state, ctx.content
    problem = errand_rules.persuade_problem(s, c, errand_id)
    if problem is not None:
        return [problem]
    said = errand_rules.clean_text(text)
    option = {o.id: o for o in ctx.options(odds=False, tick=False)}.get(f"errand:persuade:{errand_id}")
    if said is None or option is None or not option.enabled:
        return [errand_rules.PERSUADE_ASK]
    e = errand_rules.find(s, errand_id)
    d = errand_rules.find_def(c, e.figure, e.errand)
    return errand_rules.PersuadeRequest(
        errand=errand_id, figure=errand_rules.who(c, e), who=d.persuade.who if d is not None and d.persuade else "",
        place=errand_rules.place(c, e.target), text=zh.to_traditional(said),
    )


def persuade(ctx, request: errand_rules.PersuadeRequest, rate: int | None = None) -> list[str]:
    """勸降的 C 段（鎖內）：重驗同一件、同一句還按得下去才扣體力擲骰（choose 的 errand:persuade，紀錄、行狀照一般動作寫）。
    rate 是鎖外評好的 0～100；None＝模型叫不動：照批 4 的慣例落到最保守的結果——什麼都不發生（不扣體力、不打、那一件照舊在），
    回 PERSUADE_SILENT，不寫紀錄。"""
    now = persuade_request(ctx, request.errand, request.text)
    if isinstance(now, list):
        return ctx._log(now)
    if (now.errand, now.text) != (request.errand, request.text):
        return ctx._log([errand_rules.NOT_HERE])
    if rate is None:
        return ctx._log([errand_rules.PERSUADE_SILENT])
    ctx._persuade_said = (now, max(0, min(100, int(rate))))
    try:
        return ctx.choose(f"errand:persuade:{request.errand}")
    finally:
        ctx._persuade_said = None


# ── 書信與委託（大勢人物擴充第二批；letters.py）──


def letter_view(ctx) -> dict | None:
    """江湖頁「剛剛」上面那張小卡：最新一封沒看過的信；沒有是 None。"""
    return letters.view(ctx.state, ctx.content)


def read_letter(ctx, letter_id: int) -> list[str]:
    """小卡上的「收起」：記成看過了（委託照樣在身上，懸賞卡上看得到）。"""
    return letters.read(ctx.state, letter_id)


def decline_letter(ctx, letter_id: int) -> list[str]:
    """小卡上的「婉拒」：這封信附的委託作罷（不扣情誼），信記成看過了。"""
    msgs = letters.decline(ctx.state, ctx.content, letter_id)
    if msgs and msgs[0] != letters.NO_LETTER:
        ctx._write(letters.TITLE, msgs)
    return msgs


def deliver_mail(ctx, now: float) -> None:
    """同步裡書信那一格（Game.sync）：先收欠人物的事過了期限的句子（parley.lapse：NPC 智能 2.1，欠的事作罷、附的委託先作罷，書信不再補一句），
    接上人物來信、過期的委託作罷，併成一則「書信」，有字才寫。（第 19 批 mail 是呼叫端傳的；第 20 批 parley 進同一包，這一行搬進來。）"""
    mail = parley.lapse(ctx.state, ctx.content)
    mail += letters.deliver(ctx.state, ctx.content, now)
    if mail:
        ctx._write(letters.TITLE, mail)


def morning_mail(ctx, now: float) -> bool:
    """減法季「09:00 來信」（整合設計第十章，批 9）：伺服器的看守替開了推播的人送今天的信，不必等他上線（送了手機才跳得出
    「某某來信」）。只做同步裡書信那一格（letters.deliver），不補算體力、不算上線、不動「此地還有」；他下次同步照常，同一個
    送信日不會再送第二封。角色還停在上一季（換季後還沒上線過）、或這一季沒開 morning_mail 時什麼都不做。
    呼叫端拿著行動鎖、事後存角色；送了一封回 True。"""
    ctx.now = now
    if ctx.state.player.season_number < ctx.world.get_season_number():
        return False
    ctx.state.world = ctx.world.get_season()
    if letters.mail_day(ctx.content, ctx.state.world, now) is None:
        return False
    seq = ctx.state.player.letter_seq
    mail = letters.deliver(ctx.state, ctx.content, now)
    if mail:
        ctx._write(letters.TITLE, mail)
    return ctx.state.player.letter_seq != seq


def letter_request(ctx) -> letters.LetterNote | None:
    """還等著模型照他的口氣重寫的那一封（server 鎖外寫；A 段，只讀）。"""
    return letters.request(ctx.state, ctx.content)


def apply_letter(ctx, note: letters.LetterNote, text: str) -> bool:
    """C 段：還是同一封才換；寫不出來照固定句。"""
    return letters.apply(ctx.state, note, text)
