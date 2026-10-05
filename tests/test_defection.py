"""第一季正式版・甲：叛投（計畫 2026-10-06-第一季正式版-甲-叛投）。

用真實內容（content/）：投靠點、門派歸屬、頭銜都照真的；開關在測試裡才打開。"""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from tianxia import bot, bot_policy, defection
from tianxia.content import ContentError, load_content, validate
from tianxia.engine import Game
from tianxia.models import FactionDef
from tianxia.state import BotProfile, Convoy, PlayerState, Summons

CONTENT_DIR = Path(__file__).parent.parent / "content"


@pytest.fixture
def real():
    c = load_content(CONTENT_DIR)
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    return c


@pytest.fixture
def on(real):
    real.config.season_one, real.config.season_days, real.config.server_max_players = True, 2.5, 2
    return real


def _game(content, name="甲", faction=None, at=None):
    game = Game.new(content, name, rng=random.Random(0))
    game.state.player.faction = faction
    if at is not None:
        game.state.player.location = at
    return game


def test_new_fields_have_defaults_so_old_saves_load():
    p = PlayerState(name="甲", location="x", stats={}, stamina=0)
    assert (p.defected, p.pending_defect) == (False, None)
    assert FactionDef(id="x", name="X").defect_text == ""


def test_real_factions_have_defect_text(real):
    # 三句是新寫的初稿，待 joy 潤（content/scenario.json 是 JSON、FactionDef 不收多的欄位，所以標記記在這裡與 models.py）
    texts = {f.id: f.defect_text for f in real.scenario.factions}
    assert set(texts) == {"guan", "huang", "haoqiang"} and all(texts.values())


def test_defect_text_must_be_traditional(real):
    real.scenario.factions[0].defect_text = "过去的事不问"
    with pytest.raises(ContentError, match="defect_text"):
        validate(real)


# ── Task 2：叛投的規則 ─────────────────────────────────


def _faction(content, faction_id):
    return next(f for f in content.scenario.factions if f.id == faction_id)


def test_targets_only_at_another_factions_join_point(on):
    game = _game(on, faction="guan", at="huangjin_camp")
    assert [f.id for f in defection.targets_here(game.state, on)] == ["huang"]
    game.state.player.location = "changshe"  # 自己陣營的投靠點：沒有
    assert defection.targets_here(game.state, on) == []
    game.state.player.location = "yingchuan"  # 不是任何人的投靠點
    assert defection.targets_here(game.state, on) == []


def test_no_targets_for_loners_or_after_a_defection(on):
    loner = _game(on, at="huangjin_camp")
    assert defection.targets_here(loner.state, on) == []
    once = _game(on, faction="guan", at="huangjin_camp")
    once.state.player.defected = True
    assert defection.targets_here(once.state, on) == []


def test_no_targets_with_switch_off(real):
    # 分開測：on 與 real 是同一份內容（on 只是把開關打開），同一個測試裡再拿 real 就已經是開著的了
    off = _game(real, faction="guan", at="huangjin_camp")  # 開關關著（config.json 預設）
    assert defection.targets_here(off.state, real) == []


def test_prompt_names_the_cost(on):
    game = _game(on, faction="guan", at="huangjin_camp")
    p = game.state.player
    p.rank, p.followers = 2, ["follower_guan_spear", "follower_guan_crossbow"]
    text = defection.prompt(game.state, on, _faction(on, "huang"), "目前官軍 1 人、黃巾軍 0 人、地方豪強 0 人")
    assert "身份歸零（你現在是屯長）" in text and "2 名部下全部離隊" in text
    assert "這一季替官軍記下的功勞全部作廢" in text and "一季只能叛投一次" in text
    assert text.endswith("確定叛投黃巾軍？")


