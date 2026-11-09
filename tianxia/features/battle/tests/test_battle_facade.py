"""battle 這一包的測試，從 tests/core/test_engine.py 拆來（全部拆包第 61 批，只搬位置、不改斷言）。"""
from math import isclose
import random
import time
from unittest import mock
import pytest
from conftest import at, idle_step
from tianxia import atlas
from tianxia.features.battle import instance as battle_instance
from tianxia import front_lines
from tianxia.characters import open_characters
from tianxia.engine import Game, Option
from tianxia.martial_arts import MartialArt
from engine_kit import (  # noqa: F401
    DAY, HOUR, _admin, _as_warlord, _fight_to_the_end, _fighter, _install_battle_def, _install_battle_def_with_free_text,
    _install_factions, _join_and_open, _joined_a_battle_in_the_north, _open_three_move_battle, _play_showdown,
    _showdown_game, _south_cave, _strip_scores, _three_round_showdown, _to_showdown, _warlord_in_battle, ids,
)

pytestmark = pytest.mark.whole_content


@pytest.mark.parametrize("under_way", [False, True], ids=["muster", "active"])
def test_admin_end_season_with_battle_running(content, game, under_way):
    """決戰還在集結或開打時收季：照自然收季的做法（試玩回饋 FB-015）直接清掉、不套用結果，戰況不變。"""
    definition = _install_battle_def(content)
    content.config.admins = ["沈浪"]
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        game.choose("battle:join:guan")
    if under_way:
        with at(game, 1000.0 + 601):
            assert ids(game) == ["battle:act:guan_strong", "battle:act:guan_hold", "battle:act:guan_raid"]  # 開打了
    trends = dict(game.world.get_season().trends)

    game.admin_end_season(now=1000.0 + 700)

    assert game.world.get_battle() is None
    assert game.world.season_phase() == "resting"
    assert dict(game.world.get_season().trends) == trends  # 沒有套用決戰的結果
    assert not any("官軍大勝" in entry.text for entry in game.world.get_season().chronicle)
    assert ids(game) == ["season:resting"]


def test_the_engine_resolves_a_round_with_the_configured_tuning_even_against_a_bot_without_scores(content, game):
    """Config.battle 一路傳進結算（push_max 改成 4：推力不是寫死的 10）；對面是沒有快照的假人，份量 0、不當機。"""
    content.config.battle.push_max = 4.0
    battle, definition = _open_three_move_battle(game)
    game.world.mutate_battle(lambda b: battle_instance.auto_assign_latecomer(
        b, definition, "機", 300.0, random.Random(0), faction="huang", is_bot=True,
    ))
    assert game.world.get_battle().participants["機"].scores == {}
    game.choose("battle:act:guan_hold")  # 本人出完，假人在同一次推進裡跟著出，回合湊齊、結算
    after = game.world.get_battle()
    assert after.round_number == 1 and after.trend == 54  # 假人份量 0：官軍推滿 push_max
    me = after.participants[game.state.player.name]
    assert me.last_result.startswith("固守（剋制 ×") and after.participants["機"].neili < 300.0  # 剋制幾倍看假人出了哪一招


def test_battle_buttons_show_the_move_and_the_score(game):
    """按鈕寫「選項名（招・你 N 分）」：份量乘上這一場的氣血狀態（設計 3.4）。"""
    battle, definition = _open_three_move_battle(game)
    labels = [o.label for o in game._battle_options(battle, definition)]
    me = battle.participants[game.state.player.name]
    expected = round(me.scores["固守"] * battle_instance.condition(me))
    assert any(f"（固守・{expected} 分）" in label for label in labels)
    assert labels == [  # 自己這邊的三招，照內容寫的順序；對面的招不會出現
        f"guan{move}（{move}・{round(me.scores[move] * battle_instance.condition(me))} 分）"
        for move in ("強攻", "固守", "奇襲")
    ]


def test_a_wounded_fighters_button_shows_the_smaller_score(game):
    """氣血少了，按鈕上寫的分數跟著降（乘氣血狀態），玩家看得到自己現在有多少份量。"""
    battle, definition = _open_three_move_battle(game)
    name = game.state.player.name
    full = [o.label for o in game._battle_options(battle, definition)]
    battle.participants[name].neili = battle.participants[name].neili_cap / 2
    wounded = [o.label for o in game._battle_options(battle, definition)]
    score = lambda label: int(label.split("・")[-1].split(" ")[0])  # noqa: E731
    assert all(score(w) < score(f) for w, f in zip(wounded, full))


def test_a_gamble_option_is_not_a_button(content, game):
    """放手一搏走輸入框、不是按鈕：按鈕只有自己這一邊的三招。"""
    definition = _install_battle_def_with_free_text(content)
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        game.choose("battle:join:guan")
    with at(game, 1000.0 + definition.muster_seconds + 1):
        game._battle_status()
        labels = [o.label for o in game._battle_options(*game._battle_status(tick=False))]
    assert len(labels) == 3 and not any("放手一搏" in label for label in labels)
    assert game.battle_free_text_prompt() is None or "放手一搏" in game.battle_free_text_prompt()


def test_the_scene_says_what_the_other_side_did_last_round(game):
    battle, definition = _open_three_move_battle(game)
    battle.last_mix = {"guan": {"強攻": 1.0, "固守": 0.0, "奇襲": 0.0}, "huang": {"強攻": 0.2, "固守": 0.5, "奇襲": 0.3}}
    battle.participants[game.state.player.name].last_result = "固守（剋制 ×1.3）"
    text = game._battle_scene_text(battle, definition)
    enemy = "黃巾" if battle.participants[game.state.player.name].faction == "guan" else "官軍"
    assert "對面上一回合" in text and "你上一回合：固守（剋制 ×1.3）" in text and enemy in text
    assert f"對面上一回合（{enemy}）：強攻 20%・固守 50%・奇襲 30%" in text  # 對面的比例，不是自己這邊的
    # 兩句是同一段引用（markdown 的「> 」，段內換行）：網頁在 .scene blockquote 底下把它縮成小字、淡色（見 test_battle_buttons）
    assert f"> 對面上一回合（{enemy}）：強攻 20%・固守 50%・奇襲 30%\n> 你上一回合：固守（剋制 ×1.3）" in text


def test_the_scene_has_no_last_round_lines_before_anything_was_resolved(game):
    battle, definition = _open_three_move_battle(game)
    text = game._battle_scene_text(battle, definition)
    assert "對面上一回合" not in text and "你上一回合" not in text


def test_the_scene_does_not_say_what_the_other_side_did_when_nobody_on_it_played_a_move(game):
    """對面上一回合沒人出固定招（比例是空的）：不寫那一行；自己的結果照寫。"""
    battle, definition = _open_three_move_battle(game)
    battle.last_mix = {"guan": {"強攻": 0.0, "固守": 1.0, "奇襲": 0.0}, "huang": {}}
    battle.participants[game.state.player.name].last_result = "固守（剋制 ×1.0）"
    text = game._battle_scene_text(battle, definition)
    assert "對面上一回合" not in text and "你上一回合：固守（剋制 ×1.0）" in text
    assert "\n\n> 你上一回合：固守（剋制 ×1.0）" in text  # 單獨一段引用


def _play_rounds(game, definition, count):
    """對面是一個沒有快照的假人（自己會出招）、氣血給足，本人每回合固守；打 count 個回合，不讓任何人倒下。"""
    game.world.mutate_battle(lambda b: battle_instance.auto_assign_latecomer(
        b, definition, "機", 10_000.0, random.Random(0), faction="huang", is_bot=True,
    ))
    name = game.state.player.name
    game.world.mutate_battle(lambda b: (setattr(b.participants[name], "neili", 10_000.0),
                                        setattr(b.participants[name], "neili_cap", 10_000.0)))
    for _ in range(count):
        game.choose("battle:act:guan_hold")
    return game.world.get_battle()


def test_the_round_by_round_mix_line_never_reaches_the_scene_log(game):
    """審查 I1：沒有模型（或逾時、或在假人的 Game 裡結算）時潤色退回系統訊息本身，以前每一回合那一行出招比例
    （官軍：強攻 x%・…（三招交鋒，戰線往哪邊推了多少））都會進場景最近五段的記錄，每段約 88px；現在它只留在回合紀錄（戰報）。
    場景上的出招比例只寫一次：上一回合那一段引用。"""
    battle, definition = _open_three_move_battle(game)
    definition.rounds_per_act, definition.decisive_margin = 6, 51  # 打五回合還沒收場（戰局推到底也不算壓倒性）
    battle = _play_rounds(game, definition, 5)
    assert battle.phase == "active" and battle.round_number == 5
    assert not any("%（三招交鋒" in line or "強攻 0%" in line for line in battle.narrative_log)
    records = game.world.battle_rounds(battle.record_id)
    assert len(records) == 5 and all("（三招交鋒" in r.messages[0] and r.messages[0].startswith(("官軍：", "黃巾：")) for r in records)
    scene = game._battle_scene_text(battle, definition)
    assert scene.count("對面上一回合") == 1 and "%（三招交鋒" not in scene  # 最新一回合的比例還在，只寫一次
    assert scene.count("強攻 ") == 1


def test_a_round_is_resolved_without_asking_the_model(game):
    """試玩回饋 2026-10-08：回合在行動鎖裡結算，以前每回合在鎖內等模型潤色，全服跟著等。現在模型叫得動也不叫，
    場景記錄的是系統判定的句子，第一句說誰佔了上風、為什麼。"""
    battle, definition = _open_three_move_battle(game)
    definition.rounds_per_act = 6
    client = mock.Mock()
    client.chat_text.return_value = "戰場上煙塵四起。"
    with mock.patch.object(Game, "_quick_client", return_value=client):
        battle = _play_rounds(game, definition, 1)
    assert not client.chat_text.called and not client.chat_structured.called
    assert battle.narrative_log[-1].startswith("這一回合")


def test_a_resolved_round_with_only_the_mix_line_still_tells_the_player_something(game):
    """出招比例不放進回覆（場景上已經有一段）：這一回合沒有別的事時，送出最後一個行動的人看到一句交代，不是空的、
    也不是「等待其他人」。"""
    battle, definition = _open_three_move_battle(game)
    definition.rounds_per_act = 6
    game.world.mutate_battle(lambda b: battle_instance.auto_assign_latecomer(
        b, definition, "機", 10_000.0, random.Random(0), faction="huang", is_bot=True,
    ))
    msgs = game.choose("battle:act:guan_hold")
    assert len(msgs) == 1 and msgs[0].startswith("這一回合")  # 誰佔了上風、為什麼（試玩回饋 2026-10-08）


def test_the_scene_reads_the_act_text_of_whoever_leads(game):
    battle, definition = _open_three_move_battle(game)
    definition.acts[0].text_by_lead = {"guan": "官軍佔了上風。", "huang": "黃巾佔了上風。"}
    for trend, expected in ((60, "官軍佔了上風。"), (40, "黃巾佔了上風。"), (50, "兩軍對陣。")):
        battle.trend = trend
        assert expected in game._battle_scene_text(battle, definition)


def test_a_round_played_through_the_engine_shows_up_on_the_next_scene(game):
    """走一整圈：出招、結算、再看畫面——對面上一回合與自己的結果都出現（沒有人手動塞 last_mix）。"""
    battle, definition = _open_three_move_battle(game)
    game.world.mutate_battle(lambda b: battle_instance.auto_assign_latecomer(
        b, definition, "機", 300.0, random.Random(0), faction="huang", is_bot=True,
    ))
    game.choose("battle:act:guan_hold")
    battle = game.world.get_battle()
    assert battle.round_number == 1
    text = game._battle_scene_text(battle, definition)
    assert "對面上一回合（黃巾）：" in text and "你上一回合：固守（剋制 ×" in text


