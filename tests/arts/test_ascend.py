"""破境（招式與絕學稿案第三節）：自創的練成絕學，自己的招升為絕招、接後勁、破境卡、江湖史與傳聞，不再定名。"""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from tianxia import ascend, create, cultivation, moves, skillview, tactics, team, traits
from tianxia.content import load_content
from tianxia.engine import Game

ROOT = Path(__file__).parents[2]


@pytest.fixture(scope="module")
def content():
    c = load_content(ROOT / "tests" / "fixtures" / "content")
    c.config.auto_open_first_season = True
    return c


class Always:
    def random(self):
        return 0.0


def _made(content, name="破境人"):
    game = Game.new(content, name, rng=random.Random(3))
    game.world.open_season(content, now=0.0)
    p = game.state.player
    p.stats["xinde"] = 5000
    assert game.create_begin("武學", "拳腳")
    game.create_pose(create.preset(content, "進擊"))
    game.create_intent("風過林梢，影不留痕", reading=create.IntentReading(score=80, attributes=["快"], move="追風影"))
    game.create_name("疾風掌")
    p.member.wugong_id, p.member.wugong_level = "疾風掌", 10
    if "疾風掌" in p.arts:
        p.arts.remove("疾風掌")
    return game


def test_the_own_move_ascends_and_the_card_is_written(content):
    game = _made(content)
    s, w, p = game.state, game.world, game.state.player
    before = team.player_art(s, content, w, "疾風掌")
    was = moves.move_of(content, before, 10)
    msgs = ascend.ascend(s, content, w, "疾風掌", "seize")
    assert p.art_quality["疾風掌"] == "絕學" and p.naming is None  # 破境不取名
    assert "〔追風影〕忽然通了" in msgs[0]
    after = team.player_art(s, content, w, "疾風掌")
    now = moves.move_of(content, after)
    # 每回合會發的招破境後發動率 ×ascend_scale、最多 ascend_rate_cap（Joy 2026-10-23「甲 加一半」；以前一律升到必定）
    assert now.rate == min(content.config.arts.ascend_rate_cap, round(was.rate * 1.5, 3)) > was.rate and now.name == "追風影"
    assert tactics.title_of(now, after) == tactics.ULTIMATE_SEAL
    card = p.ascension
    assert card.after.startswith("絕〔追風影〕") and card.before.startswith(p.name[:1] + "〔追風影〕")
    assert card.power[1] > card.power[0]
    assert any("練到了絕處" in r.text for r in s.world.rumors)
    held = [h for h in team.tactic_holders(s, content, w) if h.skill == "疾風掌"]
    assert held and held[0].tactic.rate == now.rate


def test_the_card_line_is_rechecked_and_dismissed(content):
    game = _made(content, "寫卡人")
    s = game.state
    ascend.ascend(s, content, game.world, "疾風掌", "pill")
    req = game.ascend_request()
    assert req is not None and req.move == "追風影" and req.via == "pill"
    assert ascend.read(None, req) == ascend.FALLBACK_PILL
    game.ascend_line(req, "123")  # 寫壞了：照套句
    assert s.player.ascension.line == ascend.FALLBACK_PILL
    assert game.ascend_request() is None  # 寫過了不再叫
    game.ascend_dismiss()
    assert s.player.ascension is None and ascend.view(s) is None


def test_seize_in_a_fight_goes_through_the_ascension(content):
    game = _made(content, "契機人")
    s, p = game.state, game.state.player
    p.art_quality["疾風掌"] = "上品"
    if content.config.breakthrough.chance <= 0:
        pytest.skip("測試內容關了契機")
    msgs = cultivation.seize(s, content, game.world, 1.0, Always())
    assert msgs and "忽然通了" in msgs[0] and p.ascension is not None


def test_the_row_shows_the_fifth_ring_and_the_ripe_marks(content):
    game = _made(content, "看卡人")
    s, w = game.state, game.world
    row = next(r for r in skillview.art_rows(s, content, w) if r["id"] == "疾風掌")
    assert row["fifth"] == {"on": False, "name": "", "note": skillview.RIPE_NOTE}
    assert f"（{skillview.RIPE_MOVE}）" in row["tactic"]
    ascend.ascend(s, content, w, "疾風掌", "seize")
    row = next(r for r in skillview.art_rows(s, content, w) if r["id"] == "疾風掌")
    assert row["fifth"]["on"] and row["fifth"]["name"] == "追風影"
    assert row["tactic"].startswith("絕〔追風影〕") and skillview.RIPE_MOVE not in row["tactic"]


