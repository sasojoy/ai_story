"""輿圖第三版第 5 批（領地爭奪接縫；計畫 docs/superpowers/plans/2026-10-22-輿圖v3-接縫.md 第一節）：翻地第 1 批已經在引擎拿掉投票與
22:00 公告結算、攻城改戰書觸發；這一批把還留著「給舊季認得」的眾議、主將定奪收掉——領地爭奪從沒合進 develop／main，沒有哪一季的存檔有
投票那一版的 day_log。舊資料（帶眾議比例、by 是 vote 的那一筆）照樣讀得進來，〈天下形勢〉認不得的那一筆略過、不炸。
玩法說明（領地爭奪的季）不再寫輿圖第三版已經拿掉的「局勢層」。"""
from __future__ import annotations

import pytest

from conquest_kit import announce, conquest_game, join, plain_game
from tianxia import conquest_day, howto, xingshi
from tianxia.state import DayNote

pytestmark = pytest.mark.slow  # 建 Game、載正式內容


def test_the_vote_era_words_are_gone():
    for name in ("VOTE", "COMMANDER", "REASON_PLAIN"):
        assert not hasattr(conquest_day, name), name
    assert conquest_day.BY_WORDS == {conquest_day.LETTER: "戰書"}


def test_xingshi_has_no_vote_era_sentences():
    game = conquest_game("season21", xingshi=True)
    fact = xingshi.lines(game.content)["fact"]
    for key in ("plan_vote", "plan_commander"):
        assert key not in xingshi.FACT_KEYS and key not in fact, key
    assert "reason" not in xingshi.SAMPLE
    assert "主將" not in xingshi.SYSTEM and "戰書" in xingshi.SYSTEM  # 下一仗是誰下了戰書，不是主將挑的


def test_old_day_notes_still_load_and_are_skipped():
    """day_log 的舊資料（眾議那一版）：多的鍵（share）略過、讀得進來；by 是 vote 的那一筆〈天下形勢〉認不得，略過不寫、不炸。"""
    assert "share" not in DayNote.model_fields
    old = DayNote.model_validate({"key": 1, "side": "huang", "loc": "nanyang_road", "minute": 21 * 60, "by": "vote", "share": 0.6})
    game = conquest_game("season21", xingshi=True)
    w, c = game.state.world, game.content
    assert xingshi.note_fact(c, old) is None
    facts = xingshi.facts(w, c, [old], {})
    assert facts and not any("南陽官道" in f for f in facts)


def test_the_kit_places_a_letter_not_a_commanders_pick():
    """測試的小工具 conquest_kit.announce 排的那一場同戰書排的（以前寫 by="commander"，主將定奪）；畫面資料的 by 寫「戰書」。"""
    game = join(conquest_game("season21"), "guan")
    slot = announce(game, "nanyang_road", "huang")
    assert slot.by == {"huang": conquest_day.LETTER}
    row = next(r for r in game.conquest_view()["today"] if r["id"] == slot.id)
    assert set(row["by"].values()) == {"戰書"}


def test_the_conquest_howto_speaks_of_the_new_map():
    """玩法說明「地盤」那一節：輿圖第三版沒有局勢層了，寫天下圖的地面與區圖的名字框。領地爭奪的季第 5 批先改；關著的季原本一個字不動，
    PM 2026-10-22 定也改（設計 5.6：關著的季也用新畫法；關著的季對照只差這一句與意境那一句）。"""
    game = conquest_game("season21")
    on = "".join(howto.territory_lines(game.content, season=game.state.world))
    assert "局勢層" not in on and "天下圖" in on and "區圖" in on
    for profile in ("week7", None, "season21"):
        plain = plain_game(profile)
        off = "".join(howto.territory_lines(plain.content, season=plain.state.world))
        assert "局勢層" not in off and "天下圖的地面、區圖名字框的顏色就是此刻誰佔著" in off, profile


def test_the_strongest_insight_howto_points_at_the_region_map():
    """玩法說明「靜心感悟」那一句（STRONG_HOWTO）：輿圖第三版拿掉了意境濾鏡（第 4 批），改寫區圖名字底下的意境字與卡上的「最濃」
    （PM 2026-10-22，每一種季都改）。"""
    assert "濾鏡" not in howto.STRONG_HOWTO and "區圖" in howto.STRONG_HOWTO and "最濃" in howto.STRONG_HOWTO
    for profile in ("week7", None, "season21"):
        game = plain_game(profile)
        text = game.howto_text()
        assert "濾鏡" not in text and "局勢層" not in text and howto.STRONG_HOWTO in text, profile