def test_a_fighter_with_no_snapshot_gets_one_on_their_own_sync(game):
    """決戰打到一半上線這一版：場上已經有、沒有份量的人，在自己下一次同步時補上（照當下的武學）；不是從排程補。"""
    battle, definition = _open_three_move_battle(game)
    name = game.state.player.name
    _strip_scores(game)
    game.sync(1.0)
    after = game.world.get_battle().participants[name]
    assert after.scores == game._battle_scores() and all(v > 0 for v in after.scores.values())


def test_a_fighter_with_no_snapshot_gets_one_when_they_choose_a_move(game):
    battle, definition = _open_three_move_battle(game)
    name = game.state.player.name
    _strip_scores(game)
    game.choose("battle:act:guan_hold")
    assert game.world.get_battle().participants[name].scores == game._battle_scores()


def test_a_backfill_never_replaces_a_snapshot_taken_at_joining(game):
    """已經有快照的人不補、不換：加入之後換了武學，這一場還是照加入時的份量（Task 2 的快照規則）。"""
    battle, definition = _open_three_move_battle(game)
    name = game.state.player.name
    joined = dict(game.world.get_battle().participants[name].scores)
    game.state.player.member.wugong_id = "basic_fist"  # 加入之後換了武學
    assert game._battle_scores() != joined  # 現在算出來的已經不一樣了
    game.sync(1.0)
    game.choose("battle:act:guan_hold")
    assert game.world.get_battle().participants[name].scores == joined


def test_a_backfill_only_touches_the_players_own_fighter(game):
    """自己也沒有快照、旁人也沒有：自己補、旁人還是空的（要是補的人把自己的份量蓋到每個沒份量的人身上，這裡才抓得到）。"""
    battle, definition = _open_three_move_battle(game)
    game.world.mutate_battle(lambda b: battle_instance.auto_assign_latecomer(
        b, definition, "旁人", 300.0, random.Random(0), faction="huang",
    ))
    _strip_scores(game)
    assert game.world.get_battle().participants["旁人"].scores == {}
    game.sync(1.0)
    after = game.world.get_battle().participants
    assert after[game.state.player.name].scores == game._battle_scores()
    assert after["旁人"].scores == {}  # 別人的份量只有他自己的 Game 算得出來


def test_a_fighter_with_no_snapshot_sees_the_move_but_not_a_misleading_zero(game):
    """沒有快照的人按鈕上不寫「0 分」（那是假的：他的份量是還沒算，不是零）——只寫是哪一招。"""
    battle, definition = _open_three_move_battle(game)
    battle.participants[game.state.player.name].scores = {}
    labels = [o.label for o in game._battle_options(battle, definition)]
    assert labels == ["guan強攻（強攻）", "guan固守（固守）", "guan奇襲（奇襲）"]
    assert not any("分" in label for label in labels)


def test_battle_scores_read_the_players_two_arts(game):
    p = game.state.player
    # 武學重構：基礎武學兼容並蓄、沒有屬性；登記兩門相容屬性是實、柔的（武學的屬性照相容屬性的第一個）
    for art in (MartialArt(id="實拳", name="實拳", kind="武學", quality="下品", attribute="實", affinity=["實"], base_power=10.0, top_power=30.0),
                MartialArt(id="柔功", name="柔功", kind="內功", quality="下品", attribute="柔", affinity=["柔"], base_power=10.0, top_power=30.0)):
        assert game.world.claim_skill_name(art)
    p.member.wugong_id, p.member.neigong_id = "實拳", "柔功"  # 屬實、屬柔
    scores = game._battle_scores()
    power = game._battle_power()
    assert scores == battle_instance.move_scores(game.content.config.battle, power, "實", "柔")
    assert scores["強攻"] > scores["奇襲"]  # 實擅長強攻、不擅長奇襲；柔擅長固守、不擅長強攻
    assert scores["固守"] > scores["奇襲"]


def test_battle_scores_without_any_art_use_only_the_strength(game):
    p = game.state.player
    p.member.wugong_id = p.member.neigong_id = None
    scores = game._battle_scores()
    assert scores == battle_instance.move_scores(game.content.config.battle, game._battle_power(), None, None)
    assert len(set(scores.values())) == 1  # 沒有武學也沒有內功：沒有擅長不擅長，三招一樣重


def test_joining_in_the_muster_snapshots_the_players_scores(content, game):
    definition = _install_battle_def(content)
    p = game.state.player
    p.member.wugong_id, p.member.neigong_id = "basic_fist", "basic_breath"
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        game.choose("battle:join:guan")
    joined = dict(game.world.get_battle().participants[p.name].scores)
    assert joined == game._battle_scores() and all(v > 0 for v in joined.values())
    # 快照：加入之後換武學，這一場的份量不變
    p.member.wugong_id = None
    assert game._battle_scores() != joined
    assert game.world.get_battle().participants[p.name].scores == joined


def test_joining_late_snapshots_the_players_scores(content, game):
    definition = _install_battle_def(content)
    p = game.state.player
    p.member.wugong_id, p.member.neigong_id = "basic_fist", "basic_breath"
    game.world.start_battle(definition, now=0.0)
    with at(game, definition.muster_seconds + 1):
        game._battle_status()  # 集結關閉，已經開打
        game.choose("battle:join_late")
    assert game.world.get_battle().participants[p.name].scores == game._battle_scores()


def test_with_factions_the_muster_only_offers_your_own_side(content, game):
    """集結時只列自己陣營那一邊；硬送對方那一邊被擋回，而且什麼都不寫（江湖紀錄沒有多一則）。"""
    _install_factions(content)
    definition = _install_battle_def(content)
    game.state.player.faction = "huang"
    game.world.start_battle(definition, now=1000.0)
    before = len(game.state.journal)
    with at(game, 1000.0):
        assert [i for i in ids(game) if i.startswith("battle:")] == ["battle:join:huang"]
        assert game.choose("battle:join:guan") == ["（此刻無法這麼做。）"]
        assert len(game.state.journal) == before
        assert "選擇陣營" in game.scene_text()


def test_with_factions_an_outside_faction_enlists_and_keeps_playing(content, game):
    """不是交戰兩軍的陣營（地方豪強）不再一旁觀戰（Joy 2026-10-13）：跟散人一樣看到兩顆臨時投效，集結時照常遊玩。"""
    _install_factions(content)
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        game.state.player.faction = "haoqiang"
        assert "act:explore" in ids(game)
        assert [i for i in ids(game) if i.startswith("battle:")] == ["battle:enlist:guan", "battle:enlist:huang"]
        scene = game.scene_text()
        assert "測試決戰" in scene and "臨時投效" in scene and "觀戰" not in scene


def test_with_factions_a_free_agent_can_enlist_with_either_army_for_this_battle_only(content, game):
    """試玩回饋 2026-10-08：散人集結時可以臨時投效交戰的兩軍之一（不能投第三方），照常遊玩；只算這一場：
    參戰名單記投效的那一方，自己照樣是散人、不進投靠名冊；集結時還能改投另一邊。"""
    _install_factions(content)
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        assert game.state.player.faction is None
        assert "act:explore" in ids(game)
        assert [i for i in ids(game) if i.startswith("battle:")] == ["battle:enlist:guan", "battle:enlist:huang"]
        assert "臨時投效" in game.scene_text()
        assert "你臨時投效了官軍" in game.choose("battle:enlist:guan")[0]
        assert game.world.get_battle().participants[game.state.player.name].faction == "guan"
        assert game.state.player.faction is None and game.world.faction_counts().get("guan", 0) == 0
        opts = {o.id: (o.label, o.enabled) for o in game.options()}
        assert opts["battle:enlist:guan"] == ("已臨時投效【官軍】", False) and opts["battle:enlist:huang"][1]
        game.choose("battle:enlist:huang")  # 集結時改投
        assert game.world.get_battle().participants[game.state.player.name].faction == "huang"
        assert game.state.journal[0].title == "測試決戰・改投黃巾"


def test_with_factions_a_free_agent_can_enlist_late_and_fight_this_round(content, game):
    _install_factions(content)
    definition = _install_battle_def(content)
    definition.rounds_per_act = 3
    game.world.start_battle(definition, now=0.0)
    game.world.mutate_battle(lambda b: battle_instance.join_faction(b, "乙玩家", "huang", neili_cap=100.0))
    with at(game, definition.muster_seconds + 1):
        assert game._battle_status()[0].phase == "active"
        assert "act:explore" in ids(game)  # 還沒投效：照常遊玩，不鎖在戰場上
        assert [i for i in ids(game) if i.startswith("battle:")] == ["battle:enlist:guan", "battle:enlist:huang"]
        assert "這一回合就能出手" in game.choose("battle:enlist:guan")[0]
        assert game.world.get_battle().participants[game.state.player.name].faction == "guan"
        assert any(i.startswith("battle:act:guan_") for i in ids(game)) and "act:explore" not in ids(game)
        assert game.state.player.faction is None


def test_with_factions_a_free_agent_who_joined_a_faction_joins_its_side(content, game):
    _install_factions(content)
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=0.0)
    game.world.mutate_battle(lambda b: battle_instance.join_faction(b, "乙玩家", "huang", neili_cap=100.0))
    with at(game, definition.muster_seconds + 1):
        assert game._battle_status()[0].phase == "active"
        game.choose("faction:guan")
        game.choose("faction:confirm")
        assert game.state.player.faction == "guan"
        assert ids(game) == ["battle:join_late"]  # 投靠了交戰的一方，就能加入戰局


def _drifter_busy_with(game, busy):
    """散人眼前有事（FB-109 的四種）：擺好，回傳那件事寫在場景上、一定看得到的一句。"""
    from tianxia.features.sense import sensing
    from tianxia.models import InsightScene, SenseMethod

    s, c = game.state, game.content
    if busy == "event":
        s.pending_event = "drunk"
        return c.events["drunk"].text.split("\n")[0][:12]
    if busy == "faction":
        game.choose("faction:guan")  # 投靠的確認：「這一季不能改投」與三方人數寫在場景上
        return "投靠官軍"
    if busy == "talk":
        s.player.pending_companion = "mate"
        s.player.dialogue_history["mate"] = [{"role": "assistant", "content": "久仰大名，今日總算見著了。"}]
        return "久仰大名，今日總算見著了。"
    scene = InsightScene(
        id="town_bell", title="鐘聲", text="鐘聲從城樓上盪開。", tags=["城鎮"], hints=["慢"],
        methods=[SenseMethod(attribute=a, text=t) for a, t in (("柔", "聽聲"), ("剛", "敲鐘"), ("快", "追聲"), ("慢", "靜坐"))],
    )
    c.insight_scenes = {scene.id: scene}
    sensing.start(s, c, scene, random.Random(0))
    return "有所感・鐘聲"


@pytest.mark.parametrize("busy", ["event", "faction", "talk", "sense"])
def test_with_factions_a_drifter_who_has_not_enlisted_sees_their_own_scene_once_the_battle_runs(content, game, busy):
    """FB-109：開打後人在決戰的大區、還沒臨時投效的散人照常遊玩（投效兩顆接在平常的選單前面），場景也要跟集結期、觀戰的人一樣：
    戰場底下接自己眼前的事。以前開打後場景只回戰場，事件內文、有所感卡、人物的回話、投靠的確認都看不到，只剩按鈕。
    （現有的場景測試只看集結期；這裡是開打後。）"""
    _install_factions(content)
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=0.0)
    game.world.mutate_battle(lambda b: battle_instance.join_faction(b, "乙玩家", "huang", neili_cap=100.0))
    with at(game, definition.muster_seconds + 1):
        assert game._battle_status()[0].phase == "active"
        line = _drifter_busy_with(game, busy)
        assert [i for i in ids(game) if i.startswith("battle:")] == ["battle:enlist:guan", "battle:enlist:huang"]
        battle, _, own = game.scene_text().partition("\n\n---\n\n")
        assert "測試決戰" in battle and "回合" in battle
        assert line in own and "測試決戰" not in own


