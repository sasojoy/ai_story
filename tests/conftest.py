import contextlib
import hashlib
import json
import os
import pickle
import random
import shutil
from pathlib import Path

import pytest

from tianxia import content as content_mod
from tianxia.content import load_content
from tianxia.models import Content

FIXTURE = Path(__file__).parent / "fixtures" / "content"
REAL_CONTENT = Path(__file__).parent.parent / "content"

# 平行跑（pytest-xdist 的 -n）時，worker 由 execnet 開：它把 site-packages 的路徑寫進 worker 的標準輸入，這台機器上那個
# 路徑有中文，worker 卻照 Windows 的字碼頁（cp950）讀，沒設 PYTHONIOENCODING 的 shell 一開 -n 就在啟動時 INTERNALERROR
# （EOFError）。worker 繼承這個行程的環境變數，這個檔又在開 worker 之前載入，所以在這裡補上；已經設了的照舊。
os.environ.setdefault("PYTHONIOENCODING", "utf-8")


# ── 內容快取 ──────────────────────────────────────────────────────────
# 載入一份內容要 parse＋validate（正式內容約 0.1 秒、測試內容約 0.01 秒），以前用到它的測試每個各載一次。現在每份內容
# 在一個工作階段只完整載入、驗證一次（母本），每個測試拿母本的 pickle 複本：測試怎麼改自己那一份都碰不到母本，也漏不到
# 別的測試。正式內容（real_content）、測試內容（fixture content）、序章內容（prologue_content）都走這裡。
# 直接測載入的測試（設定覆寫檔、test_real_content_loads、改了內容再 validate 的）照舊直接呼叫 load_content。

_MASTERS: dict[tuple, tuple[Content, bytes]] = {}  # 快取的鍵 → （母本, 母本的 pickle 位元組；複本都從這份位元組做）


def _dump(content: Content) -> bytes:
    """母本的 pickle 位元組：發複本與工作階段結束時的檢查用同一個寫法。"""
    return pickle.dumps(content, pickle.HIGHEST_PROTOCOL)


def _content_key(root, profile) -> tuple:
    """快取的鍵：哪個資料夾、哪份設定覆寫檔，再加上 load_content 會併進管理者名單的兩樣（content._with_local_admins）：
    這台機器的 `.local/admins.txt`（路徑與內容）與環境變數 `TIANXIA_ADMINS`。動了這兩樣的測試拿到的是另一份母本。
    ADMINS_FILE 在呼叫的當下讀，所以 monkeypatch 換掉它也算數。"""
    admins_file = Path(content_mod.ADMINS_FILE)
    local = admins_file.read_text(encoding="utf-8") if admins_file.exists() else None
    return str(Path(root).resolve()), profile, str(admins_file), local, os.environ.get("TIANXIA_ADMINS")


def cached_content(root, profile=None) -> Content:
    """root 的內容（profile 是設定覆寫檔）：這個工作階段第一次要的時候完整載入、驗證一次當母本，每次都給一份新的複本
    （第一次也是複本，母本誰都拿不到）。兩件事要知道：
    - 母本是在第一個要它的測試當下建的，那個測試當時的環境（monkeypatch 過的東西）會跟著進母本、再進之後每一份複本。
      所以 patch 了載入或驗證路徑（load_content、validate 會碰到的東西）的測試不要用這裡，自己直接 load_content。
    - 鍵不看資料夾裡的檔：root 在一個工作階段裡不能改（正式內容、測試內容、序章母本資料夾都不改）。要改檔再載入的測試
      用自己的一份資料夾（prologue_root、copy_fixture）直接 load_content。"""
    key = _content_key(root, profile)
    if key not in _MASTERS:
        master = load_content(root, profile)
        _MASTERS[key] = (master, _dump(master))
    return pickle.loads(_MASTERS[key][1])


def real_content(profile=None) -> Content:
    """正式內容（content/）的複本；profile 是設定覆寫檔（例如 "weekend"）。"""
    return cached_content(REAL_CONTENT, profile)


