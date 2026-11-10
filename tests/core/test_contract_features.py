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

import functools
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
# companions（第 20 批審查）：原本的 "talk:leave" 這一批拿了前綴之後是人物情誼包的 id，換成核心的 "road:back"。
# battle（全部拆包第 8 批）：原本的 "battle:join:guan" 第 7 批拿了前綴之後其實是決戰包的 id（第 7 批 PM 認定第 6 條），換成核心的 "season:paused"
# travel（全部拆包第 47 批）：原本的 "move:yingshui"、"road:back" 這一批拿了前綴之後是移動包的 id，換成核心的 "act:rest"、"choice:1"（faction: 歸第 35 批、bounty: 歸第 45 批，同一波合進來不能拿它們當核心 id）。
CORE_IDS = ["act:explore", "act:train", "act:rest", "choice:0", "choice:1", "season:paused", "season:resting", "x"]
# 選單由核心原位排、包一律開著（enabled 一律 True）的包：關掉它也不會讓選單少掉那幾顆（test_a_closed_package_gives_nothing 不查選單那兩行）
MENU_BY_CORE = {"travel": "移動的選單（前往、折返、路上小事）順序算行為，Game 原位叫包的函式排（不走 Feature.options）；包一律開著，選單本來就不看開關（全部拆包第 47 批）"}


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
    """這一包在每一種局面給的選項（options、接管的選單，與坐在它的店裡時店裡那一串——店面登記，第 11 批）。行動列那一格（Verb.cell）
    給的是核心 act: 前綴的 id，不算這一包的。"""
    ids = []
    for _ in _stages(feature, game):
        ids += [o.id for o in feature.options(game)] + [o.id for o in (feature.menu(game) or [])]
        ids += [o.id for o in (feature.prep(game) or [])]  # 開季準備卡那一步（prep；None 是這一包沒有要在卡上給的）
        ids += [o.id for shop in feature.shops() if shop.inside(game) for o in shop.menu(game)]
    return ids


@functools.lru_cache(maxsize=None)
def _ids_on_a_fresh_game(name: str) -> tuple[str, ...]:
    """這一包在一個新角色上給的 id；test_choose_takes_only_its_own_ids 的 others 每一列要 35 包，一個行程算一次就好（第二輪第 75 批；三個契約檔 -n 4 量到 55 秒 → 31 秒）。
    每次現算只有 feast 不一樣（feast:join:<編號> 的編號全服累計，算一次多一個），都是 feast: 前綴，對 choose 吃不吃沒有差。"""
    return tuple(_own_ids(next(f for f in FEATURES if f.name == name), _game()))


def _starts(option_id: str, feature) -> bool:
    return any(option_id.startswith(f"{p}:") for p in features_core.prefixes(feature))


def test_each_folder_is_one_registered_package_with_a_readme():
    folders = sorted(p.name for p in FEATURE_DIR.iterdir() if (p / "__init__.py").exists())
    assert sorted(f.name for f in FEATURES) == folders
    for f in FEATURES:
        assert (FEATURE_DIR / f.name / "README.md").exists(), f.name


def test_no_two_packages_claim_the_same_prefix_verb_or_shop():
    """前綴（Feature.prefix 收字串或 tuple，第 11 批 PM 定）攤開之後全部不重複：分派照第一個對上的，兩包同一個前綴就分不清了。
    act 子動詞（Verb）一格只有一個主人、店面（Shop）的 key 不重複（同一個道理）。"""
    prefixes = [p for f in FEATURES for p in features_core.prefixes(f)]
    assert len(prefixes) == len(set(prefixes)), prefixes
    assert all(p and ":" not in p for p in prefixes), prefixes
    verbs = [v.verb for f in FEATURES for v in f.verbs()]
    assert len(verbs) == len(set(verbs)), verbs
    keys = [s.key for f in FEATURES for s in f.shops()]
    assert len(keys) == len(set(keys)), keys


SHOP_OWNERS = {"smith": "smithy", "arena": "bout", "donate": "outlets", "dadian": "outlets", "board": "bounties", "market": "gear", "tavern": "tavern"}


