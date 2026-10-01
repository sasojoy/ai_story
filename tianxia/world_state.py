"""共用世界狀態：獨立於各玩家存檔之外、所有玩家共讀共寫的一份資料（設計文件四.3／四.4／六.2）。

存四件事：
- **自創武學命名登記**：武學名稱全服不能重名，這裡是唯一的「這個名字有沒有被用過」的
  真相來源（`martial_arts.generate_from_name()` 本身是純函式，不會、也不該自己記狀態）。
- **同伴性情漂移**：歷史人物的「當下性情」是全服玩家共同形塑的，不是存在單一玩家存檔裡。
  這裡只存原始的 tag 累積計數；把計數轉成一句話性情描述的語意判斷留給
  `companion_agent.py`（還沒實作），這個模組只負責資料的共用讀寫與鎖。
- **同伴進度與招募狀態**：設計文件四.4 定案「每位歷史人物全服唯一」之後，同伴的等級／
  武學／熟練度是這個人物本身的屬性，不是某個玩家存檔裡的副本——被誰招走了，屬性也還是
  同一份，換人招募不會歸零。`PlayerState`（見 state.py）只留「這個玩家對這位人物的好感度」，
  跟他有沒有被招募、等級多高完全無關（好感度不管你招不招得到他都在累積，見設計文件七.1）。

因為 tianxia 是一個 Gradio process 服務所有連進來的玩家（見設計文件八.1），不需要真正的
client-server 架構，用檔案鎖保護一份共用 JSON 檔即可。鎖用 mkdir（在 POSIX 跟 Windows
上都是原子操作，不需要額外套件），逾時會強制回收，避免程式異常結束後鎖永遠卡住。
"""
from __future__ import annotations

import contextlib
import time
from pathlib import Path

from pydantic import BaseModel, Field

from .battle_instance import BattleInstance
from .martial_arts import MartialArt
from .models import BattleDef, Content
from .state import WorldState

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = ROOT / "saves" / "world" / "state.json"

LOCK_TIMEOUT = 5.0  # 等鎖最多幾秒
LOCK_STALE_AFTER = 30.0  # 鎖目錄存在超過這麼久視為前一個行程異常結束，強制回收
LOCK_POLL_INTERVAL = 0.05


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
    neili: float | None = None  # 氣血，None＝滿
    neigong_id: str | None = None
    neigong_level: int = 1
    wugong_id: str | None = None
    wugong_level: int = 1
    owner: str | None = None  # 目前招募他的玩家名號；None＝自由之身，誰都能嘗試招募


class SharedWorldState(BaseModel):
    created_skills: dict[str, MartialArt] = Field(default_factory=dict)  # 鍵是武學名稱
    companion_tag_counts: dict[str, dict[str, int]] = Field(default_factory=dict)  # 人物 id -> {tag: 次數}
    companion_drift_note: dict[str, str] = Field(default_factory=dict)  # 人物 id -> 目前漂移後的一句話性情
    companion_drift_synthesized_at: dict[str, int] = Field(default_factory=dict)  # 人物 id -> 上次語意化時的 tag 總數
    companions: dict[str, CompanionProgress] = Field(default_factory=dict)  # 人物 id -> 進度/招募狀態
    event_flavor: dict[str, str] = Field(default_factory=dict)  # 江湖大事 id -> 全服共用的一次性潤色句（設計文件 8.2 第 4 點）
    jade_seal_fragments: list[JadeSealFragment] = Field(default_factory=list)  # 跨季持久（設計文件九.2）

    # ── 共享賽季（真正共享的大勢/門檻/主線/結局，取代原本每個玩家各自獨立的 WorldState）──
    # 「跨季」的東西（武學命名登記、同伴進度、玉璽碎片等，上面那些欄位）永遠留著；season
    # 本身每次開新賽季會被整個換掉（見 start_new_season）。season_number 從 1 起算，
    # season_last_real 是這個賽季的共用時鐘上次對到現實時間的時間點（None＝還沒對過）。
    season: WorldState = Field(default_factory=WorldState)
    season_number: int = 1
    season_last_real: float | None = None

    # ── 全服即時多人戰鬥（設計討論：集結選陣營→逐幕逐回合鎖步）────────
    # 同一時間最多一場（先簡化成這樣；真的需要同時好幾場再擴充成 list/dict）。
    active_battle: BattleInstance | None = None


