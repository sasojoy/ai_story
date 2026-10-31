"""每一包的契約（開發規範手冊 4.1 第三級）：照 FEATURES 逐包驗——

- 選項 id 都帶自己的前綴（沒有前綴的包一個選項都不給）；
- choose 不吃別包、也不吃核心的 id；自己的 id 吃得下；
- enabled 是 False 時一個選項都不給、選單不接管、不接任何 id、江湖畫面不多一個鍵；
- 換季：這一包認領的欄位（player_fields）除了說好帶走的（carried）都跟著新角色重來；
- 每一包有 README.md、登記的名字就是資料夾名、永遠按得下去的前綴都是自己的。

要把一包擺進「有選項」的局面，在那一包的 tests/ 放 <包名>_stage.py，寫 stages(game)：每擺好一種局面 yield 一個名字
（scripts/new_feature.py 會生一個什麼都不擺的）。真實內容 week7。
"""
from __future__ import annotations

import importlib.util
import random
import re
import types
import typing
from pathlib import Path

import pytest
from pydantic import BaseModel

from conftest import next_season, real_content
from tianxia.core import features as features_core
from tianxia.core.registry import FEATURES
from tianxia.engine import Game
from tianxia.sqlite_world import open_world
from tianxia.state import PlayerState

ROOT = Path(__file__).resolve().parents[2]
FEATURE_DIR = ROOT / "tianxia" / "features"
CORE_IDS = ["act:explore", "act:train", "move:yingshui", "choice:0", "talk:leave", "battle:join:guan", "season:resting", "x"]


def _game() -> Game:
    c = real_content("week7")
    c.config.auto_open_first_season = True
    game = Game.new(c, "契約客", rng=random.Random(0), world=open_world())
    game.skip_tutorial()
    game.sync(1000.0)
    for _ in range(6):  # 開局三選一之類待選的事件：選掉
        first = next((o.id for o in game.options() if o.id.startswith("choice:") and o.enabled), None)
        if first is None:
            break
        game.choose(first)
    return game


