"""素材與經濟計畫 B7：玩法說明跟著新規則寫（收購、升階、捐軍備、找素材一階七成、出陣攻打贏給銀兩三成）；開關關著不寫。"""
from __future__ import annotations

from conftest import real_content
from tianxia.features.guide import howto as guide_howto
from tianxia.features.sortie import howto as sortie_howto
from tianxia.features.outlets import howto as outlets_howto
from tianxia.world_state import fresh_season


def _page(**econ):
    c = real_content("week7")
    for key, value in econ.items():
        setattr(c.config.economy, key, value)
    return guide_howto.page(c, fresh_season(c), recruitable=False), c


def test_the_page_explains_where_spare_materials_go():
    page, _ = _page()
    assert f"#### {outlets_howto.ECONOMY_TITLE}" in page
    # 素材四階（正式季整合 4.2、4.5）：三階收、四階不收；二換三不設一天一個，三換四一季兩個
    for words in ("一階一個 2 兩", "二階 6 兩", "三階 18 兩", "四階不收", "三個換一個", "五個換一個四階", "一季兩個", "一天最多 100 點",
                  "糧秣", "箭矢", "甲冑", "戰馬",
                  "約 5 成是同屬性的，其餘隨機"):
        assert words in page, words


def test_a_certain_upgrade_says_nothing_of_luck():
    _, c = _page(upgrade_same_share=1.0)
    lines = outlets_howto.economy_lines(c)
    assert any("三個換一個" in line for line in lines) and not any("隨機" in line for line in lines)


def test_switched_off_the_section_is_gone():
    page, _ = _page(sell=False, upgrade=False, donate=False)
    assert outlets_howto.ECONOMY_TITLE not in page


def test_only_the_switched_on_parts_are_written():
    page, _ = _page(upgrade=False, donate=False)
    assert "一階一個 2 兩" in page and "三個換一個" not in page and "糧秣" not in page


def test_sortie_says_the_new_numbers():
    c = real_content("week7")
    attack = sortie_howto.sortie_line("attack", 5, c)
    assert "銀兩也是 3 成" in attack and "不給銀兩" not in attack
    assert any("銀兩" in line and "3 成" in line for line in sortie_howto.sortie_lines(c))
    c.config.economy.sortie_silver = False
    assert "不給銀兩、不掉東西" in sortie_howto.sortie_line("attack", 5, c)