@contextlib.contextmanager
def _locked(lock_dir: Path):
    deadline = time.monotonic() + LOCK_TIMEOUT
    while True:
        try:
            lock_dir.mkdir(parents=True, exist_ok=False)
            break
        except FileExistsError:
            try:
                age = time.time() - lock_dir.stat().st_mtime
            except OSError:
                age = 0.0
            if age > LOCK_STALE_AFTER:
                with contextlib.suppress(OSError):
                    lock_dir.rmdir()
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError(f"等不到世界狀態的鎖：{lock_dir}")
            time.sleep(LOCK_POLL_INTERVAL)
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            lock_dir.rmdir()


class WorldStateStore:
    """共用世界狀態的讀寫入口。每個行程可以共用一個實例，也可以每次都重新建立——
    狀態本身在檔案裡，不在記憶體，不會因為重建實例而遺失。"""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else DEFAULT_PATH
        self.lock_dir = self.path.with_suffix(".lock")

    def read(self) -> SharedWorldState:
        if not self.path.exists():
            return SharedWorldState()
        return SharedWorldState.model_validate_json(self.path.read_text(encoding="utf-8"))

    def _write(self, state: SharedWorldState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(state.model_dump_json(indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def mutate(self, fn) -> SharedWorldState:
        """在鎖保護下讀取→套用 fn(state)→寫回，回傳套用後的狀態。fn 直接原地修改 state。"""
        with _locked(self.lock_dir):
            state = self.read()
            fn(state)
            self._write(state)
            return state

    # ── 武學命名登記 ──────────────────────────────────────

    def is_skill_name_taken(self, name: str) -> bool:
        return name.strip() in self.read().created_skills

    def claim_skill_name(self, art: MartialArt) -> bool:
        """把 art.name 登記進共用名錄；名字已被用過就不登記，回傳是否成功（在鎖內原子判斷，
        不會有兩個玩家同時取到同一個名字都成功的競態）。"""
        claimed = {"ok": False}

        def _apply(state: SharedWorldState) -> None:
            if art.name.strip() in state.created_skills:
                return
            state.created_skills[art.name.strip()] = art
            claimed["ok"] = True

        self.mutate(_apply)
        return claimed["ok"]

    # ── 同伴性情漂移 ──────────────────────────────────────

    def record_companion_tag(self, companion_id: str, tag: str) -> None:
        """累積一次交遊 tag；轉成漂移後的性情描述是 companion_agent.py 的事，這裡只記數。"""
        def _apply(state: SharedWorldState) -> None:
            counts = state.companion_tag_counts.setdefault(companion_id, {})
            counts[tag] = counts.get(tag, 0) + 1

        self.mutate(_apply)

    def get_companion_drift_note(self, companion_id: str) -> str:
        return self.read().companion_drift_note.get(companion_id, "")

    def set_companion_drift_note(self, companion_id: str, note: str) -> None:
        def _apply(state: SharedWorldState) -> None:
            state.companion_drift_note[companion_id] = note

        self.mutate(_apply)

    def tag_counts_since_last_drift(self, companion_id: str) -> int:
        """自上次語意化以來，全服玩家又新累積了幾次交遊 tag（給 companion_agent.py 判斷
        要不要觸發一次漂移語意化；用「總次數」而非時間排程，不管同時有幾個玩家在玩，
        誰的這次互動剛好跨過門檻就由誰觸發）。"""
        read = self.read()
        total = sum(read.companion_tag_counts.get(companion_id, {}).values())
        return total - read.companion_drift_synthesized_at.get(companion_id, 0)

    def record_drift_synthesis(self, companion_id: str, note: str) -> None:
        """語意化完成後，原子性地把新的一句話性情跟「這次是在累積到多少次時算的」一起
        寫回（鎖內讀當下總數，避免跟 record_companion_tag 之間有競態，把門檻標記設過頭
        或設不夠）。"""
        def _apply(state: SharedWorldState) -> None:
            state.companion_drift_note[companion_id] = note
            total = sum(state.companion_tag_counts.get(companion_id, {}).values())
            state.companion_drift_synthesized_at[companion_id] = total

        self.mutate(_apply)

    # ── 江湖大事潤色（全服共用一次）───────────────────────────

    def get_event_flavor(self, fire_id: str) -> str:
        return self.read().event_flavor.get(fire_id, "")

    def set_event_flavor(self, fire_id: str, text: str) -> None:
        """只在這個江湖大事還沒有人潤色過時才寫入（鎖內判斷），避免兩個玩家前後腳都觸發
        同一個門檻時各自呼叫一次 LLM、最後互相覆蓋彼此的結果——全服應該永遠只看到同一份。"""
        def _apply(state: SharedWorldState) -> None:
            state.event_flavor.setdefault(fire_id, text)

        self.mutate(_apply)

    # ── 傳國玉璽碎片（跨季，設計文件九）───────────────────────

    def record_jade_seal_fragment(self, finder: str, season_name: str, text: str) -> JadeSealFragment | None:
        """記錄一塊新找到的碎片；七塊都找完之後回傳 None（不再記錄，這條跨季長線到此結束）。
        在鎖內判斷「現在是第幾塊」，避免兩個玩家幾乎同時觸發時編號重複或漏編。"""
        result: dict[str, JadeSealFragment | None] = {"fragment": None}

        def _apply(state: SharedWorldState) -> None:
            if len(state.jade_seal_fragments) >= JADE_SEAL_FRAGMENT_COUNT:
                return
            fragment = JadeSealFragment(
                number=len(state.jade_seal_fragments) + 1, finder=finder, season_name=season_name, text=text,
            )
            state.jade_seal_fragments.append(fragment)
            result["fragment"] = fragment

        self.mutate(_apply)
        return result["fragment"]

    def get_jade_seal_fragments(self) -> list[JadeSealFragment]:
        return self.read().jade_seal_fragments

    def jade_seal_summary(self) -> str:
        fragments = self.get_jade_seal_fragments()
        if not fragments:
            return "傳國玉璽的七塊碎片，至今尚無人尋獲過一塊。"
        lines = [f"傳國玉璽：{len(fragments)}/{JADE_SEAL_FRAGMENT_COUNT} 塊碎片已現世——"]
        lines += [f"　第 {f.number} 塊：{f.finder}（{f.season_name}）{f.text}" for f in fragments]
        return "\n".join(lines)

    # ── 共享賽季 ──────────────────────────────────────────

    def get_season(self) -> WorldState:
        return self.read().season

    def get_season_number(self) -> int:
        return self.read().season_number

    def mutate_season(self, fn) -> WorldState:
        """在鎖保護下讀取共用賽季→套用 fn(season)→寫回，回傳套用後的狀態。fn 直接原地
        修改 season（一個 WorldState）。寫動作本身是唯一需要鎖的地方——app.py 另外還有一個
        process 內的 ACT_LOCK 序列化所有玩家行動，這裡的檔案鎖是給沒有 ACT_LOCK 的場合用的
        （CLI、測試、未來真的拆成多個行程時），兩者不衝突。"""
        def _apply(state: SharedWorldState) -> None:
            fn(state.season)

        return self.mutate(_apply).season

    def save_season(self, season: WorldState) -> None:
        """整份覆寫共用賽季：呼叫端（engine.py）已經在自己的流程裡把 state.world 指向
        get_season() 讀回的那一份、就地修改過，這裡單純寫回，不需要再做一次 fn 包裝。"""
        def _apply(state: SharedWorldState) -> None:
            state.season = season

        self.mutate(_apply)

    def start_new_season(self, content: Content) -> WorldState:
        """全服第一次開局（還沒有任何共用賽季）或目前賽季已經結束時，重新用 content 的
        劇本種出一份全新的共用賽季，賽季編號 +1；賽季還在進行中時原封不動回傳目前的賽季
        （不會因為兩個玩家前後腳都呼叫就重複重置——鎖內判斷，只有第一個真的執行重置）。"""
        def _apply(state: SharedWorldState) -> None:
            if state.season.storyline and not state.season.ended:
                return
            is_bootstrap = not state.season.storyline  # 從未真正初始化過，不是「結束後輪替」
            trends = content.scenario.trends
            state.season = WorldState(
                trends={t.id: t.start for t in trends},
                revealed={t.id for t in trends if not t.hidden},
                storyline=content.scenario.storylines[0].id,
            )
            if not is_bootstrap:
                state.season_number += 1  # 全服第一次開局維持第 1 季；只有真的輪替才遞增

        return self.mutate(_apply).season

    def catch_up_season(self, content, now: float, rng) -> list[str]:
        """被動的現實時間追趕：不管是誰在這一刻跟伺服器互動，都把共用賽季依「距離上次
        有人追趕過了多久現實時間」往前推進，而不是依呼叫者自己的步調——這樣不管幾個玩家
        同時在線、各自多久互動一次，世界的時間永遠只走一份，不會重複計算也不會停滯。
        實際的「推進 N 秒會發生什麼事」邏輯在 world.py::advance_season（避免循環 import：
        world.py 已經 import 這個模組，不能反過來由這裡 import world.py）。"""
        from . import world as world_module

        result: dict[str, list[str] | float] = {"msgs": [], "elapsed": 0.0}

        def _apply(state: SharedWorldState) -> None:
            last = state.season_last_real
            state.season_last_real = now
            if last is None:
                return
            result["elapsed"] = max(0.0, now - last) * content.config.time_scale

        self.mutate(_apply)
        elapsed = result["elapsed"]
        if elapsed <= 0:
            return []
        return world_module.advance_season(self, content, elapsed, rng)

    # ── 全服即時多人戰鬥 ──────────────────────────────────

    def get_battle(self) -> BattleInstance | None:
        return self.read().active_battle

    def mutate_battle(self, fn) -> BattleInstance | None:
        """在鎖保護下讀取目前這場戰鬥→套用 fn(battle)→寫回；戰鬥不存在時 fn 不會被呼叫，
        直接回傳 None（呼叫端自己決定要不要把「沒有進行中的戰鬥」當錯誤處理）。"""
        result: dict[str, BattleInstance | None] = {"battle": None}

        def _apply(state: SharedWorldState) -> None:
            if state.active_battle is None:
                return
            fn(state.active_battle)
            result["battle"] = state.active_battle

        self.mutate(_apply)
        return result["battle"]

    def start_battle(self, definition: BattleDef, now: float) -> BattleInstance:
        """開一場新戰鬥；已經有一場還沒結束的戰鬥時，原封不動回傳那一場（鎖內判斷，
        避免兩個觸發點前後腳都想開戰，結果互相蓋掉彼此的集結名單）。"""
        from .battle_instance import start_muster

        result: dict[str, BattleInstance] = {}

        def _apply(state: SharedWorldState) -> None:
            if state.active_battle is not None and state.active_battle.phase != "ended":
                result["battle"] = state.active_battle
                return
            state.active_battle = start_muster(definition, now)
            result["battle"] = state.active_battle

        self.mutate(_apply)
        return result["battle"]

    def clear_battle(self) -> None:
        """戰鬥結束、大家都看過結果之後清掉，讓下一場能夠開始（不清的話 start_battle
        會因為「還有一場 phase != ended」卡住——但 ended 的戰鬥本來就不會卡住
        start_battle，這裡單純是不想讓共用狀態一直留著打完的舊戰鬥）。"""
        def _apply(state: SharedWorldState) -> None:
            state.active_battle = None

        self.mutate(_apply)

    # ── 同伴進度與招募 ────────────────────────────────────

    def get_companion(self, companion_id: str) -> CompanionProgress:
        """讀目前進度；還沒有人動過這位人物時回傳一份預設值（不會寫回檔案，純讀取）。"""
        return self.read().companions.get(companion_id, CompanionProgress())

    def try_recruit(self, companion_id: str, player_name: str) -> bool:
        """嘗試把 owner 設成 player_name；已經有主的話失敗（設計文件四.4：唯一、可搶）。
        判定「招募難不難、會不會惹惱對方要求決鬥」是呼叫端（engine.py）的事，這裡只負責
        「搶到了沒」這個最終的原子操作，避免兩個玩家同時搶到同一個人。"""
        result = {"ok": False}

        def _apply(state: SharedWorldState) -> None:
            progress = state.companions.setdefault(companion_id, CompanionProgress())
            if progress.owner is not None:
                return
            progress.owner = player_name
            result["ok"] = True

        self.mutate(_apply)
        return result["ok"]

    def release_companion(self, companion_id: str) -> None:
        """放走同伴（離隊/戰敗失去等）：只清 owner，等級/武學等進度原封不動保留。"""
        def _apply(state: SharedWorldState) -> None:
            if companion_id in state.companions:
                state.companions[companion_id].owner = None

        self.mutate(_apply)

    def update_companion(self, companion_id: str, fn) -> CompanionProgress:
        """在鎖保護下修改某位同伴的進度（升級、配置武學等），fn 直接原地修改 CompanionProgress。"""
        def _apply(state: SharedWorldState) -> None:
            progress = state.companions.setdefault(companion_id, CompanionProgress())
            fn(progress)

        return self.mutate(_apply).companions[companion_id]
