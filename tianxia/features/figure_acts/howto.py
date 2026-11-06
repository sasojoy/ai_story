"""大勢人物的行動包：玩法說明「挑戰大勢人物」那一節（全部拆包第 59 批；原 tianxia/howto.py，字一個不動；順序在核心 HOWTO_ORDER）。"""
from __future__ import annotations

from tianxia import figures, rules, territory
from tianxia.models import Content
from tianxia.state import WorldState

# 挑戰大勢人物（挑戰每季都有設計 3.9，待 joy 潤）：沒有時刻表的季多寫的幾句；數字從 Config 讀，回復、上限是 0 時不寫那半句
CHALLENGE_UNTIMED = (
    "- 打贏一次他的聲威掉 {n}；沒人去打，聲威會慢慢回來。",
    "- 每位人物一天最多被打掉 {cap} 點聲威。",
    "- 聲威掉到 0 就退場，這一季不再出現。",
    "- {names}退場之後，不再替自己那一方出力。",
)
CHALLENGE_SEASON21_REGEN = "- 沒人去打，大勢人物的聲威會慢慢回來（一天回 {n} 點）。"  # 待 joy 潤：21 天季的第一季（正式季整合 3.9）


# 玩法說明「挑戰大勢人物」那一段（FB-190：以前插在「情誼」中間，最後那句「換季只帶一成」讀起來像在講聲威）。待 joy 潤
CHALLENGE_TITLE = "挑戰大勢人物"
CHALLENGE_WHO = "- 投靠了陣營的人，可以在敵方大勢人物所在的地方挑戰他本人（按鈕上寫勝算，體力同{act}）；自己陣營的人物不打{both}，散人不能挑戰。"
CHALLENGE_BOTH = "，{names}兩邊的人物都能挑戰"
CHALLENGE_SNUB = "- 打贏之後 {hours:g} 個現實小時內，他閉門不見：挑戰、求見、交友都不行。"


CHALLENGE_RISE = "- 你的隊伍越強，大勢人物越拚命：他照你們的身手出全力，這一季每被你打贏一次，下一次就更難打。鈕上的勝算照這個算。"
CHALLENGE_DRAW = "- 跟他打成平手也不白打：拿得到打贏的一半心得與經驗，也算一次頓悟的契機；不掉東西、他的聲威不動、情誼也不扣。"


def _challenge_lines(content: Content, season: WorldState) -> list[str]:
    """挑戰大勢人物本人那一段（FB-190 另起一段）：誰能挑戰（有陣營、打敵方的人物，自己陣營沒有人物的〔地方豪強〕兩邊都打，散人不行；
    同 Game._challenge_options）、閉門不見、情誼會掉；沒有時刻表的季多寫聲威怎麼掉、怎麼回、一天上限、退場與龍頭人物停手。"""
    cfg = content.config
    if not figures.challenge_on(content, season):
        return []
    sides = {fig.faction for fig in content.figures.values()}
    # 豪強分屬兩軍的季：豪強照依附那一邊只打對面的人物（Game._challenge_options 照 _side），不寫「兩邊都打」
    both = [] if rules.haoqiang_allied(content, season) else [f.name for f in content.scenario.factions if f.id not in sides]
    act = territory.SORTIE_NAME if territory.on(content) else "遊歷"  # FB-251：出陣開著時寫「體力同出陣」（挑戰本人照舊讀 action_cost["train"]）
    lines = [CHALLENGE_WHO.format(both=CHALLENGE_BOTH.format(names="、".join(both)) if both else "", act=act)]
    if cfg.snub_hours > 0:
        lines.append(CHALLENGE_SNUB.format(hours=cfg.snub_hours))
    lines.append(f"- 打贏大勢人物本人，他對你的情誼會掉 {cfg.figure_defeat_affinity}。")
    if cfg.rise.enabled:
        lines.append(CHALLENGE_RISE)
    if cfg.figure_draw_share > 0:
        lines.append(CHALLENGE_DRAW)
    if not figures.untimed(content, season):
        if figures.upkept(content, season):  # 21 天季的第一季（正式季整合 3.9）：聲威會回、一天有上限；退場照時刻表與照舊的規矩
            if cfg.figure_prestige_regen > 0:
                lines.append(CHALLENGE_SEASON21_REGEN.format(n=f"{cfg.figure_prestige_regen:g}"))
            if cfg.figure_daily_loss_cap:
                lines.append(CHALLENGE_UNTIMED[1].format(cap=cfg.figure_daily_loss_cap))
        return lines
    first = CHALLENGE_UNTIMED[0].format(n=cfg.figure_defeat_prestige)
    lines.append(first if cfg.figure_prestige_regen > 0 else first.partition("；")[0] + "。")
    if cfg.figure_daily_loss_cap:
        lines.append(CHALLENGE_UNTIMED[1].format(cap=cfg.figure_daily_loss_cap))
    lines.append(CHALLENGE_UNTIMED[2])
    leaders = list(dict.fromkeys(sim.name for sim in content.scenario.sim_players if figures.by_name(content, sim.name)))
    if leaders:
        lines.append(CHALLENGE_UNTIMED[3].format(names="、".join(leaders)))
    return lines


def challenge_section(content: Content, season: WorldState) -> list[str]:
    """「挑戰大勢人物」那一節（HOWTO_ORDER 的 challenge）：每季都有（figures.challenge_on），另起一段（FB-190）；沒有句子整節不寫。"""
    challenge = _challenge_lines(content, season)
    return [f"#### {CHALLENGE_TITLE}", *challenge, ""] if challenge else []