def test_prompt_lists_only_what_is_really_lost(on):
    """第 1 階（鄉勇）不算損失：叛投之後在新陣營一樣是第 1 階；糧車、召見只在真的有的時候才寫。"""
    game = _game(on, faction="guan", at="huangjin_camp")
    p = game.state.player
    counts = "目前官軍 1 人、黃巾軍 0 人、地方豪強 0 人"
    for rank in (0, 1):  # 存檔的 0 是投靠了還沒晉升過，也算第 1 階
        p.rank = rank
        text = defection.prompt(game.state, on, _faction(on, "huang"), counts)
        assert not any(word in text for word in ("身份歸零", "部下", "糧車", "召見"))
        assert "這一季替官軍記下的功勞全部作廢" in text and text.endswith("確定叛投黃巾軍？")
    p.convoy = Convoy(order="o1", grain=4, from_loc="xinye", to_loc="wan_city")
    assert "押著的糧車作廢、交出去的糧草不退" in defection.prompt(game.state, on, _faction(on, "huang"), counts)
    p.convoy, p.summons = None, Summons(rank=3, figure="luzhi", location="luzhi_camp")
    text = defection.prompt(game.state, on, _faction(on, "huang"), counts)
    assert "還沒去的召見作廢" in text and "糧車" not in text


def test_defect_resets_rank_and_old_progress(on):
    game = _game(on, faction="guan", at="huangjin_camp")
    p = game.state.player
    p.rank, p.followers, p.contrib, p.contrib_weeks = 2, ["follower_guan_spear"], 420, {1: 420}
    p.summons = Summons(rank=3, figure="luzhi", location="luzhi_camp")
    p.donations, p.convoy = {"wan_city:grain": 8}, Convoy(order="o1", grain=4, from_loc="xinye", to_loc="wan_city")
    p.affinities, p.fragments = {"huangfusong": 30}, {"fs_changshe_guan": [0, 2]}
    msgs = defection.defect(game.state, on, _faction(on, "huang"))
    assert (p.faction, p.defected, p.rank, p.summons, p.followers) == ("huang", True, 0, None, [])
    assert (p.contrib, p.contrib_weeks, p.donations, p.convoy) == (0, {}, {}, None)
    assert p.affinities == {"huangfusong": 30} and p.fragments == {"fs_changshe_guan": [0, 2]}  # 帶得走的照舊
    assert msgs[0] == _faction(on, "huang").defect_text and msgs[-1] == "你叛出官軍，投了黃巾軍。"


def test_defect_publishes_two_faction_notes_and_a_local_rumor(on):
    game = _game(on, faction="guan", at="huangjin_camp")
    before = len(game.state.world.rumors)
    defection.defect(game.state, on, _faction(on, "huang"))
    new = game.state.world.rumors[before:]
    assert [(r.layer, r.faction) for r in new] == [("faction", "guan"), ("faction", "huang"), ("local", None)]
    assert new[0].text == "甲叛離了官軍，投奔黃巾軍。"
    assert new[1].text == "甲從官軍投奔過來了。"
    assert new[2].text == "甲在黃巾別部營寨改投了黃巾軍。" and new[2].location == "huangjin_camp" and new[2].named
    assert all(r.layer != "world" for r in new)  # 不上天下大事（傳聞分層第五節）
    assert new[0].location is None and new[1].location is None  # 陣營軍情不帶地點（同 orders._faction_news、ranks.flush_news）


def test_defect_clears_nothing_else(on):
    """帶得走的照舊：每人每天的推動上限、背包、隊伍、屬性、功法庫、做完的伏筆鏈（第一季設計 5.1、計畫甲 Global Constraints）。"""
    game = _game(on, faction="guan", at="huangjin_camp")
    p = game.state.player
    p.pushed = {"1:yingru": 3.0}
    p.materials, p.arts, p.team, p.fs_done = {"gang_1": 2}, ["some_art"], ["luzhi"], ["fs_changshe_guan"]
    p.stats["str"] = 9
    kept = {key: getattr(p, key) for key in ("pushed", "materials", "arts", "team", "fs_done", "stats")}
    kept = {key: value.copy() for key, value in kept.items()}  # 不能留著同一份：defect 若原地改動，比較會假裝沒事
    defection.defect(game.state, on, _faction(on, "huang"))
    assert {key: getattr(p, key) for key in kept} == kept


