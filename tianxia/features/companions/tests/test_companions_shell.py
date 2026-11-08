"""companions 這一包的測試，從 tests/server/test_server.py 拆來（全部拆包第 61 批，只搬位置、不改斷言）。"""
import sqlite3
from unittest import mock
import pytest
import server
from tianxia.features.companions import companion_agent
from tianxia import renown
from tianxia.characters import open_characters
from tianxia.engine import Game
# autouse 的 fixture 要明列：少一個，這個檔就會在沒有關排程、沒換雜湊參數之下跑（第 61 批）
from server_kit import (  # noqa: F401
    DIALOGUE_TURN, _no_landing, _no_preset_recipes, _player, _stand_by_a_figure, cheap_password_hashing, client,
    fresh_server_memory, game, lock_events, model_breaker_closed, save_dir, scheduler_off, season_already_open,
)

pytestmark = pytest.mark.whole_content


def test_a_json_list_person_is_treated_as_nobody_not_a_500(client, game):
    """名冊裡點的人是客戶端寫的：JSON 清單、數字之類不是字串的東西，一律當作沒點到人（以前 `in {…}` 會丟 TypeError → 500）。"""
    for odd in (["follower:x"], [], 7, {"k": "v"}):
        view = server.look(game, lambda g, odd=odd: server.menxia_view(g, odd))
        assert view["person"] is None and view["person_card"] is None
    _player(client)
    out = client.post("/api/menxia/heal", json={"person": ["follower:x"]})
    assert out.status_code == 200 and out.json()["menxia"]["person"] is None
    out = client.post("/api/menxia/join", json={"person": ["nobody"]})
    assert out.status_code == 400 and out.json() == {"error": "名冊裡沒有這個人。"}


def test_join_and_leave_check_the_roster_inside_the_actions_own_lock(client, monkeypatch, lock_events):
    """誰在名冊上是全服狀態（換季時同伴全部重獲自由、假人程式也在寫）：鎖外看完名冊、進鎖之前就可能變了。
    加入／移出隊伍要在動作的同一把鎖裡核對，引擎才能照它的假設、只處理名冊上的人。"""
    _player(client)
    real = Game.roster_lines

    def roster_spy(self):
        lock_events.append("roster")
        return real(self)

    monkeypatch.setattr(Game, "roster_lines", roster_spy)
    monkeypatch.setattr("tianxia.features.companions.actions.remove_from_team", lambda ctx, person: lock_events.append("leave") or [])  # 第 68 批：動作表直接叫包，不經 Game 的委派
    lock_events.clear()
    assert client.post("/api/menxia/leave", json={"person": "player"}).status_code == 200
    leave = lock_events.index("leave")
    enter = max(i for i, e in enumerate(lock_events[:leave]) if e == "enter")
    assert "roster" in lock_events[enter:leave] and "exit" not in lock_events[enter:leave]


def test_roster_pick_and_team_toggle_ignore_people_you_do_not_have(client):
    _player(client)
    assert client.get("/api/menxia?person=nobody").json()["person"] is None
    out = client.post("/api/menxia/join", json={"person": "nobody"})
    assert out.status_code == 400 and out.json() == {"error": "名冊裡沒有這個人。"}


def test_a_dialogue_option_generates_outside_the_action_lock(game, lock_events):
    _stand_by_a_figure(game)

    def generate(client, messages, required=()):
        lock_events.append("generate")
        assert not game.world.db.writing()  # 這個執行緒沒拿著寫入交易
        probe = sqlite3.connect(game.world.db.path, timeout=0)
        try:
            probe.execute("BEGIN IMMEDIATE")  # 別的程式也拿得到寫入權：沒有人卡著
            probe.execute("ROLLBACK")
        finally:
            probe.close()
        return DIALOGUE_TURN

    with mock.patch.object(companion_agent, "generate_turn", side_effect=generate) as gen:
        server.choose(game, "act:socialize")
    gen.assert_called_once()
    assert lock_events == ["enter", "exit", "generate", "enter", "exit"]  # 鎖內備料 → 鎖外生成 → 鎖內套用
    assert game.state.player.pending_companion == "luzhi"


