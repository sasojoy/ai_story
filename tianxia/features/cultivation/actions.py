"""修練包的動作（全部拆包第 23 批）：原本 Game 上修練頁的那幾個方法，Game 留一行委派給 server、假人、測試與核心原位。
ctx 就是 Game（第一階）；只叫 tianxia/core/services_list.md 那張清單上的。搬進來的互相叫直接叫函式（allocate_stat → allocate_line）；
絕學的規則照模組屬性叫（cultivation.seize、cultivation.cultivate_problem……：測試換掉模組上的，這裡照樣打得到）。

- 拜師學藝（learn:）：原本 Game.choose 的 learn 那一支、Game._action_title 的那一格（choose 掛鉤，__init__.py）
- 改練、練成、意境裝卸、熔煉（批量）、絕學（服丹衝關、舊存檔的定名、破境卡三段式的 A、C 段與收卡）、傳功、配點與境界卡
- 核心原位叫的：讀檔時拿掉追風步的舊品質（_drop_stale_references）、別人定了名下一次同步補一則（sync）、絕學的契機（核心的單打服務
  _seize 與決戰包的收場補送經 ctx._seize_chance）、狀態列的破境卡（status_data 的 ascension）
"""
from __future__ import annotations

from tianxia import arts as arts_mod  # 共用規則層
from tianxia.core import annal_base as annals  # 核心（行狀記一筆，第 29 批之二）
from tianxia import attrset  # 核心（五項屬性）
from tianxia import growth, journal, library, naming, team
from tianxia import prologue as prologue_rules  # 序章（共用規則層；Game.new 有個參數也叫 prologue，照 engine 叫 prologue_rules）
from tianxia.core.option import Option
from tianxia.core.services import not_while_preparing
from tianxia.martial_arts import is_renamed
from tianxia.rules import jianfa
from tianxia.state import JournalEntry

from . import art_view, ascend, cultivation
from . import chuangong as chuangong_rules  # 這一份有個函式也叫 chuangong（Game.chuangong 的本體）

MELT_MANY_PROLOGUE = "這裡照師父說的，一門一門熔。"  # 序章裡不給批量熔煉（序章的熔煉是教學的一步）


# ── 拜師學藝（learn:；choose 掛鉤，__init__.py）──


def learn_title(ctx, skill_id: str) -> str:
    """這一下江湖紀錄的標題（原本 Game._action_title 的 learn 那一格）。"""
    return f"學藝・{ctx.content.skills[skill_id].name}"


def learn(ctx, skill_id: str) -> list[str]:
    """學一門（原本 Game.choose 的 learn 那一支）：共用規則層的 library.learn。"""
    return library.learn(ctx.state, ctx.content, skill_id)


# ── 核心原位叫的（讀檔、同步、仗打完、狀態列）──


def drop_old_zhuifeng(ctx) -> None:
    """追風步（PM 2026-10-14；企劃者跟玩家談過，玩家同意退回下品）：內容以前沒寫品質、照 SkillDef 的預設成了絕學，現在是下品。
    舊角色讀檔時照內容讀就是下品（沒有自己那一份的紀錄）；中間有一版（7f993d2）把絕學寫進了自己那一份
    （art_quality、art_rolled），這裡拿掉。追風步沒融意境、修練不了，自己那一份記成絕學只可能是那一版寫的，
    不會碰到自己修練上去的紀錄；絕學定名、江湖史只記修練上去的絕學，也碰不到它。"""
    p = ctx.state.player
    if p.art_quality.get("zhuifeng") == "絕學":
        del p.art_quality["zhuifeng"]


