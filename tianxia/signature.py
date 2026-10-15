"""本命武學的本命特效與威力（企劃者 2026-10-15「現在的本命絕學很爛，甚至比玩家自己合成的還差，也沒什麼特色效果」；
數字在 Config.signature_arts 與 content/skills.json 的 SkillDef.signature）。

- 本命特效：每門本命武學一個，那位人物獨有（SkillDef.signature）。只算玩家本人身上練著的那兩門（內功、武學各一欄），
  兩門的同一個掛點相加；同伴自己練的本命武學不吃（他們的威力也不乘 power_scale）。
- 掛點（models.SIGNATURE_HOOKS）由各處自己讀 amount：
  | 掛點 | 讀的地方 | 做什麼 |
  |---|---|---|
  | mate_power、self_power | team.team_boosts | 同伴與部下、本人的加成多幾成 |
  | toll_cut | team.take_encounter_toll、toll_saved | 一場少扣幾成氣血（跟防具一起算，合計夾 Config.armor.total_cap） |
  | injury_cut | team.take_encounter_toll | 扣掉的氣血變成內傷的少幾成 |
  | heal_after、win_heal | Game._take_toll | 打完（不論勝負／打贏）回氣血上限的幾成 |
  | win_xinde_pct、win_exp_pct、win_silver_pct | Game._battle_rewards | 打贏的心得、經驗、銀兩多幾成 |
  | dodge | team.dodge_chance | 落敗閃成僵持的機會多幾個百分點 |
  | difficulty_cut、big_win_cut、luck_narrow | team.trait_mods | 同一般功效的破甲、先手、穩，加在功效之外 |
  | condition_floor | team.team_conditions | 同一般功效的厚 |
  | train_stamina | Game._action_costs | 遊歷少花幾點體力 |
- 讀的是內容（content.skills），不碰全服：本命武學一定是內容寫的。只 import models、state。
"""
from __future__ import annotations

from .models import Content, SignatureEffect
from .state import GameState

POINT_HOOKS = {"train_stamina"}  # 點數，其他是比例
HOOK_TEXT = {  # 卡上那一串數字的寫法：{value} 換成百分比或點數
    "mate_power": "門下威力 +{value}",
    "self_power": "本人威力 +{value}",
    "toll_cut": "每場少扣 {value} 氣血",
    "injury_cut": "內傷少 {value}",
    "heal_after": "每場打完回氣血上限 {value}",
    "win_heal": "打贏回氣血上限 {value}",
    "win_xinde_pct": "打贏心得 +{value}",
    "win_exp_pct": "打贏經驗 +{value}",
    "win_silver_pct": "打贏銀兩 +{value}",
    "dodge": "落敗閃成僵持 +{value}",
    "difficulty_cut": "對手強度當作低 {value}",
    "big_win_cut": "大勝門檻少對手強度的 {value}",
    "luck_narrow": "運氣起伏縮小 {value}",
    "condition_floor": "受傷時多保住最多 {value} 威力",
    "train_stamina": "遊歷少花 {value} 點體力",
}
TITLE = "本命特效"


def of(content: Content, skill_id: str | None) -> SignatureEffect | None:
    """這門武學的本命特效；不是內容寫的、或沒有特效的是 None。"""
    skill = content.skills.get(skill_id) if skill_id else None
    return skill.signature if skill is not None else None


def is_signature(content: Content, skill_id: str | None) -> bool:
    return of(content, skill_id) is not None


def worn(state: GameState, content: Content) -> list[tuple[str, SignatureEffect]]:
    """本人身上練著的那兩門裡有本命特效的（武學在前）：（武學 id, 特效）。"""
    member = state.player.member
    out = []
    for skill_id in (member.wugong_id, member.neigong_id):
        sig = of(content, skill_id)
        if sig is not None:
            out.append((skill_id, sig))
    return out


def amount(state: GameState, content: Content, hook: str) -> float:
    """本人身上兩門的這個掛點加起來；沒有是 0。"""
    return sum(sig.effects.get(hook, 0.0) for _, sig in worn(state, content))


def scale(content: Content, skill_id: str | None) -> float:
    """玩家自己那一份本命武學的威力倍數（Config.signature_arts.power_scale）；其他武學是 1。"""
    return content.config.signature_arts.power_scale if is_signature(content, skill_id) else 1.0


def value_text(hook: str, number: float) -> str:
    return f"{number:g}" if hook in POINT_HOOKS else f"{round(number * 100, 1):g}%"


def numbers(sig: SignatureEffect) -> str:
    """特效的數字那一串（「門下威力 +10%、每場打完回氣血上限 3%」）。"""
    return "、".join(HOOK_TEXT[hook].replace("{value}", value_text(hook, n)) for hook, n in sig.effects.items())


def card_text(sig: SignatureEffect) -> str:
    """功法卡、修練頁那一段：「本命特效〔仁德〕說明（數字）」。"""
    return f"{TITLE}〔{sig.name}〕{sig.desc}（{numbers(sig)}）"


def lift_levels(state: GameState, content: Content, skill_ids) -> None:
    """本命武學學到時直接第 Config.signature_arts.start_level 成：身上那一欄照欄位、功法庫裡的照 art_levels；
    已經練得更高的不動、還沒學到的不管。學到那一刻（companion_agent）與舊角色讀檔（Game._lift_signature_levels）都叫它。"""
    start = content.config.signature_arts.start_level
    p = state.player
    for skill_id in skill_ids:
        if not is_signature(content, skill_id):
            continue
        for slot in ("wugong", "neigong"):
            if getattr(p.member, f"{slot}_id") == skill_id:
                setattr(p.member, f"{slot}_level", max(getattr(p.member, f"{slot}_level"), start))
                break
        else:
            if skill_id in p.arts:
                p.art_levels[skill_id] = max(p.art_levels.get(skill_id, 1), start)


def learned(state: GameState, content: Content) -> list[str]:
    """這個角色情誼到了、學過的本命武學（旗標「學會本命:人物 id」），照人物的本命武學與內功列出。"""
    out: list[str] = []
    for flag in state.player.flags:
        if flag.startswith("學會本命:"):
            character = content.characters.get(flag.split(":", 1)[1])
            if character is not None:
                out += [s for s in (character.starting_wugong, character.starting_neigong) if s]
    return out
