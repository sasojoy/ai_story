import contextlib
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
def isolated_database(tmp_path, monkeypatch):
    """每個測試用自己的暫存資料庫，不會讀寫到真正的 saves/tianxia.db，測試之間也不會互相汙染；
    測試結束時關掉所有連線（Windows 才刪得掉暫存檔）。"""
    from tianxia import database

    monkeypatch.delenv(database.ENV_VAR, raising=False)
    monkeypatch.setattr(database, "DEFAULT_PATH", tmp_path / "tianxia.db")
    yield
    database.close_all()


@pytest.fixture
def content():
    return load_content(FIXTURE)


@pytest.fixture
def state(content):
    from tianxia.state import new_game_state

    return new_game_state(content, "沈浪")


@pytest.fixture
def world():
    from tianxia.sqlite_world import open_world

    return open_world()


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


@contextlib.contextmanager
def at(game, now: float):
    """把這個 Game 的現在時間設成 now（線上架構第 1 期：引擎不讀電腦時鐘，取代以前 mock 掉 time.time）。"""
    game.now = now
    yield game


# ── 第一季濃縮版（計畫 T2）：測試用的時刻表與戰線 ─────────────────────

LUZHI_LOCKED = {
    "guan": "史書上，盧植不肯賄賂左豐，被誣下獄。這一次，{name} 把證據送進了大將軍府。盧植仍在廣宗城下。",
    "huang": "史書上，盧植因不肯行賄而下獄。這一次也一樣，只是金帛是黃巾的 {name} 送去的。",
}
LUZHI_LOSER = {
    "guan": "黃巾的 {loser} 託人送進宮的金帛，最後成了左豐的罪證之一。",
    "huang": "官軍的 {loser} 蒐齊的證據送進了大將軍府，何進卻遲遲沒有動作。",
}