class _Untouched:
    """碰任何屬性就丟：Feature.shop_view 開頭先認店，不是自己的店不看 ctx（靠這個問得出誰認，不用真的開一間店）。"""

    class Touched(Exception):
        pass

    def __getattr__(self, name):
        raise self.Touched(name)


def _claims(feature, shop: str) -> bool:
    try:
        return feature.shop_view(_Untouched(), shop) is not None
    except _Untouched.Touched:
        return True


def test_one_shop_has_exactly_one_package_answering_its_page():
    """第二輪第 93 批：一間店只有一包認（Feature.shop_view；features.shop_page 照 FEATURES 問、第一個不是 None 的回去，兩包都認就分不清了）。
    店的清單是 shop_base.BACKS（page_view._shop_live 認的那一份）；不認得的店沒有人認。"""
    from tianxia.core import shop_base

    claims = {shop: [f.name for f in FEATURES if _claims(f, shop)] for shop in shop_base.BACKS}
    assert claims == {shop: [owner] for shop, owner in SHOP_OWNERS.items()}
    assert [f.name for f in FEATURES if _claims(f, "沒有這間店")] == []


def test_a_tuple_prefix_is_spread_and_dispatched_by_the_first_match(monkeypatch):
    """一包兩三個前綴寫 tuple：prefixes 攤開，owner_of 照清單、照前綴找第一個對上的；字串照收、None 是沒有前綴。"""
    from tianxia.core import registry
    from tianxia.core.features import Feature

    class Two(Feature):
        name, prefix = "two", ("duel", "arena")

    class One(Feature):
        name, prefix = "one", "seal"

    two, one = Two(), One()
    monkeypatch.setattr(registry, "FEATURES", [one, two])
    assert features_core.prefixes(two) == ("duel", "arena") and features_core.prefixes(one) == ("seal",)
    assert features_core.prefixes(Feature()) == ()
    assert features_core.owner_of("arena:fight:x") is two and features_core.owner_of("duel:強攻") is two
    assert features_core.owner_of("seal:go") is one and features_core.owner_of("act:arena") is None


def _held_functions(fn) -> list:
    """fn 與它的閉包裡（一層層往下）存著的函式物件。"""
    out, stack, seen = [], [fn], set()
    while stack:
        f = stack.pop()
        if id(f) in seen or not hasattr(f, "__code__"):
            continue
        seen.add(id(f))
        out.append(f)
        for cell in getattr(f, "__closure__", None) or ():
            try:
                stack.append(cell.cell_contents)
            except ValueError:  # 還沒賦值的格
                continue
    return out


@pytest.mark.parametrize("feature", FEATURES, ids=lambda f: f.name)
def test_declared_seams_look_up_the_package_functions_when_called(feature):
    """店面登記（Shop）與 act 子動詞（Verb）建一次就留著（契約照同一個物件認），裡面每一格卻要在叫的那一下才去包的模組找函式
    （批次表第二節「同一個模組物件，monkeypatch 照樣有效」；原本 Game 上的委派每次照模組屬性找）：宣告裡、它的閉包裡都不准存著
    包裡別的模組的函式物件（`menu=actions.tavern_options`、`on = explore_actions.outing_on`）——存了的話，建好之後換掉模組上的函式打不到，
    建之前就換的話還原之後還留著，漏到同一個行程後面的測試（第 11 批審查）。寫成在包的 __init__ 裡的 lambda、照模組屬性叫。"""
    import dataclasses

    home = type(feature).__module__
    # core_world（第 25 批）：世界層的格（WorldHook）也一樣；core_effects（第 32 批）：效果的格（EffectHook）、叛投的格（DefectHook）也一樣；
    # core_eventbus（第 26 批）：事件的格（BusHook）也一樣；core_step（第 36 批）：「你這一步」的格（StepHook）也一樣
    # 玩法說明的格（HowtoHook，第 59 批）也一樣；內容驗證的格（ContentSlot，第二輪第 100 批）也一樣
    for decl in [*feature.shops(), *feature.verbs(), *feature.world(), *feature.effects(), *feature.defection(), *feature.bus(),
                 *feature.steps(), *feature.howto(), *feature.content_slots()]:
        for field in dataclasses.fields(decl):
            value = getattr(decl, field.name)
            if not callable(value):
                continue
            held = [f"{f.__module__}.{f.__qualname__}" for f in _held_functions(value) if f.__module__ != home]
            assert not held, (feature.name, type(decl).__name__, getattr(decl, "verb", getattr(decl, "key", None)), field.name, held)


