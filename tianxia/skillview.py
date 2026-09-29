"""門下頁面的說明文字：把武學效果翻成白話、列出人物數值，讓玩家看得出每門武學的差別。

只讀狀態與內容、只產生文字，不改任何東西。數字一律經 team.skill_value 依成數計算，
和戰鬥用的是同一套；何時發動、誰擋得住的說法以 battle.py 的實際規則為準。
"""
from __future__ import annotations

from . import team
from .battle import ADVANTAGE, BEATS, STAT_NAMES
from .models import Content, Skill, SkillEffect
from .state import PLAYER, GameState

HINT = "（點選上方的武學欄，或左邊武學庫裡的一門武學，這裡會說明它怎麼運作。）"
QUALITY_NAMES = {"下": "下品", "中": "中品", "上": "上品"}
CONTROL_NOTES = {"點穴": "整回合不能行動", "卸兵": "不能普攻，也不會連招", "封脈": "發不出絕招"}
STAT_NOTES = {("spd", "buff"): "（出手更早）", ("spd", "debuff"): "（出手更晚）"}
GROUP_WORDS = {"enemies": "全體", "allies": "全隊"}  # 武學庫短句裡的群體前綴
TARGET_WORDS = {"enemies": "所有敵人", "self": "自身", "ally_lowest": "內力比例最低的隊友", "allies": "全隊"}
LASTING_KINDS = ("buff", "debuff", "control", "dodge", "reduce")
CHINESE_DIGITS = "零一二三四五六七八九十"

KIND_RULES = {
    "心法": "開戰前（第一回合之前）自動運起，效果持續整場；不看機率，點穴、封脈也擋不住。",
    "絕招": (
        "輪到自己出手時先擲發動率，擲中就施展，施展完照常普攻；單體效果都落在同一名敵人身上。"
        "每回合最多發一門絕招（本命先擲，再依自選欄順序）。被封脈時發不出絕招，被點穴時整回合不能行動。"
    ),
    "連招": (
        "每次普攻之後擲發動率（普攻被閃開也照擲），擲中就順勢出招，單體效果打在普攻的同一個目標上；"
        "多門連招各擲各的。被卸兵時不能普攻，也就不會連招；被點穴時整回合不能行動。"
    ),
}


def when_text(skill: Skill) -> str:
    """何時發動；要蓄勢的絕招多說明蓄勢怎麼算。"""
    text = KIND_RULES[skill.kind]
    if skill.prep > 0:
        text += (
            f"這門絕招擲中時先蓄勢，再過 {skill.prep} 個自己的回合才施展"
            "（被封脈、點穴的回合不算；蓄勢期間照常普攻，不擲其他絕招）。"
        )
    return text


# ── 效果與摘要 ─────────────────────────────────────────


def _pct(value: float) -> int:
    return round(value * 100)


def _who(effect: SkillEffect, kind: str) -> str:
    """效果落在誰身上。絕招的單體效果落在同一名敵人身上，連招的落在普攻的目標上。"""
    if effect.target != "enemy":
        return TARGET_WORDS[effect.target]
    if effect.kind == "damage":
        return "普攻的目標" if kind == "連招" else "一名敵人"
    return "一名敵人" if kind == "心法" else "目標"


def _name(effect: SkillEffect, kind: str) -> str:
    """效果叫什麼：傷害／追加傷害、回復內力、封脈、攻擊提升、閃避、減傷……"""
    if effect.kind == "damage":
        return "追加傷害" if kind == "連招" else "傷害"
    if effect.kind == "heal":
        return "回復內力"
    if effect.kind == "control":
        return effect.control
    if effect.kind in ("buff", "debuff"):
        return STAT_NAMES[effect.stat] + ("提升" if effect.kind == "buff" else "降低")
    return "閃避" if effect.kind == "dodge" else "減傷"


def effect_label(effect: SkillEffect, kind: str) -> str:
    """效果表的列名：是什麼、落在誰身上、持續多久；不含數字（數字在旁邊的成數欄）。kind 是武學類型。"""
    who = _who(effect, kind)
    if effect.kind in ("damage", "heal"):
        return f"{_name(effect, kind)}・{who}"
    lasting = "整場" if kind == "心法" else f"{effect.rounds} 回合"
    if effect.kind == "control":
        parts = [f"{effect.control}命中率"] + ([] if who == "目標" else [who]) + [lasting]
        return "・".join(parts) + f"（{CONTROL_NOTES[effect.control]}）"
    note = "（只閃得開普攻）" if effect.kind == "dodge" else STAT_NOTES.get((effect.stat, effect.kind), "")
    return f"{_name(effect, kind)}・{who}・{lasting}{note}"


def effect_short(effect: SkillEffect, level: int, kind: str) -> str:
    """武學庫用的短句：效果名稱加上第 level 成的數字，例如「追加傷害 60%」「全體傷害 80%」。"""
    pct = _pct(team.skill_value(effect.base, effect.top, level))
    return f"{GROUP_WORDS.get(effect.target, '')}{_name(effect, kind)} {pct}%"


