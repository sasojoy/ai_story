"""功法庫：持有上限、把新武學放好、在各地學基礎武學、熔煉（武學與成長設計 3.7、4.3、4.5、附錄 B）。

武學與意境合計有上限；滿了就要取捨——熔掉不要的換心得。身上正在練的不能熔（先改練），
免得玩家把唯一的武學熔掉、出城必敗。只改狀態與回傳訊息。
"""
from __future__ import annotations

from . import insights, team
from .martial_arts import MartialArt, content_art
from .models import Content, SkillDef
from .state import GameState
from .world_state import WorldStateStore

TOWN_TAG = "城鎮"  # 開局送的兩門熔掉之後，任何城鎮都能免費重學（設計 4.3）


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


SWITCH_HINT = "到「修練」的功法庫把它改練上身。"  # 合成的結果最後一句（W5）：「收進功法庫」之後告訴玩家功法庫在哪、怎麼穿上；待 joy 潤


def store_forged(state: GameState, art: MartialArt) -> list[str]:
    """合成出來的新武學放哪（fusion.fuse、fusion.blend）：同 store_art；進了功法庫（沒有直接上身）的，再多一句指路——
    結果說「收進功法庫」，修練頁的清單也叫「功法庫」，這句把兩邊接起來。學藝、事件教的武學不走這裡，不加這句。"""
    stored = store_art(state, art)
    return stored + [SWITCH_HINT] if stored and art.id in state.player.arts else stored


def store_art(state: GameState, art: MartialArt, quality: str | None = None) -> list[str]:
    """新拿到的武學放哪：對應的欄位空著就配上身（第一成），否則進功法庫。quality 是玩家這一份的品質
    （跟全服登記的不一樣時才記；現在沒有呼叫端給它——合成也從登記的下品起修）。
    這裡不看上限：該不該擋住由呼叫端決定（合成、學藝擋，奇遇給的、買來的不擋）。"""
    p = state.player
    if art.id in owned_arts(state):  # 已經有了（配在身上或在庫裡）：不重複收，也不動它的品質與熟練度
        return []
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
    here = content.locations[state.player.location]
    starters = set(content.config.starter_skills) if TOWN_TAG in here.tags else set()
    return [
        skill for skill in content.skills.values()
        if (skill.learn is not None and skill.learn.at == here.id) or skill.id in starters
    ]


def learn_problem(state: GameState, content: Content, skill: SkillDef) -> str | None:
    """學不了的原因；None＝可以學。開局送的兩門在城鎮重學不看條件、不收錢。"""
    p = state.player
    rule = skill.learn
    if rule is not None:
        if rule.faction and p.faction != rule.faction:
            name = next((f.name for f in content.scenario.factions if f.id == rule.faction), rule.faction)
            return f"只教投靠{name}的人"
        if rule.sect and p.sect != rule.sect:
            return f"只教{content.sects[rule.sect].name}的弟子"
        if p.stats.get("fame", 0) < rule.fame:
            return f"名望 {rule.fame} 以上才肯教"
        if p.stats.get("silver", 0) < rule.silver:
            return f"學費 {rule.silver} 兩，你只有 {p.stats.get('silver', 0)} 兩"
    if full(state, content):
        return "武學與意境已經滿了，先熔掉一些"
    return None


def lesson_note(skill: SkillDef) -> str:
    """選單上「學〇〇」括號裡的說明。"""
    fee = skill.learn.silver if skill.learn is not None else 0
    return f"{skill.kind}・下品・屬{skill.attribute}・" + (f"銀兩 {fee}" if fee else "免費")


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
    return msgs + store_art(state, content_art(skill.id, skill.name, skill.kind, skill.attribute, skill.quality))


# ── 熔煉（設計 4.3）──────────────────────────────────────


def melt_refund(content: Content, level: int, quality: str, registered: str = "下品", minimum: int = 0) -> int:
    """熔一門練到第 level 成、玩家自己這一份品質是 quality 的武學退多少心得：
    max(minimum, 練成花的八成) ＋ 品質加給。

    品質加給只算玩家自己修練上去的那幾階（企劃者 2026-10-05，改了設計 4.3）：加給（quality）減去
    登記時就有的那一階的加給（registered，全服共享、沒個人化的那一份的品質），不低於 0。
    合成的武學登記在下品，所以修練到上品照領上品的加給；內容裡直接給的絕學（情誼送的本命武學、劇情教的）
    登記就是絕學、沒修練過，熔了沒有加給——不然「合一門、熔一門」就是個無本的金錢迴圈。
    minimum 是 FB-068 的基本值（Config.melt_min_refund，只給合成出來的武學，見 melt_value），墊在練成那一份底下，不另外加。"""
    cfg = content.config
    spent = sum(team.practice_price(content, n) for n in range(1, level))
    bonus = max(0, cfg.melt_quality_bonus.get(quality, 0) - cfg.melt_quality_bonus.get(registered, 0))
    return max(minimum, int(spent * cfg.melt_refund_ratio)) + bonus