def deliver_renames(ctx) -> None:
    """手上（身上或功法庫）的武學被全服第一個練成絕學的人定了正式的名字，每個人下一次同步補一則江湖紀錄（FB-083）：
    「你手上的【舊名】已由{名號}定名為【新名】。」——絕學定名改的是全服的顯示名字，別人手上那一門也跟著改，不通知的話
    玩家只會看到武學莫名其妙換了名字。一次補到好幾門就合成一則（比照 _deliver_big_events）。

    做法同 _deliver_battle_results：資料庫（全服登記的武學）才是真實來源，改名那一下不去動別人的角色，每個人自己的 Game
    同步時自己補。誰通知過記在自己的 PlayerState.renames_told（武學 id），所以一個人一次改名只通知一次：自己定的名、
    拿到的時候就已經是定過名的（library.store_art）一開始就記成通知過。舊名就是登記時的 id（絕學定名只改顯示的名字，id 不動）。
    名號照登記時記下的那一個（MartialArt.master_shown，沒有就照 masters 表的名號），不另外去查；全服第一個練成的人寫的
    一律是他的名號，匿名行走的人在登記當下記成「某位少俠」，照寫。內容手寫的武學（本命、基礎）不會被改名，也就不會在這裡出現。"""
    p = ctx.state.player
    held = [a for a in library.owned_arts(ctx.state) if a not in p.renames_told and a not in ctx.content.skills]
    if not held:
        return
    renamed = ctx.world.renamed_skill_ids()  # 一次查完這一季改過名的；沒有就不必一門一門去查
    lines = []
    for art_id in held:
        art = ctx.world.get_skill(art_id) if art_id in renamed else None
        if art is None or not is_renamed(art):
            continue
        p.renames_told.append(art_id)
        namer = art.master_shown or ctx.world.master_of(art_id)
        if namer is None or ctx.world.master_of(art_id) == p.name:  # 自己定的名（舊存檔沒記到）：定名那一句已經說過了
            continue
        lines.append(f"你手上的【{art.id}】已由{namer}定名為【{art.name}】。")
    if len(lines) == 1:
        entry = JournalEntry(time=ctx.state.world.time, title=journal.RENAMED, tag=lines[0])
    elif lines:
        entry = JournalEntry(time=ctx.state.world.time, title=journal.RENAMED, tag=f"共 {len(lines)} 則", lines=lines)
    else:
        return
    journal.add_entry(ctx.state, entry)


def seize_chance(ctx, ratio: float) -> list[str]:
    """絕學的契機（方案 C，cultivation.seize）：剛打贏一場難度比 ratio 的仗，身上到了門檻的那一門擲一次頓悟（服務清單二、查詢服務
    `ctx._seize_chance`）。核心的單打服務 Game._seize（打贏了、序章外、照這一場的難度比）與決戰包的收場補送（出手滿幾回合）叫它。"""
    return cultivation.seize(ctx.state, ctx.content, ctx.world, ratio, ctx.rng)


def ascend_view(ctx) -> dict | None:
    """剛破境、還沒看過的破境卡（status_data 的 ascension）；沒有是 None。"""
    return ascend.view(ctx.state)


# ── 修練頁的動作 ──


@not_while_preparing
def cultivate(ctx, art_id: str, use_legend: bool = False) -> list[str]:
    """修練（武學重構，Joy 2026-10-20）：品級不靠修練衝，這裡只剩上品到了極處（第十成）服一枚破境丹強行衝絕學
    （見 cultivation.py）。花體力與一枚丹。真的擲了骰才寫江湖紀錄；被拒絕（還沒到極處、沒有丹、體力不足、沒有這門武學）只回一句話。
    use_legend：玩家按的是「服丹衝關」；沒有就只回「等契機或服丹」那一句。"""
    problem = cultivation.cultivate_problem(ctx.state, ctx.content, ctx.world, art_id, use_legend=use_legend)
    if problem is not None:
        return ctx._log([problem])
    xinde, stamina, pills = ctx._xinde(), ctx.state.player.stamina, ctx.state.player.legend_items
    msgs = cultivation.cultivate(ctx.state, ctx.content, ctx.world, art_id, ctx.rng, use_legend)
    spent = round(stamina - ctx.state.player.stamina)  # 沒衝開也花了體力：數值變化寫在紀錄上，跟別的行動一樣
    taken = pills - ctx.state.player.legend_items
    extra = ([f"體力 -{spent}"] if spent > 0 else []) + (
        [f"{ctx.content.config.legend_item_name} -{taken}"] if taken > 0 else []
    )
    # 結果標記是擲骰的結果（「【X】衝開了…」「【X】撞在…」，一定以【開頭）；前面服丹那一句與後面定名的話都不是
    # 自創的那一門衝開了是「閉門衝關，〔招〕撞開了…【X】破境」（ascend.FORCED_LINE），不以【開頭，另外認
    tag = next((m for m in msgs if m.startswith("【") or m.startswith(ascend.FORCED_LINE.split("〔")[0])), msgs[0])
    msgs = ctx._log(msgs)
    ctx._menxia_entry(tag, xinde, guide=True, action="cultivate", extra=extra or None)
    return msgs


