"""假人看到決戰的鈕怎麼按（bots.py；全部拆包第 7 批拿了 battle: 前綴，bot_policy.score 先問 features_core.bot_pick、再問這一包）。
審查 nit：改 bots.py 時 test_for 只挑這一包的 tests/ 與核心契約、邊界，那 159 條沒有一條走到 bots.py（把 bots.score 改成 return None
照樣全綠），蓋著它的 test_bot_policy、test_battle_pace 等是混在別人檔裡的。這一條經 features_core.bot_pick 與 bot_policy.score 打 battle:
的加入、挑同伴、出招的分數，改壞 bots.py 或 BattleFeature.bot_pick 這裡就紅。正式內容 week7 開長社火攻；不借別的測試檔的輔助函式。"""
import random

from conftest import real_content

from tianxia import bot_policy
from tianxia.core import features as features_core
from tianxia.core.option import Option
from tianxia.engine import Game
from tianxia.features.battle import bots
from tianxia.sqlite_world import open_world
from tianxia.state import BotProfile
from tianxia.world import open_showdown

BATTLE = "changshe_fire"


def test_a_bot_joins_and_picks_its_strongest_move_through_the_package():
    c = real_content("week7")
    c.config.auto_open_first_season = True
    game = Game.new(c, "甲客", rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.faction, p.location = "guan", "changshe"
    p.tutorial_step = len(c.tutorial.steps)
    game.sync(game.now)
    profile = BotProfile(personality="普通", seed=1, faction="guan", season_number=game.world.get_season_number())
    open_showdown(game.world, c, BATTLE, game.now)  # 集結

    join = next(o for o in game.options() if o.id == "battle:join:guan")
    assert features_core.bot_pick(game, join) == (True, bots.JOIN_BATTLE_SCORE)  # 一看到加入就按（分數最高的那一級）
    assert bot_policy.score(game, join, profile) == bots.JOIN_BATTLE_SCORE  # bot_policy 經包問到同一個數
    late = Option(id="battle:join_late", label="加入戰局")
    assert features_core.bot_pick(game, late) == (True, bots.JOIN_BATTLE_SCORE)
    for other in ("battle:escort:none", "battle:escort:back", "battle:spectate", "battle:waiting"):
        assert features_core.bot_pick(game, Option(id=other, label="")) == (True, None)  # 挑同伴、觀戰、已選擇：不按

    game.choose("battle:join:guan")
    if any(o.id == "battle:escort:none" for o in game.options()):
        game.choose("battle:escort:none")
    game.world.mutate_battle(lambda b: setattr(b, "muster_deadline_real", -1.0))
    game.options()  # 集結截止：推到開打
    assert game.world.get_battle().phase == "active"
    name = p.name
    game.world.mutate_battle(lambda b: b.participants[name].scores.update({"強攻": 90.0, "固守": 60.0, "奇襲": 40.0}))

    moves = [o for o in game.options() if o.enabled and o.id.startswith("battle:act:")]
    assert len(moves) == 3
    picked = {o.label: features_core.bot_pick(game, o) for o in moves}
    assert all(owned and isinstance(value, float) for owned, value in picked.values())
    best = max(picked, key=lambda label: picked[label][1])
    assert "（強攻" in best  # 滿血時照份量挑：強攻 90 比固守 60、奇襲 40 高，扣血的差別蓋不過去
    assert {o.label: bot_policy.score(game, o, profile) for o in moves} == {k: v for k, (_, v) in picked.items()}
