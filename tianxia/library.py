"""功法庫：持有上限、把新武學放好、在各地學基礎武學、熔煉（武學與成長設計 3.7、4.3、4.5、附錄 B）。

武學與意境合計有上限；滿了就要取捨——熔掉不要的換心得。身上正在練的不能熔（先改練），
免得玩家把唯一的武學熔掉、出城必敗。只改狀態與回傳訊息。
"""
from __future__ import annotations

from . import insights, renown, signature, team
from .martial_arts import QUALITIES, MartialArt, content_art, is_renamed
from .models import Content, SkillDef
from .state import GameState
from .world_state import WorldStateStore

TOWN_TAG = "城鎮"  # 開局送的兩門熔掉之後，任何城鎮都能免費重學（設計 4.3）
TITLE_NEED = "要{title}才肯教"  # 名聲 5.1：正邪武學（待 joy 潤）
LESSON_CLOSED = "這一門現在不教"  # 名聲的 lessons 關著（_taught_here 本來就不列；直接叫 learn_problem 時才看得到）


def owned_arts(state: GameState) -> list[str]:
    """擁有的武學：身上的（內功、武學）在前，再來是功法庫。"""
    member = state.player.member
    return [a for a in (member.neigong_id, member.wugong_id) if a] + list(state.player.arts)


def level_of(state: GameState, art_id: str) -> int | None:
    """擁有的一門武學練到第幾成：配在身上的看身上那一欄，功法庫裡的看換下來時存的（沒存過從第一成算，
    跟 team.switch_art 一致）；不是自己的是 None。修練頁的資料列與功法卡共用這一份。"""
    member = state.player.member
    if art_id == member.neigong_id:
        return member.neigong_level
    if art_id == member.wugong_id:
        return member.wugong_level
    if art_id in state.player.arts:
        return state.player.art_levels.get(art_id, 1)
    return None


def held_count(state: GameState) -> int:
    return len(owned_arts(state)) + len(state.player.insights)


