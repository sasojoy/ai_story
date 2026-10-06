"""全服狀態：所有玩家共讀共寫的一份資料（設計文件四.3／四.4／六.2）——資料模型與存取介面。

存的東西：
- **自創武學命名登記與煉製配方**：武學名稱同一季全服不能重名；配方的結果全服共享，第一個煉出來的人定義它。
- **同伴性情漂移**：歷史人物的「當下性情」是全服玩家共同形塑的；這裡只存 tag 累積計數與語意化後的一句話
  （把計數轉成一句話是 companion_agent.py 的事）。
- **同伴進度與招募狀態**：每位歷史人物全服唯一（設計文件四.4），等級／武學是人物本身的屬性，不是某個玩家
  存檔裡的副本；玩家存檔只留「我對這位人物的好感度」。
- **共享賽季**（大勢、門檻、主線、結局）、投靠名冊、全服決戰，以及跨季的傳國玉璽碎片。

怎麼存不在這個模組：`WorldStateStore` 是介面（線上架構設計第二、三節）。第 1 期的實作是
`sqlite_world.SqliteWorldStore`：每個會寫的方法自己是一筆交易，呼叫端在 action_lock() 裡時併進那一筆。
第 2 期的世界主迴圈會換成「記憶體裡一份＋每個動作寫進資料庫」，介面不變。
"""
from __future__ import annotations

import random
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from .battle_instance import BattleInstance, BattleRoundRecord
from .martial_arts import Insight, MartialArt
from .models import DEFAULT_SEASON_DAYS, BattleDef, Content
from .state import Rumor, WorldState

SeasonPhase = Literal["preparing", "running", "resting"]  # 籌備（管理者還沒開季）／進行中／休季（這一季已結束）

JADE_SEAL_FRAGMENT_COUNT = 7  # 設計文件九.2：七塊碎片＝跨季長線，不是單季目標


class JadeSealFragment(BaseModel):
    """跨季持久記錄的一塊傳國玉璽碎片（設計文件九）：找到後永遠留在這裡，不會因為任何
    玩家開新季、甚至之後換到別的季別劇本而被清掉——這正是「跨季」的字面意思。"""

    number: int  # 第幾塊（1~JADE_SEAL_FRAGMENT_COUNT），依找到的先後順序
    finder: str  # 找到的玩家名號
    season_name: str  # 當時是哪一季主題劇本找到的（例如「黃巾之亂」）
    text: str  # 給玩家看的一句話紀錄（通常取自觸發事件的 chronicle 文字）


class CompanionProgress(BaseModel):
    """一位歷史人物（可招募的 7 位）目前的等級/武學/招募狀態，全服共用一份。"""

    level: int = 1
    exp: int = 0
    neili: float | None = None  # 氣血，None＝回滿（滿＝上限 − 內傷）
    injury: float = 0.0  # 內傷，同 state.Member.injury
    neigong_id: str | None = None
    neigong_level: int = 1
    wugong_id: str | None = None
    wugong_level: int = 1
    owner: str | None = None  # 目前招募他的玩家名號；None＝自由之身，誰都能嘗試招募


