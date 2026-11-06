"""契約測試（tests/core/test_contract_features.py）把單挑擺進「有選項」的局面：每擺好一種 yield 一個名字。
真實內容 week7 的 Game：坐在擂台邊（店面登記的選單：報名、返回）、擂台打到一半（menu 掛鉤接管整個選單：三招與認輸；直接擺一場
還沒打完的，同宴客直接入席）。頭目戰的三招本體在這一包（duel_actions.duel_menu），可是由 MENU_ORDER["take"] 的 duel 那一格
給（第 56 批）、不是這一包的 menu 掛鉤，不擺。"""
from tianxia.state import ArenaFight, ArenaSide


def stages(game):
    p = game.state.player
    p.picking_arena = True
    yield "坐在擂台邊"
    p.picking_arena = False  # 開打那一下收起擂台邊（arena_start）
    p.arena = ArenaFight(id=1, foe_key="守擂客", me=ArenaSide(name=p.name, power=10.0, hp=100.0, hp_cap=100.0),
                         foe=ArenaSide(name="守擂客", power=10.0, hp=100.0, hp_cap=100.0))
    yield "擂台打到一半"
