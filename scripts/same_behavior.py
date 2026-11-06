"""前後一字不變的對照（開發規範手冊第 2 階「主動搬六包」；批次表 docs/superpowers/plans/2026-10-31-主動搬六包-批次.md 第二節）。

同一支腳本拿兩份程式（base、head：各是一個解開的 git archive 或工作樹）各跑一次，比輸出的 sha256，逐位元組、不排序鍵
（/api/main 的鍵順序算行為）。只打公開的 API（FastAPI 的 TestClient）；擺局面（站哪裡、陣營、新手期、體力、軍令）直接改資料庫，
伺服器每次進鎖本來就從資料庫重讀。第 1 批（出陣）收進來；之後每一批加自己的情境，第 11 批全部重跑。情境分軌（--track）：
sortie 是第 1 批的（Scenario：出陣本體、混戰、出陣回報），duel 是第 2 批的（DuelScenario：出陣約戰）；每一軌自己一個資料庫、
自己切一半（同一個切點放不下兩種窗：混戰的 10 分與約戰的 10 分）。之後的批可以接在某一軌的段落後面，或照這樣再開一軌。

用法（python 不加 -I：-I 會連 PYTHONHASHSEED 一起忽略；子行程自己帶 PYTHONHASHSEED=0）：
  python scripts/same_behavior.py compare --base <根> --head <根> --tmp <暫存資料夾> [--profiles none,weekend,...] [--tracks sortie,duel]
      [--jobs 4] [--no-bots]
  python scripts/same_behavior.py selftest --base <根> --tmp <暫存資料夾> [--tracks ...]   同一份跑兩次一樣、前半＋後半＝整段、改一個字抓得到
  python scripts/same_behavior.py run <根> <設定> <輸出檔> --tmp <暫存資料夾> [--track sortie|duel] [--part all|first|second] [--db <資料庫檔>]
  python scripts/same_behavior.py bots <根> <設定> <輸出檔> --tmp <暫存資料夾> [--seats sortie|duel]

設定：none（不帶）、weekend、season21、week7，與 test（tests/fixtures/content，測試內容）。

固定的那幾層（不固定的話同一份程式跑兩次就不一樣，比對本身不穩）：
- 亂數：伺服器每個請求都 Game(CONTENT, state) 不傳 rng（engine 的 `self.rng = rng or random.Random()`）——這裡把
  random.Random.__init__ 換成「沒給種子就用 12345 + 7919 × 步數」，Game 的預設 rng、各處沒給種子的 Random() 都是這一顆；每個請求之前
  random.seed(步數)（模組層的 random.random()），並清空 server.GAMES（每個請求重建 Game，等於每一下之間重開伺服器：
  前半＋後半跟整段才比得了）。
- 時間：time.time 換成「CLOCK0 + 步數 × 60 秒、同一個請求裡每叫一次 +0.5 秒」；server._monotonic（鎖內模型的斷路器、大場面判讀
  與取名的預算）讀同一顆鐘、讀的時候不往前推（不然機器慢的那一次預算先用完、斷路器開得久，結果跟著牆上的時間變）。
- 模型：OllamaClient.from_config 照原樣建好之後換成不連網路的 client（chat_* 立刻丟連線錯誤、warm 什麼都不做；絕不打 11434）。
  大場面判讀那一步換成回固定判讀的（Judgment(advantage=8)），act:train 走 server.may_judge_fight → prepare_fight 那一條。
- 資料庫轉成文字：每一張表、每一列（列照 repr 排序：列的先後不是行為）；帳號的 salt、hash 抹掉（每次隨機）。

開季準備卡（develop 的五項屬性與傳承；合回第 0 段補）：卡接管整個選單，不按的話之後每一步都被擋、兩邊一樣擋，比對等於空驗。Scenario.call 看到回應裡的
main.prep 就照預設配比按 growth:、識海按 legacy:skip（clear_prep，這幾下照樣寫進輸出）；籌備中、休季不按。沒有 main.prep 的根一步都不多，輸出跟以前一個位元組都不差。

半舊半新（批次表「舊程式寫到一半、新程式接手」）：--part first 跑完那一軌的 PHASES_FIRST 停（存下步數），--part second 開同一個
資料庫接著跑 PHASES_SECOND。compare 比「base 整段」＝「base 前半＋head 後半」；selftest 比「base 整段」＝「base 前半＋base 後半」。

檔案（第二輪第 70 批）：這支只留入口，路徑與指令不變。調度與固定層在 scripts/sb/harness.py；Scenario、DuelScenario、它們的假人在 scripts/sb/base.py；
其餘每段軌一檔 scripts/sb/tracks/<軌>.py。新軌只加檔：檔尾 register_track(...)（有假人再 register_bots，新子命令登記 SUBCOMMANDS）；軌名重複載入時就擋。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# sb 一定從這支腳本自己的位置載入：compare 是 head 的腳本跑 base 的根，base 上沒有 scripts/sb/；子行程跑的也是同一支（harness._child）。
# 只走 sb.harness 這條路徑，不要有 scripts.sb.*：模組載兩份的話 BUF、STEP、CLOCK、MODEL 就不是同一個物件。
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sb import base, harness  # noqa: E402
from sb.harness import BOT_SEATS, PROFILES, SUBCOMMANDS, TRACKS, _setup_child, _tracks_on, _wipe_db, compare, selftest  # noqa: E402

harness.load_tracks()  # 軌要在 _setup_child 之前載完（它把 scripts/ 從 sys.path 拿掉、chdir 到被比的根）


def __getattr__(name: str):
    """別的工具照舊讀 same_behavior.<名字>（pm-workflows/tools/talk_log_http.py 讀 14 個）：依序找 harness、base、各軌。"""
    if not (name.startswith("__") and name.endswith("__")):
        tracks = [mod for key, mod in sorted(sys.modules.items()) if key.startswith("sb.tracks.")]
        for mod in (harness, base, *tracks):
            if hasattr(mod, name):
                return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ═══════════════════════════ 入口 ═══════════════════════════


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in SUBCOMMANDS:  # 軌自己的子命令（explore-run、explore-compare……）
        return SUBCOMMANDS[args[0]](args)
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("root")
    r.add_argument("profile", choices=PROFILES)
    r.add_argument("out")
    r.add_argument("--tmp", required=True)
    r.add_argument("--db")
    r.add_argument("--part", choices=("all", "first", "second"), default="all")
    r.add_argument("--track", choices=tuple(TRACKS), default="sortie")
    b = sub.add_parser("bots")
    b.add_argument("root")
    b.add_argument("profile", choices=PROFILES)
    b.add_argument("out")
    b.add_argument("--tmp", required=True)
    b.add_argument("--seats", choices=tuple(BOT_SEATS), default="sortie")
    for name in ("compare", "selftest"):
        x = sub.add_parser(name)
        x.add_argument("--base", required=True)
        if name == "compare":
            x.add_argument("--head", required=True)
            x.add_argument("--no-bots", action="store_true")
        x.add_argument("--tmp", required=True)
        x.add_argument("--profiles", default=",".join(PROFILES))
        x.add_argument("--tracks", default=",".join(harness.TRACK_NAMES))
        x.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args(args)
    if a.cmd == "run":
        tmp = Path(a.tmp)
        tmp.mkdir(parents=True, exist_ok=True)
        db = Path(a.db) if a.db else tmp / f"sb_{a.profile}.db"
        if a.part in ("all", "first"):
            _wipe_db(db)
        _setup_child(Path(a.root).resolve(), a.profile, db)
        TRACKS[a.track](Path(a.root).resolve(), a.profile, db).run(a.part, Path(a.out))
        sys.stdout.flush()
        os._exit(0)  # TestClient 留下的執行緒不等
    if a.cmd == "bots":
        BOT_SEATS[a.seats][1](Path(a.root).resolve(), a.profile, Path(a.out), Path(a.tmp))
        sys.stdout.flush()
        os._exit(0)
    sys.stdout.reconfigure(encoding="utf-8")
    profiles = [p for p in a.profiles.split(",") if p]
    tracks = _tracks_on([t for t in a.tracks.split(",") if t], Path(a.base))
    if not tracks:  # compare、selftest 拿到空清單會跑全部
        print("這個根沒有要跑的軌")
        return 0
    if a.cmd == "compare":
        ok = compare(Path(a.base).resolve(), Path(a.head).resolve(), Path(a.tmp), profiles, a.jobs, not a.no_bots, tracks=tracks)
    else:
        ok = selftest(Path(a.base).resolve(), Path(a.tmp), profiles, a.jobs, tracks=tracks)
    print("全部一樣" if ok else "有不一樣的")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
