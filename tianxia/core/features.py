"""功能包的掛鉤（開發規範手冊 3.3）與核心照 FEATURES 彙整（registry.py 的清單，有順序）。

一個功能一包（tianxia/features/<包>/）；核心在幾個大家都插一段的地方照清單依序問每一包。
兩種掛鉤看 enabled 的方式不一樣（手冊 3.3 寫「關著的包一個掛鉤都不叫」，指的是第一種；PM 10/31 認可，3.3 由 PM 補註）：
- 遊戲當下的（options、menu、choose、status、on_sync、on_day、on_season_*、on_drop_stale、bot_pick）：每一次先問 enabled(ctx)，
  關著的包一個都不叫（tests/core/test_contract_core.py、test_contract_features.py 守）。
- 殼啟動、載入內容時的（routes、admin_tools、check_content、bot_always，與宣告的 web、content）：那時候還沒有 ctx（沒有角色、
  開關可能在季中被管理者切換），所以不看 enabled、登記的包全部照掛：路由與管理者工具由各自的 gate 在關著時回 404（搬包之前
  商城在 server 裡也是照掛再 404）、內容照驗（檔案寫壞了早點知道）、永遠按得下去的前綴照排除（關著的包選單上本來就沒有它們）。

| 掛鉤 | 核心在哪裡問 |
|---|---|
| enabled(ctx) | 每一個彙整之前 |
| options(ctx) | Game._stamina_play_options（「此地還能做」裡，體力玩法、護衛之後、盤算之前；序章裡、休季不問） |
| menu(ctx) | Game._everyday_options：這一包此刻接管整個選單（坐在宴席上、店開著那一類）；第一個不是 None 的算。**手冊 3.3 表外**（見下） |
| choose(ctx, kind, arg) | Game.choose 建這一下的紀錄（Draft）之前：只吃自己前綴的 id，吃不到回 None，核心問下一包 |
| status(ctx) | Game.feature_status → server.main_view（合進江湖畫面的頂層，例：商城的入口 main.mall） |
| on_sync(ctx, elapsed)、on_day(ctx) | Game.sync（elapsed 是這一次補算的自己的秒數；on_day 是回體丹那一天換了：照 _pill_day，含快轉推過的 advanced_real，所以 Game.advance 跨過 00:00 也叫） |
| on_season_end(ctx)、on_season_start(ctx, old) | Game._reset_player_for_new_season（舊的那一季要丟之前；新的存檔接上之後、開場那一則之前） |
| on_drop_stale(ctx) | Game._drop_stale_references 最後 |
| bot_pick(ctx, option)、bot_always | bot_policy.score（假人看到這一顆的分數，None 是不按）；bot.pick 排除的前綴（永遠按得下去的） |
| admin_tools(shell)、routes(shell) | server：/api/do/{op} 的管理者工具、掛路由（shell 是 server 模組） |
| check_content(content, need)、web、content | content.validate（關著的包照驗）；index.html 的檔；content.py 讀的檔。check_content **手冊 3.3 表外**（見下） |

比手冊 3.3「就這幾個，不多開」那張表多開了兩個（第 1 階開的，PM 10/31 認可，理由照下面；手冊 3.3 由 PM 補；之後再要加先過 PM）：
- menu：現行的 _everyday_options 裡一包有兩個位置——接管整個選單（坐在席上、店開著……十幾樣都是）與接在「此地還能做」裡（options），
  一個 options 擺不下兩個位置。
- check_content：取代原本的 content.check_mall（載入時驗商品）。核心的 content.py 不能 import 包，3.3 的 content 那一列只宣告
  content.py 讀哪些檔、沒有「驗」，所以開一個讓包自己驗。

ctx 第一階就是 Game；功能包只准叫 services.py 那張清單上的方法。
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from .option import Option

if TYPE_CHECKING:
    from ..engine import Game
    from ..models import Content
    from ..state import GameState


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
    prefix: str | None  # 選項 id 的前綴（「feast」→ feast:join:3）；沒有選項的包是 None
    web: tuple[str, ...]  # web/ 底下這一包的檔（index.html 照舊順序載入；第 3 階才由伺服器照它生成）
    content: tuple[str, ...]  # content/ 底下這一包的檔（第 1、2 階 content.py 照舊全部讀）
    bot_always: tuple[str, ...]  # 永遠按得下去的選項前綴：整季機器人（bot.pick）不按，不然「沒得按就推進時間」的訊號會失效
    player_fields: tuple[str, ...]  # 這一包認領的 PlayerState 欄位（3.5；README 照列）
    carried: tuple[str, ...]  # 上面那些裡換季照帶走的；其餘換季跟著新角色重來（契約測試照它驗）

    def enabled(self, ctx: Game) -> bool: ...
    def options(self, ctx: Game) -> list[Option]: ...
    def menu(self, ctx: Game) -> list[Option] | None: ...
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


class Feature:
    """FeatureHooks 的預設值：什麼都不做、一個選項都不給。每一包繼承它、只改用得到的那幾個。"""

    name = ""
    prefix: str | None = None
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

    def check_content(self, content: Content, need: Callable[[bool, str], None]) -> None:
        return None

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


def owner_of(option_id: str) -> Feature | None:
    """哪一包的選項（照 id 的前綴）；不是任何一包的是 None。"""
    kind = option_id.partition(":")[0]
    return next((f for f in registered() if f.prefix is not None and f.prefix == kind), None)


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


def check_content(content: Content, need: Callable[[bool, str], None]) -> None:
    """載入內容時各包的驗證（content.validate；關著的包照驗：檔案寫壞了早點知道）。"""
    for f in registered():
        f.check_content(content, need)


def web_files() -> list[str]:
    """各包登記的網頁檔（web/ 底下，照 FEATURES 的順序）。第 3 階才由伺服器照它生成 index.html；在那之前 index.html 與
    tests/kit/webharness.APP_FILES 是手寫的，tests/core/test_contract_features.py 照這一份對它們，店面的 CSS 測試照它讀包的樣式。"""
    return [name for f in registered() for name in f.web]
