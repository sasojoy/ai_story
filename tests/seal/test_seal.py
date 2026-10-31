"""玉璽碎片（docs/superpowers/specs/2026-10-11-玉璽碎片-design.md；計畫 docs/superpowers/plans/2026-10-12-玉璽-1-核心.md）：
內容、規則的純函式、效果、現世、璽動、隱沒。接進 Game 的單挑在 test_seal_engine.py，單挑的純函式在 test_seal_duel.py。"""
from __future__ import annotations

import random
import json
import sqlite3
from typing import Literal, get_args

import pytest

from conftest import install_season_one, install_showdowns, real_content
from tianxia import naming, seal
from tianxia.content import _validate_seal
from tianxia.models import ShardDef
from pydantic import BaseModel, Field, ValidationError
from tianxia.world_state import SealEvent, SealRegistry

SHARDS = (  # 設計 7.1：id、名字、效果鍵
    ("chishou", "螭首", "hp_cap"), ("xuanniu", "玄紐", "talk_turns"), ("yunzhuan", "雲篆", "practice"),
    ("jinjiao", "金角", "dodge"), ("chenglu", "承露", "stamina_regen"), ("chizhang", "赤璋", "fuse_points"),
    ("guixin", "歸心", "mate_exp"),
)
SALT = "測試的密鹽"


def put_shards(content):
    """測試內容沒有 content/seal.json（碎片關著）：裝上七片。改版（Config.seal.revamp，預設開）在這裡關掉：這幾個檔測的是舊的
    七個效果與點名的寫法；改版的測試在 test_seal_revamp*.py（test_seal_revamp.revamp 打開）。"""
    content.seal = {sid: ShardDef(id=sid, name=name, part="印", effect=key) for sid, name, key in SHARDS}
    content.config.seal.revamp.enabled = False
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


@pytest.mark.smoke
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

@pytest.mark.smoke
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


# ── Task 3：傳承那一格與七個效果 ──

def _holding(content, world, shard="chishou", name="懷璽"):
    """把 shard 記在 name 名下（since_season 0：不是這一季到手的），回傳那個人的 Game（同步過，抄本已經照登記抄好）。"""
    from tianxia import seal
    from tianxia.engine import Game

    def _give(st):
        reg = seal.filled(st.seal, content)
        reg.shards[shard].state, reg.shards[shard].holder, reg.shards[shard].since_season = "held", name, 0

    world.mutate(_give)
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.sync(0.0)
    return game


def test_the_registry_copies_the_heirloom_onto_its_holder_and_off_everyone_else(content, world):
    """抄本照登記重抄（7.4）：是你的就寫上（id 固定「璽:片」、不吃流水號），不是就清掉；碎片關著也清掉。"""
    from tianxia import seal

    put_shards(content)
    game = _holding(content, world, "yunzhuan")
    item = game.state.player.heirloom
    assert (item.id, item.name, item.template, item.heirloom, item.slot) == ("璽:yunzhuan", "雲篆", "yunzhuan", True, "treasure")
    world.mutate(lambda st: setattr(st.seal.shards["yunzhuan"], "holder", "別人"))
    game.sync(1.0)
    assert game.state.player.heirloom is None
    world.mutate(lambda st: setattr(st.seal.shards["yunzhuan"], "holder", "懷璽"))
    content.config.seal.enabled = False
    game.sync(2.0)
    assert game.state.player.heirloom is None and not seal.on(content)


def test_the_heirloom_slot_works_with_the_treasures_switched_off(content, world):
    """傳承那一格只看 Config.seal.enabled 與內容的七片，不看寶物的開關（7.2）；跟一般寶物不同鍵，不會疊。"""
    from tianxia import treasures

    put_shards(content)
    content.config.treasures.enabled = False
    game = _holding(content, world, "chenglu")
    assert treasures.amount(game.state, content, "stamina_regen") == pytest.approx(1.1)
    assert treasures.amount(game.state, content, "dodge") == 0.0 and treasures.amount(game.state, content, "practice") == 1.0


def test_chishou_raises_only_your_own_hp_cap_and_not_the_battle_pool(content, world):
    """螭首：本人氣血上限 ×1.06（要 PM 定的第 7 條：Member.cap_scale），同伴不吃；決戰的池子（_battle_neili_cap）不吃。"""
    from tianxia import team
    from tianxia.state import PLAYER

    from tianxia.engine import Game

    put_shards(content)
    plain = Game.new(content, "平人", rng=random.Random(0), world=world)._battle_neili_cap()
    game = _holding(content, world, "chishou")
    con = team.con_of(game.state, content, world, PLAYER)
    _, cap = team.member_neili(content, game.state.player.member, con)
    assert cap == pytest.approx(plain * 1.06, abs=1)
    assert game._battle_neili_cap() == plain
    assert "cap_scale" not in game.state.player.member.model_dump()  # 不進存檔


def test_yunzhuan_discounts_practice_but_not_the_melt_refund(content, world):
    """雲篆：練成的心得 ×0.9、取整最少 1（練滿十成 90 → 81）；熔煉照原價退（library 照舊呼叫 practice_price(content, n)、不傳折扣），
    沒有「練、熔、再練」的迴圈。"""
    from tianxia import team, treasures

    put_shards(content)
    content.config.practice_xinde_per_level = 2  # 正式值（測試內容是 1）：練滿十成 90
    game = _holding(content, world, "yunzhuan")
    scale = treasures.amount(game.state, content, "practice")
    assert sum(team.practice_price(content, n, scale) for n in range(1, 10)) == 81
    assert sum(team.practice_price(content, n) for n in range(1, 10)) == 90
    assert team.practice_price(content, 1, 0.1) == 1


def test_xuanniu_adds_a_talk_turn_and_jinjiao_adds_dodge(content, world):
    from tianxia import team

    put_shards(content)
    game = _holding(content, world, "xuanniu")
    assert game._talk_cap() == content.config.talk_turns_per_day + 1
    other = _holding(content, world, "jinjiao", name="金角客")
    other.state.player.stats["agi"] = 5
    assert team.dodge_chance(other.state, content) == pytest.approx(0.03)


