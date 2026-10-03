import random
from pathlib import Path

import pytest

from tianxia.content import load_content

FIXTURE = Path(__file__).parent / "fixtures" / "content"


class FixedRandom(random.Random):
    """random() 永遠回傳固定值，讓檢定與機率判定可以預測。"""

    def __init__(self, value: float):
        super().__init__(0)
        self.value = value

    def random(self) -> float:
        return self.value


@pytest.fixture(autouse=True)
def no_real_ollama_flavor_calls(monkeypatch):
    """flavor.py 的裝飾句潤色（重遊地點/重複事件/江湖大事）現在跟著 engine.py 幾乎每個
    行動一起被呼叫（見 check_thresholds/_move/_present），如果不假掉，整個測試套件會對
    fixture content 的 ollama_url（指向故意關閉的 port，見 tests/fixtures/content/
    config.json）各自真的嘗試連線一次才失敗——雖然每次只要 ~2 秒，但乘上整個套件的測試
    數量會拖到以分鐘計。預設回傳空字串（等同「這次沒有潤色句」，跟真的連不上時的行為
    一致），需要真的驗證 flavor 呼叫內容的測試（tests/test_flavor.py、test_engine.py 的
    重遊/重複事件測試）自己用 mock.patch.object 覆蓋這個預設值即可。

    同一個理由也適用於 chat_structured——battle_instance.py::assess_action_success_rate
    現在每次自訂戰鬥行動送出都會呼叫一次，不假掉的話同樣會對關閉的 port 真的連線才
    失敗（優雅退回保底值，不影響測試正確性，只是拖慢）。這裡讓它直接拋例外，模擬
    「連不上」，跟真正連不上時的行為（各呼叫端自己的 graceful fallback）一致；
    tests/test_real_content.py 用真實內容時已經有自己的 autouse fixture 蓋掉這個
    預設值，那邊不受影響。"""
    from tianxia.ollama_client import OllamaClient

    def _no_chat_structured(self, *args, **kwargs):
        raise RuntimeError("Ollama 連不上（測試環境預設假的，見 no_real_ollama_flavor_calls）")

    monkeypatch.setattr(OllamaClient, "chat_text", lambda self, messages, **kwargs: "")
    monkeypatch.setattr(OllamaClient, "chat_structured", _no_chat_structured)


@pytest.fixture(autouse=True)
def isolated_world_state(tmp_path, monkeypatch):
    """每個測試都用自己的暫存共用世界狀態檔，不會讀寫到真正的 saves/world/state.json，
    測試之間也不會互相汙染（例如武學命名去重、同伴招募狀態）；同時把 leaderboard.py
    預設掃描的存檔目錄也隔開，不會讓 end_season() 意外讀到這台機器真正的玩家存檔。"""
    from tianxia import leaderboard, world_state

    monkeypatch.setattr(world_state, "DEFAULT_PATH", tmp_path / "world" / "state.json")
    monkeypatch.setattr(leaderboard, "DEFAULT_SAVES_DIR", tmp_path / "saves")


@pytest.fixture
def content():
    return load_content(FIXTURE)


@pytest.fixture
def state(content):
    from tianxia.state import new_game_state

    return new_game_state(content, "沈浪")


@pytest.fixture
def world():
    from tianxia.world_state import WorldStateStore

    return WorldStateStore()


@pytest.fixture
def game(content):
    from tianxia.engine import Game

    content.config.train_event_chance = 0.0
    content.config.train_stat_chance = 0.0
    return Game.new(content, "沈浪", rng=random.Random(0))


def walk_to(game, dest: str) -> list[str]:
    """步行到相鄰的 dest：從選單出發，再把時間推到抵達那一刻（地圖擴充：移動要花時間）。回傳抵達時的訊息。"""
    game.choose(f"move:{dest}")
    journey = game.state.player.journey
    assert journey is not None, f"沒有出發：選單上沒有 move:{dest}"
    return game.advance(journey.arrive_at[-1] - game.state.world.time)
