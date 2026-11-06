"""酒肆包：玩法說明別節中間的插句（全部拆包第 59 批；原 tianxia/howto.py，字一個不動；核心 HOWTO_INSERTS）：名望、名聲的來源裡酒肆那兩句（fame_tavern）。"""
from __future__ import annotations

from tianxia.models import Content

from . import rules as tavern  # 酒肆開不開


def fame_tavern(content: Content) -> list[str]:
    """名望、名聲的來源裡酒肆那兩句（HOWTO_INSERTS 的 fame_tavern；原本寫在 _fame_sources 中間）。"""
    cfg = content.config
    lines: list[str] = []
    # 酒肆（Game._tavern_treat 請酒、Game._tavern_hit_fight 打退殺手）；待 joy 潤
    if tavern.on(content):
        bar = cfg.tavern
        if bar.treat_fame > 0:
            lines.append(f"在酒肆請全店喝一輪：+{bar.treat_fame}（一天一次）。")
        if bar.hit_win_fame > 0:
            lines.append(f"打退別人雇來找你的殺手：+{bar.hit_win_fame}。")
    return lines
