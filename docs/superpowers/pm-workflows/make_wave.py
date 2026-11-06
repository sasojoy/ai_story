"""產生一波的工作流程（波次模式，企劃者 2026-11-06）。用法：make_wave.py <波> <基準 SHA> <輸出資料夾> [--scratch <資料夾>]
只開發：把產生的 wave-<波>.js 交給 Workflow。開發完回來的 built 另外寫成 JSON，用 make_wave.py <波> <基準 SHA> <輸出資料夾> --finish <built.json> --merge-base <SHA> 產生 wave-<波>-finish.js。
每一批的派工寫在 WAVES；寫過的批（第 45 批）從 paused-1104/make_more.py 的 BATCHES 拿。"""
import argparse
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = (HERE / "split-wave.js").read_text(encoding="utf-8").replace("\r\n", "\n")


def old_batches():
    text = (HERE / "paused-1104" / "make_more.py").read_text(encoding="utf-8").replace("\r\n", "\n")
    text = text.replace("N, BASE = sys.argv[1], sys.argv[2]\n", "").replace("OUT = Path(sys.argv[3]) if len(sys.argv) > 3 else Path(__file__).parent\n", "")
    text = text[: text.index("\nb = BATCHES[N]")]
    scope = {"__file__": str(HERE / "paused-1104" / "make_more.py"), "__name__": "make_more_data"}
    exec(compile(text, "make_more", "exec"), scope)
    return scope["BATCHES"], scope["COMMON_BODY"]


BATCHES, COMMON_BODY = old_batches()

WAVE_NOTE = [
    "- **波次模式蓋掉上面的「比對」「另跑」「審查」**：上面寫要跑的比對、`explore-compare`、另外要跑的那幾串測試，一律由波末的閘門一次跑，你不跑；README 的「另外要跑的」照寫。上面寫「先回報 PM」「先過 PM」的，選最保守的做法（位置與先後不動）寫進 decided，不等。",
]
SURVEY = "docs/superpowers/handoff/2026-11-06-develop合回盤點"


def batch(n, title, pkg, dev, plan, ports, body, model=None, custom=False):
    d = dict(n=n, title=title, pkg=pkg, dev=dev, plan=plan, ports=ports, body="\n".join(body + COMMON_BODY + WAVE_NOTE))
    if model:
        d["model"] = model
    if custom:
        d["custom"] = True
    return d


def b45():
    old = BATCHES["45"]
    return batch(45, old["title"], "bounties", "dev/bounties-1", old["plan"], 8244, old["body"])


def b28():
    return batch(28, "玉璽二——奪璽單挑、七種獨門行動、碎片卡、管理者九個工具（`seal_duel` 進包 `seal`）", "seal", "dev/seal-2",
                 "docs/superpowers/plans/2026-11-06-玉璽包-第2批.md", 8250, [
        "- 範圍照總表第 28 列（約 22 個方法、436 行）與第二節「玉璽碎片」：奪璽單挑、七種獨門行動、碎片卡、管理者九個工具進第 27 批開的包 `seal`；`seal_duel.py` 進包（舊名留別名）；`seal:` 前綴；`bot_policy` 的 `seal:` 那一段搬進包的 `bots.py`。",
        "- **第 27 批 PM 認定第 2 條**：`GAME_DIRECT` 裡寫「過渡：第 28 批收」的 13 筆方法搬走時，engine 裡的 `seal_rules.` 在包裡寫回 `seal.`。engine 頂端的 `from . import seal as seal_rules` 沒人用了就拿掉（戰力快照的參數 `seal` 不要動）。",
        "- develop 已經合進這條分支（`f69d306e`）：`_seal_challenge` 的 `seal_duel.faced`、`_seal_spectators` 與 `_seal_side_of` 的 `card=`、`seal_gamble` 的魅力那一行、奪璽單挑寫戰記的地方，都是現行程式，照現行程式搬。",
        "- 現有的 `relic` 軌（第 27 批開的）看走到多少，獨門行動、奪璽單挑、管理者工具走不到的才補。",
    ], model="sonnet")