def mastery_request(ctx) -> naming.NamingRequest | None:
    """定名的 A 段（伺服器假人程式在行動鎖內呼叫，見 cultivation.master_request）：只讀。賽季籌備中是 None。"""
    if ctx._preparing():
        return None
    return cultivation.master_request(ctx.state, ctx.content, ctx.world)


@not_while_preparing
def name_mastered(ctx, name: str) -> list[str]:
    """替第一個練成絕學的武學取正式名字；定成了才寫江湖紀錄，江湖史寫進共用賽季所以要存回
    （名字不合格、被用掉、沒有等著取名的武學都只回一句話）。"""
    xinde, pending = ctx._xinde(), ctx.state.player.naming
    msgs = ctx._log(cultivation.name_mastered(ctx.state, ctx.content, ctx.world, name))
    if pending is not None and ctx.state.player.naming is None:
        ctx._menxia_entry(msgs[0], xinde)
        ctx._save_season()
        shown = ctx._art_name(pending)
        annals.note(ctx.state, ctx.content, annals.DEED, f"江湖上第一個把【{pending}】練成絕學的人，定名【{shown}】。", 5)
    return msgs


@not_while_preparing
def switch_art(ctx, art_id: str) -> list[str]:
    """改練：把功法庫裡的一門換上身（見 team.switch_art）。"""
    xinde = ctx._xinde()
    msgs = ctx._log(team.switch_art(ctx.state, ctx.content, ctx.world, art_id))
    # 江湖紀錄的標記是「你改練【…】」那一句；換上後內外搭配變了時最後多一句（FB-088），不拿它當標記
    tag = next((m for m in reversed(msgs) if m.startswith("你改練")), msgs[-1] if msgs else "改練")
    switched = any(m.startswith("你改練") for m in msgs)  # 真的換上了才算序章「比一比，換上或熔掉」那一步（新手引導重做）
    ctx._menxia_entry(tag, xinde, guide=switched, action="switch")
    return msgs


def ascend_request(ctx):
    """破境卡那一句的 A 段（鎖內、只讀）：有一張還沒寫那一句的卡，回請模型寫的單子；沒有是 None。"""
    return ascend.request(ctx.state)


def ascend_line(ctx, req, line: str) -> list[str]:
    """破境卡那一句的 C 段：卡還是同一張才存。"""
    return ascend.set_line(ctx.state, req, line)


def ascend_dismiss(ctx) -> list[str]:
    """看過破境卡了，收掉。"""
    return ascend.dismiss(ctx.state)


@not_while_preparing
def slot_insight(ctx, art_id: str, insight_id: str, index: int | None = None) -> list[str]:
    """把一個意境裝進一門武學的意境槽（武學重構；修練頁與煉製頁都走這裡，MENXIA_ACTIONS["slot"]）：不花心得體力，
    裝成了寫一則「裝意境」江湖紀錄，被拒絕只回一句。"""
    xinde = ctx._xinde()
    ctx.secret_solved = None
    problem = prologue_rules.slot_problem(ctx.state, ctx.content, art_id) or arts_mod.slot_problem(
        ctx.state, ctx.content, ctx.world, art_id, insight_id, index)
    if problem is not None:
        ctx.forged = False
        return ctx._log([problem])
    solved = ctx._solved_secrets()
    msgs = ctx._log(arts_mod.slot(ctx.state, ctx.content, ctx.world, art_id, insight_id, index))
    ctx.forged = True
    ctx.forged_thing = None
    ctx._menxia_entry(msgs[0], xinde, guide=True, action="slot")
    ctx._note_solved(solved)
    return msgs


@not_while_preparing
def unslot_insight(ctx, art_id: str, insight_id: str) -> list[str]:
    """把一個意境從武學的槽上拆下來（MENXIA_ACTIONS["unslot"]）：不花東西；拆成了寫一則江湖紀錄。"""
    xinde = ctx._xinde()
    problem = prologue_rules.slot_problem(ctx.state, ctx.content, art_id)
    if problem is not None:
        return ctx._log([problem])
    slots = ctx.state.player.art_slots.get(art_id, [])
    msgs = ctx._log(arts_mod.unslot(ctx.state, ctx.content, ctx.world, art_id, insight_id))
    if insight_id in slots:
        ctx._menxia_entry(msgs[0], xinde)
    return msgs


