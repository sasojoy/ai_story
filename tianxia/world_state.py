"""共用世界狀態：獨立於各玩家存檔之外、所有玩家共讀共寫的一份資料（設計文件四.3／六.2）。

目前存兩件事：
- **自創武學命名登記**：武學名稱全服不能重名，這裡是唯一的「這個名字有沒有被用過」的
  真相來源（`martial_arts.generate_from_name()` 本身是純函式，不會、也不該自己記狀態）。
- **同伴性情漂移**：歷史人物的「當下性情」是全服玩家共同形塑的，不是存在單一玩家存檔裡
  （見設計文件四.3）。這裡只存原始的 tag 累積計數；把計數轉成一句話性情描述的語意判斷
  留給 `companion_agent.py`（還沒實作），這個模組只負責資料的共用讀寫與鎖。

因為 tianxia 是一個 Gradio process 服務所有連進來的玩家（見設計文件八.1），不需要真正的
client-server 架構，用檔案鎖保護一份共用 JSON 檔即可。鎖用 mkdir（在 POSIX 跟 Windows
上都是原子操作，不需要額外套件），逾時會強制回收，避免程式異常結束後鎖永遠卡住。
"""
from __future__ import annotations

import contextlib
import json
import time
from pathlib import Path

from pydantic import BaseModel, Field

from .martial_arts import MartialArt

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = ROOT / "saves" / "world" / "state.json"

LOCK_TIMEOUT = 5.0  # 等鎖最多幾秒
LOCK_STALE_AFTER = 30.0  # 鎖目錄存在超過這麼久視為前一個行程異常結束，強制回收
LOCK_POLL_INTERVAL = 0.05


class WorldState(BaseModel):
    created_skills: dict[str, MartialArt] = Field(default_factory=dict)  # 鍵是武學名稱
    companion_tag_counts: dict[str, dict[str, int]] = Field(default_factory=dict)  # 人物 id -> {tag: 次數}
    companion_drift_note: dict[str, str] = Field(default_factory=dict)  # 人物 id -> 目前漂移後的一句話性情


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

    def read(self) -> WorldState:
        if not self.path.exists():
            return WorldState()
        return WorldState.model_validate_json(self.path.read_text(encoding="utf-8"))

    def _write(self, state: WorldState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(state.model_dump_json(indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def mutate(self, fn) -> WorldState:
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

        def _apply(state: WorldState) -> None:
            if art.name.strip() in state.created_skills:
                return
            state.created_skills[art.name.strip()] = art
            claimed["ok"] = True

        self.mutate(_apply)
        return claimed["ok"]

    # ── 同伴性情漂移 ──────────────────────────────────────

    def record_companion_tag(self, companion_id: str, tag: str) -> None:
        """累積一次交遊 tag；轉成漂移後的性情描述是 companion_agent.py 的事，這裡只記數。"""
        def _apply(state: WorldState) -> None:
            counts = state.companion_tag_counts.setdefault(companion_id, {})
            counts[tag] = counts.get(tag, 0) + 1

        self.mutate(_apply)

    def get_companion_drift_note(self, companion_id: str) -> str:
        return self.read().companion_drift_note.get(companion_id, "")

    def set_companion_drift_note(self, companion_id: str, note: str) -> None:
        def _apply(state: WorldState) -> None:
            state.companion_drift_note[companion_id] = note

        self.mutate(_apply)
