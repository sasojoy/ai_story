"""玉璽碎片（docs/superpowers/specs/2026-10-11-玉璽碎片-design.md；計畫 docs/superpowers/plans/2026-10-12-玉璽-1-核心.md）：
內容、規則的純函式、效果、現世、璽動、隱沒。接進 Game 的單挑在 test_seal_engine.py，單挑的純函式在 test_seal_duel.py。"""
from __future__ import annotations

import random

import pytest

from conftest import install_season_one, install_showdowns, real_content
from tianxia import naming
from tianxia.content import _validate_seal
from tianxia.models import ShardDef

SHARDS = (  # 設計 7.1：id、名字、效果鍵
    ("chishou", "螭首", "hp_cap"), ("xuanniu", "玄紐", "talk_turns"), ("yunzhuan", "雲篆", "practice"),
    ("jinjiao", "金角", "dodge"), ("chenglu", "承露", "stamina_regen"), ("chizhang", "赤璋", "fuse_points"),
    ("guixin", "歸心", "mate_exp"),
)
SALT = "測試的密鹽"


def put_shards(content):
    """測試內容沒有 content/seal.json（碎片關著）：裝上七片。"""
    content.seal = {sid: ShardDef(id=sid, name=name, part="印", effect=key) for sid, name, key in SHARDS}
    return content


def seal_problems(content) -> list[str]:
    """只跑碎片那一段載入檢查（content._validate_seal），回所有不合格的原因。不跑整份 validate：install_season_one 的縮小時刻表
    引用了測試內容沒有的戰線、人物、地點（整份 validate 本來就不過，test_engine 的決戰測試也都不跑它）。"""
    problems: list[str] = []
    _validate_seal(content, lambda ok, message: ok or problems.append(message))
    return problems


@pytest.fixture
def sealed(content):
    """測試內容＋第一季（install_season_one）＋三筆時刻表決戰（install_showdowns，北區打）＋陣營＋七片；長社標 stir、宛城標 emerge。
    測試內容沒有混元一氣：emerge_skill 先關掉（要測的那一支自己借一門內容武學）。"""
    from test_engine import _install_factions

    install_season_one(content)
    install_showdowns(content)
    _install_factions(content)
    put_shards(content)
    content.config.seal.emerge_skill = None
    marks = {"changshe_fire": "stir", "wancheng": "emerge"}
    for event in content.timetable:
        event.seal = marks.get(event.id)
    assert seal_problems(content) == []
    return content


def test_the_real_content_has_seven_shards_and_marks_three_showdowns():
    """七片名字不重複、效果鍵剛好是 Config.seal.effects 的七個；時刻表標宛城現世、長社與廣宗璽動（PM 甲、8.5）。"""
    c = real_content()
    assert len(c.seal) == 7 and len({s.name for s in c.seal.values()}) == 7
    assert {s.effect for s in c.seal.values()} == set(c.config.seal.effects)
    assert {e.id: e.seal for e in c.timetable if e.seal} == {"changshe_fire": "stir", "wancheng": "emerge", "guangzong": "stir"}


def test_the_test_content_has_no_shards_so_the_seal_stays_off(content):
    from tianxia import seal

    assert content.seal == {} and not seal.on(content)
    put_shards(content)
    assert seal.on(content)
    content.config.seal.enabled = False  # 主機的緊急開關
    assert not seal.on(content)


def test_the_pm_numbers_are_the_defaults():
    """19.1 PM 的決定：7%、上限 25%、局勢全 1.0、單挑 1.0／1.0／0.6、一場每邊搏兩次、護璽 0.7、+1、三季 28 天、不到 10 人。"""
    cfg = real_content().config.seal
    assert (cfg.emerge_chance, cfg.stir_chance, cfg.season_stir_cap, cfg.cap, cfg.guard) == (0.35, 0.07, 2, 0.25, 0.7)
    assert cfg.side_factor == {"險勝": 1.0, "險敗": 1.0, "大敗": 1.0, "旁觀": 1.0}
    assert cfg.take_share == {"提前大勝": 1.0, "大勝": 1.0, "險勝": 0.6} and cfg.gamble_cap == 2
    assert cfg.fame == {"keep": 3, "lose": 5, "near": 1}
    assert (cfg.sink_seasons, cfg.sink_days, cfg.small_battle, cfg.emerge_skill) == (3, 28, 10, "hunyuan")