def test_anonymous_defector_is_not_named(on):
    """企劃者定：只有地方傳聞匿名；公告、陣營軍情、晉升、江湖史一律寫真名。選了匿名的人叛投，
    兩則陣營軍情仍寫真名（只給那個陣營自己人看），當地那一則寫「某位少俠」、標成不具名。"""
    game = _game(on, faction="guan", at="huangjin_camp")
    game.state.player.anonymous = True
    before = len(game.state.world.rumors)
    defection.defect(game.state, on, _faction(on, "huang"))
    new = game.state.world.rumors[before:]
    assert new[0].text == "甲叛離了官軍，投奔黃巾軍。" and new[1].text == "甲從官軍投奔過來了。"
    assert new[2].text == "某位少俠在黃巾別部營寨改投了黃巾軍。" and new[2].named is False
    assert new[0].named and new[1].named


def test_defect_leaves_old_active_list(on):
    game = _game(on, faction="guan", at="huangjin_camp")
    w = game.state.world
    w.active_pushers = {"guan": {"甲": w.time, "乙": w.time}, "huang": {"丙": w.time}}
    defection.defect(game.state, on, _faction(on, "huang"))
    assert w.active_pushers == {"guan": {"乙": w.time}, "huang": {"丙": w.time}}
    solo = _game(on, name="丁", faction="guan", at="huangjin_camp")
    solo.state.world.active_pushers = {"guan": {"丁": solo.state.world.time}}
    defection.defect(solo.state, on, _faction(on, "huang"))
    assert "guan" not in solo.state.world.active_pushers  # 清空的陣營整列拿掉（同 push.drop_stale）


def test_defect_leaves_old_faction_sect_only(on):
    game = _game(on, faction="guan", at="huangjin_camp")
    game.state.player.sect = "yingchuan_academy"  # 潁川書院歸官軍
    msgs = defection.defect(game.state, on, _faction(on, "huang"))
    assert game.state.player.sect is None and "叛出:yingchuan_academy" in game.state.player.flags
    assert "你也就此離開了潁川書院。" in msgs
    other = _game(on, name="乙", faction="huang", at="changshe")
    other.state.player.sect = "cao_manor"  # 曹氏莊院歸豪強，不是舊陣營（黃巾）的門派
    defection.defect(other.state, on, _faction(on, "guan"))
    assert other.state.player.sect == "cao_manor"


def test_clear_progress_is_the_one_place_to_reset():
    p = PlayerState(name="甲", location="x", stats={}, stamina=0, rank=3, contrib=5, followers=["a"])
    defection.clear_progress(p)
    assert (p.rank, p.contrib, p.followers) == (0, 0, [])


# ── Task 3：引擎接上（選項、確認畫面、場景、紀錄）─────────────────────────────────


def _ids(game):
    return [o.id for o in game.options(odds=False)]


def test_defect_option_and_confirm_screen(on):
    game = _game(on, faction="guan", at="huangjin_camp")
    assert "defect:huang" in _ids(game) and "faction:huang" not in _ids(game)
    msgs = game.choose("defect:huang")
    assert game.state.player.pending_defect == "huang"
    assert _ids(game) == ["defect:confirm", "defect:cancel"]
    assert "確定叛投黃巾軍？" in msgs[-1] and "叛投黃巾軍" in game.scene_text()


def test_cancel_keeps_everything(on):
    game = _game(on, faction="guan", at="huangjin_camp")
    game.state.player.rank = 2
    game.choose("defect:huang")
    assert game.choose("defect:cancel")[-1] == "你決定再想想。"
    p = game.state.player
    assert (p.faction, p.rank, p.defected, p.pending_defect) == ("guan", 2, False, None)


def test_confirm_defects_and_updates_the_roll(on):
    game = _game(on, faction="guan", at="huangjin_camp")
    other = _game(on, "乙", faction="guan")  # 再有一個官軍的人，名冊的人數才看得出從官軍搬到黃巾
    game.choose("defect:huang")  # choose 結束時把目前的陣營記進名冊（還是官軍）
    other.sync(50.0)
    assert game.world.faction_counts() == {"guan": 2}
    msgs = game.choose("defect:confirm")
    assert game.state.player.faction == "huang" and game.state.player.defected
    assert "你叛出官軍，投了黃巾軍。" in msgs
    assert game.world.faction_of("甲") == "huang"  # 名冊是 choose() 結尾的 _record_faction 更新的，_defect_step 不碰
    assert game.world.faction_counts() == {"guan": 1, "huang": 1}
    assert not any(i.startswith("defect:") for i in _ids(game))  # 一季一次