def season_one_events() -> list:
    """縮小的時刻表，照結算文件的寫法（固定、擲骰、決戰、版本、鎖定、豪強、人物效果各有一件）。"""
    from tianxia.models import FigureChange, TimetableEvent, TimetableOutcome

    O = TimetableOutcome  # noqa: N806
    return [
        TimetableEvent(id="uprising", week=1, front=None, title="三十六方起義", kind="fixed", outcomes={
            "fixed": O(text="三十六方同日起事。", chronicle="張角率三十六方同時起義。"),
        }),
        TimetableEvent(id="zhangmancheng", week=3, front="nanyang", title="張曼成攻殺南陽太守", kind="roll", roll_side="huang",
                       outcomes={
                           "成": O(text="宛城陷了。", chronicle="張曼成據宛城。", trends={"nanyang": 8}),
                           "不成": O(text="宛城守住了。", chronicle="張曼成攻宛城不下。", trends={"nanyang": -5},
                                    figures={"zhangmancheng": FigureChange(fate="受挫")}),
                       }),
        TimetableEvent(id="bocai", week=4, front="yingru", title="波才大敗朱儁", kind="roll", roll_side="huang", outcomes={
            "成": O(text="朱儁敗了。", chronicle="波才大敗朱儁。", trends={"yingru": 8}),
            "不成": O(text="朱儁穩住了。", chronicle="朱儁擋住了波才。", trends={"yingru": -5}),
        }),
        TimetableEvent(
            id="changshe_fire", week=6, front="yingru", title="長社火攻", kind="showdown",
            preface="史書上，皇甫嵩趁夜縱火，大破波才於長社。",
            third_party_text="事後才有人發現，兩軍吃的糧出自同一家：{name} 的糧車。", third_party_trends={"geju": 10},
            outcomes={
                "guan:大勝": O(text="這一次也一樣：火光燭天。", chronicle="皇甫嵩火攻長社。", trends={"yingru": -15}),
                "guan:險勝": O(text="這一次，只燒了半座營。", chronicle="波才敗走陽翟。", trends={"yingru": -8}),
                "huang:大勝": O(
                    text="這一次，火攻沒有成。", note="潁川得手之後，波才分兵北上，往廣宗去了。", chronicle="長社火攻失利。",
                    trends={"yingru": 15, "jizhou": 5}, chance_mods={"luzhi_siege": -0.10},
                    figures={"huangfusong": FigureChange(fate="重挫", front="jizhou", location="luzhi_camp")},
                ),
                "huang:險勝": O(text="這一次，黃巾死戰不退。", chronicle="長社火攻失利。", trends={"yingru": 8},
                               figures={"huangfusong": FigureChange(fate="重挫", front="jizhou", location="luzhi_camp")}),
            },
        ),
        TimetableEvent(id="luzhi_siege", week=7, front="jizhou", title="盧植圍廣宗", kind="roll", roll_side="guan", outcomes={
            "成": O(text="盧植圍了廣宗。", chronicle="盧植圍張角於廣宗。", trends={"jizhou": -8}),
            "不成": O(text="圍塹被衝開了。", chronicle="盧植圍廣宗不成。", trends={"jizhou": 5}),
        }),
        TimetableEvent(
            id="qinjie", week=7, front="nanyang", title="秦頡斬張曼成", kind="fixed", version_from="zhangmancheng",
            versions={"成": "甲", "不成": "乙"}, skip_if_out="zhangmancheng",
            outcomes={
                v: O(text=text, chronicle="秦頡斬張曼成。", trends={"nanyang": -3}, figures={
                    "zhangmancheng": FigureChange(fate="退場"),
                    "zhujun": FigureChange(fate="到任", front="nanyang", location="wan_city", only_if={"huangfusong": "yingru"},
                                           note="右中郎將朱儁也領兵南下，往宛城去了。"),
                })
                for v, text in (("甲:fixed", "新任南陽太守秦頡引兵來攻。"), ("乙:fixed", "援兵統帥秦頡趕到南陽。"))
            },
        ),
        TimetableEvent(
            id="luzhi_jailed", week=8, front=None, title="盧植下獄", kind="roll", roll_side="huang", base_chance=0.5,
            lock_result={"huang": "成", "guan": "不成"}, third_party_trends={"geju": 8},
            outcomes={
                "成": O(text="史書上，盧植下獄。這一次也一樣。", chronicle="盧植被誣下獄。", trends={"jizhou": 8},
                       locked_text={"huang": LUZHI_LOCKED["huang"]}, loser_text={"huang": LUZHI_LOSER["huang"]},
                       third_party_text="是袁本初在朝中替他說話，才減了死罪。",
                       figures={"luzhi": FigureChange(fate="下獄"),
                                "dongzhuo": FigureChange(fate="到任", front="jizhou", location="luzhi_camp")}),
                "不成": O(text="史書上，盧植下獄。這一次，奏報被壓了下來。", chronicle="盧植續圍廣宗。", trends={"jizhou": -5},
                         locked_text={"guan": LUZHI_LOCKED["guan"]}, loser_text={"guan": LUZHI_LOSER["guan"]},
                         third_party_text="朝中替盧中郎說話最力的是袁本初。{name} 在他府上坐了三個晚上。"),
            },
        ),
        TimetableEvent(
            id="wancheng", week=9, front="nanyang", title="宛城之戰", kind="showdown", version_from="zhangmancheng",
            versions={"成": "甲", "不成": "乙"},
            outcomes={
                f"{v}:{side}:{tier}": O(
                    text=f"{v}版{side}{tier}，{{官軍主將}}也在。", chronicle="宛城之戰。",
                    figures={"@commander:nanyang:guan": FigureChange(fate="受挫")} if side == "huang" else {},
                )
                for v in ("甲", "乙") for side in ("guan", "huang") for tier in ("大勝", "險勝")
            },
        ),
        TimetableEvent(id="xiaquyang", week=12, front="jizhou", title="下曲陽", kind="finale",
                       preface="史書上，皇甫嵩攻下曲陽。這一次……"),
    ]



def install_season_one(content):
    """打開第一季開關、季長 2.5 天，加上三條戰線與割據（起始值照結算文件的開季數字）與縮小的時刻表。
    每小時的虛擬玩家不在這裡測，先拿掉。"""
    from tianxia.models import Trend

    content.config.season_one, content.config.season_days = True, 2.5
    content.scenario.sim_players = []
    content.scenario.trends += [
        Trend(id="yingru", name="潁川汝南", start=40), Trend(id="nanyang", name="南陽", start=35),
        Trend(id="jizhou", name="冀州", start=55), Trend(id="geju", name="豪強割據", start=20),
    ]
    content.timetable = season_one_events()
    return content
