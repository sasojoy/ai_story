"""省電模式（Joy 2026-10-18「有時候這台電腦還要同步跑到其他東西」）。

量到的事實（2026-10-18，線上 1 個真人、近一小時 3 個）：遊戲那一側合起來根本不佔東西——
server.py 1.7%、run_bots.py 0.7%、monitor.py 與隧道 0.1% 的「一核」（這台 12 核），四個加起來約 320 MB；
吃掉這台機器的是常駐的模型：`ollama_keep_alive` 12h 讓 gemma4:12b 整天躺在 VRAM 裡（約 7.5 GiB／12 GiB 的卡，
加上 10.5 GB 的 RAM 工作集）。所以省電模式只做一件事：**把模型的 keep_alive 改短**，沒人玩就讓 Ollama 卸掉它、
把 VRAM 還給別的事。假人與行程數、巡邏頻率一概不動（量到省不了，只會讓江湖變冷清）。

開關是一個旗標檔（`.local/power_save`，或環境變數 `TIANXIA_POWER_SAVE`）：
- 不用設定覆寫檔，因為換設定要重開伺服器（登入狀態 2026-10-31 起在資料庫，重開不再全服登出，但還是會打斷正在進行的請求）。
- 不用管理者按鈕或 API，因為 `server.py` 與 `run_bots.py` 是兩個行程、各自一份 client，
  旗標檔是兩邊都看得到、又不必重開的唯一辦法。
- 檔裡可以寫要用的 keep_alive（例「2m」）；空的用 `DEFAULT`，寫 0／off／false／no 等於沒開。

代價寫清楚：模型卸掉之後，下一次要模型的動作得等它載回來（這台約 25～75 秒），而遊戲的讀取逾時是 30 秒、
鎖內 15 秒、失敗會開 180 秒的斷路器——所以省電模式要配 `scripts/warm_keeper.py`（有真人在線就每分鐘續一次）
與登入時的預熱（`server.py::_warm_model`），讓「有人在玩」的時候模型一直是熱的，只在真的沒人時才放掉。

不讀電腦時鐘、不碰遊戲狀態、不 import 任何別的模組：每次模型呼叫看一次旗標檔（一次 stat 比一次模型呼叫便宜太多）。
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FLAG = ROOT / ".local" / "power_save"  # .local/ 不進版控：這是這台主機的狀態，不是遊戲內容
ENV = "TIANXIA_POWER_SAVE"
DEFAULT = "5m"  # 省電模式的 keep_alive：最後一次模型呼叫之後五分鐘放掉 VRAM
OFF_WORDS = frozenset({"0", "off", "false", "no", "none"})
# 省電模式下要換成的模型（企劃者 2026-10-28「休眠模式的時候換成比較小的模型。不要占滿十二 GB」）：
# 只改 keep_alive 的話，有人一來整張卡又被 gemma4:12b 佔滿（9.1 GiB／12 GiB），這台就不能同時做別的重活。
# 旗標檔裡寫模型名（例 gemma3:4b）就換，沒這個檔、或寫 off／0 就照設定的模型——**不給預設值**：
# 偷偷換模型會讓 NPC 對話與旁白的品質變了而沒人知道，一定要主機端明寫（tianxia-powersave.ps1 幫你寫）。
MODEL_FLAG = ROOT / ".local" / "power_save_model"
MODEL_ENV = "TIANXIA_POWER_SAVE_MODEL"


def _clean(text: str | None) -> str | None:
    """旗標檔／環境變數寫的字清乾淨：空的、或 off 字樣一律 None。

    `strip` 連 BOM 一起吃掉：PowerShell 的 `Set-Content -Encoding utf8` 會在檔頭寫 BOM，
    帶著 BOM 送給 Ollama 是 HTTP 400（`time: invalid duration "ï»¿5m"`）或模型 404，
    而暖機失敗只記一行警告——於是「模型就是不載」而且看不出原因（2026-10-18 實機踩到）。
    """
    if text is None:
        return None
    text = text.strip().strip("﻿​").strip()
    return None if (not text or text.lower() in OFF_WORDS) else text


def _value(text: str | None) -> str | None:
    """旗標檔／環境變數寫的字換成 keep_alive：**空的等於開著、用預設值**（主機端 `New-Item` 建的空檔就是開）。"""
    if text is None:
        return None
    cleaned = _clean(text)
    if cleaned is not None:
        return cleaned
    return None if text.strip().strip("﻿​").strip() else DEFAULT


def wanted() -> str | None:
    """省電模式要用的 keep_alive，沒開是 None。環境變數優先（測試與臨時用），其次旗標檔。"""
    env = _value(os.environ.get(ENV))
    if env is not None or os.environ.get(ENV) is not None:
        return env
    try:
        if not FLAG.is_file():
            return None
        return _value(FLAG.read_text(encoding="utf-8"))
    except OSError:  # 讀不到就當沒開：省電是方便，不能因為它讓模型叫不動
        return None


def small_model() -> str | None:
    """省電模式下要換成的模型名，沒指定是 None（照設定的模型）。環境變數優先，其次旗標檔。"""
    env = os.environ.get(MODEL_ENV)
    if env is not None:
        return _clean(env)
    try:
        if not MODEL_FLAG.is_file():
            return None
        return _clean(MODEL_FLAG.read_text(encoding="utf-8"))
    except OSError:  # 讀不到就照設定的模型：省電是方便，不能因為它讓模型叫不動
        return None


def on() -> bool:
    """省電模式開著嗎（給腳本與說明用；要值的地方直接問 wanted）。"""
    return wanted() is not None


def keep_alive(normal: str) -> str:
    """這一次模型呼叫要送的 keep_alive：省電模式開著就是它的值，否則照設定（Config.ollama_keep_alive）。"""
    return wanted() or normal


def model(normal: str) -> str:
    """這一次模型呼叫要用的模型：省電模式開著**而且**指定了小模型才換，否則照設定（Config.ollama_model）。

    `_value` 連 keep_alive 那套 BOM 與 off 字樣一起處理（寫 off／0 ＝ 不換）。省電模式一關就立刻回到大模型，
    不必記得去刪那個檔。兩站共用一張卡：換模型的那一刻另一站也要跟著換，不然 12 GB 放不下兩個（見主機端技能）。
    """
    if wanted() is None:
        return normal
    return small_model() or normal