def test_with_factions_a_drifter_who_enlisted_after_the_start_sees_only_the_battle(content, game):
    """投效了（開打後才投效的也一樣）就是場上的人：選單整份換成三招，整個畫面就是戰場（FB-109 只改還沒投效的散人）。"""
    _install_factions(content)
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=0.0)
    game.world.mutate_battle(lambda b: battle_instance.join_faction(b, "乙玩家", "huang", neili_cap=100.0))
    with at(game, definition.muster_seconds + 1):
        game._battle_status()
        game.choose("battle:enlist:guan")
        scene = game.scene_text()
    assert "測試決戰" in scene and "---" not in scene and game.location_text() not in scene


def test_with_factions_a_latecomer_joins_their_own_side(content, game):
    _install_factions(content)
    definition = _install_battle_def(content)
    game.state.player.faction = "huang"
    game.world.start_battle(definition, now=0.0)
    # 黃巾已經有人了，單看人數平衡會把後來的人分去官軍；玩家仍要站在自己的黃巾這一邊。
    game.world.mutate_battle(lambda b: battle_instance.join_faction(b, "乙玩家", "huang", neili_cap=100.0))
    with at(game, definition.muster_seconds + 1):
        game._battle_status()
        game.choose("battle:join_late")
    assert game.world.get_battle().participants["沈浪"].faction == "huang"


def test_a_warlord_enlists_with_either_army_for_this_battle_only(game):
    """豪強集結時跟散人一樣看到兩軍各一顆臨時投效；投效了只算這一場：參戰名單記投效的那一軍，自己照樣是地方豪強。"""
    definition = _as_warlord(game)
    game.content.config.admins = [game.state.player.name]
    game.now = 0.0
    game.admin_start_battle(definition.id, now=0.0)
    battle = game.world.get_battle()
    assert [o.id for o in game._battle_options(battle, definition)] == ["battle:enlist:guan", "battle:enlist:huang"]
    assert "你是地方豪強的人，不是交戰的兩軍，可以臨時投效其中一方" in game._battle_scene_text(battle, definition)
    msgs = game._battle_choose("enlist:huang")
    assert msgs == ["你臨時投效了黃巾，只算這一場：打完你照樣是地方豪強的人。"]
    assert game.world.get_battle().participants[game.state.player.name].faction == "huang"
    assert game.state.player.faction == "haoqiang"
    assert game.state.journal[0].title == "三招決戰・臨時投效黃巾"
    assert "你已臨時投效【黃巾】" in game._battle_scene_text(game.world.get_battle(), definition)


def test_a_warlord_fights_with_the_army_it_enlisted_with(game):
    """開打之後豪強的招就是投效那一軍的三招，戰局條也站那一邊；沒有第三方的招，也沒有豪強那一欄戰功。"""
    battle, definition = _warlord_in_battle(game, "huang")
    ids = [o.id for o in game._battle_options(battle, definition)]
    assert ids and all(i.startswith("battle:act:huang_") for i in ids)
    g = game.battle_gauge()
    assert g["left"]["id"] == "huang" and "third" not in g and set(g["merit"]) == {"me", "left", "right"}


def test_a_warlord_can_enlist_late_once_the_battle_has_started(game):
    definition = _as_warlord(game)
    game.content.config.admins = [game.state.player.name]
    game.now = 0.0
    game.admin_start_battle(definition.id, now=0.0)
    game.world.mutate_battle(lambda b: battle_instance.join_faction(b, "乙", "huang", neili_cap=100.0))
    game.world.mutate_battle(lambda b: setattr(b, "muster_deadline_real", -1.0))
    game._run_battle_tick(definition)
    battle = game.world.get_battle()
    assert battle.phase == "active"
    assert [o.id for o in game._battle_options(battle, definition)] == ["battle:enlist:guan", "battle:enlist:huang"]
    assert "這一回合就能出手" in game._battle_choose("enlist:guan")[0]
    assert game.world.get_battle().participants[game.state.player.name].faction == "guan"


def test_an_army_member_cannot_enlist(game):
    """投效只給不是交戰兩軍的人：官軍的人送投效被擋回。"""
    definition = _as_warlord(game)
    game.state.player.faction = "guan"
    game.content.config.admins = [game.state.player.name]
    game.now = 0.0
    game.admin_start_battle(definition.id, now=0.0)
    assert game._battle_choose("enlist:huang") == ["（此刻無法這麼做。）"]
    assert game.world.get_battle().participants == {}


def test_a_warlord_rallies_to_the_battle_but_a_drifter_does_not(game):
    """假人照 rally_region 趕路：豪強要趕去臨時投效，散人不為了投效趕過去。"""
    definition = _as_warlord(game)
    here = atlas.region_of(game.content, game.state.player.location)
    definition.region = next(r.id for r in game.content.map.regions if here is None or r.id != here.id)
    game.content.config.admins = [game.state.player.name]
    game.now = 0.0
    game.admin_start_battle(definition.id, now=0.0)
    assert game.rally_region() == definition.region
    game.state.player.faction = None
    assert game.rally_region() is None

def test_a_battle_with_no_fighters_ends_with_its_fallback_outcome_once_the_round_times_out(content, game):
    _install_factions(content)
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=0.0)
    closed = definition.muster_seconds + 1
    with at(game, closed):
        assert game._battle_status()[0].phase == "active"
    with at(game, closed + definition.round_seconds - 1):
        assert game._battle_status() is not None  # 回合還沒逾時，不提前收場
    with at(game, closed + definition.round_seconds):
        assert "act:explore" in ids(game)
    assert game.world.get_battle().phase == "ended"
    assert any("官軍大勝" in r.text for r in game.world.get_season().chronicle)


def test_an_active_muster_shows_faction_join_options(content, game):
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        assert ids(game)[:2] == ["battle:join:guan", "battle:join:huang"]
        assert "測試決戰" in game.scene_text()


def test_a_fighter_who_joined_sees_it_on_the_button_and_in_the_scene(content, game):
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        game.choose("battle:join:guan")
    with at(game, 1000.0 + 125):
        opts = {o.id: (o.label, o.enabled) for o in game.options()}
        assert opts["battle:join:guan"] == ("已加入【官軍】", False)
        assert opts["battle:join:huang"] == ("加入【黃巾】", True)  # 不分陣營的劇本：集結時還能換邊
        assert opts["act:explore"][1] and "move:lake" in opts
        scene = game.scene_text()
        assert "你已加入【官軍】，集結還剩現實 7 分 55 秒" in scene and "選擇陣營" not in scene
        assert game.choose("battle:join:guan") == ["（此刻無法這麼做。）"]


def test_with_factions_a_fighter_who_joined_only_sees_joined(content, game):
    _install_factions(content)
    definition = _install_battle_def(content)
    game.state.player.faction = "huang"
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        game.choose("battle:join:huang")
        battle_ids = [o for o in game.options() if o.id.startswith("battle:")]
        assert [(o.id, o.label, o.enabled) for o in battle_ids] == [("battle:join:huang", "已加入【黃巾】", False)]


def test_the_battle_scene_shows_which_round_of_how_many(content, game):
    """FB-016：決戰的場景在幕名後面寫第幾回合、一共幾回合，讓人知道還要打多久。"""
    definition = _install_battle_def(content)
    definition.rounds_per_act = 3  # 一幕三回合：整場 3 回合
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
        game.world.mutate_battle(lambda b: battle_instance.join_faction(b, "乙玩家", "huang", neili_cap=100.0))
    with at(game, definition.muster_seconds + 1):
        game._battle_status()  # 開打
        assert "【初探】（第 1／3 回合・已送出 0／在場 2，最遲 2 分 0 秒後結算）雙方試探。" in game.scene_text()
        game.world.mutate_battle(lambda b: battle_instance.submit_action(b, "乙玩家", "huang_hold"))
        assert "（第 1／3 回合・已送出 1／在場 2，" in game.scene_text()  # 在等人，不是壞了（試玩回饋 2026-10-08）
        game.choose("battle:act:guan_hold")  # 兩人都出手了：第 1 回合結算
        assert game.world.get_battle().round_number == 1
        assert "【初探】（第 2／3 回合・已送出 0／在場 2，" in game.scene_text()


def test_the_fighting_menu_still_replaces_everything_once_the_muster_closes(content, game):
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        game.choose("battle:join:guan")
    with at(game, 1000.0 + 601):
        assert ids(game) == ["battle:act:guan_strong", "battle:act:guan_hold", "battle:act:guan_raid"]


def test_an_unfinished_battle_is_dropped_without_its_outcome_when_the_season_ends(content, game):
    """季一結束，沒打完的決戰直接收掉、不套用結果（這一季勝負已經定了），參戰者回到休季畫面（試玩回饋 FB-015）。"""
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        game.choose("battle:join:guan")
    with at(game, 1000.0 + 601):
        assert ids(game) == ["battle:act:guan_strong", "battle:act:guan_hold", "battle:act:guan_raid"]  # 開打了
    trends = dict(game.world.get_season().trends)
    game.world.mutate_season(lambda season: (setattr(season, "ended", True), setattr(season, "ending_title", "天下太平")))
    game.sync(1000.0 + 700)
    with at(game, 1000.0 + 700):
        assert ids(game) == ["season:resting"]
        assert "測試決戰" not in game.scene_text()
    assert game.world.get_battle() is None
    assert dict(game.world.get_season().trends) == trends  # 沒有套用決戰的結果
    assert not any("官軍大勝" in entry.text for entry in game.world.get_season().chronicle)


def test_joining_a_faction_during_muster(content, game):
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        game.choose("battle:join:guan")
    assert game.world.get_battle().participants["沈浪"].faction == "guan"


def test_muster_auto_closes_once_the_deadline_passes(content, game):
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        game.choose("battle:join:guan")
    with at(game, 1000.0 + definition.muster_seconds + 1):
        status = game._battle_status()
    assert status is not None and status[0].phase == "active"


def _a_round_against_a_bot(content, game):
    """沈浪站官軍、一個機器人站黃巾；集結一過，沈浪送出固守。回傳之後的戰局。"""
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
        game.world.mutate_battle(
            lambda b: battle_instance.join_faction(b, "機器人", "huang", neili_cap=100.0, is_bot=True)
        )
    with at(game, definition.muster_seconds + 1):
        game._battle_status()  # 推進一次，確保集結已關閉、進入 active
        game.choose("battle:act:guan_hold")  # 人類送出，機器人在同一次 tick 裡自動補上，回合應該已經結算
    return game.world.get_battle()


def test_submitting_an_action_and_a_bot_auto_fills_then_the_round_resolves(content, game):
    battle = _a_round_against_a_bot(content, game)
    assert battle.trend != 50  # 已經結算過，trend 被推動了
    assert battle.round.pending_actions == {}  # 回合已經重置


def test_the_player_whose_action_completes_the_round_sees_the_resolution_text(content, game):
    """送出最後一個行動的那個人，自己這次 choose() 的回傳就該看到這一回合真正發生的事
    （不能是空清單）——不管這回合只是普通推進，還是剛好把戰鬥打完。"""
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
        game.world.mutate_battle(
            lambda b: battle_instance.join_faction(b, "機器人", "huang", neili_cap=100.0, is_bot=True)
        )
    after_muster = definition.muster_seconds + 1
    with at(game, after_muster):
        game._battle_status()
        msgs = game.choose("battle:act:guan_hold")
    assert msgs != []
    assert any("官軍大勝" in m or "官軍獲勝" in m for m in msgs)  # _install_battle_def 的保底結果沒有數值門檻，第一回合就分出勝負