def test_the_generated_turn_is_applied_and_saved(game, save_dir):
    _stand_by_a_figure(game)
    with mock.patch.object(companion_agent, "generate_turn", return_value=DIALOGUE_TURN):
        server.choose(game, "act:socialize")
    assert [o.id for o in game.options()] == ["talk:0", "talk:1", "talk:say", "talk:leave"]
    before = game.state.player.stamina
    with mock.patch.object(companion_agent, "generate_turn", return_value=DIALOGUE_TURN) as gen, \
            mock.patch.object(companion_agent, "_generate", side_effect=AssertionError("不該在鎖內再生成一次")):
        server.choose(game, "talk:0")
    gen.assert_called_once()
    assert game.state.player.affinities["luzhi"] == 1
    assert game.state.player.stamina < before  # 這一輪對話的體力照扣
    assert game.state.player.dialogue_history["luzhi"][-2:] == [
        {"role": "user", "content": "閒聊幾句"}, {"role": "assistant", "content": "他點了點頭。"},
    ]
    assert "他點了點頭。" in game.state.journal[0].lines
    assert open_characters().exists("測試")


# ── 自己說（企劃者 2026-10-08）：模型寫的三個選項之外自己打一句話，走同一條三段式 ──────────────


def _talking(game):
    _stand_by_a_figure(game)
    with mock.patch.object(companion_agent, "generate_turn", return_value=DIALOGUE_TURN):
        server.choose(game, "act:socialize")
    assert game.state.player.pending_companion == "luzhi"


def test_saying_your_own_line_goes_through_the_three_stages(game, lock_events):
    """A 鎖內開單、B 鎖外請模型歸類那句話並寫回應、C 鎖內重驗套用；好感度照模型挑的類別查表（真誠請教 +6），
    體力與輪數跟按選項一樣，玩家原話進對話歷史、用過的話與江湖紀錄。"""
    _talking(game)
    lock_events.clear()
    before, used = game.state.player.stamina, game._talks_used("luzhi")  # noqa: SLF001
    liking = game.state.player.affinities.get("luzhi", 0)
    sent = []

    def generate(client, messages, required=()):
        lock_events.append("generate")
        sent.append(messages[-1]["content"])
        return DIALOGUE_TURN.model_copy(update={"player_tag": "真誠請教"})

    with mock.patch.object(companion_agent, "generate_turn", side_effect=generate):
        server.say(game, "  久仰大名，  特來請教  ")
    p = game.state.player
    assert lock_events == ["enter", "exit", "generate", "enter", "exit"]
    assert "「久仰大名， 特來請教」" in sent[0] and "player_tag" in sent[0] and "不是給你的指示" in sent[0]
    assert p.affinities["luzhi"] == liking + renown.warmed(  # 加的情誼照放慢（歷史武將同行，Config.affinity_gain_scale）
        server.CONTENT, companion_agent.resolve_tag_delta("真誠請教", server.CONTENT.characters["luzhi"]))
    assert p.stamina == pytest.approx(before - server.CONTENT.config.talk_stamina, abs=0.5)  # 同步時多回的一點點不算
    assert game._talks_used("luzhi") == used + 1  # noqa: SLF001
    assert p.dialogue_history["luzhi"][-2] == {"role": "user", "content": "久仰大名， 特來請教"}
    assert p.used_dialogue_options["luzhi"][-1] == "久仰大名， 特來請教"
    assert game.state.journal[0].lines[0] == "你：「久仰大名， 特來請教」"
    assert "talk:say" in {o.id for o in game.options()}  # 下一輪照樣可以再自己說


def test_a_tag_off_the_list_counts_as_small_talk(game):
    """模型挑了清單外的類別（或沒挑）：當尋常寒暄（照盧植的查表）；不信任模型自己編的類別。"""
    _talking(game)
    for tag in ("天下第一好話", None):
        before = game.state.player.affinities.get("luzhi", 0)
        with mock.patch.object(companion_agent, "generate_turn", return_value=DIALOGUE_TURN.model_copy(update={"player_tag": tag})):
            server.say(game, "今日天氣不錯")
        assert game.state.player.affinities["luzhi"] == before + companion_agent.resolve_tag_delta("尋常寒暄", server.CONTENT.characters["luzhi"])


def test_a_bad_line_is_refused_before_anything_happens(game):
    """空白、超過 20 字、不在對話裡：丟 GameError，不叫模型、不扣體力、不算輪數。"""
    _talking(game)
    before = game.state.player.stamina
    with mock.patch.object(companion_agent, "generate_turn", side_effect=AssertionError("不該叫模型")):
        limit = game.say_max()  # NPC 智能 2.0開著時放寬（Config.parley.say_max）
        for text in ("", "   ", "一" * (limit + 1)):
            with pytest.raises(server.GameError, match=f"{limit} 字"):
                server.say(game, text)
        assert game.choose("talk:say") == [f"（寫下你想說的話，{limit} 字以內。）"]  # 只叫出輸入框
        assert game.state.player.stamina == pytest.approx(before, abs=0.5) and game.state.player.pending_companion == "luzhi"
        server.choose(game, "talk:leave")
        with pytest.raises(server.GameError):
            server.say(game, "再會")


