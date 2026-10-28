"""暖機看守（省電模式的另一半，Joy 2026-10-18「有時候這台電腦還要同步跑到其他東西」）。

省電模式（`tianxia/power_save.py`）把模型的 keep_alive 改短，沒人玩就讓 Ollama 卸掉模型、把 VRAM 還出來。
光這樣會踩到 2026-10-10 那個坑：模型卸掉之後，下一個要模型的動作得等它載回來（這台約 25～75 秒），
而遊戲的讀取逾時 30 秒、鎖內 15 秒，失敗還會開 180 秒的斷路器——玩家看到的是「武將不會對話」。

所以這支程式只做一件事：**有真人在線就每分鐘替模型續一次命**（送一個不產生任何字的請求，Ollama 照 keep_alive 續期），
沒人在線就不送，省電模式下還順手請 Ollama 現在就卸掉。於是：
- 有人在玩 → 模型一直是熱的，體驗跟平常一模一樣（連「只走路、半小時沒叫過模型」的人也是）。
- 沒人在玩 → VRAM 是空的，這台電腦可以去做別的事。

跟遊戲完全分開：自己一個行程、資料庫唯讀（`mode=ro`）、不碰任何遊戲狀態，掛了不影響遊戲。
「在線」的判法跟遊戲一致（`characters` 的 `last_real` 在 presence 秒內，同 `tianxia/social.py::here`），
而且**只算真人**（`is_bot = 0`）：假人不需要模型熱著，它們鎖內一個模型都不叫。

用法（跟伺服器同一份設定、同一個資料庫）：
    .venv/Scripts/python.exe -u scripts/warm_keeper.py
    .venv/Scripts/python.exe -u scripts/warm_keeper.py --every 60 --presence 600
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import console  # noqa: E402
from tianxia import database, power_save  # noqa: E402
from tianxia.content import env_profile, load_content, profile_line  # noqa: E402
from tianxia.ollama_client import OllamaClient  # noqa: E402

UNLOAD_SECONDS = 20.0  # 請 Ollama 卸掉模型：它回得很快，不必等久
# 「真的在線」自己一個窗口，**刻意不讀 Config.presence_seconds**：那個是「此地還有／截殺得到」的窗口，
# 2026-10-19 照 Joy 的要求拉到 24 小時（殺得到是重點，城鎮是避風港），照它判等於永遠有人在玩、
# 模型永遠不卸、省電模式整個白做。這裡要的是「還有人正在按按鈕」，十分鐘剛好。
ONLINE_SECONDS = 600.0
# 暖機不給自己的逾時：要讓那個請求跑到模型載完（OllamaClient.warm 的預設 WARM_TIMEOUT）。
# 給 2 秒的話，熱的模型續命看起來正常（回得快），但冷的模型永遠載不起來——請求一斷，Ollama 就把載入取消
# （2026-10-18 實機踩到，warm_err.log 寫「Read timed out. (read timeout=2.0)」）。


def players_online(db: Path, presence: float, now: float) -> int:
    """唯讀數一下 presence 秒內同步過的真人。資料庫讀不到就回 -1（當成不知道，不動模型）。"""
    try:
        conn = sqlite3.connect("file:" + db.as_posix() + "?mode=ro", uri=True)
    except sqlite3.Error:
        return -1
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM characters WHERE is_bot = 0 "
            "AND json_extract(data,'$.last_real') >= ?", (now - presence,),
        ).fetchone()
        return int(row[0]) if row else 0
    except sqlite3.Error:
        return -1
    finally:
        conn.close()


def loaded_models(client: OllamaClient) -> list[str]:
    """Ollama 此刻載著哪幾個模型（/api/ps）。問不到就回空的（當成不知道，不動模型）。"""
    import requests
    try:
        res = requests.get(f"{client.base_url}/api/ps", timeout=UNLOAD_SECONDS)
        return [str(m.get("model") or m.get("name")) for m in (res.json().get("models") or []) if m.get("model") or m.get("name")]
    except Exception:  # noqa: BLE001
        return []


def unload(client: OllamaClient) -> None:
    """請 Ollama 現在就把模型卸掉（keep_alive 0）：省電模式下沒人玩時用，不用等 keep_alive 到期。

    **卸掉載著的每一個，不只 client 此刻要用的那一個**：省電模式可以換小模型（power_save.model），
    換過去之後大模型還躺在 VRAM 裡、要等它自己的 keep_alive（正式設定 12h）才會走，那整段時間卡還是滿的。
    問不到 /api/ps 時退回只卸自己那一個（舊行為）。
    """
    import requests
    for name in loaded_models(client) or [client.model]:
        try:
            requests.post(
                f"{client.base_url}/api/generate", json={"model": name, "keep_alive": 0}, timeout=UNLOAD_SECONDS,
            )
        except Exception:  # noqa: BLE001  卸不掉就算了，keep_alive 到期一樣會卸
            pass


def main(argv: list[str] | None = None) -> None:
    console.use_utf8()
    parser = argparse.ArgumentParser(description="有真人在線就把模型留在記憶體裡，沒人就放掉")
    parser.add_argument("--every", type=float, default=60, help="多久看一次（現實秒，預設 60）")
    parser.add_argument("--presence", type=float, default=0,
                        help=f"多久以內算「真的在線」（現實秒，預設 {ONLINE_SECONDS:g}）")
    parser.add_argument("--rounds", type=int, default=0, help="看幾輪就結束（測試用，預設一直跑）")
    parser.add_argument("--warm-now", action="store_true",
                        help="不管有沒有人在線，先暖一次就結束（開服腳本用：keep_alive 照省電模式，不會把 12h 釘回去）")
    args = parser.parse_args(argv)

    profile = env_profile()
    content = load_content(ROOT / "content", profile=profile)
    presence = args.presence or ONLINE_SECONDS
    client = OllamaClient.from_config(content.config)
    db = database.default_path().resolve()
    print(f"暖機看守：每 {args.every:g} 秒看一次　在線＝{presence:g} 秒內的真人　模型 {client.model}", flush=True)
    print(f"資料庫：{db}（唯讀）", flush=True)
    print(profile_line(content, profile), flush=True)
    small = power_save.small_model() if power_save.on() else None
    print(f"省電模式：{'開（keep_alive ' + str(power_save.wanted()) + '）' if power_save.on() else '關'}"
          f"{'　模型換成 ' + small if small else ''}"
          f"　——開關是 {power_save.FLAG}，隨時改、不必重開（Ctrl+C 結束）", flush=True)

    if args.warm_now:  # 開服腳本用：讓 client 自己決定 keep_alive（省電模式開著就是短的）
        client.warm(block=True)  # 這個行程馬上就結束，一定要等它載完（背景那條會跟著行程被砍）
        print(f"已送暖機請求（keep_alive {client.keep_alive}）。", flush=True)
        return

    warm, done = None, 0
    while args.rounds <= 0 or done < args.rounds:
        people = players_online(db, presence, time.time())
        if people >= 0 and (people > 0) != warm:  # 只在「有人／沒人」翻過來的時候印一行
            warm = people > 0
            if warm:
                print(f"有人在玩（{people} 人）：模型留著。", flush=True)
            elif power_save.on():
                print("沒人在玩：請 Ollama 卸掉模型，VRAM 還出去。", flush=True)
            else:
                print("沒人在玩：不再續命（省電模式沒開，照 Config.ollama_keep_alive 到期才卸）。", flush=True)
        if people > 0:
            # 續命：不產生任何字，Ollama 照 keep_alive 重新計時。--rounds 的那幾輪會結束，所以要等它載完
            client.warm(block=args.rounds > 0)
        elif people == 0 and power_save.on():
            unload(client)
        done += 1
        if args.rounds <= 0 or done < args.rounds:
            time.sleep(args.every)


if __name__ == "__main__":
    main()
