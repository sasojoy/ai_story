"""功能包的掛鉤（開發規範手冊 3.3）與核心照 FEATURES 彙整（registry.py 的清單，有順序）。

一個功能一包（tianxia/features/<包>/）；核心在幾個大家都插一段的地方照清單依序問每一包。
兩種掛鉤看 enabled 的方式不一樣（手冊 3.3 寫「關著的包一個掛鉤都不叫」，指的是第一種；PM 10/31 認可，3.3 由 PM 補註）：
- 遊戲當下的（options、menu、choose、status、on_sync、on_day、on_season_*、on_drop_stale、bot_pick）：每一次先問 enabled(ctx)，
  關著的包一個都不叫（tests/core/test_contract_core.py、test_contract_features.py 守）。
- 殼啟動、載入內容時的（routes、admin_tools、main_actions、menxia_actions、threads、check_content、bot_always，與宣告的 web、content）：那時候還沒有 ctx（沒有角色、
  開關可能在季中被管理者切換），所以不看 enabled、登記的包全部照掛：路由與管理者工具由各自的 gate 在關著時回 404（搬包之前
  商城在 server 裡也是照掛再 404）、內容照驗（檔案寫壞了早點知道）、永遠按得下去的前綴照排除（關著的包選單上本來就沒有它們）。

| 掛鉤 | 核心在哪裡問 |
|---|---|
| enabled(ctx) | 每一個彙整之前 |
| options(ctx) | Game._stamina_play_options（「此地還能做」裡，體力玩法、護衛之後、盤算之前；序章裡、休季不問） |
| menu(ctx) | Game._everyday_options：這一包此刻接管整個選單（坐在宴席上、店開著那一類）；第一個不是 None 的算。**手冊 3.3 表外**（見下） |
| prep(ctx) | Game._season_prep：開季準備卡（企劃者 2026-11-05），挑完成長配比之後這一包此刻接管整個選單，排在事件（開局三選一）前面；第一個不是 None 的算。**手冊 3.3 表外**（傳承的識海；跟 menu 差在位置：menu 在事件之後） |
| choose(ctx, kind, arg) | Game.choose 建這一下的紀錄（Draft）之前：只吃自己前綴的 id，吃不到回 None，核心問下一包 |
| status(ctx) | Game.feature_status → server.main_view（合進江湖畫面的頂層，例：商城的入口 main.mall）；整體是 main 表（status_slots）的 features 那一格 |
| on_sync(ctx, elapsed)、on_day(ctx) | Game.sync（elapsed 是這一次補算的自己的秒數；on_day 是回體丹那一天換了：照 _pill_day，含快轉推過的 advanced_real，所以 Game.advance 跨過 00:00 也叫） |
| on_season_end(ctx)、on_season_start(ctx, old) | Game._reset_player_for_new_season（舊的那一季要丟之前；新的存檔接上之後、開場那一則之前） |
| on_drop_stale(ctx) | Game._drop_stale_references 最後 |
| bot_pick(ctx, option)、bot_always | bot_policy.score（假人看到這一顆的分數，None 是不按）；bot.pick 排除的前綴（永遠按得下去的） |
| bot_idle(ctx, option) | core_bots（全部拆包第 60 批）：bot.pick 排除裡有條件、或要比相等的那幾顆（此刻按了也白按）；前綴放不下才寫這一格。不問 enabled（舊濾網不看開關，關著的包選單上本來就沒有它們） |
| admin_tools(shell)、routes(shell) | server：/api/do/{op} 的管理者工具、掛路由（shell 是 server 模組） |
| main_actions(shell)、menxia_actions(shell) | server：建 MAIN_ACTIONS（/api/do/{op}）、MENXIA_ACTIONS（/api/menxia/{op}）兩張表：{op: fn(g, body)}，照 action_table 排回寫死的順序。**手冊 3.3 表外**（全部拆包第 68 批，見檔尾 shell_server 那一段） |
| outlock(shell) | server：/api/do/{op} 先接走的鎖外三段式（ops）與放鎖之後要開的背景寫字（jobs），殼啟動時問、不看 enabled、登記的全掛；jobs 的先後是寫死的 OUTLOCK_ORDER。**手冊 3.3 表外**（全部拆包第 69 批，總表第六節第 1 條寫明的跨包機制，見檔尾 shell_server 那一段） |
| threads(shell) | server.main（殼開、測試停：只有 main 叫 start_threads，測試不叫；不回東西。全部拆包第 52 批，開給戰記與第 53 批的看守） |
| check_content(content, need)、web、content | content.validate（關著的包照驗）；/ 的 script 標籤（web_scripts、with_scripts；css 的 link 還是 index.html 手寫）；content.py 讀的檔（第 62 批起在包裡的 content/，pack_content；第 63 批起測試內容在包裡的 tests/content/，pack_test_content）。check_content **手冊 3.3 表外**（見下） |
| content_slots()（ContentSlot）、check_at(slot, content, need, *args) | core_content（第二輪第 100 批）：content.validate 與 figures.check_figures 的原位（單一包的內容驗證，先後由那幾行定，格在 CONTENT_SLOTS；不看 enabled、讀 registry.DECLARED）。**手冊 3.3 表外**（見下面 check_content 底下那一段） |

比手冊 3.3「就這幾個，不多開」那張表多開了兩個（第 1 階開的，PM 10/31 認可，理由照下面；手冊 3.3 由 PM 補；之後再要加先過 PM）：
- menu：現行的 _everyday_options 裡一包有兩個位置——接管整個選單（坐在席上、店開著……十幾樣都是）與接在「此地還能做」裡（options），
  一個 options 擺不下兩個位置。
- check_content：取代原本的 content.check_mall（載入時驗商品）。核心的 content.py 不能 import 包，3.3 的 content 那一列只宣告
  content.py 讀哪些檔、沒有「驗」，所以開一個讓包自己驗。

**接縫掛鉤**（全部拆包第 11 批「核心收接縫」開的；計畫 docs/superpowers/plans/2026-11-01-核心收接縫.md）：第 1～10 批把功能搬進包時，
先後會影響結果的接縫當時留在原位直接叫包（邊界測試的 GAME_DIRECT、GAME_DELEGATE_CALLERS；GAME_DIRECT 第二輪第 98 批清空）。這一批在原本那一行的位置開掛鉤：核心在那一行
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
| scene_over(ctx) | core/scene_view.scene_text 最前面（蓋在畫面上的戰場）；自己眼前的那一張與圖是 scenes()（core_scene，第二輪第 91 批） |
| record_detail(ctx, record) | Game.battle_detail：戰報頁那一筆（決戰照 battles 表重讀完整戰況） |
| on_season_close(ctx, reread) | Game.admin_end_season 讀回收季那一份季之後、補大事之前（reread=False）；Game.admin_next_season 休季時、開下一季之前（reread=True：收兵之前讀回手上那一份季）——收季的收兵（決戰；全部拆包第 8 批） |
| shops()（Shop） | 店面登記：店裡那一串（_everyday_options）、進店那一顆、哪一間開著（_shop_open）、動身收店（_depart）、此地不開了收店（sync、_drop_stale_references） |
| shop_view(ctx, shop) | 店面那一頁的資料（shop_page，core/page_view.shop_view 問；一間店只有一包認，開頭先認店；第二輪第 93 批） |
| verbs()（Verb） | act 子動詞：_act 最前面、_action_title、行動列那一格（_everyday_options）、行動列底下那一行（action_notes）、只打開一張卡的回話（choose）；
  這一下打哪一路（_fight_squad 最前面：大場面判讀問；sortie：全部拆包第 17 批多開的一格 squad）。帶後綴的 act:<verb>:<後綴>（全部拆包第 57 批：tail_run、tail_title、tail_squad）問同一張表；
  只有 act:heal 與舊探索 act:explore 留在 _act 原位（計畫 docs/superpowers/plans/2026-11-06-分派標題收接縫-第57批.md 第四節）。
  假人（core_bots，全部拆包第 60 批：bot、tail_bot、bot_skip、tail_bot_skip）：bot_policy.score 的 act: 那一段問 act_score，bot.pick 問 bot_idle；都不問 enabled（計畫 docs/superpowers/plans/2026-11-06-假人殼收尾-第60批.md 第一節） |
| world()（WorldHook） | 世界層的格（core_world：全部拆包第 25 批）：world.advance_world_state 每一步、season_events 的週初與每天、settle_season_start、
  end_season、_open_claimed；sqlite_world 的開季與換季；figure_life.tick 每一位對話人物（life，第 40 批）。照檔尾那張寫死的順序表 WORLD_ORDER 一格一格叫（包與還沒成包的舊模組穿插），不問 enabled |
| effects()（EffectHook） | 一則效果的格（core_effects：全部拆包第 32 批）：rules.apply_effect 從頭到尾一段一格，照檔尾寫死的順序表 EFFECT_ORDER 一格一格叫
  （每一個效果欄位歸哪一格寫在 EFFECT_FIELDS），不問 enabled |
| defection()（DefectHook） | 叛投那一刻的格（core_effects）：defection.clear_progress（clear）、defection.defect（leave、stranded）、陣營包
  defect_actions.defect_step 確定那一支（after；第 35 批前是 Game._defect_step）四個位置，照檔尾寫死的順序表 DEFECT_ORDER 一格一格叫（各包清自己的進度），不問 enabled |
| bus()（BusHook） | 一種事件的格（core_eventbus：全部拆包第 26 批）：ctx.publish 的八個發布點（打贏一場〔兩處〕、出門一趟、舊探索、抵達、截殺打贏、
  人物託付〔護衛、犒軍〕、決戰收場），照檔尾寫死的順序表 BUS_ORDER 一格一格叫，不問 enabled |
| steps()（StepHook） | 「你這一步」的格（core_step：全部拆包第 36 批）：本週卡「眼下要事」的候選（weekcard._steps 叫 step.items）與四勝利開著時補目標
  （step.finish 照每一件 _ref 的第一個字找回那一格的 place），照檔尾寫死的順序表 STEP_ORDER 一格一格叫（包登記自己那一格；懸賞榜兩格第 45 批
  由懸賞榜包登記），不問 enabled |
| seams()（SeamHook） | 補算與換季的格（core_seams：全部拆包第 55 批）：Game.sync、advance、world_tick、_advance_player_local、own_turn_checks、_drop_stale_references、
  _reset_player_for_new_season 裡各包那一段，照檔尾寫死的順序表 SEAM_ORDER 一格一格叫（包與核心的段穿插），不問 enabled |
| menus()（MenuHook） | 選單與動身的格（core_seams：全部拆包第 56 批）：Game.options、_everyday_options、action_notes、_idle、_shop_open、_stamina_play_options、atlas.travel_block、
  移動包的出發收店裡各包那一段，第 57 批加 Game.choose 那幾顆「選單上、不建紀錄」的（quick），照檔尾寫死的順序表 MENU_ORDER 一格一格問（包與核心的格穿插），不問 enabled |
| scenes()（SceneHook） | 場景卡的格（core_scene：第二輪第 91 批）：core/scene_view.py 的 _own_scene_text、scene_art 照順序表 SCENE_ORDER 一格一格問（包與核心的格穿插），第一個不是 None 的算，不問 enabled |
| howto()（HowtoHook） | 玩法說明的格（全部拆包第 59 批「引導二」）：設定抽屜那一頁（guide/howto.py 的 page）照檔尾寫死的順序表 HOWTO_ORDER 一格一格接；
  別節中間的插句（判斷在別包）走 HOWTO_INSERTS（howto_insert），不問 enabled |
| status_slots()（StatusHook） | 狀態列（Game.status_data）、江湖畫面（server._main_view_body）與管理頁（features/admin/routes.py 的 admin_choices，第二輪第 90 批）的格（shell_web：全部拆包第 66 批）：照檔尾寫死的順序表 STATUS_ORDER
  一格一格叫、回的鍵照順序合（JSON 鍵的先後、叫的先後都算行為；關著的包原位那幾行本來就照叫），不問 enabled；表外的格接在表尾（第二輪第 74 批） |
| scratch() | 包寄放在 Game 上的旗標 {名字: 預設值}（core_choose：第二輪第 92 批）：Game 建好時 scratch_init 照 registry.DECLARED 一包一包擺上去，不問 enabled；每次回新的 dict。不進存檔 |

ctx 第一階就是 Game；功能包只准叫 services_list.md 那張清單上的方法，和自己這一包的委派。
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from .option import Option

if TYPE_CHECKING:
    from ..engine import Game
    from ..models import Content, Location, Squad
    from ..state import BattleRecord, GameState, WorldState


@dataclass(frozen=True)
class Shop:
    """店面登記（第 11 批）：一間開在城裡、坐進去選單整個換成那間店的店。核心在店共用的那幾處照清單問，排在 MENU_ORDER 的 shops 那一格（懸賞榜、鐵匠鋪、馬市不登記，
    走 MENU_ORDER 自己的格，第 56 批計畫第四節）。每一樣都拿 ctx（Game）。"""

    key: str  # Game._shop_open 回的字（店面那一頁畫哪一間；server 的 main_view 照它）
    inside: Callable[[Any], bool]  # 此刻坐在店裡（picking_*）
    here: Callable[[Any], bool]  # 這裡此刻開著這間店（開關、地點、不在路上……）
    close: Callable[[Any], None]  # 收起來（掌櫃那一句一併清）
    menu: Callable[[Any], list[Option]]  # 坐在店裡時的整個選單
    entry: Callable[[Any], Option | None]  # 「此地還能做」裡進店那一顆；這裡不開門是 None


@dataclass(frozen=True)
class Verb:
    """act:<verb> 那一格的主人（act 子動詞；第 11 批先開給主人已經成包的三格，全部拆包第 57 批把其餘的接上同一張表，只留 act:heal 與舊探索）。每一樣都可以是 None，
    回 None 也一樣：照舊由核心做（核心那一支還在：舊探索、療傷）。
    選項帶後綴的（act:<verb>:<後綴>，第 57 批）：verb 寫冒號前那一段，按下去、標題、打哪一路問 tail_* 那三格，同一個 Verb 可以同時管 act:recruit 與 act:recruit:<人物>；
    行動列那一格、底下那一行、picks 只認沒有後綴的。一格一主、子動詞互斥，沒有先後，不開順序表（tests/core/test_contract_core.py、test_contract_features.py 鎖 {verb: 包}、不准兩包認同一格）。"""

    verb: str
    run: Callable[[Any, Any], list[str] | None] | None = None  # Game._act 最前面：按下去（ctx, prepared）
    title: Callable[[Any], str | None] | None = None  # Game._action_title：這一下江湖紀錄的整個標題
    cell: Callable[[Any, Any, int, bool], list[Option] | None] | None = None  # 行動列那一格（ctx, 地點, 體力, 寫不寫勝算）；[] 是接了、一顆都沒有
    note: Callable[[Any, Any], str | None] | None = None  # 行動列底下那一行（ctx, 地點）
    picks: tuple[str, ...] = ()  # 按了只打開一張卡的回話：不算做過、不寫江湖紀錄（Game.choose 的 picked_only、quiet）
    # sortie（全部拆包第 17 批「出陣三」多開的一格；第 11 批計畫第五節第 1 條預告的「這一下打不打仗」）：Game._fight_squad 最前面，
    # 這一格按下去會打哪一路（大場面判讀、鎖外 A 段與鎖內 C 段的重驗都問它）；不打仗是 None（核心照舊往下，act: 那幾格往下也是 None）
    squad: Callable[[Any], Squad | None] | None = None
    # core_seams（全部拆包第 57 批）：帶後綴的那一下
    tail_run: Callable[[Any, Any, str], list[str] | None] | None = None  # Game._act 最前面：按下去（ctx, prepared, 後綴）
    tail_title: Callable[[Any, str], str | None] | None = None  # Game._action_title：這一下江湖紀錄的整個標題（ctx, 後綴）
    tail_squad: Callable[[Any, str], Squad | None] | None = None  # Game._fight_squad 最前面：這一下打哪一路（ctx, 後綴）
    # core_bots（全部拆包第 60 批）：假人怎麼按這一格。bot、tail_bot 是 bot_policy.score 問的分數（ctx, 名牌[, 後綴]），回 None 是不按；這一格沒寫（None）算沒主人，
    # bot_policy 照舊落到 ACT_SCORES.get(arg, 0.0)，0.0 是隨機挑得到的、不是不按，別寫成回 None 的格。bot_skip、tail_bot_skip 是 bot.pick 不按（只是打開一張卡、一直按得下去）
    bot: Callable[[Any, Any], float | None] | None = None
    tail_bot: Callable[[Any, Any, str], float | None] | None = None
    bot_skip: bool = False
    tail_bot_skip: bool = False
    # core_rest（第二輪第 99 批）：標題只在 kind == "act" 才問主人（銀兩那四樣；別的 kind 帶同一個字照舊是「提前出關」，同帶後綴的）
    act_only: bool = False


@dataclass(frozen=True)
class Outcome:
    """choose 接走一顆選項：title 是這一下江湖紀錄的標題（核心在動作之前先拿，同 Game._action_title），run 做那個動作、回那幾句話。
    後面三格（core_choose，第二輪第 92 批）管這一則紀錄怎麼落，沒給就是一下一則：quiet(entry) 建好這一則之後問，真的就不寫（只是翻頁）；merge 併進上一則同標題的（journal.add_entry）；
    fold() 動作之後要寫那一則時才叫，回 add_entry 的 fold（是函式因為 Outcome 在動作之前建，判斷可能要讀動作之後的狀態）。"""

    title: str
    run: Callable[[], list[str]]
    quiet: Callable[[Any], bool] | None = None
    merge: bool = False
    fold: Callable[[], Any] | None = None


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
    web: tuple[str, ...]  # web/ 底下這一包的檔：js 的 script 標籤由伺服器照它生成（web_scripts、with_scripts）；css 的 link 還是 index.html 手寫（第 67 批）
    content: tuple[str, ...]  # 這一包的內容檔，相對於 tianxia/features/<包>/content/（第 62 批起 content.py 照 pack_content 去那裡讀；寫法同它以前在 content/ 底下，例 events/x.json；第 63 批起同一個 rel 的測試內容在 tests/content/<rel>，有才算）
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
    def bot_idle(self, ctx: Game, option: Option) -> bool: ...  # core_bots（全部拆包第 60 批）：不問 enabled
    def admin_tools(self, shell: Any) -> dict[str, AdminTool]: ...
    def main_actions(self, shell: Any) -> dict[str, Callable[[Any, dict], Any]]: ...  # shell_server
    def menxia_actions(self, shell: Any) -> dict[str, Callable[[Any, dict], Any]]: ...  # shell_server
    def outlock(self, shell: Any) -> Outlock: ...  # shell_server
    def routes(self, shell: Any) -> Any: ...
    def check_content(self, content: Content, need: Callable[[bool, str], None]) -> None: ...
    def content_slots(self) -> tuple[ContentSlot, ...]: ...  # core_content（第二輪第 100 批）
    # ── 接縫掛鉤（第 11 批；不問 enabled，Shop.menu、Shop.entry、Verb.cell 除外）──
    def on_due(self, ctx: Game) -> None: ...
    def on_away(self, ctx: Game, away_from: float) -> None: ...
    def deliver_results(self, ctx: Game) -> None: ...
    def deliver_notices(self, ctx: Game) -> None: ...
    def choose_unlisted(self, ctx: Game, option_id: str) -> list[str] | None: ...
    def after_action(self, ctx: Game) -> list[str]: ...
    def on_own_turn(self, ctx: Game) -> None: ...
    def scene_over(self, ctx: Game) -> tuple[str, bool] | None: ...
    def record_detail(self, ctx: Game, record: BattleRecord) -> BattleRecord | None: ...
    # battle（全部拆包第 8 批：收季的收兵；第 11 批 PM 認定第 7 條「兩段要一起進收季的位置」）
    def on_season_close(self, ctx: Game, reread: bool) -> None: ...
    def shops(self) -> tuple[Shop, ...]: ...
    def shop_view(self, ctx: Game, shop: str) -> dict | None: ...
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
    # core_seams（全部拆包第 55 批：補算與換季的格，先後在 SEAM_ORDER；不問 enabled）
    def seams(self) -> tuple[SeamHook, ...]: ...
    # core_seams（全部拆包第 56 批：選單與動身的格，先後在 MENU_ORDER；不問 enabled）
    def menus(self) -> tuple[MenuHook, ...]: ...
    # core_scene（第二輪第 91 批：場景卡的格，先後在 SCENE_ORDER；不問 enabled）
    def scenes(self) -> tuple[SceneHook, ...]: ...
    # howto（全部拆包第 59 批：玩法說明的格，先後在 HOWTO_ORDER；不問 enabled）
    def howto(self) -> tuple[HowtoHook, ...]: ...
    # tale（全部拆包第 52 批：殼啟動時開這一包的背景執行緒；只有 server.main 叫，測試不叫；不問 enabled，殼啟動還沒有 ctx）
    def threads(self, shell: Any) -> None: ...
    # shell_web（全部拆包第 66 批：狀態列與江湖畫面的格，先後在 STATUS_ORDER；不問 enabled）
    def status_slots(self) -> tuple[StatusHook, ...]: ...
    # core_choose（第二輪第 92 批：包寄放在 Game 上的旗標；不問 enabled，走 registry.DECLARED，見 scratch_init）
    def scratch(self) -> dict[str, Any]: ...


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

    def bot_idle(self, ctx: Game, option: Option) -> bool:
        return False

    def admin_tools(self, shell: Any) -> dict[str, AdminTool]:
        return {}

    def main_actions(self, shell: Any) -> dict[str, Callable[[Any, dict], Any]]:  # shell_server
        return {}

    def menxia_actions(self, shell: Any) -> dict[str, Callable[[Any, dict], Any]]:  # shell_server
        return {}

    def outlock(self, shell: Any) -> Outlock:  # shell_server
        return Outlock()

    def routes(self, shell: Any) -> Any:
        return None

    def threads(self, shell: Any) -> None:
        return None

    def check_content(self, content: Content, need: Callable[[bool, str], None]) -> None:
        return None

    def content_slots(self) -> tuple[ContentSlot, ...]:
        return ()

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

    def scene_over(self, ctx: Game) -> tuple[str, bool] | None:
        return None

    def record_detail(self, ctx: Game, record: BattleRecord) -> BattleRecord | None:
        return None

    def on_season_close(self, ctx: Game, reread: bool) -> None:
        return None

    def shops(self) -> tuple[Shop, ...]:
        return ()

    def shop_view(self, ctx: Game, shop: str) -> dict | None:
        return None

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

    def seams(self) -> tuple[SeamHook, ...]:
        return ()

    def menus(self) -> tuple[MenuHook, ...]:
        return ()

    def scenes(self) -> tuple[SceneHook, ...]:  # core_scene
        return ()

    def howto(self) -> tuple[HowtoHook, ...]:
        return ()

    def status_slots(self) -> tuple[StatusHook, ...]:
        return ()

    def scratch(self) -> dict[str, Any]:
        return {}

    def __repr__(self) -> str:
        return f"<功能包 {self.name}>"


# ── 核心照清單問（registry 延後 import：包的 __init__ 要 import 這一份的 Feature）──


def registered() -> list[Feature]:
    """登記的全部包（有順序；關著的也在）。"""
    from .registry import FEATURES  # noqa: PLC0415

    return FEATURES


# core_content（全部拆包第 62 批：內容照包分）
def pack_content() -> dict[str, Path]:
    """各包宣告的內容檔：rel（宣告的字串，同它以前在 content/ 底下的相對路徑）→ tianxia/features/<包>/content/<rel>，照 registry.DECLARED 的順序
    （不讀 FEATURES，理由在 DECLARED 那裡）。同一個 rel 兩包都宣告就報錯（用 rel 認、不用檔名認：sects.json 與 events/sects.json 是兩個檔）。"""
    from ..content import ContentError  # noqa: PLC0415  只有 content.py 叫這一支（content.py 延後 import 這裡）
    from .registry import DECLARED  # noqa: PLC0415

    home = Path(__file__).resolve().parent.parent / "features"
    files: dict[str, Path] = {}
    for f in DECLARED:
        for rel in f.content:
            if rel in files:
                raise ContentError(f"內容檔 {rel} 有兩包宣告（{f.name} 與 {files[rel]}）")
            files[rel] = home / f.name / "content" / rel
    return files


def pack_test_content(only: str | None = None) -> dict[str, Path]:
    """各包的測試內容（全部拆包第 63 批）：rel → tianxia/features/<包>/tests/content/<rel>，判準同真實內容：Feature.content 宣告了這個 rel 才歸包，
    照 registry.DECLARED 的順序（理由同 pack_content）。**檔在才收**：測試內容靠「沒有這個檔就是空的」（沒有 mall.json 就沒有商品），包宣告了不等於測試內容也要有。
    only 給了只留那一包的（load_content(only=)），不是登記的包就報錯。"""
    from ..content import ContentError  # noqa: PLC0415  同 pack_content
    from .registry import DECLARED  # noqa: PLC0415  同 pack_content

    if only is not None and only not in {f.name for f in DECLARED}:
        raise ContentError(f"沒有 {only} 這一包，不能只載它的內容")
    home = Path(__file__).resolve().parent.parent / "features"
    candidates = ((rel, home / f.name / "tests" / "content" / rel) for f in DECLARED if only in (None, f.name) for rel in f.content)
    return {rel: path for rel, path in candidates if path.is_file()}


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


# core_bots（全部拆包第 60 批「假人殼收尾」；計畫 docs/superpowers/plans/2026-11-06-假人殼收尾-第60批.md 第一節）


def bot_idle(ctx: Game, option: Option) -> bool:
    """這一顆是不是「一直按得下去、按了也白按」（bot.pick 排除，不然「沒得按就推進時間」的訊號會失效）：包宣告的前綴（bot_always）、
    act:<verb> 那一格的 bot_skip、act:<verb>:<後綴> 那一格的 tail_bot_skip、選項主人的 bot_idle（有條件的、要比相等的）。都是只讀的濾網，互相沒有先後；
    不問 enabled（舊濾網不看開關，關著的包選單上本來就沒有它們）。"""
    oid = option.id
    if oid.startswith(bot_always()):
        return True
    kind, _, rest = oid.partition(":")
    if kind == "act":
        head, sep, _ = rest.partition(":")
        if any(v.tail_bot_skip if sep else v.bot_skip for v in _verbs(None, head)):
            return True
    owner = owner_of(oid)
    return owner is not None and owner.bot_idle(ctx, option)


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


# core_content（第二輪第 100 批；計畫 docs/superpowers/plans/2026-11-07-第二輪-第100批.md 第二節）：單一包的內容驗證，位置固定的格。
# 這些驗證的先後夾在 content.validate、figures.check_figures 的固定幾行之間，先後就是行為（第一個錯誤的全文不准變），接 check_content 會全部挪到
# check_features 那一處（手冊第 34 批認定第 2 條），所以原位一行換一行、叫 check_at。
@dataclass(frozen=True)
class ContentSlot:
    """一格內容驗證（Feature.content_slots() 回一串）：check(content, need, *原位多傳的) 跟搬之前同一個簽名。包的函式在叫的那一下才照模組屬性找（同 HowtoHook）。"""

    slot: str
    check: Callable[..., None]


# 格的先後由 content.validate、check_figures 那幾行定，這張表不排先後，只擋打錯字與鎖主人。改表先過 PM（同 BUS_ORDER）；tests/core/test_contract_core.py 逐字鎖住。
#
# 格              主人                原位多傳的
# insight_scenes  有所感 sense
# insight_strong  有所感 sense
# faction_choices 陣營 faction
# seal            玉璽 seal
# stances         人物情誼 companions where, fig（check_figures 的迴圈裡）
# errands         人物情誼 companions where, fig（check_figures 的迴圈裡）
# companions      人物情誼 companions
# foreshadows     軍情 military       known, region_ids, front_ids, counters_written
# promotions      軍情 military       known
# opportunities   軍情 military       known, front_ids
# duels           單挑 bout           known
# gear            裝備 gear           known
# signature_arms  裝備 gear           known
# bounties        懸賞 bounties
# storylines      長篇奇事 story
CONTENT_SLOTS: tuple[str, ...] = (
    "insight_scenes", "insight_strong", "faction_choices", "seal", "stances", "errands", "companions", "foreshadows", "promotions", "opportunities",
    "duels", "gear", "signature_arms", "bounties", "storylines",
)


def check_at(slot: str, content: Content, need: Callable[[bool, str], None], *args: Any) -> None:
    """叫 slot 那一格的內容驗證。走 registry.DECLARED、不走 registered()，不看 enabled：搬之前這些驗證不看 FEATURES，契約測試把 FEATURES 換成假的或 []
    時內容母本可能正好在建（DECLARED 那裡的理由），讀 registered() 就靜靜少驗。slot 不在表上、每一次驗登記的全部格：表外的格、同一格登記兩次（兩包或同一包）
    都丟 ValueError（同 howto_hooks）；沒人登記就跳過（契約測試鎖 15 格都有主）。"""
    from .registry import DECLARED  # noqa: PLC0415  同 pack_content

    if slot not in CONTENT_SLOTS:
        raise ValueError(f"內容驗證沒有 {slot} 這一格")
    own: dict[str, ContentSlot] = {}
    for f in DECLARED:
        for hook in f.content_slots():
            if hook.slot not in CONTENT_SLOTS:
                raise ValueError(f"{f.name} 登記了內容驗證表上沒有的格 {hook.slot}")
            if hook.slot in own:
                raise ValueError(f"內容驗證的 {hook.slot} 登記了兩次（{f.name}）")
            own[hook.slot] = hook
    hook = own.get(slot)
    if hook is not None:
        hook.check(content, need, *args)


def web_files() -> list[str]:
    """各包登記的網頁檔（web/ 底下，照 FEATURES 的順序）。js 由伺服器照它生成 / 的 script 標籤（下面的 web_scripts、with_scripts）；css 的 link 與
    tests/kit/webharness.APP_FILES 是手寫的，tests/core/test_contract_features.py 照這一份對它們，店面的 CSS 測試照它讀包的樣式。"""
    return [name for f in registered() for name in f.web]


# ── shell_web（全部拆包第 64 批；計畫 docs/superpowers/plans/2026-11-06-網頁殼化-第64批.md 第三節）：/ 的 script 由伺服器生成 ──
# 頁面上載入 js 的先後（性質同 BUS_ORDER：先後就是行為）。不是 FEATURES 的順序：這幾支一直是這個先後，頂層敘述照這個順序跑；
# shell.js 最先（包一載入就叫 registerPage），app.js 最後（它最後一行才啟動，排在包檔前面的話 enter 可能在包檔到之前跑）；
# state.js、fit.js 是第 66 批從 app.js 切出來的殼：state.js 不能排在 admin.js 前面（S 的字面值在載入當下叫 admin.js 的 onAdminPath）。
WEB_ORDER = ("shell.js", "main.js", "map.js", "outing.js", "mall.js", "legacy.js", "arena_anim.js", "arena_scene.js", "admin.js", "state.js", "fit.js", "app.js")
WEB_MARK = "<!--scripts-->"  # web/index.html 裡換成一串 script 標籤的那個標記


def web_scripts() -> list[str]:
    """/ 載入的 js：WEB_ORDER（除了 app.js），接著各包登記、不在 WEB_ORDER 的 js（照 FEATURES），最後 app.js。之後新包只要寫 Feature.web。"""
    head = [name for name in WEB_ORDER if name != "app.js"]
    return head + [name for name in web_files() if name.endswith(".js") and name not in WEB_ORDER] + ["app.js"]


def with_scripts(html: str) -> str:
    """把 index.html 的標記換成一串 script 標籤，行尾跟檔案一樣。標記不是剛好一個就丟例外（同 server.versioned_page：啟動時就壞，不默默送壞頁）。"""
    if html.count(WEB_MARK) != 1:
        raise ValueError(f"index.html 要有剛好一個 {WEB_MARK}，現在有 {html.count(WEB_MARK)} 個")
    newline = "\r\n" if "\r\n" in html else "\n"
    return html.replace(WEB_MARK, newline.join(f'<script src="/static/{name}"></script>' for name in web_scripts()))


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


def scene_over(ctx: Game) -> tuple[str, bool] | None:
    """蓋在畫面上的（core/scene_view.scene_text 最前面）：(那一段, 要不要整個取代自己眼前的事)；第一個不是 None 的算。"""
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


def shop_page(ctx: Game, shop: str) -> dict | None:
    """店面那一頁的資料（core/page_view.shop_view，第二輪第 93 批）：問每一包，第一個不是 None 的回去（一間店只有一包認，契約測試守）。
    不問 enabled：原本的分派不看開關，_shop_open 的 open 格也不看。"""
    for f in registered():
        view = f.shop_view(ctx, shop)
        if view is not None:
            return view
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
    """act:<verb> 按下去（Game._act 最前面）：主人接了回那幾句；都不接是 None，核心照舊。帶後綴的（<verb>:<後綴>，第 57 批）問 tail_run。"""
    head, sep, tail = verb.partition(":")
    for v in _verbs(None, head):
        if sep:
            got = v.tail_run(ctx, prepared, tail) if v.tail_run is not None else None
        else:
            got = v.run(ctx, prepared) if v.run is not None else None
        if got is not None:
            return got
    return None


def act_title(ctx: Game, verb: str, kind: str = "act") -> str | None:
    """act:<verb> 那一下江湖紀錄的標題（Game._action_title 那張表之前；表照 arg 查、不看 kind，這裡也一樣，只有帶後綴的與 Verb.act_only 那幾樣要 kind == "act"）。帶後綴的（第 57 批）問 tail_title。"""
    head, sep, tail = verb.partition(":")
    for v in _verbs(None, head):
        if kind != "act" and (sep or v.act_only):
            continue
        if sep:
            got = v.tail_title(ctx, tail) if v.tail_title is not None else None
        else:
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
    不問 enabled（原位那一支本來就不看開關，同 run、title、note）。帶後綴的（第 57 批）問 tail_squad。"""
    head, sep, tail = verb.partition(":")
    for v in _verbs(None, head):
        if sep:
            got = v.tail_squad(ctx, tail) if v.tail_squad is not None else None
        else:
            got = v.squad(ctx) if v.squad is not None else None
        if got is not None:
            return got
    return None