def test_waiting_for_others_returns_a_placeholder_message(content, game):
    """送出行動但還有人沒選完，回合不會結算：至少要有個訊息，不能讓畫面看起來像沒反應。"""
    definition = _install_battle_def(content)
    definition.rounds_per_act = 3  # 讓這回合分不出勝負
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
        game.world.mutate_battle(lambda b: battle_instance.join_faction(b, "乙玩家", "huang", neili_cap=100.0))
    after_muster = definition.muster_seconds + 1
    with at(game, after_muster):
        game._battle_status()
        msgs = game.choose("battle:act:guan_hold")
    assert msgs == ["你選擇了行動，等待其他人……"]


def test_battle_outcome_applies_trend_delta_and_flags_to_the_shared_season(content, game):
    definition = _install_battle_def(content)
    definition.outcomes[0] = definition.outcomes[0].model_copy(
        update={"world_flags_add": ["huangjin_decisive_win"], "trend_delta": {"kou": -40}}
    )
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
        game.world.mutate_battle(
            lambda b: battle_instance.join_faction(b, "機器人", "huang", neili_cap=100.0, is_bot=True)
        )
    before = game.world.get_season().trends["kou"]
    after_muster = definition.muster_seconds + 1
    with at(game, after_muster):
        game._battle_status()
        game.choose("battle:act:guan_hold")
    season = game.world.get_season()
    assert season.trends["kou"] == max(0, before - 40)
    assert "huangjin_decisive_win" in season.flags
    assert any("官軍大勝" in r.text for r in season.chronicle)


def test_a_battle_that_ends_inside_a_normal_choice_keeps_its_trend_and_flags(content, game):
    """旁觀者按一般選項時，options() 的決戰 tick 剛好讓決戰收場：結果寫進共用賽季之後，choose() 最後的
    _save_season 不能拿記憶體裡比較舊的賽季把大勢與旗標蓋掉（總審查重現過：kou 停在原值、旗標不見）。"""
    _install_factions(content)
    definition = _install_battle_def(content)
    definition.outcomes[0] = definition.outcomes[0].model_copy(
        update={"world_flags_add": ["huangjin_decisive_win"], "trend_delta": {"kou": -40}}
    )
    game.world.start_battle(definition, now=0.0)
    game.world.mutate_battle(lambda b: battle_instance.join_faction(b, "官軍機器人", "guan", neili_cap=100.0, is_bot=True))
    game.world.mutate_battle(lambda b: battle_instance.join_faction(b, "黃巾機器人", "huang", neili_cap=100.0, is_bot=True))
    game.sync(0.0)
    before = game.state.world.trends["kou"]
    assert before > 0  # 才看得出被扣掉
    with at(game, definition.muster_seconds + 1):  # 集結關閉、兩個機器人補位、這一回合就分出勝負——全在 options() 的 tick 裡
        game.choose("act:explore")
    assert game.world.get_battle().phase == "ended"
    season = game.world.get_season()
    assert season.trends["kou"] == max(0, before - 40)
    assert "huangjin_decisive_win" in season.flags and "huangjin_decisive_win" in season.flag_times
    assert sum("官軍大勝" in r.text for r in season.chronicle) == 1  # 江湖史只寫一則
    assert game.state.world.trends["kou"] == season.trends["kou"]  # 記憶體裡的那份也跟上了


def test_a_battle_ended_by_a_tick_survives_a_later_travel_save(content, game):
    """同一個根因的另一條路：先有一次 options() 的 tick 把決戰收了場，之後 travel() 的 _save_season 也不能蓋掉它。"""
    _install_factions(content)
    definition = _install_battle_def(content)
    definition.outcomes[0] = definition.outcomes[0].model_copy(
        update={"world_flags_add": ["huangjin_decisive_win"], "trend_delta": {"kou": -40}}
    )
    game.world.start_battle(definition, now=0.0)
    game.world.mutate_battle(lambda b: battle_instance.join_faction(b, "官軍機器人", "guan", neili_cap=100.0, is_bot=True))
    game.world.mutate_battle(lambda b: battle_instance.join_faction(b, "黃巾機器人", "huang", neili_cap=100.0, is_bot=True))
    game.sync(0.0)
    before = game.state.world.trends["kou"]
    with at(game, definition.muster_seconds + 1):
        game.options()  # 決戰在這裡的 tick 收場
        game.travel("lake")
        assert game.state.player.journey is not None  # 真的出發了，_save_season 才跑得到
    season = game.world.get_season()
    assert game.world.get_battle().phase == "ended"
    assert season.trends["kou"] == max(0, before - 40)
    assert "huangjin_decisive_win" in season.flags


def test_an_eliminated_participant_sees_a_spectate_only_option(content, game):
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
    # 場上還有別人站著：只剩倒下的人時當場用保底收場（U-08），就沒有觀戰這一刻了
    game.world.mutate_battle(lambda b: battle_instance.join_faction(b, "同袍", "guan", neili_cap=100.0))
    after_muster = definition.muster_seconds + 1
    with at(game, after_muster):
        game._battle_status()  # 讓集結自動關閉
    game.world.mutate_battle(lambda b: setattr(b.participants["沈浪"], "eliminated", True))
    with at(game, after_muster):
        opts = game.options()
    assert opts == [Option(id="battle:spectate", label="（觀戰中，無法行動）", enabled=False)]


def test_a_latecomer_can_join_an_already_active_battle(content, game):
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=0.0)
    with at(game, definition.muster_seconds + 1):
        game._battle_status()  # 讓集結自動關閉，模擬戰鬥已經開打
        assert ids(game) == ["battle:join_late"]
        game.choose("battle:join_late")
    assert "沈浪" in game.world.get_battle().participants


def test_a_latecomer_is_told_they_can_act_this_round_and_can(content, game):
    """FB-028：晚到的人當回合就能出招（企劃者決定改說法、不改規則），提示要照實說。"""
    definition = _install_battle_def(content)
    definition.rounds_per_act = 3  # 這一回合不會一結算就收場
    game.world.start_battle(definition, now=0.0)
    game.world.mutate_battle(lambda b: battle_instance.join_faction(b, "乙玩家", "huang", neili_cap=100.0))
    with at(game, definition.muster_seconds + 1):
        game._battle_status()  # 集結關閉，已經開打
        assert game.choose("battle:join_late") == ["你趕到了戰場，這一回合就能出手。"]
        battle = game.world.get_battle()
        assert battle_instance.options_for(battle, definition, "沈浪")
        assert ids(game) == ["battle:act:guan_strong", "battle:act:guan_hold", "battle:act:guan_raid"]
        game.choose("battle:act:guan_hold")
    battle = game.world.get_battle()
    assert battle.round_number == 0 and battle.round.pending_actions == {"沈浪": "guan_hold"}  # 送出了、等乙玩家


# ── 決戰選項的江湖紀錄（FB-030：加入與趕到各寫一則，每回合出招不寫）──────────────


def test_joining_a_side_in_the_muster_writes_one_journal_entry(content, game):
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=0.0)
    before = len(game.state.journal)
    with at(game, 0.0):
        msgs = game.choose("battle:join:guan")
    assert msgs == ["你加入了這場戰局。"]  # 回話照舊
    assert len(game.state.journal) == before + 1
    entry = game.state.journal[0]
    assert entry.title == "測試決戰・加入官軍" and entry.lines == ["你加入了這場戰局。"]


def test_changing_sides_in_the_muster_writes_its_own_entry(content, game):
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
        before = len(game.state.journal)
        game.choose("battle:join:huang")
    assert len(game.state.journal) == before + 1
    assert game.state.journal[0].title == "測試決戰・改選黃巾"


def test_joining_late_writes_one_journal_entry_with_the_line_it_returns(content, game):
    definition = _install_battle_def(content)
    definition.rounds_per_act = 3
    game.world.start_battle(definition, now=0.0)
    game.world.mutate_battle(lambda b: battle_instance.join_faction(b, "乙玩家", "huang", neili_cap=100.0))
    before = len(game.state.journal)
    with at(game, definition.muster_seconds + 1):
        game._battle_status()
        msgs = game.choose("battle:join_late")
    assert msgs == ["你趕到了戰場，這一回合就能出手。"]
    assert len(game.state.journal) == before + 1
    entry = game.state.journal[0]
    assert entry.title == "測試決戰・趕到戰場" and entry.lines == msgs


def test_a_rounds_action_is_not_journaled(content, game):
    """每回合一句太吵：戰局的敘事在場景裡，收場後補送的那一則才留下完整的結果。"""
    definition = _install_battle_def(content)
    definition.rounds_per_act = 3
    game.world.start_battle(definition, now=0.0)
    game.world.mutate_battle(lambda b: battle_instance.join_faction(b, "乙玩家", "huang", neili_cap=100.0))
    with at(game, definition.muster_seconds + 1):
        game._battle_status()
        game.choose("battle:join_late")
        before = len(game.state.journal)
        assert game.choose("battle:act:guan_hold") == ["你選擇了行動，等待其他人……"]
    assert len(game.state.journal) == before


def test_the_join_entry_is_what_the_just_now_card_shows(content, game):
    """加入寫的那則不是戰鬥紀錄（沒有 battle_id）：「剛剛」放那一則本身，不放戰鬥卡片。"""
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
        assert not game.shows_battle_card()
        assert "加入官軍" in game.latest_entry_html()


def _showdown_entries(game):
    """收場補送的那一則（掛著戰報的 battle_id）；加入、趕到寫的紀錄（FB-030）標題也有決戰的名字，但不是戰報。"""
    return [e for e in game.state.journal if "測試決戰" in e.title and e.battle_id is not None]


def test_every_fighter_gets_the_showdown_in_their_journal_and_battle_reports(content, game):
    definition = _three_round_showdown(content)
    game.state.player.faction = "guan"
    fallen = _fighter(content, game, "乙", "huang")
    watcher = Game.new(content, "丙", rng=random.Random(2), world=game.world)  # 散人：打不了，只能觀戰
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0), at(fallen, 0.0):
        game.choose("battle:join:guan")
        fallen.choose("battle:join:huang")
    game.world.mutate_battle(lambda b: setattr(b.participants["乙"], "neili", 20.0))  # 固守扣 15：第 2 回合倒下
    start = definition.muster_seconds + 1
    for i in range(3):
        with at(game, start + i), at(fallen, start + i):
            game.choose("battle:act:guan_hold")
            if i < 2:
                fallen.choose("battle:act:huang_hold")  # 兩人都出手了：這一回合結算
    assert game.world.get_battle().phase == "ended"

    entry = game.state.journal[0]  # 收場那一下出手的人當場就有
    assert (entry.title, entry.tag) == ("測試決戰・官軍大勝", "你站在官軍")
    assert entry.lines == [  # 結果之後寫勝負的關鍵（試玩回饋 2026-10-08）
        "官軍獲勝。", "勝負的關鍵：第 1 回合，黃巾氣血耗損，漸漸撐不住官軍，沈浪帶頭固守；第 3 回合，黃巾沒有人正面出陣迎戰，官軍放手壓了上去，沈浪帶頭固守。",
        "你出手 3 回合", "你帶頭衝陣、替自己這一邊佔了上風 3 回合",  # 出固定招的人也有名字（Joy 2026-10-10）
        "你的戰功 15，在官軍排第 1／1（出手 3 回合、帶頭佔上風 3 回合）",  # 個人戰功（Joy 2026-10-10）
        "你是官軍這一仗的首功，名字傳遍了江湖。",
    ]
    assert entry.changes == ["寇亂 -20", "名望 +2"]
    report = game.state.battles[0]
    assert report.kind == "showdown" and entry.battle_id == report.id
    assert (report.opponent, report.side, report.tier) == ("黃巾", "官軍", "官軍大勝")
    assert game.shows_battle_card()  # 「剛剛」放這一場的卡片，連得到完整戰報
    assert "威力" not in game.battle_detail(report.id)

    assert _showdown_entries(fallen) == []  # 倒下的那位：下次同步時才補
    fallen.sync(start + 10)
    mine = fallen.state.journal[0]
    assert (mine.title, mine.tag) == ("測試決戰・官軍大勝", "你站在黃巾")
    assert mine.lines[0] == "官軍獲勝。" and mine.lines[1].startswith("勝負的關鍵：")
    assert mine.lines[2:] == [
        "你出手 2 回合", "你在第 2 回合倒下，轉為觀戰", "你的戰功 4，在黃巾排第 1／1（出手 2 回合）", "你是黃巾這一仗的首功，名字傳遍了江湖。",
    ]
    assert (game.state.player.showdowns, game.state.player.top_merits) == (1, 1)
    assert fallen.state.battles[0].kind == "showdown" and fallen.state.battles[0].opponent == "官軍"

    watcher.sync(start + 10)
    assert _showdown_entries(watcher) == [] and watcher.state.battles == []

    for g in (game, fallen):  # 再同步一次不會多寫
        g.sync(start + 20)
        assert len(_showdown_entries(g)) == 1 and len(g.state.battles) == 1


