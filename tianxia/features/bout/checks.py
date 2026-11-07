"""單挑包的內容驗證（第二輪第 100 批從核心 content.py 搬來，本體照搬）：content.validate 在原位經 features.check_at 叫（格在 core/features.py 的 CONTENT_SLOTS），先後不變；關著的包照驗。"""
from __future__ import annotations

from tianxia.models import Content


def check_duels(c: Content, need, known) -> None:
    """單人頭目戰（content/duels.json）：地點、素材認得；每個陣營都挑得到一個不是自己人的面貌（散人挑第一個）；
    面貌的陣營認得；出招偏好只寫三招、權重不是負的、加起來大於 0。"""
    from tianxia.models import MOVES  # noqa: PLC0415

    factions = {f.id for f in c.scenario.factions}
    for boss in c.duels.values():
        where = f"頭目 {boss.id}"
        need(bool(boss.locations), f"{where}：至少要有一個地點")
        known(where, boss.locations, c.locations, "地點")
        known(where, boss.drops, c.materials, "素材")
        for i, foe in enumerate(boss.foes):
            if foe.side is not None:
                need(foe.side in factions, f"{where} 的第 {i + 1} 個面貌：未知的陣營 {foe.side}")
            need(set(foe.moves) <= set(MOVES), f"{where} 的第 {i + 1} 個面貌：moves 只能寫{'、'.join(MOVES)}")
            need(all(w >= 0 for w in foe.moves.values()) and (not foe.moves or sum(foe.moves.values()) > 0),
                 f"{where} 的第 {i + 1} 個面貌：moves 的權重不能是負的、也不能全是 0")
        for faction in sorted(factions):
            need(any(foe.side != faction for foe in boss.foes), f"{where}：{faction} 的人挑不到一個不是自己人的面貌")
