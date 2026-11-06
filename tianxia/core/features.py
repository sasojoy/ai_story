"""功能包的掛鉤（開發規範手冊 3.3）與核心照 FEATURES 彙整（registry.py 的清單，有順序）。

一個功能一包（tianxia/features/<包>/）；核心在幾個大家都插一段的地方照清單依序問每一包。
兩種掛鉤看 enabled 的方式不一樣（手冊 3.3 寫「關著的包一個掛鉤都不叫」，指的是第一種；PM 10/31 認可，3.3 由 PM 補註）：
- 遊戲當下的（options、menu、choose、status、on_sync、on_day、on_season_*、on_drop_stale、bot_pick）：每一次先問 enabled(ctx)，
  關著的包一個都不叫（tests/core/test_contract_core.py、test_contract_features.py 守）。
- 殼啟動、載入內容時的（routes、admin_tools、threads、check_content、bot_always，與宣告的 web、content）：那時候還沒有 ctx（沒有角色、
  開關可能在季中被管理者切換），所以不看 enabled、登記的包全部照掛：路由與管理者工具由各自的 gate 在關著時回 404（搬包之前
  商城在 server 裡也是照掛再 404）、內容照驗（檔案寫壞了早點知道）、永遠按得下去的前綴照排除（關著的包選單上本來就沒有它們）。

| 掛鉤 | 核心在哪裡問 |
|---|---|
| enabled(ctx) | 每一個彙整之前 |
| options(ctx) | Game._stamina_play_options（「此地還能做」裡，體力玩法、護衛之後、盤算之前；序章裡、休季不問） |
| menu(ctx) | Game._everyday_options：這一包此刻接管整個選單（坐在宴席上、店開著那一類）；第一個不是 None 的算。**手冊 3.3 表外**（見下） |
| prep(ctx) | Game._season_prep：開季準備卡（企劃者 2026-11-05），挑完成長配比之後這一包此刻接管整個選單，排在事件（開局三選一）前面；第一個不是 None 的算。**手冊 3.3 表外**（傳承的識海；跟 menu 差在位置：menu 在事件之後） |
| choose(ctx, kind, arg) | Game.choose 建這一下的紀錄（Draft）之前：只吃自己前綴的 id，吃不到回 None，核心問下一包 |
| status(ctx) | Game.feature_status → server.main_view（合進江湖畫面的頂層，例：商城的入口 main.mall） |
| on_sync(ctx, elapsed)、on_day(ctx) | Game.sync（elapsed 是這一次補算的自己的秒數；on_day 是回體丹那一天換了：照 _pill_day，含快轉推過的 advanced_real，所以 Game.advance 跨過 00:00 也叫） |
| on_season_end(ctx)、on_season_start(ctx, old) | Game._reset_player_for_new_season（舊的那一季要丟之前；新的存檔接上之後、開場那一則之前） |
| on_drop_stale(ctx) | Game._drop_stale_references 最後 |
| bot_pick(ctx, option)、bot_always | bot_policy.score（假人看到這一顆的分數，None 是不按）；bot.pick 排除的前綴（永遠按得下去的） |
| admin_tools(shell)、routes(shell) | server：/api/do/{op} 的管理者工具、掛路由（shell 是 server 模組） |
| threads(shell) | server.main（殼開、測試停：只有 main 叫 start_threads，測試不叫；不回東西。全部拆包第 52 批，開給戰記與第 53 批的看守） |
| check_content(content, need)、web、content | content.validate（關著的包照驗）；index.html 的檔；content.py 讀的檔。check_content **手冊 3.3 表外**（見下） |

比手冊 3.3「就這幾個，不多開」那張表多開了兩個（第 1 階開的，PM 10/31 認可，理由照下面；手冊 3.3 由 PM 補；之後再要加先過 PM）：
- menu：現行的 _everyday_options 裡一包有兩個位置——接管整個選單（坐在席上、店開著……十幾樣都是）與接在「此地還能做」裡（options），
  一個 options 擺不下兩個位置。
- check_content：取代原本的 content.check_mall（載入時驗商品）。核心的 content.py 不能 import 包，3.3 的 content 那一列只宣告
  content.py 讀哪些檔、沒有「驗」，所以開一個讓包自己驗。

**接縫掛鉤**（全部拆包第 11 批「核心收接縫」開的；計畫 docs/superpowers/plans/2026-11-01-核心收接縫.md）：第 1～10 批把功能搬進包時，
先後會影響結果的接縫留在原位直接叫包（邊界測試的 GAME_DIRECT、GAME_DELEGATE_CALLERS）。這一批在原本那一行的位置開掛鉤：核心在那一行
照清單問每一包，現在每一個位置都只有一包回答，順序一字不變；之後別的包接同一個位置，照 FEATURES 的順序排在前後。每一個位置夾在哪兩行
之間寫在計畫 1.3。看不看 enabled：給選項的三樣（Shop.menu、Shop.entry、Verb.cell）照遊戲當下的掛鉤先問，關著的包不給選項；其餘的
不問——原位那幾行本來就不看包的開關（酒肆的三個 deliver、決戰補送、收店、標題……），包把原位的判斷照搬過去。

| 掛鉤 | 核心在哪裡問 |
|---|---|
| on_due(ctx) | Game.world_tick、sync、advance 結算到時的事那一行（約戰） |
| on_away(ctx, away_from) | Game.sync 補算完本人下線那一段之後（殺手找上門） |
| deliver_results(ctx) | Game.sync 收場補送那一格：時刻表大事之後、絕學定名補送之前（決戰：先補份量快照〔全部拆包第 8 批把原本緊接著的前一行併進來〕、再補送；玉璽：碎片的事〔全部拆包第 27 批把原本緊接著的下一行併進來〕） |
| deliver_notices(ctx) | Game.sync 別人捎來的那一格：護衛補帳之後、領地爭奪換天之前（酒肆的風聲、殺手單、託付留意） |
| choose_unlisted(ctx, option_id) | Game.choose 查選單之前：不在選單上的動作（約戰的 sortie:*） |
| after_action(ctx) | Game.choose 最後：本人做完一件事（殺手檢查） |
| on_own_turn(ctx) | Game.own_turn_checks 最前面：本人這一輪（商城的封測發放） |
| scene(ctx)、scene_over(ctx) | Game._own_scene_text 擂台之後（坐在宴席上）；Game.scene_text 最前面（蓋在畫面上的戰場） |
| record_detail(ctx, record) | Game.battle_detail：戰報頁那一筆（決戰照 battles 表重讀完整戰況） |
| on_season_close(ctx, reread) | Game.admin_end_season 讀回收季那一份季之後、補大事之前（reread=False）；Game.admin_next_season 休季時、開下一季之前（reread=True：收兵之前讀回手上那一份季）——收季的收兵（決戰；全部拆包第 8 批） |
| shops()（Shop） | 店面登記：店裡那一串（_everyday_options）、進店那一顆、哪一間開著（_shop_open）、動身收店（_depart）、此地不開了收店（sync、_drop_stale_references） |
| verbs()（Verb） | act 子動詞：_act 最前面、_action_title、行動列那一格（_everyday_options）、行動列底下那一行（action_notes）、只打開一張卡的回話（choose）；
  這一下打哪一路（_fight_squad 最前面：大場面判讀問；sortie：全部拆包第 17 批多開的一格 squad） |
| world()（WorldHook） | 世界層的格（core_world：全部拆包第 25 批）：world.advance_world_state 每一步、season_events 的週初與每天、settle_season_start、
  end_season、_open_claimed；sqlite_world 的開季與換季；figure_life.tick 每一位對話人物（life，第 40 批）。照檔尾那張寫死的順序表 WORLD_ORDER 一格一格叫（包與還沒成包的舊模組穿插），不問 enabled |
| effects()（EffectHook） | 一則效果的格（core_effects：全部拆包第 32 批）：rules.apply_effect 從頭到尾一段一格，照檔尾寫死的順序表 EFFECT_ORDER 一格一格叫
  （每一個效果欄位歸哪一格寫在 EFFECT_FIELDS），不問 enabled |
| defection()（DefectHook） | 叛投那一刻的格（core_effects）：defection.clear_progress（clear）、defection.defect（leave、stranded）、陣營包
  defect_actions.defect_step 確定那一支（after；第 35 批前是 Game._defect_step）四個位置，照檔尾寫死的順序表 DEFECT_ORDER 一格一格叫（各包清自己的進度），不問 enabled |
| bus()（BusHook） | 一種事件的格（core_eventbus：全部拆包第 26 批）：ctx.publish 的七個發布點（打贏一場、出門一趟、舊探索、抵達、截殺打贏、
  決戰收場），照檔尾寫死的順序表 BUS_ORDER 一格一格叫，不問 enabled |
| steps()（StepHook） | 「你這一步」的格（core_step：全部拆包第 36 批）：本週卡「眼下要事」的候選（weekcard._steps 叫 step.items）與四勝利開著時補目標
  （step.finish 照每一件 _ref 的第一個字找回那一格的 place），照檔尾寫死的順序表 STEP_ORDER 一格一格叫（包登記自己那一格、懸賞榜兩格由
  step._STEP_CORE 核心代叫），不問 enabled |

ctx 第一階就是 Game；功能包只准叫 services.py 那張清單上的方法。
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from .option import Option

if TYPE_CHECKING:
    from ..engine import Game
    from ..models import Content, Location, Squad
    from ..state import BattleRecord, GameState


@dataclass(frozen=True)
class Shop:
    """店面登記（第 11 批）：一間開在城裡、坐進去選單整個換成那間店的店。核心在七間店共用的那幾處照清單問（舊的六間還在 engine，
    搬成包的店接在它們後面）。每一樣都拿 ctx（Game）。"""

    key: str  # Game._shop_open 回的字（店面那一頁畫哪一間；server 的 main_view 照它）
    inside: Callable[[Any], bool]  # 此刻坐在店裡（picking_*）
    here: Callable[[Any], bool]  # 這裡此刻開著這間店（開關、地點、不在路上……）
    close: Callable[[Any], None]  # 收起來（掌櫃那一句一併清）
    menu: Callable[[Any], list[Option]]  # 坐在店裡時的整個選單
    entry: Callable[[Any], Option | None]  # 「此地還能做」裡進店那一顆；這裡不開門是 None


@dataclass(frozen=True)
class Verb:
    """act:<verb> 那一格的主人（act 子動詞；第 11 批先開給主人已經成包的三格，總表第 57 批其餘的接上同一張表）。每一樣都可以是 None，
    回 None 也一樣：照舊由核心做（核心那一支還在：舊探索、遊歷……）。"""

    verb: str
    run: Callable[[Any, Any], list[str] | None] | None = None  # Game._act 最前面：按下去（ctx, prepared）
    title: Callable[[Any], str | None] | None = None  # Game._action_title：這一下江湖紀錄的整個標題
    cell: Callable[[Any, Any, int, bool], list[Option] | None] | None = None  # 行動列那一格（ctx, 地點, 體力, 寫不寫勝算）；[] 是接了、一顆都沒有
    note: Callable[[Any, Any], str | None] | None = None  # 行動列底下那一行（ctx, 地點）
    picks: tuple[str, ...] = ()  # 按了只打開一張卡的回話：不算做過、不寫江湖紀錄（Game.choose 的 picked_only、quiet）
    # sortie（全部拆包第 17 批「出陣三」多開的一格；第 11 批計畫第五節第 1 條預告的「這一下打不打仗」）：Game._fight_squad 最前面，
    # 這一格按下去會打哪一路（大場面判讀、鎖外 A 段與鎖內 C 段的重驗都問它）；不打仗是 None（核心照舊往下，act: 那幾格往下也是 None）
    squad: Callable[[Any], Squad | None] | None = None


@dataclass(frozen=True)
class Outcome:
    """choose 接走一顆選項：title 是這一下江湖紀錄的標題（核心在動作之前先拿，同 Game._action_title），run 做那個動作、回那幾句話。"""

    title: str
    run: Callable[[], list[str]]


@dataclass(frozen=True)
class AdminTool:
    """設定頁的一樣管理者工具（/api/do/{op}）：gate 在這一包關著時丟 404（先於登入的檢查），run(game, body) 做、回那幾句；
    paused_ok 是賽季時鐘暫停中照做（帳跟季無關的那一類）。"""

    gate: Callable[[], None]
    run: Callable[[Any, dict], list[str]]
    paused_ok: bool = True


class FeatureHooks(Protocol):
    """一包要回答的（手冊 3.3）。簽名第一階定的；比 3.3 的表多兩個（menu、check_content，見模組的說明，PM 10/31 認可）。
    之後要加先看這一張表，不多開；真的要加先過 PM。"""

    name: str  # 包名（資料夾名）
    # 選項 id 的前綴（「feast」→ feast:join:3）；沒有選項的包是 None。一包兩三個前綴寫 tuple（第 11 批，PM 定：單挑、銀兩出口、有所感、陣營都會用到），
    # 分派照清單、照 tuple 的順序找第一個對上的（owner_of）；兩包不能宣告同一個前綴（tests/core/test_contract_features.py）
    prefix: str | tuple[str, ...] | None
    web: tuple[str, ...]  # web/ 底下這一包的檔（index.html 照舊順序載入；第 3 階才由伺服器照它生成）
    content: tuple[str, ...]  # content/ 底下這一包的檔（第 1、2 階 content.py 照舊全部讀）
    bot_always: tuple[str, ...]  # 永遠按得下去的選項前綴：整季機器人（bot.pick）不按，不然「沒得按就推進時間」的訊號會失效
    player_fields: tuple[str, ...]  # 這一包認領的 PlayerState 欄位（3.5；README 照列）
    carried: tuple[str, ...]  # 上面那些裡換季照帶走的；其餘換季跟著新角色重來（契約測試照它驗）

    def enabled(self, ctx: Game) -> bool: ...
    def options(self, ctx: Game) -> list[Option]: ...
    def menu(self, ctx: Game) -> list[Option] | None: ...
    def prep(self, ctx: Game) -> list[Option] | None: ...
    def choose(self, ctx: Game, kind: str, arg: str) -> Outcome | None: ...
    def status(self, ctx: Game) -> dict: ...
    def on_sync(self, ctx: Game, elapsed: float) -> None: ...
    def on_day(self, ctx: Game) -> None: ...
    def on_season_end(self, ctx: Game) -> None: ...
    def on_season_start(self, ctx: Game, old: GameState) -> None: ...
    def on_drop_stale(self, ctx: Game) -> None: ...
    def bot_pick(self, ctx: Game, option: Option) -> float | None: ...
    def admin_tools(self, shell: Any) -> dict[str, AdminTool]: ...
    def routes(self, shell: Any) -> Any: ...
    def check_content(self, content: Content, need: Callable[[bool, str], None]) -> None: ...
    # ── 接縫掛鉤（第 11 批；不問 enabled，Shop.menu、Shop.entry、Verb.cell 除外）──
    def on_due(self, ctx: Game) -> None: ...
    def on_away(self, ctx: Game, away_from: float) -> None: ...
    def deliver_results(self, ctx: Game) -> None: ...
    def deliver_notices(self, ctx: Game) -> None: ...
    def choose_unlisted(self, ctx: Game, option_id: str) -> list[str] | None: ...
    def after_action(self, ctx: Game) -> list[str]: ...
    def on_own_turn(self, ctx: Game) -> None: ...
    def scene(self, ctx: Game) -> str | None: ...
    def scene_over(self, ctx: Game) -> tuple[str, bool] | None: ...
    def record_detail(self, ctx: Game, record: BattleRecord) -> BattleRecord | None: ...
    # battle（全部拆包第 8 批：收季的收兵；第 11 批 PM 認定第 7 條「兩段要一起進收季的位置」）
    def on_season_close(self, ctx: Game, reread: bool) -> None: ...
    def shops(self) -> tuple[Shop, ...]: ...
    def verbs(self) -> tuple[Verb, ...]: ...
    # core_world（全部拆包第 25 批：世界層的格，位置與先後在 WORLD_ORDER；不問 enabled）
    def world(self) -> tuple[WorldHook, ...]: ...
    # core_effects（全部拆包第 32 批：一則效果的格與叛投那一刻的格，先後在 EFFECT_ORDER、DEFECT_ORDER；不問 enabled）
    def effects(self) -> tuple[EffectHook, ...]: ...
    def defection(self) -> tuple[DefectHook, ...]: ...
    # core_eventbus（全部拆包第 26 批：一種事件的格，先後在 BUS_ORDER；不問 enabled）
    def bus(self) -> tuple[BusHook, ...]: ...
    # core_step（全部拆包第 36 批：「你這一步」的格，先後在 STEP_ORDER；不問 enabled）
    def steps(self) -> tuple[StepHook, ...]: ...
    # tale（全部拆包第 52 批：殼啟動時開這一包的背景執行緒；只有 server.main 叫，測試不叫；不問 enabled，殼啟動還沒有 ctx）
    def threads(self, shell: Any) -> None: ...


class Feature:
    """FeatureHooks 的預設值：什麼都不做、一個選項都不給。每一包繼承它、只改用得到的那幾個。"""

    name = ""
    prefix: str | tuple[str, ...] | None = None
    web: tuple[str, ...] = ()
    content: tuple[str, ...] = ()
    bot_always: tuple[str, ...] = ()
    player_fields: tuple[str, ...] = ()
    carried: tuple[str, ...] = ()

    def enabled(self, ctx: Game) -> bool:
        return False

    def options(self, ctx: Game) -> list[Option]:
        return []

    def menu(self, ctx: Game) -> list[Option] | None:
        return None

    def prep(self, ctx: Game) -> list[Option] | None:
        return None

    def choose(self, ctx: Game, kind: str, arg: str) -> Outcome | None:
        return None

    def status(self, ctx: Game) -> dict:
        return {}

    def on_sync(self, ctx: Game, elapsed: float) -> None:
        return None

    def on_day(self, ctx: Game) -> None:
        return None

    def on_season_end(self, ctx: Game) -> None:
        return None

    def on_season_start(self, ctx: Game, old: GameState) -> None:
        return None

    def on_drop_stale(self, ctx: Game) -> None:
        return None

    def bot_pick(self, ctx: Game, option: Option) -> float | None:
        return None

    def admin_tools(self, shell: Any) -> dict[str, AdminTool]:
        return {}

    def routes(self, shell: Any) -> Any:
        return None

    def threads(self, shell: Any) -> None:
        return None

    def check_content(self, content: Content, need: Callable[[bool, str], None]) -> None:
        return None

    def on_due(self, ctx: Game) -> None:
        return None

    def on_away(self, ctx: Game, away_from: float) -> None:
        return None

    def deliver_results(self, ctx: Game) -> None:
        return None

    def deliver_notices(self, ctx: Game) -> None:
        return None

    def choose_unlisted(self, ctx: Game, option_id: str) -> list[str] | None:
        return None

    def after_action(self, ctx: Game) -> list[str]:
        return []

    def on_own_turn(self, ctx: Game) -> None:
        return None

    def scene(self, ctx: Game) -> str | None:
        return None

    def scene_over(self, ctx: Game) -> tuple[str, bool] | None:
        return None

    def record_detail(self, ctx: Game, record: BattleRecord) -> BattleRecord | None:
        return None

    def on_season_close(self, ctx: Game, reread: bool) -> None:
        return None

    def shops(self) -> tuple[Shop, ...]:
        return ()

    def verbs(self) -> tuple[Verb, ...]:
        return ()

    def world(self) -> tuple[WorldHook, ...]:
        return ()

    def effects(self) -> tuple[EffectHook, ...]:
        return ()

    def defection(self) -> tuple[DefectHook, ...]:
        return ()

    def bus(self) -> tuple[BusHook, ...]:
        return ()

    def steps(self) -> tuple[StepHook, ...]:
        return ()

    def __repr__(self) -> str:
        return f"<功能包 {self.name}>"


# ── 核心照清單問（registry 延後 import：包的 __init__ 要 import 這一份的 Feature）──


def registered() -> list[Feature]:
    """登記的全部包（有順序；關著的也在）。"""
    from .registry import FEATURES  # noqa: PLC0415

    return FEATURES


def active(ctx: Game) -> list[Feature]:
    """此刻開著的包（照清單的順序）。"""
    return [f for f in registered() if f.enabled(ctx)]


def options(ctx: Game) -> list[Option]:
    out: list[Option] = []
    for f in active(ctx):
        out += f.options(ctx)
    return out


def menu(ctx: Game) -> list[Option] | None:
    for f in active(ctx):
        got = f.menu(ctx)
        if got is not None:
            return got
    return None


def prep(ctx: Game) -> list[Option] | None:
    for f in active(ctx):
        got = f.prep(ctx)
        if got is not None:
            return got
    return None


def choose(ctx: Game, kind: str, arg: str) -> Outcome | None:
    for f in active(ctx):
        got = f.choose(ctx, kind, arg)
        if got is not None:
            return got
    return None


def status(ctx: Game) -> dict:
    out: dict = {}
    for f in active(ctx):
        out.update(f.status(ctx))
    return out


def on_sync(ctx: Game, elapsed: float) -> None:
    for f in active(ctx):
        f.on_sync(ctx, elapsed)


def on_day(ctx: Game) -> None:
    for f in active(ctx):
        f.on_day(ctx)


def on_season_end(ctx: Game) -> None:
    for f in active(ctx):
        f.on_season_end(ctx)


def on_season_start(ctx: Game, old: GameState) -> None:
    for f in active(ctx):
        f.on_season_start(ctx, old)


def on_drop_stale(ctx: Game) -> None:
    for f in active(ctx):
        f.on_drop_stale(ctx)


def prefixes(feature: Feature) -> tuple[str, ...]:
    """這一包的選項前綴（Feature.prefix 收字串或 tuple，第 11 批）：一律攤成 tuple，沒有前綴是空的。"""
    p = feature.prefix
    if p is None:
        return ()
    return (p,) if isinstance(p, str) else tuple(p)


def owner_of(option_id: str) -> Feature | None:
    """哪一包的選項（照 id 的前綴）；不是任何一包的是 None。照 FEATURES 的順序、每一包照它的前綴依序找，第一個對上的算
    （兩包不能宣告同一個前綴，契約測試守，所以頂多一個對得上）。"""
    kind = option_id.partition(":")[0]
    return next((f for f in registered() if kind in prefixes(f)), None)


def bot_pick(ctx: Game, option: Option) -> tuple[bool, float | None]:
    """(是不是哪一包的選項, 假人的分數)：是的話照那一包的 bot_pick（關著的包不叫，回 None＝不按）。"""
    owner = owner_of(option.id)
    if owner is None:
        return False, None
    return True, owner.bot_pick(ctx, option) if owner.enabled(ctx) else None


def bot_always() -> tuple[str, ...]:
    """各包宣告永遠按得下去的前綴（bot.pick 排除；關著的包也算，選單上本來就沒有它們）。"""
    return tuple(p for f in registered() for p in f.bot_always)


def admin_tools(shell: Any) -> dict[str, AdminTool]:
    """各包的管理者工具（/api/do/{op}；關著的包也列，由 gate 擋 404）。兩包同名丟例外。"""
    out: dict[str, AdminTool] = {}
    for f in registered():
        for op, tool in f.admin_tools(shell).items():
            if op in out:
                raise ValueError(f"管理者工具 {op} 兩包都有")
            out[op] = tool
    return out


def routers(shell: Any) -> list[Any]:
    """各包的路由（APIRouter；殼照清單的順序掛）。"""
    return [r for f in registered() if (r := f.routes(shell)) is not None]


def start_threads(shell: Any) -> None:
    """各包的背景執行緒（殼開、測試停）：只有 server.main 叫，測試不叫它，停靠 tests/conftest.py 收尾認殼上的名字（全部拆包第 52 批）。
    照清單問登記的每一包、不看 enabled：殼啟動還沒有 ctx。"""
    for f in registered():
        f.threads(shell)


def check_content(content: Content, need: Callable[[bool, str], None]) -> None:
    """載入內容時各包的驗證（content.validate；關著的包照驗：檔案寫壞了早點知道）。"""
    for f in registered():
        f.check_content(content, need)


def web_files() -> list[str]:
    """各包登記的網頁檔（web/ 底下，照 FEATURES 的順序）。第 3 階才由伺服器照它生成 index.html；在那之前 index.html 與
    tests/kit/webharness.APP_FILES 是手寫的，tests/core/test_contract_features.py 照這一份對它們，店面的 CSS 測試照它讀包的樣式。"""
    return [name for f in registered() for name in f.web]


# ── 接縫掛鉤（第 11 批；計畫 docs/superpowers/plans/2026-11-01-核心收接縫.md 1.3 寫每一個在哪兩行之間）──
# 不問 enabled 的照清單問登記的每一包（registered）：原位那幾行本來就不看包的開關，包照搬原位的判斷。
# 給選項的三樣（shop_menu、shop_entries、act_cell）照遊戲當下的掛鉤問開著的包（active）。


def on_due(ctx: Game) -> None:
    """到時的結算（world_tick、sync、advance 原本叫約戰結算的那一行）。"""
    for f in registered():
        f.on_due(ctx)


def on_away(ctx: Game, away_from: float) -> None:
    """本人補算完下線那一段（sync；有上一次同步才叫，away_from 是上一次同步的現實秒）。"""
    for f in registered():
        f.on_away(ctx, away_from)


def deliver_results(ctx: Game) -> None:
    """收場補送（sync：時刻表大事之後、絕學定名補送之前；決戰包在這一格先補份量快照，全部拆包第 8 批；玉璽包接著補碎片的事，第 27 批）。"""
    for f in registered():
        f.deliver_results(ctx)


def deliver_notices(ctx: Game) -> None:
    """別人捎來的（sync：護衛補帳之後、領地爭奪換天之前）。"""
    for f in registered():
        f.deliver_notices(ctx)


def choose_unlisted(ctx: Game, option_id: str) -> list[str] | None:
    """不在選單上的動作（Game.choose 查選單、建紀錄之前）：第一個不是 None 的算；都不接是 None，核心照舊查選單。"""
    for f in registered():
        got = f.choose_unlisted(ctx, option_id)
        if got is not None:
            return got
    return None


def after_action(ctx: Game) -> list[str]:
    """本人做完一件事（Game.choose 最後：記下陣營之後、存回季之前）：各包的回話照清單串起來。"""
    out: list[str] = []
    for f in registered():
        out += f.after_action(ctx)
    return out


def on_own_turn(ctx: Game) -> None:
    """本人這一輪（Game.own_turn_checks 最前面，暫停的檢查之前：暫停中照做）。"""
    for f in registered():
        f.on_own_turn(ctx)


def scene(ctx: Game) -> str | None:
    """自己眼前的場景卡（Game._own_scene_text：擂台之後、有所感之前）：第一個不是 None 的算。"""
    for f in registered():
        got = f.scene(ctx)
        if got is not None:
            return got
    return None


def scene_over(ctx: Game) -> tuple[str, bool] | None:
    """蓋在畫面上的（Game.scene_text 最前面）：(那一段, 要不要整個取代自己眼前的事)；第一個不是 None 的算。"""
    for f in registered():
        got = f.scene_over(ctx)
        if got is not None:
            return got
    return None


def record_detail(ctx: Game, record: BattleRecord) -> BattleRecord:
    """戰報頁那一筆（Game.battle_detail 找到之後）：第一個不是 None 的換掉它；都不換照原本那一筆。"""
    for f in registered():
        got = f.record_detail(ctx, record)
        if got is not None:
            return got
    return record


# battle（全部拆包第 8 批）
def on_season_close(ctx: Game, reread: bool = False) -> None:
    """收季的收兵（Game.admin_end_season：讀回收季那一份季之後、補大事之前；Game.admin_next_season：休季時、開下一季之前，reread=True）：
    沒打完的仗收起來、不算勝負。不問 enabled（原位那兩段本來就不看包的開關）。"""
    for f in registered():
        f.on_season_close(ctx, reread)


def _shops(ctx: Game, *, gated: bool) -> list[Shop]:
    return [shop for f in (active(ctx) if gated else registered()) for shop in f.shops()]


def shop_menu(ctx: Game) -> list[Option] | None:
    """坐在店裡時的整個選單（Game._everyday_options：舊的六間店之後、伏筆答題之前）。給選項：只問開著的包。"""
    for shop in _shops(ctx, gated=True):
        if shop.inside(ctx):
            return shop.menu(ctx)
    return None


def shop_entries(ctx: Game) -> list[Option]:
    """「此地還能做」裡進店的那幾顆（Game._everyday_options：馬市之後、擂台入口之前）。給選項：只問開著的包。"""
    return [option for shop in _shops(ctx, gated=True) if (option := shop.entry(ctx)) is not None]


def shop_open(ctx: Game) -> str | None:
    """哪一間店開著（Game._shop_open：舊的六間店之後）：坐在店裡、這裡也還開著是那一間的 key；坐在店裡、這裡已經不開門了是 None。"""
    for shop in _shops(ctx, gated=False):
        if shop.inside(ctx):
            return shop.key if shop.here(ctx) else None
    return None


def close_shops(ctx: Game) -> None:
    """動身了：坐著的店收起來（Game._depart：收擂台之後）。"""
    for shop in _shops(ctx, gated=False):
        if shop.inside(ctx):
            shop.close(ctx)


def drop_shops(ctx: Game) -> None:
    """此地不開這間店了（開關關了、人被挪走、內容改版）：坐著的收起來（Game.sync、_drop_stale_references：收擂台之後）。"""
    for shop in _shops(ctx, gated=False):
        if shop.inside(ctx) and not shop.here(ctx):
            shop.close(ctx)


def _verbs(ctx: Game | None, verb: str) -> list[Verb]:
    features = registered() if ctx is None else active(ctx)
    return [v for f in features for v in f.verbs() if v.verb == verb]


def act(ctx: Game, verb: str, prepared: Any) -> list[str] | None:
    """act:<verb> 按下去（Game._act 最前面）：主人接了回那幾句；都不接是 None，核心照舊。"""
    for v in _verbs(None, verb):
        got = v.run(ctx, prepared) if v.run is not None else None
        if got is not None:
            return got
    return None


def act_title(ctx: Game, verb: str) -> str | None:
    """act:<verb> 那一下江湖紀錄的標題（Game._action_title 那張表之前；表照 arg 查、不看 kind，這裡也一樣）。"""
    for v in _verbs(None, verb):
        got = v.title(ctx) if v.title is not None else None
        if got is not None:
            return got
    return None


def act_cell(ctx: Game, verb: str, loc: Location, cost: int, odds: bool) -> list[Option] | None:
    """行動列那一格（Game._everyday_options）：開著的主人接了回那幾顆（[] 是接了、一顆都沒有）；都不接是 None，核心照舊。給選項：只問開著的包。"""
    for v in _verbs(ctx, verb):
        got = v.cell(ctx, loc, cost, odds) if v.cell is not None else None
        if got is not None:
            return got
    return None


def act_note(ctx: Game, verb: str, loc: Location) -> str | None:
    """行動列底下那一行（Game.action_notes）：主人接了回那一句（可以是空字串）；都不接是 None，核心照舊。"""
    for v in _verbs(None, verb):
        got = v.note(ctx, loc) if v.note is not None else None
        if got is not None:
            return got
    return None


def pick_replies(verb: str | None = None) -> tuple[str, ...]:
    """按了只打開一張卡的回話（Verb.picks；Game.choose 的 picked_only 照 verb 認、quiet 不看 verb）。"""
    return tuple(r for f in registered() for v in f.verbs() if verb is None or v.verb == verb for r in v.picks)


# sortie（全部拆包第 17 批「出陣三」）


def act_squad(ctx: Game, verb: str) -> Squad | None:
    """act:<verb> 按下去會打哪一路（Game._fight_squad 最前面；Verb.squad）：主人回那一路；不打仗、都不接是 None，核心照舊往下。
    不問 enabled（原位那一支本來就不看開關，同 run、title、note）。"""
    for v in _verbs(None, verb):
        got = v.squad(ctx) if v.squad is not None else None
        if got is not None:
            return got
    return None


# core_world（全部拆包第 25 批「世界層掛鉤」；計畫 docs/superpowers/plans/2026-11-05-世界層掛鉤-第25批.md 1.4、2.1）


@dataclass(frozen=True)
class WorldHook:
    """世界層的一格（Feature.world() 回一串）：核心在 at 那個位置照 WORLD_ORDER[at] 一格一格叫，輪到 slot 就叫 run。照 registered() 問、
    不看 enabled（原位那幾行本來就不看包的開關：宴客關著也照散席、擂台只看 arena_ranks.on，同第 11 批的接縫掛鉤）。run 的簽名照位置
    （WORLD_ORDER 底下那張）；包的 run 在叫的那一下才照模組屬性找自己的函式（monkeypatch 照樣有效）。"""

    at: str
    slot: str
    run: Callable[..., Any]


# 世界層的順序表：位置 → 那一個位置的格，照換成掛鉤之前一行一行的呼叫順序。順序就是行為（同一步裡先推誰、後推誰、亂數抽到的順序都算）。
# 包登記自己那一格（Feature.world()），其餘由核心代叫（world.py、sqlite_world.py 裡的一張 {格: 函式}：還沒成包、不在共用規則層的舊模組，
# 與核心自己的那幾格）。寫死在這裡、不照 FEATURES 的先後：同一個位置包與舊模組穿插（step 的宴客夾在人物行事與盤算之間、月旦評排最後；
# muster 的龍頭上陣排在屯糧與玉璽之後），照 FEATURES 只排得出「所有包擠在同一個位置」。之後舊模組成包只是那一格換主人，表不動。
# 改這張表先過 PM；tests/core/test_contract_core.py 逐字鎖住。
#
# 位置    核心在哪裡問                                                         run 的簽名                                   回傳
# step    world.advance_world_state 每一步：sim_tick 之後、季還沒收（季曆交界之前）  (vehicle, content, store, step)               bounties、figures.revive、seal_acts 的 list 接進訊息；其餘 None
# week    world.season_events 季曆跨進新的一週（WEEK_HOOKS，那一刻的大事之前）       (state, content, rng) -> list[str]           接
# day     world.season_events 21 天季跨進新的一天（DAY_HOOKS，週初那一串之後）       (state, content, rng) -> list[str]           接
# start   world.settle_season_start 第一季規則關著的季（季沒收）                     (state, content, rng) -> list[str]           接
# close   world.end_season：分級（_settle_tiers）之後、榜單之前                      (state, content, store) -> None              不接
# muster  world._open_claimed 開成之後（_open_battle 回了訊息）                       (store, content, definition, start, now)      接
# open    sqlite_world 開季那一刻（seed_first_season 自動開的、open_season）          (shared, content, now) -> None               不接（自動開的 now 是 None）
# retire  sqlite_world.next_season 換新季之前（首創之後、清奪璽單挑之前）             (shared, content, now, seen) -> bool         寫了上一季的江湖史就是 True
# next    sqlite_world.next_season 蓋上新的天機之後、挪開半夜之前                     (shared, content, now, old_season) -> None   不接
# life    figure_life.tick 每一輪每一位對話人物（_maybe_rally 之前；core_world2）      (state, content, cid, turn) -> None          不接
WORLD_ORDER: dict[str, tuple[str, ...]] = {
    "step": ("bounties", "figures.recover", "figures.revive", "seal_acts", "figure_life", "feast", "plans", "yuedan"),
    "week": ("seats", "orders", "bounties", "stances"),
    "day": ("orders", "bounties", "stances"),
    "start": ("bounties",),
    "close": ("arena",),
    "muster": ("front", "works", "seal", "generals"),
    "open": ("divine", "seal.cache"),
    "retire": ("seal",),
    "next": ("inscriptions", "divine", "seal.mandate", "seal.cache"),
    "life": ("feast",),  # core_world2（全部拆包第 40 批）：設宴，宴客包登記；核心不代叫
}


def world_hooks(at: str) -> dict[str, Callable[..., Any]]:
    """at 那個位置包登記的格 {slot: run}：照 registered()、不看 enabled。每一次都驗登記的全部格：表上沒有的格、同一格登記兩次（兩包或
    同一包）都丟 ValueError（tests/core/test_contract_core.py 守）。"""
    if at not in WORLD_ORDER:
        raise ValueError(f"世界層沒有 {at} 這個位置")
    own: dict[str, Callable[..., Any]] = {}
    for f in registered():
        for hook in f.world():
            if hook.slot not in WORLD_ORDER.get(hook.at, ()):
                raise ValueError(f"{f.name} 登記了世界層表上沒有的格 {hook.at}/{hook.slot}")
            if hook.at == at:
                if hook.slot in own:
                    raise ValueError(f"世界層的 {at}/{hook.slot} 登記了兩次（{f.name}）")
                own[hook.slot] = hook.run
    return own


def world_run(at: str, core: dict[str, Callable[..., Any]], *args: Any,
              hooks: dict[str, Callable[..., Any]] | None = None) -> list[Any]:
    """照 WORLD_ORDER[at] 走每一格：包登記了叫包的，沒有叫 core 那一份（核心代叫的格）；兩邊都沒有（那一格的包沒登記：契約測試換掉
    FEATURES 時）跳過。回每一格的回傳值（照順序、跳過的不算）：接不接由呼叫端照位置決定，跟換之前一行一行寫的一樣。
    hooks 是呼叫端先取好的 world_hooks(at)（advance_world_state 一次推進只取一次：FEATURES 在一次推進裡不會變）。
    core 寫了表上沒有的格丟 ValueError（打錯字的格不會默默不跑）。"""
    order = WORLD_ORDER[at]
    if not core.keys() <= set(order):
        raise ValueError(f"核心代叫了世界層 {at} 表上沒有的格 {sorted(core.keys() - set(order))}")
    own = world_hooks(at) if hooks is None else hooks
    out: list[Any] = []
    for slot in order:
        run = own.get(slot) or core.get(slot)
        if run is not None:
            out.append(run(*args))
    return out


# core_effects（全部拆包第 32 批「效果與叛投掛鉤」；計畫 docs/superpowers/plans/2026-11-06-效果與叛投掛鉤-第32批.md 1.2、1.3、2.1）


@dataclass(frozen=True)
class EffectHook:
    """一則效果的一格（Feature.effects() 回一串）：rules.apply_effect 照 EFFECT_ORDER 一格一格叫，輪到 slot 就叫 run(r)（r 是 rules.EffectRun），
    回這一格的那幾句（沒有是 []）。照 registered() 問、不看 enabled（原位不看包的開關：一條線關著也照記記號）。包的 run 在叫的那一下才照
    模組屬性找自己的函式（monkeypatch 照樣有效）。"""

    slot: str
    run: Callable[..., Any]


# 一則效果的分派順序（rules.apply_effect 從頭到尾一段一格，核心自己的段也在表上）：照換成掛鉤之前的先後。回話的先後、世界旗標與存檔寫入的先後
# 都算行為，格與格之間也有讀寫的先後（召見往下一段在晉升清召見之前、推大勢的一次性看立旗之前、碎片看這一下新立的旗標與江湖史那一句），所以寫死。
# 包登記自己那一格（Feature.effects()），其餘由 rules._EFFECT_CORE 代叫（核心自己的、共用規則層的、還沒成包的舊模組的〔標批號〕）。
# 改這張表先過 PM；tests/core/test_contract_core.py 逐字鎖住。
EFFECT_ORDER: tuple[str, ...] = (
    "text", "stats", "materials", "insights", "gear", "stamina", "affinity",
    "patron", "grain", "fs_fragments", "runic", "event_mods", "summons_next", "promote",
    "flags", "learn_skills", "join_sect", "leave_sect", "recruit", "trend", "world_flags", "marks",
    "foreshadow", "rumor", "chronicle", "shard", "story",
)
# 每一格認領哪幾個效果欄位（照效果欄位分派給主人）：併起來＝models.Effect 的欄位扣掉 apply_effect 不讀的 next_event、contribution，每一個欄位剛好一格。
# shard 不認領（讀 world_flags_add 新立的那一面與 chronicle）。
EFFECT_FIELDS: dict[str, tuple[str, ...]] = {
    "text": ("text",), "stats": ("stats",), "materials": ("materials",), "insights": ("insights",), "gear": ("gear",),
    "stamina": ("stamina",), "affinity": ("affinity",), "patron": ("patron",), "grain": ("donate_grain",),
    "fs_fragments": ("fs_fragments",), "runic": ("runic",), "event_mods": ("event_mods",), "summons_next": ("summons_next",),
    "promote": ("promote", "followers"), "flags": ("flags_add", "flags_remove"), "learn_skills": ("learn_skills",),
    "join_sect": ("join_sect",), "leave_sect": ("leave_sect",), "recruit": ("recruit",), "trend": ("trend",),
    "world_flags": ("world_flags_add",), "marks": ("marks",), "foreshadow": ("clue_items", "fs_counters"),
    "rumor": ("rumor",), "chronicle": ("chronicle",), "shard": (), "story": ("story",),
}


@dataclass(frozen=True)
class DefectHook:
    """叛投那一刻的一格（Feature.defection() 回一串）：核心在 at 那個位置照 DEFECT_ORDER[at] 一格一格叫，輪到 slot 就叫 run。照 registered() 問、
    不看 enabled（原位不看包的開關：押糧關著也照清）。run 的簽名照位置（DEFECT_ORDER 底下那張）；包的 run 在叫的那一下才照模組屬性找。"""

    at: str
    slot: str
    run: Callable[..., Any]


# 叛投那一刻各包清自己的進度：位置 → 那一個位置的格，照換成掛鉤之前一行一行的先後（同 WORLD_ORDER：包與還沒成包的舊模組穿插，寫死在這裡）。
# 包登記自己那一格（Feature.defection()），其餘由核心代叫——現在只剩 defection._STRANDED_CORE（懸賞，主人還是舊模組 bounties；defection 第 35 批
# 搬進陣營包、舊名是別名）；defection._CLEAR_CORE／_LEAVE_CORE、engine._DEFECT_AFTER_CORE 第 35 批拿掉（progress、leave_behind 改由陣營包登記）。
# 改這張表先過 PM；tests/core/test_contract_core.py 逐字鎖住。
#
# 位置      核心在哪裡問                                                      run 的簽名                       回傳
# clear     defection.clear_progress(p) 整個身體                              (p: PlayerState) -> None         不接
# leave     defection.defect：clear_progress 之後、改投之前                    (state) -> None                  不接
# stranded  defection.defect 最後：「你叛出…」那一句之後                       (state, content, new_side)       接（list[str]）
# after     陣營包 defect_actions.defect_step 確定那一支：defection.defect 之後（第 35 批前是 Game._defect_step）
#                                                                             (ctx, side) -> list[str]         接
DEFECT_ORDER: dict[str, tuple[str, ...]] = {
    "clear": ("progress", "convoy", "hints", "opportunities"),
    "leave": ("plots",),
    "stranded": ("bounties",),
    "after": ("leave_behind", "parley"),
}


def effect_hooks() -> dict[str, Callable[..., Any]]:
    """包登記的效果格 {slot: run}：照 registered()、不看 enabled。表外的格、同一格登記兩次（兩包或同一包）都丟 ValueError
    （同 world_hooks；tests/core/test_contract_core.py 守）。"""
    own: dict[str, Callable[..., Any]] = {}
    for f in registered():
        for hook in f.effects():
            if hook.slot not in EFFECT_ORDER:
                raise ValueError(f"{f.name} 登記了效果表上沒有的格 {hook.slot}")
            if hook.slot in own:
                raise ValueError(f"效果的 {hook.slot} 登記了兩次（{f.name}）")
            own[hook.slot] = hook.run
    return own


def effect_run(core: dict[str, Callable[..., Any]], *args: Any,
               hooks: dict[str, Callable[..., Any]] | None = None) -> list[Any]:
    """照 EFFECT_ORDER 走每一格：包登記了叫包的，沒有叫 core 那一份（rules._EFFECT_CORE）；兩邊都沒有（那一格的包沒登記：契約測試換掉
    FEATURES 時）跳過。回每一格的回傳值（照順序、跳過的不算）。core 寫了表上沒有的格丟 ValueError（打錯字的格不會默默不跑）。"""
    if not core.keys() <= set(EFFECT_ORDER):
        raise ValueError(f"核心代叫了效果表上沒有的格 {sorted(core.keys() - set(EFFECT_ORDER))}")
    own = effect_hooks() if hooks is None else hooks
    out: list[Any] = []
    for slot in EFFECT_ORDER:
        run = own.get(slot) or core.get(slot)
        if run is not None:
            out.append(run(*args))
    return out


def defect_hooks(at: str) -> dict[str, Callable[..., Any]]:
    """at 那個位置包登記的叛投格 {slot: run}：照 registered()、不看 enabled。每一次都驗登記的全部格：表上沒有的格、同一格登記兩次
    （兩包或同一包）、沒有的位置都丟 ValueError（同 world_hooks）。"""
    if at not in DEFECT_ORDER:
        raise ValueError(f"叛投沒有 {at} 這個位置")
    own: dict[str, Callable[..., Any]] = {}
    for f in registered():
        for hook in f.defection():
            if hook.slot not in DEFECT_ORDER.get(hook.at, ()):
                raise ValueError(f"{f.name} 登記了叛投表上沒有的格 {hook.at}/{hook.slot}")
            if hook.at == at:
                if hook.slot in own:
                    raise ValueError(f"叛投的 {at}/{hook.slot} 登記了兩次（{f.name}）")
                own[hook.slot] = hook.run
    return own


def defect_run(at: str, core: dict[str, Callable[..., Any]], *args: Any) -> list[Any]:
    """照 DEFECT_ORDER[at] 走每一格：包登記了叫包的，沒有叫 core 那一份（核心代叫的格）；兩邊都沒有跳過。回每一格的回傳值（照順序、
    跳過的不算）：接不接由呼叫端照位置決定。core 寫了表上沒有的格丟 ValueError。"""
    own = defect_hooks(at)  # 沒有的位置在這裡丟
    order = DEFECT_ORDER[at]
    if not core.keys() <= set(order):
        raise ValueError(f"核心代叫了叛投 {at} 表上沒有的格 {sorted(core.keys() - set(order))}")
    out: list[Any] = []
    for slot in order:
        run = own.get(slot) or core.get(slot)
        if run is not None:
            out.append(run(*args))
    return out


# core_eventbus（全部拆包第 26 批「事件機制」；計畫 docs/superpowers/plans/2026-11-06-事件機制-第26批.md 1.2、2.1）


@dataclass(frozen=True)
class BusHook:
    """一種事件的一格（Feature.bus() 回一串）：核心在發布點（ctx.publish）照 BUS_ORDER[event] 一格一格叫，輪到 slot 就叫 run(ctx, *args)，
    回這一格的那幾句（沒有是 []；battle_end 回 None、不接）。照 registered() 問、不看 enabled（原位不看包的開關，判斷在被叫的函式裡）。
    包的 run 在叫的那一下才照模組屬性找自己的函式（monkeypatch 照樣有效）。"""

    event: str
    slot: str
    run: Callable[..., Any]


# 事件 → 訂閱的格，照換成事件之前一行裡的呼叫先後。同一下兩個訂閱者的先後就是回話與存檔寫入的先後（outing：打探懸賞→撿玉璽碎片；
# arrive：交糧車→護送懸賞；調了就抓得到，計畫 1.9），所以寫死。包登記自己那一格（Feature.bus()），其餘由 engine._BUS_CORE 代叫（還沒成包的
# 舊模組，標批號）。之後懸賞（第 45 批）、玉璽（第 27 批）成包只是那一格換主人，表不動。改這張表先過 PM；tests/core/test_contract_core.py 逐字鎖住。
# 「集結開始」是世界層 WORLD_ORDER["muster"] 的 seal 那一格（第 25 批），不在這裡。
#
# 事件        發布點（位置不動）                                                                 run 的簽名                         回傳
# win         Game._squad_encounter 打贏（不是野怪、不在序章）；探索包 outing_fight 遭遇打贏（不是城裡）   (ctx, loc_id, squad_id)            接 list[str]
# outing      探索包 explore_one 收尾                                                             (ctx, loc_id)                      接
# explore     探索包 explore_base.explore（舊探索，序章外）                                        (ctx, loc_id)                      接
# arrive      移動包 departure.arrive 抵達一站（Game._arrive 留一行委派）                           (ctx, loc_id)                      接
# raid_win    Game._raid_bounty（截殺、設伏打贏）                                                  (ctx, target)                      接
# battle_end  決戰包 progress.settle_showdown（時刻表決戰收場，讀回季之前）                         (ctx, battle, definition, result)  不接（None）
BUS_ORDER: dict[str, tuple[str, ...]] = {
    "win": ("bounties",),
    "outing": ("bounties", "seal"),
    "explore": ("bounties",),
    "arrive": ("convoy", "bounties"),
    "raid_win": ("bounties",),
    "battle_end": ("seal",),
}


def bus_hooks(event: str) -> dict[str, Callable[..., Any]]:
    """event 那一種包登記的格 {slot: run}：照 registered()、不看 enabled。每一次都驗登記的全部格：表上沒有的事件或格、同一格登記兩次
    （兩包或同一包）都丟 ValueError（同 world_hooks、defect_hooks）。"""
    if event not in BUS_ORDER:
        raise ValueError(f"事件沒有 {event} 這一種")
    own: dict[str, Callable[..., Any]] = {}
    for f in registered():
        for hook in f.bus():
            if hook.slot not in BUS_ORDER.get(hook.event, ()):
                raise ValueError(f"{f.name} 登記了事件表上沒有的格 {hook.event}/{hook.slot}")
            if hook.event == event:
                if hook.slot in own:
                    raise ValueError(f"事件的 {event}/{hook.slot} 登記了兩次（{f.name}）")
                own[hook.slot] = hook.run
    return own


def bus_run(event: str, core: dict[str, Callable[..., Any]], *args: Any,
            hooks: dict[str, Callable[..., Any]] | None = None) -> list[Any]:
    """照 BUS_ORDER[event] 走每一格：包登記了叫包的，沒有叫 core 那一份（核心代叫的格：engine._BUS_CORE）；兩邊都沒有（那一格的包沒登記：
    契約測試換掉 FEATURES 時）跳過。回每一格的回傳值（照順序、跳過的不算）：接不接由發布點決定（battle_end 不接）。
    core 寫了表上沒有的格丟 ValueError（打錯字的格不會默默不跑）；沒有這一種事件丟 ValueError。"""
    own = bus_hooks(event) if hooks is None else hooks  # 沒有這一種事件在 bus_hooks 丟
    order = BUS_ORDER.get(event)
    if order is None:
        raise ValueError(f"事件沒有 {event} 這一種")
    if not core.keys() <= set(order):
        raise ValueError(f"核心代叫了事件 {event} 表上沒有的格 {sorted(core.keys() - set(order))}")
    out: list[Any] = []
    for slot in order:
        run = own.get(slot) or core.get(slot)
        if run is not None:
            out.append(run(*args))
    return out


# core_step（全部拆包第 36 批「你這一步」；計畫 docs/superpowers/plans/2026-11-06-你這一步-第36批.md 1.2、1.3、2.1）


@dataclass(frozen=True)
class StepHook:
    """「你這一步」（本週卡 main.week_card.steps，畫面叫「眼下要事」）的一格（Feature.steps() 回一串）：step.items 照 STEP_ORDER 一格一格叫
    items(ctx, status, orders)（status 是 Game.status_data()、orders 是 Game.orders_view()，殼算好傳進來的那一份），把每一格回的那幾件照順序
    接起來（每一件 {"kind", "text", …}；要補目標的掛一個 step.REF＝(ref, …)，自己帶好 target 的不掛）；四勝利開著時 step.finish 照每一件
    _ref 的第一個字找回寫它的那一格、叫 place(ctx, ref) 補 (id, target, then)。照 registered() 問、不看 enabled（原位那幾行本來就不看包的開關，
    判斷都在被叫的函式裡）。包的函式在叫的那一下才照模組屬性找（monkeypatch 照樣有效：tests/bots/test_step.py 換 tianxia.foreshadow.next_trip）。
    items 回 list（不准回字串、None）；place 回三個（沒有就是 None）。"""

    slot: str
    items: Callable[..., list[dict]]
    ref: str | None = None
    place: Callable[..., tuple[Any, Any, Any]] | None = None


# 「你這一步」的順序表：照換成掛鉤之前 weekcard._steps 一段一段接的先後（整合設計 6.1：託付 → 軍令 → 揭了的懸賞 → 伏筆 → 新手目標 → 去投靠；
# 託付量下來是兩格）。先後就是行為（卡上的先後、「換一件事」從哪一件排起：計畫 1.9 任兩格對調都抓得到），寫死在這裡、不照 FEATURES。包登記
# 自己那一格（Feature.steps()），其餘由核心代叫（step._STEP_CORE：還沒成包的懸賞榜，第 45 批）。章回那一件不在這裡（weekcard 排在最前面、
# 不跟著輪）。改這張表先過 PM；tests/core/test_contract_core.py 逐字鎖住。
#
# 格          主人                                  寫的 kind    ref（_ref 第一個字）  place 補什麼（四勝利開著）
# errand      人物情誼 companions                   errand       —（自己帶 id、target） —
# commission  懸賞 bounties（核心代叫，第 45 批）    errand       errand                那一張委託或求援的地點（護送是終點）
# order       軍情 military                         order        order                 那道軍令去哪裡做（最近的摸清了的）；護糧還沒接糧車多 then（終點）
# bounty      懸賞 bounties（核心代叫，第 45 批）    bounty       bounty                那一張懸賞的地點（護送是終點、打探討伐是地點）
# foreshadow  軍情 military                         foreshadow   foreshadow            伏筆那一趟的地點
# newbie      新手引導 guide                        newbie       newbie                新手目標「去做」帶去的地點
# join        陣營 faction                          join         join                  最近的投靠點
STEP_ORDER: tuple[str, ...] = ("errand", "commission", "order", "bounty", "foreshadow", "newbie", "join")


def step_hooks() -> dict[str, StepHook]:
    """包登記的格 {slot: StepHook}：照 registered()、不看 enabled。每一次都驗登記的全部格：表上沒有的格、同一格登記兩次（兩包或同一包）
    都丟 ValueError（同 world_hooks、bus_hooks）。"""
    own: dict[str, StepHook] = {}
    for f in registered():
        for hook in f.steps():
            if hook.slot not in STEP_ORDER:
                raise ValueError(f"{f.name} 登記了「你這一步」表上沒有的格 {hook.slot}")
            if hook.slot in own:
                raise ValueError(f"「你這一步」的 {hook.slot} 登記了兩次（{f.name}）")
            own[hook.slot] = hook
    return own


def step_table(core: dict[str, StepHook]) -> list[StepHook]:
    """照 STEP_ORDER 排好的每一格：包登記了用包的，沒有用 core 那一份（核心代叫的格：step._STEP_CORE）；兩邊都沒有（那一格的包沒登記：
    契約測試換掉 FEATURES 時）跳過。core 寫了表上沒有的格、key 跟 slot 對不上、兩格寫同一個 ref 都丟 ValueError（finish 照 ref 找回那一格）。"""
    if not core.keys() <= set(STEP_ORDER) or any(k != h.slot for k, h in core.items()):
        raise ValueError(f"核心代叫了「你這一步」表上沒有的格 {sorted(core)}")
    own = step_hooks()
    table = [own.get(slot) or core.get(slot) for slot in STEP_ORDER]
    table = [h for h in table if h is not None]
    refs = [h.ref for h in table if h.ref is not None]
    if len(refs) != len(set(refs)):
        raise ValueError(f"「你這一步」兩格寫了同一個 ref {refs}")
    return table


def step_places(core: dict[str, StepHook]) -> dict[str, Callable[..., Any]]:
    """{ref: place}：step.finish 照每一件 _ref 的第一個字找回那一格補目標（沒有 ref 或沒有 place 的格不列）。"""
    return {h.ref: h.place for h in step_table(core) if h.ref is not None and h.place is not None}