def summary(skill: Skill, level: int) -> str:
    """武學庫的一行摘要：第一個效果的短句，絕招／連招再加上發動率。"""
    text = effect_short(skill.effects[0], level, skill.kind)
    if skill.kind != "心法":
        text += f"，發動 {_pct(team.skill_value(skill.chance_base, skill.chance_top, level))}%"
    return text


def rules_line(content: Content) -> str:
    cfg = content.config
    return (
        f"一門武學同時只能配給一個人，某人的本命不能配給同隊的人；第 n 成升一成要心得 {cfg.xinde_cost_factor}×n；"
        f"散功返還{_ratio_word(cfg.dispel_refund)}；本命不能散功"
    )


def _ratio_word(ratio: float) -> str:
    """0.8 →「八成」；不是整成時用百分比。"""
    tenths = round(ratio * 10)
    if abs(ratio * 10 - tenths) < 1e-9 and 1 <= tenths <= 10:
        return CHINESE_DIGITS[tenths] + "成"
    return f" {round(ratio * 100)}%"


# ── 武學詳情 ──────────────────────────────────────────


def _resolve(state: GameState, content: Content, target: str | None) -> tuple[Skill, int] | None:
    """target（skill:<id>／innate:<key>）→（武學, 目前成數）；沒有這門武學時回傳 None。"""
    if not target:
        return None
    level = team.target_level(state, content, target)
    if level is None:
        return None
    kind, _, ident = target.partition(":")
    skill_id = ident if kind == "skill" else team.innate_of(state, content, ident)
    return content.skills[skill_id], level


def _style_name(style: str) -> str:
    return "無流派" if style == "無" else style


def _mult(value: float) -> str:
    text = f"{value:g}"
    return text if "." in text else text + ".0"


def _num(value: float) -> str:
    return f"{round(value, 1):g}"


def _has(skill: Skill, kind: str) -> bool:
    return any(e.kind == kind for e in skill.effects)


def _placements(state: GameState, content: Content, target: str) -> list[str]:
    """這門武學配在誰的哪一欄，例如「韓鐵・自選1」、「沈浪・本命」。"""
    p = state.player
    kind, _, ident = target.partition(":")
    if kind == "innate":
        return [f"{team.member_name(state, content, ident)}・本命"]
    spots = []
    if ident == content.config.player_innate:
        spots.append(f"{team.member_name(state, content, PLAYER)}・本命")
    lined = team.lined_up(state)
    for key in lined + [k for k in p.loadouts if k not in lined]:
        for i, skill_id in enumerate(p.loadouts.get(key, [])):
            if skill_id == ident:
                spots.append(f"{team.member_name(state, content, key)}・自選{i + 1}")
    return spots


def _level_table(skill: Skill, level: int) -> str:
    maxed = level >= team.MAX_SKILL_LEVEL
    rows = [
        f"| 效果 | 目前第{level}成 | {'下一成' if maxed else f'升到第{level + 1}成'} |",
        "|---|---|---|",
    ]

    def cells(base: float, top: float | None) -> str:
        now = f"{_pct(team.skill_value(base, top, level))}%"
        nxt = "已達第十成" if maxed else f"{_pct(team.skill_value(base, top, level + 1))}%"
        return f"{now} | {nxt}"

    if skill.kind != "心法":
        rows.append(f"| 發動率 | {cells(skill.chance_base, skill.chance_top)} |")
    for effect in skill.effects:
        rows.append(f"| {effect_label(effect, skill.kind)} | {cells(effect.base, effect.top)} |")
    return "\n".join(rows)


def _notes(skill: Skill) -> list[str]:
    notes = []
    if _has(skill, "damage"):
        notes.append("傷害以一次普攻為 100%。")
    if _has(skill, "control"):
        notes.append("控制命中率＝表中機率 ×（1 +（自己悟性 − 對方悟性）× 5%），最低 5%、最高 95%。")
    if skill.kind != "心法" and any(e.kind in LASTING_KINDS for e in skill.effects):
        notes.append("回合數以承受者自己的回合計（被點穴而沒出手也算一回合）。")
    return notes


def _counter_line(skill: Skill) -> str:
    style = skill.style
    if style == "無":
        return "無流派，不參與相剋。"
    if not _has(skill, "damage"):
        return f"{style}流派，但這門武學不造成傷害，相剋不影響它。"
    beats = BEATS[style]
    beaten_by = next(k for k, v in BEATS.items() if v == style)
    return (
        f"剋{beats}（對{beats}流派的敵人傷害 ×{_mult(ADVANTAGE)}）、"
        f"被{beaten_by}剋（對{beaten_by}流派的敵人傷害 ×{_mult(1 / ADVANTAGE)}）"
    )


def _holder(content: Content, target: str) -> str | None:
    """本命武學的主人（只有他能用）；不是本命時回傳 None。"""
    if not team.is_innate(content, target):
        return None
    kind, _, ident = target.partition(":")
    return ident if kind == "innate" else PLAYER


