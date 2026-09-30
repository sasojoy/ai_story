import json
import random
from collections import Counter

import pytest

from conftest import FixedRandom
from tianxia import gacha, roster
from tianxia.engine import Game
from tianxia.models import CharacterDef, in_gacha_pool
from tianxia.save import load_game
from tianxia.state import Member, Pull, new_game_state

# 固定亂數抽到的品階（夾具的機率照預設：天 3、地 12、玄 35、黃 50，依天地玄黃累加）
TIAN, DI, XUAN, HUANG = 0.01, 0.1, 0.3, 0.99


class Scripted(random.Random):
    """random() 依序回傳 values，用完之後一直回傳最後一個：每一抽的品階可以預先排好。
    每一抽用兩個：先擲品階，再在同品階裡挑一位（夾具每個品階只有一人，第二個值是多少都一樣）。"""

    def __init__(self, *values: float):
        super().__init__(0)
        self.values = list(values)

    def random(self) -> float:
        return self.values.pop(0) if len(self.values) > 1 else self.values[0]


def join(state, *keys):
    for key in keys:
        state.player.members[key] = Member()
        state.player.loadouts[key] = [None, None]


def tiers(state, content):
    return [content.characters[x.character].tier for x in state.player.gacha_last]


@pytest.fixture
def rich(state):
    state.player.yuanbao = 5000
    return state


# ── 卡池、價格與機率 ─────────────────────────────────────


def test_pool_lists_everyone_marked_for_zhaoxian(content):
    """開局的韓鐵、只能收徒的書生、只能招降的頭目都不在卡池裡。"""
    assert gacha.pool(content) == {"天": ["sage"], "地": ["hero"], "玄": ["friend"], "黃": ["pupil"]}


def test_the_pool_predicate_is_shared_and_needs_a_companion_tier(content):
    """卡池與載入時的檢查用同一個判斷（models.in_gacha_pool）；敵人就算寫了「招賢」也不算。"""
    listed = {cid for ids in gacha.pool(content).values() for cid in ids}
    assert listed == {cid for cid, ch in content.characters.items() if in_gacha_pool(ch)}
    thug = content.characters["thug"].model_dump()
    assert not in_gacha_pool(CharacterDef(**{**thug, "sources": ["招賢"]}))
    assert in_gacha_pool(CharacterDef(**{**thug, "tier": "黃", "sources": ["招賢"]}))


def test_pulls_are_refused_without_enough_yuanbao_or_after_the_season(state, content):
    assert gacha.block(state, content, 1) == "元寶不足，要 100"
    state.player.yuanbao = 999
    assert gacha.block(state, content, 1) == ""
    assert gacha.block(state, content, 10) == "元寶不足，要 1000"
    assert gacha.block(state, content, 5) == "沒有這種抽法"
    state.world.ended = True
    assert gacha.block(state, content, 1) == "賽季已落幕"


def test_rates_follow_the_config(state, content):
    rng = random.Random(7)
    counts = Counter(gacha.roll_tier(state, content, rng) for _ in range(20000))
    for tier, rate in content.config.gacha_rates.items():
        assert abs(counts[tier] / 20000 - rate / 100) < 0.015, counts
    assert state.player.gacha_pity == 0  # 只擲品階，不算一抽


def test_everyone_in_a_tier_is_equally_likely(content):
    content.characters["scholar"].sources.append("招賢")  # 玄品多一位書生
    assert gacha.pool(content)["玄"] == ["scholar", "friend"]
    state = new_game_state(content, "沈浪")
    state.player.yuanbao = 100 * 2000
    rng = random.Random(3)
    counts = Counter()
    for _ in range(2000):
        state.player.gacha_pity = 0  # 不讓保底插進來
        gacha.pull(state, content, rng, 1)
        counts[state.player.gacha_last[0].character] += 1
    assert 0.4 <= counts["scholar"] / (counts["scholar"] + counts["friend"]) <= 0.6, counts


# ── 抽到新人 ───────────────────────────────────────────


def test_a_single_pull_costs_yuanbao_and_brings_someone_new(rich, content):
    msgs = gacha.pull(rich, content, FixedRandom(HUANG), 1)
    p = rich.player
    assert (p.yuanbao, p.gacha_pity) == (4900, 1)
    assert p.gacha_last == [Pull(character="pupil", new=True)]
    assert roster.where(rich, "pupil") == "候補"
    assert msgs == ["元寶 -100", "【小六】入門（黃品・快・統御 2），從第 1 級練起，先列候補。"]


def test_newcomers_join_at_the_lowest_level_in_the_teams(rich, content):
    p = rich.player
    p.members["player"].level, p.members["mate"].level = 6, 4
    gacha.pull(rich, content, FixedRandom(DI), 1)
    assert p.members["hero"].level == 4 and p.loadouts["hero"] == [None, None]


# ── 十連與保底 ─────────────────────────────────────────


def test_ten_pull_guarantees_one_di_or_better(rich, content):
    """前九抽都是黃品：第十抽只在地、天之間抽。同一次十連抽到同一位新人兩次，第二次就算重複。"""
    gacha.pull(rich, content, FixedRandom(HUANG), 10)
    p = rich.player
    assert tiers(rich, content) == ["黃"] * 9 + ["地"]
    assert [x.new for x in p.gacha_last] == [True] + [False] * 8 + [True]
    assert (p.yuanbao, p.stats["xinde"], p.gacha_xinde) == (4000, 80, 80)
    assert p.gacha_pity == 10  # 十連保底給的地品不會重算天品保底