def b51():
    return batch(51, "玉璽三——`seal_acts` 拆兩半：16 個璽效查詢進共用規則層，目標、灰掉的原因、碎片卡進包", "seal", "dev/seal-3",
                 "docs/superpowers/plans/2026-11-06-玉璽包-第3批.md", 8251, [
        "- 範圍照總表第 51 列（0 個 `Game` 方法）：`tianxia/seal_acts.py` 裡 16 個璽效查詢（別包會讀的）進共用規則層或核心 `core/seal_base.py`（照第 27 批把純函式放 `seal_base` 的前例，包 re-export 同一個物件），目標、灰掉的原因、碎片卡進包 `seal`；舊名留別名。別包讀的照新位置改，不准包對包。",
        "- 這一批從第 28 批的結果開。不必加新軌（`relic` 與第 28 批補的走到就好）；走不到才加。",
    ], model="sonnet")


def b52():
    return batch(52, "戰記——`tale`、`tale_html`、server 的戰記那一段與 `/api/tale`（新包 `tale`）；先開「背景執行緒」小掛鉤", "tale", "dev/tale-1",
                 "docs/superpowers/plans/2026-11-06-戰記包-第1批.md", 8252, [
        "- 範圍照總表第 52 列與盤點 `" + SURVEY + "/3-features.md` 第 2.10 節：`tianxia/tale.py`、`tale_html.py`、server 的戰記那一段（`TALES`、`narrate_*`、`tale_cover`、`tale_page_view`、`tale_view`、封面常數）、`/api/tale` 與分享頁路由進新包 `tale`（路由照商城的做法進包的 `routes.py`；舊名留別名）。develop 的戰記線已經合進這條分支（`f69d306e`），照現行程式搬。",
        "- **先做**：開「背景執行緒」小掛鉤（殼開、測試停；`tests/conftest.py` 收尾用到的名字不改），第 53 批的看守執行緒會用它。核心開掛鉤的寫法照 `core/features.py` 既有的。",
        "- **`web/` 不碰**：`app.js` 的戰記歸第 66 批（網頁殼化三）。",
        "- `battle_instance.write_tales` 等決戰包或 `battle_instance` 叫戰記的地方留原位，改經服務或核心的小模組，不准包對包。第 54 批同時在拆 `battle_instance`，你不動那個檔的別的地方。",
        "- 看現有的軌有沒有走到戰記（模型擋著時的預設字、`/api/tale`、分享頁）；走不到的補一軌，模型一律擋著（`127.0.0.1:9`）。",
    ])


def b53():
    return batch(53, "手機通知——`notices`、`server_push` 的推播那一半、`/api/push` 五條與 `/sw.js`（新包 `push`）；看守執行緒用第 52 批的掛鉤", "push", "dev/push-1",
                 "docs/superpowers/plans/2026-11-06-手機通知包-第1批.md", 8253, [
        "- 範圍照總表第 53 列：`tianxia/notices.py`、`server_push.py` 的 Web Push 那一半（`b64url`、`encrypt`、`Vapid`、`PushStore`、`WebPush` 這一段；SSE 的 `PushHub`、`watch_world`、`sse_stream` 是殼，留在 `server_push.py`）、`/api/push` 五條與 `/sw.js` 進新包 `push`；舊名留別名；開行程的那一下留殼或用第 52 批的背景執行緒掛鉤。**包名先查同名**：`tianxia/push.py` 存在就換名，寫進 decided。",
        "- 這一批從第 52 批的結果開。`server_push.py` 這一批可以改（總表第 53 列寫的；develop 從錨點以來沒動它）。只在這條分支上改，不碰任何正在跑的伺服器；`.local/webpush_vapid.pem` 不動、不讀內容。",
        "- **`web/` 不碰**：`app.js` 的推送、`sw.js` 檔本身歸第 66 批；`/sw.js` 路由搬、檔不搬。",
        "- 看現有的軌有沒有走到 `/api/push` 五條與 `/sw.js`；走不到的補一軌（訂閱、退訂、測試推送都不准真的打外面：`push_host_ok` 擋或換掉送出那一下，兩邊一樣）。",
    ], model="sonnet")