@not_while_preparing
def melt_art(ctx, art_id: str) -> list[str]:
    """熔煉：功法庫裡的一門熔成心得（見 library.melt_art）；身上正在練的不能熔。熔成了才寫江湖紀錄，
    被拒絕（身上正在練的、庫裡沒有）只回一句話（武學與成長計畫 F12）。"""
    xinde, held = ctx._xinde(), library.held_count(ctx.state)
    only = prologue_rules.melt_only(ctx.state, ctx.content)  # 序章只准熔師父說的那一門（None＝不限）
    msgs = library.melt_art(ctx.state, ctx.content, ctx.world, art_id, only=only)
    if library.held_count(ctx.state) < held:  # 看有沒有真的少一門，不看心得：下品第一成的武學熔了只退 0 點
        line = prologue_rules.after_line(ctx.state, ctx.content, 心得=ctx._xinde() - xinde)  # 草廬這一步寫了結果那一句（設計 10.3「熔了之後」）就用它（T7 審查 M1）
        if line is not None:
            msgs[0] = line
        relearn = art_view.relearn_note(ctx.state, ctx.content, art_id)  # 基礎武學熔了還能重學：結果最後一句指路（FB-081）
        msgs = ctx._log(msgs + [relearn] if relearn else msgs)
        ctx._menxia_entry(msgs[0], xinde, guide=True, action="melt")  # 序章第 10 步（新手引導計畫一）
        return msgs
    return ctx._log(msgs)


@not_while_preparing
def melt_many(ctx, art_ids: list[str], insight_ids: list[str]) -> list[str]:
    """批量熔煉（見 library.melt_many）：修練頁勾好的武學與意境一次熔完，寫一則江湖紀錄。
    序章裡一門一門照師父說的熔（序章的熔煉是教學的一步），這裡直接回一句。"""
    if prologue_rules.melt_only(ctx.state, ctx.content) is not None or (
        insight_ids and prologue_rules.melt_insight_problem(ctx.state, ctx.content) is not None
    ):
        return ctx._log([MELT_MANY_PROLOGUE])
    xinde, held = ctx._xinde(), library.held_count(ctx.state)
    msgs = ctx._log(library.melt_many(ctx.state, ctx.content, ctx.world, art_ids, insight_ids))
    if library.held_count(ctx.state) < held:
        ctx._menxia_entry(msgs[0], xinde)
    return msgs


@not_while_preparing
def melt_insight(ctx, insight_id: str) -> list[str]:
    """把一個意境化成心得（見 library.melt_insight）；同 melt_art，熔成了才寫江湖紀錄。"""
    refusal = prologue_rules.melt_insight_problem(ctx.state, ctx.content)  # 序章的意境是合成要用的，熔了後面就走不下去
    if refusal is not None:
        return ctx._log([refusal])
    xinde, held = ctx._xinde(), library.held_count(ctx.state)
    msgs = ctx._log(library.melt_insight(ctx.state, ctx.content, ctx.world, insight_id))
    if library.held_count(ctx.state) < held:
        ctx._menxia_entry(msgs[0], xinde)
    return msgs


def practice_refusal(ctx, kind: str) -> str | None:
    """練成這一欄現在做不做得了（序章只准練新得的那一門，prologue.practice_problem）：不能時回寫給玩家看的原因，
    修練頁的練成鈕灰掉、寫它；跟 practice 的拒絕同一個判斷。序章外是 None（心得夠不夠、練滿了沒由網頁照 slot_cards 自己看）。"""
    return prologue_rules.practice_problem(ctx.state, ctx.content, ctx.world, kind)


@not_while_preparing
def practice(ctx, kind: str) -> list[str]:
    """練成：身上這一門加深一成，花心得、累積受傷風險（見 team.practice）。"""
    refusal = prologue_rules.practice_problem(ctx.state, ctx.content, ctx.world, kind)  # 序章只准練新得的那一門
    if refusal is not None:
        return ctx._log([refusal])
    xinde = ctx._xinde()
    member = ctx.state.player.member
    level_slot = "neigong_level" if kind == "內功" else "wugong_level"
    has_art = getattr(member, "neigong_id" if kind == "內功" else "wugong_id") is not None
    before = getattr(member, level_slot)
    msgs = ctx._log(team.practice(
        ctx.state, ctx.content, ctx.world, kind, ctx.rng, safe=prologue_rules.active(ctx.state, ctx.content),
    ))
    # FB-007：引導那一步要的是「真的練了一成」：沒學過就練不到、心得不夠沒練成，都不算；
    # 已經第十成（練無可練）也算（可能在走到這一步前就練滿了，只認「真的加一成」會永遠卡住）。
    counted = has_art and (getattr(member, level_slot) > before or before >= team.MAX_LEVEL)
    if not counted:  # 練不成（還沒學、心得不足）：什麼都沒變，只回那一句話，不寫「修練」紀錄（武學與成長計畫 F12）
        return msgs
    return msgs + ctx._menxia_entry(msgs[0], xinde, guide=True)