def test_the_ten_pull_floor_can_bring_tian_too(rich, content):
    gacha.pull(rich, content, Scripted(*[HUANG] * 18, 0.1), 10)  # 第十抽在天 3：地 12 之間抽：0.1 落在天品
    assert tiers(rich, content) == ["黃"] * 9 + ["天"]
    assert rich.player.gacha_pity == 0


def test_the_floor_is_left_alone_once_met(rich, content):
    gacha.pull(rich, content, Scripted(DI, DI, HUANG), 10)
    assert tiers(rich, content) == ["地"] + ["黃"] * 9


def test_pity_brings_tian_on_the_fortieth_pull(rich, content):
    p = rich.player
    p.gacha_pity = 38
    gacha.pull(rich, content, FixedRandom(HUANG), 1)
    assert tiers(rich, content) == ["黃"] and p.gacha_pity == 39
    gacha.pull(rich, content, FixedRandom(HUANG), 1)  # 連續第 40 抽沒出天品：必得天品
    assert p.gacha_last == [Pull(character="sage", new=True)] and p.gacha_pity == 0


def test_any_tian_starts_the_pity_over(rich, content):
    rich.player.gacha_pity = 12
    gacha.pull(rich, content, FixedRandom(TIAN), 1)
    assert tiers(rich, content) == ["天"] and rich.player.gacha_pity == 0


def test_pity_and_the_ten_pull_floor_count_separately(rich, content):
    """保底在十連的第五抽給了天品：十連的「至少一名地品以上」已經滿足，第十抽照常抽。"""
    rich.player.gacha_pity = 35
    gacha.pull(rich, content, FixedRandom(HUANG), 10)
    assert tiers(rich, content) == ["黃"] * 4 + ["天"] + ["黃"] * 5
    assert rich.player.gacha_pity == 5


# ── 重複與付費心得護欄 ─────────────────────────────────────


def test_duplicates_turn_into_xinde_by_tier(rich, content):
    join(rich, "pupil", "hero", "friend", "sage")
    msgs = gacha.pull(rich, content, FixedRandom(HUANG), 1)
    assert msgs == ["元寶 -100", "【小六】（黃品）重複 → 心得 +10", "心得 +10"]
    for value in (DI, XUAN, TIAN):
        gacha.pull(rich, content, FixedRandom(value), 1)
    p = rich.player
    assert (p.stats["xinde"], p.gacha_xinde) == (180, 180)  # 10＋50＋20＋100
    assert p.gacha_last == [Pull(character="sage", new=False, xinde=100)]
    assert set(p.members) == {"player", "mate", "pupil", "hero", "friend", "sage"}


def test_duplicates_give_half_only_once_the_season_is_over_150(rich, content):
    join(rich, "hero")
    p = rich.player
    p.gacha_xinde = 149
    gacha.pull(rich, content, FixedRandom(DI), 1)
    assert p.gacha_xinde == 199  # 149 還沒超過 150：照給 50
    msgs = gacha.pull(rich, content, FixedRandom(DI), 1)
    assert msgs[1:] == ["【俠女】（地品）重複 → 心得 +25（本季招賢心得已超過 150，減半）", "心得 +25"]
    assert (p.gacha_xinde, p.stats["xinde"]) == (224, 75)


def test_a_duplicate_at_exactly_150_still_gives_the_full_amount(rich, content):
    """剛好 150 不算超過：照給整份；超過的下一個才減半。"""
    join(rich, "hero")
    p = rich.player
    p.gacha_xinde = 150
    msgs = gacha.pull(rich, content, FixedRandom(DI), 1)
    assert msgs[1:] == ["【俠女】（地品）重複 → 心得 +50", "心得 +50"]
    assert (p.gacha_xinde, p.gacha_last) == (200, [Pull(character="hero", new=False, xinde=50)])
    msgs = gacha.pull(rich, content, FixedRandom(DI), 1)
    assert msgs[1:] == ["【俠女】（地品）重複 → 心得 +25（本季招賢心得已超過 150，減半）", "心得 +25"]
    assert p.gacha_xinde == 225


def test_duplicates_top_up_to_the_cap_then_give_silver(rich, content):
    join(rich, "sage")
    p = rich.player
    p.gacha_xinde = 290
    msgs = gacha.pull(rich, content, FixedRandom(TIAN), 1)
    assert msgs[1:] == ["【隱士】（天品）重複 → 心得 +10（補到本季上限 300）", "心得 +10"]
    assert p.gacha_xinde == 300
    msgs = gacha.pull(rich, content, FixedRandom(TIAN), 1)
    assert msgs[1:] == ["【隱士】（天品）重複 → 銀兩 +100（本季招賢心得已滿 300）", "銀兩 +100"]
    assert p.gacha_last == [Pull(character="sage", new=False, silver=100)]
    assert (p.gacha_xinde, p.stats["xinde"], p.stats["silver"]) == (300, 10, 150)


def test_event_duplicates_do_not_count_toward_the_cap(state, content):
    """劇情事件結識到已入門的人換到的心得（1c-1）不算招賢心得。"""
    roster.recruit(state, content, "mate")
    assert (state.player.stats["xinde"], state.player.gacha_xinde) == (20, 0)


# ── 舊存檔 ──────────────────────────────────────────────


def test_old_save_without_gacha_fields_loads(tmp_path, content, game):
    dump = game.state.model_dump(mode="json")
    for key in ("yuanbao", "gacha_pity", "gacha_xinde", "gacha_last"):
        del dump["player"][key]
    path = tmp_path / "old.json"
    path.write_text(json.dumps(dump, ensure_ascii=False), encoding="utf-8")
    p = Game(content, load_game(path)).state.player
    assert (p.yuanbao, p.gacha_pity, p.gacha_xinde, p.gacha_last) == (0, 0, 0, [])