def test_chizhang_is_read_and_guixin_grows_companions(content, world):
    """赤璋：武學重構之後合成不擲品質，改成自創的意分 +5（create.seal_points，底子威力的倍數照它推）；
    歸心：同伴拿到的經驗 ×1.1、取整，本人那一份不變。"""
    from unittest import mock

    from tianxia import team, treasures

    put_shards(content)
    game = _holding(content, world, "chizhang")
    assert treasures.amount(game.state, content, "fuse_points") == 5
    from tianxia import create
    assert create.seal_points(game.state, content) == 5
    guixin = _holding(content, world, "guixin", name="歸心客")
    guixin.state.player.team = ["mate"]  # 測試內容的人物 mate 帶在身邊（grant_team_exp 只讀 team 與 content.characters）
    seen = []
    with mock.patch.object(team, "add_exp", lambda content_, who, amount, name: seen.append(amount) or []):
        team.grant_team_exp(guixin.state, content, world, 10)
    assert seen == [10, 11]  # 本人照舊 10、同伴 round(10 × 1.1)


def test_the_heirloom_is_recopied_before_stamina_regen_and_on_kin_games(content, world):
    """承露照整段離線時間算體力回復：抄本要排在 _advance_player_local 之前（7.4）；別人算你（_kin）時也重抄。
    跟一個同時加入的人比（新手期的倍數兩邊一樣），回的體力剛好多一成。"""
    from tianxia.engine import Game

    put_shards(content)
    plain = Game.new(content, "平人", rng=random.Random(0), world=world)
    plain.sync(0.0)
    game = _holding(content, world, "chenglu")
    plain.state.player.stamina = game.state.player.stamina = 0.0
    game.state.player.heirloom = None  # 模擬抄本還沒抄上（例如剛換季重來的角色）
    later = content.config.stamina_regen_seconds * 10 / content.config.time_scale
    plain.sync(later)
    game.sync(later)
    assert game.state.player.stamina == pytest.approx(plain.state.player.stamina * 1.1)
    copy = game.state.model_copy(deep=True)
    copy.player.heirloom = None  # 存檔裡的抄本過期了：別人建他的 Game（_kin）時照登記重抄
    assert game._kin(copy).state.player.heirloom is not None


def test_the_heirloom_is_not_in_the_rack_and_cannot_be_dismantled(content, world):
    """7.3：傳承那一格不進裝備庫、拆不了（照前綴或照 rack 找東西的函式都碰不到它）。"""
    put_shards(content)
    game = _holding(content, world, "jinjiao")
    assert all(item.id != "璽:jinjiao" for item in game.state.player.rack)
    game.dismantle_weapon("璽:jinjiao")
    assert game.state.player.heirloom is not None and game.state.player.heirloom.id == "璽:jinjiao"


def test_seen_real_is_written_only_by_your_own_request(content, world):
    """「這一季上線過」看 seen_real（5.3）：只有自己的請求（mark_seen）寫，Game.sync 不寫；換季帶著走。"""
    from conftest import next_season
    from tianxia.engine import Game

    game = Game.new(content, "自己", rng=random.Random(0), world=world)
    game.sync(50.0)
    assert game.state.player.seen_real is None and not game.own_request
    game.mark_seen(60.0)
    assert game.state.player.seen_real == 60.0 and game.own_request
    next_season(content, world, game)
    assert game.state.player.seen_real == 60.0


# ── Task 4：舊玉璽鏈 ──

YUXI_EVENTS = {"yuxi_scroll", "yuxi_antique", "yuxi_dig", "yuxi_rival", "yuxi_scholar", "yuxi_guardian"}


def test_season_one_switches_off_the_old_jade_chain(on):
    """11.2 第 1 條：第一季開著時舊鏈的門檻、支線、六則事件、目標、董卓奪璽都關掉；南華觀第一季直接開（黃巾伏筆的丹爐灰在那裡）。"""
    off = on.scenario.season_one_off
    assert {"yuxi_50", "yuxi_100"} <= set(off.thresholds) and "yuxi_line" in off.storylines
    assert YUXI_EVENTS <= set(off.events) and "take_shard" in off.milestones
    assert off.world_events == ["dongzhuo_takes_shard"] and off.unlocks == ["jade_cave"]


def test_a_switched_off_world_event_never_fires_in_season_one(on, world):
    """董卓奪璽（xi_open 滿 48 小時）第一季不觸發，管理者也觸發不了、清單不列。"""
    from tianxia import world as world_rules
    from tianxia.engine import Game

    on.config.admins = ["管理者"]
    game = Game.new(on, "管理者", rng=random.Random(0), world=world)
    w = game.state.world
    w.flags.add("xi_open")
    w.flag_times["xi_open"] = 0.0
    w.time = 49 * 3600.0
    world_rules.check_thresholds(game.state, on, world)
    assert "dongzhuo_takes_shard" not in w.fired_thresholds
    assert world_rules.fire_by_id(game.state, on, "dongzhuo_takes_shard", world) is None
    assert "dongzhuo_takes_shard" not in {f.id for f in game.admin_fires()}


def test_jade_cave_opens_in_season_one_without_the_old_flag(on, world):
    from tianxia import atlas
    from tianxia.engine import Game

    game = Game.new(on, "甲", rng=random.Random(0), world=world)
    cave = on.locations["jade_cave"]
    assert "xi_open" not in game.state.world.flags
    assert atlas.is_unlocked(cave, game.state, on)
    assert not atlas.is_unlocked(cave, game.state)  # 沒給內容：照舊只看旗標


