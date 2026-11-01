"""建角色選性別（PM 2026-10-12，企劃者「創建角色時可以選擇性別」）：存在 PlayerState，不影響數值；
別人看得到的稱呼、內容寫給玩家的稱呼、模型提示照性別換；假人照比例給。"""
from __future__ import annotations

import random
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import server
from conftest import real_content
from tianxia import battle_instance, biography, gender, mounts, ranger, rules, social
from tianxia.bot_runner import FEMALE_SAMPLE, BotRunner
from tianxia.engine import GENDER_LOCKED, Game


@pytest.fixture
def real():
    c = real_content()
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    return c


def _game(content, name="甲", sex=None, at="yingchuan"):
    game = Game.new(content, name, rng=random.Random(0), sex=sex)
    game.state.player.location = at
    return game


@pytest.mark.smoke
def test_the_helpers_switch_only_for_women():
    assert (gender.pronoun("女"), gender.hero("女"), gender.anon("女")) == ("她", "女俠", "某位女俠")
    assert (gender.pronoun("男"), gender.hero("男"), gender.anon("男")) == ("他", "少俠", "某位少俠")
    assert gender.of("隨便寫") == "男"  # 不認得的一律是男（舊存檔）
    said = "劉備大喜：「得少俠相助！」賢弟，那女俠的刀快。"
    assert gender.address(said, "女") == "劉備大喜：「得女俠相助！」賢妹，那女俠的刀快。"
    assert gender.address(said, "男") == said
    assert gender.prompt_line("男") == "" and "女俠" in gender.prompt_line("女")


def test_new_characters_choose_once_and_old_ones_choose_in_settings(real):
    chosen = _game(real, "甲", sex="女")
    assert (chosen.state.player.gender, chosen.state.player.gender_chosen) == ("女", True)
    assert chosen.set_gender("男") == [GENDER_LOCKED] and chosen.state.player.gender == "女"
    old = _game(real, "乙")  # 舊角色：沒選過、預設男
    assert (old.state.player.gender, old.state.player.gender_chosen) == ("男", False)
    assert old.status_data()["gender"] == "男" and old.status_data()["gender_chosen"] is False
    assert old.set_gender("貓") == ["沒有這個選項。"] and not old.state.player.gender_chosen
    old.set_gender("女")
    assert (old.state.player.gender, old.state.player.gender_chosen) == ("女", True)
    assert old.set_gender("男") == [GENDER_LOCKED]


def test_gender_carries_into_the_next_season(real):
    real.config.admins = ["管"]
    admin = _game(real, "管")
    game = _game(real, "甲", sex="女")
    game.sync(100.0)
    admin.admin_end_season(now=200.0)
    admin.admin_next_season(now=300.0)
    game.sync(400.0)
    assert game.state.player.season_number == 2
    assert (game.state.player.gender, game.state.player.gender_chosen) == ("女", True)


def test_what_others_read_follows_her_gender(real):
    her = _game(real, "甲", sex="女")
    him = _game(real, "乙")
    her.state.player.anonymous = him.state.player.anonymous = True
    assert (rules.display_name(her.state), rules.display_name(him.state)) == ("某位女俠", "某位少俠")
    him.state.player.taunt_muted = [social.name_key(her.state.player.name)]  # 結伴同行拿掉了（名帖改版），改看封了挑釁話之後那一顆
    her.state.player.taunt_muted = [social.name_key(him.state.player.name)]
    assert social._greet_buttons(him, her)[-1].label == "再接她的挑釁話"
    assert social._greet_buttons(her, him)[-1].label == "再接他的挑釁話"
    assert mounts.RAID_FLED_TAG.format(him=gender.pronoun(her.state)) == "她策馬跑了"


def test_content_lines_said_to_her_call_her_a_heroine(real):
    her = _game(real, "甲", sex="女")
    assert rules.fill_marks("布商拉住你：「少俠！」", her.state) == "布商拉住你：「女俠！」"
    him = _game(real, "乙")
    assert rules.fill_marks("布商拉住你：「少俠！」", him.state) == "布商拉住你：「少俠！」"


def test_the_ranger_title_that_names_a_man_has_a_womans_form(real):
    real.config.renown.titles = False  # 舊的遊俠名號；名聲開著時的女版稱號見 test_renown.test_women_get_the_female_title
    her = _game(real, "甲", sex="女")
    her.state.player.ranger_evil = real.config.ranger.thresholds[0]
    assert ranger.title(real, her.state) == "綠林女傑"


class _Capture:
    def __init__(self):
        self.messages = None

    def chat_structured(self, messages, *a, **kw):
        self.messages = messages
        raise RuntimeError("不必真的回")


def test_the_model_hears_she_is_a_woman():
    act = SimpleNamespace(title="長社", text="火起。")  # assess_gamble 只讀 title、text
    cap = _Capture()
    battle_instance.assess_gamble(cap, act, "官軍", "放火", "", sex="女")
    system = cap.messages[0]["content"]
    assert "以「這位女俠」開頭" in system and "女子" in system
    cap = _Capture()
    battle_instance.assess_gamble(cap, act, "官軍", "放火", "", sex="男")
    assert "以「這位少俠」開頭" in cap.messages[0]["content"] and "女子" not in cap.messages[0]["content"]
    req = biography.BiographyRequest(season=1, name="沈青", scenario="黃巾之亂", era_note="", sex="女")
    assert "全篇稱她為「沈青」" in biography.messages(req)[0]["content"]


def test_bots_follow_the_players_share_and_keep_their_rng(real, monkeypatch):
    assert gender.for_bot("王子") == gender.for_bot("王子")  # 照名號，每次一樣
    names = [f"甲{i}" for i in range(400)]
    share = sum(gender.for_bot(n, 0.3) == "女" for n in names) / len(names)
    assert 0.2 < share < 0.4
    assert all(gender.for_bot(n, 0.0) == "男" for n in names[:50])
    runner = BotRunner.__new__(BotRunner)

    class _Store:
        def __init__(self, states):
            self.states = states

        def all(self, bots_only=False):
            return self.states

    few = [_game(real, f"真{i}", sex="女").state for i in range(FEMALE_SAMPLE - 1)]
    runner.characters = _Store(few)
    assert runner._female_share() == gender.BOT_FEMALE_SHARE  # 選過的真人太少：照預設
    many = few + [_game(real, f"男{i}", sex="男").state for i in range(4)] + [_game(real, "沒選").state]
    runner.characters = _Store(many)
    assert runner._female_share() == pytest.approx(4 / 8)  # 沒選過的不算


def test_the_create_screen_sends_the_gender(real, monkeypatch):
    monkeypatch.setattr(server, "CONTENT", real)
    client = TestClient(server.app)
    client.post("/api/register", json={"login": "sex_01", "password": "secret-pw", "again": "secret-pw"})
    client.post("/api/character", json={"name": "沈青衫", "gender": "女"})
    p = server.game_for("沈青衫").state.player
    assert (p.gender, p.gender_chosen) == ("女", True)
    client2 = TestClient(server.app)
    client2.post("/api/register", json={"login": "sex_02", "password": "secret-pw", "again": "secret-pw"})
    client2.post("/api/character", json={"name": "沈黑衫", "gender": "<貓>"})
    p = server.game_for("沈黑衫").state.player
    assert (p.gender, p.gender_chosen) == ("男", False)  # 不認得的當沒選：設定頁還能選一次