def holding_cap(content: Content, level: int, lore: float) -> int:
    """武學與意境合計最多幾個（設計 4.5、6.3）：基本 50，每升 5 級多 3 格，博聞比基準（5）每多一點多 2 格；
    博聞少於基準不扣格（被事件扣了也不會比基本加等級的少）。"""
    cfg = content.config
    from_lore = max(0, int(lore) - team.BASE_STAT) * cfg.holding_per_lore_point
    return cfg.holding_cap_base + (level // cfg.holding_cap_levels) * cfg.holding_cap_step + from_lore


def cap_of(state: GameState, content: Content) -> int:
    """這個人現在的持有上限：照自己的等級與博聞。"""
    p = state.player
    return holding_cap(content, p.member.level, p.stats.get(team.LORE, team.BASE_STAT))


def full(state: GameState, content: Content) -> bool:
    """滿了（或超過）：不能再合成、合併、學新的武學。悟意境不受限（設計 4.5：不然奇遇給的稀有意境會直接消失）。
    博聞掉下來之後持有可能超過上限：照樣算滿，熔回上限以內之前不能合成、合併。"""
    return held_count(state) >= cap_of(state, content)


SWITCH_HINT = "到「修練」的功法庫把它改練上身。"  # 合成的結果最後一句（W5，fusion._store_forged 用）：「收進功法庫」之後告訴玩家功法庫在哪、怎麼穿上；待 joy 潤


def store_art(state: GameState, art: MartialArt, quality: str | None = None) -> list[str]:
    """新拿到的武學放哪：對應的欄位空著就配上身（第一成），否則進功法庫。quality 是玩家這一份的品質
    （武學＋武學合出來的照兩門來源算，fusion.blend_grade）：跟全服登記的不一樣時記成自己那一份的品質。
    這裡不看上限：該不該擋住由呼叫端決定（合成、學藝擋，奇遇給的、買來的不擋）。"""
    p = state.player
    if art.id in owned_arts(state):  # 已經有了（配在身上或在庫裡）：不重複收，也不動它的品質與熟練度
        return []
    if is_renamed(art) and art.id not in p.renames_told:  # 拿到時就已經是定過名的：看到的就是新名，之後不必通知「改名了」（FB-083）
        p.renames_told.append(art.id)
    if quality is not None and quality != art.quality:
        p.art_quality[art.id] = quality
    slot = "neigong_id" if art.kind == "內功" else "wugong_id"
    if getattr(p.member, slot) is None:
        setattr(p.member, slot, art.id)
        setattr(p.member, slot.replace("_id", "_level"), 1)
        return [f"你當場就把【{art.name}】練到了第一成。"]
    if art.id not in p.arts:
        p.arts.append(art.id)
    return [f"【{art.name}】收進功法庫。"]


# ── 在各地學基礎武學（附錄 B）──────────────────────────────


def _taught_here(state: GameState, content: Content) -> list[SkillDef]:
    """這裡教的：寫了 learn.at 是這裡的，城鎮再加開局送的兩門。正邪武學（learn.title，名聲 5.1）在名聲的 lessons 關著時不教。"""
    here = content.locations[state.player.location]
    starters = set(content.config.starter_skills) if TOWN_TAG in here.tags else set()
    lessons = renown.on(content, "lessons")
    return [
        skill for skill in content.skills.values()
        if (skill.learn is not None and skill.learn.at == here.id and (lessons or skill.learn.title is None)) or skill.id in starters
    ]


def learn_problem(state: GameState, content: Content, skill: SkillDef) -> str | None:
    """學不了的原因；None＝可以學。開局送的兩門在城鎮重學不看條件、不收錢。"""
    p = state.player
    rule = skill.learn
    if rule is not None:
        if rule.faction and p.faction != rule.faction:
            name = content.scenario.faction_name(rule.faction, rule.faction)
            return f"只教投靠{name}的人"
        if rule.sect and p.sect != rule.sect:
            return f"只教{content.sects[rule.sect].name}的弟子"
        if rule.title is not None:  # 名聲 5.1：正邪武學看善惡稱號（走那條路、到那一段）
            if not renown.on(content, "lessons"):
                return LESSON_CLOSED
            if not renown.meets(state, content, rule.title.path, rule.title.tier):
                return TITLE_NEED.format(title=renown.named(renown.VIRTUE_TITLES[rule.title.path][rule.title.tier], state))
        need = int(rule.fame * renown.scale(state.world) + 0.5)  # 名聲 2.4：拜師的名望門檻跟求見同一個理由乘季長倍數
        if p.stats.get("fame", 0) < need:
            return f"名望 {need} 以上才肯教"
        if p.stats.get("silver", 0) < rule.silver:
            return f"學費 {rule.silver} 兩，你只有 {p.stats.get('silver', 0)} 兩"
    if full(state, content):
        return "武學與意境已經滿了，先熔掉一些"
    return None


def lesson_note(skill: SkillDef) -> str:
    """選單上「學〇〇」括號裡的說明；正邪武學多寫正派、邪派（名聲 5.1）。"""
    fee = skill.learn.silver if skill.learn is not None else 0
    lean = f"{skill.lean}派・" if skill.lean != "無" else ""
    return f"{skill.kind}・下品・屬{skill.attribute}・{lean}" + (f"銀兩 {fee}" if fee else "免費")


def lessons_here(state: GameState, content: Content) -> list[tuple[SkillDef, str | None]]:
    """這個地點教、而且自己還沒會的基礎武學，連同學不了的原因（None＝可以學）。"""
    owned = set(owned_arts(state))
    return [(skill, learn_problem(state, content, skill)) for skill in _taught_here(state, content) if skill.id not in owned]


def learn(state: GameState, content: Content, skill_id: str) -> list[str]:
    skill = content.skills.get(skill_id)
    if skill is None or skill not in _taught_here(state, content) or skill_id in owned_arts(state):
        return ["這裡沒有人教這一門。"]
    problem = learn_problem(state, content, skill)
    if problem is not None:
        return [f"學不了【{skill.name}】：{problem}。"]
    fee = skill.learn.silver if skill.learn is not None else 0
    state.player.stats["silver"] = state.player.stats.get("silver", 0) - fee
    msgs = [f"你學會了【{skill.name}】（{skill.kind}・下品・屬{skill.attribute}）。"] + ([f"銀兩 -{fee}"] if fee else [])
    return msgs + store_art(state, content_art(skill.id, skill.name, skill.kind, skill.attribute, skill.quality, lean=skill.lean, affinity=skill.affinity))


# ── 熔煉（設計 4.3）──────────────────────────────────────


def melt_refund(
    content: Content, level: int, quality: str, registered: str = "下品", minimum: int = 0, free_below: int = 1,
) -> int:
    """熔一門練到第 level 成、玩家自己這一份品質是 quality 的武學退多少心得：
    max(minimum, 練成花的八成) ＋ 品質加給。

    品質加給只算玩家自己修練上去的那幾階（企劃者 2026-10-05，改了設計 4.3）：加給（quality）減去
    登記時就有的那一階的加給（registered，全服共享、沒個人化的那一份的品質），不低於 0。
    合成的武學登記在下品，所以修練到上品照領上品的加給；內容裡直接給的絕學（情誼送的本命武學、劇情教的）
    登記就是絕學、沒修練過，熔了沒有加給——不然「合一門、熔一門」就是個無本的金錢迴圈。
    minimum 是 FB-068 的基本值（Config.melt_min_refund，只給合成出來的武學，見 melt_value），墊在練成那一份底下，不另外加。
    free_below 是學到時就有的成數：本命武學學到時直接第七成（Config.signature_arts.start_level），那幾成沒花心得，熔了不退
    （不然一學到就熔，白拿 33 點心得）。"""
    cfg = content.config
    spent = sum(team.practice_price(content, n) for n in range(max(1, free_below), level))
    bonus = max(0, cfg.melt_quality_bonus.get(quality, 0) - cfg.melt_quality_bonus.get(registered, 0))
    return max(minimum, int(spent * cfg.melt_refund_ratio)) + bonus


SIGNATURE_KEPT = "本命武學是那位人物親傳的，熔不得。"  # Joy 2026-10-16「本命應該要不能熔掉」


def melt_problem(
    state: GameState, art_id: str, name: str | None = None, only: str | None = None, content: Content | None = None,
) -> str | None:
    """熔不掉的原因；None＝可以熔。熔煉鈕亮不亮（skillview.art_rows）與 melt_art 的拒絕走同一個判斷，
    兩邊才不會各說各話。name 是這門武學現在的名字（寫進「先替它定名」那一句；不給就寫「這一門」）。
    only：序章（新手引導計畫一）只准熔師父說的那一門，空字串是這一步一門都不准熔；None＝不限。
    由呼叫端查序章再傳進來（prologue 會 import rules、rules 會 import 這個模組，這裡不能反過來 import 它）。
    content 給了才認得本命武學（signature.is_signature）：本命熔不得（Joy 2026-10-16），拿去當底合成照舊可以。"""
    if only is not None and art_id != only:
        return "師父沒叫你熔這一門。"
    p = state.player
    if art_id in (p.member.neigong_id, p.member.wugong_id):
        return "身上正在練的不能熔，先改練別的。"
    if art_id not in p.arts:
        return "你的功法庫裡沒有這一門。"
    if content is not None and signature.is_signature(content, art_id):
        return SIGNATURE_KEPT
    if art_id == p.naming:
        # 練成絕學、等著定名的那門：熔了，讀檔清理會把取名權（p.naming）丟掉，而全服的第一人登記還在，
        # 那門就永遠沒有人替它定名
        return f"【{name or '這一門'}】是你練成絕學、還等著定名的武學——先替它定名，再談熔掉。"
    return None


def melt_value(state: GameState, content: Content, world: WorldStateStore, art_id: str) -> int:
    """熔掉功法庫裡的 art_id 會退多少心得。熔煉頁寫的「退回心得 N」（skillview.art_rows）與 melt_art 真的退的
    共用這一個數：武學重構之後品級不靠修練衝，所以只退練成花的八成；品質加給只剩全服登記的那一階之上（絕學契機那一階）。
    FB-068 的基本值（Config.melt_min_refund）只給全服登記的武學（合成出來的；art_id 不是內容裡的武學）：
    內容裡的基礎武學有的免費教、學藝也不花體力，給了基本值就是「學、熔、再學」的無本迴圈。"""
    mine = team.player_art(state, content, world, art_id)
    registered = team.resolve_art(art_id, content, world)
    minimum = 0 if art_id in content.skills else content.config.melt_min_refund
    start = registered.quality if registered else "下品"
    grade = state.player.art_quality.get(art_id)  # 合出來的品級是兩門來源帶來的、不是修練上去的：不給加給
    if grade in QUALITIES and QUALITIES.index(grade) > QUALITIES.index(start) and grade != "絕學":
        start = grade
    free = content.config.signature_arts.start_level if signature.is_signature(content, art_id) else 1
    return melt_refund(
        content, state.player.art_levels.get(art_id, 1), mine.quality if mine else "下品", start, minimum, free,
    )


MELT_NO_XINDE = "沒有心得，只空出一格"  # 熔煉那一行與確認框用：退 0 心得的熔煉其實只是空出一格（W9，待 joy 潤）


def melt_note(value: int) -> str:
    """功法卡那一行「熔煉：…」：熔了退多少心得；退 0 時直說沒有心得、只空出一格（熔掉仍空出一格，所以照樣准熔，不騙人說退了什麼）。"""
    return f"退回心得 {value}" if value > 0 else MELT_NO_XINDE


def melt_confirm(name: str, value: int, relearn: str | None = None) -> str:
    """熔煉鈕按下去的確認框，整句只在這裡寫（W9 與 FB-081 合成一句，待 joy 潤）：有心得的寫退多少；退 0 心得的直說只空出一格
    （熔掉仍空出一格，所以照樣准熔，不騙人說退了什麼）。relearn 是 skillview.relearn_note 給的「熔了去哪裡再學」那一句
    （開局送的基礎武學在城鎮免費重學、各地教的回教它的地方；合成的與內容直接給的沒有），有就接在後面，所以「免費重學」只說一次；
    有心得又沒有重學的地方才說「熔掉就沒了」。"""
    if value > 0:
        return f"把【{name}】熔成心得？退回心得 {value}。{relearn or '熔掉就沒了。'}"
    return f"把【{name}】熔掉？這門熔了沒有心得，只空出一格。{relearn or ''}"


def remove_art(state: GameState, art_id: str) -> None:
    """功法庫拿掉一門，連同 PlayerState 以功法 id 為鍵的全部私有紀錄（成、自己那一份的品質、熟練度）；槽裡的意境拆回背包。
    熔煉（melt_art）與交出懸賞（bounties.give，懸賞榜設計 4.6）共用；呼叫端先擋（身上的、等著定名的）。全服登記的那一門不動。"""
    from . import arts as arts_mod

    p = state.player
    p.arts.remove(art_id)
    arts_mod.release_all(state, art_id)
    for record in (p.art_levels, p.art_quality, p.art_mastery):
        record.pop(art_id, None)


def melt_art(
    state: GameState, content: Content, world: WorldStateStore, art_id: str, only: str | None = None,
) -> list[str]:
    p = state.player
    art = team.player_art(state, content, world, art_id)
    problem = melt_problem(state, art_id, art.name if art else art_id, only=only, content=content)
    if problem is not None:
        return [problem]
    refund = melt_value(state, content, world, art_id)
    remove_art(state, art_id)
    p.stats["xinde"] = p.stats.get("xinde", 0) + refund
    name = art.name if art else art_id
    if refund <= 0:  # 退 0 心得（第一成的內容武學）：不寫「熔成了心得。心得 +0」，只說空出一格（W9，待 joy 潤）
        return [f"你把【{name}】熔掉了，空出一格。"]
    return [f"你把【{name}】熔成了心得。", f"心得 +{refund}"]


MELT_MANY_MAX = 120  # 一次最多熔幾樣（持有上限一季最多 88 格，留一點餘地；多送的當沒送）
MELT_MANY_NONE = "沒有勾選要熔的功法。"
MELT_MANY_NOTHING = "一樣都沒熔成。"
MELT_MANY_SHOWN = 6  # 結果那一句最多點幾個名字，其餘寫「等 N 樣」
MELT_MANY_SKIPS = 3  # 熔不掉的最多列幾句原因


def melt_many(
    state: GameState, content: Content, world: WorldStateStore, art_ids: list[str], insight_ids: list[str],
) -> list[str]:
    """批量熔煉（企劃者 2026-10-14「合成越來越多，需要能快速熔煉的機制」）：功法庫裡勾的武學與意境一次熔完。
    每一門照 melt_problem／melt_value 跟一門一門熔一樣算（擋的、退的心得一模一樣），意境照 melt_insight 的價錢；
    熔不掉的跳過、寫原因。結果合成一則：熔了幾樣、點名、心得合計、熔掉意境之後不能再修練的那幾門。
    序章由呼叫端擋（Game.melt_many），這裡不看。"""
    p = state.player
    arts = list(dict.fromkeys(a for a in art_ids if a))[:MELT_MANY_MAX]
    ins = list(dict.fromkeys(i for i in insight_ids if i))[: max(0, MELT_MANY_MAX - len(arts))]
    if not arts and not ins:
        return [MELT_MANY_NONE]
    melted: list[str] = []
    skipped: list[str] = []
    refund = 0
    art_count = 0
    for art_id in arts:
        art = team.player_art(state, content, world, art_id)
        name = art.name if art else art_id
        problem = melt_problem(state, art_id, name, content=content)
        if problem is not None:
            skipped.append(f"【{name}】沒熔：{problem}")
            continue
        refund += melt_value(state, content, world, art_id)
        remove_art(state, art_id)
        melted.append(f"【{name}】")
        art_count += 1
    insight_count = 0
    for insight_id in ins:
        if insight_id not in p.insights:
            skipped.append(f"「{insight_id}」沒熔：你沒有這個意境。")
            continue
        insight = insights.resolve(insight_id, content, world, state)
        stuck = melt_insight_problem(state, content, world, insight_id)
        if stuck is not None:
            skipped.append(f"「{insight.name if insight else insight_id}」沒熔：{stuck}")
            continue
        p.insights.remove(insight_id)
        refund += content.config.melt_insight_xinde
        melted.append(f"「{insight.name if insight else insight_id}」")
        insight_count += 1
    if not melted:
        return [MELT_MANY_NOTHING, *skipped[:MELT_MANY_SKIPS]]
    p.stats["xinde"] = p.stats.get("xinde", 0) + refund
    parts = [f"{art_count} 門武學" if art_count else "", f"{insight_count} 個意境" if insight_count else ""]
    names = "".join(melted[:MELT_MANY_SHOWN]) + (f"等 {len(melted)} 樣" if len(melted) > MELT_MANY_SHOWN else "")
    msgs = [f"你一口氣熔掉了 {'、'.join(x for x in parts if x)}：{names}。"]
    if refund > 0:
        msgs.append(f"心得 +{refund}")
    msgs += skipped[:MELT_MANY_SKIPS]
    if len(skipped) > MELT_MANY_SKIPS:
        msgs.append(f"還有 {len(skipped) - MELT_MANY_SKIPS} 樣沒熔。")
    return msgs


INSIGHT_SLOTTED = "「{name}」還裝在【{art}】上，先拆下來。"  # 待 joy 潤


def melt_insight_problem(state: GameState, content: Content, world: WorldStateStore, insight_id: str) -> str | None:
    """這個意境熔不熔得掉：不是自己的、或還裝在某一門武學的意境槽上（武學重構）都不行。None＝可以。"""
    from . import arts as arts_mod  # arts import library

    if insight_id not in state.player.insights:
        return "你沒有這個意境。"
    where = arts_mod.where_slotted(state, insight_id)
    if where is not None:
        insight = insights.resolve(insight_id, content, world, state)
        art = team.resolve_art(where, content, world)
        return INSIGHT_SLOTTED.format(name=insight.name if insight else insight_id, art=art.name if art else where)
    return None


def melt_insight(state: GameState, content: Content, world: WorldStateStore, insight_id: str) -> list[str]:
    p = state.player
    problem = melt_insight_problem(state, content, world, insight_id)
    if problem is not None:
        return [problem]
    insight = insights.resolve(insight_id, content, world, state)
    p.insights.remove(insight_id)
    amount = content.config.melt_insight_xinde
    p.stats["xinde"] = p.stats.get("xinde", 0) + amount
    name = insight.name if insight else insight_id
    return [f"你把「{name}」的領悟化成了心得。", f"心得 +{amount}"]