# ── 配點與境界卡 ──


@not_while_preparing
def allocate_stat(ctx, stat: str) -> list[str]:
    """把升級得到的屬性點分配到一項（武學與成長設計 6.2）：每項最高 stat_cap，這個版本不能洗點。
    配成了才寫江湖紀錄，連按幾次（玩家、假人都一樣）併成一則「配點」；被拒絕（沒有點、到頂、沒這項屬性）
    只回一句話，不留紀錄（武學與成長計畫 F12）。"""
    p, cfg = ctx.state.player, ctx.content.config
    if attrset.on(ctx.content, ctx.state.world):
        return allocate_v2(ctx, stat)
    name = cfg.stat_names.get(stat, stat)
    if stat not in team.COMBAT_STATS:
        return ctx._log(["（沒有這項屬性。）"])
    if p.stat_points <= 0:
        return ctx._log(["沒有可以分配的屬性點，升級才會有。"])
    if p.stats.get(stat, 0) >= cfg.stat_cap:
        return ctx._log([f"{name}已經到頂（{cfg.stat_cap}）。"])
    seen = jianfa(ctx.content, ctx.state.world, "stat_milestones")  # 減法季屬性五段：配點那一刻寫實際變了多少（設計 4.5「看得見」）
    was = p.stats.get(stat, 0)
    power = team.fresh_power(ctx.state, ctx.content, ctx.world) if seen else 0.0
    p.stat_points -= 1
    p.stats[stat] = p.stats.get(stat, 0) + 1
    said = allocate_line(ctx, stat, was, power) if seen else ""
    if seen and p.stat_points <= 0:
        p.milestone_due = 0  # 境界卡（main.milestone）：配完就收
    journal.add_entry(
        ctx.state, JournalEntry(time=ctx.state.world.time, title=journal.ALLOCATE, changes=[f"{name} +1"],
                                lines=[said] if said else []),
        merge=True,
    )
    left = f"（還有 {p.stat_points} 點可以分配）" if p.stat_points else ""  # 最後一點不寫「還有 0 點」
    ctx._guide(ctx._note_action("allocate"))  # 序章第 9 步（新手引導計畫一）
    ctx._check_hints()  # 博聞加了持有上限會變（h_cap 的條件）：配成了之後看一遍（新手引導計畫三）
    return ctx._log([f"{said or f'{name} +1'}{left}"])


def allocate_v2(ctx, stat: str) -> list[str]:
    """五項屬性的季的配點（attrset）：送的點加到一項（PlayerState.attr_alloc），沒有上限；寫法同舊的配點。（原本 Game._allocate_v2，只有 allocate_stat 叫）"""
    p, c = ctx.state.player, ctx.content
    if stat not in attrset.keys(c):
        return ctx._log(["（沒有這項屬性。）"])
    if p.stat_points <= 0:
        return ctx._log([f"沒有可以分配的屬性點，每 {c.config.attributes.v2.bonus_every} 級送一次。"])
    name = attrset.names(c, ctx.state.world).get(stat, stat)
    p.stat_points -= 1
    p.attr_alloc[stat] = p.attr_alloc.get(stat, 0) + 1
    journal.add_entry(ctx.state, JournalEntry(time=ctx.state.world.time, title=journal.ALLOCATE, changes=[f"{name} +1"]), merge=True)
    left = f"（還有 {p.stat_points} 點可以分配）" if p.stat_points else ""
    ctx._guide(ctx._note_action("allocate"))
    return ctx._log([f"{name} +1{left}"])