def test_shard_names_are_kept_off_the_name_space():
    """七片的名字不讓模型與玩家取走（7.1 最後一條）。"""
    c = real_content()
    assert naming.name_problem("螭首", c) == naming.SEAL_CLASH
    assert naming.name_problem("雲篆劍", c) is None  # 只擋同名


@pytest.mark.parametrize(("change", "message"), [
    (lambda c: c.seal.pop("guixin"), "剛好七片"),
    (lambda c: setattr(c.seal["guixin"], "effect", "win_exp_pct"), "效果"),
    (lambda c: setattr(c.seal["guixin"], "name", c.skills["basic_fist"].name), "名字"),  # 撞到內容武學的名字
    (lambda c: setattr(c.seal["guixin"], "name", "螭首"), "不重複"),
    (lambda c: setattr(c.config.seal, "side_factor", {"險勝": 1.2, "險敗": 1.0, "大敗": 1.0, "旁觀": 1.0}), "不能超過 1"),
    (lambda c: setattr(c.config.seal, "take_share", {"提前大勝": 1.5}), "不能超過 1"),
    (lambda c: setattr(c.config.seal, "emerge_skill", "沒有這門"), "emerge_skill"),
    (lambda c: [setattr(e, "seal", "emerge") for e in c.timetable if e.id == "changshe_fire"], "剛好一件"),
    (lambda c: [setattr(e, "seal", "stir") for e in c.timetable if e.id == "uprising"], "只能標在決戰"),
])
def test_a_bad_seal_setup_is_refused_at_load(sealed, change, message):
    assert seal_problems(sealed) == []  # 改之前是好的
    change(sealed)
    assert any(message in problem for problem in seal_problems(sealed)), seal_problems(sealed)


def test_no_shards_means_the_marks_and_the_emerge_skill_are_not_checked(content):
    """沒有 content/seal.json（測試內容、碎片關著）時，時刻表的標記與 emerge_skill 都不檢查（8.5：沒標也不算錯，那個劇本就是
    不現世、不璽動；測試內容沒有混元一氣，預設的 emerge_skill 不能讓整份測試內容載入失敗）。"""
    install_season_one(content)
    for event in content.timetable:
        event.seal = "stir" if event.kind == "showdown" else None
    assert content.config.seal.emerge_skill == "hunyuan" and "hunyuan" not in content.skills
    assert seal_problems(content) == []


# ── Task 2：全服登記、密鹽、亂數 ──

def test_the_registry_lives_on_the_shared_world_and_survives_a_new_season(sealed, world):
    """登記在 world 那一列（不分季）：換季不清；開季、換季寫 opened_real（「這一季上線過」與隱沒都看它，5.3）。"""
    from conftest import next_season
    from tianxia import seal
    from tianxia.engine import Game

    world.mutate(lambda st: seal.log(seal.filled(st.seal, sealed), st.season_number, "emerge", shard="chishou", holder="甲"))
    game = Game.new(sealed, "甲", rng=random.Random(0), world=world)
    before = world.seal_state().registry.opened_real
    next_season(sealed, world, game)
    view = world.seal_state()
    assert [e.kind for e in view.registry.history] == ["emerge"] and set(view.registry.shards) == {s for s, _, _ in SHARDS}
    assert view.registry.opened_real == 300.0 and view.registry.opened_real != before and view.season == 2


def test_the_salt_is_made_once_and_never_shown(sealed, world):
    from tianxia import seal

    reg = world.seal_state().registry
    assert reg.salt == ""
    assert seal.ensure_salt(reg) and len(reg.salt) == 32
    first = reg.salt
    assert not seal.ensure_salt(reg) and reg.salt == first


def test_the_dice_are_seeded_by_salt_tianji_and_purpose():
    from tianxia import seal

    a = seal.dice(SALT, 3, "seal-stir", "changshe_fire", "chishou").random()
    assert a == seal.dice(SALT, 3, "seal-stir", "changshe_fire", "chishou").random()
    assert a != seal.dice("別的鹽", 3, "seal-stir", "changshe_fire", "chishou").random()
    assert a != seal.dice(SALT, 4, "seal-stir", "changshe_fire", "chishou").random()


def test_shard_of_matches_names_without_case(sealed, world):
    from tianxia import seal
    from tianxia.world_state import SealRegistry

    reg = seal.filled(SealRegistry(), sealed)
    reg.shards["yunzhuan"].state, reg.shards["yunzhuan"].holder = "held", "Rayal"
    assert seal.shard_of(reg, "rayal").id == "yunzhuan" and seal.holders(reg) == {seal.key("Rayal")}
    assert seal.shard_of(reg, "別人") is None
