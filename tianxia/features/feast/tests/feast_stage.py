"""契約測試（tests/core/test_contract_features.py）把宴客擺進「有選項」的局面：每擺好一種 yield 一個名字。
真實內容 week7 的 Game（figure_life 開著）：腳下擺一場宴（此地還能做多一顆入席）、入席之後（整個選單換成敬酒詞與離席）。"""
from tianxia.state import Feast


def stages(game):
    s = game.state
    s.world.feast_seq += 1
    s.world.feasts.append(Feast(id=s.world.feast_seq, host="xushao", place=s.player.location, start=s.world.time,
                                end=s.world.time + 2 * 3600.0))
    game._save_season()
    yield "宴席擺著"
    s.player.feasting = s.world.feast_seq
    yield "坐在席上"