def pick_growth(ctx, preset: str, custom: dict | None) -> list[str]:
    """挑成長配比的本體（籌備中、這一季沒有配比、已定這三步留在 Game.pick_growth，Refused 只在 engine）：
    自己配的整理、查問題、定下、寫紀錄。（原本 Game.pick_growth 的後半）"""
    s, c = ctx.state, ctx.content
    custom = {str(k): v for k, v in (custom or {}).items()} if isinstance(custom, dict) else None
    problem = attrset.growth_problem(c, preset, custom)
    if problem:
        return ctx._log([problem])
    line = attrset.pick(s, c, preset, custom)
    journal.add_entry(s, JournalEntry(time=s.world.time, title="成長配比", lines=[line]))  # 一整句：寫成敘事（數值變化的小框放不下，手機上會撐出畫面）
    ctx._guide(ctx._note_action("allocate"))  # 五項屬性的季，序章配點那一步就是挑成長配比（升一級沒有點可配）
    return ctx._log([line])


def allocate_line(ctx, stat: str, was: float, power: float) -> str:
    """配點那一句（減法季屬性五段，設計 4.5）：「臂力 8 → 9：武學威力 +6%，此刻全隊 182 → 193」——前後威力用 team.fresh_power
    （滿血、不看對手）各算一次，沒變（身法、悟性、博聞）就不寫全隊那一段。待 joy 潤。（原本 Game._allocate_line，只有 allocate_stat 叫）"""
    s, c = ctx.state, ctx.content
    name = c.config.stat_names.get(stat, stat)
    after = team.fresh_power(s, c, ctx.world)
    tail = f"，此刻全隊 {power:.0f} → {after:.0f}" if round(after) != round(power) else ""
    return f"{name} {was:.0f} → {was + 1:.0f}：{art_view.stat_step(s, c, stat, was)}{tail}"


def milestone_card(ctx) -> dict | None:
    """境界卡（減法季屬性五段，設計 4.5；欄位表 main.milestone）：升到境界那一級、手上還有點沒配時是
    {"level": 20, "points": 5, "title": "筋骨大成"}；配完了、關著的季是 None。名字照 growth.MILESTONE_TITLES（待 joy 潤）。"""
    s, c = ctx.state, ctx.content
    p = s.player
    if not p.milestone_due or p.stat_points <= 0 or not jianfa(c, s.world, "stat_milestones"):
        return None
    return {"level": p.milestone_due, "points": p.stat_points, "title": growth.milestone_title(p.milestone_due)}


# ── 傳功門下 ──


def chuangong_ready(ctx) -> bool:
    """傳功開著、有傳得起的一門（新手引導碰到才說的 h_chuangong 問，經 Game 一行委派 _chuangong_ready；包不能 import 包）。"""
    return chuangong_rules.on(ctx.content) and chuangong_rules.cheapest(ctx.state, ctx.content, ctx.world) is not None


@not_while_preparing
def chuangong(ctx, key: str, what: str) -> list[str]:
    """傳功門下（Config.chuangong）：用心得替名冊上的同伴或部下練武學、加屬性（chuangong.teach）。
    傳成了寫進江湖紀錄（併進「修練」那一則）；傳不了只回那一句話，不寫紀錄。"""
    xinde = ctx._xinde()
    msgs = ctx._log(chuangong_rules.teach(ctx.state, ctx.content, ctx.world, str(key), str(what)))
    if ctx._xinde() == xinde:  # 沒花到心得：被拒絕了
        return msgs
    return msgs + ctx._menxia_entry(msgs[0], xinde)


def chuangong_lessons(ctx, key: str | None) -> list[dict]:
    """修練頁人物卡底下的傳功鈕（server.menxia_view 的 lessons）：每一項的 what、鈕上的字、效果、按不下去的原因。"""
    return [
        {"what": row.what, "label": row.label, "effect": row.effect, "problem": row.problem}
        for row in chuangong_rules.lessons(ctx.state, ctx.content, ctx.world, key)
    ]


def lesson_options(ctx) -> list[Option]:
    """here/lessons 那一格（core_seams，全部拆包第 56 批；原本在 Game._everyday_options）：拜師學藝（武學與成長設計附錄 B）：不花體力。"""
    s, c = ctx.state, ctx.content
    opts: list[Option] = []
    for skill, problem in library.lessons_here(s, c):
        note = library.lesson_note(skill) if problem is None else problem
        opts.append(Option(id=f"learn:{skill.id}", label=f"學{skill.name}（{note}）", enabled=problem is None))
    return opts