def test_an_offline_fighter_gets_the_showdown_on_the_next_sync_without_the_timed_out_rounds(content, game):
    """乙出了第 1 回合就下線（角色只在資料庫裡）：後兩回合逾時由系統代選，不算他自己出手；回來第一次同步就補到。"""
    definition = _three_round_showdown(content)
    game.state.player.faction = "guan"
    away = _fighter(content, game, "乙", "huang")
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0), at(away, 0.0):
        game.choose("battle:join:guan")
        away.choose("battle:join:huang")
    start = definition.muster_seconds + 1
    with at(game, start), at(away, start):
        game.choose("battle:act:guan_hold")
        away.choose("battle:act:huang_hold")
    open_characters().save(away.state)
    end = _fight_to_the_end(game, definition, start + 1)
    assert "你出手 3 回合" in game.state.journal[0].lines

    back = Game(content, open_characters().load("乙"), rng=random.Random(3), world=game.world)
    assert _showdown_entries(back) == []  # 讀回來還沒同步：還沒補
    back.sync(end + 10)
    entry = back.state.journal[0]
    assert entry.title == "測試決戰・官軍大勝" and entry.changes == ["寇亂 -20", "名望 +2"]  # 黃巾只有他一個：首功
    assert "你出手 1 回合" in entry.lines and not any("倒下" in line for line in entry.lines)
    assert back.state.battles[0].kind == "showdown"


def _showdown_ends_the_season(content, game):
    """寇亂 30 → 80 跨過收季的門檻：決戰收場、季的時鐘再走一個鐘頭，季就收了。乙加入之後就下線。回傳那時的時間。"""
    content.config.decisive_from_week = 1  # 這一支不是在測收季門檻要等到決定性那一週（FB-165，test_world 另測）：關掉那一道
    definition = _three_round_showdown(content, trend_delta={"kou": 50})
    game.state.player.faction = "guan"
    away = _fighter(content, game, "乙", "huang")
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0), at(away, 0.0):
        game.choose("battle:join:guan")
        away.choose("battle:join:huang")
    open_characters().save(away.state)
    end = _fight_to_the_end(game, definition, definition.muster_seconds + 1)
    with at(game, end):
        game.advance(HOUR)
    assert game.world.season_phase() == "resting"
    return end


def test_a_fighter_back_during_the_off_season_gets_the_showdown_that_ended_it(content, game):
    end = _showdown_ends_the_season(content, game)
    back = Game(content, open_characters().load("乙"), rng=random.Random(3), world=game.world)
    back.sync(end + 10)
    assert ids(back) == ["season:resting"]
    entry = back.state.journal[0]
    assert entry.title == "測試決戰・官軍大勝" and entry.changes == ["寇亂 +50"]  # 還是這一季打的：大勢照常是數值變化；全程掛機不拿首功
    assert "你出手 0 回合" in entry.lines
    open_characters().save(back.state)

    game.world.next_season(content, now=end + 20)  # 補過的那一場，到了下一季不會再補一次
    again = Game(content, open_characters().load("乙"), rng=random.Random(4), world=game.world)
    again.sync(end + 30)
    assert _showdown_entries(again) == [] and again.state.battles == []


def test_a_fighter_first_back_next_season_gets_last_seasons_showdown_marked_with_its_season(content, game):
    end = _showdown_ends_the_season(content, game)
    game.world.next_season(content, now=end + 20)
    back = Game(content, open_characters().load("乙"), rng=random.Random(3), world=game.world)
    back.sync(end + 30)
    entry = back.state.journal[0]
    assert (entry.title, entry.tag) == ("第 1 季・測試決戰・官軍大勝", "你站在黃巾")
    assert entry.changes == []  # 上一季的大勢不放進數值變化：那看起來像剛發生在你身上
    assert "（第 1 季）寇亂 +50" in entry.lines
    report = back.state.battles[0]
    assert report.kind == "showdown" and report.location.startswith("第 1 季・") and report.changes == []
    (_, battle), = game.world.ended_battles()
    assert battle.end_time is not None
    assert entry.time == report.time == battle.end_time  # 收場時（第 1 季）的時間，不是補送這一刻
    assert battle.end_time != back.state.world.time  # 這一季的時鐘
    back.sync(end + 40)
    assert len(_showdown_entries(back)) == 1 and len(back.state.battles) == 1


# ── 季終時沒打完的決戰：不算勝負，但參戰者補一則江湖紀錄（FB-035）──────────────

SHELVED_LINE = "季終了，這場決戰沒打完就各自收兵，不算勝負。"


def _showdown_under_way(content, game):
    """一幕三回合的決戰打到第 2 回合還在等人：沈浪（官軍、在線）與乙（黃巾，出完第 1 回合就下線，角色只在資料庫裡）
    各出手 1 回合；散人丙在一旁觀戰。回傳（丙, 現在的時間）。"""
    definition = _three_round_showdown(content)
    game.state.player.faction = "guan"
    away = _fighter(content, game, "乙", "huang")
    watcher = Game.new(content, "丙", rng=random.Random(2), world=game.world)
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0), at(away, 0.0):
        game.choose("battle:join:guan")
        away.choose("battle:join:huang")
    start = definition.muster_seconds + 1
    with at(game, start), at(away, start):
        game.choose("battle:act:guan_hold")
        away.choose("battle:act:huang_hold")  # 兩人都出手了：第 1 回合結算
    open_characters().save(away.state)
    battle = game.world.get_battle()
    assert battle.phase == "active" and battle.round_number == 1
    return watcher, start


def _assert_got_the_shelved_note(fighter, side, label=""):
    """補到的是一則只有江湖紀錄的交代：沒有戰報、沒有「剛剛」的戰鬥卡片、沒有數值變化；再同步也不重複。"""
    entry = fighter.state.journal[0]
    assert (entry.title, entry.tag) == (f"{label}測試決戰・未分勝負", f"你站在{side}")
    assert entry.lines == [SHELVED_LINE, "你出手 1 回合"]
    assert entry.changes == [] and entry.battle_id is None
    assert fighter.state.battles == [] and fighter.state.battle_card is None and not fighter.shows_battle_card()
    fighter.sync(entry.time + 1000.0)
    assert [e.title for e in fighter.state.journal].count(entry.title) == 1


def test_admin_ending_the_season_tells_each_fighter_the_battle_was_shelved(content, game):
    content.config.admins = ["管理者"]
    admin = Game.new(content, "管理者", rng=random.Random(5), world=game.world)
    watcher, now = _showdown_under_way(content, game)
    season = game.world.get_season()
    trends, flags, chronicle = dict(season.trends), set(season.flags), len(season.chronicle)

    admin.admin_end_season(now=now)

    assert game.world.get_battle() is None
    after = game.world.get_season()
    assert dict(after.trends) == trends and set(after.flags) == flags  # 不套任何結果
    assert not any("未分勝負" in entry.text or "官軍大勝" in entry.text for entry in after.chronicle[chronicle:])
    (_, shelved), = game.world.ended_battles()  # 標成收場、才補送得到；但記著它沒打完
    assert shelved.unfinished and shelved.outcome_title == "未分勝負" and shelved.outcome_text is None
    assert shelved.end_time == after.time
    assert not any("未分勝負" in e.title for e in admin.state.journal)  # 管理者沒參戰：什麼都沒有

    online = game
    offline = Game(content, open_characters().load("乙"), rng=random.Random(3), world=game.world)
    assert not any("未分勝負" in e.title for e in offline.state.journal)  # 讀回來還沒同步：還沒補
    online.sync(now + 10)
    offline.sync(now + 10)
    _assert_got_the_shelved_note(online, "官軍")
    _assert_got_the_shelved_note(offline, "黃巾")
    watcher.sync(now + 10)  # 觀戰的人照舊什麼都沒有
    assert not any("未分勝負" in e.title for e in watcher.state.journal) and watcher.state.battles == []


def test_a_season_that_ends_on_its_own_tells_each_fighter_too(content, game):
    watcher, now = _showdown_under_way(content, game)
    with at(game, now):
        game.advance(2 * DAY)  # 快轉到季末，季自己收了
    assert game.state.world.ended and game.world.get_battle() is not None  # 還沒有人刷新畫面：決戰還掛著
    trends = dict(game.world.get_season().trends)

    with at(game, now + 1):
        assert ids(game) == ["season:resting"]  # 畫面刷新那一下把沒打完的收起來
    assert game.world.get_battle() is None
    assert dict(game.world.get_season().trends) == trends  # 官軍大勝的 -20 沒有套
    (_, shelved), = game.world.ended_battles()
    assert shelved.unfinished and shelved.outcome_title == "未分勝負"

    offline = Game(content, open_characters().load("乙"), rng=random.Random(3), world=game.world)
    game.sync(now + 10)
    offline.sync(now + 10)
    _assert_got_the_shelved_note(game, "官軍")
    _assert_got_the_shelved_note(offline, "黃巾")
    watcher.sync(now + 10)
    assert not any("未分勝負" in e.title for e in watcher.state.journal)


def test_a_fighter_first_back_next_season_gets_the_shelved_note_marked_with_its_season(content, game):
    content.config.admins = ["管理者"]
    admin = Game.new(content, "管理者", rng=random.Random(5), world=game.world)
    _, now = _showdown_under_way(content, game)
    admin.admin_end_season(now=now)
    admin.admin_next_season(now=now + 5)
    back = Game(content, open_characters().load("乙"), rng=random.Random(3), world=game.world)
    back.sync(now + 10)
    assert back.state.player.season_number == 2
    _assert_got_the_shelved_note(back, "黃巾", label="第 1 季・")
    (_, shelved), = game.world.ended_battles()
    assert back.state.journal[0].time == shelved.end_time  # 收季那一刻（第 1 季）的時間，不是補送這一刻


def test_opening_the_next_season_shelves_a_battle_nobody_ticked_after_the_natural_end(content, game):
    """季自然結束、到管理者開下一季之前沒有人同步過（沒人走到 _battle_status 收掉它）：開下一季先把它收起來，
    參戰者照樣補得到「不算勝負」那一則，不會被換季靜靜清掉（FB-035）。"""
    content.config.admins = ["管理者"]
    admin = Game.new(content, "管理者", rng=random.Random(5), world=game.world)
    _, now = _showdown_under_way(content, game)
    game.world.mutate_season(lambda season: (setattr(season, "ended", True), setattr(season, "ending_title", "天下太平")))
    ended_at = game.world.get_season().time

    admin.admin_next_season(now=now + 5)

    assert game.world.get_season_number() == 2
    (_, shelved), = game.world.ended_battles()
    assert shelved.unfinished and shelved.end_time == ended_at
    back = Game(content, open_characters().load("乙"), rng=random.Random(3), world=game.world)
    back.sync(now + 10)
    _assert_got_the_shelved_note(back, "黃巾", label="第 1 季・")