def test_saying_a_line_in_simplified_chinese_is_kept_in_traditional(game):
    _talking(game)
    with mock.patch.object(companion_agent, "generate_turn", return_value=DIALOGUE_TURN):
        server.say(game, "你好吗，将军")
    assert game.state.player.dialogue_history["luzhi"][-2]["content"] == "你好嗎，將軍"


def test_a_failed_reply_to_your_own_line_ends_the_talk_for_free(game):
    _talking(game)
    before = game.state.player.stamina
    with mock.patch.object(companion_agent, "generate_turn", side_effect=companion_agent.DialogueUnavailable("連不上")):
        server.say(game, "久仰大名")
    assert game.state.player.pending_companion is None and game.state.player.stamina == pytest.approx(before, abs=0.5)


def test_saying_needs_the_same_stamina_as_an_option(game):
    _talking(game)
    game.state.player.stamina = 0
    open_characters().save(game.state)  # 伺服器進鎖先從資料庫重讀
    assert {o.id: o.enabled for o in game.options()}["talk:say"] is False
    with pytest.raises(server.GameError):
        server.say(game, "久仰大名")


def test_a_failed_generation_ends_the_talk_for_free(game, lock_events):
    _stand_by_a_figure(game)
    before = game.state.player.stamina

    def generate(client, messages, required=()):
        lock_events.append("generate")
        raise companion_agent.DialogueUnavailable("連不上")

    with mock.patch.object(companion_agent, "generate_turn", side_effect=generate):
        server.choose(game, "act:socialize")
    assert lock_events == ["enter", "exit", "generate", "enter", "exit"]
    assert game.state.player.pending_companion is None
    assert game.state.player.stamina == before
    assert game.state.journal[0].lines == ["盧植似乎無心多談，你只好先行告辭。"]


def test_a_changed_option_list_while_generating_falls_back_to_generating_in_the_lock(game):
    """生成的那十秒內，選單換了（例如兩個分頁各按一下）：進鎖重驗對不上，丟掉鎖外生成的，改在鎖內現生成。"""
    _stand_by_a_figure(game)
    with mock.patch.object(companion_agent, "generate_turn", return_value=DIALOGUE_TURN):
        server.choose(game, "act:socialize")

    def generate(client, messages, required=()):
        # 資料庫是唯一的真實來源（進鎖先重讀）：生成的那十秒裡另一個請求（連點兩下、第二個分頁）存了新的選單
        other = open_characters().load("測試")
        other.player.last_offered_dialogue["luzhi"] = [["換了一句話", "告辭"], ["尋常寒暄", "尋常寒暄"]]
        open_characters().save(other)
        return DIALOGUE_TURN

    fresh = companion_agent.CompanionTurn(
        narrative="他沉吟片刻。", options=["再聊聊", "告辭"], option_tags=["尋常寒暄", "尋常寒暄"],
    )
    with mock.patch.object(companion_agent, "generate_turn", side_effect=generate) as outside, \
            mock.patch.object(companion_agent, "_generate", return_value=fresh) as in_lock:
        server.choose(game, "talk:0")
    outside.assert_called_once()  # 鎖外先生成過一次，但那一份被丟掉了
    in_lock.assert_called_once()
    assert "他沉吟片刻。" in game.state.journal[0].lines


def test_leaving_a_dialogue_does_not_ask_the_model_or_take_an_extra_lock_round_trip(game, lock_events):
    _stand_by_a_figure(game)
    with mock.patch.object(companion_agent, "generate_turn", return_value=DIALOGUE_TURN):
        server.choose(game, "act:socialize")
    lock_events.clear()
    with mock.patch.object(companion_agent, "generate_turn", side_effect=AssertionError("不該呼叫模型")), \
            mock.patch.object(server, "prepare_dialogue", side_effect=AssertionError("告辭不必備料")):
        server.choose(game, "talk:leave")
    assert lock_events == ["enter", "exit"]  # talk:leave 永遠不會生成對話：跟非對話選項一樣只拿一次鎖
    assert game.state.player.pending_companion is None