class SharedWorldState(BaseModel):
    companion_tag_counts: dict[str, dict[str, int]] = Field(default_factory=dict)  # 人物 id -> {tag: 次數}
    companion_drift_note: dict[str, str] = Field(default_factory=dict)  # 人物 id -> 目前漂移後的一句話性情
    companion_drift_synthesized_at: dict[str, int] = Field(default_factory=dict)  # 人物 id -> 上次語意化時的 tag 總數
    companions: dict[str, CompanionProgress] = Field(default_factory=dict)  # 人物 id -> 進度/招募狀態
    event_flavor: dict[str, str] = Field(default_factory=dict)  # 江湖大事 id -> 全服共用的一次性潤色句（設計文件 8.2 第 4 點）
    jade_seal_fragments: list[JadeSealFragment] = Field(default_factory=list)  # 跨季持久（設計文件九.2）

    # ── 共享賽季（真正共享的大勢/門檻/主線/結局，取代原本每個玩家各自獨立的 WorldState）──
    # 上面那些欄位不跟著 season 整個換掉，但換季時同伴進度會照「跨季不滾雪球」清空，玉璽碎片等才是
    # 永遠留著；武學命名、煉製配方、投靠名冊每季各一份（存在各自的表裡，見 sqlite_world），換季自然是空的。
    # season 本身每次開新賽季會被整個換掉（見 next_season）。season_number 從 1 起算，
    # season_last_real 是這個賽季的共用時鐘上次對到現實時間的時間點（None＝還沒對過）。
    season: WorldState = Field(default_factory=WorldState)
    season_number: int = 1
    season_last_real: float | None = None
    season_opened: bool = False  # 這一季管理者開季了沒；False＝籌備中（見 season_phase）
    # 賽季時鐘暫停（線上架構設計第四節、8.3「公告停機時賽季時鐘暫停，季末跟著往後延」）：按「暫停」的現實時間；None＝沒有暫停。
    # 暫停中補算（catch_up_season）不推季的時間、對時點也不動；引擎（Game）不推決戰、選單只剩一顆灰的、不能快轉，
    # 管理者的動作只留「繼續」；伺服器擋住不走選單的動作（server._refuse_while_paused）、假人程式不出手；
    # 按「繼續」時對時點往後挪停的長度（resume_clock），進行中的決戰期限與排好的決戰也跟著挪，
    # 所以停的這一段不算進賽季。舊資料沒有這一欄＝沒有暫停
    paused_at: float | None = None
    tianji: int = 0  # 天機：每次換季 +1，自創武學「名字 → 數值」的配方跟著換（跨季不滾雪球第三條）

    # ── 全服即時多人戰鬥（設計討論：集結選陣營→逐幕逐回合鎖步）────────
    # 同一時間最多一場（先簡化成這樣；真的需要同時好幾場再擴充成 list/dict）。
    active_battle: BattleInstance | None = None

    def season_phase(self) -> SeasonPhase:
        if not self.season.storyline or not self.season_opened:
            return "preparing"
        return "resting" if self.season.ended else "running"


def fresh_season(content: Content) -> WorldState:
    """照劇本種出一季全新的共用賽季（大勢起始值、公開的大勢線、第一條主線），並蓋上當下的章（stamp_season）。
    seed_first_season、next_season 都走這裡；籌備中的季在管理者開季時再蓋一次（open_season）。"""
    from .rules import seed_trends  # rules → world_state：在函式裡 import，避免循環

    season = WorldState(storyline=content.scenario.storylines[0].id)
    stamp_season(season, content)  # 先蓋章：種哪些大勢線看這一季的章（rules.seed_trends）
    seed_trends(season, content)
    return season


def stamp_season(season: WorldState, content: Content) -> None:
    """把當下的開關與季長蓋章在這一季上（計畫 T2「舊季不會被補算」）：之後換了設定，這一季照它自己的章走。
    開關開著時順便填決戰與季末的預設時間（管理者開季後可以改，T10）。只在季還沒開始時呼叫：種季、換季、開季。"""
    from .figures import seed  # noqa: PLC0415  延後 import：figures → rules → world_state
    from .timetable import default_schedule  # noqa: PLC0415  延後 import：timetable → rules → world_state

    cfg = content.config
    season.season_one = cfg.season_one
    season.length_days = cfg.season_days
    season.schedule = default_schedule(content, season) if cfg.season_one else {}  # 照剛蓋好的季長排
    season.figures = {}
    if cfg.season_one:  # 大勢人物照人物表種好（T4）：時刻表的 only_if、伏筆的出面人物從第一刻起就看得到每一位
        seed(season, content)


def season_length_days(season: WorldState, content: Content) -> float:
    """這一季有幾個遊戲日：照開季時蓋的章；T2 之前開的季沒有章，一律照它開季時的長度（DEFAULT_SEASON_DAYS，
    那些季都是用預設設定開的），不跟著現在載入的設定走——換成週末設定的 2.5 天也不會把它收掉（FB-037）。"""
    return season.length_days if season.length_days is not None else DEFAULT_SEASON_DAYS


def jade_seal_summary(fragments: list[JadeSealFragment]) -> str:
    if not fragments:
        return "傳國玉璽的七塊碎片，至今尚無人尋獲過一塊。"
    lines = [f"傳國玉璽：{len(fragments)}/{JADE_SEAL_FRAGMENT_COUNT} 塊碎片已現世——"]
    lines += [f"　第 {f.number} 塊：{f.finder}（{f.season_name}）{f.text}" for f in fragments]
    return "\n".join(lines)


