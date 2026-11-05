"""鐵匠順口（全部拆包第 41 批；打造隱藏配方設計 6.2）：鐵匠鋪的動作不花時間，種子多帶這一下之後的銀兩與素材數；中了說出這家知道的那一句。
原本 Game._smith_clue，Game 留一行委派，因為測試換掉它（tests/gear/test_econ_smith.py、test_shop.py），包裡其餘各檔一律經 ctx._smith_clue 叫才打得到。
第一個參數 ctx 是 Game。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import forge_secrets  # 共用規則層
from tianxia import secret_recipes  # 共用規則層

if TYPE_CHECKING:
    from tianxia.engine import Game


def smith_clue(ctx: Game, paid: bool = True) -> list[str]:
    """鐵匠順口（打造隱藏配方設計 6.2；計畫「要 PM 定的」第 3 條）：鐵匠鋪的動作不花時間，種子多帶這一下之後的銀兩與素材數，
    同一刻連按也各擲各的；中了說出這家知道的那一句（已經聽過不再說）。自己的亂數，不動 ctx.rng。
    paid：這一下有沒有收銀兩（一階淬煉只收素材）——沒收的那一句不寫「收錢」（smith_frame_free，FB-142）。"""
    s, rule = ctx.state, ctx.content.config.forge_secrets
    p = s.player
    seed = f"鐵匠|{p.name}|{s.world.time}|{p.location}|{p.stats.get('silver', 0)}|{sum(p.materials.values())}"
    if not secret_recipes.roll(rule.smith_chance, seed):
        return []
    clue = forge_secrets.hear_smith(s, ctx.content, secret_recipes.tianji_of(ctx.world))
    return [(rule.smith_frame if paid else rule.smith_frame_free).format(clue=clue)] if clue else []
