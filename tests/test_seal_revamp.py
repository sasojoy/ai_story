"""玉璽碎片改版第 1 批（docs/superpowers/specs/2026-10-21-玉璽碎片改版-design.md；計畫 docs/superpowers/plans/2026-10-21-玉璽碎片改版-1.md）：
子開關 Config.seal.revamp、七片的常駐效果（戰力 ×1.10＋照部位的成長或生活）、奪璽單挑與江湖水漲不吃戰力。持有者藏起來在
test_seal_revamp_hidden.py。舊的七個效果（開關關著）照 test_seal.py。"""
from __future__ import annotations

import random

import pytest

from conftest import real_content
from test_seal import put_shards, seal_problems, sealed  # noqa: F401  sealed 是夾具
from tianxia import seal, treasures

REVAMP = {  # 設計第三章：每片的常駐成長或生活效果鍵（戰力 ×1.10 每片都有，不在這裡）
    "chishou": ["injury"], "xuanniu": ["talk_turns", "audience"], "yunzhuan": ["practice"], "jinjiao": ["keep_silver"],
    "chenglu": ["stamina_regen"], "chizhang": ["fuse_points"], "guixin": ["mate_exp", "chuangong"],
}
NUMBERS = {  # 設計第三章的【預設】
    "injury": 0.5, "talk_turns": 2, "audience": 5, "practice": 0.75, "keep_silver": 1,
    "stamina_regen": 1.25, "fuse_points": 10, "mate_exp": 1.25, "chuangong": 0.9,
}


def revamp(content):
    """測試內容裝上七片、打開改版（put_shards 預設關著改版，舊測試照舊規則）。"""
    put_shards(content)
    for sid, keys in REVAMP.items():
        content.seal[sid].effects = list(keys)
    content.config.seal.revamp.enabled = True
    return content


def holding(content, world, shard="chishou", name="懷璽", now=0.0):
    """把 shard 記在 name 名下（since_season 0），回傳他的 Game（同步過：抄本照登記抄好）。"""
    from tianxia.engine import Game

    def _give(st):
        reg = seal.filled(st.seal, content)
        reg.shards[shard].state, reg.shards[shard].holder, reg.shards[shard].since_season = "held", name, 0

    world.mutate(_give)
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.sync(now)
    return game


# ── Task 1：子開關、內容 ──

@pytest.mark.slow
def test_the_real_content_gives_each_shard_its_revamp_effects():
    """七片的常駐效果鍵照設計第三章；數字是【預設】；子開關預設開（PM 五之一 6）；戰力 ×1.10。"""
    c = real_content()
    assert {sid: list(s.effects) for sid, s in c.seal.items()} == REVAMP
    cfg = c.config.seal.revamp
    assert cfg.enabled and cfg.power == pytest.approx(1.10)
    assert cfg.effects == pytest.approx(NUMBERS)
    assert seal.revamp_on(c) and treasures.revamp_on(c)
    for profile in ("weekend", "season21"):
        assert seal.revamp_on(real_content(profile))


def test_the_switch_needs_the_seal_and_its_own_flag(content):
    put_shards(content)
    assert not seal.revamp_on(content)  # put_shards 關著改版（舊測試照舊規則）
    revamp(content)
    assert seal.revamp_on(content) and treasures.revamp_on(content)
    content.config.seal.enabled = False  # 主機的緊急開關：碎片整個關著，改版也不算
    assert not seal.revamp_on(content) and not treasures.revamp_on(content)


def test_an_unknown_revamp_effect_is_refused_at_load(sealed):
    assert seal_problems(sealed) == []
    sealed.seal["guixin"].effects = ["mate_exp", "沒有這一種"]
    assert any("沒有這一種" in problem and "revamp" in problem for problem in seal_problems(sealed)), seal_problems(sealed)