def b54():
    return batch(54, "決戰收尾——`battle_instance` 拆兩半：資料型別留核心，規則進決戰包", "battle", "dev/battle-end",
                 "docs/superpowers/plans/2026-11-06-決戰包-收尾.md", 8254, [
        "- 範圍照總表第 54 列（`Game` 方法 0 個，模組約 2,367 行）：`world_state`、`sqlite_world` 用的資料型別（約 290 行）留核心（例 `core/battle_types.py`，照 `seal_base` 的前例；或就留 `tianxia/battle_instance.py` 當薄的那一半，量了選一種，寫進 decided），規則（約 101 個函式、1,700 行）進 `tianxia/features/battle/`，舊名留別名、re-export 同一批物件。**這是全表最大的一刀**：太大就分兩個 commit，不用拆批。",
        "- develop 改過這個檔，已經合進這條分支（`f69d306e`），照現行程式搬。被 patch 的名字（`git grep` 測試、`scripts/`）要打得到：呼叫端照舊經被換的那個模組屬性叫。",
        "- 第 52 批同時在搬戰記：`write_tales` 這類叫戰記的地方，你照搬、不改內容，合併時接。",
        "- 不必加新軌（`battle` 系列的軌都走到了）；閘門會逐位元組比。",
    ])


def s2a():
    return batch("合回2A", "主幹合回 develop 第 2 段 A：屬性 v2 的動作進修練包（`pick_growth` 與事件歷練）", "cultivation", "dev/mb-a",
                 "docs/superpowers/plans/2026-11-06-develop合回-A.md", 8255, [
        "- 範圍照盤點 `" + SURVEY + "/3-features.md` 第 2.1～2.4 節、`0-critic.md` 第二之 4、第三節第 2 段 A，與手冊第十五節「develop 合回的 PM 認定」第 1、5、6、7、13 條：屬性 v2 新加的 `Game` 方法進 `tianxia/features/cultivation/`，`Game` 留一行委派或依第 6 條的三步。`pick_growth` 留在 `Game` 的只有三步（籌備中擋、沒有配比、已定回 `Refused`），其餘進修練包，不進 `GAME_DELEGATES`。",
        "- **收掉**邊界測試裡寫「暫時：第 2 段 A 收」的每一筆（`git grep -n '第 2 段 A' tests/`）。存檔欄位一律原名（`growth_preset`、`growth_custom`、`attr_event`、`attr_alloc`、`attrs_v2`）。",
        "- 現有的 `growth` 軌（第 0 段寫的）已經走到；不加新軌。這是 develop 上已經上線的玩法，一個字都不能變。",
    ], model="sonnet", custom=True)


def s2b():
    return batch("合回2B", "主幹合回 develop 第 2 段 B：傳承包補規矩（網頁切出 `web/legacy.js`、局面檔、契約的 `prep`）", "legacy", "dev/mb-b",
                 "docs/superpowers/plans/2026-11-06-develop合回-B.md", 8256, [
        "- 範圍照盤點 `" + SURVEY + "/3-features.md` 第 2.8、2.9 節、`0-critic.md` 第三節第 2 段 B，與手冊第十五節「develop 合回的 PM 認定」第 2、4 條：`web/app.js` 裡傳承那約 130 行切到 `web/legacy.js`（改 `index.html`、`tests/kit/webharness.py` 的 `APP_FILES`、包的 README），局面檔、契約的 `prep` 兩條照盤點補。`features/legacy/`、`features/hire/` 已經是包，補的是主幹的規矩（`stage`、`player_fields`、`aliases()`、`bots.py`……照盤點逐條）。",
        "- **這一批可以碰 `web/`，只碰傳承那一段**：純切出去，一個字不改；載入順序不能動到別的。",
        "- 現有的 `legacy` 軌（第 0 段寫的）已經走到；不加新軌。",
    ], model="sonnet", custom=True)