def test_a_shelved_battle_that_is_still_linked_is_not_taken_for_a_normal_finish(content, game):
    """收季時「標成 ended＋unfinished」與「清掉」是兩步（同一筆交易裡）。就算有人在兩步之間看到它還掛著，也不能當成
    剛打完去套結果：_battle_status 看到的是本來就 ended 的，_apply_battle_outcome 認得 unfinished、直接不動。"""
    definition = _three_round_showdown(content, trend_delta={"kou": -20})
    game.state.player.faction = "guan"
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
    game.world.mutate_battle(lambda b: (
        setattr(b, "phase", "ended"), setattr(b, "unfinished", True), setattr(b, "outcome_title", "未分勝負"),
    ))
    season = game.world.get_season()
    trends, chronicle = dict(season.trends), len(season.chronicle)
    with at(game, 1.0):
        assert game._battle_status() is None
    game._apply_battle_outcome(game.world.get_battle())
    after = game.world.get_season()
    assert dict(after.trends) == trends and len(after.chronicle) == chronicle
    assert dict(game.state.world.trends) == trends


def test_you_can_join_a_battle_only_in_its_region(content, game):
    definition = _install_battle_def(content)
    definition.region = "south"
    _south_cave(content, game)
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        assert "act:explore" in ids(game)  # 人在北區：照常遊玩
        assert "這場決戰在測試南區" in game.scene_text()
        assert game._battle_choose("join:guan") == ["（這場決戰在測試南區，人要到了那裡、不在路上才能加入。）"]
        game.state.player.location = "cave"
        assert ids(game)[:2] == ["battle:join:guan", "battle:join:huang"]  # 集結中：加入的按鈕在平常的選單前面


def test_nobody_on_the_road_can_join(content, game):
    definition = _install_battle_def(content)  # 不限地點
    game.choose("move:lake")  # 先出發：在路上的人不算到了戰場
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        assert not any(i.startswith("battle:") for i in ids(game))
        assert game._battle_choose("join:guan") == ["（你還在路上，到了才能加入戰局。）"]


def test_arriving_mid_battle_lets_you_join_late(content, game):
    definition = _install_battle_def(content)
    definition.region = "south"
    _south_cave(content, game)
    game.world.start_battle(definition, now=0.0)
    with at(game, definition.muster_seconds + 1):
        assert game._battle_status()[0].phase == "active"
        assert "act:explore" in ids(game)
        game.travel("cave", "dash")
        assert ids(game) == ["battle:join_late"]


def test_a_fighter_who_leaves_the_region_sits_the_rounds_out_until_back(content, game):
    definition = _install_battle_def(content)
    definition.region = "north"
    definition.rounds_per_act = 3  # 不要一回合就分出勝負
    _south_cave(content, game)
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
        game.world.mutate_battle(lambda b: battle_instance.join_faction(b, "乙玩家", "huang", neili_cap=100.0))
    with at(game, definition.muster_seconds + 1):
        game._battle_status()  # 開打
        game.travel("cave", "dash")  # 離開北區
        battle = game.world.get_battle()
        assert battle.participants["沈浪"].away
        assert "act:explore" in ids(game) and "你離開了測試北區" in game.scene_text()
        assert game.battle_free_text_prompt() is None
        game.world.mutate_battle(lambda b: battle_instance.submit_action(b, "乙玩家", "huang_hold"))
        assert battle_instance.round_is_complete(game.world.get_battle())  # 不等離開的人
        game.travel("lake", "dash")  # 回到北區
        assert not game.world.get_battle().participants["沈浪"].away
        assert any(i.startswith("battle:act:") for i in ids(game))


def test_a_fighter_walking_inside_the_region_can_still_change_sides_during_the_muster(content, game):
    """已經報名的人在區內站與站之間走動，集結期還看得到改選陣營的按鈕；按下去是改選、不是「加入」，
    不能被「人要到了那裡、不在路上才能加入」擋下。"""
    definition = _install_battle_def(content)
    definition.region = "north"
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
        game.travel("lake", "walk")
        assert game.state.player.journey is not None
        assert "battle:join:huang" in ids(game)
        assert game.choose("battle:join:huang") == ["你加入了這場戰局。"]
    participant = game.world.get_battle().participants["沈浪"]
    assert participant.faction == "huang" and not participant.away


@pytest.mark.parametrize("region, away", [("north", True), (None, False)], ids=["a-battle-in-the-north", "a-battle-with-no-region"])
def test_walking_out_of_the_battles_region_is_away_from_the_start_only_when_it_has_a_region(content, game, region, away):
    """小鎮—湖邊在北區，終點寶洞在南區：這一趟還沒走到的站有一個在區外，一出發就算離開。不限地點的決戰（region 是 None）
    沒有大區，就沒有「離開」。"""
    definition = _install_battle_def(content)
    definition.region = region
    _south_cave(content, game)
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
    game.travel("cave", "walk")
    assert game.state.player.journey is not None
    assert game.world.get_battle().participants["沈浪"].away is away


def test_rally_region_names_a_battle_you_should_head_for(content, game):
    _install_factions(content)
    definition = _install_battle_def(content)
    definition.region = "south"
    _south_cave(content, game)
    game.state.player.faction = "guan"
    assert game.rally_region() is None  # 沒有決戰
    game.world.start_battle(definition, now=time.time())
    assert game.rally_region() == "south"
    game.state.player.faction = "haoqiang"
    assert game.rally_region() == "south"  # 豪強趕去臨時投效（Joy 2026-10-13）
    game.state.player.faction = None
    assert game.rally_region() is None  # 散人不為了投效趕過去
    game.state.player.faction = "guan"
    game.state.player.location = "cave"
    assert game.rally_region() is None  # 已經在南區
    definition.region = None
    game.state.player.location = "town"
    assert game.rally_region() is None  # 不限地點的決戰不用趕


def test_rally_region_sends_a_fighter_who_left_the_region_back_unless_they_have_fallen(content, game):
    definition = _joined_a_battle_in_the_north(content, game)
    with at(game, definition.muster_seconds + 1):
        game._battle_status()  # 開打
        assert game.rally_region() is None  # 人在戰場上
        game.travel("cave", "dash")  # 離開北區
        assert game.rally_region() == "north"  # 參戰了卻離開大區：該趕回去
        game.world.mutate_battle(lambda b: setattr(b.participants["沈浪"], "eliminated", True))
        assert game.rally_region() is None  # 已經倒下，趕回去也沒得打


def test_free_text_option_is_excluded_from_the_button_list(content, game):
    definition = _install_battle_def_with_free_text(content)
    after_muster = _join_and_open(content, game, definition)
    with at(game, after_muster):
        labels = [o.label for o in game.options()]
        assert len(labels) == 3 and not any("放手一搏" in label for label in labels)  # 自訂行動不是按鈕，只有三招


def test_battle_free_text_prompt_shows_when_available(content, game):
    definition = _install_battle_def_with_free_text(content)
    after_muster = _join_and_open(content, game, definition)
    with at(game, after_muster):
        assert game.battle_free_text_prompt() == "放手一搏（20字內）"
        # 輸入框旁邊講清楚賭的是什麼（試玩回饋 2026-10-08），成功率不事前寫
        assert "重傷的是你自己" in game.battle_free_text_note() and "%" not in game.battle_free_text_note()


def test_battle_free_text_note_warns_when_one_more_miss_would_drop_you(content, game):
    # 長社火攻 14 個真人倒下 12 個，都是自己放手一搏失手扣光的（PM 2026-10-15）：撐不過一次最壞的失手時多一句，不寫數字
    from tianxia.models import FreeTextGamble

    definition = _install_battle_def_with_free_text(content)
    definition.free_text_gamble = FreeTextGamble()  # 最壞的失手扣池子上限的 35%
    after_muster = _join_and_open(content, game, definition)
    name = game.state.player.name
    with at(game, after_muster):
        assert game.BATTLE_GAMBLE_LAST not in game.battle_free_text_note()
        game.world.mutate_battle(lambda b: setattr(b.participants[name], "neili", b.participants[name].neili_cap * 0.3))
        note = game.battle_free_text_note()
        assert note.endswith(game.BATTLE_GAMBLE_LAST) and not any(ch.isdigit() for ch in note)


def test_battle_free_text_prompt_is_none_outside_battle(content, game):
    assert game.battle_free_text_prompt() is None
    assert game.battle_free_text_note() is None


def test_battle_free_text_prompt_is_none_after_submitting(content, game):
    definition = _install_battle_def_with_free_text(content)
    after_muster = _join_and_open(content, game, definition)
    with at(game, after_muster):
        game.submit_battle_custom_action("直取波才首級")
        assert game.battle_free_text_prompt() is None


def test_submit_battle_custom_action_truncates_to_20_characters(content, game):
    """這場測試戰鬥只有一幕、保底結果沒有數值門檻，機器人補位後這回合會立刻結算（round
    也會跟著重置），所以改檢查 narrative_log（結算後仍然保留）而不是 round.custom_texts
    （結算後已經清空）。（有設定賭局的戰鬥才會把玩家打的字寫進結算訊息。）"""
    definition = _install_battle_def_with_gamble(content)
    after_muster = _join_and_open(content, game, definition)
    long_text = "一二三四五六七八九十" * 3  # 30 字
    with at(game, after_muster):
        game.submit_battle_custom_action(long_text)
    battle = game.world.get_battle()
    assert any(long_text[:20] in line for line in battle.narrative_log)
    assert not any(long_text in line for line in battle.narrative_log)  # 完整 30 字版本不該出現


def test_submit_battle_custom_action_rejects_empty_input(content, game):
    definition = _install_battle_def_with_free_text(content)
    after_muster = _join_and_open(content, game, definition)
    with at(game, after_muster):
        msgs = game.submit_battle_custom_action("   ")
    assert msgs == ["（請先輸入你想做的事。）"]
    assert "沈浪" not in game.world.get_battle().round.pending_actions


def test_submit_battle_custom_action_works_even_as_the_very_first_call_after_muster_overruns(content, game):
    """自訂行動輸入框不是透過 choose() 進來的，沒有 choose() 開頭那次 self.options()
    順便推進過一次的保護——真的抓到過的 bug：如果這是集結逾時後的第一個請求，
    submit_battle_custom_action() 自己沒有先追趕，battle_instance.submit_action()
    內部看到 battle.phase 還是 "muster" 會悄悄把這次送出的行動吃掉，玩家完全不知道
    自己其實白打了一輪字。"""
    definition = _install_battle_def_with_gamble(content)
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
        game.world.mutate_battle(
            lambda b: battle_instance.join_faction(b, "機器人", "huang", neili_cap=100.0, is_bot=True)
        )
    after_muster = definition.muster_seconds + 1
    with at(game, after_muster):
        # 注意：這裡故意不先呼叫 game.options()/game._battle_status() 暖身，
        # 直接送出自訂行動，模擬「這是逾時後第一個進來的請求」。
        msgs = game.submit_battle_custom_action("直取波才首級")
    assert msgs != ["（此刻無法這麼做。）"]
    battle = game.world.get_battle()
    assert any("直取波才首級" in line for line in battle.narrative_log)


def test_custom_action_without_a_gamble_config_changes_nothing(content, game):
    """這個 fixture 沒有設定 free_text_gamble，所以就算玩家打的字會先被送去評成功率，也沒有賭局可以走：
    這個人這回合不推戰局、不扣血（不會因為文字內容不同而有不同結果）——有設定 free_text_gamble 的戰鬥則相反，
    見 test_submit_battle_custom_action_assesses_success_rate_and_feeds_the_gamble。"""
    definition = _install_battle_def_with_free_text(content)
    after_muster = _join_and_open(content, game, definition)
    with at(game, after_muster):
        game.submit_battle_custom_action("直取波才首級")
    battle = game.world.get_battle()
    cap = game._battle_neili_cap()  # 玩家真實的氣血上限（join 時是這樣算的，不是隨便假設的數字）
    assert battle.participants["沈浪"].neili == cap and not battle.participants["沈浪"].eliminated