def _aptitude_block(state: GameState, content: Content, skill: Skill, target: str) -> str:
    """資質只乘在同流派的傷害上：列出誰用這門武學的倍率，順手的排前面；本命只列主人。"""
    head = "**誰用最順手**"
    holder = _holder(content, target)
    if skill.style == "無":
        reason = "無流派"
    elif not _has(skill, "damage"):
        reason = "這門武學不造成傷害"
    else:
        reason = None
    if reason is not None:
        if holder is not None:
            return f"{head}　本命只有本人能用；{reason}，資質不影響它。"
        return f"{head}　{reason}，資質不影響它，誰用都一樣。"
    keys = [holder] if holder is not None else team.lined_up(state)
    note = "（本命只有本人能用）" if holder is not None else ""
    rows = []
    for key in keys:
        _, grades = team.member_style(content, key)
        grade = grades.get(skill.style, "B")
        mult = team.APTITUDE[grade]
        rows.append((mult, f"- {team.member_name(state, content, key)} {skill.style}{grade} ×{_mult(mult)}{note}"))
    rows.sort(key=lambda row: -row[0])
    return f"{head}（資質只放大或縮小這門武學的傷害）\n\n" + "\n".join(line for _, line in rows)


def detail(state: GameState, content: Content, target: str | None) -> str:
    """武學庫裡一門武學（skill:<id> 或 innate:<key>）的完整說明（Markdown）。"""
    resolved = _resolve(state, content, target)
    if resolved is None:
        return HINT
    skill, level = resolved
    parts = [f"### {skill.name}　〔{skill.kind}〕〔{_style_name(skill.style)}〕〔{QUALITY_NAMES[skill.quality]}〕"]
    if skill.desc:
        parts.append(f"*{skill.desc}*")
    parts.append(f"**何時發動**　{when_text(skill)}")
    parts.append(_level_table(skill, level))
    notes = _notes(skill)
    if notes:
        parts.append("註：" + "".join(notes))
    parts.append(f"**相剋**　{_counter_line(skill)}")
    parts.append(_aptitude_block(state, content, skill, target))
    parts.append(f"**目前配置於**　{'、'.join(_placements(state, content, target)) or '未配置'}")
    if level >= team.MAX_SKILL_LEVEL:
        parts.append("**已達第十成**")
    else:
        parts.append(f"**升一成需要心得** {team.upgrade_cost(content, level)}")
    if team.is_innate(content, target):
        parts.append("本命武學不能散功。")
    return "\n\n".join(parts)


# ── 人物卡、武學欄、武學庫 ──────────────────────────────


def member_card(state: GameState, content: Content, key: str) -> str:
    """人物卡（Markdown）：等級、流派、內力、升級後的屬性與四流派資質。"""
    p, cfg = state.player, content.config
    member = p.members[key]
    leader = "（隊長）" if team.team_of(state, key) is not None and team.teammates(state, key)[0] == key else ""
    style, grades = team.member_style(content, key)
    exp = "已滿級" if member.level >= cfg.max_level else f"經驗 {member.exp}/{cfg.level_exp * member.level}"
    now, cap = team.member_neili(state, content, key)
    stats = team.member_stats(state, content, key)
    return "\n\n".join([
        f"### {team.member_name(state, content, key)}{leader}",
        f"第 {member.level} 級（{exp}）　流派 {style}",
        f"內力 {int(now)} / {int(cap)}",
        "　".join(f"{cfg.stat_names[k]} {_num(stats[k])}" for k in team.COMBAT_STATS),
        "資質　" + "　".join(f"{s}{grades.get(s, 'B')}" for s in team.STYLES),
    ])


def _art_label(skill: Skill, level: int) -> str:
    return f"{skill.name}（{skill.kind}）第{level}成"


def slot_label(state: GameState, content: Content, key: str, slot: int | None) -> str:
    """武學欄按鈕的文字；slot 為 None 代表本命，0、1 代表自選1、自選2。"""
    if slot is None:
        innate = team.innate_of(state, content, key)
        if not innate:
            return "本命　（無）"
        return f"本命　{_art_label(content.skills[innate], team.innate_level(state, content, key))}"
    skill_id = team.slot_skill(state, key, slot)
    if not skill_id:
        return f"自選{slot + 1}　（空）"
    return f"自選{slot + 1}　{_art_label(content.skills[skill_id], state.player.skills[skill_id])}"


def library(state: GameState, content: Content) -> list[tuple[str, str]]:
    """武學庫：（短短一行, target），順序同 team.upgrade_options；完整說明在 detail。"""
    items = []
    for _, target in team.upgrade_options(state, content):
        skill, level = _resolve(state, content, target)
        spots = _placements(state, content, target)
        label = (
            f"{skill.name}（{skill.kind}・{_style_name(skill.style)}）第{level}成"
            f"　{summary(skill, level)}〔{'、'.join(spots) or '未配置'}〕"
        )
        items.append((label, target))
    return items