def _stages(feature, game):
    path = FEATURE_DIR / feature.name / "tests" / f"{feature.name}_stage.py"
    if not path.exists():
        yield "平常"
        return
    spec = importlib.util.spec_from_file_location(f"{feature.name}_stage", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    yield from module.stages(game)


def _own_ids(feature, game) -> list[str]:
    ids = []
    for _ in _stages(feature, game):
        ids += [o.id for o in feature.options(game)] + [o.id for o in (feature.menu(game) or [])]
    return ids


def test_each_folder_is_one_registered_package_with_a_readme():
    folders = sorted(p.name for p in FEATURE_DIR.iterdir() if (p / "__init__.py").exists())
    assert sorted(f.name for f in FEATURES) == folders
    for f in FEATURES:
        assert (FEATURE_DIR / f.name / "README.md").exists(), f.name
    prefixes = [f.prefix for f in FEATURES if f.prefix is not None]
    assert len(prefixes) == len(set(prefixes))


def test_every_package_web_file_is_loaded_by_the_page_and_the_web_harness():
    """一包登記的網頁檔（Feature.web；手冊 3.3、3.7）現在還記在三個地方：登記、index.html、tests/kit/webharness.APP_FILES（第 3 階才由伺服器
    照 FEATURES 生成）。三份要對得上：漏寫進 index.html 頁面上就沒有它，漏寫進 APP_FILES 網頁測試的假瀏覽器裡就沒有它，兩種都不會讓別的測試紅。
    js 排在殼的 app.js 前面（頂層的名字同在一個全域裡，app.js 一載入就用得到），css 排在 style.css 後面（同權重的它說了算）。"""
    import webharness

    web = ROOT / "web"
    page = (web / "index.html").read_text(encoding="utf-8")
    files = features_core.web_files()
    assert files == [name for f in FEATURES for name in f.web] and len(files) == len(set(files))
    for name in files:
        assert (web / name).exists(), name
        if name.endswith(".js"):
            assert page.count(f'<script src="/static/{name}"></script>') == 1, name
            assert page.index(f'src="/static/{name}"') < page.index('src="/static/app.js"'), name
            assert name in webharness.APP_FILES and webharness.APP_FILES.index(name) < webharness.APP_FILES.index("app.js"), name
        else:
            assert name.endswith(".css"), name
            assert page.count(f'<link rel="stylesheet" href="/static/{name}">') == 1, name
            assert page.index('href="/static/style.css"') < page.index(f'href="/static/{name}"'), name
    scripts = re.findall(r'<script src="/static/([^"]+)"></script>', page)
    assert scripts == list(webharness.APP_FILES)  # 頁面載入的 js 就是假瀏覽器接起來的那幾個、同一個順序


@pytest.mark.parametrize("feature", FEATURES, ids=lambda f: f.name)
def test_options_carry_the_package_prefix(feature):
    game = _game()
    ids = _own_ids(feature, game)
    if feature.prefix is None:
        assert ids == []
    assert all(i.startswith(f"{feature.prefix}:") for i in ids), ids
    assert all(p.startswith(f"{feature.prefix}:") for p in feature.bot_always), feature.bot_always


@pytest.mark.parametrize("feature", FEATURES, ids=lambda f: f.name)
def test_choose_takes_only_its_own_ids(feature):
    game = _game()
    own = _own_ids(feature, game)
    others = [i for f in FEATURES if f is not feature for i in _own_ids(f, _game())]
    for option_id in CORE_IDS + others:
        kind, _, arg = option_id.partition(":")
        assert feature.choose(game, kind, arg) is None, option_id
    for option_id in own:
        kind, _, arg = option_id.partition(":")
        assert feature.choose(game, kind, arg) is not None, option_id


@pytest.mark.parametrize("feature", FEATURES, ids=lambda f: f.name)
def test_a_closed_package_gives_nothing(feature, monkeypatch):
    game = _game()
    staged = list(_stages(feature, game))  # 擺到最後一種局面
    own = _own_ids(feature, _game())
    shown = set(feature.status(game))  # 開著時它會放進江湖畫面的鍵
    monkeypatch.setattr(type(feature), "enabled", lambda self, ctx: False)
    assert staged and feature not in features_core.active(game)
    assert features_core.menu(game) is None
    assert not shown & set(game.feature_status())
    if feature.prefix is not None:
        assert not any(o.id.startswith(f"{feature.prefix}:") for o in features_core.options(game))
        assert not any(o.id.startswith(f"{feature.prefix}:") for o in game.options())
    for option_id in own:
        kind, _, arg = option_id.partition(":")
        assert features_core.choose(game, kind, arg) is None
        assert game.choose(option_id) == ["（此刻無法這麼做。）"]


def _dirty(annotation, default):
    """換季前把欄位擺成一個跟預設不一樣的值。"""
    origin = typing.get_origin(annotation)
    args = [a for a in typing.get_args(annotation) if a is not type(None)]
    optional = origin in (typing.Union, types.UnionType)
    if annotation is bool:
        return not default
    if annotation is int or (optional and args == [int]):
        return (default or 0) + 7
    # 小數、字串、可以沒有的子模型：主動搬六包第 2 批補的（約戰的 sortie_cooldown_until、answer_cooldown_until 是 float | None；
    # 批次表第二節、critic.json issues[4]：走一趟的 outing 是 Outing | None、escort_pick 是 str。改核心測試，算例外）
    if annotation is float or (optional and args == [float]):
        return (default or 0.0) + 7.5
    if annotation is str or (optional and args == [str]):
        return (default or "") + "契約"
    if optional and len(args) == 1 and isinstance(args[0], type) and issubclass(args[0], BaseModel):
        return args[0].model_construct()  # 一份全是預設值的（不驗必填）：跟預設的 None 不一樣就夠
    if origin is list:
        return [7]
    if origin is set:
        return {"x"}
    if origin is dict:
        return {"x": 7}
    raise AssertionError(f"契約測試還不會擺 {annotation} 這種欄位，補 _dirty")


@pytest.mark.parametrize("field", ["sortie_cooldown_until", "hidden_until", "escort_pick", "outing_last", "outing", "sorties_today",
                                   "picking_audience", "visited", "team", "affinities", "sect"])  # sect 是 str | None（dev/sortie-2 審查補）
def test_dirty_moves_every_kind_of_field_off_its_default(field):
    """_dirty 每一種都真的擺得出跟預設不一樣的值（還沒有包認領的那幾種也擺一次：不然補了永遠沒跑過）。只挑型別定義在 PlayerState 前面的欄位：
    寫在後面的（letters 的 Letter）在 PlayerState 第一次建出來之前，model_fields 裡還是 ForwardRef（xdist 分到這一條先跑的那個 worker 就紅過）；
    換季那一條先建了 Game，讀到的都是解開的型別。"""
    info = PlayerState.model_fields[field]
    default = info.get_default(call_default_factory=True)
    assert _dirty(info.annotation, default) != default


@pytest.mark.parametrize("feature", FEATURES, ids=lambda f: f.name)
def test_a_new_season_keeps_only_what_the_package_carries(feature):
    c = real_content("week7")
    c.config.auto_open_first_season = True
    world = open_world()
    game = Game.new(c, "換季客", rng=random.Random(0), world=world)
    game.skip_tutorial()
    game.sync(100.0)
    fields = PlayerState.model_fields
    assert set(feature.carried) <= set(feature.player_fields)
    before = {}
    for name in feature.player_fields:
        value = _dirty(fields[name].annotation, fields[name].get_default(call_default_factory=True))
        setattr(game.state.player, name, value)
        before[name] = value
    next_season(c, world, game)
    for name in feature.player_fields:
        now = getattr(game.state.player, name)
        if name in feature.carried:
            assert now == before[name], name
        else:
            assert now == fields[name].get_default(call_default_factory=True), name