def _install_battle_def_with_gamble(content):
    from tianxia.models import FreeTextGamble

    definition = _install_battle_def_with_free_text(content)
    definition.id = "t3"
    content.battles[definition.id] = definition
    definition.free_text_gamble = FreeTextGamble(
        success_trend_base=5, success_trend_per_risk=0.3, success_neili_share=0.05,
        failure_trend_per_risk=0.1, failure_trend_cap=100, failure_neili_share_base=0.1, failure_neili_share_per_risk=0.01,
        side_trend_cap=100,
    )
    return definition


def test_submit_battle_custom_action_assesses_success_rate_and_feeds_the_gamble(content, game):
    """跟上一個測試同一套劇本，差別只在這個 definition 有設定 free_text_gamble——這次
    送出的自訂行動會先呼叫 LLM（這裡用 mock）評成功率，評出來的結果真的拿去擲骰、
    算出不是固定 50 點的傷害，證明整條鏈路（engine.submit_battle_custom_action →
    battle_instance.assess_action_success_rate → resolve_round 的賭局分支）真的接起來了。"""
    definition = _install_battle_def_with_gamble(content)
    after_muster = _join_and_open(content, game, definition)
    with at(game, after_muster), \
         mock.patch.object(game.client, "chat_structured", return_value=battle_instance.SuccessRateJudgment(success_rate=20)):
        game.submit_battle_custom_action("直取波才首級")
    battle = game.world.get_battle()
    cap = game._battle_neili_cap()
    # success_rate=20、risk=80：成功時扣氣血池的 5%（賭贏代價低），失敗時扣（0.1＋80×0.01）＝九成——用的是 game.rng
    # （真的隨機，不是 FixedRandom），究竟成功還是失敗不好預測，但傷害一定精確落在這兩個數字其中之一，證明真的走了賭局公式。
    damage = cap - battle.participants["沈浪"].neili
    assert any(isclose(damage, cap * share) for share in (0.05, 0.9))


def test_an_admin_starts_a_battle_right_away(content, game):
    definition = _install_battle_def(content)
    _admin(content, game)
    msgs = game.admin_start_battle(definition.id, now=time.time())
    assert any("集結號角" in m for m in msgs)
    assert game.world.get_battle().phase == "muster"
    assert game.admin_start_battle(definition.id, now=time.time()) == ["（已經有一場戰鬥在進行。）"]
    assert game.admin_start_battle("no_such_battle", now=time.time()) == ["（沒有這場戰鬥。）"]


def test_the_admin_menus_leave_out_what_season_one_turns_off(content, game):
    """計畫 T8：開關打開、這一季蓋了「開」的章時，第一季不觸發的決戰與門檻不列在管理者的選單上、也觸發不了；
    開關關著照舊。"""
    from tianxia.models import SeasonOneOff

    definition = _install_battle_def(content)
    _admin(content, game)
    content.scenario.season_one_off = SeasonOneOff(thresholds=["kou50"], battles=[definition.id])
    assert [b.id for b in game.admin_battles()] == [definition.id]  # 開關關著：照舊
    assert [x.id for x in game.admin_fires()] == ["kou50", "kou80", "bao100", "grab"]
    content.config.season_one = True
    game.world.mutate_season(lambda season: setattr(season, "season_one", True))
    game.sync(time.time())
    assert game.admin_battles() == [] and [x.id for x in game.admin_fires()] == ["kou80", "bao100", "grab"]
    assert game.admin_start_battle(definition.id, now=time.time()) == ["（沒有這場戰鬥。）"]
    assert game.admin_fire("kou50") == ["（沒有這件大事。）"]
    assert game.world.get_battle() is None and "kou50" not in game.world.get_season().fired_thresholds


def test_the_muster_closes_by_the_time_passed_to_sync(content, game):
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=0.0)
    game.sync(1.0)
    game.choose("battle:join:guan")
    assert game._battle_status()[0].phase == "muster"
    game.sync(definition.muster_seconds + 1)
    assert game._battle_status()[0].phase == "active"


def test_showdown_starts_at_scheduled_time_in_region(content, world):
    """排定的時間（第 6 週週四 20:00）一到就在那個大區開集結：起點照潁川的戰況（40 → 55），季上記下開過了；
    人要在那個大區才能加入。"""
    game = _showdown_game(content, world)
    schedule = game.state.world.schedule["changshe_fire"]
    game.advance(schedule - 1.0 - game.state.world.time)
    assert world.get_battle() is None and "changshe_fire" not in world.get_season().showdowns_opened
    msgs = game.advance(2.0)
    battle = world.get_battle()
    assert (battle.battle_id, battle.phase, battle.trend) == ("changshe_fire", "muster", 55)
    assert battle.muster_deadline_real == game.now + content.battles["changshe_fire"].muster_seconds
    assert "🛡️ 【全服戰報】長社火攻的集結號角已經吹響！" in msgs
    assert world.get_season().showdowns_opened == {"changshe_fire": "changshe_fire"}
    assert game.state.world.showdowns_opened == {"changshe_fire": "changshe_fire"}  # 手上的那一份也跟上了
    assert "battle:join:guan" in ids(game) and "battle:join:huang" not in ids(game)
    content.battles["changshe_fire"].region = "south"  # 人不在決戰的大區：加入不了
    assert "battle:join:guan" not in ids(game)


def test_showdown_result_feeds_timetable(content, world):
    """收場後 timeline["changshe_fire"] 有結果（不再走保底的 BattleOutcome）：戰況照表跳，波才照表退場；公告進每個人的
    江湖紀錄，參戰者的戰報與那一則紀錄寫的是時刻表那一格（官軍大勝）。"""
    from tianxia.models import FigureChange

    game = _showdown_game(content, world)
    content.map.regions[0].front = "yingru"  # 測試夾具的北區沒寫戰線：這裡宣告它算潁川汝南，官軍的目標是把它壓低
    next(f for f in content.scenario.factions if f.id == "guan").goals = {"yingru": -1}
    event = next(e for e in content.timetable if e.id == "changshe_fire")
    event.outcomes["guan:大勝"].figures = {"bocai": FigureChange(fate="退場")}
    event.outcomes["guan:險勝"].figures = {"bocai": FigureChange(fate="聲威大減")}
    _to_showdown(game, "changshe_fire")
    _play_showdown(game, "guan_strong")  # 55 → 65 → 75 → 85：黃巾沒人出招，官軍每回合推滿 10，打滿三回合，官軍大勝
    season = world.get_season()
    assert season.timeline["changshe_fire"].key == "guan:大勝"
    assert season.trends["yingru"] == 40 - 15 and season.figures["bocai"].status == "retired"
    assert "皇甫嵩火攻長社。" in [r.text for r in season.chronicle]
    assert not any("長社火攻戰罷" in r.text for r in season.chronicle)  # 保底結果不寫江湖史
    assert game.state.world.timeline["changshe_fire"].key == "guan:大勝"  # 手上的那一份也跟上了（之後存檔不會蓋掉）
    report = next(e for e in game.state.journal if e.battle_id is not None)
    assert (report.title, report.tag) == ("長社火攻・官軍大勝", "你站在官軍")
    # 第一季規則開著、潁川汝南是一條戰線：大勢增減不再是帶正負號的數字（FB-064）——江湖紀錄存的是機器可讀的標籤（畫出來是
    # 一句話，官軍看是綠的），戰報不收
    assert season.timeline["changshe_fire"].text in report.lines and report.changes == [front_lines.mark("yingru", -15), "名望 +2"]
    assert game.state.battles[0].changes == ["名望 +2"] and "潁川汝南 -15" not in game.state.battles[0].notes
    assert any("潁川汝南：官軍" in html and "tx-up" in html for html in (game.battle_extra_html(),))
    assert game.state.battles[0].tier == "官軍大勝"
    assert any(e.title == "江湖大事" and "火光燭天" in e.tag for e in game.state.journal)
    other = Game.new(content, "丙", rng=random.Random(5), world=world)  # 沒參戰的人也收到公告，但沒有戰報
    other.sync(game.now + 10)
    assert any(e.title == "江湖大事" and "火光燭天" in e.tag + "".join(e.lines) for e in other.state.journal)  # 幾件合成一則
    assert not any(e.battle_id is not None for e in other.state.journal)


def test_admin_can_open_a_showdown_by_hand_once(content, world):
    """管理者「立刻開戰」：第一季列出還沒開過的時刻表決戰（宛城只列這一季版本的那一筆），開出來的跟排定時間開的一樣
    （起點照戰況、記下開過了）；開過就不再列、時間到了也不再開。開關關著不列時刻表決戰。"""
    game = _showdown_game(content, world)
    content.config.admins = ["沈浪"]
    assert [b.id for b in game.admin_battles()] == ["changshe_fire", "wancheng_jia"]
    assert any("長社火攻的集結號角" in m for m in game.admin_start_battle("changshe_fire", now=0.0))
    assert (world.get_battle().battle_id, world.get_battle().trend) == ("changshe_fire", 55)
    assert game.state.world.showdowns_opened == {"changshe_fire": "changshe_fire"}
    assert [b.id for b in game.admin_battles()] == ["wancheng_jia"]
    assert game.admin_start_battle("changshe_fire", now=1.0) == ["（沒有這場戰鬥。）"]
    record = world.get_battle().record_id
    _to_showdown(game, "changshe_fire")
    assert world.get_battle().record_id == record and world.get_season().showdowns_waiting == []
    content.config.season_one = False
    assert game.admin_battles() == []


# ── 季末時決戰還在打（計畫 T9 Review Focus 5）──────────────────────


def test_ending_once_when_battle_running(content, world):
    """第一季排定的季末到了、長社還在打：結局只算一次、季末公告一則、決戰收兵不算結果（戰況不動）、
    參戰者之後同步收到「沒打完、不算勝負」那一則（沒有戰報）、階段是休季。"""
    game = _showdown_game(content, world)
    _to_showdown(game, "changshe_fire", after=2.0)
    with at(game, game.now):
        game.choose("battle:join:guan")
    start = game.world.get_battle().muster_deadline_real + 1
    with at(game, start):
        game.choose("battle:act:guan_hold")  # 打到一半：還在交戰
    assert game.world.get_battle().phase == "active"
    trends = dict(game.world.get_season().trends)

    game.advance(game.state.world.schedule["finale"] + 1 - game.state.world.time)
    season = game.world.get_season()
    assert season.ended and season.ending_id and season.timeline["xiaquyang"].key == season.ending_id
    assert sum(1 for r in season.chronicle if r.text == f"賽季落幕：{season.ending_title}") <= 1
    assert game.world.season_phase() == "resting"

    with at(game, start + 1):
        assert ids(game) == ["season:resting"]  # 畫面刷新那一下把沒打完的收起來
    assert game.world.get_battle() is None
    after = game.world.get_season()
    # 決戰的結果沒有套：潁川（長社的戰線）沒動，時間軸沒有長社（之後別的大事照常動了南陽、冀州）
    assert after.trends["yingru"] == trends["yingru"] and "changshe_fire" not in after.timeline
    (_, shelved), = [b for b in game.world.ended_battles() if b[1].battle_id == "changshe_fire"]
    assert shelved.unfinished
    game.sync(start + 10)
    assert SHELVED_LINE in game.state.journal[0].lines and game.state.journal[0].battle_id is None
    assert game.state.battles == []
    game.advance(60)  # 收季之後再推也不會再收一次
    assert game.world.get_season().ending_id == season.ending_id


