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

CHANGSHE_LOCKED = "史書上，皇甫嵩趁夜縱火，大破波才於長社。這一次，{name} 讓史書沒有落空。"
CHANGSHE_LOSER = "黃巾的 {loser} 曾看破火攻，可惜晚了一步。"


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
                "guan:大勝": O(text="這一次也一樣：火光燭天。", chronicle="皇甫嵩火攻長社。", trends={"yingru": -15},
                              locked_text={"guan": CHANGSHE_LOCKED}, loser_text={"guan": CHANGSHE_LOSER}),
                "guan:險勝": O(text="這一次，只燒了半座營。", chronicle="波才敗走陽翟。", trends={"yingru": -8},
                              locked_text={"guan": CHANGSHE_LOCKED}, loser_text={"guan": CHANGSHE_LOSER}),
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


# ── 伏筆（計畫 T7a）：fixture 的幾條鏈與準備事件，掛在上面的第一季內容上 ─────────────

FORESHADOW_FIXTURE = Path(__file__).parent / "fixtures" / "foreshadow"


def install_foreshadows(content):
    """第一季內容（install_season_one）加上伏筆要的東西，最後整份跑一次 content.validate：
    - 三個陣營 guan（小鎮投靠）、huang（湖邊投靠）、haoqiang；遊歷不接戰後事件、不加屬性；
    - 戰線 yingru、nanyang、jizhou 也當大區（地圖右上角的小三角，不蓋到任何地點），各自的 front 就是自己，時刻表與伏筆的
      戰線檢查才認得；
    - 南區的「渡口」（port，連小鎮），加上時刻表會用到的盧植營、宛城；
    - 大勢人物：皇甫嵩在湖邊、朱儁在渡口、波才在小鎮可以對話，盧植、董卓、張曼成只是時刻表的人物；
    - 慢屬性三階（凡 1、靈 3、天 9 份糧草）與一支官軍的巡邏隊；
    - tests/fixtures/foreshadow/foreshadows.json 的六條鏈與 events.json 的三則事件。"""
    import json

    from tianxia.content import validate
    from tianxia.models import (
        CharacterDef, Connection, Drop, Event, FactionDef, Foreshadows, Location, MapRegion, Material, Squad,
    )

    install_season_one(content)
    content.config.train_event_chance = 0.0
    content.config.train_stat_chance = 0.0
    content.scenario.factions = [
        FactionDef(id="guan", name="官軍", join_at=["town"]),
        FactionDef(id="huang", name="黃巾", join_at=["lake"]),
        FactionDef(id="haoqiang", name="地方豪強"),
    ]
    for i, (rid, name) in enumerate((("yingru", "潁川汝南"), ("nanyang", "南陽"), ("jizhou", "冀州"))):
        x = 360 + i * 12
        content.map.regions.append(MapRegion(
            id=rid, name=name, front=rid, points=[[x, 0], [x + 10, 0], [x + 10, 8]], fill="#EEEEEE", text_fill="#999999",
            label_x=x, label_y=4,
        ))
    content.locations["port"] = Location(
        id="port", name="渡口", description="南邊的渡口。", connections=["town"], tags=["城鎮"], x=100, y=170,
    )
    content.locations["town"].connections.append(Connection("port"))
    for loc_id, name, x in (("luzhi_camp", "盧植營", 40), ("wan_city", "宛城", 60)):
        content.locations[loc_id] = Location(id=loc_id, name=name, description=f"{name}。", connections=[], x=x, y=170)
    stats = {"str": 6, "agi": 6, "con": 6, "wis": 6}
    for cid, name, talk_at in (
        ("huangfusong", "皇甫嵩", "lake"), ("zhujun", "朱儁", "port"), ("bocai", "波才", "town"),
        ("luzhi", "盧植", None), ("dongzhuo", "董卓", None), ("zhangmancheng", "張曼成", None),
    ):
        content.characters[cid] = CharacterDef(
            id=cid, name=name, kind="locked", deep_interaction=talk_at is not None, talk_at=talk_at, stats=stats,
        )
    for tier, name in ((1, "粗糧"), (2, "細糧"), (3, "軍糧")):
        content.materials[f"man_{tier}"] = Material(id=f"man_{tier}", name=name, attribute="慢", tier=tier)
    content.squads["guan_patrol"] = Squad(
        id="guan_patrol", name="官軍巡邏隊", difficulty=1, attribute="慢", faction="guan",
        drops=[Drop(material="man_2", chance=0.0), Drop(material="man_3", chance=0.0)],  # 只為了讓靈、天兩階有來源
    )
    content.foreshadows = Foreshadows.model_validate(
        json.loads((FORESHADOW_FIXTURE / "foreshadows.json").read_text(encoding="utf-8"))
    )
    for raw in json.loads((FORESHADOW_FIXTURE / "events.json").read_text(encoding="utf-8")):
        content.events[raw["id"]] = Event(**raw)
    validate(content)
    return content