def melt_problem(state: GameState, art_id: str, name: str | None = None, only: str | None = None) -> str | None:
    """熔不掉的原因；None＝可以熔。熔煉鈕亮不亮（skillview.art_rows）與 melt_art 的拒絕走同一個判斷，
    兩邊才不會各說各話。name 是這門武學現在的名字（寫進「先替它定名」那一句；不給就寫「這一門」）。
    only：序章（新手引導計畫一）只准熔師父說的那一門，空字串是這一步一門都不准熔；None＝不限。
    由呼叫端查序章再傳進來（prologue 會 import rules、rules 會 import 這個模組，這裡不能反過來 import 它）。"""
    if only is not None and art_id != only:
        return "師父沒叫你熔這一門。"
    p = state.player
    if art_id in (p.member.neigong_id, p.member.wugong_id):
        return "身上正在練的不能熔，先改練別的。"
    if art_id not in p.arts:
        return "你的功法庫裡沒有這一門。"
    if art_id == p.naming:
        # 練成絕學、等著定名的那門：熔了，讀檔清理會把取名權（p.naming）丟掉，而全服的第一人登記還在，
        # 那門就永遠沒有人替它定名
        return f"【{name or '這一門'}】是你練成絕學、還等著定名的武學——先替它定名，再談熔掉。"
    return None


def melt_value(state: GameState, content: Content, world: WorldStateStore, art_id: str) -> int:
    """熔掉功法庫裡的 art_id 會退多少心得。熔煉頁寫的「退回心得 N」（skillview.art_rows）與 melt_art 真的退的
    共用這一個數：玩家自己那一份的品質跟全服登記的那一份（沒個人化）比，只有修練上去的幾階有加給。
    FB-068 的基本值（Config.melt_min_refund）只給全服登記的武學（合成出來的；art_id 不是內容裡的武學）：
    內容裡的基礎武學有的免費教、學藝也不花體力，給了基本值就是「學、熔、再學」的無本迴圈。"""
    mine = team.player_art(state, content, world, art_id)
    registered = team.resolve_art(art_id, content, world)
    minimum = 0 if art_id in content.skills else content.config.melt_min_refund
    return melt_refund(
        content, state.player.art_levels.get(art_id, 1),
        mine.quality if mine else "下品", registered.quality if registered else "下品", minimum,
    )


MELT_NO_XINDE = "沒有心得，只空出一格"  # 熔煉那一行與確認框用：退 0 心得的熔煉其實只是空出一格（W9，待 joy 潤）


def melt_note(value: int) -> str:
    """功法卡那一行「熔煉：…」：熔了退多少心得；退 0 時直說沒有心得、只空出一格（熔掉仍空出一格，所以照樣准熔，不騙人說退了什麼）。"""
    return f"退回心得 {value}" if value > 0 else MELT_NO_XINDE


def melt_confirm(content: Content, name: str, art_id: str, value: int) -> str:
    """熔煉鈕按下去的確認框。退 0 心得時照實說（W9，待 joy 潤）；開局送的基礎武學在城鎮免費重學（_taught_here），
    所以只有它們才多這一句——別的武學不免費，不能這樣寫。"""
    if value > 0:
        return f"把【{name}】熔成心得？熔掉就沒了。"
    again = "（基礎武學在城鎮可以免費重學）" if art_id in content.config.starter_skills else ""
    return f"把【{name}】熔掉？這門熔了沒有心得，只空出一格{again}。"


def melt_art(
    state: GameState, content: Content, world: WorldStateStore, art_id: str, only: str | None = None,
) -> list[str]:
    p = state.player
    art = team.player_art(state, content, world, art_id)
    problem = melt_problem(state, art_id, art.name if art else art_id, only=only)
    if problem is not None:
        return [problem]
    refund = melt_value(state, content, world, art_id)
    p.arts.remove(art_id)
    for record in (p.art_levels, p.art_quality, p.art_mastery):
        record.pop(art_id, None)
    p.stats["xinde"] = p.stats.get("xinde", 0) + refund
    name = art.name if art else art_id
    if refund <= 0:  # 退 0 心得（第一成的內容武學）：不寫「熔成了心得。心得 +0」，只說空出一格（W9，待 joy 潤）
        return [f"你把【{name}】熔掉了，空出一格。"]
    return [f"你把【{name}】熔成了心得。", f"心得 +{refund}"]


def melt_insight(state: GameState, content: Content, world: WorldStateStore, insight_id: str) -> list[str]:
    p = state.player
    if insight_id not in p.insights:
        return ["你沒有這個意境。"]
    insight = insights.resolve(insight_id, content, world)
    p.insights.remove(insight_id)
    amount = content.config.melt_insight_xinde
    p.stats["xinde"] = p.stats.get("xinde", 0) + amount
    name = insight.name if insight else insight_id
    msgs = [f"你把「{name}」的領悟化成了心得。", f"心得 +{amount}"]
    needing = [
        art.name for art in (team.resolve_art(a, content, world) for a in owned_arts(state))
        if art is not None and art.insight == insight_id
    ]
    if needing:
        msgs.append(f"{'、'.join(f'【{n}】' for n in needing)}從此不能再修練（修練要用「{name}」）。")
    return msgs