def test_with_the_shards_on_the_old_chain_no_longer_records_a_fragment(real, world):
    """11.2 第 2 條：碎片開著（正式內容有七片）時，打贏看守者不寫舊的跨季紀錄、不回「第 N 塊碎片」；碎片關著照舊記（舊測試就是這樣）。"""
    from tianxia import rules
    from tianxia.engine import Game
    from tianxia.models import Effect

    flag = real.scenario.jade_seal_flag
    game = Game.new(real, "甲", rng=random.Random(0), world=world)
    msgs = rules.apply_effect(Effect(world_flags_add=[flag]), game.state, real, world)
    assert world.get_jade_seal_fragments() == [] and not any("塊碎片" in m for m in msgs)
    real.seal = {}
    game.state.world.flags.discard(flag)
    rules.apply_effect(Effect(world_flags_add=[flag]), game.state, real, world)
    assert len(world.get_jade_seal_fragments()) == 1


# ── Task 5：參戰快照、挑人、現世 ──

def _registry(content, **held):
    """一份補齊七片、有密鹽的登記；held 是 片 id → 持有者（since_season 0）。"""
    from tianxia import seal
    from tianxia.world_state import SealRegistry

    reg = seal.filled(SealRegistry(salt=SALT), content)
    for shard_id, name in held.items():
        reg.shards[shard_id].state, reg.shards[shard_id].holder, reg.shards[shard_id].since_season = "held", name, 0
    return reg


def _ended(battle_id, rows, rounds=9, record=7, **seal_fields):
    """收場的決戰：rows 是（名號, 陣營, 自己出手幾回合, 帶頭佔上風幾回合）；戰功照 Joy 的 merit_points（出手 2、帶頭 3）。"""
    from tianxia.battle_instance import BattleInstance, BattleParticipant

    parts = {
        name: BattleParticipant(name=name, faction=side, neili=300.0, neili_cap=300.0, power=60.0, acted_rounds=acted,
                                led_rounds=led, scores={"強攻": 50.0, "固守": 50.0, "奇襲": 50.0})
        for name, side, acted, led in rows
    }
    return BattleInstance(battle_id=battle_id, phase="ended", participants=parts, round_number=rounds, record_id=record, **seal_fields)


def test_joining_snapshots_turncoat_and_newbie(sealed, world):
    """參戰者加入時快照「這一季叛投過」與「新手期」（4.6），挑挑戰者只讀快照。"""
    from tianxia import battle_instance
    from tianxia.battle_instance import BattleInstance
    from tianxia.engine import Game

    game = Game.new(sealed, "甲", rng=random.Random(0), world=world)
    game.state.player.defected = True
    marks = game._battle_marks()
    # 新角色還在新手期；沒有本命戰法；稱號（名聲 2.5）測試內容關著
    assert marks == {"turncoat": True, "newbie": True, "kit": None, "renown": [], "escort": None}  # 沒派同伴（歷史武將同行）
    b = BattleInstance(battle_id="changshe_fire")
    battle_instance.join_faction(b, "甲", "guan", 300.0, **marks)
    assert (b.participants["甲"].turncoat, b.participants["甲"].newbie) == (True, True)
    battle_instance.join_faction(b, "乙", "guan", 300.0)
    assert (b.participants["乙"].turncoat, b.participants["乙"].newbie) == (False, False)  # 舊的呼叫法照舊


def test_emergence_rolls_its_own_dice_once_a_season(sealed):
    """3.2：一季最多一片；照密鹽＋天機＋季別擲 35%，挑還沒現世過的；管理者強制現世略過機率。"""
    from tianxia import seal

    reg = _registry(sealed)
    hits = [s for s in range(1, 200) if seal.roll_emerge(reg, sealed, s, 0) is not None]
    assert 0.25 < len(hits) / 199 < 0.45
    reg.emerge_season = hits[0]
    assert seal.roll_emerge(reg, sealed, hits[0], 0) is None
    reg.force_emerge = "*"
    assert seal.roll_emerge(reg, sealed, 999, 0) is not None
    for shard in reg.shards.values():
        shard.state = "held"
    assert seal.roll_emerge(reg, sealed, 1000, 0) is None  # 這一輪都現世過了


def test_the_round_threshold_relaxes_on_a_small_battle(sealed):
    """min(3, 實打回合)；參戰名單不到 10 人時放寬到 1 回合（PM 癸）。"""
    from tianxia import seal

    cfg = sealed.config.seal
    twelve = [(f"人{i}", "guan", 1, 0) for i in range(12)]
    assert seal.threshold(_ended("wancheng_jia", twelve, rounds=2), cfg) == 2
    assert seal.threshold(_ended("wancheng_jia", twelve, rounds=9), cfg) == 3
    assert seal.threshold(_ended("wancheng_jia", [("甲", "guan", 1, 0)], rounds=9), cfg) == 1


def test_the_pick_takes_the_top_three_by_merit_and_prefers_the_former_holder_only_inside():
    from tianxia import seal

    rows = [("甲", 30), ("乙", 20), ("丙", 10), ("丁", 5)]
    assert {seal.weighted_pick(rows, random.Random(i), 3) for i in range(200)} == {"甲", "乙", "丙"}
    assert seal.weighted_pick(rows, random.Random(0), 3, prefer="乙") == "乙"
    assert seal.weighted_pick(rows, random.Random(0), 3, prefer="丁") in {"甲", "乙", "丙"}  # 前主不在前三名：不插隊
    assert seal.weighted_pick([("甲", 0), ("乙", 0)], random.Random(0), 3) in {"甲", "乙"}  # 戰功都是 0：平均抽
    assert seal.weighted_pick([], random.Random(0), 3) is None


def test_wancheng_raises_a_shard_at_muster_when_the_dice_say_so(sealed, world):
    """宛城（標 emerge）開集結：擲中就記在這一場（seal_emerge），天下大事多一句異光。"""
    from tianxia import seal
    from tianxia import world as world_rules

    world.seed_first_season(sealed)
    world.mutate(lambda st: setattr(seal.filled(st.seal, sealed), "force_emerge", "yunzhuan"))
    msgs = world_rules.open_showdown(world, sealed, "wancheng", 0.0)
    battle = world.get_battle()
    assert battle.seal_emerge == "yunzhuan" and battle.battle_id.startswith("wancheng")
    assert any("集結號角" in m for m in msgs)
    assert any("異光" in r.text for r in world.get_season().rumors if r.layer == "world")
    assert world.seal_state().registry.force_emerge is None  # 強制現世用掉了


