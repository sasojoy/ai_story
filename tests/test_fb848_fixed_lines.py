"""FB-848：模型叫不動時，同一篇傳裡每位寫手的固定句不重複（QA：波才與曹操同一個理由，固定句一字不差）。
固定句改成整篇一起挑（zhuan_end.fixed_verdicts）：同一個理由的寫手照順序輪著挑、整篇不撞句；自己那一組不夠了往別組借，句子全用過了才重複。"""
from __future__ import annotations

import pytest
from zhuan_fix_kit import add_story, close_season, make_game, verdict_paras

from jianfa_kit import jianfa_game
from tianxia import zhuan_end

pytestmark = pytest.mark.slow


def _writers(*pairs) -> list[zhuan_end.Writer]:
    return [zhuan_end.Writer(fid, reason) for fid, reason in pairs]


def test_fixed_lines_never_repeat_inside_one_piece():
    content = jianfa_game().content
    ws = _writers(("huangfusong", zhuan_end.TIER), ("zhujun", zhuan_end.AFFINITY), ("caocao", zhuan_end.AFFINITY),
                  ("liubei", zhuan_end.AFFINITY), ("guanyu", zhuan_end.AFFINITY), ("luzhi", zhuan_end.BOUGHT),
                  ("xunyu", zhuan_end.BOUGHT))
    for name in ("甲客", "乙客", "沈浪", "丙", "丁客", "無名氏", "蘭陵王", "青衫"):
        for season in (1, 2, 3):
            lines = zhuan_end.fixed_verdicts(content, ws, name, season)
            assert list(lines) == [w.fid for w in ws]
            assert len(set(lines.values())) == len(ws), (name, season)
            assert all(name in line and "{name}" not in line for line in lines.values())


def test_each_writer_gets_a_line_from_his_own_reason_while_the_pool_lasts():
    content = jianfa_game().content
    ws = _writers(("huangfusong", zhuan_end.TIER), ("zhujun", zhuan_end.AFFINITY), ("luzhi", zhuan_end.BOUGHT))
    lines = zhuan_end.fixed_verdicts(content, ws, "甲客", 1)
    for w in ws:
        assert lines[w.fid] in [x.replace("{name}", "甲客") for x in content.verdicts[w.reason]]


def test_the_same_inputs_give_the_same_lines():
    content = jianfa_game().content
    ws = _writers(("zhujun", zhuan_end.AFFINITY), ("caocao", zhuan_end.AFFINITY))
    assert zhuan_end.fixed_verdicts(content, ws, "甲客", 1) == zhuan_end.fixed_verdicts(content, ws, "甲客", 1)


def test_a_content_with_one_fixed_line_per_reason_still_never_repeats():
    content = jianfa_game().content
    content.verdicts = {}  # 測試內容沒有 verdicts.json：照 DEFAULT_VERDICTS 每種一句，同理由的第二位往別組借
    ws = _writers(("zhujun", zhuan_end.AFFINITY), ("caocao", zhuan_end.AFFINITY), ("luzhi", zhuan_end.AFFINITY))
    assert len(set(zhuan_end.fixed_verdicts(content, ws, "甲客", 1).values())) == 3


def test_more_writers_than_lines_repeats_instead_of_failing():
    content = jianfa_game().content
    content.verdicts = {"affinity": ["{name}一。", "{name}二。"], "tier": ["{name}三。"], "bought": ["{name}四。"]}
    ws = _writers(*[(f"p{i}", zhuan_end.AFFINITY) for i in range(6)])
    lines = zhuan_end.fixed_verdicts(content, ws, "甲客", 1)
    assert len(lines) == 6 and len(set(lines.values())) == 4  # 四句都用過了才重複


def test_the_content_pools_are_big_enough_for_the_most_writers_a_piece_can_have():
    content = jianfa_game().content
    most = content.config.jianfa.deep_figures + 1  # 深交三位加名額一位
    assert len(content.verdicts[zhuan_end.AFFINITY]) >= most
    assert len(content.verdicts[zhuan_end.BOUGHT]) >= content.mall["zhuan_quote"].limit.season
    lines = [line for pool in content.verdicts.values() for line in pool]
    assert len(lines) == len(set(lines))  # 各組之間、組裡面都不重複（往別組借時才不會借到同一句）


def test_the_content_check_catches_a_repeated_line():
    content = jianfa_game().content
    assert zhuan_end.check_verdicts(content) == []
    content.verdicts = {"affinity": ["{name}可交。", "{name}可交。"], "tier": ["{name}可交。"]}
    problems = zhuan_end.check_verdicts(content)
    assert any("重複" in p for p in problems)


def test_four_deep_friends_and_a_tier_writer_get_five_different_lines():
    game = make_game()
    assert game.mall_buy("deep_slot", "d1")[0].startswith("買下")
    p = game.state.player
    p.contrib = 120  # 第一階：官軍的主將（皇甫嵩，情誼 0）替他寫
    p.affinities.update({"zhujun": 80, "caocao": 75, "liubei": 72, "guanyu": 71})
    game.sync(game.now)
    assert len(p.deep_order) == 4
    add_story(game)
    close_season(game)
    request = game.biography_request(1)
    assert [(j.fid, j.reason) for j in request.verdicts] == [
        ("huangfusong", zhuan_end.TIER), ("zhujun", zhuan_end.AFFINITY), ("caocao", zhuan_end.AFFINITY),
        ("liubei", zhuan_end.AFFINITY), ("guanyu", zhuan_end.AFFINITY)]
    assert len({j.fixed for j in request.verdicts}) == 5
    assert game.write_biography(request, None, game.now + 30)  # 模型叫不動：整篇都是固定句
    said = [para.split("：「", 1)[1] for para in verdict_paras(game.biography_view(1)["paragraphs"])]
    assert len(said) == 5 and len(set(said)) == 5


def test_a_single_writer_keeps_the_old_entry_point():
    content = jianfa_game().content
    writer = zhuan_end.Writer("luzhi", zhuan_end.TIER)
    assert zhuan_end.fixed_verdict(content, writer, "甲客", 1) in [line.replace("{name}", "甲客") for line in content.verdicts["tier"]]