def test_confirm_after_leaving_does_nothing(on):
    game = _game(on, faction="guan", at="huangjin_camp")
    game.choose("defect:huang")
    game.state.player.location = "yingchuan"  # 確認之前走開了（或在另一個分頁移動）
    assert game.choose("defect:confirm")[-1] == "（你已經不在叛投的地方了。）"
    assert game.state.player.faction == "guan" and not game.state.player.defected
    assert game.state.player.pending_defect is None


def test_confirm_after_defecting_elsewhere_does_nothing(on):
    """另一個分頁已經叛投過了（defected 是 True）：這一頁的「確定」不能再叛投第二次。"""
    game = _game(on, faction="guan", at="huangjin_camp")
    game.choose("defect:huang")
    game.state.player.defected = True
    assert game.choose("defect:confirm")[-1] == "（你已經不在叛投的地方了。）"
    assert game.state.player.faction == "guan"


def test_confirm_screen_blocks_map_travel(on):
    """輿圖的「安排前往」在叛投確認畫面上跟投靠的確認一樣按不下去（寫原因、要回江湖頁了結），不然走開之後「確定」就過期了。"""
    game = _game(on, faction="guan", at="huangjin_camp")
    reason = "叛投還沒決定，先決定再安排前往"
    assert game.travel_refusal("changshe") is None  # 還沒按叛投：走得了
    game.choose("defect:huang")
    assert game.travel_refusal("changshe") == reason
    assert [(o.enabled, o.label, o.to_jianghu) for o in game.travel_options("changshe")] == [(False, reason, True)]
    assert game.travel("changshe") == [f"（{reason}。）"] and game.state.player.location == "huangjin_camp"
    game.choose("defect:cancel")
    assert game.travel_refusal("changshe") is None


def test_stale_pending_defect_is_dropped(on):
    game = _game(on, faction="guan", at="huangjin_camp")
    game.state.player.pending_defect = "no_such_faction"
    game._drop_stale_references()  # noqa: SLF001
    assert game.state.player.pending_defect is None


def test_new_season_allows_defecting_again(on):
    """角色每季重來：叛投過的人，新的一季是散人、defected 回到 False（同 test_ranks 的換季寫法）。"""
    on.config.admins = ["管"]
    admin = _game(on, "管")
    player = _game(on, "甲", faction="huang")
    player.state.player.defected = True
    player.sync(100.0)
    admin.admin_end_season(now=200.0)
    admin.admin_next_season(now=300.0)
    player.sync(400.0)
    assert (player.state.player.faction, player.state.player.defected) == (None, False)


def test_switch_off_no_defect_option(real):
    game = _game(real, faction="guan", at="huangjin_camp")
    assert not any(i.startswith("defect:") for i in _ids(game))


# ── Task 4：假人與整季機器人不叛投 ─────────────────────────────────


def test_bots_never_defect(on):
    game = _game(on, faction="guan", at="huangjin_camp")
    options = [o for o in game.options(odds=False) if o.id.startswith("defect:")]
    assert options  # 選單上確實有
    assert bot.pick(game, options, random.Random(0)) is None  # 整季機器人：只剩叛投就當作沒得挑
    profile = BotProfile(personality="普通", seed=1, faction="guan", season_number=1)
    assert all(bot_policy.score(game, o, profile) is None for o in options)


def test_server_bot_turn_never_picks_a_defect_option(on):
    """take_turn 的候選清單也排除 defect:（score 回 None 之外的第二道）：站在別的陣營的投靠點上，假人照常做別的事、不叛投。"""
    profile = BotProfile(personality="普通", seed=1, faction="guan", season_number=1)
    for seed in range(8):  # 每個種子一個新假人：走了一步就離開投靠點，同一個假人只能測一輪
        game = _game(on, f"假{seed}", faction="guan", at="huangjin_camp")
        game.state.player.bot = profile
        assert any(o.id.startswith("defect:") for o in game.options(odds=False))
        bot_policy.take_turn(game, profile, random.Random(seed))
        p = game.state.player
        assert (p.faction, p.defected, p.pending_defect) == ("guan", False, None)
