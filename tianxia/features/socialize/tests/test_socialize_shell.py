"""socialize 這一包的測試，從 tests/server/test_server.py 拆來（全部拆包第 61 批，只搬位置、不改斷言）。"""
import random
import threading
from unittest import mock
import pytest
import llm_queue
import server
from tianxia import companion_agent
from tianxia.characters import open_characters
from tianxia.engine import Game
# autouse 的 fixture 要明列：少一個，這個檔就會在沒有關排程、沒換雜湊參數之下跑（第 61 批）
from server_kit import (  # noqa: F401
    DIALOGUE_TURN, _no_landing, _no_preset_recipes, _stand_by_a_figure, _stand_in_a_hall, cheap_password_hashing,
    fresh_server_memory, game, lock_events, model_breaker_closed, save_dir, scheduler_off, season_already_open,
)

pytestmark = pytest.mark.whole_content


def test_opening_and_closing_the_audience_list_never_asks_the_model(game, lock_events):
    _stand_in_a_hall(game)
    assert "act:socialize" not in [o.id for o in game.options()]  # 廣宗沒有交友事件：兩位人物都要求見
    with mock.patch.object(server, "prepare_dialogue", side_effect=AssertionError("打開或收起名單不必備料")), \
            mock.patch.object(companion_agent, "generate_turn", side_effect=AssertionError("不該呼叫模型")):
        server.choose(game, "act:call")
        assert [o.id for o in game.options()] == ["call:zhangjiao", "call:zhangliang", "call:back"]
        server.choose(game, "call:back")
    assert lock_events == ["enter", "exit", "enter", "exit"]  # 各拿一次鎖，沒有備料那一趟
    assert not game.state.player.picking_audience


class _PicksEvent(random.Random):
    """rng.choices 從候選名單裡挑指定 id 的那一則：挑得到就證明它真的是合格的候選。"""

    def __init__(self, wanted: str):
        super().__init__(0)
        self.wanted = wanted

    def choices(self, population, weights=None, *, cum_weights=None, k=1):
        return [next(event for event in population if event.id == self.wanted)]


def test_socializing_at_the_generals_mansion_reaches_yuanshaos_meeting(game):
    """大將軍府有何進、袁紹兩位人物，也有袁紹的結識事件：交友只走事件、從不開口，所以結識事件發得出來。"""
    game.state.world.precise_actions = False  # 一類一顆之前的交友、求見（新規則在 tests/test_precise_actions.py，設計 8.4）
    game.state.player.location = "dajiangjun_fu"
    game.state.player.stats["fame"] = 99  # 兩位都見得到也一樣：交友不找人
    game.state.player.fortune = True
    ids = [o.id for o in game.options()]
    assert "act:socialize" in ids and "act:call" in ids
    assert not game.socialize_starts_dialogue()
    game.rng = _PicksEvent("meet_yuanshao")
    with mock.patch.object(companion_agent, "_generate", side_effect=AssertionError("交友不該開口對話")):
        game.choose("act:socialize")
    assert game.state.pending_event == "meet_yuanshao"
    assert game.state.player.pending_companion is None


@pytest.mark.parametrize("option", ["call:zhangliang", "act:socialize"])
def test_two_connections_asking_the_same_person_at_once_the_second_is_refused_and_the_first_is_applied(option, monkeypatch):
    """FB-077（佇列開著）：同一個帳號開兩條連線、同時按「求見」同一個人（交友同一條路：盧植營只有盧植一位，交友直接找他）。
    以前第二件在 B 段被擋下來拿 cancelled，C 段進鎖當成「生成不出對話」：寫一行「…似乎無心多談，你只好先行告辭。」、把求見的選單收掉，
    之後第一件的回話（模型花了十幾秒）套用時選單已經換了、重驗對不上，兩邊都沒談成、也沒人知道為什麼。現在跟開爐、隨口應對、大場面
    一樣：第二件被擋下來（丟 GameError，BUSY_DIALOGUE），不寫紀錄、求見的選單還開著、不扣體力；第一件照常套用。"""
    queue = llm_queue.LlmQueue(slots=2, bot_cap=1)
    monkeypatch.setattr(server, "QUEUE", queue)
    game = Game.new(server.CONTENT, "測試")
    audience = option.startswith("call:")
    (_stand_in_a_hall if audience else _stand_by_a_figure)(game)  # 求見要在兩位以上人物的地點（廣宗）：先打開求見名單，再指名
    game.state.player.picking_audience = audience
    figure = option.removeprefix("call:") if audience else "luzhi"
    open_characters().save(game.state)
    stamina = game.state.player.stamina
    started, release, asked, first = threading.Event(), threading.Event(), [], {}

    def generate(client, messages, required=()):
        asked.append(1)
        started.set()
        release.wait(5)
        return DIALOGUE_TURN

    monkeypatch.setattr(companion_agent, "generate_turn", generate)
    thread = threading.Thread(target=lambda: first.update(msgs=server.choose(game, option)))
    thread.start()
    assert started.wait(2)  # 第一件還在模型那邊
    with pytest.raises(server.GameError, match=server.BUSY_DIALOGUE):
        server.choose(game, option)  # 第二條連線按同一個人
    stored = open_characters().load("測試")
    assert (stored.player.stamina, stored.player.picking_audience, stored.player.pending_companion) == (stamina, audience, None)
    assert not any("無心多談" in "".join(e.lines) for e in stored.journal)  # 沒有寫紀錄
    assert option in [o.id for o in game.options()]  # 選項還在：求見的選單還開著
    assert asked == [1]  # 模型只被叫一次（第一件的）
    release.set()
    thread.join(5)
    stored = open_characters().load("測試")  # 第一件照常套用：對話開始、花了這一次的體力、求見的選單收起
    assert stored.player.pending_companion == figure and not stored.player.picking_audience
    assert stored.player.stamina == stamina - server.CONTENT.config.action_cost["socialize"]
    assert "他點了點頭。" in "".join(line for entry in stored.journal for line in entry.lines)
    assert not any("無心多談" in "".join(e.lines) for e in stored.journal)
    assert queue.snapshot() == {"running": 0, "waiting": 0}