class WorldStateStore(Protocol):
    """全服狀態的存取介面。引擎只認這個介面，實作見 sqlite_world.SqliteWorldStore。

    交易：每個會寫的方法自己就是一筆交易（讀→改→寫回一起成功或一起撤回）；呼叫端在 action_lock()
    裡時，併進那一筆。「補算時間＋做動作＋存檔」整段一律包在 action_lock() 裡（server.py、假人程式）。"""

    def action_lock(self, timeout: float | None = None) -> AbstractContextManager[object]:
        """一個動作＝一筆交易（線上架構設計 3.1）。timeout=None 等到拿到為止（伺服器）；給秒數時等不到就丟
        TimeoutError（假人程式跳過這一輪，不卡住正在等 LLM 的真人）。出錯時整個動作一起撤回。可以巢狀。"""
        ...

    def read(self) -> SharedWorldState: ...

    def mutate(self, fn: Callable[[SharedWorldState], None]) -> SharedWorldState:
        """讀取→套用 fn(state)→寫回，同一筆交易，回傳套用後的狀態。fn 直接原地修改 state。
        fn 裡面不能再呼叫會寫入的 store 方法（mutate、mutate_season、mutate_battle、update_companion 等）：
        內層寫的會被外層最後的整份存檔蓋掉，實作遇到巢狀會直接丟 RuntimeError。交易本身（action_lock）可以巢狀，
        不可以的只有 mutate 這一類「整份讀、整份寫」的區段。"""
        ...

    # ── 武學命名登記與煉製配方（這一季）──
    def get_skill(self, name: str) -> MartialArt | None:
        """這一季登記過的自創或煉製功法（自創功法的 id 就是它的名字）；沒有就是 None。"""
        ...

    def is_skill_name_taken(self, name: str) -> bool: ...

    def is_character_name(self, name: str) -> bool:
        """name 是不是江湖上某個角色的名號（真人、假人一樣，不分大小寫、不管前後空白，同 characters.name_key）。
        給命名過濾用（FB-069：武學、意境不能取成角色的名號）；只回是或不是，不透露那個角色是不是假人。"""
        ...

    def claim_skill_name(self, art: MartialArt) -> bool:
        """把 art 登記成這一季的自創武學；名字已經有人用過就不登記。回傳有沒有登記成功（原子判斷，
        不會有兩個玩家同時取到同一個名字都成功）。"""
        ...

    def lookup_recipe(self, key: str) -> MartialArt | None:
        """這個配方這一季已經有人煉出來過嗎？有就回傳登記在案的那一門（全服看到同一個結果）。"""
        ...

    def recipe_keys(self) -> set[str]:
        """這一季已經有人煉出來的配方鍵。"""
        ...

    def claim_recipe(self, key: str, art: MartialArt) -> tuple[MartialArt | None, bool]:
        """登記配方與功法，回傳（這個配方的功法, 是不是首創），原子判斷。三種結果：
        - 配方已經有人登記 → 回傳登記在案的那一門與 False（配方的結果全服共享，無限煉製設計 §十二 第 1 點）。
        - 配方還沒人登記、art.name 也還沒被占用 → 登記，回傳 (art, True)。
        - 配方還沒人登記、但 art.name 已經被別人的自創功法或別的配方占用 → 回傳 (None, False)，
          呼叫端換一個名字再試（取名自創仍然是獨佔的）。"""
        ...

    # ── 改名、合併出來的意境、第一個練成絕學的人（武學與成長設計 3.2、3.6；這一季）──
    def rename_skill(self, skill_name: str, new_name: str) -> bool:
        """把這一季登記過的功法（skill_name 是它的 id）改叫 new_name：id 不變（身上、功法庫照舊指得到），
        只換顯示的名字；new_name 已經被任何功法、改過的名字或意境用掉時不改、回 False（原子判斷）。"""
        ...

    def renamed_skill_ids(self) -> set[str]:
        """這一季被改過名字的功法 id（絕學定名，FB-083）。一次查完：同步時拿來判斷手上的武學有沒有被改過，不必一門一門查。"""
        ...

    def get_insight(self, name: str) -> Insight | None:
        """這一季合併出來的意境；基本意境不在這裡（在 content.insights）。"""
        ...

    def lookup_insight_recipe(self, key: str) -> Insight | None: ...

    def claim_insight_recipe(self, key: str, insight: Insight) -> tuple[Insight | None, bool]:
        """跟 claim_recipe 同一套：配方有了回 (登記在案的, False)；名字被占用回 (None, False)；否則登記、回 (insight, True)。"""
        ...

    # ── 合到舊的（武學與成長設計 12.2；這一季）──
    def fused_arts(self) -> list[MartialArt]:
        """這一季靠合成登記的功法（origin 是 fused），照登記的先後；「合到舊的」從這裡找候選。"""
        ...

    def merged_insights(self) -> list[Insight]:
        """這一季合併出來的意境，照登記的先後；基本意境不在這裡。"""
        ...

    def link_recipe(self, key: str, skill_name: str, creator: str | None) -> tuple[MartialArt | None, bool]:
        """把配方指到這一季已經登記的一門功法（合到舊的），原子判斷：配方已經有人登記 → (登記在案的, False)；
        那門功法不存在 → (None, False)；否則記下這個配方 → (那一門, True)。功法本身不動，首創者照舊。
        skill_name 是登記的 id（資料表裡 skills.name 那一欄）：練成絕學改名之後顯示的名字就對不上了，所以呼叫端傳 art.id、不是 art.name。"""
        ...

    def link_insight_recipe(self, key: str, insight_name: str, creator: str | None) -> tuple[Insight | None, bool]:
        """跟 link_recipe 同一套，指到這一季合併出來的一個意境。insight_name 是登記的名字（insights.name 那一欄，跟 insight.id 一樣；意境不改名）。"""
        ...

    def claim_master(self, skill_name: str, player: str, shown: str | None = None) -> bool:
        """這門武學這一季第一個修到絕學的人：還沒有人就記成 player、回 True；已經有人回 False（原子判斷）。
        player 是名號（身分：取名權照它認）；shown 是寫給別人看的名號（引擎現在不給，一律寫名號；這一版之前匿名行走的人記成「某位少俠」），
        同一筆交易寫進那門武學的 master_shown（後到的人那一句、換季的江湖史照它寫）。"""
        ...

    def master_of(self, skill_name: str) -> str | None: ...

    # ── 感悟的首悟紀錄（悟意境設計 0.2b）──
    def claim_insight_first(self, key: str, name: str, creator: str, place: str, time: float = 0.0) -> bool:
        """這一季第一個在這裡、用這個做法、畫出這個屬性悟到的人：key 是「地點|做法屬性|畫出的屬性」（sensing.first_key）。
        還沒有人就記下（名字、名號、地名）、回 True；已經有人回 False（原子判斷，不看誰先送出模型請求）。
        記的是紀錄、不是定義：意境本身存在悟到的人自己的存檔裡，後面的人照樣自己悟、自己取名。換季寫進那一季的江湖史。"""
        ...

    def insight_first(self, key: str) -> tuple[str, str] | None:
        """這一季這個鍵的首悟紀錄：（意境名, 名號）；沒有人悟過是 None。"""
        ...

    # ── 同伴性情漂移 ──
    def record_companion_tag(self, companion_id: str, tag: str) -> None: ...

    def get_companion_drift_note(self, companion_id: str) -> str: ...

    def set_companion_drift_note(self, companion_id: str, note: str) -> None: ...

    def tag_counts_since_last_drift(self, companion_id: str) -> int:
        """自上次語意化以來，全服玩家又新累積了幾次交友 tag（用總次數而非時間排程：誰的這次互動剛好跨過門檻就由誰觸發）。"""
        ...

    def record_drift_synthesis(self, companion_id: str, note: str) -> None:
        """語意化完成後，把新的一句話性情跟「這次是在累積到多少次時算的」一起寫回（同一筆交易裡讀當下總數）。"""
        ...

    # ── 江湖大事潤色（全服共用一次）──
    def get_event_flavor(self, fire_id: str) -> str: ...

    def set_event_flavor(self, fire_id: str, text: str) -> None:
        """只在這個江湖大事還沒有人潤色過時才寫入：全服永遠只看到同一份。"""
        ...

    # ── 傳國玉璽碎片（跨季）──
    def record_jade_seal_fragment(self, finder: str, season_name: str, text: str) -> JadeSealFragment | None:
        """記錄一塊新找到的碎片（編號在交易裡決定，不會重複或漏編）；七塊都找完之後回傳 None。"""
        ...

    def get_jade_seal_fragments(self) -> list[JadeSealFragment]: ...

    def jade_seal_summary(self) -> str: ...

    # ── 共享賽季 ──
    def get_season(self) -> WorldState:
        """目前這一季，連同這一季全部的傳聞與江湖史（給畫面看）。read()／mutate()／mutate_season()
        給出的賽季不讀傳聞與江湖史，兩個清單是空的，往裡面加的照樣會寫進去。"""
        ...

    def chronicle_before(self, season_number: int) -> list[tuple[int, list[Rumor]]]:
        """season_number 以前每一季的江湖史，新的一季在前（線上架構設計 3.2：江湖史跨季保留）。"""
        ...

    def get_season_number(self) -> int: ...

    def mutate_season(self, fn: Callable[[WorldState], None]) -> WorldState:
        """讀取共用賽季→套用 fn(season)→寫回，同一筆交易。"""
        ...

    def save_season(self, season: WorldState) -> None:
        """寫回共用賽季：呼叫端（engine.py）把 state.world 指向 get_season() 讀回的那一份、就地修改過，這裡寫回。"""
        ...

    def season_phase(self) -> SeasonPhase: ...

    def seed_first_season(self, content: Content) -> WorldState:
        """全服第一次開局：照劇本種出第 1 季。預設停在籌備中等管理者開季；內容設定 auto_open_first_season
        時直接開季。已經種過就原封不動回傳。"""
        ...

    def open_season(self, content: Content, now: float) -> bool:
        """管理者開季：籌備中 → 進行中，賽季時鐘從 now 起算。還沒種、或已經開過，回傳 False。
        開季時照現在的設定重新蓋章（stamp_season）：第一次啟動忘了設 TIANXIA_PROFILE、種下的季蓋的是「關」，
        設好重開之後開季，這一季照新的設定跑。籌備中的季時間是 0、什麼都還沒跑，重蓋是安全的。"""
        ...

    def next_season(self, content: Content, now: float) -> bool:
        """管理者開下一季：只在休季時有效。換上全新的一季、賽季編號 +1、直接開季，賽季時鐘從 now 起算；
        同伴全部重獲自由、沒打完的決戰清掉，天機 +1；玉璽碎片不動。武學命名、煉製配方、投靠名冊每季各一份，
        新的一季自然是空的。舊的一季整份留著（線上架構設計 3.2），上一季的首創（合成首創、首悟意境、練成絕學）寫進那一季的江湖史。"""
        ...

    def catch_up_season(self, content: Content, now: float, rng: random.Random) -> list[str]:
        """被動的現實時間追趕：把共用賽季依「距離上次有人追趕過了多久現實時間」往前推進，世界的時間
        永遠只走一份。時鐘只會往前：拿比上次對過的還早的時間來追趕，不推進、也不把時鐘撥回去。
        賽季時鐘暫停中（paused_at）什麼都不做：不推進、對時點也不動（繼續時才一起往後挪，見 resume_clock）。"""
        ...

    # ── 賽季時鐘暫停（線上架構設計第四節、8.3）──
    def paused_at(self) -> float | None:
        """賽季時鐘從哪個現實時間起暫停；沒有暫停是 None。只讀一個欄位、很快：引擎每次排選單、推決戰都會問。"""
        ...

    def pause_clock(self, now: float) -> bool:
        """暫停賽季時鐘：只在進行中、還沒暫停時有效（記下 now、回 True）；籌備、休季、已經停著都什麼都不做、回 False。"""
        ...

    def resume_clock(self, content: Content, now: float) -> float | None:
        """讓賽季時鐘繼續走，回傳停了幾個現實秒；沒有暫停回 None。停的這一段不算進賽季：對時點（season_last_real）往後挪
        world.pause_skip 那麼多（第一季照整個曆時往下取整，其他照停的長度）——暫停前還沒補算的那一小段照算，季末與一般的大事
        跟著往後延。還沒收場的決戰，集結截止或這一回合開放的時間往後挪停的長度（battle_instance.shift_deadlines），
        剩下的時間跟暫停前一樣。排好、還沒開的決戰照原本的現實時間開（企劃者 2026-10-06 定 B3，world.keep_showdowns_on_time）；
        原本的時間落在暫停裡的記進 showdowns_waiting（B11）。
        繼續之後緊接著還要補算、開集結（不補算的話，決戰會在它前面的一般大事還沒結算時就開成）：呼叫端不要自己接這幾步，
        一律走 world.resume_season_clock。"""
        ...

    # ── 投靠名冊 ──
    def record_faction(self, name: str, faction_id: str) -> None: ...

    def faction_of(self, name: str) -> str | None:
        """這一季投靠名冊上這個名號的陣營；還沒記過是 None。"""
        ...

    def faction_counts(self) -> dict[str, int]:
        """這一季各陣營投靠了幾人（只列有人的陣營）。"""
        ...

    def fingerprint_parts(self) -> tuple[SharedWorldState, int, int]:
        """（全服狀態，這一季最大的天下大事傳聞流水號，這一季江湖史的則數），同一個唯讀快照裡讀的；賽季裡的傳聞與江湖史
        不讀回每一列。推送的看守用（server.current_fingerprint）。"""
        ...

    # ── 全服即時多人戰鬥 ──
    def get_battle(self) -> BattleInstance | None: ...

    def mutate_battle(self, fn: Callable[[BattleInstance], None]) -> BattleInstance | None:
        """讀取目前這場戰鬥→套用 fn(battle)→寫回；沒有戰鬥時 fn 不會被呼叫，直接回傳 None。"""
        ...

    def start_battle(self, definition: BattleDef, now: float, trend_start: int | None = None) -> BattleInstance:
        """開一場新戰鬥；已經有一場還沒結束的戰鬥時，原封不動回傳那一場。trend_start 是這一場的起點（時刻表決戰照
        前線戰況算）；不給照 definition.trend_start（見 battle_instance.start_muster）。"""
        ...

    def clear_battle(self) -> None: ...

    def battle_rounds(self, record_id: int) -> list[BattleRoundRecord]:
        """這一場（BattleInstance.record_id）結算過的每一回合，照先後。BattleInstance.rounds 只放這次讀出來
        之後才結算、還沒寫進資料庫的回合，存檔後讀出來是空的；要看以前的回合查這裡。"""
        ...

    def ended_battles(self, after: int = 0) -> list[tuple[int, BattleInstance]]:
        """收場的決戰（phase 是 ended）裡流水號（record_id）比 after 大的，不分季別、照先後，每一場連同它是第幾季
        打的：（季別, 戰鬥），戰鬥帶著 record_id。決戰的結果常常就把季收掉，所以參戰者休季、下一季才回來也要補得到
        （FB-027，見 Game._deliver_battle_results）。只讀。

        after 是呼叫端已經處理過的最大流水號：決戰照開戰的先後收場，所以比它小的不會再有新收場的。理由——
        同一時間只有一場還沒收場（start_battle 在它收場或被清掉之前不另開），被清掉的（換季 next_season、季終
        clear_battle）不再指到、永遠不會收場，而新開的一場流水號一定比之前的都大（實作要保證這一點，SQLite 版是
        從不刪列的 INTEGER PRIMARY KEY）。所以一場收場時，它比之前收場的每一場都大。

        季終沒打完的決戰，Game 先用 mutate_battle 標成 ended 且 unfinished（沒有結果、不套用）再 clear_battle，
        所以它也列在這裡（FB-035）；用的人要看 BattleInstance.unfinished 分辨。它收場的那一刻仍是同時唯一還沒收場的那一場，
        流水號的先後前提不變。"""
        ...

    # ── 同伴進度與招募 ──
    def get_companion(self, companion_id: str) -> CompanionProgress:
        """讀目前進度；還沒有人動過這位人物時回傳一份預設值（不寫回）。"""
        ...

    def try_recruit(self, companion_id: str, player_name: str) -> bool:
        """把 owner 設成 player_name；已經有主的話失敗（設計文件四.4：唯一、可搶）。"""
        ...

    def release_companion(self, companion_id: str) -> None:
        """放走同伴：只清 owner，等級/武學等進度原封不動。"""
        ...

    def update_companion(
        self, companion_id: str, fn: Callable[[CompanionProgress], None],
    ) -> CompanionProgress: ...