def test_world_tick_shelves_a_battle_after_the_season_ended(content, game):
    """季已經結束、決戰還在打、沒人在線：排程那一下照 FB-035 收兵（Review Focus 3）。"""
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        game.choose("battle:join:guan")
    open_characters().save(game.state)
    game.world.mutate_season(lambda s: (setattr(s, "ended", True), setattr(s, "ending_title", "天下太平")))
    Game.for_world(content, game.world, rng=random.Random(3)).world_tick(1100.0)
    assert game.world.get_battle() is None
    (_, shelved), = game.world.ended_battles()
    assert shelved.unfinished


def test_a_fighter_joins_with_the_role_of_their_standout_stat_and_it_shows(content, game):
    """進場依屬性給職位（試玩回饋 2026-10-08）：根骨最高是盾陣，固守的份量多一成半；決戰畫面與戰報都寫。"""
    definition = _three_round_showdown(content)
    game.state.player.faction = "guan"
    game.state.player.stats["con"] = 8
    foe = _fighter(content, game, "乙", "huang")
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0), at(foe, 0.0):
        game.choose("battle:join:guan")
        foe.choose("battle:join:huang")
        assert "你的職位：盾陣（固守的份量多 15%）" in game.scene_text()
    battle = game.world.get_battle()
    me, them = battle.participants[game.state.player.name], battle.participants["乙"]
    assert (me.role, them.role) == ("con", "")  # 乙五項一樣高：沒有職位
    start = definition.muster_seconds + 1
    with at(game, start):
        assert "你的職位：盾陣" in game.scene_text()
    for i in range(3):
        with at(game, start + i), at(foe, start + i):
            game.choose("battle:act:guan_hold")
            foe.choose("battle:act:huang_hold")
    game.sync(start + 10)  # 收場那一下是乙出的手：自己的那一則同步時補
    assert "你以盾陣出陣，出手 3 回合" in game.state.journal[0].lines


def test_the_most_dramatic_gamble_of_a_battle_goes_round_the_world_and_earns_fame(content, game):
    """每場收場挑最有戲的那一搏寫進天下大事傳聞；那一搏是成了的，那個人名望 +1（試玩回饋 2026-10-08）。"""
    definition = _three_round_showdown(content)
    game.state.player.faction = "guan"
    foe = _fighter(content, game, "乙", "huang")
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0), at(foe, 0.0):
        game.choose("battle:join:guan")
        foe.choose("battle:join:huang")
    me = game.state.player.name
    game.world.mutate_battle(lambda b: setattr(b, "highlight", battle_instance.GambleMoment(
        name=me, faction="guan", text="扮成絕世美女色誘對面主將", story=f"{me}一扭腰，對面主將看傻了眼。", rate=0, won=True,
    )))
    fame = game.state.player.stats.get("fame", 0)
    start = definition.muster_seconds + 1
    for i in range(3):
        with at(game, start + i), at(foe, start + i):
            foe.choose("battle:act:huang_hold")
            game.choose("battle:act:guan_hold")
    assert game.world.get_battle().phase == "ended"
    line = f"測試決戰上，{me}放手一搏：「扮成絕世美女色誘對面主將」——成算不到1成，竟然成了。{me}一扭腰，對面主將看傻了眼。"
    with at(game, start + 5):
        idle_step(game)  # 再存一次賽季：傳聞不會被記憶體那份蓋掉
    assert [r.text for r in game.world.get_season().rumors].count(line) == 1
    top = content.config.battle.top_fame  # 官軍只有他一個，也是首功（個人戰功）：名望合起來寫一筆
    assert game.state.player.stats["fame"] == fame + 1 + top
    entry = next(e for e in game.state.journal if e.title.startswith("測試決戰・"))
    assert f"名望 +{1 + top}" in entry.changes and "你那一搏成了這一仗最令人印象深刻的一幕，江湖上傳開了。" in entry.lines


def _paid_showdown(content, game, foe_rounds=3):
    """照正式的軍餉設定（測試內容把軍餉關掉）打一場三回合的決戰，官軍贏（戰局 65 以上是官軍大勝）。"""
    from tianxia.models import MOVES, BattleOutcome, ShowdownPay

    content.config.showdown_pay = ShowdownPay()
    definition = _three_round_showdown(content)
    definition.outcomes = [
        BattleOutcome(faction="guan", trend_min=65, title="官軍大勝", text="官軍獲勝。"),
        BattleOutcome(faction="huang", trend_max=35, title="黃巾得勢", text="黃巾獲勝。"),
        BattleOutcome(faction="guan", title="兩軍膠著", text="不分勝負。"),
    ]
    game.state.player.faction = "guan"
    foe = _fighter(content, game, "乙", "huang")
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0), at(foe, 0.0):
        game.choose("battle:join:guan")
        foe.choose("battle:join:huang")
    game.world.mutate_battle(lambda b: setattr(b.participants["乙"], "scores", {m: 1.0 for m in MOVES}))  # 乙打不動：官軍大勝
    if not foe_rounds:  # 乙離開了大區，一回合都沒出手
        game.world.mutate_battle(lambda b: battle_instance.set_away(b, "乙", True))
    start = definition.muster_seconds + 1
    for i in range(3):
        with at(game, start + i), at(foe, start + i):
            if i < foe_rounds:
                foe.choose("battle:act:huang_hold")
            game.choose("battle:act:guan_strong")
    with at(foe, start + 10):
        foe.sync(start + 10)
    return definition, foe


def test_every_fighter_draws_pay_and_the_winners_draw_more(content, game):
    """決戰的軍餉（試玩回饋 2026-10-08）：參戰照個人戰功發銀兩與經驗（只出手 6 回合的戰功算一倍，Joy 2026-10-10），贏的一方大勝再加一倍。"""
    silver = game.state.player.stats.get("silver", 0)
    _, foe = _paid_showdown(content, game)
    battle = game.world.ended_battles(after=0)[-1][1]
    assert (battle.outcome_side, battle.outcome_margin) == ("guan", "大勝")
    entry = next(e for e in game.state.journal if e.title == "測試決戰・官軍大勝")
    # 出手 3 回合、帶頭佔上風 3 回合：戰功 3×2＋3×3 ＝ 15，份量 15／12 ＝ 1.25：40 × 1.25 × 2 ＝ 100 兩、60 × 1.25 × 2 ＝ 150 經驗
    assert ["銀兩 +100", "經驗 +150"] == [c for c in entry.changes if c.startswith(("銀兩", "經驗"))]
    assert "得勝的軍餉發下來了。" in entry.lines
    assert game.state.player.stats["silver"] == silver + 100
    lost = next(e for e in foe.state.journal if e.title == "測試決戰・官軍大勝")
    assert ["銀兩 +20", "經驗 +30"] == [c for c in lost.changes if c.startswith(("銀兩", "經驗"))]  # 輸的一方照拿基本軍餉
    assert "軍餉發下來了。" in lost.lines
    foe.sync(foe.now + 60)  # 補過的不會再補
    assert sum(e.title == "測試決戰・官軍大勝" for e in foe.state.journal) == 1


def test_someone_who_never_acted_draws_only_a_token(content, game):
    _, foe = _paid_showdown(content, game, foe_rounds=0)  # 乙一回合都沒出手（全程被代選）
    lost = next(e for e in foe.state.journal if e.title == "測試決戰・官軍大勝")
    assert ["銀兩 +4", "經驗 +6"] == [c for c in lost.changes if c.startswith(("銀兩", "經驗"))]  # 一成


def test_a_faction_member_also_banks_contribution_but_a_drifter_who_enlisted_does_not(content, game):
    """投靠了陣營、替自己陣營出戰的人另記本季貢獻（推大勢的帳：contrib_per_push × 點數 × 份量）；臨時投效的散人不記。"""
    from tianxia.models import ShowdownPay

    content.config.showdown_pay = ShowdownPay()
    content.config.season_one = True
    game.state.world.season_one = True
    battle = battle_instance.BattleInstance(battle_id="t", phase="ended", outcome_side="guan", outcome_margin="險勝")
    me = battle_instance.BattleParticipant(name=game.state.player.name, faction="guan", neili=1, neili_cap=1, acted_rounds=6)
    game.state.player.faction = "guan"
    lines: list[str] = []
    changes = game._showdown_pay(battle, me, lines)
    per = content.config.contrib_per_push
    # 滿出手、險勝：40 × 1.5 ＝ 60 兩、90 經驗；貢獻（2 ＋ 3）點 × contrib_per_push
    assert changes[:2] == ["銀兩 +60", "經驗 +90"] and changes[2] == f"貢獻 +{5 * per}"
    game.state.player.faction = None  # 散人臨時投效官軍
    assert not any(c.startswith("貢獻") for c in game._showdown_pay(battle, me, []))


def test_a_gamble_naming_an_enemy_tells_the_model_who_it_is(content, game):
    """點名的對手由引擎認（Joy 2026-10-10），單子上多一行給模型。"""
    definition = _install_battle_def_with_gamble(content)
    after_muster = _join_and_open(content, game, definition)
    with at(game, after_muster):
        assert game.battle_text_request("生擒機器人").target.startswith("機器人（黃巾，身手")
        assert game.battle_text_request("火燒連營").target == ""


def test_the_battle_scene_says_who_is_after_you_and_what_you_can_do(content, game):
    definition = _install_battle_def_with_gamble(content)
    definition.free_text_gamble.per_act = 1  # 「下一幕才能再搏」只在真的有上限時才寫（預設 0 ＝ 不限）
    after_muster = _join_and_open(content, game, definition)

    def spot(b):
        b.last_targets = {"沈浪": ["機器人"]}
        b.marked = {"沈浪": b.act_index}
        b.participants["沈浪"].gambled_act, b.participants["沈浪"].gambles_this_act = b.act_index, 1

    game.world.mutate_battle(spot)
    with at(game, after_muster):
        scene = game.scene_text()
        assert "機器人盯上了你。" in scene and "這一幕你已經放手一搏過了" in scene and "你在這一幕太顯眼了" in scene
        assert game.battle_free_text_prompt() is None
        assert game.submit_battle_custom_action("再搏一次") == ["（此刻無法這麼做。）"]
    game.world.mutate_battle(lambda b: setattr(b.participants["沈浪"], "pinned_round", b.round_number + 1))
    with at(game, after_muster):
        assert "你被牽制住了，這一回合只能固守。" in game.scene_text()
        assert [o.id for o in game.options()] == ["battle:act:guan_hold"]


def test_the_showdown_report_says_who_you_hurt_and_who_hunted_you(content, game):
    definition = _three_round_showdown(content)
    game.state.player.faction = "guan"
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")

    def scars(b):
        me = b.participants["沈浪"]
        me.hurt_dealt, me.targeted_by, me.hurt_taken = 120.4, ["甲", "乙"], 80.0

    game.world.mutate_battle(scars)
    _fight_to_the_end(game, definition, definition.muster_seconds + 1)
    lines = _showdown_entries(game)[0].lines
    assert "你的放手一搏點名打傷了對手，打掉他們氣血 120" in lines
    assert "甲、乙在陣上點名要對付你，你被打掉氣血 80" in lines


def test_an_enlisted_warlord_ranks_and_takes_first_merit_with_the_army_it_joined(game):
    """臨時投效的豪強算在投效的那一軍：論功那一則寫那一軍的首功，戰局條的戰功也排在那一軍。"""
    battle, definition = _warlord_in_battle(game, "guan")
    me = game.state.player.name
    game.world.mutate_battle(lambda b: setattr(b.participants[me], "acted_rounds", 2))
    battle = game.world.get_battle()
    assert game._merit_line(battle, definition) == f"{definition.name}論功：官軍首功{me}。"
    g = game.battle_gauge()
    assert g["merit"]["left"][0]["name"] == me and "third" not in g["merit"]
    assert g["merit"]["me"]["rank"] == 1 and "due" in g
