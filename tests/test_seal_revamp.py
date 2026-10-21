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


# ── Task 2：常駐效果走傳承那一格、說明句 ──

@pytest.mark.parametrize(("shard", "key", "value"), [
    ("chishou", "injury", 0.5), ("xuanniu", "talk_turns", 2), ("xuanniu", "audience", 5), ("yunzhuan", "practice", 0.75),
    ("jinjiao", "keep_silver", 1), ("chenglu", "stamina_regen", 1.25), ("chizhang", "fuse_points", 10),
    ("guixin", "mate_exp", 1.25), ("guixin", "chuangong", 0.9),
])
def test_each_shard_feeds_its_revamp_numbers_into_the_hooks(content, world, shard, key, value):
    """傳承那一格照改版的效果鍵與 Config.seal.revamp.effects（設計第三章）；一片兩個效果的（玄紐、歸心）兩個都給。"""
    revamp(content)
    game = holding(content, world, shard)
    assert treasures.amount(game.state, content, key) == pytest.approx(value)
    content.config.seal.revamp.effects[key] = 7  # 數字照 Config 讀，不寫死
    assert treasures.amount(game.state, content, key) == pytest.approx(7)


def test_chishou_and_jinjiao_drop_their_old_effects(content, world):
    """螭首不再加氣血上限（取代「氣血上限 ×1.06」）、金角不再加閃避（取代「落敗閃成僵持 +3%」，那一條算戰力，拿掉）。"""
    from tianxia import team

    revamp(content)
    chishou = holding(content, world, "chishou")
    assert treasures.amount(chishou.state, content, "hp_cap") == 1.0 and chishou.state.player.member.cap_scale == 1.0
    jinjiao = holding(content, world, "jinjiao", name="金角客")
    jinjiao.state.player.stats["agi"] = 5
    assert team.dodge_chance(jinjiao.state, content) == 0.0


def test_the_talk_cap_and_stamina_regen_take_the_bigger_numbers(content, world):
    from tianxia.engine import Game

    revamp(content)
    xuanniu = holding(content, world, "xuanniu")
    assert xuanniu._talk_cap() == content.config.talk_turns_per_day + 2
    plain = Game.new(content, "平人", rng=random.Random(0), world=world)
    plain.sync(0.0)
    chenglu = holding(content, world, "chenglu", name="承露客")
    plain.state.player.stamina = chenglu.state.player.stamina = 0.0
    later = content.config.stamina_regen_seconds * 10 / content.config.time_scale
    plain.sync(later)
    chenglu.sync(later)
    assert chenglu.state.player.stamina == pytest.approx(plain.state.player.stamina * 1.25)


def test_switched_off_the_shards_keep_their_old_effects(content, world):
    """子開關關著：舊的七個效果與數字（Config.seal.effects）一個都不變，新的鍵是中性值、沒有戰力倍數。"""
    revamp(content)
    content.config.seal.revamp.enabled = False
    old = {"chishou": ("hp_cap", 1.06), "xuanniu": ("talk_turns", 1), "jinjiao": ("dodge", 0.03), "guixin": ("mate_exp", 1.1)}
    for i, (sid, (key, value)) in enumerate(old.items()):
        game = holding(content, world, sid, name=f"舊{i}")
        assert treasures.amount(game.state, content, key) == pytest.approx(value)
        assert treasures.power_scale(game.state, content) == 1.0
        for new_key in ("injury", "audience", "keep_silver", "chuangong"):
            assert treasures.amount(game.state, content, new_key) == (1.0 if new_key in treasures.MULTIPLY else 0.0)


def test_only_the_holder_gets_the_power_scale(content, world):
    from tianxia.engine import Game

    revamp(content)
    game = holding(content, world, "yunzhuan")
    assert treasures.power_scale(game.state, content) == pytest.approx(1.10)
    other = Game.new(content, "旁人", rng=random.Random(0), world=world)
    other.sync(0.0)
    assert treasures.power_scale(other.state, content) == 1.0


def test_the_heirloom_row_and_card_say_power_and_every_effect(content, world):
    """傳承那一列、角色卡、碎片卡（只給自己看）寫「戰力 ×1.1、…」（待 joy 潤）；一片兩個效果照 content/seal.json 的順序接。關著照舊一句。"""
    revamp(content)
    game = holding(content, world, "xuanniu")
    text = "戰力 ×1.1、每位人物每日多談 2 輪、求見門檻 −5"
    assert seal.shard_text(content, "xuanniu") == text
    assert treasures.rows(game.state, content)["heirloom"]["effect_text"] == text
    assert f"【玄紐】{text}" in treasures.card_line(game.state, content)
    assert game.seal_view()["effect_text"] == text
    assert seal.shard_text(content, "jinjiao") == "戰力 ×1.1、落敗不失銀兩"
    content.config.seal.revamp.enabled = False
    assert seal.shard_text(content, "xuanniu") == "每位人物每日多談 1 輪"
    assert treasures.rows(game.state, content)["heirloom"]["effect_text"] == "每位人物每日多談 1 輪"


def test_got_and_assigned_lines_name_the_revamp_effects(content, world):
    """拿到碎片那一句（現世、管理者指定）照改版的說明寫（自己的江湖紀錄）。"""
    revamp(content)
    content.config.admins = ["管理"]
    from tianxia.engine import Game

    admin = Game.new(content, "管理", rng=random.Random(0), world=world)
    admin.sync(0.0)
    admin.admin_seal_assign("chenglu", "懷璽")
    game = Game.new(content, "懷璽", rng=random.Random(0), world=world)
    game.sync(1.0)
    lines = [line for e in game.state.journal if e.title == seal.SEAL_TITLE for line in [e.tag, *e.lines]]
    assert any("戰力 ×1.1、體力回復 ×1.25" in line for line in lines), lines
