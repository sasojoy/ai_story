"""人物情誼包：玩法說明「情誼」那一節（全部拆包第 59 批；原 tianxia/howto.py，字一個不動；順序在核心 HOWTO_ORDER）。"""
from __future__ import annotations

from tianxia import calendar, precise
from tianxia.models import Content
from tianxia.state import WorldState


def bond_section(content: Content, season: WorldState, recruitable: bool) -> list[str]:
    """「情誼」那一節（HOWTO_ORDER 的 bond）。recruitable：內容裡有沒有能招募的人物（正式內容現在沒有：不提招募）。"""
    cfg = content.config
    first = calendar.season_one_on(season, content)
    bond = [
        "- 跟人物談話，照你說的話漲跌；談話時他的名字旁邊寫著（"
        + ("交友名單上也有）。" if precise.on(content, season) else "求見名單上也有）。"),
        f"- 情誼到 {cfg.signature_affinity}，有些人物會把本命武學傳給你。",
    ]
    if first:
        # 片段只給做得了那條鏈的人（foreshadow.capable 要陣營對得上）：散人聽不到（審查 M4，待 joy 潤）
        bond.append("- 情誼夠深，他會跟你聊起一些風聲：機緣的話題，還有你那一邊的伏筆的片段（散人聽不到片段）。")
    if recruitable:
        gate = f"情誼到 {cfg.recruit_min_affinity} 才開得了口招攬，" if cfg.recruit_min_affinity > 0 else ""
        bond.append(f"- 想招攬的人，{gate}情誼越高成算越高（最多多 {cfg.recruit_affinity_bonus * 100:g} 個百分點）。")
    bond.append(f"- 換季只帶 {cfg.affinity_carry_ratio * 10:g} 成到下一季。")
    return ["#### 情誼", *bond, ""]
