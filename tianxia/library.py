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


def holding_cap(content: Content, level: int) -> int:
    """武學與意境合計最多幾個：基本 50，每升 5 級多 5 格（設計 4.5）。"""
    cfg = content.config
    return cfg.holding_cap_base + (level // cfg.holding_cap_levels) * cfg.holding_cap_step


def full(state: GameState, content: Content) -> bool:
    """滿了（或超過）：不能再合成、合併、學新的武學。悟意境不受限（設計 4.5：不然奇遇給的稀有意境會直接消失）。"""
    return held_count(state) >= holding_cap(content, state.player.member.level)


def store_art(state: GameState, art: MartialArt, quality: str | None = None) -> list[str]:
    """新拿到的武學放哪：對應的欄位空著就配上身（第一成），否則進功法庫。quality 是玩家這一份的品質
    （跟全服登記的不一樣時才記）。這裡不看上限：該不該擋住由呼叫端決定（合成、學藝擋，奇遇給的、買來的不擋）。"""
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


def melt_refund(content: Content, level: int, quality: str) -> int:
    """熔一門練到第 level 成、品質 quality 的武學退多少心得：練成花的八成＋品質加給。"""
    cfg = content.config
    spent = sum(team.practice_price(content, n) for n in range(1, level))
    return int(spent * cfg.melt_refund_ratio) + cfg.melt_quality_bonus.get(quality, 0)


def melt_problem(state: GameState, art_id: str, name: str | None = None) -> str | None:
    """熔不掉的原因；None＝可以熔。熔煉鈕亮不亮（skillview.art_rows）與 melt_art 的拒絕走同一個判斷，
    兩邊才不會各說各話。name 是這門武學現在的名字（寫進「先替它定名」那一句；不給就寫「這一門」）。"""
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


def melt_art(state: GameState, content: Content, world: WorldStateStore, art_id: str) -> list[str]:
    p = state.player
    art = team.player_art(state, content, world, art_id)
    problem = melt_problem(state, art_id, art.name if art else art_id)
    if problem is not None:
        return [problem]
    level = p.art_levels.get(art_id, 1)
    refund = melt_refund(content, level, art.quality if art else "下品")
    p.arts.remove(art_id)
    for record in (p.art_levels, p.art_quality, p.art_mastery):
        record.pop(art_id, None)
    p.stats["xinde"] = p.stats.get("xinde", 0) + refund
    return [f"你把【{art.name if art else art_id}】熔成了心得。", f"心得 +{refund}"]


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
