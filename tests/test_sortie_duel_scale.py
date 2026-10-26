"""減法季批 3b 收尾：約戰自己的推進倍數（Config.sortie.duel_progress_scale）照量表定在兩份設定覆寫檔（計畫 4.0 之四第 6 條）。

scripts/measure_conquest.py（20 人、一半假人、一季）照「一季易手 7～8 次」調：7 天季 27、21 天季 10。只寫在 week7、season21 的 `sortie`
那一塊（content/config.json 沒有 `sortie`，淺層合併不會蓋掉別的鍵）；舊出陣讀的 Config.conquest.progress_scale 不動（7 天季 12、其餘 2），
不帶設定（14 天）、週末沒有這個數（約戰在那兩種季本來就關著）。"""
from __future__ import annotations

import pytest

from conftest import real_content
from tianxia import sortie_duel
from tianxia.models import SortieRules

pytestmark = pytest.mark.slow  # 載正式內容（四份）


@pytest.mark.parametrize(("profile", "duel", "old"), [("week7", 27, 12), ("season21", 10, 2)])
def test_jianfa_seasons_carry_their_own_duel_scale(profile, duel, old):
    c = real_content(profile)
    assert c.config.sortie.duel_progress_scale == duel and sortie_duel.progress_scale(c) == duel
    assert c.config.conquest.progress_scale == old  # 舊出陣（約戰關著的季）那一個數不動
    # sortie 那一塊只多寫了這兩個鍵：其餘照 Config 預設
    assert c.config.sortie.model_copy(update={"duel_progress_scale": None, "treasure_cap": SortieRules().treasure_cap}) == SortieRules()


@pytest.mark.parametrize("profile", [None, "weekend"])
def test_other_seasons_have_no_duel_scale(profile):
    c = real_content(profile)
    assert c.config.sortie.duel_progress_scale is None
    assert sortie_duel.progress_scale(c) == c.config.conquest.progress_scale == 2