def test_a_winner_of_the_emergence_is_drawn_from_the_winning_side_by_merit(sealed, world):
    """3.3：勝方、自己出手滿門檻、手上沒有碎片的人裡照戰功前三名抽；登記寫上他、這一季有新主保護；天下大事與江湖史各一句；
    不碰 Game.rng（誰觸發收場結果都一樣）。"""
    from tianxia.engine import Game

    world.mutate(lambda st: setattr(st, "seal", _registry(sealed, chishou="懷璽")))
    game = Game.new(sealed, "旁人", rng=random.Random(0), world=world)
    battle = _ended("wancheng_jia", [("甲", "guan", 9, 3), ("乙", "guan", 9, 0), ("懷璽", "guan", 9, 9), ("丙", "huang", 9, 9)],
                    seal_emerge="yunzhuan")
    before = game.rng.getstate()
    game._seal_settle(battle, sealed.battles["wancheng_jia"], {"side": "guan", "margin": "險勝"})
    assert game.rng.getstate() == before
    view = world.seal_state()
    shard = view.registry.shards["yunzhuan"]
    assert shard.state == "held" and shard.holder in {"甲", "乙"} and shard.since_season == view.season
    assert view.registry.emerge_season == view.season and view.registry.history[-1].kind == "emerge"
    season = world.get_season()
    assert any(shard.holder in r.text and "雲篆" in r.text for r in season.rumors if r.layer == "world")
    assert any("雲篆" in r.text for r in season.chronicle)


def test_nobody_eligible_lets_the_shard_sink_back(sealed, world):
    """落空（沒有合格的人、保底收場）：這一季不算現世，那一片照舊未現世；只寫天下大事。"""
    from tianxia.engine import Game

    world.mutate(lambda st: setattr(st, "seal", _registry(sealed)))
    game = Game.new(sealed, "旁人", rng=random.Random(0), world=world)
    battle = _ended("wancheng_jia", [("甲", "guan", 0, 0)], rounds=1, seal_emerge="yunzhuan")
    game._seal_settle(battle, sealed.battles["wancheng_jia"], {"side": "guan", "margin": "大勝"})
    reg = world.seal_state().registry
    assert reg.shards["yunzhuan"].state == "hidden" and reg.emerge_season is None
    assert any("沉入了地底" in r.text for r in world.get_season().rumors)


def test_a_battle_nobody_could_fight_to_the_end_raises_nothing(sealed, world):
    """保底收場（兩軍都沒人還能打，end_without_fighters）：出手夠的人也不給，現世落空（設計 3.3、4.5 邊界 3）。"""
    from tianxia.engine import Game

    world.mutate(lambda st: setattr(st, "seal", _registry(sealed)))
    game = Game.new(sealed, "旁人", rng=random.Random(0), world=world)
    battle = _ended("wancheng_jia", [("甲", "guan", 3, 0)], seal_emerge="yunzhuan")
    battle.participants["甲"].eliminated = True
    game._seal_settle(battle, sealed.battles["wancheng_jia"], {"side": "guan", "margin": "大勝"})
    assert world.seal_state().registry.shards["yunzhuan"].state == "hidden"


# ── Task 6：璽動 ──

def test_stirring_skips_protected_shards_and_stops_at_the_season_cap(sealed):
    """4.1、4.2：每片各擲 7%（照密鹽＋天機＋event_id＋片），一場最多一片；新主保護、每片每季一次、全服一季兩次；管理者強制璽動略過。"""
    from tianxia import seal

    reg = _registry(sealed, chishou="甲", xuanniu="乙")
    rolls = [seal.roll_stir(reg, sealed, 5, t, "changshe_fire") for t in range(400)]
    assert 0.09 < sum(r is not None for r in rolls) / 400 < 0.19  # 兩片各 7%：1 − 0.93² ≈ 13.5%
    reg.shards["chishou"].since_season = 5  # 這一季才到手
    assert all(seal.roll_stir(reg, sealed, 5, t, "changshe_fire") in (None, "xuanniu") for t in range(200))
    reg.shards["xuanniu"].stirred_season = 5  # 這一季動過了
    assert all(seal.roll_stir(reg, sealed, 5, t, "changshe_fire") is None for t in range(200))
    reg = _registry(sealed, chishou="甲")
    seal.log(reg, 6, "stir", shard="xuanniu")
    seal.log(reg, 6, "stir", shard="yunzhuan")
    assert all(seal.roll_stir(reg, sealed, 6, t, "guangzong") is None for t in range(200))  # 全服這一季已經兩次
    reg.force_stir = "chishou"
    assert seal.roll_stir(reg, sealed, 6, 0, "guangzong") == "chishou"


def test_the_four_tiers_from_the_holder_side():
    from tianxia import seal

    assert seal.tier_for("guan", "guan", "大勝") == "大勝" and seal.tier_for("guan", "guan", "險勝") == "險勝"
    assert seal.tier_for("guan", "huang", "險勝") == "險敗" and seal.tier_for("guan", "huang", "大勝") == "大敗"
    assert seal.tier_for(None, "huang", "大勝") == "旁觀"


def test_a_stir_snapshots_the_holder_and_his_faction_at_muster(sealed, world):
    """4.3：擲中時登記記 stirred_season、天下大事一句（具名）；這一場快照 seal_shard、seal_holder、seal_holder_faction（投靠名冊，
    不讀存檔）、seal_holder_side（是交戰兩方之一才記）。"""
    from tianxia import world as world_rules

    world.seed_first_season(sealed)
    reg = _registry(sealed, chishou="懷璽")
    reg.force_stir = "chishou"
    world.mutate(lambda st: setattr(st, "seal", reg))
    world.record_faction("懷璽", "huang")
    world_rules.open_showdown(world, sealed, "changshe_fire", 0.0)
    b = world.get_battle()
    assert (b.seal_shard, b.seal_holder, b.seal_holder_faction, b.seal_holder_side) == ("chishou", "懷璽", "huang", "huang")
    view = world.seal_state()
    assert view.registry.shards["chishou"].stirred_season == view.season and view.registry.force_stir is None
    assert any("懷璽" in r.text and "螭首" in r.text for r in world.get_season().rumors if r.layer == "world")