def test_a_patched_package_function_reaches_the_seam_before_and_after_the_first_call(monkeypatch):
    """同上，照實際的路走一次：先照常問一次紀錄標題（宣告建好），再換掉酒肆的招牌、探索的開關，掛鉤要叫到換過的；宣告建之前就換、
    換回來之後，掛鉤要跟著回到真的那一個（不留在閉包裡）。"""
    from tianxia import journal
    from tianxia.features.explore import FEATURE as explore
    from tianxia.features.explore import explore_actions
    from tianxia.features.tavern import actions as tavern_actions

    game = _game()
    game._action_title("act", "tavern")
    game._action_title("act", "explore")
    monkeypatch.setattr(tavern_actions, "tavern_sign", lambda ctx: "換過的招牌")
    assert game._action_title("act", "tavern") == "換過的招牌"
    real = bool(explore_actions.outing_on(game))
    monkeypatch.setattr(explore_actions, "outing_on", lambda ctx: not real)
    assert game._action_title("act", "explore").startswith(journal.OUTING) is (not real)
    monkeypatch.undo()

    monkeypatch.setattr(explore, "_verbs", None)  # 宣告還沒建（例：同一個 worker 裡這是第一個問它的測試）
    with monkeypatch.context() as m:
        m.setattr(explore_actions, "outing_on", lambda ctx: not real)
        assert game._action_title("act", "explore").startswith(journal.OUTING) is (not real)
    assert bool(explore_actions.outing_on(game)) is real
    assert game._action_title("act", "explore").startswith(journal.OUTING) is real


def test_every_package_web_file_is_loaded_by_the_page_and_the_web_harness():
    """一包登記的網頁檔（Feature.web；手冊 3.3、3.7）：js 的 script 標籤第 64 批起由伺服器照 FEATURES 生成（features_core.with_scripts），
    css 的 link 與 tests/kit/webharness.APP_FILES 還是手寫的。要對得上：漏寫進去頁面上就沒有它，漏寫進 APP_FILES 網頁測試的假瀏覽器裡就沒有它，兩種都不會讓別的測試紅。
    js 排在殼的 app.js 前面（頂層的名字同在一個全域裡，app.js 一載入就用得到），css 排在 style.css 後面（同權重的它說了算）。"""
    import webharness

    web = ROOT / "web"
    page = features_core.with_scripts((web / "index.html").read_text(encoding="utf-8"))
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
    assert all(_starts(i, feature) for i in ids), ids
    assert all(_starts(p, feature) for p in feature.bot_always), feature.bot_always


@pytest.mark.parametrize("feature", FEATURES, ids=lambda f: f.name)
def test_choose_takes_only_its_own_ids(feature):
    game = _game()
    own = _own_ids(feature, game)
    others = [i for f in FEATURES if f is not feature for i in _ids_on_a_fresh_game(f.name)]
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
    # 給選項的接縫掛鉤（第 11 批）也不給：店裡那一串、進店那一顆、行動列那一格（一格只有一個主人，主人關著就沒人接）
    assert not any(s in features_core._shops(game, gated=True) for s in feature.shops())
    entries = features_core.shop_entries(game)
    assert not any((e := s.entry(game)) is not None and e in entries for s in feature.shops())
    loc = game.content.locations[game.state.player.location]
    assert all(features_core.act_cell(game, v.verb, loc, 0, False) is None for v in feature.verbs() if v.cell is not None)
    if feature.prefix is not None:
        assert not any(_starts(o.id, feature) for o in features_core.options(game))
    if feature.prefix is not None and feature.name not in MENU_BY_CORE:
        assert not any(_starts(o.id, feature) for o in game.options())
    for option_id in own:
        kind, _, arg = option_id.partition(":")
        assert features_core.choose(game, kind, arg) is None
        assert game.choose(option_id) == ["（此刻無法這麼做。）"]