# core_bots（全部拆包第 60 批「假人殼收尾」）


def act_score(ctx: Game, verb: str, profile: Any) -> tuple[bool, float | None]:
    """(這一格有沒有主人打分數, 假人的分數)：bot_policy.score 的 act: 那一段問。主人回 None 是不按；那一格沒寫算沒主人（owned=False），bot_policy 照舊落到
    ACT_SCORES.get(arg, 0.0)。不問 enabled（原位不看開關，同 act、act_title；不開順序表：一格一主，沒有「同一下誰先」，第 57 批第一節）。帶後綴的問 tail_bot。"""
    head, sep, tail = verb.partition(":")
    for v in _verbs(None, head):
        if sep and v.tail_bot is not None:
            return True, v.tail_bot(ctx, profile, tail)
        if not sep and v.bot is not None:
            return True, v.bot(ctx, profile)
    return False, None


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
# 改這張表先過 PM；tests/core/test_contract_core.py 逐字鎖住。改格的本體或這張表另外要跑（scripts/test_for.py 挑不全）：tests/map/test_atlas.py、tianxia/features/guide/tests/ 的 test_explain、test_prologue、tianxia/features/peers/tests/test_social.py，
# tianxia/features/smithy/tests/test_shop.py，tests/figures/ 的 test_day_scale、test_gentry_allied、test_orders，與 scripts/same_behavior.py 的 stack 一軌（兩層以上疊著的先後只有它比）。
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
# 包登記自己那一格（Feature.defection()）。核心代叫的都空了：defection._STRANDED_CORE 第 45 批留 {}（懸賞榜包登記 stranded 那一格）；defection._CLEAR_CORE／_LEAVE_CORE、
# engine._DEFECT_AFTER_CORE 第 35 批拿掉（progress、leave_behind 改由陣營包登記）。
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
# 舊模組，標批號；懸賞第 45 批、玉璽第 27 批成包之後每一列都空了，表不動，只有第 45 批加了 aid 那一列，PM 點頭）。改這張表先過 PM；tests/core/test_contract_core.py 逐字鎖住。
# 「集結開始」是世界層 WORLD_ORDER["muster"] 的 seal 那一格（第 25 批），不在這裡。
#
# 事件        發布點（位置不動）                                                                 run 的簽名                         回傳
# win         core/combat.py 的 squad_encounter 打贏（Game._squad_encounter 一行委派；不是野怪、不在序章）；探索包 outing_fight 遭遇打贏（不是城裡）   (ctx, loc_id, squad_id)            接 list[str]
# outing      探索包 explore_one 收尾                                                             (ctx, loc_id)                      接
# explore     探索包 explore_base.explore（舊探索，序章外）                                        (ctx, loc_id)                      接
# arrive      移動包 departure.arrive 抵達一站（Game._arrive 留一行委派）                           (ctx, loc_id)                      接
# raid_win    懸賞榜包 actions.raid_bounty（截殺、設伏打贏；Game._raid_bounty 留一行委派）              (ctx, target)                      接
# aid         大勢人物包 aid_actions（護衛、犒軍辦成：他發的求援委託算辦成；第 45 批開的）              (ctx, cid)                         接
# battle_end  決戰包 progress.settle_showdown（時刻表決戰收場，讀回季之前）                         (ctx, battle, definition, result)  不接（None）
BUS_ORDER: dict[str, tuple[str, ...]] = {
    "win": ("bounties",),
    "outing": ("bounties", "seal"),
    "explore": ("bounties",),
    "arrive": ("convoy", "bounties"),
    "raid_win": ("bounties", "zongmen"),  # zongmen（門派第三批：截殺打贏親傳撿殘頁；Joy 2026-11-08「不錯，按照設計稿動工」，設計稿 v6 卷二）
    "aid": ("bounties",),  # bounties（全部拆包第 45 批：人物託付開成事件，PM 點頭，只加這一列）
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
# 自己那一格（Feature.steps()）；懸賞榜兩格第 45 批成包，step._STEP_CORE 空了。章回那一件不在這裡（weekcard 排在最前面、
# 不跟著輪）。改這張表先過 PM；tests/core/test_contract_core.py 逐字鎖住。
#
# 格          主人                                  寫的 kind    ref（_ref 第一個字）  place 補什麼（四勝利開著）
# errand      人物情誼 companions                   errand       —（自己帶 id、target） —
# commission  懸賞 bounties                          errand       errand                那一張委託或求援的地點（護送是終點）
# order       軍情 military                         order        order                 那道軍令去哪裡做（最近的摸清了的）；護糧還沒接糧車多 then（終點）
# bounty      懸賞 bounties                          bounty       bounty                那一張懸賞的地點（護送是終點、打探討伐是地點）
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


# core_seams（全部拆包第 55 批「補算與換季收接縫」；計畫 docs/superpowers/plans/2026-11-06-補算換季收接縫-第55批.md 一、二、六）


@dataclass(frozen=True)
class SeamHook:
    """補算與換季的一格（Feature.seams() 回一串）：核心在 at 那個位置照 SEAM_ORDER[at] 一格一格叫，輪到 slot 就叫 run。照 registered() 問、
    不看 enabled（原位那幾行本來就不看包的開關：碎片關著照樣要重抄、把抄本清掉；on_sync、on_drop_stale、on_season_* 只問開著的包，所以接不了，
    第 42 批認定第 7 條）。run 的簽名照位置（SEAM_ORDER 底下那張）；包的 run 在叫的那一下才照模組屬性或 ctx 找（monkeypatch 照樣有效）。"""

    at: str
    slot: str
    run: Callable[..., Any]


# 補算與換季的順序表：位置 → 那一個位置的格，照換成掛鉤之前一行一行的呼叫順序。順序就是行為（同一下誰先誰後、江湖紀錄的先後、世界旗標、亂數抽到的順序都算；
# test_seats 那條「抄帳排在抵達與密謀之後」就是 sync.deliver 的 seat 在 arrive、plots 之後的守門），所以寫死、連核心自己的段一起列。包登記自己那一格（Feature.seams()），
# 其餘由核心代叫（engine._SEAM_CORE；要用區域變數的 day、on_sync 由 Game._sync_core 回 closure）。改這張表先過 PM；tests/core/test_contract_core.py 逐字鎖住。
#
# 位置            核心在哪裡問                                                   run 的簽名            回傳
# local           Game._advance_player_local 最後（體力氣血回完）                 (ctx)                 接進 msgs
# sync.heirloom   Game.sync 補算自己的時間之前（承露照整段離線時間算體力回復）      (ctx)                 不接
# sync.close      Game.sync 補算完下線那一段之後：收店、收伏、抵達                 (ctx)                 接成 arrived（只有 arrive 回字）
# sync.deliver    Game.sync 寫完江湖大事之後：補送到席次                           (ctx)                 接成回話（依序 plots、summons、seat；其餘回 None）
# advance.arrive  Game.advance 跨日之後                                           (ctx)                 接成 arrived
# advance.turn    Game.advance 抵達之後、存季之前                                 (ctx)                 接進 msgs（只有 conquest 回字）
# advance.held    Game.advance 最後                                               (ctx)                 不接
# tick            Game.world_tick 到時的結算（on_due）之後                         (ctx)                 接進 msgs（只有 conquest 回字）
# own_turn        Game.own_turn_checks 暫停那一道之後                              (ctx)                 不接
# season.carry    Game._reset_player_for_new_season 建好新存檔之後：照帶的欄位      (ctx, old, fresh)     不接（self.state 還是舊的：格裡只准讀 old、fresh、ctx.content）
# season.grant    Game._reset_player_for_new_season 開場那一則之後                  (ctx, old)            不接
# stale.first     Game._drop_stale_references 最前面（對齊賽季之前，換季會清掉陣營） (ctx)                 不接
# stale.early     同上，補體丹之後、所在地之前                                     (ctx)                 不接
# stale.mid       同上，所在地之後、路上之前                                       (ctx)                 不接
# stale.road      同上，隊伍之前                                                   (ctx, lost_place)     不接
# stale.late      同上，等著取名之後、主線之前                                     (ctx)                 不接
SEAM_ORDER: dict[str, tuple[str, ...]] = {
    "local": ("seclusion", "fortune"),
    "sync.heirloom": ("seal",),
    "sync.close": ("smithy", "gear", "shops", "ambush", "arrive"),
    "sync.deliver": ("big_events", "results", "renames", "echoes", "guard", "notices", "conquest", "conquest.deliver", "arena",
                     "marks", "stances", "zhuan", "mail", "plans", "day", "on_sync", "held_gear", "checkin", "partings", "bounties",
                     "plots", "summons", "story", "seat", "enlist", "hints", "party"),
    "advance.arrive": ("arrive",),
    "advance.turn": ("conquest", "conquest.deliver", "due"),
    "advance.held": ("held_gear",),
    "tick": ("conquest", "battle", "seal"),
    "own_turn": ("bounties",),
    "season.carry": ("guide", "ties", "companions", "self", "mall", "sortie", "outlets", "battle", "seal", "rack", "peers", "story", "legacy", "guard"),  # guard：親衛隊長跟著帳號走（Joy 2026-11-09「其他都按照建議」：設計稿推薦跨季帶著）
    "season.grant": ("faction",),
    "stale.first": ("guide",),
    "stale.early": ("cultivation", "resting", "sense", "companions"),
    "stale.mid": ("bounties", "smithy", "gear", "shops", "treasures", "forge", "signature", "seal"),
    "stale.road": ("travel",),
    "stale.late": ("figure_acts",),
}


def seam_hooks(at: str) -> dict[str, Callable[..., Any]]:
    """at 那個位置包登記的格 {slot: run}：照 registered()、不看 enabled。每一次都驗登記的全部格：表上沒有的格、同一格登記兩次（兩包或同一包）
    都丟 ValueError（同 world_hooks、bus_hooks）。"""
    if at not in SEAM_ORDER:
        raise ValueError(f"補算與換季沒有 {at} 這個位置")
    own: dict[str, Callable[..., Any]] = {}
    for f in registered():
        for hook in f.seams():
            if hook.slot not in SEAM_ORDER.get(hook.at, ()):
                raise ValueError(f"{f.name} 登記了補算與換季表上沒有的格 {hook.at}/{hook.slot}")
            if hook.at == at:
                if hook.slot in own:
                    raise ValueError(f"補算與換季的 {at}/{hook.slot} 登記了兩次（{f.name}）")
                own[hook.slot] = hook.run
    return own


def seam_run(at: str, core: dict[str, Callable[..., Any]], *args: Any,
             hooks: dict[str, Callable[..., Any]] | None = None) -> list[Any]:
    """照 SEAM_ORDER[at] 走每一格：包登記了叫包的，沒有叫 core 那一份（核心代叫的格）；兩邊都沒有（那一格的包沒登記：契約測試換掉 FEATURES 時）
    跳過。回每一格的回傳值（照順序、跳過的不算）：接不接由呼叫端照位置決定。core 寫了表上沒有的格丟 ValueError（打錯字的格不會默默不跑）。"""
    own = seam_hooks(at) if hooks is None else hooks  # 沒有這個位置在 seam_hooks 丟
    order = SEAM_ORDER.get(at)
    if order is None:
        raise ValueError(f"補算與換季沒有 {at} 這個位置")
    if not core.keys() <= set(order):
        raise ValueError(f"核心代叫了補算與換季 {at} 表上沒有的格 {sorted(core.keys() - set(order))}")
    out: list[Any] = []
    for slot in order:
        run = own.get(slot) or core.get(slot)
        if run is not None:
            out.append(run(*args))
    return out


def seam_lines(at: str, core: dict[str, Callable[..., Any]], *args: Any) -> list[str]:
    """同 seam_run，把每一格回的那幾句照順序接成一串。每一格只准回 list 或 None，回別的丟 TypeError（回字串會被一個字一個字接進回話、回 tuple
    是把某個回傳值漏接：當場紅，不要默默進回話）；回傳不接的格（sync.deliver 的 conquest、partings、story……）包成回 None。"""
    lines: list[str] = []
    for got in seam_run(at, core, *args):
        if got is None:
            continue
        if not isinstance(got, list):
            raise TypeError(f"補算與換季 {at} 的格只准回 list 或 None，回了 {type(got).__name__}")
        lines += got
    return lines


# core_seams（全部拆包第 56 批「選單收接縫」；計畫 docs/superpowers/plans/2026-11-06-選單收接縫-第56批.md 一、二、七）


@dataclass(frozen=True)
class MenuHook:
    """選單與動身的一格（Feature.menus() 回一串）：核心在 at 那個位置照 MENU_ORDER[at] 一格一格問，輪到 slot 就叫 run。照 registered() 問、不看 enabled
    （原位那幾行本來就不看包的開關；menu、options、on_drop_stale 只問開著的包，所以接不了，第 42 批認定第 7 條）。run 的簽名照位置（MENU_ORDER 底下那張）；
    包的 run 在叫的那一下才照模組屬性或 ctx 找（monkeypatch 照樣有效）。"""

    at: str
    slot: str
    run: Callable[..., Any]


# 選單與動身的順序表：位置 → 那一個位置的格，照換成掛鉤之前一行一行的先後。順序就是行為（誰先接管整個選單、「此地還能做」誰排前面、動身被擋先說哪一句都算），
# 所以寫死、連核心自己的格一起列。包登記自己那一格（Feature.menus()），其餘由核心代叫（engine._MENU_CORE、atlas._BLOCK_CORE、travel/departure._DEPART_CORE）。
# 改這張表先過 PM；tests/core/test_contract_core.py 逐字鎖住。改格的本體或這張表另外要跑（scripts/test_for.py 挑不全）：tests/map/test_atlas.py、tianxia/features/guide/tests/ 的 test_explain、test_prologue、tianxia/features/peers/tests/test_social.py，
# tianxia/features/smithy/tests/test_shop.py，tests/figures/ 的 test_day_scale、test_gentry_allied、test_orders，與 scripts/same_behavior.py 的 stack 一軌（兩層以上疊著的先後只有它比）。
#
# 位置    核心在哪裡問                                          run 的簽名                 怎麼叫
# tick    Game.options 最前面（tick=True 才問）                   (ctx)                      menu_run，回傳不接
# front   Game.options：決戰的鈕與平常的選單前面（兩處）            (ctx)                      menu_lines
# rest    Game._everyday_options 休季那一顆後面                   (ctx)                      menu_lines
# take    Game._everyday_options 事件之後：此刻接管整個選單的       (ctx)                      menu_first（空的 [] 也算接管：髒存檔的待確認畫面真的是空選單）
# busy    Game._everyday_options 閉關中                           (ctx)                      menu_lines
# road    Game._everyday_options 在路上                           (ctx, journey)             menu_lines
# here    Game._everyday_options 站在地點上（序章的過濾之前）       (ctx, loc, cost, odds)     menu_lines
# plays   Game._stamina_play_options 序章、休季那一道之後           (ctx)                      menu_lines
# notes   Game.action_notes 探索、出陣那兩行之後                   (ctx, ids, loc)            menu_run，回 dict，照順序 update（鍵的順序算行為）
# idle    Game._idle 前五樣（籌備、休季、事件、閉關、路上）之後      (ctx)                      menu_any（有一格是真的就不算閒著）
# open    Game._shop_open                                         (ctx)                      menu_first（"" 是坐著、這裡不開門；核心 or None）
# depart  移動包 departure.depart 最前面：動身了，店收起來          (ctx)                      menu_run，回傳不接
# block   atlas.travel_block：現在不能安排前往的原因               (state, content)           menu_first（沒有 ctx：party 拿別人的 state 問，格裡一律讀傳進來的）
# quick   Game.choose 查完選單、清掉「剛剛」與引導之後、建紀錄之前  (ctx, kind, arg, option_id)  menu_first（第 57 批：選單上、不建紀錄的那幾顆；回的話由核心 _log 一次，格裡不寫紀錄。回 None 照舊往下）
# stale   Game.choose 查完選單、「此刻無法」之前：鈕過時了（兩個分頁搶）  (ctx, option, option_id)  menu_first（第二輪第 92 批；option 是選單上查到的那一顆或 None。回 Refused 就直接回給玩家，寫不寫江湖紀錄〔_log〕由格自己定；
#         回 Option 換掉查到的那一顆〔「改幫…」不在選單上照樣收〕；回 None 照舊往下。跟 SEAM_ORDER 的 stale.*〔清失效參照，讀檔那一下〕是兩件事）
MENU_ORDER: dict[str, tuple[str, ...]] = {
    "tick": ("seal",),
    "front": ("seal",),
    "rest": ("zhuan",),
    "take": ("duel", "menu", "sense", "story", "talk", "faction", "audience", "bounties", "smithy", "gear", "shops", "omen"),
    "busy": ("seclusion", "arena"),
    "road": ("head", "parley", "halt", "tasks", "arena"),
    "here": ("explore", "train", "challenge", "summons", "story", "sect", "social", "recruit", "move", "lessons", "join", "defect", "lean",
             "order", "rank2", "rank", "omen", "errand", "invite", "bounties", "smithy", "gear", "shops", "plays", "heal", "donate", "dadian", "rest"),
    "plays": ("head", "aid", "options", "plan"),
    "notes": ("socialize",),
    "idle": ("audience", "bounties", "smithy", "omen", "sense", "duel", "gear", "outlets", "tavern", "arena", "faction"),
    "open": ("arena", "bounties", "smithy", "gear", "shops"),
    "depart": ("bounties", "escort", "smithy", "gear", "shops"),
    "block": ("ended", "prologue", "event", "bout", "talk", "audience", "bounties", "smithy", "gear", "outlets", "tavern", "faction", "omen", "follow", "busy", "ambush"),
    "quick": ("battle", "seal", "duel", "arena", "errand", "canvas"),  # core_seams（全部拆包第 57 批）
    "stale": ("lean", "bounties", "market", "recruit", "arena"),  # core_choose（第二輪第 92 批）
}


def menu_hooks(at: str) -> dict[str, Callable[..., Any]]:
    """at 那個位置包登記的格 {slot: run}：照 registered()、不看 enabled。每一次都驗登記的全部格：表上沒有的格、同一格登記兩次（兩包或同一包）
    都丟 ValueError（同 seam_hooks）。"""
    if at not in MENU_ORDER:
        raise ValueError(f"選單與動身沒有 {at} 這個位置")
    own: dict[str, Callable[..., Any]] = {}
    for f in registered():
        for hook in f.menus():
            if hook.slot not in MENU_ORDER.get(hook.at, ()):
                raise ValueError(f"{f.name} 登記了選單與動身表上沒有的格 {hook.at}/{hook.slot}")
            if hook.at == at:
                if hook.slot in own:
                    raise ValueError(f"選單與動身的 {at}/{hook.slot} 登記了兩次（{f.name}）")
                own[hook.slot] = hook.run
    return own


def _menu_slots(at: str, core: dict[str, Callable[..., Any]]) -> list[Callable[..., Any]]:
    """照 MENU_ORDER[at] 排好的每一格：包登記了用包的，沒有用 core 那一份（核心代叫的格）；兩邊都沒有（那一格的包沒登記：契約測試換掉 FEATURES 時）跳過。
    core 寫了表上沒有的格丟 ValueError（打錯字的格不會默默不跑）。"""
    own = menu_hooks(at)  # 沒有這個位置在這裡丟
    order = MENU_ORDER[at]
    if not core.keys() <= set(order):
        raise ValueError(f"核心代叫了選單與動身 {at} 表上沒有的格 {sorted(core.keys() - set(order))}")
    return [run for slot in order if (run := own.get(slot) or core.get(slot)) is not None]


def menu_run(at: str, core: dict[str, Callable[..., Any]], *args: Any) -> list[Any]:
    """每一格都叫，回每一格的回傳值（照順序、跳過的不算）：接不接由呼叫端照位置決定。"""
    return [run(*args) for run in _menu_slots(at, core)]


def menu_first(at: str, core: dict[str, Callable[..., Any]], *args: Any) -> Any:
    """一格一格叫，第一個不是 None 的就回它、後面的不叫；都是 None 回 None。空的 [] 也算（take：選單整個被接管，只是一顆都沒有）。"""
    for run in _menu_slots(at, core):
        got = run(*args)
        if got is not None:
            return got
    return None


def menu_lines(at: str, core: dict[str, Callable[..., Any]], *args: Any) -> list[Any]:
    """每一格都叫，照順序接成一串。每一格只准回 list，回別的丟 TypeError（回字串會被一個字一個字接進選單、回 None 是有一支漏了 return：當場紅）。"""
    lines: list[Any] = []
    for run in _menu_slots(at, core):
        got = run(*args)
        if not isinstance(got, list):
            raise TypeError(f"選單與動身 {at} 的格只准回 list，回了 {type(got).__name__}")
        lines += got
    return lines


def menu_any(at: str, core: dict[str, Callable[..., Any]], *args: Any) -> bool:
    """一格一格叫，第一個真值就停、回 True；都不是回 False。"""
    return any(run(*args) for run in _menu_slots(at, core))


# core_scene（第二輪第 91 批「場景卡收接縫」；計畫 docs/superpowers/plans/2026-11-07-第二輪-第91批.md 第二節）


@dataclass(frozen=True)
class SceneHook:
    """場景卡的一格（Feature.scenes() 回一串）：core/scene_view.py 在 at 那個位置照 SCENE_ORDER[at] 一格一格問，輪到 slot 就叫 run(ctx)，回 None 是「不是我，往下問」。
    照 registered() 問、不看 enabled（原位那幾行本來就不看包的開關，坐席、談著、投靠的髒存檔關著開關也要照舊；options、on_drop_stale 只問開著的包，所以接不了，第 42 批認定第 7 條）。
    包的 run 在叫的那一下才照模組屬性或 ctx 找（monkeypatch 照樣有效）。"""

    at: str
    slot: str
    run: Callable[..., Any]


# 場景卡的順序表：位置 → 那一個位置的格，照換成掛鉤之前 if 鏈一支一支的先後。順序就是行為（誰蓋住誰；art 的 place 要讀整條 own 鏈來判斷是不是真的站在地點上，少一格整張圖會蓋錯或不見），
# 所以寫死、連核心自己的格一起列。包登記自己那一格（Feature.scenes()），其餘由核心代叫（core/scene_view.py 的 OWN_CORE、ART_CORE）。
# 改這張表先過 PM；tests/core/test_contract_core.py 逐字鎖住。改格的本體或這張表另外要跑（scripts/test_for.py 挑不全）：scripts/same_behavior.py 的 vista、stack 兩軌（兩層以上疊著的先後只有它們比）。
#
# 位置  核心在哪裡問                       每一格回什麼
# own   core/scene_view._own_scene_text    那一張的 Markdown；""（取名的意境不在了）也算接管
# art   core/scene_view.scene_art          {} 是「這個畫面是我的，沒有圖」、非空 dict 是那張圖（scene_art 把 {} 換回 None）。答題、取名不在表上是刻意的：疊在談著上面時文字是答題、圖是人像
SCENE_ORDER: dict[str, tuple[str, ...]] = {
    "own": ("ended", "event", "duel", "arena", "feast", "sense", "story", "talk", "ally", "faction", "defect", "audience", "omen", "road", "place"),
    "art": ("ended", "battle", "event", "bout", "feast", "sense", "talk", "place"),
}


def scene_hooks(at: str) -> dict[str, Callable[..., Any]]:
    """at 那個位置包登記的格 {slot: run}：照 registered()、不看 enabled。每一次都驗登記的全部格：表上沒有的格、同一格登記兩次（兩包或同一包）
    都丟 ValueError（同 menu_hooks）。"""
    if at not in SCENE_ORDER:
        raise ValueError(f"場景卡沒有 {at} 這個位置")
    own: dict[str, Callable[..., Any]] = {}
    for f in registered():
        for hook in f.scenes():
            if hook.slot not in SCENE_ORDER.get(hook.at, ()):
                raise ValueError(f"{f.name} 登記了場景卡表上沒有的格 {hook.at}/{hook.slot}")
            if hook.at == at:
                if hook.slot in own:
                    raise ValueError(f"場景卡的 {at}/{hook.slot} 登記了兩次（{f.name}）")
                own[hook.slot] = hook.run
    return own


def scene_first(at: str, core: dict[str, Callable[..., Any]], ctx: Game) -> Any:
    """照 SCENE_ORDER[at] 一格一格叫：包登記了用包的，沒有用 core 那一份（核心自己的格）；兩邊都沒有（那一格的包沒登記：契約測試換掉 FEATURES 時）跳過。
    第一個不是 None 的就回它、後面的不叫（""、{} 也算接管）；都是 None 回 None。core 寫了表上沒有的格丟 ValueError（打錯字的格不會默默不跑）。"""
    own = scene_hooks(at)  # 沒有這個位置在這裡丟
    order = SCENE_ORDER[at]
    if not core.keys() <= set(order):
        raise ValueError(f"核心代叫了場景卡 {at} 表上沒有的格 {sorted(core.keys() - set(order))}")
    for slot in order:
        run = own.get(slot) or core.get(slot)
        if run is None:
            continue
        got = run(ctx)
        if got is not None:
            return got
    return None


# howto（全部拆包第 59 批「引導二」；計畫 docs/superpowers/plans/2026-11-06-玩法說明-第59批.md 第二節）


@dataclass(frozen=True)
class HowtoPage:
    """玩法說明那一頁呼叫端算好傳進來的兩樣（guide/howto.py 的 page）。recruitable：內容裡有沒有能招募的人物；rule：收季規則那一句。"""

    recruitable: bool = False
    rule: str = ""


@dataclass(frozen=True)
class HowtoHook:
    """玩法說明的一格（Feature.howto() 回一串）：lines(content, season, page) 回這一格的那幾行（空行與標題都算在格裡，全部接起來 "\n".join 之後
    才一字不差；這一格沒有句子回 []，不准回字串、None）。不看 enabled：判斷都在各節自己裡面（換成掛鉤之前也不看）。包的函式在叫的那一下才照模組屬性找。"""

    slot: str
    lines: Callable[..., list[str]]


# 玩法說明的順序表：照換成掛鉤之前 howto.page 一段一段接的先後。先後就是行為（那一頁由上往下寫），寫死在這裡、不照 FEATURES。改這張表先過 PM；
# tests/core/test_contract_core.py 逐字鎖住。
#
# 格         主人                 回什麼
# season     新手引導 guide       「這一季在打什麼」一節
# act_head   新手引導 guide       「行動」的標題
# explore    探索 explore         探索那一行（探索一顆或舊探索）
# growth     新手引導 guide       減法季的成長那幾行
# sortie     出陣 sortie          出陣那幾行（地盤開著）或舊遊歷
# socialize  交友求見 socialize   交友那一行
# travel     移動 travel          移動那一行
# ambush     體力玩法 stamina_plays 設伏那一行（開著才有）
# stamina    新手引導 guide       「體力」一節（開頭多一個空行）
# fame       新手引導 guide       「名聲」或「名望」一節
# join       陣營 faction         「投靠與軍令」一節
# factions   陣營 faction         「各陣營有什麼不同」一節
# land       地盤行動 territory_acts 「地盤」一節（地盤開著才有）
# bond       人物情誼 companions  「情誼」一節
# challenge  大勢人物 figure_acts 「挑戰大勢人物」一節（有句子才有）
# xinde      修練 cultivation     「心得」一節
# pages      修練 cultivation     「修練與煉製」一節
# forge      鐵匠鋪 smithy        「鐵匠鋪與神器」一節
# insight    有所感 sense         「意境」一節
# bag        新手引導 guide       「背包」一節（沒有末尾空行）
# economy    銀兩出口 outlets     「素材的出路」一節（有句子才有，開頭多一個空行）
# mall       商城 mall            「商城」一節（有句子才有，開頭多一個空行）
HOWTO_ORDER: tuple[str, ...] = (
    "season", "act_head", "explore", "growth", "sortie", "socialize", "travel", "ambush", "stamina", "fame", "join", "factions", "land",
    "bond", "challenge", "xinde", "pages", "forge", "insight", "bag", "economy", "mall",
)
# 別節中間的那幾句（那一節的主人寫到這一格就問，判斷在別包）：fame_seal、fame_tavern 在名聲的來源裡（guide 的 _fame_sources），land_seal 在
# 地盤那一節倒數第二句（territory_acts 的 conquest_lines）。主人是玉璽 seal、酒肆 tavern。
HOWTO_INSERTS: tuple[str, ...] = ("fame_seal", "fame_tavern", "land_seal")


def howto_hooks() -> dict[str, HowtoHook]:
    """包登記的格 {slot: HowtoHook}：照 registered()、不看 enabled。每一次都驗登記的全部格：表上沒有的格、同一格登記兩次（兩包或同一包）
    都丟 ValueError（同 step_hooks）。"""
    own: dict[str, HowtoHook] = {}
    for f in registered():
        for hook in f.howto():
            if hook.slot not in HOWTO_ORDER and hook.slot not in HOWTO_INSERTS:
                raise ValueError(f"{f.name} 登記了玩法說明表上沒有的格 {hook.slot}")
            if hook.slot in own:
                raise ValueError(f"玩法說明的 {hook.slot} 登記了兩次（{f.name}）")
            own[hook.slot] = hook
    return own


def howto_table() -> list[HowtoHook]:
    """照 HOWTO_ORDER 排好的每一格；沒人登記的格跳過（那一格的包沒登記：契約測試換掉 FEATURES 時）。"""
    own = howto_hooks()
    return [own[slot] for slot in HOWTO_ORDER if slot in own]


def howto_insert(slot: str, content: Content, season: WorldState) -> list[str]:
    """別節中間的那幾句：只認 HOWTO_INSERTS（寫錯丟 ValueError）；沒人登記回 []。"""
    if slot not in HOWTO_INSERTS:
        raise ValueError(f"玩法說明沒有 {slot} 這個插句")
    hook = howto_hooks().get(slot)
    return [] if hook is None else hook.lines(content, season, HowtoPage())


# ── shell_web（全部拆包第 66 批；計畫 docs/superpowers/plans/2026-11-06-網頁殼化-第66批.md 第四節）：狀態列與 /api/main 的格 ──


@dataclass(frozen=True)
class StatusHook:
    """狀態列（table "status"，Game.status_data）、江湖畫面（table "main"，server._main_view_body）或管理頁（table "admin"，features/admin/routes.py 的 admin_choices）的一格（Feature.status_slots() 回一串）：
    status_run 照 STATUS_ORDER[table] 一格一格叫 run(ctx, frame)，回的鍵照順序合進去（這一下沒有鍵回 {}，回別的丟 TypeError）。frame：status、admin 表是
    目前合到一半的那一份 dict，main 表是 MainFrame。照 registered() 問、不看 enabled（原位那幾行本來就不看包的開關，關著的也要有 null）。
    包的函式在叫的那一下才照模組屬性找（monkeypatch 照樣有效）。"""

    table: str
    slot: str
    run: Callable[[Any, Any], dict]


@dataclass
class MainFrame:
    """main 表每一格拿到的：status、options、card 是殼一開頭算好的（會推進全服戰鬥的選單只叫一次，所以照原本的順序一格一格叫，不是先全叫完再排鍵）；
    view 是合到一半的畫面（入伍段的 glow 那一格改 view["guide"]）；shell 是 server 模組（同 routes(shell)：server.figure_face 這些照舊打得到）；
    orders 是 orders 那一格算好留給 week_card 那一格的（殼的兩格，核心的本週卡也讀同一份）。"""

    status: dict
    options: list
    card: Any
    view: dict
    shell: Any
    orders: list = field(default_factory=list)


# 狀態列與江湖畫面的順序表：照換成掛鉤之前 Game.status_data、server._main_view_body 一段一段寫的先後。先後就是行為（JSON 鍵的先後閘門逐位元組比；
# 叫的先後也算：選單會推進全服戰鬥），寫死在這裡、不照 FEATURES。表上的格一格不挪；新包的格不用列進來，表外的接在表尾、照登記的先後（第二輪第 74 批，同 action_table）。
# 包登記自己那幾格（Feature.status_slots()）；核心的格是 engine 的 status_data、
# 殼的格是 server._main_view_body 傳進來的閉包。改這張表先過 PM（性質同 BUS_ORDER）；tests/core/test_contract_core.py 逐字鎖住。條件鍵的判斷（is not None
# 才放、if mostly、if orders）照原位搬，不統一。
#
# status 表（Game.status_data）
# 格            主人                 鍵
# head          核心                 name, affiliation, ranger, renown
# bounties      懸賞 bounties        bounties
# manual        核心                 manual, manual_total
# seal          玉璽 seal            seal_duel, seal, seal_watch
# armament      銀兩出口 outlets     armament
# forge_manual  核心                 forge_manual
# create        煉製與自創 craft     create
# ascension     修練 cultivation     ascension
# self          核心                 anonymous … pills
# newbie        引導 guide           newbie
# vitals        核心                 hp … busy_hours（含 growth、lilian 兩個條件鍵）
# journey       移動 travel          journey
# calendar      核心                 calendar, next_event（第一季）
# help          核心                 stamina_help, howto_entry（讀 frame["pills"]）
# checkin       簽到 checkin         checkin（None 沒有鍵）
# war           核心                 fronts … war_help（第一季）
# invites       玩家互動 peers       invites（第一季）
#
# main 表（server._main_view_body）
# 格            主人                     鍵
# screen        殼                       status, quest, scene, art, options
# outing        探索 explore             outing
# say_max       人物情誼 companions      say_max
# sortie        出陣 sortie              sortie
# modes         殼                       precise, training
# action_notes  殼                       action_notes
# sense_help    有所感 sense             sense_help
# on_road       移動 travel              on_road
# free_text     殼                       free_text, free_text_note, free_op, event_free_text, event_tier, story_cards, keepsakes, card, card_id
# gauges        決戰 battle              battle_gauge, card_gauge
# journal       殼                       latest, journal, older, now, front
# peers         玩家互動 peers           here, calls
# party         移動 travel              party
# news          殼                       bulletin, trends, rumors, chronicle
# tales         戰記 tale                tales
# admin         殼                       admin, paused
# guide         引導 guide               guide, prologue, onboard
# horse_art     殼                       horse_art
# push          殼                       push, push_spread
# web_push      手機通知 notify          web_push
# shop          殼                       shop
# prep          殼                       prep
# milestone     修練 cultivation         milestone
# features      殼                       Game.feature_status()（FEATURES 的 status：mall、looks、legacy、hire）
# glow          引導 guide               改 view["guide"]["glow"]，沒有鍵
# fronts        殼                       fronts
# orders        殼                       orders（順手存 frame.orders）
# week_card     殼                       week_card
# mostly        探索 explore             mostly
# sides_card    陣營 faction             sides_card
# figures_here  交友求見 socialize       figures_here
# companions    人物情誼 companions      talk, figure, errands
# event_opts    殼                       event_opts
# rumor_layers  殼                       rumor_layers
# convoy        軍情 military            convoy
# conquest      地盤 territory_acts      conquest
# sortie_cards  出陣 sortie              sortie_card, sorties
# siege         決戰 battle              siege
# xingshi       地盤 territory_acts      xingshi, xingshi_mark
# plan          大勢人物的行動 figure_acts  plan
# place_state   殼                       place_state
# place_deeds   大勢人物的行動 figure_acts  place_deeds
# letter        人物情誼 companions      letter
# zhuan         列傳 zhuan               zhuan
# season_result 殼                       season_result
# ending        陣營 faction             ending
#
# admin 表（features/admin/routes.py 的 admin_choices，第二輪第 90 批；frame 是合到一半的 dict）
# 格                 主人                     鍵
# phase              管理者 admin             phase
# battles            決戰 battle              battles
# events             管理者 admin             events
# trends             管理者 admin             trends
# timetable          管理者 admin             timetable, results, locks
# season_one         管理者 admin             season_one
# season21           管理者 admin             season21
# realign            管理者 admin             realign
# default_dates      管理者 admin             default_dates
# mandate_at         管理者 admin             mandate_at
# showdowns          決戰 battle              showdowns
# next_has_timetable 管理者 admin             next_has_timetable
# fallen             大勢人物的行動 figure_acts  fallen
# seal               玉璽 seal                seal
# xingshi            地盤 territory_acts      xingshi
# conquest           地盤 territory_acts      conquest
# mingtie            玩家互動 peers           mingtie
# divine_out         管理者 admin             divine_out
# llm_queue          管理者 admin             llm_queue
# now                管理者 admin             now
STATUS_ORDER: dict[str, tuple[str, ...]] = {
    "status": ("head", "bounties", "manual", "seal", "armament", "forge_manual", "create", "ascension", "self", "newbie", "vitals", "journey",
               "calendar", "help", "checkin", "war", "invites"),
    "main": ("screen", "outing", "say_max", "sortie", "modes", "action_notes", "sense_help", "on_road", "free_text", "gauges", "journal", "peers",
             "party", "news", "tales", "admin", "guide", "horse_art", "push", "web_push", "shop", "prep", "milestone", "features", "glow", "fronts",
             "orders", "week_card", "mostly", "sides_card", "figures_here", "companions", "event_opts", "rumor_layers", "convoy", "conquest",
             "sortie_cards", "siege", "xingshi", "plan", "place_state", "place_deeds", "letter", "zhuan", "season_result", "ending"),
    "admin": ("phase", "battles", "events", "trends", "timetable", "season_one", "season21", "realign", "default_dates", "mandate_at", "showdowns",
              "next_has_timetable", "fallen", "seal", "xingshi", "conquest", "mingtie", "divine_out", "llm_queue", "now"),
}


def slot_some(key: str, value: Any) -> dict:
    """「不是 None 才有這個鍵」那幾格的寫法（if mostly、if orders 那種看真假的照原位自己寫）。"""
    return {} if value is None else {key: value}


def status_hooks(table: str) -> dict[str, Callable[[Any, Any], dict]]:
    """table 那一張包登記的格 {slot: run}：照 registered()、不看 enabled。每一次都驗登記的全部格：表名不在 STATUS_ORDER、同一格登記兩次（兩包或同一包）
    都丟 ValueError（同 bus_hooks、step_hooks）。格不在那張表上不丟：是新包接在表尾的，status_run 照登記的先後叫（第二輪第 74 批）。"""
    if table not in STATUS_ORDER:
        raise ValueError(f"狀態列沒有 {table} 這一張表")
    own: dict[str, Callable[[Any, Any], dict]] = {}
    seen: set[tuple[str, str]] = set()
    for f in registered():
        for hook in f.status_slots():
            if hook.table not in STATUS_ORDER:
                raise ValueError(f"{f.name} 登記了狀態列沒有的表 {hook.table}/{hook.slot}")
            if (hook.table, hook.slot) in seen:
                raise ValueError(f"狀態列的 {hook.table}/{hook.slot} 登記了兩次（{f.name}）")
            seen.add((hook.table, hook.slot))
            if hook.table == table:
                own[hook.slot] = hook.run
    return own


def status_run(table: str, core: dict[str, Callable[[Any, Any], dict]], frame: Any, ctx: Game) -> dict:
    """照 STATUS_ORDER[table] 走每一格：包登記了叫包的，沒有叫 core 那一份（核心或殼的閉包）；兩邊都沒有（那一格的包沒登記：契約測試換掉 FEATURES 時）
    跳過。走完表再走包登記的表外格（接在表尾，照登記的先後）。每一格回的 dict 照順序合進 frame（main 表是 frame.view），回那一份。core 寫了表上沒有的格
    丟 ValueError（只有包能接尾巴；核心打錯字的格不會默默不跑）；某一格回的不是 dict 丟 TypeError。"""
    own = status_hooks(table)  # 沒有這一張表在 status_hooks 丟
    order = STATUS_ORDER[table]
    on_table = set(order)
    if not core.keys() <= on_table:
        raise ValueError(f"核心代叫了狀態列 {table} 表上沒有的格 {sorted(core.keys() - on_table)}")
    into = frame.view if isinstance(frame, MainFrame) else frame
    for slot in (*order, *(s for s in own if s not in on_table)):
        run = own.get(slot) or core.get(slot)
        if run is None:
            continue
        got = run(ctx, frame)
        if not isinstance(got, dict):
            raise TypeError(f"狀態列的 {table}/{slot} 回的不是 dict：{type(got).__name__}")
        into.update(got)
    return into


# ── shell_server（全部拆包第 68 批「伺服器分包一」；計畫 docs/superpowers/plans/2026-11-06-伺服器分包-第68批.md 第五節）：
# 殼的 MAIN_ACTIONS、MENXIA_ACTIONS 照包分（Feature.main_actions、menxia_actions）；管理者那一張走現成的 admin_tools，這裡只多一個沒有總開關的 gate。
# 兩個新掛鉤同 admin_tools：殼啟動時問、不看 enabled、登記的全掛、兩包同名丟例外。 ──


def no_gate() -> None:
    """沒有總開關的管理者工具共用（原本 ADMIN_ACTIONS 那些本來就沒有 404）：什麼都不擋，各動作自己驗。"""


def _merged_actions(tables: list[dict[str, Callable[[Any, dict], Any]]], label: str) -> dict[str, Callable[[Any, dict], Any]]:
    out: dict[str, Callable[[Any, dict], Any]] = {}
    for table in tables:
        for op, fn in table.items():
            if op in out:
                raise ValueError(f"{label} {op} 兩包都有")
            out[op] = fn
    return out


def main_actions(shell: Any) -> dict[str, Callable[[Any, dict], Any]]:
    """各包的 /api/do/{op}（殼的 MAIN_ACTIONS；關著的包也列，各動作自己回一句）。兩包同名丟例外。"""
    return _merged_actions([f.main_actions(shell) for f in registered()], "玩家動作")


def menxia_actions(shell: Any) -> dict[str, Callable[[Any, dict], Any]]:
    """各包的 /api/menxia/{op}（殼的 MENXIA_ACTIONS；關著的包也列，各動作自己回一句）。兩包同名丟例外。"""
    return _merged_actions([f.menxia_actions(shell) for f in registered()], "修練頁動作")


def action_table(order: tuple[str, ...], core: dict[str, Callable[[Any, dict], Any]],
                 packages: dict[str, Callable[[Any, dict], Any]]) -> dict[str, Callable[[Any, dict], Any]]:
    """殼的一張動作表（普通 dict，測試照舊 setitem、取值）：照寫死的 order 排，核心留在殼的與各包的穿插。
    order 上有、沒人提供丟例外（包登記漏了，開機就知道）；核心與包同名丟例外；order 外的（之後新包加的）接在後面。"""
    both = sorted(set(core) & set(packages))
    if both:
        raise ValueError(f"動作 {both} 殼與包都有")
    merged = {**core, **packages}
    missing = [op for op in order if op not in merged]
    if missing:
        raise ValueError(f"動作 {missing} 沒有人提供")
    table = {op: merged[op] for op in order}
    for op, fn in merged.items():
        table.setdefault(op, fn)
    return table


# ── shell_server（全部拆包第 69 批「伺服器分包二」；計畫 docs/superpowers/plans/2026-11-06-伺服器分包-第69批.md 第四節）：
# 鎖外工作（三段式的 B 段與放鎖之後才開的背景寫字）進各包的 routes.py，殼只留框架。同 main_actions：殼啟動時問、不看 enabled（原本這幾條本來就不看包的開關）、
# 登記的全掛。模型呼叫絕不進鎖：ops 在 api_do 裡、鎖外叫；jobs 的 waiting 在鎖內問（只讀、不叫模型），start 放鎖之後才開。 ──


# 放鎖之後要開的背景寫字，先後就是這一張（原本 server.act 那六行的順序；問與開都照它，順序算行為）。戰記的 tale_round 照舊在 threads 掛鉤（定時背景，不是動作之後才開）。
# 表上的格一格不挪；新包的格不用列進來，表外的接在表尾、照登記的先後（第二輪第 74 批，同 action_table）。
OUTLOCK_ORDER: tuple[str, ...] = ("tale", "crowd", "chatter", "letter", "yuedan", "xingshi")


@dataclass(frozen=True)
class OutlockJob:
    """放鎖之後才開的一條背景寫字。waiting(game)：行動鎖內問（只讀、不叫模型），回真值才算有；start(game, got)：鎖放掉之後才叫，got 是 waiting 回的那個值（酒肆閒談是地點 id）。"""

    slot: str  # OUTLOCK_ORDER 上的一格，或包自己接在表尾的格
    waiting: Callable[[Any], Any]
    start: Callable[[Any, Any], Any]


@dataclass(frozen=True)
class Outlock:
    """一包的鎖外工作。ops：/api/do/{op} 先接走的那幾條 {op: fn(game, body)}，自己拿鎖、自己照三段式走（不經 act 包一層）；jobs：放鎖之後要開的背景寫字。"""

    ops: dict[str, Callable[[Any, dict], Any]] = field(default_factory=dict)
    jobs: tuple[OutlockJob, ...] = ()


def outlock_ops(shell: Any) -> dict[str, Callable[[Any, dict], Any]]:
    """各包的鎖外 /api/do/{op}（殼的 OUTLOCK_OPS；關著的包也列，各動作自己回一句）。兩包同名丟例外。"""
    return _merged_actions([f.outlock(shell).ops for f in registered()], "鎖外工作")


def outlock_jobs(shell: Any) -> tuple[OutlockJob, ...]:
    """各包的背景寫字（殼的 OUTLOCK_JOBS），照 OUTLOCK_ORDER 排，表外的格接在表尾（照登記的先後）。兩包同格、表上沒人登記都丟例外（開機就知道）。"""
    by_slot: dict[str, OutlockJob] = {}
    for f in registered():
        for job in f.outlock(shell).jobs:
            if job.slot in by_slot:
                raise ValueError(f"背景寫字 {job.slot} 兩包都有")
            by_slot[job.slot] = job
    missing = [slot for slot in OUTLOCK_ORDER if slot not in by_slot]
    if missing:
        raise ValueError(f"背景寫字 {missing} 沒有人登記")
    return (*(by_slot[slot] for slot in OUTLOCK_ORDER), *(job for slot, job in by_slot.items() if slot not in OUTLOCK_ORDER))


# core_api（第二輪第 72 批「一行委派進各包的表」；計畫 docs/superpowers/plans/2026-11-07-第二輪-第72批.md）：
# Game 上包的一行委派搬進 features/<包>/game_api.py 的 TABLE（名字 → 函式本身），engine.py 檔尾掛一次，`g.xxx` 照舊。
def game_api_tables() -> dict[str, dict[str, Callable | str]]:
    """各包的 TABLE：照資料夾名排序、檔在才收。不經 registry：`import tianxia.engine` 這一刻 registry 還沒載，它一載就多載一串包，
    sys.modules 的先後會變；用 import_module，因為這裡只讀表、不用包的東西。"""
    import importlib  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    root = Path(__file__).resolve().parent.parent / "features"
    return {path.parent.name: importlib.import_module(f"tianxia.features.{path.parent.name}.game_api").TABLE
            for path in sorted(root.glob("*/game_api.py"))}


def attach_game_api(cls: type, tables: dict[str, dict[str, Callable | str]] | None = None) -> None:
    """把 TABLE 掛上類別（setattr 函式本身，不包；第 98 批起另有幾格是字，原本是 Game 的類別屬性）。同名丟例外：類別本體已經有、或兩包都掛同一個名字；
    先全部查完才掛。"""
    tables = game_api_tables() if tables is None else tables
    owners: dict[str, str] = {}
    for package, table in tables.items():
        for name in table:
            if name in vars(cls):
                raise ValueError(f"{package}/game_api.py 的 {name}：{cls.__name__} 上已經有這個名字")
            if name in owners:
                raise ValueError(f"{package}/game_api.py 的 {name}：{owners[name]} 也掛了這個名字")
            owners[name] = package
    for table in tables.values():
        for name, value in table.items():
            setattr(cls, name, value)


# core_choose（第二輪第 92 批；計畫 docs/superpowers/plans/2026-11-07-第二輪-第92批.md 第二節）


def scratch_init(ctx: Game) -> None:
    """每一包宣告的旗標（Feature.scratch）擺上這一份 Game。Game.__init__ 在 _drop_stale_references 正上方叫：那一支會換季、跑掛鉤，會讀旗標；
    _kin、_load_kin、_admin_target 開的 Game 都走 __init__，一樣有。走 registry.DECLARED、不走 registered()、不看 enabled（理由同 pack_content）：
    測試常把 FEATURES 換掉再建 Game，核心的 combat、pushing、choose 照樣讀這些旗標，少了就 AttributeError。"""
    from .registry import DECLARED  # noqa: PLC0415  同 pack_content

    for f in DECLARED:
        for name, value in f.scratch().items():
            setattr(ctx, name, value)