def test_a_free_or_absent_holder_is_snapshotted_as_a_bystander(sealed, world):
    """散人、這一季還沒上線過（名冊上沒有他）：陣營快照 None、算旁觀，不讀存檔裡上一季的 p.faction（4.2 第 4 條）。"""
    from tianxia import world as world_rules

    world.seed_first_season(sealed)
    reg = _registry(sealed, chishou="懷璽")
    reg.force_stir = "chishou"
    world.mutate(lambda st: setattr(st, "seal", reg))
    world_rules.open_showdown(world, sealed, "changshe_fire", 0.0)
    b = world.get_battle()
    assert (b.seal_holder_faction, b.seal_holder_side) == (None, None)


def test_the_top_merit_on_both_sides_hear_they_may_be_pushed_forward(sealed):
    """4.3 最後一條：被璽動的那一場，兩邊合格的前三名各收到一句（持有者本人與快照陣營相同的人不收）。"""
    from tianxia import seal

    battle = _ended("changshe_fire", [("甲", "guan", 3, 2), ("乙", "guan", 3, 0), ("懷璽", "guan", 3, 3), ("丙", "huang", 3, 0)],
                    rounds=3, seal_shard="chishou", seal_holder="懷璽", seal_holder_faction="guan", seal_holder_side="guan")
    battle.phase = "active"
    assert seal.hint_names(battle, sealed, set()) == {"丙"}
    battle.seal_holder_faction = battle.seal_holder_side = None  # 持有者是散人：兩邊都提示（他自己不收）
    assert seal.hint_names(battle, sealed, set()) == {"甲", "乙", "丙"}



def test_the_hint_and_the_pick_use_one_rule_fb177(sealed):
    """FB-177：畫面那一句（hint_names）與挑挑戰者（Game._seal_challengers）照同一個條件 seal.challenger_ok：倒下的照樣在內
    （挑人本來就不看倒下）；叛投過、新手期、補位的機器人兩邊都不算（以前畫面那一句沒擋叛投與新手，會跟挑人對不上）。"""
    from tianxia import seal

    battle = _ended("changshe_fire", [("甲", "huang", 3, 2), ("乙", "huang", 3, 1), ("丙", "huang", 3, 0), ("懷璽", "guan", 3, 3)],
                    rounds=3, seal_shard="chishou", seal_holder="懷璽", seal_holder_faction="guan", seal_holder_side="guan")
    battle.phase = "active"
    battle.participants["甲"].eliminated = True
    battle.participants["乙"].turncoat = True
    assert seal.hint_names(battle, sealed, set()) == {"甲", "丙"}
    need = seal.threshold(battle, sealed.config.seal)
    assert [seal.challenger_ok(p, need, set(), "懷璽") for p in battle.participants.values()] == [True, False, True, False]


def test_a_fallen_fighter_still_hears_the_merit_hint_fb177(sealed, world):
    """FB-177：倒下的人照樣可能被挑上陣前，畫面也寫「你此役戰功居前…」；跟倒下無關的那幾句（盯上你、牽制、放手一搏、顯眼）倒下了不寫。"""
    from tianxia import seal
    from tianxia.engine import Game

    game = Game.new(sealed, "甲", rng=random.Random(0), world=world)
    battle = _ended("changshe_fire", [("甲", "huang", 3, 2), ("懷璽", "guan", 3, 3)], rounds=3, seal_shard="chishou",
                    seal_holder="懷璽", seal_holder_faction="guan", seal_holder_side="guan")
    battle.phase = "active"
    p = battle.participants["甲"]
    p.eliminated = True
    battle.last_targets["甲"] = ["懷璽"]
    assert game._battle_spotlight(battle, sealed.battles["changshe_fire"], p) == [seal.MERIT_HINT]
    p.eliminated = False
    assert game._battle_spotlight(battle, sealed.battles["changshe_fire"], p)[0] == "懷璽盯上了你。"


def test_the_battle_scene_and_report_mention_the_stir(sealed, world):
    from tianxia import seal
    from tianxia.engine import Game

    game = Game.new(sealed, "旁觀者", rng=random.Random(0), world=world)
    battle = _ended("changshe_fire", [("旁觀者", "guan", 3, 0)], rounds=3, seal_shard="chishou", seal_holder="懷璽")
    battle.phase = "muster"
    text = game._battle_scene_text(battle, sealed.battles["changshe_fire"])
    assert seal.STIR_SCENE.format(holder="懷璽", shard="螭首") in text
    battle.phase, battle.seal_notes = "ended", ["璽動：丙將與懷璽的懷璽陣前單挑。"]
    game._file_showdown(battle, battle.participants["旁觀者"], None)
    assert "璽動：丙將與懷璽的懷璽陣前單挑。" in game.state.battles[0].notes


# ── Task 10：隱沒 ──