def s2d():
    return batch("合回2D", "主幹合回 develop 第 2 段 D：人物與地點畫面、往來紀錄（`figures_here_view`、`_figure_side_name`、`talk_view`、`place_state_view`、`talk_log` 與路由）", "companions", "dev/mb-d",
                 "docs/superpowers/plans/2026-11-06-develop合回-D.md", 8257, [
        "- 範圍照盤點 `" + SURVEY + "/3-features.md` 第 2.5、2.6、2.7 節、`0-critic.md` 第三節第 2 段 D，與手冊第十五節「develop 合回的 PM 認定」第 3、7、8、9 條：`figures_here_view` 進交友求見包（`features/socialize/`，邊界測試那幾筆寫的）、`_figure_side_name`、`talk_view` 一起搬；`talk_log.py`（119 行）與路由 19 行進人物情誼包（舊名留別名）；`place_state` 留共用層、`place_state_view` 留核心；`figures.side_name` 照盤點。`server.py` 的 `figure_intro`、`FIGURE_INTROS`（develop 最後那 5 筆，`5-重量.md`）跟著 `figures_here_view` 走。",
        "- **收掉**邊界測試裡寫「暫時：第 2 段 D 收」的每一筆（`git grep -n '第 2 段 D' tests/`）。存檔欄位一律原名（`places`、`card`）。",
        "- **新軌 `here`、`places`**（原創名字照盤點，接在檔尾），各跑一次 selftest。**往來紀錄不在 same_behavior 裡**（只清小檔不比）：這一批自己做一次兩台伺服器 HTTP 比對（base＝這條分支的開工那一筆，head＝做好的），同一串步驟打到往來紀錄的每一條路由，逐位元組比，寫進計畫。這是這件事唯一一次驗。",
    ], custom=True)


WAVES = {
    "A": dict(
        lines=[
            dict(name="懸賞榜", batches=[b45]),
            dict(name="玉璽", batches=[b28, b51]),
            dict(name="戰記與通知", batches=[b52, b53]),
            dict(name="決戰收尾", batches=[b54]),
            dict(name="合回2A", batches=[s2a]),
            dict(name="合回2B", batches=[s2b]),
            dict(name="合回2D", batches=[s2d]),
        ],
        merge_port=8258, fix_port=8259,
        web_check=dict(ports="8260、8261", steps="開季準備卡的識海（傳承）那幾個畫面：候選開著、挑好、撞名候選、解不開的封存；其他畫面不用看（這一波 `web/` 只動傳承那一段）。"),
    ),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("wave")
    ap.add_argument("base")
    ap.add_argument("out")
    ap.add_argument("--scratch", default=r"C:\Users\ray61\AppData\Local\Temp\claude\81800b313c89d0f8\ade93b70-b3b7-42db-a8af-21f7a7cbdb16\scratchpad")
    ap.add_argument("--finish", default="", help="開發回來的 built（JSON 檔）；有給就只合併、閘門、審查、修正")
    ap.add_argument("--merge-base", default="")
    ap.add_argument("--merge-extra", default="", help="合併時要多合的東西（文字檔）")
    a = ap.parse_args()
    w = WAVES[a.wave]
    args = {"wave": a.wave, "scratch": a.scratch, "branch": f"wave/{a.wave}", "merge_port": w["merge_port"], "fix_port": w["fix_port"]}
    if a.finish:
        args["built"] = json.loads(Path(a.finish).read_text(encoding="utf-8"))
        args["merge_base"] = a.merge_base
        if w.get("web_check"):
            args["web_check"] = w["web_check"]
        if a.merge_extra:
            args["merge_extra"] = Path(a.merge_extra).read_text(encoding="utf-8")
        name = f"wave-{a.wave}-finish.js"
    else:
        args["stop_after_build"] = True
        args["lines"] = [dict(name=l["name"], base=a.base, batches=[f() for f in l["batches"]]) for l in w["lines"]]
        name = f"wave-{a.wave}.js"
    meta_end = SRC.index("}\n", SRC.index("export const meta")) + 2
    body = re.sub(r"\bargs\b", "ARGS", SRC[meta_end:])
    text = SRC[:meta_end] + "\nconst ARGS = " + json.dumps(args, ensure_ascii=False) + "\n" + body
    (Path(a.out) / name).write_text(text, encoding="utf-8", newline="\n")
    print("wrote", Path(a.out) / name, len(text))


if __name__ == "__main__":
    main()
