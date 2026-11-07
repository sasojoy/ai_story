"""sortie 這一包的測試，從 tests/core/test_engine.py 拆來（全部拆包第 61 批，只搬位置、不改斷言）。"""
import random
from unittest import mock
import pytest
from conftest import walk_to
from tianxia import encounter, fight_llm, team
from engine_kit import ACCOUNTS, JUDGMENT, _boss_at_the_lake, _judged, _training_factions  # noqa: F401

pytestmark = pytest.mark.whole_content


def test_a_big_fight_the_player_left_while_it_was_judged_says_so_and_fights_nothing(game):
    """等模型判讀的時候（另一個分頁）把人帶走了，回來時這個選項已經不在選單上：不打、不寫戰報、不寫江湖紀錄，
    回一句話告訴玩家這一仗沒打成（不是把空的回給畫面）。模型叫不動（判讀是 None）時一樣。"""
    _boss_at_the_lake(game)
    request = game.fight_request("act:train")
    game.state.player.location = "town"
    journal = len(game.state.journal)
    for judgment in (JUDGMENT, None):
        assert game.choose("act:train", fight=fight_llm.PreparedFight(request=request, judgment=judgment)) == ["你離開了，這一仗沒打成。"]
    assert game.state.battles == [] and len(game.state.journal) == journal
    assert game.choose("act:train") == ["（此刻無法這麼做。）"]  # 沒有判讀過的過期按鈕：照舊是那一句


def test_a_judgment_is_dropped_after_another_fight(game):
    """Review Focus 3：等模型的時候（另一個分頁）又打了一場，戰報流水號變了：回來的判讀作廢、照平常打。"""
    _boss_at_the_lake(game)
    request = game.fight_request("act:train")
    game.choose("act:train")
    game.choose("act:train", fight=_judged(request))
    newest = game.state.battles[0]
    assert newest.id == request.battle_seq + 2 and newest.narration == ""
    assert game.state.battles[1].narration == ""


class _FirstChoice(random.Random):
    """rng.choice 一律挑第一個：看得出遊歷的對手是不是照 Game.rng 挑的。"""

    def choice(self, seq):
        return seq[0]


class _LastChoice(random.Random):
    """rng.choice 一律挑最後一個。"""

    def choice(self, seq):
        return seq[-1]


def _train_wait(game) -> str:
    return next(o for o in game.options() if o.id == "act:train").wait


def _next_seq(game, squad_id: str) -> int:
    """從現在的戰報流水號往後找，第一個讓 _train_pick 挑到 squad_id 的流水號，並把流水號設成它（只往後跳，戰報的編號不會重複）。"""
    return next(n for n in range(game.state.battle_seq, game.state.battle_seq + 100) if _pick(game, n) == squad_id)


def test_a_trip_where_a_big_foe_lurks_meets_the_foe_the_button_names(game):
    """遊歷的池子裡有大場面的對手時，這一趟遇上哪一路一律照 _train_pick（名號｜地點｜戰報流水號的雜湊），不擲 Game.rng：
    按鈕、備料、套用與判讀失敗的退路都是同一路（Task 2 審查修正 3）。判讀過的照優勢平移判定差距；判讀不到（模型叫不動）
    照樣打按鈕寫的那一路，優勢 0、照範本回合演出。挑到一般的那一路就是一般的仗：不寫「兩人對峙」、不問模型。"""
    from tianxia import encounter, team

    game.content.locations["lake"].enemies = ["thug", "boss"]
    walk_to(game, "lake")
    game.state.player.member.wugong_id = "basic_fist"

    game.rng = _FirstChoice(0)  # Game.rng 要是被拿去挑對手，會挑到水寇小隊
    _next_seq(game, "boss")
    assert _train_wait(game) == "兩人對峙……"
    request = game.fight_request("act:train")
    assert request.squad_id == "boss"
    with mock.patch.object(team, "fight", wraps=team.fight) as fight:
        game.choose("act:train", fight=_judged(request))
    assert game.state.battles[0].opponent == "翻江龍" and game.state.battles[0].narration in ACCOUNTS
    assert fight.call_args.kwargs["shift"] == pytest.approx(encounter.advantage_shift(200, 15))

    _next_seq(game, "boss")  # 判讀失敗（伺服器拿到 None）：照樣打按鈕寫的翻江龍，優勢 0
    assert _train_wait(game) == "兩人對峙……"
    with mock.patch.object(team, "fight", wraps=team.fight) as fight:
        game.choose("act:train")
    record = game.state.battles[0]
    assert record.opponent == "翻江龍" and record.narration == "" and record.rounds
    assert fight.call_args.kwargs["shift"] == 0.0

    game.rng = _LastChoice(0)  # 這回 Game.rng 要是被拿去挑，會挑到翻江龍
    _next_seq(game, "thug")
    assert _train_wait(game) == "" and game.fight_request("act:train") is None
    game.choose("act:train")
    assert game.state.battles[0].opponent == "水寇小隊" and game.state.battles[0].narration == ""


def _pick(game, battle_seq: int) -> str:
    game.state.battle_seq = battle_seq
    return game._train_pick(game.content.locations[game.state.player.location]).id


def test_train_trend_push_previews_the_push_for_your_faction(content, game):
    _training_factions(content)
    game.state.player.faction = "huang"
    assert game.train_trend_push("lake") == {"kou": 1}
    assert game.train_trend_push("town") == {}
    game.state.player.faction = None
    assert game.train_trend_push("lake") == {"kou": -1}