def test_a_shard_sinks_only_after_three_absent_seasons_and_twenty_eight_days(sealed):
    """PM 庚：連續三季沒上線、而且距上次上線滿 28 天才隱沒；上線了就歸零；opened_real 是 None 不動；查不到那一列（None）照沉。"""
    from tianxia import seal

    cfg = sealed.config.seal
    day = 86400.0
    reg = _registry(sealed, chishou="甲", xuanniu="乙")
    reg.opened_real = 100 * day
    for season in (2, 3):
        assert seal.sink(reg, season, {"甲": 50 * day, "乙": 101 * day}, 110 * day, cfg) == []
    assert (reg.shards["chishou"].absent, reg.shards["xuanniu"].absent) == (2, 0)
    sunk = seal.sink(reg, 4, {"甲": 50 * day, "乙": 101 * day}, 110 * day, cfg)
    assert [(s.id, name) for s, name in sunk] == [("chishou", "甲")] and reg.shards["chishou"].state == "sunk"
    assert reg.shards["chishou"].holder is None and reg.history[-1].kind == "sink"
    reg2 = _registry(sealed, chishou="甲")
    reg2.opened_real = 100 * day
    reg2.shards["chishou"].absent = 2
    assert seal.sink(reg2, 4, {"甲": 99 * day}, 110 * day, cfg) == []  # 三季沒上線，但距上次上線還不到 28 天
    reg2.opened_real = None
    assert seal.sink(reg2, 5, {"甲": None}, 300 * day, cfg) == [] and reg2.shards["chishou"].absent == 3  # 判斷不了：不動


def test_next_season_sinks_absent_holders_and_clears_the_duels(sealed, world):
    """7.6、5.11：換季那一筆交易裡判隱沒（江湖史只寫「不知所蹤」）、清空 seal_duels（還沒收場的記成未分勝負）、寫新的 opened_real。"""
    from conftest import next_season
    from tianxia import seal
    from tianxia.engine import Game
    from test_seal_duel import _duel

    world.seed_first_season(sealed)
    if world.season_phase() == "preparing":
        world.open_season(sealed, 0.0)
    reg = _registry(sealed, chishou="不見人")
    reg.opened_real = 0.0
    reg.shards["chishou"].absent = 2
    world.mutate(lambda st: (setattr(st, "seal", reg), st.seal_duels.append(_duel())))
    game = Game.new(sealed, "路人", rng=random.Random(0), world=world)
    next_season(sealed, world, game)  # 「不見人」那一列不存在：當成沒上線、而且滿 28 天
    view = world.seal_state()
    assert view.registry.shards["chishou"].state == "sunk" and view.duels == []
    assert {"sink", "unsettled"} <= {e.kind for e in view.registry.history}
    assert any("不知所蹤" in line for _, entries in world.chronicle_before(view.season) for line in [r.text for r in entries])


# ── FB-695（2026-10-31 從 tests/seal/test_seal_fb695_rollback.py 併進來）────────
# FB-695：起用過碎片的獨門行動之後，退回舊程式（main 54802f52、1d12fa6c）一啟動就讀不進 world 那一列——起用記在全服登記的
# history、kind 是 "use"，舊程式的 SealEvent.kind 是 Literal、不認得它（pydantic 驗證錯，伺服器與假人程式都起不來）。
#
# 修法（PM 2026-10-22）：起用另記在 SealRegistry.uses（舊程式的登記模型沒有這一欄，pydantic 預設略過不認得的欄位）；讀檔時把舊資料
# history 裡 kind "use" 的搬過去，搬完 history 不留 use；沒人起用過時 JSON 不多 uses 這個鍵（存檔一個位元組都不變）。
#
# OLD_* 是舊程式（54802f52 與 1d12fa6c 兩版一樣）tianxia/world_state.py 的登記模型原樣抄下來的：新程式寫進資料庫的登記，舊程式那一版的
# 模型要讀得進來。舊程式的伺服器與假人程式真的開同一份資料庫，實測寫在試玩回饋 FB-695 那一列。


# ── 舊程式的登記模型（54802f52／1d12fa6c 的 world_state.py，原樣；不要跟著新程式改）──


class OldSealEvent(BaseModel):
    seq: int
    season: int
    kind: Literal["emerge", "stir", "keep", "take", "sink", "unsettled", "assign", "recall", "scatter", "mandate"]
    shard: str | None = None
    holder: str | None = None
    other: str | None = None
    record: int | None = None
    where: str = ""
    result: str | None = None
    fresh: bool = False
    proxied: list[str] = Field(default_factory=list)
    absent: list[str] = Field(default_factory=list)
    at: float | None = None
    lines: list[str] = Field(default_factory=list)
    edge: float | None = None
    round: int | None = None
    holders: dict[str, str] = Field(default_factory=dict)
    text: str = ""


class OldSealShard(BaseModel):
    id: str
    state: Literal["hidden", "held", "sunk"] = "hidden"
    holder: str | None = None
    since_season: int | None = None
    stirred_season: int | None = None
    emerged_round: int | None = None
    former: str | None = None
    absent: int = 0


class OldSealCache(BaseModel):
    season: int
    shard: str
    loc: str


class OldSealRegistry(BaseModel):
    shards: dict[str, OldSealShard] = Field(default_factory=dict)
    round: int = 1
    seq: int = 0
    opened_real: float | None = None
    salt: str = ""
    emerge_season: int | None = None
    force_emerge: str | None = None
    force_stir: str | None = None
    last_showdown: int | None = None
    last_showdown_dueled: bool = False
    last_showdown_where: str = ""
    mandate_season: int | None = None
    mandate_pending: bool = False
    cache: OldSealCache | None = None
    history: list[OldSealEvent] = Field(default_factory=list)


def _old_use(seq: int, holder: str, act: str, what: str, at: float, *, shard: str = "yunzhuan", season: int = 1) -> dict:
    """FB-695 以前的新程式（main 3e69e094）寫進 history 的那一筆，欄位與順序照 SealEvent.model_dump_json。"""
    return {"seq": seq, "season": season, "kind": "use", "shard": shard, "holder": holder, "other": None, "record": None,
            "where": what, "result": act, "fresh": False, "proxied": [], "absent": [], "at": at, "lines": [], "edge": None,
            "round": 1, "holders": {}, "text": ""}


def _event(seq: int, kind: str, **fields) -> dict:
    return json.loads(SealEvent(seq=seq, season=1, kind=kind, round=1, **fields).model_dump_json())


# ── 純模型 ──

