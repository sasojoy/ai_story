"""人物情誼的煙霧測試（開發規範手冊 4.1 第三級：一包一條，走一次最常見的路）：week7 的官軍，盧植託他送一封信，走到長社交信：
這一件辦成、情誼與貢獻到手、他回一封道謝信；人物頁看得到這一件。"""
import pytest

from stances_kit import LUZHI, real_game
from tianxia import errands
from tianxia.core.registry import FEATURES


@pytest.mark.smoke
def test_a_figure_entrusts_a_letter_and_it_gets_delivered():
    feature = next(f for f in FEATURES if f.name == "companions")
    g = real_game("week7")
    s, c = g.state, g.content
    assert feature.enabled(g) and feature.prefix == "errand"
    s.player.affinities[LUZHI] = 50
    errands.give(s, c, LUZHI, "luzhi_letter")
    e = s.player.errands[-1]
    assert g.figure_view(LUZHI)["errands"][0]["id"] == e.id
    s.player.location = e.target
    contrib = s.player.contrib
    assert f"errand:deliver:{e.id}" in {o.id for o in g.options(odds=False) if o.enabled}
    g.choose(f"errand:deliver:{e.id}")
    assert e.status == "done" and s.player.contrib > contrib and s.player.letters[-1].kind == "道謝"