@pytest.mark.parametrize("feature", [f for f in FEATURES if type(f).prep is not features_core.Feature.prep], ids=lambda f: f.name)
def test_a_closed_package_gives_nothing_on_the_prep_card(feature, monkeypatch):
    """開季準備卡那一步（prep）：要在「它給得出東西」的那一種局面當場關才驗得到。上一條擺到最後一種局面才關，傳承的候選
    那時已經封掉，開著也是 None。沒有一種局面給得出東西，就是局面檔沒擺到，一樣算紅。"""
    game = _game()
    reached = 0
    for _ in _stages(feature, game):
        if not feature.prep(game):
            continue
        reached += 1
        assert any(_starts(o.id, feature) for o in features_core.prep(game) or [])
        with monkeypatch.context() as closed:
            closed.setattr(type(feature), "enabled", lambda self, ctx: False)
            assert features_core.prep(game) is None
    assert reached


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
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):  # 一定有的子模型（女子與隱線的 heroines）：頭一格擺髒
        name, field = next(iter(annotation.model_fields.items()))
        return default.model_copy(update={name: _dirty(field.annotation, field.get_default(call_default_factory=True))})
    if origin is list:
        # story（全部拆包第 30 批）：lasting 是字串的清單，換季時併進旗標集合（annals 讀旗標的字串開頭），擺 7 會壞；字串的清單擺字串
        return ["x"] if typing.get_args(annotation) == (str,) else [7]
    if origin is set:
        return {"x"}
    if origin is dict:
        value = typing.get_args(annotation)[-1]
        if isinstance(value, type) and issubclass(value, BaseModel):  # story（全部拆包第 30 批）：一條線的進度 StoryProgress，必填的 line 擺一個內容裡沒有的 id；不驗（人物情誼包的 TalkMemo 必填的 at 是小數，第 30 批合併時改）
            return {"x": value.model_construct(**{n: "x" for n, f in value.model_fields.items() if f.is_required()})}
        if len(args) == 2 and typing.get_origin(args[1]) is list:  # 值是清單的（人物情誼包的 dialogue_history）：換季會對值取長度，擺 7 會壞
            return {"x": []}
        return {"x": 7}
    raise AssertionError(f"契約測試還不會擺 {annotation} 這種欄位，補 _dirty")


@pytest.mark.parametrize("field", ["sortie_cooldown_until", "hidden_until", "escort_pick", "outing_last", "outing", "sorties_today",
                                   "picking_audience", "visited", "team", "affinities", "sect", "dialogue_history"])  # dialogue_history 值是清單（第 20 批審查補）；sect 是 str | None（dev/sortie-2 審查補）
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
    # 傳承（week7 2026-11-05 起打開）換季那一刻會結算、改寫帶著的那一份：這裡只驗「帶不帶」，結算本身在 features/legacy/tests
    c.config.legacy.enabled = False
    # 親衛隊長（week7 2026-11-10 起打開）：還沒救下、還沒收養的那一段換季重新遇見（features/guard actions.on_season_start，設計稿照推薦）；這裡只驗「帶不帶」，清掉那一段在 features/guard/tests
    c.config.guard.enabled = False
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
    # checkin（全部拆包第 30 批）：新季第一次同步會自動簽第 1 天（簽到開著），checkin_days 就不是預設的空值；擺局面時關掉，斷言不動
    c.config.checkin.enabled = False
    next_season(c, world, game)
    for name in feature.player_fields:
        now = getattr(game.state.player, name)
        if name in feature.carried:
            assert now == before[name], name
        else:
            assert now == fields[name].get_default(call_default_factory=True), name