def test_history_only_has_kinds_the_old_program_knows():
    """history 的 kind 跟舊程式一樣：多一種，退回舊程式整列 world 就讀不進來（FB-695）。要加新的紀錄另開欄位（空的時候不寫）。"""
    assert set(get_args(SealEvent.model_fields["kind"].annotation)) == set(get_args(OldSealEvent.model_fields["kind"].annotation))
    with pytest.raises(ValidationError):
        seal.log(SealRegistry(), 1, "use", shard="yunzhuan", holder="懷璽")


@pytest.mark.smoke
def test_no_uses_writes_the_same_bytes_as_before():
    """沒人起用過：登記的 JSON 不多 uses 這個鍵，跟舊程式的模型寫出來的一個位元組都不差。"""
    reg = SealRegistry.model_validate({"seq": 2, "salt": "鹽", "shards": {"yunzhuan": {"id": "yunzhuan", "state": "held", "holder": "甲"}},
                                       "history": [_event(1, "emerge", shard="yunzhuan", holder="甲", text="現世"), _event(2, "stir", shard="yunzhuan")]})
    raw = reg.model_dump_json()
    assert "uses" not in json.loads(raw)
    # 舊模型照同一份資料寫出來的（新程式多的 act_* 三欄是舊程式不認得的，拿掉再比）
    shards = {k: {f: v for f, v in s.items() if not f.startswith("act_")} for k, s in json.loads(raw)["shards"].items()}
    assert OldSealRegistry.model_validate_json(raw).model_dump_json() == json.dumps(
        {**json.loads(raw), "shards": shards}, ensure_ascii=False, separators=(",", ":"))
    assert SealRegistry().model_dump_json() == OldSealRegistry().model_dump_json()