def test_the_after_blow_follows_the_slots():
    """後勁要內容寫了絕招（測試內容沒寫）：用正式內容。"""
    content = load_content(ROOT / "content")
    content.config.auto_open_first_season = True
    game = _made(content, "後勁人")
    s, w = game.state, game.world
    p = s.player  # 舊樣子的意境（沒擲效果）：功效就是那一路的一般功效，強度 3（同 test_ultimates._mastered）
    p.insights.append("feng")
    p.insight_strength["feng"] = 3
    p.art_slots["疾風掌"] = ["feng", None, None]
    ascend.ascend(s, content, w, "疾風掌", "seize")
    art = team.player_art(s, content, w, "疾風掌")
    tail = traits.ultimate_of(content, art)
    assert tail is not None and tail.name != art.name  # 後勁照功效取名，不再叫門名
    assert s.player.ascension.after_tail.startswith(traits.AFTER_TITLE + "〔")
    names = [h.tactic.name for h in team.tactic_holders(s, content, w)]
    assert "追風影" in names and tail.name in names


def test_ascending_raises_every_round_moves_to_a_cap_and_keeps_openers(content):
    """破境的發動率（Joy 2026-10-23「甲 加一半」）：每回合會發的乘 1.5、最多五成，本來就超過的照舊；起手的照原本的。"""
    from tianxia.models import CreateMove, TacticDef
    row = CreateMove(attribute="剛", timing="出招", name="甲", kind="heavy_blow", desc="", rate=0.2, grow=["rate", "mult"], params={"mult": 2.0})
    def made(rate, rounds=0):
        return TacticDef(name="甲", timing="出招" if not rounds else "起手", kind="heavy_blow", desc="", rate=rate, rounds=rounds, params={"mult": 2.0})
    assert moves.ascend(content, row, made(0.2)).rate == 0.3
    assert moves.ascend(content, row, made(0.4)).rate == 0.5  # 0.6 夾到五成
    assert moves.ascend(content, row, made(0.6)).rate == 0.6  # 本來就比五成高：照舊
    assert moves.ascend(content, row, made(1.0)).rate == 1.0
    assert moves.ascend(content, row, made(0.45, rounds=1)).rate == 0.45  # 起手的不升
    assert moves.ascend(content, row, made(0.2)).params["mult"] == 2.5  # 會長的數照舊乘 1.5


def test_wins_while_flawless_do_not_count_toward_the_streak(content):
    """乘勝的後勁（連贏 → 下一回合無隙）：無隙那一回合贏的不算連贏（Joy 2026-10-23「甲 加一半」的共同修正），不然一路鎖死。"""
    import random
    from tianxia.models import TacticDef
    t = TacticDef(name="後勁", timing="心法", kind="streak", desc="", rate=1.0, params={"wins": 2, "turns": 1})
    f = tactics._Fight([tactics.Holder(who="你", key="player", skill="x", tactic=t)], tactics.Ctx(foe="乙"), content.config.tactics, random.Random(1))
    tactics._after(f, True)
    tactics._after(f, True)
    assert f.us.later.get("無隙") == 1 and f.stacks["後勁"] == 0
    f.flawless = True  # 下一回合無隙，贏了
    tactics._after(f, True)
    assert f.stacks["後勁"] == 0
    f.flawless = False
    tactics._after(f, True)
    assert f.stacks["後勁"] == 1


def test_the_breakthrough_line_is_traditional_and_screened():
    """2026-10-31 自檢：破境那一句以前不轉繁體，英文、「機器人」都照收。"""
    assert ascend.clean("你的掌风如雷霆万钧般劈开了黑暗") == "你的掌風如雷霆萬鈞般劈開了黑暗"
    assert ascend.clean("You finally broke through the limit now") == ""
    assert ascend.clean("你這個機器人終於通了最後一關，破境成功") == ""