@pytest.fixture(scope="session", autouse=True)
def content_masters_stay_unchanged():
    """工作階段結束時，每份母本重新 pickle 一次，位元組要跟發第一份複本時一模一樣，不一樣就寫出是哪一份、哪幾個欄位。
    cached_content 從不交出母本，所以這一條守的是 cached_content 本身（例如有人改成直接回母本），不是在查測試之間的複本：
    複本之間本來就不共用任何東西。"""
    yield
    changed = []
    for key, (master, blob) in _MASTERS.items():
        if _dump(master) != blob:
            first = pickle.loads(blob)
            fields = [name for name in Content.model_fields if getattr(master, name) != getattr(first, name)]
            changed.append(f"{key[0]}（設定 {key[1]}）的 {fields or '某處'}")
    assert not changed, f"內容快取的母本被改過：{'；'.join(changed)}"


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
    """測試內容（tests/fixtures/content）：這個測試自己的一份（cached_content 的複本），怎麼改都不會漏到別的測試。"""
    return cached_content(FIXTURE)


PROLOGUE = Path(__file__).parent / "fixtures" / "prologue"


def _folder_digest(root: Path) -> dict[str, str]:
    """資料夾裡每個檔（相對路徑 → 內容的 sha256）。"""
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*")) if path.is_file()
    }


_PROLOGUE_DIGEST: dict[Path, dict[str, str]] = {}  # 序章母本資料夾 → 剛做好時每個檔的 sha256


def _prologue_master_unchanged(root: Path, when: str) -> None:
    """序章母本資料夾跟剛做好時一模一樣；不一樣就寫出是哪幾個檔（改了、多了、少了）與發現的時間點。"""
    before, now = _PROLOGUE_DIGEST[root], _folder_digest(root)
    if now == before:
        return
    diff = ([f"改了 {p}" for p in sorted(before.keys() & now.keys()) if before[p] != now[p]]
            + [f"多了 {p}" for p in sorted(now.keys() - before.keys())]
            + [f"少了 {p}" for p in sorted(before.keys() - now.keys())])
    pytest.fail(f"序章內容的母本資料夾被改過（{when}）：{'、'.join(diff)}（{root}）", pytrace=False)


@pytest.fixture(scope="session")
def _prologue_master(tmp_path_factory):
    """有序章的測試內容（新手引導計畫一）的母本資料夾，每個工作階段只做一份：測試內容加上草廬（hut，只連 town）、
    斷眉（duanmei）、一門雜學（junk）、三則序章事件、四筆師門配方與十一步的序章；開局送 basic_breath、basic_fist，
    升級門檻照正式的 10，開局心得 20（測試內容沒寫 start_stats 時心得是 0，合成與修練都付不起）。
    測試不直接用它：要改內容再載入的測試（驗證）用 prologue_root（自己的一份複本），只要載入好的內容用 prologue_content。
    prologue_root 每次複製前後、以及工作階段結束時，都檢查這個資料夾裡每個檔都沒被改過。"""
    root = tmp_path_factory.mktemp("prologue") / "prologue_content"
    shutil.copytree(FIXTURE, root)
    for name in ("tutorial.json", "preset_recipes.json", "insight_scenes.json"):
        shutil.copy(PROLOGUE / name, root / name)
    shutil.copy(PROLOGUE / "events.json", root / "events" / "prologue.json")

    def edit(name, change):
        path = root / name
        data = json.loads(path.read_text(encoding="utf-8"))
        change(data)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def locations(locs):
        next(loc for loc in locs if loc["id"] == "town")["connections"].append("hut")
        locs.append({
            "id": "hut", "name": "草廬", "description": "滿屋子酒味。", "connections": ["town"],
            "x": 60, "y": 60, "tags": ["草廬"], "insights": ["feng", "shan", "shui", "huo"], "prologue_only": True,
        })

    edit("locations.json", locations)
    edit("squads.json", lambda squads: squads.append(
        {"id": "duanmei", "name": "斷眉", "difficulty": 10, "attribute": "剛", "reward_silver": 0, "reward_xinde": 0, "exp": 10}
    ))
    edit("skills.json", lambda skills: skills.append(
        {"id": "junk", "name": "蠻牛拳", "kind": "武學", "attribute": "剛", "quality": "下品"}
    ))
    # start_stats 要寫整份（會取代預設）：測試內容沒寫時心得是 0，合成與修練都付不起，序章走不下去
    edit("config.json", lambda cfg: cfg.update(
        starter_skills=["basic_breath", "basic_fist"], level_exp=10,
        start_stats={"str": 5, "agi": 5, "con": 5, "wis": 5, "lore": 5, "silver": 50, "good": 0, "evil": 0, "fame": 0, "xinde": 20},
    ))
    _PROLOGUE_DIGEST[root] = _folder_digest(root)
    yield root
    _prologue_master_unchanged(root, "工作階段結束時")