def test_empty_uses_leave_no_key_on_any_pydantic_2():
    """uses 空的時候不寫這個鍵，不靠 Pydantic 的版本：Field(exclude_if=…) 是 2.11 才有的，requirements.txt 寫 pydantic>=2.6，舊版把它當多餘的
    參數略過、`"uses":[]` 照寫，存檔就跟以前不一樣。所以靠的是 SealRegistry 自己的 wrap serializer（_drop_empty_uses，同
    BattleInstance._drop_empty_front_note）：這一欄沒掛 exclude_if、tianxia 裡沒有任何呼叫帶 exclude_if，JSON 與 Python 兩種寫法、
    包在 SharedWorldState 裡（world 那一列的寫法）都沒有 uses；有一筆才寫。"""
    import ast
    from pathlib import Path

    from tianxia.world_state import SharedWorldState

    assert getattr(SealRegistry.model_fields["uses"], "exclude_if", None) is None
    used = []
    for path in sorted(Path(seal.__file__).resolve().parent.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and any(k.arg == "exclude_if" for k in node.keywords):
                used.append(f"{path.name}:{node.lineno}")
    assert used == []
    reg = SealRegistry(seq=1, history=[SealEvent(seq=1, season=1, kind="emerge", shard="yunzhuan")])
    assert "uses" not in json.loads(reg.model_dump_json()) and "uses" not in reg.model_dump()
    row = json.loads(SharedWorldState(seal=reg).model_dump_json(exclude={"season", "active_battle", "sieges"}))
    assert "uses" not in row["seal"] and "uses" not in SharedWorldState(seal=reg).model_dump()["seal"]
    seal.log_use(reg, 1, shard="yunzhuan", holder="甲", act="banzhao", what="", at=5.0)
    assert [u["holder"] for u in json.loads(reg.model_dump_json())["uses"]] == ["甲"] and len(reg.model_dump()["uses"]) == 1


def test_a_use_goes_to_its_own_list_that_the_old_model_skips():
    reg = SealRegistry(seq=1, history=[SealEvent(seq=1, season=1, kind="emerge", shard="yunzhuan", holder="甲")])
    used = seal.log_use(reg, 1, shard="yunzhuan", holder="甲", act="banzhao", what="", at=50.0)
    assert (used.seq, reg.seq) == (2, 2) and [e.kind for e in reg.history] == ["emerge"]
    assert [(u.seq, u.season, u.shard, u.holder, u.act, u.what, u.at) for u in reg.uses] == [(2, 1, "yunzhuan", "甲", "banzhao", "", 50.0)]
    raw = reg.model_dump_json()
    assert json.loads(raw)["uses"][0]["holder"] == "甲"
    old = OldSealRegistry.model_validate_json(raw)  # 舊程式略過 uses
    assert [e.kind for e in old.history] == ["emerge"] and old.seq == 2
    assert SealRegistry.model_validate_json(raw).uses == reg.uses  # 新程式讀回來一樣


def test_old_use_records_in_history_move_to_uses_on_read():
    """FB-695 以前的新程式寫的：history 裡的 use 讀進來搬到 uses（照流水號、欄位照原本的意思換），history 只剩舊程式認得的。"""
    raw = json.dumps({"seq": 4, "history": [
        _event(1, "emerge", shard="yunzhuan", holder="甲"), _old_use(2, "甲", "banzhao", "", 30.0),
        _event(3, "assign", shard="xuanniu", holder="乙"), _old_use(4, "乙", "yinjiang", "波才", 40.0, shard="xuanniu"),
    ]}, ensure_ascii=False)
    with pytest.raises(ValidationError):
        OldSealRegistry.model_validate_json(raw)  # 修之前的資料：舊程式讀不進來（QA 重現的那一個錯）
    reg = SealRegistry.model_validate_json(raw)
    assert [(e.seq, e.kind) for e in reg.history] == [(1, "emerge"), (3, "assign")]
    assert [(u.seq, u.holder, u.shard, u.act, u.what, u.at) for u in reg.uses] == [
        (2, "甲", "yunzhuan", "banzhao", "", 30.0), (4, "乙", "xuanniu", "yinjiang", "波才", 40.0)]
    assert reg.seq == 4
    again = reg.model_dump_json()
    assert '"use"' not in json.dumps(json.loads(again)["history"])
    assert len(OldSealRegistry.model_validate_json(again).history) == 2  # 搬完之後舊程式讀得進來
    assert SealRegistry.model_validate_json(again) == reg  # 再讀一次不變


def test_a_half_moved_registry_keeps_one_copy_per_number():
    """兩邊都有（uses 已經有、history 又出現同一號）：同一號只留一筆；不同號照流水號排。"""
    raw = json.dumps({"seq": 3, "uses": [{"seq": 2, "season": 1, "shard": "yunzhuan", "holder": "甲", "act": "banzhao", "what": "", "at": 30.0}],
                      "history": [_old_use(2, "甲", "banzhao", "", 30.0), _old_use(3, "甲", "banzhao", "", 90.0)]}, ensure_ascii=False)
    reg = SealRegistry.model_validate_json(raw)
    assert [u.seq for u in reg.uses] == [2, 3] and reg.history == []


# ── 正式內容：七種行動都起用過，舊程式的模型讀得進資料庫裡那一列（標 slow） ──

def _raw_seal(w) -> str:
    con = sqlite3.connect(str(w.db.path))
    try:
        return con.execute("SELECT json_extract(data, '$.seal') FROM world WHERE id = 1").fetchone()[0]
    finally:
        con.close()


@pytest.mark.slow
def test_after_all_seven_acts_the_old_model_still_reads_the_world_row():
    from test_seal_acts import _do, _give, _person
    from test_seal_acts3 import _season, _world

    from conftest import no_plans

    from tianxia import conquest

    c, w = _world()  # 21 天季＋領地爭奪打開：鎮地、補缺才起用得了
    no_plans(c)  # 引將要引的波才，行程開著時一開季就先被帶到長社（盤算公告）：「已經在這裡」，起用不成
    c.config.admins = ["管理"]
    cases = [  # 碎片、持有者、站哪、目標
        ("xuanniu", "甲客", "changshe", "bocai"), ("yunzhuan", "乙客", "yingchuan_wilds", ""),
        ("chenglu", "丙客", "yingchuan_wilds", ""), ("chizhang", "丁客", "yingchuan_wilds", "yingru"),
        ("guixin", "戊客", "yingchuan_wilds", "caocao"), ("jinjiao", "己客", "runan", "runan"),
        ("chishou", "庚客", "runan_academy", "runan_academy"),
    ]
    for shard, name, at, _ in cases:
        _give(c, w, shard, name)
        _person(c, w, name, side="huang", at=at)
    admin = _person(c, w, "管理", side=None)
    _season(c, w, lambda wd: conquest.push(wd, c, "runan", "guan", "官甲", 100, "attack"), now=100.0, name="己客")  # 汝南被官軍翻走
    for i, (shard, name, _, target) in enumerate(cases):
        msgs = _do(c, w, name, lambda g, t=target: g.seal_use(t), now=3800.0 + i)
        assert msgs and "還能再起用 1 次" in msgs[0], (shard, msgs)
    raw = _raw_seal(w)
    old = OldSealRegistry.model_validate_json(raw)  # 修之前這裡是 ValidationError（seal.history.N.kind）
    assert "use" not in {e.kind for e in old.history}
    reg = w.seal_state().registry
    assert [(u.holder, u.shard, u.act) for u in reg.uses] == [(name, shard, c.seal[shard].act) for shard, name, _, _ in cases]
    assert {sid: reg.shards[sid].act_uses for sid, *_ in cases} == {sid: 1 for sid, *_ in cases}
    rows = _do(c, w, "管理", lambda g: g.admin_seal_choices()["uses"], now=4000.0)
    assert [r["who"] for r in rows] == [name for _, name, _, _ in cases] and all(r["when"] for r in rows)
    assert admin is not None


@pytest.mark.slow
def test_a_database_with_old_use_records_reads_and_behaves_the_same():
    """內測資料庫有 FB-695 以前寫的 history use：讀進來搬過去，管理者看到的、次數、間隔都跟搬之前一樣；寫回時 history 不留 use。"""
    from test_seal_acts import _do, _holder, _person, _use

    from tianxia.calendar import DAY

    c, w, g = _holder("yunzhuan")
    c.config.admins = ["管理"]
    _person(c, w, "管理")
    _use(c, w, now=10.0)
    before = _do(c, w, "管理", lambda game: game.admin_seal_choices()["uses"], now=20.0)
    # 把資料庫改回 FB-695 以前的樣子：uses 拿掉、同一筆照舊的寫法插回 history
    data = json.loads(_raw_seal(w))
    [u] = data.pop("uses")
    data["history"] = sorted([*data["history"], _old_use(u["seq"], u["holder"], u["act"], u["what"], u["at"], season=u["season"])],
                             key=lambda e: e["seq"])
    con = sqlite3.connect(str(w.db.path))
    with con:
        con.execute("UPDATE world SET data = json_set(data, '$.seal', json(?)) WHERE id = 1", (json.dumps(data, ensure_ascii=False),))
    con.close()
    with pytest.raises(ValidationError):
        OldSealRegistry.model_validate_json(_raw_seal(w))  # 改回去的樣子舊程式確實讀不進來
    assert [x.seq for x in w.seal_state().registry.uses] == [u["seq"]] and not any(e.kind == "use" for e in w.seal_state().registry.history)
    assert _do(c, w, "管理", lambda game: game.admin_seal_choices()["uses"], now=20.0) == before
    assert "之後才能再起用" in _use(c, w, now=10.0 + DAY)[0]  # 間隔照舊
    w.mutate(lambda st: None)  # 任何一次寫回（伺服器、假人程式啟動時的 ensure_salt 也是）就存成新的樣子
    assert [e.kind for e in OldSealRegistry.model_validate_json(_raw_seal(w)).history] == [
        e["kind"] for e in data["history"] if e["kind"] != "use"]
    assert "還能再起用 0 次" in _use(c, w, now=10.0 + 3 * DAY + 1)[0]  # 第二次照常，次數照舊算
    assert [x.holder for x in w.seal_state().registry.uses] == ["懷璽", "懷璽"]