# core_world（全部拆包第 25 批「世界層掛鉤」；計畫 docs/superpowers/plans/2026-11-05-世界層掛鉤-第25批.md 1.4、2.4、Task 4）
def test_the_core_and_the_packages_fill_every_world_slot_exactly_once():
    """世界層的每一個位置：核心代叫的格（world.py、sqlite_world.py 裡那幾張 {格: 函式}；收季那一格核心沒有，寫 {}）與包登記的格
    （Feature.world()）合起來剛好是 WORLD_ORDER 上的格、沒有重疊——不然 world_run 會叫包的那一份、核心那一份默默不跑，或那一格誰都不跑。
    包登記的就是計畫 2.4 那五格；每一個位置照 FEATURES 問都問得出來（world_hooks 不丟 ValueError）。"""
    from tianxia import sqlite_world, world

    core = {
        "step": world._STEP_CORE, "week": world._WEEK_CORE, "day": world._DAY_CORE, "start": world._START_CORE, "close": {},
        "muster": world._MUSTER_CORE, "open": sqlite_world.SqliteWorldStore._open_core(), "retire": sqlite_world._RETIRE_CORE,
        "next": sqlite_world.SqliteWorldStore._next_core(),
        "life": {},  # core_world2（全部拆包第 40 批）：figure_life.tick 設宴那一格核心不代叫
    }
    owners = {(hook.at, hook.slot): f.name for f in FEATURES for hook in f.world()}
    assert len(owners) == sum(len(f.world()) for f in FEATURES)  # 同一格不會有兩包
    assert owners == {("step", "feast"): "feast", ("step", "yuedan"): "figure_acts", ("close", "arena"): "bout",
                      ("muster", "generals"): "battle", ("next", "inscriptions"): "explore",
                      ("muster", "works"): "stamina_plays",  # 全部拆包第 39 批
                      ("life", "feast"): "feast",  # core_world2（全部拆包第 40 批）
                      # 全部拆包第 27 批：玉璽包登記五格（原本核心代叫 world._MUSTER_CORE、sqlite_world 的 _open_core、_next_core、_RETIRE_CORE 那幾格）
                      ("muster", "seal"): "seal", ("open", "seal.cache"): "seal", ("next", "seal.mandate"): "seal",
                      ("next", "seal.cache"): "seal", ("retire", "seal"): "seal",
                      # 全部拆包第 45 批：懸賞榜包登記四格（原本核心代叫 world._STEP_CORE、_WEEK_CORE、_DAY_CORE、_START_CORE 那幾格）
                      ("step", "bounties"): "bounties", ("week", "bounties"): "bounties", ("day", "bounties"): "bounties", ("start", "bounties"): "bounties",
                          # 酒肆題壁跨季（Joy 2026-11-10「可以 按照建議」）
                          ("next", "tavern_walls"): "tavern"}
    assert set(core) == set(features_core.WORLD_ORDER)
    for at, order in features_core.WORLD_ORDER.items():
        own = set(features_core.world_hooks(at))
        assert own == {slot for (where, slot) in owners if where == at}, at
        assert not own & set(core[at]) and own | set(core[at]) == set(order), at
    # 週初、每天那兩串照表建、一格一個函式（season_events 照串列的順序叫）
    assert len(world.WEEK_HOOKS) == len(features_core.WORLD_ORDER["week"]) and len(world.DAY_HOOKS) == len(features_core.WORLD_ORDER["day"])


# shell_web（全部拆包第 66 批；計畫 docs/superpowers/plans/2026-11-06-網頁殼化-第66批.md 第四節）
def test_the_core_and_the_packages_take_every_status_slot_exactly_once(monkeypatch):
    """真的 FEATURES 登記的格＋核心、殼傳進 status_run 的格＝STATUS_ORDER，沒有重疊——不然 status_run 會叫包的那一份、核心那一份變死碼；少一格畫面就少鍵。"""
    import server

    real = features_core.status_run
    core: dict[str, set[str]] = {}

    def spy(table, slots, frame, ctx):
        core[table] = set(slots)
        return real(table, slots, frame, ctx)

    monkeypatch.setattr(features_core, "status_run", spy)
    view = server.main_view(_game())
    assert list(view)[:5] == ["status", "quest", "scene", "art", "options"]
    from tianxia.features.admin import routes as admin_routes  # noqa: PLC0415  管理頁那一張不在 main_view 裡（第二輪第 90 批）

    admin_view = admin_routes.admin_choices(server, _game())
    assert list(admin_view)[:2] == ["phase", "battles"]
    assert core.keys() == features_core.STATUS_ORDER.keys()
    for table, order in features_core.STATUS_ORDER.items():
        own = set(features_core.status_hooks(table))
        assert not own & core[table] and set(order) <= own | core[table], table  # 表外的格是包接在表尾的（第二輪第 74 批），這裡只管表上的一格不少