@pytest.fixture
def prologue_root(tmp_path, _prologue_master):
    """有序章的測試內容（見 _prologue_master）放在哪個資料夾：這個測試自己的一份複本，要改內容再載入的測試（驗證）用這個；
    只要載入好的內容用 prologue_content。複製之前先確認母本沒被改過（改了就是之前哪個測試動的），這個測試做完再確認一次
    （改了就是這個測試動的）：一份 20 個檔的雜湊約 2 毫秒。"""
    _prologue_master_unchanged(_prologue_master, "這個測試開始之前")
    root = tmp_path / "prologue_content"
    shutil.copytree(_prologue_master, root)
    yield root
    _prologue_master_unchanged(_prologue_master, "這個測試做完之後")


@pytest.fixture
def prologue_content(_prologue_master):
    """有序章的測試內容（見 _prologue_master）載入好的一份：這個測試自己的一份（cached_content 的複本）。"""
    return cached_content(_prologue_master)


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
    return Game.new(content, "沈浪", rng=random.Random(0))


# ── 真實內容的 real、on（test_orders、test_enlist、test_enlist_web 共用這一份）────────────
# 其他檔有自己的 real／on（設定各不相同），在那些檔裡蓋過這兩個：pytest 用離測試最近的定義。


@pytest.fixture
def real():
    """真實內容，開關關著（beta 那一季的樣子）；季自己開、遊歷打完不接戰後事件。"""
    c = real_content()
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    return c


@pytest.fixture
def on(real):
    """同一份真實內容，照週末設定打開：開關、季長 2.5 天、人數上限 2（每道軍令 4 次）。"""
    real.config.season_one = True
    real.config.season_days = 2.5
    real.config.server_max_players = 2
    return real


def next_season(content, world, *players):
    """管理者收季再開下一季，再讓每個玩家同步一次（換季重來發生在 sync 裡）；照 test_engine._roll_one_season 的做法。"""
    from tianxia.engine import Game

    content.config.admins = ["管理者"]
    admin = Game.new(content, "管理者", rng=random.Random(1), world=world)
    admin.admin_end_season(now=200.0)
    admin.admin_next_season(now=300.0)
    for player in players:
        player.sync(400.0)
        assert player.state.player.season_number == 2


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


def install_showdowns(content, region: str = "north"):
    """第一季內容（install_season_one）加上時刻表決戰的 BattleDef（計畫 T8）：長社（守方官軍、潁川）、宛城甲（守方黃巾）、
    宛城乙（守方官軍、南陽）。都在 region 這個大區打（fixture 的小鎮在北區），一幕三回合；兩邊各有強攻、固守、奇襲
    （<陣營>_strong／_hold／_raid，決戰改版一）；保底結果只有一筆（實際結果走時刻表）。回傳 {id: BattleDef}。"""
    from tianxia.models import MOVES, BattleAct, BattleDef, BattleFaction, BattleOption, BattleOutcome

    codes = {"強攻": "strong", "固守": "hold", "奇襲": "raid"}
    options = [
        BattleOption(text=f"{side}{move}", tag=f"{side}_{codes[move]}", faction=side, move=move)
        for side in ("guan", "huang") for move in MOVES
    ]
    made = {}
    for bid, name, event, version, defender, front in (
        ("changshe_fire", "長社火攻", "changshe_fire", None, "guan", "yingru"),
        ("wancheng_jia", "宛城之戰", "wancheng", "甲", "huang", "nanyang"),
        ("wancheng_yi", "宛城之戰", "wancheng", "乙", "guan", "nanyang"),
    ):
        made[bid] = content.battles[bid] = BattleDef(
            id=bid, name=name, region=region, timetable_event=event, version=version, defender=defender, front=front,
            factions=[BattleFaction(id="guan", name="官軍"), BattleFaction(id="huang", name="黃巾軍")],
            acts=[BattleAct(id=f"{bid}_1", title="兩軍對陣", text="兩軍列陣。", goal="分出勝負", options=list(options))],
            outcomes=[BattleOutcome(faction=defender, title=f"{name}戰罷", text="廝殺停了下來。")],
            muster_seconds=600, round_seconds=120,
        )
    return made


# ── 伏筆（計畫 T7a）：fixture 的幾條鏈與準備事件，掛在上面的第一季內容上 ─────────────

FORESHADOW_FIXTURE = Path(__file__).parent / "fixtures" / "foreshadow"


def install_foreshadows(content):
    """第一季內容（install_season_one）加上伏筆要的東西，最後整份跑一次 content.validate：
    - 三個陣營 guan（小鎮投靠）、huang（湖邊投靠）、haoqiang；遊歷不接戰後事件；
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
