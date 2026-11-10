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


CORE_RULE = "- **核心批，沒有新包**：Task 2～4 寫「搬進 `tianxia/features/<包>/`」的地方換成：**Task 2** 在 `tianxia/core/features.py` 開掛鉤（寫法照第 11、25 批：位置固定、不看包的 `enabled`、照 `registered()` 問；叫各包的順序寫死在核心的順序表，加一條契約測試鎖住）；**Task 3** 把 `Game` 裡直接碰各包的地方改叫掛鉤，各包在自己的檔裡掛上自己那一格；**Task 4** 契約與邊界測試。**順序就是行為**：同一下各包的先後、訊息行、世界旗標、亂數抽到的順序都要跟現在一模一樣。接不上的（開關問法不同、先後會變）留 `GAME_DIRECT` 寫明理由，不硬接。"
WEB_RULE = "- **網頁批**：可以碰 `web/`、`index.html`、`tests/kit/webharness.py` 的 `APP_FILES`。只切、不改：每段程式一個字不動、頂層敘述的先後等價（載入順序就是行為）；`web/` 的檔連註解都不准寫假人那幾個字（`tests/bots/test_server_bots.py` 掃）。新檔照手冊 G9 叫 `web/<包>.js`、`web/<包>.css`。跑 `tests/web` 裡寫到這幾個檔名的測試一次（挑得到幾個跑幾個，不跑全部）。波末有一次實機驗收，你不做。"


def b55():
    return batch(55, "補算與換季收接縫（核心）", "core_seams", "dev/core-seams-1", "docs/superpowers/plans/2026-11-06-補算換季收接縫-第55批.md", 8262, [
        CORE_RULE,
        "- 範圍照總表第 55 列整格：`sync`、`advance`、`world_tick`、換季重設、清失效參照裡各包的那一段，改成 `on_sync`、`on_day`、`on_season_*`、`on_drop_stale`。先後會影響結果的留 `GAME_DIRECT`，寫明理由。`signature_arms.refresh_names` 照第 40 批 `smith_base` 的前例放進共用層或核心的 `*_base`，收掉那一筆 `GAME_DIRECT`（`on_drop_stale` 只問開著的包，原位的 `refresh_names` 不看開關）。",
    ])


def b56():
    return batch(56, "選單收接縫（核心）", "core_seams", "dev/core-seams-2", "docs/superpowers/plans/2026-11-06-選單收接縫-第56批.md", 8263, [
        CORE_RULE,
        "- 範圍照總表第 56 列整格：`_everyday_options`、`action_notes`、`_preparing`、`is_idle` 裡各包的那一段改成 `options`、`menu` 掛鉤；`fs_asking` 那兩處改問 `omen_base.fs_answering`；`atlas.travel_block` 直接讀的別包欄位（第 56 列的 13 個，加第 45 批記的 `picking_bounty`，以現行程式為準）改成動身被擋掛鉤加一張先後表，判斷的先後照現在 `travel_block` 的順序。",
        "- **三間店排進 `Shop`**（第 41、42、45 批 PM 認定留給這一批）：入口先後維持 懸賞榜 → 鐵匠鋪 → 馬市 → 其他店。`features_core._shops` 照 `FEATURES` 走、酒肆排在前面；`sync` 只收鐵匠鋪、馬市；鐵匠鋪的 `here` 有兩個意思。要動到先後或多收一次的，**這三間就照舊留原位**、寫進 decided，不硬接。",
    ])


def b57():
    return batch(57, "分派與標題收接縫（核心）", "core_seams", "dev/core-seams-3", "docs/superpowers/plans/2026-11-06-分派標題收接縫-第57批.md", 8264, [
        CORE_RULE,
        "- 範圍照總表第 57 列整格（範圍已改小）：`_act` 其餘的子動詞接上第 11 批開的同一張 `Verb` 表，選項 id 一個字不改；子動詞數開工重量。「做完一件事、引導跟著走」（`_note_action` 那七處與 `_faction_step`、`_arrive`、`take_stamina_pill`）：量了之後要開事件才接得上的，**不開**、照舊留著寫理由（開新事件要過 PM，波次模式選保守的）。",
    ])


def b58():
    return batch(58, "商城收尾——拿掉 12 個一行委派、寄放的兩項收回包、三處過渡 import 換核心服務", "mall", "dev/mall-end", "docs/superpowers/plans/2026-11-06-商城收尾-第58批.md", 8265, [
        "- 範圍照總表第 58 列。這一批**會改測試的呼叫**（`g.mall_buy` 這類改叫包裡的函式），這是總表寫明的，只改呼叫方式、不改斷言；寫進 decided 改了幾處。第 55～57 批同時在改 `engine.py` 別的地方，你只拿掉委派那幾行。",
    ], model="sonnet")


def b59():
    return batch(59, "引導二：玩法說明——`howto` 進包、開「說明行」小掛鉤、`/api/howto`", "guide", "dev/guide-howto", "docs/superpowers/plans/2026-11-06-玩法說明-第59批.md", 8266, [
        "- 範圍照總表第 59 列：`howto`（約 1,329 行，import 26 個模組）進引導包；各節由各包交（「說明行」小掛鉤，順序表寫死在核心、跟現在每一節的先後一樣）；`/api/howto` 進包的 `routes.py`。**輸出逐字不變**。別包的那一節放在那一包的檔裡；讀到還沒成包的舊模組的，標過渡。",
    ], model="sonnet")


def b60():
    return batch(60, "假人殼收尾（核心）——`bot_policy` 改叫服務、「永遠按得下去」只問包的宣告、`act:` 那一段分給各包", "core_bots", "dev/core-bots", "docs/superpowers/plans/2026-11-06-假人殼收尾-第60批.md", 8267, [
        CORE_RULE,
        "- 範圍照總表第 60 列：`bot_policy` 不再叫 `Game` 的私有方法，改叫服務；`bot.pick` 的「永遠按得下去」只問各包的宣告；`act:` 那一段約 70 行照第 57 批的子動詞分給各包；`choice:`、`season:` 兩段留核心。**假人的選擇逐位元組不變**（閘門的假人軌會比），分數相同時的先後也算。任何畫面、輸出不能透露誰是假人。",
    ])


def b61():
    return batch(61, "混合測試檔歸位——`test_engine`、`test_server`、`test_jianghu_page_web` 等照包拆開搬走、拿掉 `test_for` 的過渡挑法", "core_tests", "dev/core-tests", "docs/superpowers/plans/2026-11-06-混合測試檔歸位-第61批.md", 8272, [
        "- 範圍照總表第 61 列：混合測試檔照包拆開搬進各包的 `tests/`，**只搬位置、不改斷言**（寫一支腳本比搬前搬後的測試名與本體：一條都不能少、語法樹一樣）；檔名全 repo 不能重複；被裸名 import 的檔留意 `tests/conftest.py` 的 `sys.path`；拿掉 `test_for` 的過渡挑法。第 38 批 PM 認定第 2 條照總表那一格。**不開伺服器、不改程式**，只有 `engine.py` 那一行過渡 import 與 `GAME_IMPORTS` 那一筆照總表拿掉。",
    ], model="sonnet")


def b62():
    return batch(62, "內容照包分一（核心）——`content.py` 照 `FEATURES` 載各包的 `content/`，已成包的 json 搬進包", "core_content", "dev/core-content-1", "docs/superpowers/plans/2026-11-06-內容照包分-第62批.md", 8268, [
        "- 範圍照總表第 62 列、第四節。**載入的順序與結果逐位元組不變**（同名蓋掉的先後算行為）；`content/config.json` 與設定覆寫檔留原處；`scripts/`、`check_content`、`banned_names` 讀的路徑跟著改。內容檔只搬不改字；招募內容檔照 PM 定的只改名。主機端開伺服器的方式（`beta-主機端操作.md`）不能因此要多做一步。",
    ])


def b63():
    return batch(63, "內容照包分二（核心）——事件池與測試內容照包分、第二級測試只載核心加一包", "core_content", "dev/core-content-2", "docs/superpowers/plans/2026-11-06-內容照包分-第63批.md", 8269, [
        "- 範圍照總表第 63 列、第四節：事件池照包分（沒人認領的 23 個事件池歸核心，附錄甲）、`tests/fixtures/content` 照包分；第二級測試只載核心加一包。事件抽選的先後（亂數抽到的順序）跟現在一模一樣。",
    ])


def b64():
    return batch(64, "網頁殼化一——`index.html` 的 script 標籤由伺服器照 `FEATURES` 生成、`registerPage` 掛鉤、切出修練與煉製的畫面", "shell_web", "dev/shell-web-1", "docs/superpowers/plans/2026-11-06-網頁殼化-第64批.md", 8270, [
        WEB_RULE,
        "- 範圍照總表第 64 列、第四節（約 1,400 行）。生成的 script 標籤順序要讓頂層敘述跟現在等價：先照現在的順序排，切出去的檔接在原本那一段的位置；`/` 回的 HTML 除了多出來的 script 標籤之外一個字不變。傳承的 `web/legacy.js`（A 波切的）照新做法接上。develop 從錨點以來改了很多 `web/`，都已經合進來，以現行程式為準。",
    ])


def b65():
    return batch(65, "網頁殼化二——鐵匠鋪、裝備、銀兩出口、酒肆、懸賞榜、擂台的畫面", "shell_web", "dev/shell-web-2", "docs/superpowers/plans/2026-11-06-網頁殼化-第65批.md", 8271, [
        WEB_RULE,
        "- 範圍照總表第 65 列（約 600 行），做法照第 64 批。懸賞榜那幾個函式（`boardHtml`、`paperHtml`、`boardUnpick`、`boardZoom`、`boardClose`、`boardLeave`、`boardHanded`、`STAMP_MS`）在這一批。",
    ], model="sonnet")


def b66():
    return batch(66, "網頁殼化三＋狀態列掛鉤——其餘各包的畫面、`/api/main` 的鍵由 `status` 掛鉤照現在的順序合", "shell_web", "dev/shell-web-3", "docs/superpowers/plans/2026-11-06-網頁殼化-第66批.md", 8273, [
        WEB_RULE,
        "- 範圍照總表第 66 列（約 1,100 行）：玩家互動、有所感、引導、玉璽、列傳、通知、戰記、出陣、移動、地盤等；`app.js` 的戰記、推送（第 52、53 批留的）；`sw.js` 檔照新位置（路由第 53 批搬了）。`/api/main` 的鍵改由 `status` 掛鉤照現在的順序合（**JSON 鍵的先後算行為**，閘門逐位元組比）。`CORE_TOP_DELEGATE_CALLERS` 那 4 對（`weekcard` → `_opening_pending`、`sides_card`、`tier_hint`）照總表收。量一次 `app.js` 行數（目標 < 3,000，超過照總表第四節先拆 `S`、`FIT_STEPS`），寫進回報。",
    ])


def b67():
    return batch(67, "網頁殼化四——江湖頁 `main.js` 與 `style.css` 照包分", "shell_web", "dev/shell-web-4", "docs/superpowers/plans/2026-11-06-網頁殼化-第67批.md", 8274, [
        WEB_RULE,
        "- 範圍照總表第 67 列（`main.js` 約 1,867 行、`style.css` 約 3,568 行）。**CSS 的先後就是行為**（同權重後蓋前）：切出去的 `web/<包>.css` 照原本的位置順序載入；拿不準的段落留在 `style.css`。`bountiesHtml`、`rewardChips` 在這一批。",
    ], model="sonnet")


def b68():
    return batch(68, "伺服器分包一——`MAIN_ACTIONS`、`ADMIN_ACTIONS`、`MENXIA_ACTIONS` 照包分、管理者頁照 `admin_tools` 掛上來", "shell_server", "dev/shell-server-1", "docs/superpowers/plans/2026-11-06-伺服器分包-第68批.md", 8275, [
        "- 範圍照總表第 68 列：三張動作表照包分（表的先後與鍵的順序不變），管理者頁照各包的 `admin_tools` 掛上來、畫面逐字不變。`web/admin.js` 不動（第 64～67 批在動 `web/` 別的檔，這一批不碰）。",
    ], model="sonnet")


def b69():
    return batch(69, "伺服器分包二——三段式的鎖外那一段進各包、開「鎖外工作」掛鉤", "shell_server", "dev/shell-server-2", "docs/superpowers/plans/2026-11-06-伺服器分包-第69批.md", 8276, [
        "- 範圍照總表第 69 列（`prepare_*`、`write_*`、`*_once` 約 1,000 行）。旁白、排程照舊在殼。**模型呼叫絕不進鎖**，A、B、C 三段的先後與「過期就丟掉」照舊；`_quick_client`、`in_lock_model_timeout`、`MODEL_BREAKER_SECONDS` 那一套不動。第 24 批 `sense_draw` 是範本。",
    ])


EXTRA_LENSES_B = [
    dict(key="order", text="**順序就是行為**。第 55、56、57 批把 `sync`、`advance`、`world_tick`、`_advance_player_local`、`own_turn_checks`、`_drop_stale_references`、`_reset_player_for_new_season`、`options`、`_everyday_options`、`action_notes`、`_idle`、`atlas.travel_block`、`departure` 收店、`_act`、`_action_title` 改成照 `SEAM_ORDER`、`MENU_ORDER`、`Verb` 問。逐段把 base 的原始碼（語句的先後、回話接的順序、亂數、世界旗標、有沒有開關判斷）跟 head 照表展開之後的先後並排比，每一格對一行。特別打：`season.carry` 開發自己承認不是一行對一行（L583-656 併成 13 格，「純欄位互不讀」是推論），請你用語法樹列每一格讀寫的欄位，證明或推翻互不干擾；`heirloom`、`naming`（讀 prune 之前算好的 owned）、`lost_place`；核心代叫的 `_SEAM_CORE` 格與包的格穿插的地方；開發列的「軌走不到」：`advance` 的 `conquest_tick` 回話有字、測試內容裡假人換季、L767、L881、`pill_line` 0 顆、`faction_lines`。"),
    dict(key="bots", text="**假人的選擇不能變，也不能露餡**。第 60 批把 `bot_policy.score` 的 `act:` 那一段分給各包、`bot.pick` 只問宣告。逐項比 base 的 `score`、`pick`、`take_turn` 與 head 展開之後：同一個選項拿到的分數、分數相同時的先後、亂數抽幾次、落到 `ACT_SCORES.get(arg, 0.0)` 的（0.0 是隨機挑得到的，不是不按）、`bot_skip`、`bot_idle` 比相等與比前綴有沒有多排或少排；`picking_*` 六處；同值重寫的常數。另外 `web/` 與任何畫面、輸出不能出現假人那幾個字（`tests/bots/test_server_bots.py` 掃的範圍涵蓋新檔了嗎：`web/shell.js`、`state.js`、`fit.js` 與各包 js、css）。"),
    dict(key="locks", text="**模型呼叫不進鎖、三段式不變**。第 69 批把鎖外那一段搬進各包 `routes.py`、開 `outlock`。逐個比 base 與 head：A、B、C 三段的先後、哪一段在 `action_lock` 裡、過期就丟掉、`_quick_client`、`in_lock_model_timeout`、`MODEL_BREAKER_SECONDS`、`model_call`、`within_budget`；背景六格的先後（`OUTLOCK_ORDER`）跟原本 `act` 那幾行的順序；閉包有沒有抓到舊值（迴圈變數、`shell.<名字>` 當下讀與 import 時讀）；執行緒是不是 daemon、`threads` 掛鉤開的時機與 `uvicorn.run` 的先後；`conftest` 收尾停得到每一條；第 52、53 批的 `TALES_*`、`NOTICE_*`。`server.py` 頂上那行只為了 import 先後留著的名字（玩家卡按鈕順序只靠它）：`core.cards.ACTIONS` 的登記順序在 base、head、`run_bots.py`、單獨 `import tianxia.engine` 四種入口各印一次，有沒有不一樣。"),
    dict(key="content", text="**內容一筆都不能掉、先後不能變，主機也要開得起來**。第 62、63 批把內容檔搬進各包。用真的 `load_content` 在 base 與 head 各載一次 season21、week7、不帶設定與測試內容，`model_dump_json` 比雜湊；事件池的先後（同名蓋掉、抽籤順序）。`_locate` 認「真實的根」的判斷：另一份 clone、`C:\\Ray\\tianxia-play` 那種部署目錄（只讀路徑推演、**不要碰那個資料夾**）、`.claude/worktrees/` 底下、`TIANXIA_DB` 不同時，會不會判錯變成讀不到而靜靜變空。`scripts/` 裡直接讀 `content/<檔>` 的（`git grep -n 'content/' scripts`，含 `make_*`、`convert_*`、`measure_*`、`warm_keeper`、`monitor`）；`docs/superpowers/feedback/beta-主機端操作.md` 寫的步驟要不要多做什麼；`.gitignore`、`git archive` 的 export-ignore 會不會漏掉包裡的 `content/`；`test_real_content`、`DIFFICULTY_BANDS` 還讀得到全部事件嗎。"),
    dict(key="web", text="**頁面不能壞，載入順序就是行為**。第 64～67 批把 `app.js`、`main.js`、`style.css` 切成包的檔，`index.html` 的 script 由伺服器生成。靜態證明：把 base 的 `app.js`、`main.js` 與 head 所有 js 照實際載入順序接起來，頂層敘述（非函式宣告）的先後逐條比；有沒有檔在載入當下就讀到還沒定義的 `const`、`let`（TDZ，函式宣告才會提升）：這是切檔最常見的炸法，用 node 的 `--check` 不夠，要把每支檔頂層讀的識別字對到它定義的檔與載入順序。CSS：`scripts/css_order_check.py` 抓不到資料表組出來的 class，你另外列 js 裡組字串產生的 class，對照它們的規則搬到哪一支、先後有沒有反轉。`/`、`/admin`、`/static/...` 與 service worker（`web/sw.js`）快取清單有沒有漏新檔；`?v=` 版本號；`web/` 新檔有沒有被 `.gitignore` 擋。`style.css` 第 2931 行多的 `}` 兩邊都一樣嗎（這一波不修）。"),
]

WAVES["B"] = dict(
    extra_lenses=EXTRA_LENSES_B,
    lines=[
        dict(name="核心接縫", batches=[b55, b56, b57, b60]),
        dict(name="商城收尾", batches=[b58]),
        dict(name="玩法說明", batches=[b59]),
        dict(name="內容", batches=[b62, b63]),
        dict(name="網頁", batches=[b64, b65, b66, b67]),
        dict(name="伺服器", batches=[b68, b69]),
    ],
    merge_port=8277, fix_port=8278,
    web_check=dict(ports="8279、8280", steps="每一頁都看：江湖頁（本週卡、三方卡）、修練（改練、意境、熔煉、配點）、煉製與自創、鐵匠鋪、馬市、銀兩出口、酒肆、懸賞榜、擂台、玩家卡、有所感、引導框、玉璽碎片卡、列傳、戰記頁、通知開關、出陣、移動、地盤、輿圖、管理頁。"),
)
EXTRA_LENSES_C = [
    dict(key="takein", text="**新進來的東西不能掉，位置要對**。這一波把 develop 的大決戰面板（sasojoy/ai_story#180，`34e4ca8f..c543d3d0`）與 main 的神品意境一人兩份（`ca258cc6`）合進已經切好的新架構。閘門比的是 `4033ddc0`（develop＋main，舊位置）對 head，只抓得到情境走得到的，面板是新功能，多半沒有軌走到。逐 hunk 核對：兩個提交的每一段增刪在 head 上都找得到（位置可以不同）。`web/app.js`、`web/main.js`、`web/index.html` 每一段；`web/battle.js`、`web/battle.css` 兩邊同名合起來的結果，字面都在、先後沒變；js 頂層有沒有 TDZ，每個頂層讀的識別字對到定義的檔與載入順序；`WEB_ORDER`、`APP_FILES`、`web_scripts()` 一致；`css_order_check.py` 對 `4033ddc0`。`battles.json`：用真的 `load_content` 在 `4033ddc0` 與 head 各載 season21、week7、不帶設定，`model_dump_json` 比雜湊。`test_battle_panel`、`test_battle_gauge`、#180 動過的 jianghu 測試、`test_epiphany`、`test_legacy` 都在、收集得到（`--collect-only`）。battle 包 `__init__.py` 那 8 行接到哪、面板資料真的出現在 `/api/main`（行程內 TestClient，不開埠）。`tianxia/arts.py`、`features/legacy/actions.py`、`models.py` 的改動字面都在。"),
]
WAVES["C"] = dict(
    lines=[dict(name="測試歸位", batches=[b61])], merge_port=8281, fix_port=8282,
    extra_lenses=EXTRA_LENSES_C,
    web_check=dict(ports="8283、8284", steps="**只看這一波新合的畫面，其他畫面上一波比過了（B 波 1482 鏡，same=true）**。工具可以重用：C:\\Users\\ray61\\AppData\\Local\\Temp\\claude\\81800b313c89d0f8\\ade93b70-b3b7-42db-a8af-21f7a7cbdb16\\scratchpad\\waveB\\qaBui\\tools（`unpack.py`、`go.py`、`detail.py`；出陣與決戰那幾鏡的場景寫好了，先讀檔頭）。看：(1) 大決戰面板：集結、開打、出招不跳提示、放手一搏的輸入框、倒數、主將血條、戰報、陣中氣血、關鍵時刻覆蓋、收場；決戰期間本週條不寫兩軍數字。(2) 煉製頁的預覽卡放兩份同一路意境：`.lv i` 沒亮那一格的底色與圓角跟 base 一樣（B 波修過，這是第一次走真實流程）。(3) 江湖頁、修練頁各一鏡當煙霧。**不超過 80 鏡、約 60 分鐘**，到了就交，沒走到的寫清楚。"),
)


R2 = "docs/superpowers/plans/2026-11-07-第二輪拆分-總表.md"
R2_NOTE = [
    "- **第二輪的批**：範圍照第二輪總表 `" + R2 + "` 這一批那一節整節（grep 標題找到，只讀那一節、第二節的「裁決」與第十節；第一輪總表的列與附錄甲不適用）。數字量在舊的一筆，**開工照現行程式重量，對不上以程式為準**，寫進 decided。",
    "- **各包 README、`docs/guide` 線上不動（PM 11/07 定）**：要寫的句子放回報的 `docs`（一條一句，寫明哪個檔、改哪裡），波末一位文件代理統一寫。",
]


def r2(n, title, pkg, dev, ports, body, model=None):
    plan = f"docs/superpowers/plans/2026-11-07-第二輪-第{n}批.md"
    return batch(n, f"第二輪第 {n} 批：{title}", pkg, dev, plan, ports, body + R2_NOTE, model=model, custom=True)


QA_TOOLS = r"C:\Users\ray61\AppData\Local\Temp\claude\81800b313c89d0f8\ade93b70-b3b7-42db-a8af-21f7a7cbdb16\scratchpad"


def b70():
    return r2(70, "same_behavior 一軌一檔（`scripts/sb/`）", "tools", "dev/sb-1", "8285", [
        "- 範圍照那一節：調度與固定層進 `scripts/sb/harness.py`，Scenario、DuelScenario、假人進 `scripts/sb/base.py`，每段軌一檔 `scripts/sb/tracks/<軌>.py`。`scripts/same_behavior.py` 留 CLI 入口、路徑與指令不變：`wave_gate.py`、`trunk_daily.py`、`nightly`、`split-wave.js` 都照這個路徑叫，這幾支這一批不動，要改的句子放回報。用語法樹腳本機械搬；搬檔工具放暫存，不進 repo。",
        "- **這一批的驗證閘門做不到，你自己跑（這一條優先於波次模式的「你不跑 compare」與下面「波次模式蓋掉」那一條）**：閘門是拿 head 的腳本比兩邊，新腳本掉了一段情境，兩邊一起掉，照樣綠。所以用舊腳本（開工那一筆的 `scripts/same_behavior.py`）與新腳本，對同一對 base、head 各跑一次 `compare` 與 `explore-compare`（186 格加假人 5 組），**每一格的雜湊逐筆相同**，不是只看「兩邊一樣」。約 50 分、不花 token：用 `Start-Process` 分離啟動、輸出導到檔，`docs/superpowers/pm-workflows/wait_file.py <完成標記> 570` 等，不要前景跑。另外每條繼承鏈挑一軌 selftest（改一字抓得到），軌數還是 62。",
        "- 坑照那一節（`_setup_child` 拿掉 scripts/ 的路徑，軌要先載入；BUF、STEP、CLOCK、MODEL 要同一物件）。另外要留意：`compare` 用 head 的腳本跑 base 的根，`scripts/sb/` 一定要從腳本自己的位置載入，不能從被比的那棵樹載入，否則 base 上沒有這個資料夾。子行程也一樣。",
        "- `_*_register_track` 收成一個、`TRACK_NAMES` 照檔名排、軌名重複載入時就擋。",
    ])


def b71():
    return r2(71, "閘門快取與每軌秒數", "tools", "dev/sb-2", "8286", [
        "- 範圍照那一節，從第 70 批的結果開。`wave_gate.py` 只有這條線動。",
        "- **PM 定，跟那一節寫的相反：快取預設關，`--cache` 才開**（那一節寫「加 `--no-cache`」）。鍵漏掉相依會假綠，預設關才不會忘；只有同一波修正後重跑閘門時 PM 才加。進 develop、上 main 的那一次不開。",
        "- **閘門 `--web` 的介面（PM 定，第 77 批在另一條線做另一半）**：`wave_gate.py --web` 叫 `scripts/webqa/gate.py --base <sha> --head <sha> --out <資料夾>`，結束碼 0 才綠、其他算紅，結果接進 `result.json` 的 `web`。那個檔不存在（第 77 批順延）時印一行、`web` 寫沒跑，不擋。",
        "- 這一批不碰 `tianxia/`、`server.py`、`web/`。比對的驗證你自己跑（這一條優先於波次模式的「你不跑 compare」與下面「波次模式蓋掉」那一條），但只跑幾軌：開快取與不開結果一致、selftest 突變全部抓到（開快取時改一個字照樣抓得到）、前半快照接 head2 的雜湊等於整段。",
    ])


def b72():
    return r2(72, "一行委派進各包的表（`features/<包>/game_api.py`）", "core_api", "dev/game-api-1", "8287", [
        "- 範圍照那一節。**Q1 企劃者還沒答（PM 建議改）**：這條線先做，答否 PM 整條不合，你照「改」做，不用為了否做任何事。",
        "- **PM 定的寫法**：直接掛函式本身，不包 `*args, **kwargs`。委派與本體參數名不同的（例 `write_biography(request,…)` 對 `write(ctx, req,…)`、`_ambush_record(…spoils…)` 對 `record(…got…)`）今天沒有關鍵字呼叫，attach 時用語法樹比一次、不同的列成名單，寫一條測試守。attach 遇同名丟例外。",
        "- 全腳本生成，手寫只有 attach 與兩支工具（工具放暫存）。只有委派在用的 `from .features` 與別名 import 分第二個 commit 拿掉，好退。比 `sys.modules` 順序：只拿委派要完全一樣；連 import 拿時逐一看 peers、bounties、renown、looks 的登記順序（玩家卡按鈕靠 `order=`，手冊第十五節「波次 B、C」第 8 條）。",
        "- 語法樹確認每個名字都在 `Game` 上、參數一致。一般測試一行都不改；守門的 `test_feature_boundaries`、`test_test_for`、`test_for.engine_delegates` 照那一節改。",
    ])


def b73():
    return r2(73, "邊界測試的名單正規化", "core_api", "dev/game-api-2", "8288", [
        "- 範圍照那一節，從第 72 批的結果開。第 72 批之後剩多少名單先重量，剩得少就併成一檔，不要真開 30 個檔。新舊所有大寫名單逐張相等（dict 的理由字也一樣），寫一支暫存腳本比；52 條本體不動。",
    ])


def b74():
    return r2(74, "核心表放鬆與服務清單", "core_api", "dev/game-api-3", "8289", [
        "- 範圍照那一節，從第 73 批的結果開。`merge=union` 先在本地驗過再用；GitHub 網頁驗不了，寫進回報。`tuning/<包>.py` 與 `new_feature.py` 照手冊第十五節「波次 B、C」第 15 條。",
    ])


def b75():
    return r2(75, "契約變快與 test_for 規則", "core_api", "dev/game-api-4", "8290", [
        "- 範圍照那一節，從第 74 批的結果開。第十節的 `test_for` 看穿 kit、`test_explain*` 搬進 guide 都在這一批。**核心服務檔（combat、pushing、pills、status_view、page_view、scene_view）這時還不存在**（E 波才開），規則先寫好、測試用假檔名驗。`IMPORT_CAP` 照舊不准動。量牆鐘寫進回報。",
    ])


def b76():
    return r2(76, "資料清單改一行", "core_data", "dev/data-lists", "8291", [
        "- 範圍照那一節。**一定用 `Field(..., json_schema_extra=QUIET)`，不能用 `Annotated`**（原型踩過：有 6 個欄位型別在後面，會多寫 6 個鍵）。**存檔位元組不變**：新算的 QUIET 集合等於舊清單，抽樣狀態 `model_dump_json` 比對，寫一支暫存腳本。資料庫結構不改。",
        "- 屬性等級武學那條線也在動 `models.py`、`state.py`，只動那一節寫的清單，不順手整理別的。",
    ])


def b77():
    return r2(77, "網頁比對工具正式化（`scripts/webqa/`）", "tools", "dev/webqa", "8292、8293", [
        "- 範圍照那一節。**工具的來源**：`" + QA_TOOLS + "\\waveB\\qaBui\\tools`（六輪 1,482 鏡）與 `" + QA_TOOLS + "\\waveC\\qaCui\\tools`（後來改過的版本，兩份都看，以 C 波的為新）；B 波的並排圖在 `waveB\\qaBui\\sheets`，比對紀錄在 `waveC\\qaCui\\log\\detail_f3.txt`。收進 repo 的路徑、埠、Chromium 都改參數，不寫死這份暫存。**不下載、不安裝任何東西**，用這台現有的。",
        "- **第 71 批在別條線接閘門，介面 PM 定了**：`scripts/webqa/gate.py --base <sha> --head <sha> --out <資料夾>`，結束碼 0 才綠。",
        "- **雜訊是這批成敗的關鍵**（那一節的坑：雜訊沒壓下來會成每次要人判的紅燈）。B、C 波判過的雜訊都要自動分類：圓角抗鋸齒差 1 色階、1280 捲軸 15px、canvas 影格、分享碼、臨時密碼、戰記寫作時機。算好的樣式是捲回頂端、換寬度後馬上取的，C 波跨輪出現方向對調的假差異（`.kiln compact`、`.shell` 高度與 margin）：**等版面穩定才取**。B 波的 `newbie_c05`、`pe_c07` 是判成雜訊但沒嚴格證明的，順手重現一次。",
        "- C 波學到的流程坑寫進工具：舊頁面還開著會輪詢、把覆蓋演掉，**改狀態前先離開頁面**；來信小卡會蓋掉本週條，要驗本週條得先婉拒託付信；換視窗大小會重畫，輸入框的字要送出前才填；開打前世界時間還是 0 時下戰書那場攻城會作罷，先快轉再下。拍覆蓋時要關自動關，另外實測一次自動關。",
        "- 語料除了那一節的序章、輿圖，**B 波沒走到的能走就補**：神器打造表單、看火候熬料確認送出、人物對話模型回話與勸降表單（模型指 `127.0.0.1:9`，走保底）、決戰 MVP 動畫與擂台特效、商城與形象買賣上架、管理頁 6 顆（`pause_clock`、`fire`、`summon` 等）、本週卡下一步與單項收起；C 波沒走到的：戰場摺疊、再看一次、官軍主將重創。走不到的寫清楚。",
        "- 工具自測：base 對 base 要 0、故意改一條要紅（正控制沿用 `.card` padding 與 style.css 排最後）；同一份跑兩次全同。**這條線不碰 `tianxia/`、`server.py`、`web/`**。跑完伺服器 `taskkill /T`、大檔刪掉。不超過 2 小時，到了就交，沒做完的放 leftovers。",
    ])


def b78():
    return r2(78, "版本網址長快取", "shell", "dev/long-cache", "8294", [
        "- 範圍照那一節，只改 `WebFiles.get_response` 與新增 2 條測試。**條件全部成立才回 `max-age=31536000, immutable`**：設了 `TIANXIA_PUBLIC_URL`，而且 `?v=` 等於那個檔現在的內容雜湊；其餘（沒帶 `?v=`、`?v=` 對不上、`/`、`/admin`、`/sw.js`、`index.html`）照舊 `no-cache`，測試各打一條。部署的人不用多做事。不碰 `web/`。",
    ])


EXTRA_LENSES_D = [
    dict(key="tools", text="**驗證工具不能變鈍**。第 70、71 批把 same_behavior 搬成一軌一檔、加快取。逐軌比開工那一筆與 head：每一段情境的步驟、每一條 `MUTATIONS`、`EXPLORE_MUTATIONS` 的目標句（搬了檔之後 `_mutant` 還找得到嗎）、`_bot_runs`、半舊半新的切點；`compare` 用 head 的腳本跑 base 的根時 `scripts/sb/` 從哪裡載入；子行程的 `sys.path`；有沒有一軌因為載入順序、同名覆蓋而靜靜少跑（印軌數不夠，要逐軌確認跑到了）。快取預設真的關著嗎；開快取時鍵有沒有漏相依（繼承鏈的檔、Python 與依賴版本、內容檔）。`undef_scan` 擴到 `scripts/`、`tests/` 之後有沒有把真問題當白名單。"),
    dict(key="delegates", text="**掛上去的函式跟委派要等價**（企劃者 11/07 答：搬）。第 72 批把一行委派換成表。逐個比開工那一筆的委派與 head 掛上去的函式：參數名與預設值（有沒有測試或包用關鍵字叫；`inspect.signature` 比一遍）；`self` 傳到哪；bound method 與 `Game.x` 當類別屬性讀（`patch.object(Game, 'x')`、`monkeypatch.setattr`、`getattr(Game, name)`、`hasattr`、`dir(Game)`、`callable` 的判斷有沒有因此變）；`@_not_while_preparing` 那 6 個有沒有保住；`staticmethod`、`classmethod` 與不傳 self 的 9 個；`same_behavior`、`bot_policy`、`server.py` 用字串叫的（`getattr(game, name)`、選項表）；pydantic、pickle、deepcopy 有沒有碰到 Game 上的屬性；import 先後（`sys.modules` 順序、`core.cards.ACTIONS` 登記順序）在 `server.py`、`run_bots.py`、單獨 `import tianxia.engine` 三種入口各印一次比。第 73 批的名單新舊逐張相等；第 74 批拿掉的服務名字真的沒人用（字串拼的 `ctx.<名字>` 也算）。"),
    dict(key="save", text="**存檔一個位元組都不能變**。第 76 批把 QUIET 清單改標到 `Field`。用真的 `PlayerState`、`WorldState`、`SharedWorldState`：開工那一筆與 head 各建預設物件、各載幾份舊存檔的 JSON（`tests/fixtures` 或自己造，含缺欄位的舊存檔），`model_dump_json`、`QUIET_DEFAULTS` 算出來的集合、鍵順序、`_drop_new_defaults` 的結果逐一比；有沒有哪個欄位因為多了 `json_schema_extra` 改變序列化或 schema。`ALLOW_FIXED`、`ALLOW_FAMILIES`、`REVEAL_KEYS` 集合相等。第 78 批：沒設 `TIANXIA_PUBLIC_URL`（這台開發、測試）行為一個位元組都不變；`/`、`/sw.js`、`index.html` 絕不長快取；雜湊怎麼算的，跟 `?v=` 產生的地方是同一支函式嗎。"),
]
WEB_D = "**這一波 `web/` 沒動（第 78 批只動 `server.py` 的快取標頭），上面「照 tianxia-qa 並排截圖」不用做。這一關是第 77 批網頁比對工具的第一次全量，E 波切畫面要靠它。** 工具在 head 的 `scripts/webqa/`（先讀 `gate.py`、`selftest.py` 檔頭與 `C:\\Users\\ray61\\AppData\\Local\\Temp\\claude\\81800b313c89d0f8\\ade93b70-b3b7-42db-a8af-21f7a7cbdb16\\scratchpad\\wf\\built-D-notes.txt` 第 77 批那一節；解一份 head 來跑）。都不花 token：用 `Start-Process` 分離啟動、輸出導到檔，`docs/superpowers/pm-workflows/wait_file.py <檔> 570` 等，**不要前景跑**。不帶 `--ports`（預設 `--jobs 2`，各挑空埠，拒絕 7861）。\n1. `gate.py --base <base> --head <head> --out <暫存>\\\\web1 --write-must-reach`（fast）。量實際分鐘數，寫進回報。\n2. 看 `summary.json`、`report.txt`。結束碼 0 就把產生的 `must_reach.txt` 存到 `<暫存>\\\\web1\\\\must_reach.txt`，回報寫路徑（PM 提交）。結束碼 1、2：逐列分成①工具誤報（第 77 批點名第一候選：main 的天下形勢排在史官後面，`.xingshi_mark` 只有一邊寫好；再出現就把 `tale_done` 搬進 common）②這一波真的改了（第 72、76、78 批）。兩種都寫進 `diffs`、`same=false`，下一關會修。\n3. `selftest.py --sha <head> --out <暫存>\\\\self`（base 對 base 綠、跑兩次 fingerprint 全同、兩個正控制都紅；約 8 分一趟四趟，第 77 批只跑過 `--only accounts,smoke`）。\n4. 時間還夠才做：第 77 批第 6 項（`newbie_c05`、`pe_c07` 重現，指令在那一節）。\n**整關不超過 3 小時**，到了就交，沒走到的寫清楚。"
WAVES["D"] = dict(
    round2=True,
    extra_lenses=EXTRA_LENSES_D,
    lines=[
        dict(name="驗證工具", batches=[b70, b71]),
        dict(name="委派與守門", batches=[b72, b73, b74, b75]),
        dict(name="資料清單", batches=[b76]),
        dict(name="網頁工具", batches=[b77]),
        dict(name="版本快取", batches=[b78]),
    ],
    merge_port=8295, fix_port=8296,
    web_check=dict(ports="8297、8298", steps=WEB_D),
)


R2E_NOTE = [
    "- **D 波之後的新位置（以現行程式為準）**：一行委派進 `tianxia/features/<包>/game_api.py` 的 `TABLE`；搬進 `tianxia/core/` 的服務照 event_check 前例在 `Game` 留一行委派，表只管包。邊界名單在 `tests/core/boundary_tables.py`；服務清單在 `tianxia/core/services_list.md`，`CROSS_PACKAGE_CALLS`、`SHELL_FOREIGN` 紅了照訊息補列或拿掉。調校數字 `tianxia/core/tuning/<包>.py`。新存檔欄位要空的不寫鍵用 `Field(<預設>, json_schema_extra=QUIET)`。情境在 `scripts/sb/tracks/<軌>.py`，檔尾 `register_track`；`scripts/same_behavior.py` 只是入口。",
    "- **這一波 8 條線同時開工（企劃者 11/07「加快分拆，不要卡著」，PM 重排）**：好幾條線都動 `tianxia/engine.py`（各搬各的段）、`tests/core/boundary_tables.py`、`tianxia/core/features.py`、`tianxia/core/registry.py`。**只動你要搬的那幾段**，不順手整理、不重排、不改別人的 import 行；拿掉的 import 只拿你造成沒人用的。總表那一節寫的「依賴」「同線」跟這張派工單不一樣時，照這張派工單。",
    "- 看到別批的問題、工具的誤報，寫進 leftovers，不修。",
]
CORE_FILE = "- **開核心服務檔（第 79、80、81 批共通）**：照實調 `scripts/test_for.py` 的 `CORE_SERVICES` 的底，補一條用真檔的測試；服務檔經 `ctx._x` 互叫的不會往上算（`_core_refs` 只看 `ast.Name`）。被 patch 的方法互叫走 `ctx._x`，其餘直接叫（那一節的坑）。"
WEBQA_NAMES = "- `scripts/webqa/serve.py` 的 `PATCH_NAMES` 讀 `server` 模組的名字：你搬走的名字 `server` 模組要還認得，`tests/web/test_webqa.py` 要綠。"


def r2e(n, title, pkg, dev, ports, body, model=None):
    return r2(n, title, pkg, dev, ports, body + R2E_NOTE, model=model)


def b79():
    return r2e(79, "單打服務收進 `core/combat.py`", "core_combat", "dev/combat", "8299", [
        "- 範圍照那一節。`test_explain2.py` 現在在 `tianxia/features/guide/tests/`。`_squad_encounter`：那一節要收、第 72 批留的話說照舊留 `GAME_DIRECT`，以現行程式為準選保守的，擲骰順序不動，寫進 decided。",
        CORE_FILE,
    ])


def b80():
    return r2e(80, "推大勢與回體丹（`core/pushing.py`、`core/pills.py`）", "core_pushing", "dev/pushing", "8300", [
        "- 範圍照那一節，從第 79 批的結果開。`push_trend` 的 int 與 float 細節不動。",
        CORE_FILE,
    ])


def b81():
    return r2e(81, "畫面搬出 engine（`core/status_view.py`、`core/page_view.py`）", "core_views", "dev/views", "8301", [
        "- 範圍照那一節。**自己一條線，不接第 79、80 批（PM 定）**：它們搬的方法在 `Game` 上名字還在，你照舊 `self.x` 叫。`status_data` 的閉包整段不拆。",
        "- `skillview.stat_uses`、`STAT_CHECK_NOTE`、`practice_hint` 照搬進 `core/status_view.py`。第 88 批在別條線切 skillview，合併時接，你不動。`shop_view` 的分派這批照搬，第 93 批下一波才改。",
        CORE_FILE,
    ])


def b83():
    return r2e(83, "殼的殘留與 import", "shell", "dev/shell-rest", "8302", [
        "- 範圍照那一節。第 82 批砍了（PM 判斷：付 14 格表換 5 筆，不划算），不用對它。`cards.ACTIONS` 的 sorted 跟 `test_social.py:552` 同一串要印出來對。第 69 批那條補註要收回：句子放 docs。",
        WEBQA_NAMES,
    ])


def b90():
    return r2e(90, "管理者開包 `features/admin`", "admin", "dev/admin", "8303", [
        "- 範圍照那一節，從第 83 批的結果開。`/` 回的 HTML 與 script 順序不變：`web/admin.js` 只改由這包宣告，內容不動（第 85 批在別條線把 admin 的 submit 分支搬進它，合併時接）。**`/api/admin*` 與 `/admin` 每一條的權限檢查一個字都不動**，測試各打一條「不是管理者」要被擋。",
        "- `switchboard` 軌補 `/api/admin/accounts`、`reset_password`（那一節寫現在 0 處打到）；`schedule`、`jump_next`、`clear_lock`、`set_trend` 開工先查有沒有打到，沒打到補情境。手冊 3.1 要補的認定句子放 docs。",
        WEBQA_NAMES,
    ])


def b84():
    return r2e(84, "點擊分派接手（`registerClicks`）", "shell_web", "dev/clicks", "8304", [
        WEB_RULE,
        "- 範圍照那一節。case 行逐字不動（縮排 8 格），查表一律 `return await`。`web/` 的檔連註解都不准寫假人那幾個字。facade、map 軌的 `FACADE_SHELL_LINES` 照那一節放行。第 86 批在別條線切 style.css，實切的 `test_shell_web` 那 1 條是這批解的。looks 的 24 個 case 先進 `mall.js`，第 94 批同線接著搬。",
    ])


def b85():
    return r2e(85, "表單與 change 分派（`registerForms`）", "shell_web", "dev/forms", "8305", [
        WEB_RULE,
        "- 範圍照那一節，從第 84 批的結果開。殼留登入、建角、改密碼、隨口應對，keydown 留殼。`web/battle.js` 的 `battleInner` 舊註解與恆真的 `typeof bpOn` 守衛這批清（第十節）。admin 的 41 行進 `web/admin.js`；第 90 批在別條線只改這個檔由誰宣告，不動內容。",
    ])


def b94():
    return r2e(94, "`mall.js` 切出 `looks.js`", "looks", "dev/looks-js", "8306", [
        WEB_RULE,
        "- 範圍照那一節，從第 85 批的結果開，第 84 批進 `mall.js` 的 24 個 case 跟著走。頂層 const 載入時有沒有互讀先量。**`mall.css` 的 look 段這批不切（PM 定：第 86 批同波在動 CSS 先後）**，放 leftovers。",
    ])


def b86():
    return r2e(86, "`style.css` 切 `map.css`、`shop.css`", "map", "dev/css-cut", "8307", [
        WEB_RULE,
        "- 範圍照那一節。link **放 `style.css` 正後面**；多的 `}`（FB-9441）與作廢那條一起走、不修。先修 `scripts/css_order_check.py`（所有樣式照載入順序接成合成 base 再比）。加一條測試：`style.css` 不准再出現切走的那幾個前綴。",
        "- `test_shell_web` 那 1 條紅是第 84 批解的，別條線在做，你不修，在 base 上確認、寫進 decided。語料重播（`scripts/webqa`）波末比對一次跑，你只跑 `css_order_check.py` 與讀這些 css 的測試。",
    ])


def b87():
    return r2e(87, "收口一：事件三支、合成、`server_bots`", "core_shared", "dev/old-shared", "8308", [
        "- 範圍照那一節。邊界名單開工逐行分。動到共用層登記寫明理由。",
    ])


def b88():
    return r2e(88, "skillview 切開", "core_shared", "dev/skillview", "8309", [
        "- 範圍照那一節，從第 87 批的結果開。第 81 批在別條線把 `skillview.*` 搬進 `core/status_view.py`：你改 engine 上還看得到的；`core/status_view.py` 那幾個合併時照新位置接，寫進 leftovers。第 82 批砍了，`features/*/__init__.py` 不用對它。",
    ])


def b89():
    return r2e(89, "假人一：包讀的搬進包", "core_bots", "dev/bots-1", "8310", [
        "- 範圍照那一節。**自己一條線，不接第 88 批（PM 定）**：開工先確認搬的東西沒有用到第 88 批新開的位置，用到的照舊讀 `skillview`、寫進 leftovers。`_TURN`、`_turn_cached` 不能變兩份狀態。假人的選擇逐位元組不變，任何畫面、輸出不能透露誰是假人。",
    ])


def b101():
    return r2e(101, "假人二：每包的按法搬進 `bots.py`", "core_bots", "dev/bots-2", "8311", [
        "- 範圍照那一節，從第 89 批的結果開。分數相同時的先後、亂數抽幾次都算行為。",
    ])


def b96():
    return r2e(96, "內容驗證：共用層那一類回各自模組", "core_content", "dev/content-check-1", "8312", [
        "- 範圍照那一節。一律函式內 import，validate 原位呼叫。一次性比對各類內容改壞時 `ContentError` 全文（含先後）一樣，寫一支暫存腳本。",
    ])


def b100():
    return r2e(100, "內容驗證：單包的進包", "core_content", "dev/content-check-2", "8313", [
        "- 範圍照那一節，從第 96 批的結果開。**`check_shop_lines` 這批不搬（PM 定）**：它讀 `shopview.SITUATIONS`，第 93 批下一波才切，放 leftovers 給第 93 批。`ContentError` 全文比對照第 96 批那支。另跑 `tests/core/test_content.py`、`tests/core/test_content_packs.py`。",
    ])


EXTRA_LENSES_E = [
    dict(key="clicks", text="**按鈕一顆都不能掉，也不能兩包都認**。第 84、85、94 批把 `app.js` 的 switch、submit、change 分進包的 js。把 base 的每個 case、每條 else-if 與 head 各包的 `<包>Click`、`registerClicks`、`registerForms` 逐一對，寫腳本不要用看的：case 行逐字、有沒有漏、同一 act 兩包認；查表一律 `return await`（`app.js` 靠 try/catch 吞 `api()` 的 throw）；fallthrough 的 case 有沒有被拆開；else-if 鏈改寫後條件的先後。頂層 TDZ：每支檔頂層讀的識別字對到定義的檔與載入順序，`WEB_ORDER`、`APP_FILES`、`web_scripts()` 一致；`looks.js` 載入當下的頂層 const。`web/` 的檔連註解都不准寫假人那幾個字。"),
    dict(key="css", text="**CSS 先後就是行為**。第 86 批把 `style.css` 兩大段切進 `map.css`、`shop.css`，link 放 `style.css` 正後面。用 `scripts/css_order_check.py` 對 base 跑；`NOT_EVERYWHERE` 每一組的理由逐條讀，讀程式確認真的打不到；js 組字串產生的 class（資料表組出來的）它抓不到，你另外列，對照搬去哪、先後有沒有反轉；多的 `}`（FB-9441，吃掉 `.shop-layer.shop-tavern`）切出去之後效果跟 base 一樣嗎；`mall.css` 排在哪；`style.css` 不准再出現切走前綴的那條測試真的會紅嗎（改一行試）；`sw.js` 快取清單與 `?v=`、長快取的雜湊有沒有涵蓋新檔。"),
    dict(key="core", text="**搬進核心的行為不能變，測試換的東西還換得到**。第 79、80、81 批把單打、推大勢、回體丹、狀態列與頁面搬進 `core/`。逐個比 base 與 head：被 patch 的方法（`git grep` 測試與 `scripts/sb`）互叫時真的走 `ctx._x` 嗎，經直接呼叫的是不是測試沒 patch；`sortie.on` 換 `territory.on` 的等價證明；`PROLOGUE_FIGHT` 的 re-export 是同一物件；`_battle_rewards`、`_squad_encounter` 擲骰次數與順序；`push_trend` 的 int 與 float；`status_data` 的閉包有沒有抓到舊值、鍵的先後（`/api/main` 逐位元組）；engine re-export 的 `FIGHT_GONE_LINES`、`LOW_HP_RATIO`、`REFILL_*`、`PILL_DAY_FULL`、`_cn_count` 都在；核心有沒有 import 包；兩條線都動 engine.py 合起來有沒有掉方法或重複（`Game` 的名字集合 base 對 head 比一次）。"),
    dict(key="admin", text="**管理者的門不能少一道**。第 90 批把管理者工具與 `/api/admin*`、`/admin`、`reset_password` 搬進新包 `features/admin`。列出 base 與 head 每一條路由，逐條對權限檢查（沒登入、登入了不是管理者、休季時 `paused_ok`）的語句與先後，用 TestClient 實打「不是管理者」每一條都要被擋（行程內，不開埠）；`FEATURE_ADMIN_ACTIONS` 與 `ADMIN_OWNERS` 每一格；`admin_choices` 的鍵順序（`STATUS_ORDER[\"admin\"]`）；`is_admin` 的來源沒變；第 83 批 `cards.ACTIONS` 字典順序變了之後，真的只有 sorted 與 `.get` 在讀嗎。"),
    dict(key="models", text="**假人與內容不能變**。第 89、101 批：`_TURN`、`_turn_cached` 只有一份狀態（`id()` 比一次）；同一個局面的 `score`、`pick`、同分先後、亂數抽幾次在 base 與 head 一樣；假人四支定成殼之後包有沒有 import。第 96、100 批：造幾種壞內容，`ContentError` 全文與先後在 base 與 head 一樣，`load_content` 在 season21、week7、不帶設定各載一次 `model_dump_json` 比雜湊；函式內 import 有沒有環。第 87、88 批：re-export 是同一物件（`is` 比），`patch.object(create, …)`、`patch.object(skillview, …)` 打得到；`seal.on` 改讀 `seal_base` 等價；共用層登記 `SHARED` 有沒有多放行包。"),
]
WEB_E = "**這一波切了 `app.js` 的分派、`style.css`、`mall.js`，用 head 的 `scripts/webqa/`，上面「照 tianxia-qa 並排截圖」不用做。** 都不花 token：用 `Start-Process` 分離啟動、輸出導到檔，`docs/superpowers/pm-workflows/wait_file.py <檔> 570` 等，**不要前景跑**。不帶 `--ports`（各挑空埠，拒絕 7861）。\n1. `gate.py --base <base> --head <head> --out <暫存>\\\\web1 --jobs 4 --keep-corpus`（fast；改到 css 會自動跑重播）。量分鐘數，寫進回報。\n2. 看 `summary.json`、`report.txt`。結束碼 0：same=true。結束碼 1：逐列分成①工具誤報（寫進 report，不算 diffs）②這一波真的改了（寫進 diffs，same=false）。結束碼 2：工具壞了，same=true、report 開頭寫「比對沒跑完」與原因。\n3. 印 main 語料含 `#map-host` 的快照數（第 86 批要這個數；0 就寫明輿圖那一半沒有語料證據）。\n4. 工具走不到的實機各走一次，主控台 0 錯誤、網路沒有 4xx／5xx：管理頁重設密碼、酒肆四張表單、形象與絕招頁（第 85、94 批）。\n**不修工具、不修程式、不跑 selftest，整關不超過 75 分鐘**，到了就交，沒走到的寫清楚。"
WAVES["E"] = dict(
    round2=True,
    extra_lenses=EXTRA_LENSES_E,
    lines=[
        dict(name="戰鬥與推大勢", batches=[b79, b80]),
        dict(name="畫面搬出", batches=[b81]),
        dict(name="殼與管理者", batches=[b83, b90]),
        dict(name="點擊分派", batches=[b84, b85, b94]),
        dict(name="樣式", batches=[b86]),
        dict(name="舊模組", batches=[b87, b88]),
        dict(name="假人", batches=[b89, b101]),
        dict(name="內容驗證", batches=[b96, b100]),
    ],
    merge_port=8314, fix_port=8315,
    web_check=dict(ports="8316、8317", steps=WEB_E),
)


R2F_NOTE = [
    R2E_NOTE[0],
    "- **E 波之後的新位置（以現行程式為準）**：單打 `core/combat.py`、推大勢 `core/pushing.py`、回體丹 `core/pills.py`、狀態列與頁面 `core/status_view.py`、`core/page_view.py`，`Game` 留一行委派。內容檢查：共用層的在各模組，單包的在 `features/<包>/checks.py`，位置固定的走 `Feature.content_slots()`、`features.check_at`，工具在 `core/content_base.py`。假人：共用的在 `bot_base`，各包在 `features/<包>/bots.py`，殼四支包不准 import。網頁：點擊、表單、change 用 `registerClicks`、`registerForms`、`registerChanges` 寫在包的 js；店面樣式 `web/shop.css`、輿圖 `web/map.css`。管理者 `features/admin`。`skillview` 是給測試用的殼（`TEST_ONLY_SHELLS`），產品碼不准 import，新位置 `art_cards`、`art_view`、`forge_view`、`leaderboard`。",
    "- **這一波好幾條線同時開工（企劃者 11/07「加快分拆，不要卡著」）**：好幾條線都動 `tianxia/engine.py`（各搬各的段）、`tests/core/boundary_tables.py`、`tianxia/core/features.py`、`tianxia/core/registry.py`。**只動你要搬的那幾段**，不順手整理、不重排、不改別人的 import 行；拿掉的 import 只拿你造成沒人用的。總表那一節寫的「依賴」「同線」跟這張派工單不一樣時，照這張派工單。",
    R2E_NOTE[2],
]


def r2f(n, title, pkg, dev, ports, body, model=None):
    return r2(n, title, pkg, dev, ports, body + R2F_NOTE, model=model)


def b91():
    return r2f(91, "場景卡收接縫", "core_scene", "dev/scene", "8318", [
        "- 範圍照那一節。**PM 開波重量，還熱，做**：`_own_scene_text` 兩週改 11 次（雲端與 Joy 3 次）、`scene_art` 3（2）、`location_text` 2（1）。**自己一條線，不接第 92 批（PM 定）**。",
        "- `scene_art` 靠 `_own_scene_text() != location_text()` 判斷，排錯整張圖不見：開工寫一支暫存比對，把 if 鏈每一格都擺出來，比 `scene_text`、`scene_art` 舊新一樣，第二段收尾再比一次。投靠、叛投、求見同掛的髒存檔逐支照舊。`SCENE_ORDER` 照 `core/features.py` 的 `MENU_ORDER`、`STATUS_ORDER` 寫法，新開的掛鉤寫進回報，不用先問。",
        CORE_FILE,
    ])


def b92():
    return r2f(92, "choose 收尾與寄放欄位", "core_choose", "dev/choose-end", "8319", [
        "- 範圍照那一節。**PM 開波重量，還熱，做**：`choose` 兩週改 43 次（雲端與 Joy 7 次）、`_everyday_options` 28（5）、`__init__` 15（6）、`_action_title` 32（4）。**自己一條線，不接第 91 批（PM 定）**。",
        "- `Outcome` 多欄不准改現有欄位的預設與先後（各包都在用）。句子順序就是行為；挑擂那支不寫 `_log`；`Feature.scratch()` 要在 `_drop_stale_references` 之前跑完，`_kin`、`_admin_target`、`_load_kin` 開的 `Game` 也要走到。第 99 批總表點名的 `_action_title` 字面放 leftovers 看第 99 批要不要接，這批不動。",
    ])


def b98():
    return r2f(98, "engine 對包的 import 清到零", "core_imports", "dev/engine-imports", "8320", [
        "- 範圍照那一節，E 波留的都接進來（下面 leftovers）。`_squad_encounter` 這批收進 `core/combat.py`：`sortie.on` 換 `territory.on` 的等價寫出證明（`CLAUDE.md` 寫三個同一件事，對程式），`PROLOGUE_FIGHT` 字搬核心，engine re-export 同一物件，7 對 `GAME_DELEGATE_CALLERS`、`GAME_DIRECT`、`GAME_IMPORTS` 一起清。擲骰順序不動。",
        "- **engine 頂端沒人用的 import**（E 波之後約 73 個，開工重數）：拿掉 `from . import` 裡的會改載入順序，每拿一組就比 `sys.modules` 先後；動到先後的查 import 當下有沒有副作用，沒有才拿，寫進 decided（第 90 批前例）。`encounter` 有 2 處 patch，先改。`wins_rules` 為了載入順序留著（第 80 批），查過再定。邊界把 `GAME_IMPORTS`、`GAME_DIRECT` 鎖成空。第 91、92 批同波別條線，它們造成沒人用的不算你的。",
        "- **第 102 批靠這一批**：核心不 import 包要變成真的。",
        CORE_FILE,
    ])


def b99():
    return r2f(99, "有主的零碎歸位與 engine 收尾", "core_rest", "dev/engine-rest", "8321", [
        "- 範圍照那一節，從第 98 批的結果開。「engine 讀 skillview 改讀 art_cards」第 88 批做掉了，開工確認。`_deliver_away` 在 sync 最後一句、`_renown_after` 在 `_log` 第一句：只換本體不換呼叫位置。墓碑與沒人讀的 import 分開提交好退。`_deliver_echoes` 的路徑寫死在 `test_explain2`（現在在 `tianxia/features/guide/tests/`）。第 91、92 批同波別條線：`scene_*`、`choose`、`_everyday_options` 附近的墓碑不動。",
    ])


def b93():
    return r2f(93, "shopview 切五家", "shop", "dev/shops", "8322", [
        "- 範圍照那一節，開工照現行程式重量。**PM 定寫法**：`Feature.shop_view(self, ctx, shop) -> dict | None`，一間店只有一包認（店 id → 包：`smith` smithy、`arena` bout、`donate`、`dadian` outlets、`board` bounties、`market` gear、`tavern` tavern，開工對程式，對不上以程式為準）。`core/page_view.shop_view` 改問包（第 81 批把分派搬到那裡），`_shop_open` 的先後不動。契約加一條「一間店只有一包認」。店共用進 `core/shop_base.py`。`shopview.py` 改給測試用的殼，進 `TEST_ONLY_SHELLS`，同 skillview。",
        "- **`check_shop_lines` 這批搬（第 100 批留的）**：它是跨店的，跟 `SITUATIONS` 一起進 `core/shop_base.py`，validate 原位函式內 import、一句不動，**不開新的 `CONTENT_SLOTS` 格（PM 定）**。`ContentError` 全文比對：造幾種壞的 `shop_lines`，舊新一樣。`test_feature_boundaries.py` 的 `outside_imports` 例子原本是 shopview，要換（第 87 批留的）。",
    ])


def b95():
    return r2f(95, "test_for：殼的 js 照函式挑", "tools", "dev/test-for-js", "8323", [
        "- 範圍照那一節，第 84、85、94 批之後 `app.js` 剩的少了很多，**開工重量**，只剩幾個 case 不值得就把結論寫進 decided、只做第二條。",
        "- **第二條（第 96 批留的）**：改共用層模組裡的 `check_*`、`validate_*` 時也挑 `tests/core/test_content.py`，模組說明裡那句「要另外跑」拿掉（14 個模組，只動那一句）。`IMPORT_CAP` 不准動。",
    ])


def b97():
    return r2f(97, "共用層瘦身", "core_shared", "dev/shared-slim", "8324", [
        "- 範圍照那一節。總表附錄甲裁定 siege 不進包，這批改了要寫一筆認定：句子放 docs。共用層不准 re-export 包，要改 import。第 96 批把 `check_siege_templates` 搬進 `siege.py` 了，開工重量。",
    ])


def b104():
    return r2f(104, "網頁的零碎歸位", "shell_web", "dev/web-rest", "8325", [
        WEB_RULE,
        "- E 波留的、批號待 PM 分配的，這批收：① `web/mall.css` 的 look 段（最多約 125 行）切進 `web/looks.css`，`LooksFeature.web` 宣告，`scripts/css_order_check.py` 結束碼 0、先後反了又可能打架 0 對；② `sayLine` 進 `web/companions.js`、`gatherSay` 進 `web/explore.js`（第 85 批把分支搬走、函式留殼），有沒有人叫先量，沒人叫也照搬、寫進 leftovers；③ 恆真的 `typeof bpOn`（`app.js` 約 1564、`main.js` 579、1021）與 `web/admin.js` 的 `typeof adTrendNow`：只切 `main.js` 的測試真的有的話留著，寫進 decided；④ 舊註解 `web/cultivation.js:283,286`（寫 mall.js）、`web/companions.js:84`、`web/zhuan.js:58`（寫 server.…）、`web/app.js:903` 一帶寫 `style.css` 的：照第 85 批做法在 `FACADE_SHELL_LINES` 放行整行字面。",
        "- 這批不動分派、不改名。`web/` 的檔連註解都不准寫假人那幾個字。",
    ])


EXTRA_LENSES_F = [
    dict(key="seams", text="**新接縫不能掉格，也不能換先後**。第 91、92 批開了 `SCENE_ORDER`、`MENU_ORDER[\"stale\"]`、`Outcome` 新欄、`Feature.scratch()`。逐格比 base 與 head：`scene_text`、`scene_art`（`_own_scene_text() != location_text()` 那一句）、`choose` 前段 5 支被拒的先後與句子、後段 quiet、merge、fold；`_everyday_options` 事件段；`__init__` 的旗標每一個都還在、初值一樣，`_kin`、`_admin_target`、`_load_kin` 開的 `Game` 也有；`Outcome` 舊欄位預設沒變。寫腳本，不要用看的。假的包登記一格，真的問得到嗎。"),
    dict(key="shop", text="**五家店一間都不能變**。第 93 批。`/api/main` 的 `shop` 在每間店每種情況舊新逐位元組比（行程內，不開埠）；一間店只有一包認；`core/shop_base` 沒有 import 包；`shopview` 殼的名字一個不少、都是同一物件（`is`）；`check_shop_lines` 造壞內容 `ContentError` 全文與先後一樣；`check_shop_lines` 的呼叫位置沒動。`TEST_ONLY_SHELLS` 測試真的會紅嗎（改一行試）。"),
    dict(key="imports", text="**核心不 import 包要變成真的，載入先後不能出事**。第 98、99 批。`GAME_IMPORTS`、`GAME_DIRECT` 真的空了；`import tianxia.engine` 當下 `sys.modules` 先後 base 對 head 列差異，每個挪動的模組查 import 當下有沒有副作用（模組層登記、`aliases()`、`register_*`）；`_squad_encounter` 擲骰次數與順序、`sortie.on` 換 `territory.on` 的等價、`PROLOGUE_FIGHT` 同一物件；`Game` 的名字集合 base 對 head（方法與 `game_api` 表）；`test_the_engine_the_bot_program_and_the_bots_load_no_web_framework`；第 99 批搬的本體呼叫位置（`_deliver_away` 在 sync 最後一句、`_renown_after` 在 `_log` 第一句）沒動。"),
]
WEB_F = "**這一波切了 `shopview`、`mall.css`，動了幾支 js 的零碎，用 head 的 `scripts/webqa/`，上面「照 tianxia-qa 並排截圖」不用做。** 都不花 token：用 `Start-Process` 分離啟動、輸出導到檔，`docs/superpowers/pm-workflows/wait_file.py <檔> 570` 等，**不要前景跑**。不帶 `--ports`（各挑空埠，拒絕 7861）。\n1. `gate.py --base <base> --head <head> --out <暫存>\\\\web1 --jobs 4`（fast；改到 css 會自動跑重播）。量分鐘數，寫進回報。\n2. 看 `summary.json`、`report.txt`。結束碼 0：same=true。結束碼 1：逐列分成①工具誤報（寫進 report，不算 diffs）②這一波真的改了（寫進 diffs，same=false）。結束碼 2：工具壞了，same=true、report 開頭寫「比對沒跑完」與原因。\n3. 工具走不到的實機各走一次，主控台 0 錯誤、網路沒有 4xx／5xx：形象頁（第 104 批切樣式）、鐵匠鋪、馬市、懸賞榜、打點、軍需帳、擂台。\n**不修工具、不修程式、不跑 selftest，整關不超過 75 分鐘**，到了就交，沒走到的寫清楚。"
WAVES["F"] = dict(
    round2=True,
    extra_lenses=EXTRA_LENSES_F,
    lines=[
        dict(name="場景卡", batches=[b91]),
        dict(name="choose 收尾", batches=[b92]),
        dict(name="引擎收尾", batches=[b98, b99]),
        dict(name="店面", batches=[b93]),
        dict(name="挑測試", batches=[b95]),
        dict(name="共用層", batches=[b97]),
        dict(name="網頁零碎", batches=[b104]),
    ],
    merge_port=8326, fix_port=8327,
    web_check=dict(ports="8328、8329", steps=WEB_F),
)


def b102():
    return r2f(102, "過渡收口", "core_shared", "dev/transit-end", "8330", [
        "- 範圍照那一節。**`CLAUDE.md` 這批不碰**：要改的句子放 docs，PM 改、先給企劃者看。`new_feature.py` 範本與手冊 G11 補新鈕用 `registerClicks`、CSS link 的位置（第 84、86 批留的）這批做。故意寫一行違規要紅，每一條硬規矩都試一次、印出訊息。",
        "- 第 103 批會把殼收掉，`SHARED_LATER` 之類這批拿掉時，三個殼（`howto`、`skillview`、`shopview`）照 `TEST_ONLY_SHELLS` 走，不開別的白名單。",
        "- **E 波審查留的守門，這批一起做（PM 定）**：①共用層 `bot_base` 准拿 `Game`，第 89 批開的路（`bot_base._sortie_win` 叫 `game._sortie_foes`）照認，手冊第十五節寫落地認定；`tests/core/boundary_tables.py` 加一張 `bot_base` 准碰的 `game.xxx` 名單，邊界測試掃 `tianxia/bot_base.py`，不在名單就紅。其他共用層不准拿 `Game`。②`test_nobody_calls_an_event_subscriber_outside_the_publish_points` 的掃描範圍補上核心服務檔（`core/`），搬進核心的函式也要守；掃得到才算（先寫一行違規證明會紅）。③`BOT_SHELL_PENDING` 已是空集合，連名字與用到它的測試分支一起拿掉。",
        "- **F 波留的（PM 定）**：`engine.py` 的 `TYPE_CHECKING` 裡的包名（`companion_agent`、`parley`、`xingshi`）也清，註記寫字串或寬一點的型別，核心不 import 包不留這個例外；`from .rules import jianfa` 重複的那一行拿掉（量過先後不變）；`from . import wins`、`story_base`、`outcome_rules` 三行是為了 `run_bots` 的載入先後留的，理由註解寫實（『第 98 批清這一區時一起看』已過時）。",
    ])


def b103():
    return r2f(103, "別名與測試殼收掉", "core_shared", "dev/alias-end", "8331", [
        "- 範圍照那一節，從第 102 批的結果開，數字開工全部重量。**PM 11/07 量過開著的分支**：別名 67 個，新加的行用到舊名的只有擱著的 `feature/map-view`（落後 `develop` 1,838 筆，本來就要重做），Joy 那條 11/07 的 `claude/project-thread-li7stm-*` 沒用到，所以可以做。之後舊名的 PR 合進來會 `ImportError`，是認了的。用腳本改、語法樹驗（除 import 與字串全一樣），`pytest --collect-only` 條目一樣。`same_behavior` 的 `MUTATIONS` 舊名跟著改。`CLAUDE.md`、`docs/guide` 的舊名句子放 docs，文件輪做。",
    ])


WEB_G = "**這一波沒動 `web/`，但收了 70 個舊模組、路由與 `server.py` 的 import 都動了；函式裡才 import 的舊名要走到才會炸，這也是第二輪最後一次走全程。用 head 的 `scripts/webqa/`，上面「照 tianxia-qa 並排截圖」不用做。** 都不花 token：用 `Start-Process` 分離啟動、輸出導到檔，`docs/superpowers/pm-workflows/wait_file.py <檔> 570` 等，**不要前景跑**。不帶 `--ports`（各挑空埠，拒絕 7861）。\n1. `gate.py --base <base> --head <head> --out <暫存>\\\\web1 --jobs 4`（fast）。量分鐘數，寫進回報。\n2. 看 `summary.json`、`report.txt`。結束碼 0：same=true。結束碼 1：逐列分成①工具誤報（寫進 report，不算 diffs）②這一波真的改了（寫進 diffs，same=false）。結束碼 2：工具壞了，same=true、report 開頭寫「比對沒跑完」與原因。\n3. 工具走不到的實機各走一次，主控台 0 錯誤、網路沒有 4xx／5xx、伺服器的 log 沒有 `ImportError`、`ModuleNotFoundError`、`AttributeError`：第 102 批改過的路由（單挑的文字、擂台開賽與圍觀、奪璽單挑、戰記）、手機通知的登記頁；管理頁各分頁。\n4. F 波沒走到的兩樣各試一次，叫不出來不要硬試，寫清楚：跟人物對話送出一句（`sayLine`）、採集喊話（`gatherSay`）。\n5. 收之前 `grep` 兩台伺服器的 log 有沒有 `ImportError`、`ModuleNotFoundError`，有就是 blocker。\n**不修工具、不修程式、不跑 selftest，整關不超過 75 分鐘**，到了就交，沒走到的寫清楚。"


WAVES["G"] = dict(
    round2=True,
    extra_lenses=[
        dict(key="aliases", text="**舊名全部收掉之後什麼都不能壞**。第 102、103 批。`git grep` 每個舊名（別名表 base 上列出來）在 `tianxia/`、`tests/`、`scripts/`、`server.py`、`run_bots.py` 還有誰讀；`importlib` 把 `tianxia` 底下每個模組各開新行程 import 一次（`features/looks/cutting` 要 scipy，這台 venv 沒裝，除外）；`patch.object`、字串路徑（`monkeypatch.setattr(\"tianxia.x.y\")`）真的打到本體；`scripts/` 逐支語法檢查與 `--help`；硬規矩故意違規真的紅。主機端工具（`scripts/warm_keeper.py`、`scripts/monitor.py`、`scripts/set_password.py`、`scripts/nightly.ps1`）與根目錄的 `server_push.py`、`console.py`、`llm_queue.py`、`run_studio.py`、`run_bots.py` 照舊跑得動；**函式裡才 import 的**舊名用語法樹掃，不靠 grep 的字串樣子。`scripts/new_feature.py` 生一包出來，邊界與契約照舊綠（生在暫存複本，不留）。"),
    ],
    lines=[dict(name="收口", batches=[b102, b103])],
    merge_port=8332, fix_port=8333,
    web_check=dict(ports="8334、8335", steps=WEB_G),
)


H_PLAN = "docs/superpowers/plans/2026-11-08-架構收尾.md"
H_NOTE = [
    "- **架構收尾這一波**：範圍照 `" + H_PLAN + "` 這一批那一節整節（只讀第一段與那一節；第二輪總表不適用，第二節的裁決也不適用）。行號量在 `3e5f69b22`，**開工照現行程式重量，對不上以程式為準**，寫進 decided。上面「計畫不超過 120 行」照舊，計畫寫在 `plan` 那個路徑。",
    "- **各包 README、`docs/guide`、手冊、`CLAUDE.md` 線上不動**：要寫的句子放回報的 `docs`（一條一句，寫明哪個檔、改哪裡），波末一位文件代理統一寫。**這一波不改行為、不改存檔、不動資料庫版本。**",
]


def hb(n, title, dev, ports, body):
    plan = f"docs/superpowers/plans/2026-11-08-架構收尾-第{n}批.md"
    return batch(n, f"架構收尾第 {n} 批：{title}", "core_shared", dev, plan, ports, body + H_NOTE, custom=True)


def b105():
    return hb(105, "沒照架構的搬回去", "dev/fold-back", "8336", [
        "- 範圍照那一節的 1～6，不多做。心神認定是核心資源是 PM 定的，不開包。每一項一個 commit。搬完語法樹比：搬的函式本體除了 `self` 換 `ctx` 之外一樣。",
    ])


def b106():
    return hb(106, "殼不再長", "dev/shell-lock", "8337", [
        "- 範圍照那一節的 1～15，**產品程式 0 行**。每一條守門都先注入違規證明會紅，把注入與紅的訊息寫進回報；哪一條注入了還是綠就是沒做好。名單的數字開工重量。第 15 條的工具做好，規矩的句子放 docs，等企劃者。",
    ])


WEB_H = "**這一波搬了 `web/` 幾段（`.ck-pop`、`heroines`、`faction`、`heroStay`），用 head 的 `scripts/webqa/`，上面「照 tianxia-qa 並排截圖」不用做。** 都不花 token：用 `Start-Process` 分離啟動、輸出導到檔，`docs/superpowers/pm-workflows/wait_file.py <檔> 570` 等，**不要前景跑**。不帶 `--ports`（各挑空埠，拒絕 7861）。\n1. `gate.py --base <base> --head <head> --out <暫存>\\\\web1 --jobs 4`（fast）。量分鐘數，寫進回報。\n2. 看 `summary.json`、`report.txt`。結束碼 0：same=true。結束碼 1：逐列分成①工具誤報（寫進 report，不算 diffs）②這一波真的改了（寫進 diffs，same=false）。結束碼 2：工具壞了，same=true、report 開頭寫「比對沒跑完」與原因。\n3. 工具走不到的實機各走一次，主控台 0 錯誤、網路沒有 4xx／5xx：每天第一次進來的簽到小窗（`.ck-pop`）、設定抽屜的成人內容那一列（`adult-yes`、`adult-no`）、本週卡的「先投一方」與三方表、修練頁的 `heroStay`、狀態列的心神那一格、跟人物說一句扣心神、問酒家的次數到頂。\n4. 收之前 `grep` 兩台伺服器的 log 有沒有 `ImportError`、`ModuleNotFoundError`、`AttributeError`，有就是 blocker。\n**不修工具、不修程式、不跑 selftest，整關不超過 75 分鐘**，到了就交，沒走到的寫清楚。"


WAVES["H"] = dict(
    round2=True,
    extra_lenses=[
        dict(key="guards", text="**守門真的會紅，搬的東西沒變**。第 105、106 批。第 106 批每一條守門親自注入一處違規，跑那個測試，要紅、訊息要說得清楚該放哪；現況要綠。挑最可能的漏網寫法試（不同的引號、多行、別名、`getattr`）。第 105 批：心神、問酒家的次數、`heroines`、`faction` 搬的函式跟原本語法樹比；`Game` 上被叫的名字都還在或呼叫端改了；舊存檔（`tavern_asks` 有值、`xinshen_*` 有值）照讀；新包照 `scripts/new_feature.py` 生出來，守門不會誤紅（生在暫存複本）。`compare --new` 帶參數一樣、不帶紅。"),
    ],
    lines=[dict(name="收尾", batches=[b105, b106])],
    merge_port=8338, fix_port=8339,
    web_check=dict(ports="8340、8341", steps=WEB_H),
)


I_PLAN = "docs/superpowers/plans/2026-11-08-測試流程優化.md"
I_NOTE = [
    "- **測試流程優化這一波**：範圍照 `" + I_PLAN + "` 這一批那一節整節（只讀開頭與那一節；第二輪總表不適用）。數字量在 G 波閘門 `e8e50945`，**開工照現行程式重量，對不上以程式為準**，寫進 decided。上面「計畫不超過 120 行」照舊，計畫寫在 `plan` 那個路徑。",
    "- **各包 README、`docs/guide`、手冊、`CLAUDE.md` 線上不動**：要寫的句子放回報的 `docs`（一條一句，寫明哪個檔、改哪裡），波末一位文件代理統一寫。**不動 `tianxia/`、`web/`、`content/`**（第 108 批准動 `scripts/measure_*.py`、`scripts/sim_server_bots.py` 的參數）。每一項先注入一處壞法證明會紅、再還原，寫進回報。",
]


def ib(n, title, dev, ports, body):
    plan = f"docs/superpowers/plans/2026-11-08-測試流程優化-第{n}批.md"
    return batch(n, f"測試流程優化第 {n} 批：{title}", "core_shared", dev, plan, ports, body + I_NOTE, custom=True)


def b107():
    return ib(107, "閘門與比對只跑改到的", "dev/gate-slim", "8346", [
        "- 範圍照那一節的 1～4。`wave_gate.py` 的 `--changed` 與 `--full`、`scripts/sb/` 的 `covers`、`--covers`、`--crossover`、拿掉 base 前半、`scripts/webqa/` 的對照表與 `--changed-files`。每一樣都要有測試或 selftest；`covers` 用突變法量、寫死進各軌。拿 D～H 五波實際的 diff 跑 `--changed --dry-run` 對照當時的差異，寫進回報。這批不改手冊、不改 `CLAUDE.md`，句子放 docs。",
    ])


def b108():
    return ib(108, "pytest 瘦身", "dev/pytest-slim", "8347", [
        "- 範圍照那一節的 1～5。每一項先單獨量秒數、改完再量、寫進回報；每一項先把被測的東西改壞一次證明斷言還抓得到，再還原。`exp_pace` 那條先 `cProfile` 查原因再決定改哪裡，原因在遊戲規則就不改、寫 leftovers。不刪任何斷言、不標 slow 來藏。",
    ])


WEB_I = "**這一波沒動 `web/`，但改了網頁比對工具本身（`scripts/webqa/gate.py` 的 `--changed-files` 與對照表）。這一關不比畫面，驗工具**。都不花 token：用 `Start-Process` 分離啟動、輸出導到檔，`docs/superpowers/pm-workflows/wait_file.py <檔> 570` 等，**不要前景跑**。不帶 `--ports`（各挑空埠，拒絕 7861）。\n1. 用 head 的 `scripts/webqa/gate.py`：`--mutate` 的每一種 selftest 各跑一次（照它的說明），要全部抓得到。\n2. `coverage.py check` 過；`gate.py --changed-files` 給三種清單各跑一次 dry-run（只列回合不走）：空清單、只有 `web/checkin.js`、含 `web/app.js`，結果要分別是「不跑」「只走命中的回合」「全走」，寫進回報。\n3. 真跑一次 `gate.py --base <base> --head <head> --changed-files web/checkin.js --out <暫存>\\\\web1 --jobs 4`（只為了量時間與確定走得完），量分鐘數；結束碼 0 或 1 都照舊分類，結束碼 2 是工具壞了。\n4. 收之前 `grep` 兩台伺服器的 log 有沒有 `ImportError`、`ModuleNotFoundError`、`AttributeError`，有就是 blocker。\n**不修工具、不修程式，整關不超過 60 分鐘**，到了就交，沒走到的寫清楚。"


WAVES["I"] = dict(
    round2=True,
    extra_lenses=[
        dict(key="proof", text="**工具改了，證明力不能掉**。第 107、108 批。第 107 批：`same_behavior selftest` 全軌三設定要全部一樣、改一個字抓得到；快照版的「前半＋後半＝整段」要真的證明（拿一軌故意在切點之後改行為，前半＋後半要紅）；`covers` 用突變法抽三包驗：改那一包的規則，`--covers <包>` 挑到的軌至少一軌紅、沒挑到的軌裡有沒有也會紅的（有就是 covers 漏了）；`--changed` 對 D～H 的 diff 選的軌要涵蓋當時真正差異過的軌；`webqa` 的對照表突變測試真的紅。第 108 批：每一項改前改後的秒數要重量一次（`--durations=0 -p no:xdist`），斷言還抓得到突變（把量表腳本少印一行、整季拿掉一個事件），`--collect-only` 條數的變化逐條對得上回報。**全程只讀 repo，實驗在暫存複本做。**"),
    ],
    lines=[dict(name="閘門", batches=[b107]), dict(name="瘦身", batches=[b108])],
    merge_port=8342, fix_port=8343,
    web_check=dict(ports="8344、8345", steps=WEB_I),
)


J_DESIGN = "docs/superpowers/specs/2026-11-08-帳號綁定與客服-design.md"
J_PLAN = "docs/superpowers/plans/2026-11-08-帳號與客服-計畫.md"
J_NOTE = [
    "- **帳號與客服這一波**：規格是設計 `" + J_DESIGN + "`（企劃者 11/08 點頭第 2 版），每一批的範圍與不做的照 `" + J_PLAN + "` 這一批那一節。這一批**不做**設計裡別批的事，碰到了寫 leftovers。",
    "- **各包 README 自己填**（新包的 README 是你的）；`docs/guide`、手冊、`CLAUDE.md` 不動，句子放回報的 docs。畫面照 `C:\\Users\\ray61\\AppData\\Local\\Temp\\claude\\81800b313c89d0f8\\ade93b70-b3b7-42db-a8af-21f7a7cbdb16\\scratchpad\\mock\\pick.txt` 企劃者挑的版本；檔案不存在就照對比圖裡 PM 建議的那一版做，畫法集中在一個函式好換。",
]


def jb(n, title, pkg, dev, ports, body):
    plan = f"docs/superpowers/plans/2026-11-08-帳號與客服-第{n}批.md"
    return batch(n, f"帳號與客服第 {n} 批：{title}", pkg, dev, plan, ports, body + J_NOTE, custom=True)


def b201():
    return jb(201, "帳號一：沒有密碼的帳號、登入頁的格、旁檔與備份", "identity", "dev/acct-1", "8348", [
        "- 範圍照計畫第 201 批那一節：`identity` 包生出來（開關預設關）、`accounts.py` 認得沒有密碼的帳號與 `id:<n>` 鍵、`registerGateSlot` 與 `/api/identity/gate`、兩個旁檔與 `_wipe_db`、備份與還原旁檔、`shell_tables.py` 加設計列的路由。**這一批沒有第三方、沒有驗證碼、沒有綁定頁**：那是後面幾批。",
    ])


def b211():
    return jb(211, "客服一：客服單、客服身分、管理頁分流、通知", "support", "dev/support-1", "8349", [
        "- 範圍照計畫第 211 批那一節：`support` 包生出來（開關預設關）、客服單旁檔、玩家送單與看單、客服身分名單與 `/api/support/*`、管理頁分流、通知、契約測試（客服身分打全部管理者 API 被拒）、XSS 測試。**查帳號不做**（客服二）。跟帳號一平行，不要碰 `accounts.py`、`web/shell.js` 的登入頁（客服信箱那一行由帳號一的 `registerGateSlot` 掛，你先在包裡備好 `Feature` 的字，帳號一合進來後再接）。",
    ])


WEB_J = "**這一波加了兩個新包的畫面（開關預設關）**。用 head 的 `scripts/webqa/`，上面「照 tianxia-qa 並排截圖」照做。都不花 token：用 `Start-Process` 分離啟動、輸出導到檔，`docs/superpowers/pm-workflows/wait_file.py <檔> 570` 等，**不要前景跑**。不帶 `--ports`（各挑空埠，拒絕 7861）。\n1. **開關關著**：`gate.py --base <base> --head <head> --out <暫存>\\\\web1 --jobs 4`（fast）。要全部一樣（新包的 js、css 多出來的 script 與 link 行工具自己放行；其他差異是 blocker）。\n2. **開關開著**（head 的設定覆寫檔把 `identity.enabled`、`support.enabled` 打開，只開 head；identity 還要在 head 複本的 `.local/identity.json` 放一把測試金鑰，格式看 `tianxia/core/identity_base.py` 的 `KEY_FILE`，沒有金鑰等於關著；客服身分用 `TIANXIA_SUPPORT=<你建的帳號>` 給）：實機走登入頁多出來的格、設定抽屜的客服格送一張單、客服身分登入看單與回單、玩家被拒的回話；主控台 0 錯誤、網路沒有 4xx／5xx（刻意的 404、400 除外）；375 淺、375 深、1280 各一張，存進回報。\n3. 收之前 `grep` 兩台伺服器的 log 有沒有 `ImportError`、`ModuleNotFoundError`、`AttributeError`，有就是 blocker。\n**不修工具、不修程式，整關不超過 60 分鐘**，到了就交，沒走到的寫清楚。"


WAVES["J"] = dict(
    round2=True, feature=True, design=J_DESIGN, new_packages="identity,support",
    extra_lenses=[
        dict(key="feature", text="**新功能掛開關、關著一個字不變、開著照設計、看不出假人**。第 201、211 批。親自驗：①開關關著：兩包的每條路由 404、`/api/me`、`/api/main`、登入頁輸出位元組一樣（對 base）；`compare --new identity,support` 四軌 season21 一樣（跑一次，幾分鐘）。②開著：照設計 4.1、4.2、6.1、6.2 逐條對程式與測試，少做的、做錯的、做多的都列；每個行為有沒有測試先紅後綠（看 commit 裡測試與程式同一筆、測試斷言真的會紅：挑三條把程式改壞跑看）。③假人：假人沒有帳號，所有對外回話、拒絕、狀態只給本人；用一個假人名號打新路由，回話要跟不存在的人同一句。④殼：`shell_tables.py` 多的每一筆都在設計第七節；`core_changes` 列的每一處都在第七節；沒有讀時鐘；包沒有 import 別包。⑤新字每一句旁有 `待 joy 潤`。⑥旁檔在 `_wipe_db`、備份與還原都接到。**全程只讀 repo，實驗在暫存複本做。**"),
    ],
    lines=[dict(name="帳號", batches=[b201]), dict(name="客服", batches=[b211])],
    merge_port=8350, fix_port=8351,
    web_check=dict(ports="8352、8353", steps=WEB_J),
)


def b202():
    return jb(202, "帳號二：LINE、Google 登入，建角色前不開帳號", "identity", "dev/acct-2", "8354", [
        "- 範圍照計畫第 202 批那一節（含「J 波落地時 PM 加的」兩條：`/api/me` 帶 `identity` 旗標、identity.js 沒旗標不問 gate；登入頁的客服信箱只留 support 包的 gate slot）。假的登入服務測；`NO_LOGIN_ROUTES` 加 start 與 callback 並寫理由；開帳號那一步共用殼的註冊限制。畫面照 `pick.txt` 的 C 版。**不做**驗證碼、綁定頁、忘記密碼。",
    ])


def b203():
    return jb(203, "帳號三：Email、手機驗證碼登入、防刷、寄送介面", "identity", "dev/acct-3", "8355", [
        "- 範圍照計畫第 203 批那一節與設計 4.2 驗證碼、4.6 防刷、4.7 介面：challenge 綁 cookie 與用途、分池上限、Turnstile 伺服器端驗、IPv6 /64、兩個寄送介面與假的實作、個資告知短文連隱私權頁。計數全在旁檔原子化。**不做**綁定、門號回收（第 204 批）。跟第 202 批平行：不要碰 `/api/me`、`server.py`、`web/shell.js`；identity 包裡新開 `codes.py`、`senders.py`，`routes.py` 只加自己的路由，`__init__.py` 的 `Feature` 只加自己的格。",
    ])


def b212():
    return jb(212, "客服二：查帳號", "support", "dev/support-2", "8356", [
        "- 範圍照計畫第 212 批那一節（含「J 波落地時 PM 加的」三條：關著一律 404 且 gate 先於參數解析、易名帖客服本人也不能改名、客服紀錄先存檔成功再標旁檔）。查帳號只收完整帳號、Email、手機（比對 HMAC，用 `core/identity_base.py` 的正規化；手機與 Email 的 HMAC 查詢要等第 203 批的 `logins` 列，這批先接 identity_base 的函式，查不到就回查無）、要帶單號、每位客服每小時 20 次、每次留紀錄（含查無）、看綁定遮掉的字與 `Wallet.ledger`；單上的帳號帶出帳號卡不算查帳次數、照樣留紀錄（企劃者 11/08 挑 B 版）。桌面兩欄照 `pick.txt`。",
    ])


WEB_K = WEB_J.replace("**這一波加了兩個新包的畫面（開關預設關）**", "**這一波：登入頁的快速登入（LINE、Google、Email、手機）、建角色的「已經有帳號？」、客服桌面的查帳號與帳號卡（開關預設關）**").replace(
    "實機走登入頁多出來的格、設定抽屜的客服格送一張單、客服身分登入看單與回單、玩家被拒的回話",
    "實機走：登入頁按 LINE（假的登入服務回一個 subject）進到建角色、「已經有帳號？」那一行、用 Email 收碼（假寄送把碼印在 log）登入、驗證碼錯 5 次作廢、同一號碼 60 秒內再寄被擋、客服桌面點開一張單帶出帳號卡、查完整 Email、**J 波沒走到的客服桌面那一頁（管理頁 B 版：手機與 1024 寬）**")


WAVES["K"] = dict(
    round2=True, feature=True, design=J_DESIGN, new_packages="identity,support", new_existing=True,
    extra_lenses=[
        dict(key="feature", text=WAVES["J"]["extra_lenses"][0]["text"].replace("第 201、211 批", "第 202、203、212 批").replace("照設計 4.1、4.2、6.1、6.2", "照設計 4.2、4.6、4.7、6.3 與計畫的「J 波落地時 PM 加的」") + " **另外**：關著時沒登入打每一條新路由都要 404（不是 401、422）；驗證碼的計數用兩個執行緒同時送同一號碼，不能多寄；challenge 跨用途（登入碼拿去綁定）要被拒；關著時登入頁不再打 `/api/identity/gate`。"),
    ],
    lines=[dict(name="帳號二", batches=[b202]), dict(name="帳號三與客服二", batches=[b203, b212])],
    merge_port=8357, fix_port=8358,
    web_check=dict(ports="8359、8360", steps=WEB_K),
)


def b204():
    return jb(204, "帳號四：綁定頁、近期驗證、解綁、補設密碼、忘記密碼、門號回收、管理者工具、驗證碼登入的畫面", "identity", "dev/acct-4", "8361", [
        "- 範圍照計畫第 204 批那一節全部（含「J 波留下來的」、「K 波留下來的」、「K 波審查與修正輪留下」三段）與設計 4.3、4.4、6.4、6.5；畫面照 `pick.txt`：設定抽屜「帳號綁定」B 版（摺起來、跟修改密碼放一起、摺著時一行寫現況、紅點在摺疊列與 ⚙），驗證碼登入那一頁照登入頁 C 版的手機驗證碼流程。拆成這幾步、每步一筆 commit：①這次 session 的登入方式與時間（`session_auth`）：`server._start_session` 回 token（設計第七節 `server.py` 那一列，PM 11/08 加），密碼、LINE、Google、驗證碼四種登入都記；近期驗證（有密碼打密碼、沒密碼對現有一種重驗一次，查不到就當沒驗過）。②綁：四種都走登入那一套、`purpose=bind`、bind 池；`verified_at`；72 小時新綁限制 `new_binding_hours`；解綁至少留一種（密碼算一種）、解綁後 30 天 `rebind_days`（解綁與刪帳號的雜湊永久留著）；每次綁、解綁、設密碼寫一則「帳號」遊戲紀錄並通知現有 Email、手機（假寄送）。③補設密碼（取帳號名過 `check_login`、同一筆交易寫 `password` 列、鍵不變）；忘記密碼（用綁定方式登入後 10 分鐘內、短效 HttpOnly cookie 證明、`/api/password` 不動、其他裝置登出、通知其他綁定；新綁不滿 72 小時的不能用）。④門號回收：`fresh_days` 180、過期的三種處理、用密碼或第三方的玩家 180 天提醒一次不擋遊戲。⑤管理者工具（identity 包 `admin_tools`：解綁某一種、刪帳號〔刪 `accounts` 與 `logins` 列、名號占住、錢包留著〕、看綁定與時間）；管理者重設密碼畫面列綁定、對沒密碼的回「這個帳號沒有密碼，請他用綁定的方式登入」；名單上的帳號用驗證碼或第三方進來的 session 不給管理與客服權限、權限動作要密碼登入且 6 小時內驗過（接客服一的 strict xfail `test_staff_needs_password_session`，拿掉 xfail）。⑥畫面：綁定頁 B 版；驗證碼登入那一頁（填號碼、Turnstile、收碼、重寄倒數、錯 5 次作廢的提示；K 波的鈕寫「尚未開放」，路由都在）；已登入的瀏覽器再走登入先問一次要不要換帳號；`phone_gate` 開著、沒綁手機時 `Feature.status` 給本人 `phone_missing`、摺疊列與 ⚙ 紅點（第 205 批不碰 identity 包與 `web/identity.*`，紅點歸你）。",
        "- **K 波審查與修正輪留下、這一批順手收**（計畫 204 那一節的「K 波審查與修正輪留下」一段，PM 11/08 加；開工時計畫裡可能還沒有這一段，照這裡）：`routes.py` 的 `api_code_send`、`api_code_verify` 改走 `shell.time.time()`（現在自己 `import time`）；`IdentityStore` 每次請求都建構並跑 DDL 與 `PRAGMA journal_mode=WAL`，改成開一次（新檔併發會 database is locked）；Turnstile `hostname` 為 None 時不要跳過比對；`fake_services` 開著時啟動印警告、正式設定（`season21`、`week7`）載入時擋掉；`AccountStore.login_key` 與 `identity_base.account_key_for` 併成一份。",
        "- **不做**九個入口與灰鈕（第 205 批）、CSP（213）、登入頁客服信箱那一行（214，support 包）、註冊勾選（206）。`web/admin.js` 只改計畫列的那幾行（`:22` 分流、`data-login` 改放 `key`、重設畫面列綁定）；`server.py` 只改 `_start_session` 回 token；`web/shell.js`、`web/app.js` 不碰（設定抽屜那一格走 identity 包已有的掛法）。新字每句 `待 joy 潤`，`rollback` 逐欄寫（旁檔新欄、`session_auth`、`verified_at`）。",
    ])


def b205():
    return jb(205, "帳號五：`phone_ok` 的九個入口、灰鈕、封測發放的手機編號", "identity", "dev/acct-5", "8362", [
        "- 範圍照計畫第 205 批那一節與設計 4.5：`identity_base.phone_ok(ctx, key)` 照判斷順序補完（`identity.enabled` 或 `phone_gate` 關 → 真；鍵不在 `phone_required` 表上 → 真；假人 `state.player.bot` 不是 None → 真；不是假人又查不到帳號 → 假；其餘看 `logins` 有沒有 `provider='phone'`；**開工前先看第 203 批手機驗證碼登入建出來的 `logins` 列長什麼樣，照那一份查**）；九個入口照 4.5「問的位置」那張表逐個接（截殺 `peers/raid_actions.raid`；掛通緝 `bounties/actions` 的 wanted；玩家單 `take`、`give` 只看發單的是不是玩家；贈物 `peers/social._gift`；切磋、論武的發起 `spar_actions.spar`、`discuss_actions.request` 叫模型之前；接受一律在 `invite_actions.answer_invite` 最前面、`invites.drop` 之前，被擋時邀請留著、發起人看到的跟被不理一樣；市集 `looks/actions` 的 list 與 buy，unlist 不擋；商城 `mall/actions.purchase`；封測發放 `mall/actions.grant` 開頭）；被擋時卡與店面的鈕預先灰掉寫原因（`CardButton(enabled=False, note=…)`，只問自己）、回話一句（待 joy 潤）；封測元寶綁了手機那一輪才發、再記一筆 `grant:beta:phone:<HMAC>`（`mall_ledger.ref` UNIQUE）、同一支手機一輩子一次、解綁刪帳號都不放掉；`phone_gate` 開與關各跑一次的測試；**對手三種（沒綁的真人、綁了的真人、假人）發起人看到的逐字相同**（逐字測試；照「只問動手的人」暫定，企劃者問完別人要改再開一批）。",
        "- **不碰** `tianxia/features/identity/`、`web/identity.*`、`web/shell.js`、`web/app.js`（紅點與 `phone_missing` 歸第 204 批）；`identity_base.py` 只改 `phone_ok` 與它要的查詢；別的包只在 4.5 列的那幾個函式開頭加一次判斷、不重排、不改別的字；包不准 import identity 包（問核心 `identity_base`）。`phone_gate` 預設關、關著一個字不變（compare 要一樣）。",
    ])


def b213():
    return jb(213, "CSP 標頭、`battle.js` 的 `onerror`", "server", "dev/csp", "8363", [
        "- 範圍照計畫第 213 批那一節：`server.py` 每個回應加 `Content-Security-Policy: script-src 'self' https://challenges.cloudflare.com; object-src 'none'; base-uri 'none'`（Turnstile 要 `challenges.cloudflare.com`；設計第三節點名「CSP 標頭另開小批」，這就是那一批）；先把 `web/battle.js` 四處 `onerror=` 改成事件註冊；全 repo 掃 `web/`、`index.html`、伺服器生成的頁有沒有 inline `<script>`、`on*=` 屬性、`javascript:` 連結、`eval`／`new Function`，有就改走事件註冊或拿掉，一個都不能留；`tests/server/test_server.py` 加一條每個頁與 API 回應都帶這個標頭、`tests/web/` 加一條 `web/*.js` 與 `index.html` 沒有 inline handler（守住以後不長回來）；用 head 開伺服器實機走江湖、輿圖、店面、決戰、管理頁、登入頁各一次，主控台不能有 `Refused to`。",
        "- **CSP 不是開關**：加了就是整站都有，網頁比對（全回合）要跟 base 一樣、壞一頁就是整站壞。**不做**其他標頭（HSTS、frame-ancestors、Referrer-Policy 另開）。`server.py` 只加這個 middleware 一處（設計第七節 `server.py` 那一列：PM 11/08 加「CSP 標頭」）。",
    ])


def b214():
    return jb(214, "客服三：登入頁的客服信箱那一行（support 包畫）", "support", "dev/support-3", "8364", [
        "- 範圍：登入頁的客服信箱那一行歸 support 包（計畫第 204 批「K 波留下來的」第 202 批那一條，PM 拆成這一批；企劃者 11/08 挑「遊戲內客服單＋登入頁放聯絡方式（客服信箱）」）：`web/support.js` 用 `registerGateSlot` 畫一行「登不進去？寫信到 <信箱>」（字照 `Config.support.mailbox`；待 joy 潤；support 包自己的 `gate_slot()` 與 `GATE_LINE` 接上），開一條不用登入的 `GET /api/support/mailbox`（第一行 gate、關著 404、進 `NO_LOGIN_ROUTES` 寫理由；設計第七節有列）；關著時登入頁輸出位元組一樣（對 base）；`web/support.js` 的 node 測試補這一格；375 與 1280 各看一次。",
        "- **不碰** `web/shell.js`、`web/app.js`、identity 包、`server.py`。接在第 213 批之後同一條線做（同一個工作樹，等 213 commit 完再開；213 動了 `server.py` 的標頭，你開的新路由自然帶到）。",
    ])


WEB_L = WEB_J.replace("**這一波加了兩個新包的畫面（開關預設關）**", "**這一波：設定抽屜的帳號綁定（B 版）、驗證碼登入那一頁、忘記密碼與補設密碼、綁手機才能用的九個入口（`phone_gate`）、登入頁的客服信箱那一行（開關預設關）；CSP 標頭沒有開關、整站都有**").replace(
    "實機走登入頁多出來的格、設定抽屜的客服格送一張單、客服身分登入看單與回單、玩家被拒的回話",
    "實機走：登入頁按 Email 進驗證碼那一頁（假寄送把碼印在 log）登入、設定抽屜「帳號綁定」摺疊列展開、綁一個 Email（走驗證碼）、解綁、補設密碼並取帳號名、忘記密碼（用綁定登入後設新密碼）、管理者重設畫面列綁定；再開 `phone_gate`：沒綁手機時贈物或切磋的鈕灰掉寫原因、⚙ 與摺疊列紅點、用手機驗證碼綁上之後鈕回來；登入頁底下客服信箱那一行；**每一頁主控台沒有 CSP 違規（`Refused to`）**，江湖、輿圖、店面、管理頁也各開一次看").replace(
    "要全部一樣（新包的 js、css 多出來的 script 與 link 行工具自己放行；其他差異是 blocker）", "要全部一樣（新包的 js、css 多出來的 script 與 link 行工具自己放行；其他差異是 blocker）。CSP 關不掉，所以這一關同時在驗 CSP 沒有弄壞任何一頁").replace(
    "客服身分用 `TIANXIA_SUPPORT=<你建的帳號>` 給）", "客服身分用 `TIANXIA_SUPPORT=<你建的帳號>` 給；`fake_services: true` 要一起開——合併時 PM 定過只有公開網址是正式網域才擋，head 要是還擋 `season_one`，覆寫檔多寫 `\"season_one\": false`；`fake_services` 開著 Turnstile 一律過、不必設網站金鑰，head 要是還要 `\"ok\"`，直接打 API 補那一步並寫進回報）")


WAVES["L"] = dict(
    round2=True, feature=True, design=J_DESIGN, new_packages="identity,support", new_existing=True,
    extra_lenses=[
        dict(key="feature", text=WAVES["J"]["extra_lenses"][0]["text"].replace("第 201、211 批", "第 204、205、213、214 批").replace("照設計 4.1、4.2、6.1、6.2", "照設計 4.3、4.4、4.5、6.4、6.5 與計畫 204、205、213 三節") + " **另外**：對手三種（沒綁的真人、綁了的真人、假人）發起人看到的逐字相同（拿三個對手各跑一次截殺、贈物、切磋，把回話與數字 diff）；`phone_gate` 開著假人一律回真、identity 關著一律回真；72 小時、30 天、180 天各挑一條把數字改壞看測試會紅；忘記密碼的 cookie 過期或新綁不滿 72 小時就不能設；名單上的帳號用驗證碼進來打管理者 API 與客服 API 都要被拒；解綁至少留一種；CSP 標頭每個回應都有、`web/` 與 `index.html` 沒有 inline handler；登入頁關著時位元組一樣。"),
    ],
    lines=[dict(name="帳號四", batches=[b204]), dict(name="帳號五", batches=[b205]), dict(name="CSP 與客服三", batches=[b213, b214])],
    merge_port=8365, fix_port=8366,
    web_check=dict(ports="8367、8368", steps=WEB_L),
)


def b207():
    return jb(207, "帳號七：名單上的帳號非密碼 session 不給管理者權限、密碼至少 12 字", "identity", "dev/acct-7", "8369", [
        "- 範圍（企劃者 2026-11-08 答 PM「做，排第 207 批」兩題；設計 4.4、第七節 PM 11/08 補的兩列）：①**名單上的帳號（`config.admins`、`.local/admins.txt`、`TIANXIA_ADMINS`，與客服名單）用驗證碼或第三方進來的 session 不給管理者權限**：殼的 `/api/main` 的 `admin` 欄、`/api/do` 走到管理者動作（`admin:` 前綴、`admin_tools`）那一段、admin 包的 `/api/admin*` 守門、identity 包的 `/api/identity/admin/accounts` 與三個管理者工具，都接上核心 `identity_base.staff_session_ok`（第 204 批寫好的：這次 session 是密碼登入、而且 `staff_hours` 6 小時內登入或重驗過）。**identity 關著時管理者行為位元組一樣**：這一層只在 `identity_base.on()` 真時判（客服那一半 identity 關著看 `SessionStore.created`，管理者這一半照同樣寫法），退版寫清楚。`engine.Game.is_admin` 留名號判斷（遊戲規則到處用它），殼在呼叫前多一層 session 判斷；不夠的回話跟不是管理者同一句、管理頁的分流跟不是管理者一樣。②**名單上的帳號密碼至少 12 字**：`accounts.check_password` 分出「名單上的帳號」那一條，`/api/register`（取到名單上的帳號名）、`/api/password`、管理者重設、`scripts/set_password.py` 都走；現有的短密碼下次改才要求、登入不擋；新字一句（待 joy 潤）。測試：名單上的角色用手機驗證碼登入（假寄送）後 `/api/main` 的 `admin` 是 False、`/api/admin/reset_password`、`/api/do` 的管理者動作、identity 的管理者工具都被拒，密碼登入 7 小時前的也被拒、重驗後回來；identity 關著時全部照舊（對 base 位元組一樣）；12 字四條路都有先紅後綠。殼只改設計第七節那兩列點名的地方，`shell_tables` 不加。",
        "- **不做**扣押期的入口、通知、池上限、紅點（第 208 批，平行線：不要碰 `tianxia/features/identity/binding.py`、`notes.py`、`web/identity.js`、mall／peers／looks；identity 的 `routes.py` 只動管理者那三條與 `admin/accounts`）。",
    ])


def b208():
    return jb(208, "帳號八：扣押期的入口、綁定通知寄到加密存的號碼、池上限通知管理者、紅點即時更新", "identity", "dev/acct-8", "8370", [
        "- 範圍照計畫第 207 批那一節的前四條與企劃者 2026-11-08 的答案：①**扣押期的入口**（設計 4.3、4.4、6.4）：新綁 72 小時內的那一種、只剩過期一種時的 7 天扣押、管理者重設密碼後 72 小時，都不能花元寶、贈物、上架市集：核心 `identity_base` 加 `hold_reason(ctx, key)`（照 `phone_ok` 的樣子：假人、沒帳號、identity 關著一律沒有扣押），資料用第 204 批旁檔的 `bindings_meta.bound_at`、`holds`；入口在第 205 批接 `phone_ok` 的同一批函式旁邊多問一次（`mall/actions.purchase` 與貨架、`peers/social._gift`、`looks/actions` 的 list），被擋時灰鈕與那一句（待 joy 潤；`phone_ok` 的那一套照抄）；管理者重設密碼（admin 包 `reset_password`）之後寫一則「帳號」紀錄並記 72 小時的 hold（admin 包不能 import identity 包，經核心 `identity_base` 寫）。②**綁、解綁、設密碼的通知**（企劃者 11/08 選「另存加密的號碼給通知用」；設計 4.3 補了做法）：`.local/identity.json` 第二把金鑰 `notify_key`（讀不到就只寫紀錄、不寄、不 500），綁 Email、手機成功時把號碼用它加密存旁檔新表（跟 HMAC 分開、不進任何查詢與比對），只在寄通知那一刻解開，解綁、刪帳號就刪那一列；每次綁、解綁、補設密碼、忘記密碼都經 `senders` 寄一則給現有的 Email、手機（假寄送測，`outbox` 之外也印一行到 log 讓 QA 看得到；正式機 `NoSender` 就是不寄）。③**全服池上限到了通知管理者**（第 203 批留下）：`check_all_and_record` 回滿的那一格桶名，寫一行進管理頁（admin 包現成的訊息欄；admin 包經核心讀）並經 `shell.WEB_PUSH` 推給管理者名單上開著推播的人（None 就跳過），同一格一小時最多通知一次。④綁、解綁手機之後 ⚙ 紅點與摺疊列標題不重新載入就更新（`web/identity.js`，L 波實機點到的）；管理頁解綁、刪帳號做完自己重找一次（`web/admin.js` 那幾行，facade 軌 `IDENTITY_ADMIN_TOUCHED` 跟著改並逐行列進回報）。",
        "- **不做**管理者權限那一半、12 字（第 207 批，平行線：不要碰 `server.py`、`engine.py`、`accounts.check_password`、identity 的 `routes.py` 管理者那三條與 `admin/accounts`、`admin.py`）；`scripts/maintenance.py` 的 inline script 與其他標頭另開。資料庫第 9 版不動；旁檔新表 `CREATE TABLE IF NOT EXISTS`。",
    ])


WEB_M = WEB_J.replace("**這一波加了兩個新包的畫面（開關預設關）**", "**這一波：名單上的帳號非密碼 session 不給管理者權限、密碼 12 字、扣押期的灰鈕、綁定通知、紅點即時更新（開關預設關）**").replace(
    "實機走登入頁多出來的格、設定抽屜的客服格送一張單、客服身分登入看單與回單、玩家被拒的回話",
    "實機走：名單上的角色用 Email 驗證碼登入（假寄送把碼印在 log）後進不了管理頁、`/api/main` 的 admin 是 False，用密碼登入就回來；名單上的帳號改密碼 11 字被拒、12 字過；新綁手機後商城購買鈕灰掉寫原因（把時鐘撥過 72 小時後回來）；綁 Email 時 log 裡有一則寄給它的通知；綁、解綁手機後 ⚙ 紅點與摺疊列標題不重新載入就變").replace(
    "客服身分用 `TIANXIA_SUPPORT=<你建的帳號>` 給）", "客服身分用 `TIANXIA_SUPPORT=<你建的帳號>` 給；`fake_services: true`；`.local/identity.json` 多放 `notify_key`）")


WAVES["M"] = dict(
    round2=True, feature=True, design=J_DESIGN, new_packages="identity,support", new_existing=True,
    extra_lenses=[
        dict(key="feature", text=WAVES["J"]["extra_lenses"][0]["text"].replace("第 201、211 批", "第 207、208 批").replace("照設計 4.1、4.2、6.1、6.2", "照設計 4.3、4.4、6.4 與計畫第 207 批那一節加企劃者 11/08 的四個答案") + " **另外**：名單上的角色用驗證碼登入後管理者 API 全部被拒（`/api/do` 的管理者動作、admin 包、identity 的管理者工具、`/api/main` 的 admin 欄），identity 關著時管理者行為對 base 位元組一樣；扣押期三種各有一條先紅後綠；加密存的號碼不進任何查詢（grep 旁檔的 SELECT 只用 HMAC 欄）；`notify_key` 讀不到不寄也不 500；池上限的通知一小時最多一次。"),
    ],
    lines=[dict(name="帳號七", batches=[b207]), dict(name="帳號八", batches=[b208])],
    merge_port=8371, fix_port=8372,
    web_check=dict(ports="8373、8374", steps=WEB_M),
)


B107_SCRATCH = r"C:\Users\ray61\AppData\Local\Temp\claude\81800b313c89d0f8\ade93b70-b3b7-42db-a8af-21f7a7cbdb16\scratchpad\waveI\b107"


def b109():
    return ib(109, "covers 重量、decide 收窄、網頁回合不再跟著退回全軌", "dev/covers-109", "8375", [
        "- 範圍：計畫第 109 批那一節的第 1、2、4、5、6 項，加第 11 項裡 `docs/superpowers/pm-workflows/wave_gate.py` 那一半（PM 11/08 深夜落地 M 波時把第 3、7～10 項與第 11 項 `scripts/webqa/gate.py` 那一半拆成第 110 批，平行線；計畫檔上那一節頭一段寫了怎麼分，照這裡）。`wave_gate.py` 只有這一批動；**不碰 `scripts/webqa/`、`tests/web/`**（第 110 批的）。",
        "- **第 1 項 covers 重量**：第 107 批的一次性腳本在 `" + B107_SCRATCH + "`（`measure.py`、`measure_all.py`、`analyze.py`、`write_covers.py`、`covers_measured.json`），拿來改成一支可重跑的工具放 `scripts/sb/`（例 `scripts/sb/covers_measure.py`；量一次全軌 season21 多久寫進回報），不是再寫一次性腳本。量到函式層級（`sys.monitoring` 照舊）；先算「每一軌都叫到的共同那一組」（被 ≥ 90% 的軌碰到的函式；門檻寫進 decided，試過別的門檻也寫），扣掉之後只算超出的函式屬於哪一包，各軌 `register_track(covers=…)` 改成量出來的；`wicket`、`missive`（K 波開的）實際量。**反向驗**：抽 5 對（包, 軌）改字突變——改 A 包的規則，`--covers A` 挑到的軌至少一軌紅、沒挑到的軌一軌都不能紅；紅在沒挑到的軌就是 covers 漏了，補上再驗，5 對的結果逐對寫進回報。量不出合理的結果（例：扣掉共同組之後大半軌還是碰到全部包）就把分佈數字與原因寫進回報、`ALWAYS_TRACKS` 的過渡維持，不硬改。",
        "- **第 2 項 decide 收窄**（`wave_gate.decide`）：只改一軌的 `scripts/sb/tracks/<軌>.py` 只跑那一軌（改到 `scripts/sb/` 其他檔照舊退回全軌）；`tianxia/core/*.md`（例 `services_list.md`）不退；`.gitattributes` 不退。每一條在 `tests/core/test_same_behavior_gate.py` 先紅後綠。拿 D～M 各波的真 diff（tag 與 `develop` 上各波落地的 SHA，交接第一節有）`--dry-run --changed` 各跑一次，改前改後對照（軌數、設定、半舊半新、網頁）列成表寫進回報。",
        "- **第 11 項 gate 那一半**：`decide` 的 `web_all_rounds` 現在是 `web_other or full`，所以動到核心退回全軌時網頁也全回合（M 波只改 `web/identity.js`、`web/identity.css`，卻因 `server.py`、核心 identity_base 退回全軌，網頁全回合跑了 70 分）。改成只看 `web_other`：核心退回全軌只管比對的軌，網頁回合照改到的 `web/` 檔挑；`server.py` 回頁面的行、css、html、`scripts/webqa/` 照舊全走。`--changed-files` 給的檔在對照表上對不到時怎麼辦由第 110 批在 `gate.py` 裡定，你只把檔名原樣交過去。先紅後綠一條。",
        "- **第 4 項**只做決定：拿第 107 批量到的秒數（到 0.67、3.44、3.51、16.57）決定要不要一個子行程連跑多軌，決定與理由寫進回報，**這一批不實作**。**第 6 項**不另跑整波：用 `C:\\Ray\\專案\\天下大勢\\.local\\wave_gate\\<head8>\\result.json` 裡 K、L、M 三波的分鐘數（`cb411b94`、`63909841`、`a86686c7`、`96862401` 有哪個用哪個）列表寫進回報。**第 5 項**兩個檔的快取：先量再改、各省多少秒寫回報；超過 30 分鐘就寫 leftovers。",
    ])


def b110():
    return ib(110, "網頁比對工具：對照表重建、`--new` 扣新包的 css、c 回合 overlay、`--jobs` 各自複本、outbox、對不到回合的檔", "dev/webqa-110", "8376", [
        "- 範圍：計畫第 109 批那一節的第 3、7、8、9、10 項與第 11 項 `scripts/webqa/gate.py` 那一半（PM 11/08 深夜從第 109 批拆出來的第 110 批，平行線；計畫檔上那一節頭一段寫了怎麼分）。只動 `scripts/webqa/**`、`tests/web/test_webqa.py`（`tests/kit/webharness.py` 非動不可寫理由）；**不碰 `docs/superpowers/pm-workflows/wave_gate.py`、`scripts/sb/`**（第 109 批的）。你的計畫檔照 `ib` 的路徑寫（`…-第110批.md`）。",
        "- **第 9 項先做**（其他項要跑比對都靠它）：`--jobs N` 時每個 job 自己一份 head、base 複本，或起伺服器前先把 `.local/webpush_vapid.pem` 放好（兩邊同一把測試金鑰，不讀 repo 的 `.local/`）；證明：`--jobs 4` 跑一次沒有 MalformedFraming、沒有一軌中途停。",
        "- **第 3 項對照表重建**：`coverage.json` 用不帶 `--quick` 的走法重建（4 個 `zh_` 必到場景要走到；`must_reach.txt`），埠用 OS 給的空埠（拒絕 7861）或明說 4 個；`explore.js`、`territory_acts.js`、`state.js`、`sw.js` 要在表上，或 `coverage.py check` 說得出為什麼不在（例 `sw.js` 不是頁面 script）。重建一次多久寫進回報。",
        "- **第 7 項 `--new <包>` 扣 css**：`css-rules` 的差異扣掉那些包自己的 css（`web/<包>.css`）的規則，扣掉的印成清單進 report（跟 compare 一樣「新東西列出來，其餘一樣」）；別的 css 照樣 real。突變兩條：改 `identity.css` 一條規則 → 列進扣掉清單、不算 real；改 `style.css` 一條 → real。",
        "- **第 8 項 `c` 回合 `bt_open_overlay`**：那一景靠 `web/battle.js` 開場 overlay 4.2 秒自動關，base、head 哪邊慢一點就拍到關了的。改成確定的：拍之前把自動關閉停掉（driver 給 `window.__qaHold` 那一類鉤子）或比 `facts.overlay` 不等截圖；**`web/battle.js` 不是你的檔**，鉤子要是非得頁面配合，寫成 leftovers 給 battle 包、這一批用等待條件的做法。證明：同一筆 base＝head 跑 c 回合兩次都 0 real。",
        "- **第 10 項 outbox**：第 208 批定了驗證碼不進 log，只有通知那一行 `LOG_LINE`。webqa 的回合要是走到驗證碼（現在沒有，identity 關著）就讀 `fake_services` 的 outbox：`serve.py` 加一個選項把 outbox 傾進檔（M 波實機驗收用包住 `server.main` 的啟動檔做的），只在 identity 開著時用；寫進 gate.py 的說明。沒有流程走到就寫清楚「備好、沒驗過」。",
        "- **第 11 項 gate.py 那一半**：`--changed-files` 給的檔在對照表上對不到時：包的檔（`web/<包>.js`、`web/<包>.css`，`tianxia/features/<包>/` 存在）→ 不走，report 寫「關著時沒有回合走到」；殼的檔（其他 `web/`、`index.html`）→ 全走。dry-run（只列回合不走）三種清單各印一次：空、`web/identity.js`、`web/app.js`，結果要分別是不跑、不走（寫原因）、全走，寫進回報。`wave_gate.py` 那一半（`web_all_rounds` 不再因 full 而真）是第 109 批的。",
    ])


WEB_N = "**這一波沒動 `web/`，改的是網頁比對工具本身。這一關不比畫面，驗工具**。都不花 token：用 `Start-Process` 分離啟動、輸出導到檔，`docs/superpowers/pm-workflows/wait_file.py <檔> 570` 等，**不要前景跑**。不帶 `--ports`（各挑空埠，拒絕 7861）。\n1. 用 head 的 `scripts/webqa/`：`selftest.py`／`gate.py --mutate` 每一種各跑一次，要全部抓得到；`coverage.py check` 過。\n2. `gate.py --changed-files` 三種清單各 dry-run 一次（只列回合不走）：空、`web/identity.js`、`web/app.js`，結果要分別是「不跑」「不走（寫原因）」「全走」，寫進回報。\n3. 真跑一次 `gate.py --base <base> --head <head> --out <暫存>\\\\web1 --jobs 4 --new identity,support`（工具改了、頁面沒改：要 0 real；c 回合不能紅；沒有 MalformedFraming），量分鐘數；結束碼 0 或 1 都照舊分類，結束碼 2 是工具壞了。\n4. 收之前 `grep` 兩台伺服器的 log 有沒有 `ImportError`、`ModuleNotFoundError`、`AttributeError`，有就是 blocker。\n**不修工具、不修程式，整關不超過 60 分鐘**，到了就交，沒走到的寫清楚。"


WAVES["N"] = dict(
    round2=True,
    extra_lenses=[
        dict(key="proof", text="**工具改了，證明力不能掉**。第 109、110 批。第 109 批：covers 用突變法再抽 3 對（跟開發抽的不同）驗——改那一包的規則，`--covers <包>` 挑到的軌至少一軌紅、沒挑到的軌一軌都不紅；共同組的門檻合理（看量出來的分佈：扣掉共同組之後每軌平均碰幾包、最多幾包；`--covers` 對 D～M 真 diff 各挑幾軌，跟那幾波閘門真正差異過的軌對得上）；decide 收窄的每一條有先紅後綠的測試；`web_all_rounds` 不再因 full 而真、但殼的檔（`server.py` 回頁面的行、css、html、`scripts/webqa/`）仍全走。第 110 批：對照表是不帶 `--quick` 重建的、4 個 `zh_` 必到場景在；`--new` 扣 css 的兩條突變（identity.css 扣掉、style.css 仍 real）真的一邊紅一邊不紅；`c` 回合 base＝head 跑兩次 0 real；`--jobs 4` 沒有 MalformedFraming；`--changed-files` 三種清單的結果對。兩批合起來 `same_behavior selftest` 全軌三設定仍全部一樣、改一字抓得到。**全程只讀 repo，實驗在暫存複本做。**"),
    ],
    lines=[dict(name="比對", batches=[b109]), dict(name="網頁工具", batches=[b110])],
    merge_port=8377, fix_port=8378,
    web_check=dict(ports="8379、8380", steps=WEB_N),
)


N_COV_REPORT = r"C:\Users\ray61\AppData\Local\Temp\claude\81800b313c89d0f8\ade93b70-b3b7-42db-a8af-21f7a7cbdb16\scratchpad\waveN\cov\report.txt"


def b111():
    return ib(111, "網頁比對的 flow 跟上 Joy 的 UI 手感批與見聞頁改版、對照表重建、`news` 包進 covers", "dev/webqa-111", "8385", [
        "- 範圍：只動 `scripts/webqa/**`（flows、snippets、must_reach.txt、coverage.json）與 `tests/web/test_webqa.py`；第 3 項另准 `scripts/sb/covers_measure.py write` 改各軌的 `covers=`（只那一個關鍵字）。**不動 `web/`、`tianxia/`、`content/`、`docs/superpowers/pm-workflows/wave_gate.py`、`scripts/sb/` 其他檔**。flow 真的點不到（新 UI 沒有那個控制了）就寫 leftovers 給那個包或 Joy，不改頁面。",
        "- 起因：Joy 11/09 02:10～02:22 合了 #197～#205 進 develop（見聞頁改版〔新包 `news`、`web/news.js`〕、UI 手感甲～戊批：店面蓋住底下選單、決戰陣容不寫兩次、灰的懸賞寫原因、交友先挑人、名帖、擂台榜、成長剪影與決戰回合格的圖）。PM 在 N 波落地那一筆上用 `scripts/webqa/gate.py --base X --head X --jobs 4` 重走八回合，**14 個必到場景沒到**：main 的 `sm_repair`、`sm_temper`、`sm_material`、`mk_wield`、`mk_buy`、`market_left`、`bd_take`、`bd_drop`、`mt_edit`、`mt_shuffle`、`mt_close`、`call_list`、`call_zhujun`；x 的 `x_news_xingshi`。報告在 `" + N_COV_REPORT + "`（「not reached」那一段列了每一景點不到的 selector，例：`.shop-layer .shop-back`、`[data-act=\"news\"][data-news=\"mingtie\"]`、`[data-act=\"mt-edit\"]`、`[data-act=\"choose\"][data-id^=\"bounty:\"]`、`[data-act=\"tav-do\"]`）。先讀 Joy 那幾筆的 diff（`git diff 0b5a4864e d3befbb21 -- web/`）再改 flow。下一波的網頁閘門會因為這些必到場景結束碼 2，所以這一批要快。",
        "- **第 1 項 flow 跟上新 UI**：每一個沒到的場景照新 UI 的 DOM 改 flow 的走法（selector、先開哪一層、店面的返回鈕在哪），讓它在 season21 的 base＝head 走法下到得了；`must_reach.txt` 一景都不拿掉（新 UI 真的沒有那個控制了才拿掉，理由寫進 decided 與 leftovers）。證明：`gate.py --base <develop 那一筆> --head <同一筆> --out <暫存> --jobs 4` 整趟 exit 0、tool 0、`missing_must_reach` 空，量分鐘數寫進回報。",
        "- **第 2 項對照表重建**：第 1 項那一趟走完用 `coverage.py build <summary.json>` 重建 `coverage.json`；看 cs 回合這次有沒有自己量到 `figure_acts.js`、`sortie.js`（有就不用跟舊表聯集；沒有照第 110 批的做法聯集，寫進 decided）；`coverage.py check` 過；`web/news.js` 要在表上。",
        "- **第 3 項 `news` 包進 covers**：`python scripts/sb/covers_measure.py measure --out <夾>`（三設定全軌約 16 分）→ `analyze <夾>`（門檻 90%，ALWAYS 不變量破了結束碼 1）→ `write <夾>`，讓 `news` 有軌（`tests/core/test_same_behavior_covers.py` 的「沒有一軌走到的包」警告消失）；反向驗一對：改 `tianxia/features/news/` 一處一定跑到的字（在暫存複本改，不提交），`same_behavior pick --covers news` 挑到的軌至少一軌紅、沒挑到的軌一軌都不紅。量出來沒有軌進得了見聞頁的後端就寫 decided、留警告、不硬加軌。",
        "- **第 4 項證明工具還活著**：`selftest.py` 至少跑 c 回合版（同對同綠、兩個正控制紅；一個回合約 500 秒，別跟第 1 項那一趟同時跑）。`tests/web/test_webqa.py` 既有的全過，改了 selector 的地方若有 snippet 測試就補。",
        "- 要寫進 docs 的（放回報，文件輪寫）：手冊 4.2 或 tianxia-flow「網頁閘門」加一句「UI 改了（Joy 的 PR 合進 develop 之後尤其）要跑一次 `gate.py --base X --head X --jobs 4` 看 `must_reach`，點不到的 flow 要跟著改，不然下一波網頁閘門結束碼 2」。",
    ])


WEB_O = "**這一波沒動 `web/`，改的是網頁比對的 flow。這一關不比畫面，驗工具**。都不花 token：用 `Start-Process` 分離啟動、輸出導到檔，`docs/superpowers/pm-workflows/wait_file.py <檔> 570` 等，**不要前景跑**。不帶 `--ports`（各挑空埠，拒絕 7861）。\n1. 用 head 的 `scripts/webqa/`：`gate.py --base <head> --head <head> --out <暫存>\\\\web1 --jobs 4` 整趟（約 35 分）：要 exit 0、tool 0、`missing_must_reach` 空（14 個必到場景全到，含 `x:x_news_xingshi`）；量分鐘數。\n2. `coverage.py check` 過；`coverage.json` 裡 `web/news.js` 在表上；`scripts/same_behavior.py pick --covers news` 印出的軌（沒有就看開發 decided 寫的理由）。\n3. `gate.py --dry-run --changed-files` 三種清單各一次：空、`web/news.js`、`web/app.js`，結果要是不跑、挑到表上那幾回合、全走。\n4. 收之前 `grep` 兩台伺服器的 log 有沒有 `ImportError`、`ModuleNotFoundError`、`AttributeError`，有就是 blocker。\n**不修工具、不修程式，整關不超過 60 分鐘**，到了就交，沒走到的寫清楚。"


WAVES["O"] = dict(
    round2=True,
    extra_lenses=[
        dict(key="proof", text="**工具改了，證明力不能掉**。第 111 批。flow 改了 selector 之後那 14 個必到場景是真的走到新 UI 的那一層（看 summary 的 scenes 與 facts，不是只看 must_reach 沒缺）；`must_reach.txt` 沒有被拿掉任何一景（拿掉的要有 decided 與 leftovers）；`coverage.json` 是從這一趟 summary 的 `round_files` 建的（抽兩個回合對一次）；`news` 的 covers 反向驗一對跟開發抽的不同的突變；`tests/web/test_webqa.py` 全綠。**全程只讀 repo，實驗在暫存複本做。**"),
    ],
    lines=[dict(name="網頁工具", batches=[b111])],
    merge_port=8386, fix_port=8387,
    web_check=dict(ports="8388、8389", steps=WEB_O),
)


def b209():
    return jb(209, "帳號九：登入驗碼補存通知號碼、驗碼與回呼補扣押、「請用密碼重新登入」、identity 開著全體 12 字、新標頭與維修頁", "identity", "dev/acct-9", "8390", [
        "- 範圍照計畫第 209 批那一節（M 波留下的五條與順手核對），加企劃者 2026-11-09 答 PM 的兩題（原話「1 不改，2 選 A」）：①**一般動作裡只問 `ctx.is_admin()` 的兩處（探索包抹除副本 `outing_actions.py`、名帖 `mingtie_actions.py`）不改**：`engine.Game.is_admin` 留名號判斷、那兩處一個字不動，只在你的計畫檔與 identity 包 README 寫一句「企劃者 11/09 答不改」。②**A：identity 開著時全體密碼至少 12 字**（不只名單上的，這樣註冊頁就試不出客服名單）：`accounts.check_password(password, staff)` 的嚴格條件改成「identity 開著就全體」（參數改名成 `strict` 之類，所有呼叫一起改）；六條路都走——`server.py` 的 `register`（1609 行那一段）、`change_password`（1649 行那一段）、identity 包 `routes.py` 的補設密碼 `/api/identity/password/set` 與忘記密碼 `/api/identity/password/reset`、admin 包 `routes.py` 重設密碼那一行（173 行）、`scripts/set_password.py`（67～73 行）——通通不再查 `identity_base.listed`，只看 `identity_base.on(CONTENT)`；拒絕的那一句改成不帶「這個帳號」的寫法（例「密碼至少 12 字。」，`# 待 joy 潤`，舊的 `STAFF_SHORT_PASSWORD` 換字或改名）；現有的短密碼登入不擋、下次改才要求（同第 207 批）；**identity 關著六條路對 base 位元組一樣**（`PASSWORD_MIN` 照舊）；登入頁註冊格 identity 開著時多一行提示「密碼至少 12 字」，由 identity 的 gate slot（`identityGateHtml`）畫，**不改殼的 `main.js`、`app.js`**。測試：六條路 11 字都被拒、名單上與名單外同一句、12 字過；identity 關著 8 字照舊過；先紅後綠。",
        "- **M 波留下的五條**：③登入用途的驗碼成功（`/api/identity/code/verify`）與用驗證碼開新帳號（`/api/identity/character` 那條路）也把那支 Email、手機用第 208 批的寫法封存成通知用的號碼（`contacts.py` 的 AESGCM、`store.put_contact`；`notify_key` 讀不到就不存、不 500；第三方登入沒有號碼不存）；之後解綁、補設密碼等通知就寄得到。④驗碼那一步（`code_verify`）與第三方回呼（`api_callback`）補 `identity_base.reset_held(...)`：扣押中就擋、回跟 `start` 那一步同一句 `RESET_NO_BIND`。⑤**「請用密碼重新登入」的提示**：identity 包加一條要登入的路由（第一行 gate、關著 404、沒登入先 401；例 `GET /api/identity/session`）回 `{\"relogin\": true}`，**只有這個帳號在名單上（`identity_base.listed`）而且 `admin_session_ok` 假時才真**，名單外永遠假、回同一個形狀（本人登入後問自己的帳號，試不出別人）；`web/identity.js` 在設定抽屜「帳號綁定」摺疊（`identityFoldHtml`）上方多一行提示（一句新字 `// 待 joy 潤`），`/api/main` 的 `admin` 假時才問、旗標假時不畫；殼不動、`web/admin.js` 不動（admin 包的；要在管理頁也提示寫 leftovers）。⑥**管理者重設、管理者解綁、「這不是我的帳號」要不要寄通知——PM 2026-11-09 定：寄**（照第 208 批的規矩經 `senders` 寄給剩下綁著的 Email、手機；「這不是我的帳號」寄給被拿掉那一支以外的；沒有可寄的只寫紀錄；每種一句 `# 待 joy 潤`）。⑦**標頭與維修頁**：`server.py` 現有的 CSP middleware 那一處（第七節「只加一處 middleware」，不另開第二處）每個回應多 `Strict-Transport-Security: max-age=31536000; includeSubDomains`（不加 preload）、`Referrer-Policy: strict-origin-when-cross-origin`、`X-Content-Type-Options: nosniff`，CSP 加 `frame-ancestors 'none'`（我們嵌 Turnstile 的 iframe 不受這條影響；公開頁 `/zhuan/*`、`/zhanji/*` 也不給人嵌）；`style-src`、`img-src`、`default-src` **只掃不加**：掃 `web/`、`index.html`、公開頁、維修頁的 inline `style=`、`<style>`、`data:` 圖與外部圖網域，數字與清單寫進回報與 leftovers（加 `default-src` 時要連 `frame-src https://challenges.cloudflare.com` 一起）。`scripts/maintenance.py` 的 inline `<script>` 搬成它自己回的外部檔（同一支腳本多一條路徑），頁面照舊每 N 秒探一次。測試：`tests/server/test_server.py` 標頭那一條加三個新標頭與 `frame-ancestors`；維修頁一條「沒有 inline script、script 帶 src、探測那段照舊」。",
        "- **順手核對**：⑧扣押期擋的花元寶現在只有商城買（`mall/actions.py`）、形象市集買與上架（`looks/actions.py`）、贈物（`peers/social.py`）：找全部花元寶的入口（錢包 `Wallet` 的扣款從哪幾處叫：自建形象、招式下單、其他），沒擋的照第 205、208 批的寫法經核心 `identity_base.hold_reason(ctx, <key>)` 補（灰鈕加那一句、照抄 `phone_ok` 那一套），補了哪幾處列進回報；真的沒有別處就寫沒有。⑨identity 開著的幾段沒有 same_behavior 軌走到——**這一批不加軌**，寫 leftovers 給測試流程線（加一軌開著 identity 的情境要先問 PM）。",
        "- **不做**：第 206 批（條款）、IPv6 /64、support 包、`web/admin.js`、`engine.py`（企劃者答不改）、`Game.is_admin`、`main.js`／`app.js`、`shell_tables`（路由都在 identity 包裡；殼只改第七節點名的 `register`、`change_password` 兩段與 CSP middleware 那一處）。資料庫第 9 版不動；旁檔新欄 `ADD COLUMN`／新表 `CREATE TABLE IF NOT EXISTS` 照第 208 批。`core_changes` 逐條列（`identity_base.py` 是 identity 的核心接縫、`accounts.py`、`server.py` 三段、admin 包那一行、`scripts/set_password.py`、`scripts/maintenance.py`），寫企劃者原話「1 不改，2 選 A」（2026-11-09）。退版照第 207、208 批的寫法逐欄寫（換回舊程式：12 字只是不再要求、標頭少掉、提示那條路由 404、補存的 contacts 列沒人讀，什麼都不丟；季中能換）。",
    ])


WEB_P = "**這一波：identity 開著全體密碼 12 字、名單上的帳號非密碼 session 的「請用密碼重新登入」提示、登入驗碼補存通知號碼、驗碼與回呼補扣押、新標頭與維修頁（開關預設關）**。用 head 的 `scripts/webqa/`，上面「照 tianxia-qa 並排截圖」照做。都不花 token：用 `Start-Process` 分離啟動、輸出導到檔，`docs/superpowers/pm-workflows/wait_file.py <檔> 570` 等，**不要前景跑**。不帶 `--ports`（各挑空埠，拒絕 7861）。\n1. **開關關著**：閘門帶 `--changed` 已經跑過網頁比對（`.local/wave_gate/<head8>/web/report.txt`），這一關不重跑，只看它有沒有 real（有就是 blocker）。另外對 head 與 base 各 `curl -I` 首頁與 `/api/main`：head 每個回應都有 HSTS、`Referrer-Policy`、`X-Content-Type-Options`，CSP 多 `frame-ancestors 'none'`；base 沒有。\n2. **開關開著**（head 的設定覆寫檔把 `identity.enabled`、`support.enabled` 打開，只開 head；`fake_services: true`；`.local/identity.json` 放測試金鑰與 `notify_key`，格式看 `tianxia/core/identity_base.py` 的 `KEY_FILE` 與 `tianxia/features/identity/contacts.py`；客服身分用 `TIANXIA_SUPPORT=<你建的帳號>`）：實機走——註冊頁用 11 字密碼開一個不在名單上的帳號被拒、換 12 字過；用名單上的帳號名（`config.json` 的 `admins` 裡的 `Rayal`）11 字也被拒、回話跟前面一字不差；登入頁註冊格看得到「密碼至少 12 字」那一行提示（base 沒有）；名單上的角色用 Email 驗證碼登入（假寄送把碼印在 log）後設定抽屜看得到「請用密碼重新登入」那一行、看不到「管理者工具 ›」，不在名單上的人用驗證碼登入看不到那一行；用驗證碼登入的這個 Email 之後在綁定頁解綁，log 裡有一則寄給它的通知（這一批補存的號碼）；管理者重設某人密碼之後，那個人拿重設前寄出的驗證碼去驗被擋、回的是扣押那一句；主控台 0 錯誤、沒有 `Refused to`；網路沒有 4xx／5xx（刻意的 404、400、401 除外）；375 淺、375 深、1280 各一張，存進回報。\n3. 照 `scripts/maintenance.py` 開頭的說明把維修頁起在空埠：頁面沒有 inline `<script>`、script 帶 src、自己探的那一段照常每 N 秒打一次 `/api/main`；主控台沒有 `Refused to`。\n4. 收之前 `grep` 兩台伺服器的 log 有沒有 `ImportError`、`ModuleNotFoundError`、`AttributeError`，有就是 blocker。\n**不修工具、不修程式，整關不超過 60 分鐘**，到了就交，沒走到的寫清楚。"


WAVES["P"] = dict(
    round2=True, feature=True, design=J_DESIGN, new_packages="identity,support", new_existing=True,
    extra_lenses=[
        dict(key="feature", text=WAVES["J"]["extra_lenses"][0]["text"].replace("第 201、211 批", "第 209 批").replace("照設計 4.1、4.2、6.1、6.2", "照設計 4.3、4.4、第七節與計畫第 209 批那一節加企劃者 11/09 的兩個答案（原話「1 不改，2 選 A」）") + " **另外**：identity 開著時註冊、改密碼、補設、忘記密碼、管理者重設、`scripts/set_password.py` 六條路 11 字都被拒、名單上與名單外回同一句（名單試不出來）、12 字過；identity 關著六條路對 base 位元組一樣；「請用密碼重新登入」的旗標只有名單上的帳號本人登入後拿得到，名單外永遠假、路由第一行 gate；`engine.Game.is_admin` 與探索抹除副本、名帖那兩處一個字沒動（企劃者答「不改」）；驗碼成功與第三方回呼在 `reset_held` 時被擋；登入用途驗碼成功有把號碼加密存進 contacts（`notify_key` 讀不到不存、不 500）；每個回應都有新標頭、`frame-ancestors 'none'` 不擋我們嵌的 Turnstile；維修頁沒有 inline script；扣押期補擋的花元寶入口每一處都經核心 `identity_base.hold_reason`。"),
    ],
    lines=[dict(name="帳號九", batches=[b209])],
    merge_port=8391, fix_port=8392,
    web_check=dict(ports="8393、8394", steps=WEB_P),
)


def b112():
    return ib(112, "decide 把 `tuning/<包>.py` 歸包、假人座位進 covers、子行程啟動占比、webqa 沒到的景與 flow 說明、identity 開著的軌怎麼開", "dev/gate-112", "8395", [
        "- 範圍：計畫第 112 批那一節（PM 11/09 從「之後（不在這一波）」挑出來的六項）。動 `docs/superpowers/pm-workflows/wave_gate.py`、`scripts/sb/**`（`covers_measure.py`、`harness.py`、軌檔只准改 `covers=`）、`scripts/webqa/**`（flows、`driver.mjs` 的說明、`must_reach.txt`）、`tests/core/test_same_behavior_gate.py`、`tests/core/test_same_behavior_covers.py`、`tests/web/test_webqa.py`。**不碰 `tianxia/`、`web/`、`server.py`**。",
        "- **第 1 項 decide 歸包**（`wave_gate.decide`）：改 `tianxia/core/tuning/<包>.py` 算改那一包（`packages` 加它，跟改 `tianxia/features/<包>/` 一樣挑軌；包不存在才退回全軌），不再因它退回全軌。先紅後綠一條。拿 K、L、M、P 四波的真 diff（交接第一節有 SHA：`cb411b94`、`63909841`、`96862401`、P 波合好的那一筆）`--changed --dry-run` 改前改後各跑一次，表寫進回報（P 波因 `server.py`、`accounts.py` 仍退全軌，照實寫）。",
        "- **第 2 項 假人座位進 covers**：`covers_measure.py measure` 也量 `harness.BOT_SEATS` 每個座位的 runner 走到哪幾包（同一套 `sys.monitoring`、同一個共同組門檻），寫進 `covers.json` 與 `register_bots(covers=…)`（或等值的登記）；`same_behavior.py pick --covers <包>` 挑到的座位才跑、`ALWAYS_TRACKS` 的座位照跑；`verify --mutate` 一對（改一包的規則，挑到的座位紅、沒挑到的不紅）。量一次多久寫進回報。",
        "- **第 3 項 子行程啟動占比**：covers 收窄之後再量一次（拿 P 波閘門 `compare.txt` 各軌 base／head 秒數與 `--tracks drape,facade` 那種小跑的總牆鐘，算啟動佔比），**只做決定**：要不要一個子行程連跑多軌，決定與理由寫進回報，這一批不實作。",
        "- **第 4 項 webqa 沒到的景**：酒肆 `tv_*_do1`、`tv_hit`、`tavern_left`（`tav-do` 第二下 missing；`tv_hire` 之後 `.shop-layer .shop-back` missing）、召喚對話 `call_log`、`call_talk`、`call_act`、`call_close`（`fig-talk` 打開對話後 `fig-log`、`fig-talk`、`fig-act`、`fig-close` missing）、求兵 `bd_pick`、`bd_give`（第一張揭得下的告示不是求兵），**加上 P 波閘門新冒出來的感悟畫板兩景** `sense_pad_clear`、`sense_sent`（must_reach 裡的；`133_sense_pad_drawn` 之後 `sense-clear`、`sense-send` 兩側都 missing、連 disabled 的都沒有；O 波基準 `97e0a3ee0` 走得到、`727234452` 起走不到，中間只有 Joy 11/09 合的六個 PR：見聞改版的「改版資訊進遊戲後跳一次」、俠客頁多信匣與名帖匣、結義、書信、條款、拿掉豪強的季。PM 11/09 另派查核，結果寫在 `origin/develop` 的交接「現在在跑」與 `docs/superpowers/plans/2026-11-09-波次P紀錄.md`「落地（PM）」節，**開工先 `git fetch origin develop` 讀那兩處**：查出是畫面真的壞〔玩家畫完鈕不見〕就不在這一批修、寫進回報交 PM；是 flow 走不到才在這裡修）——照現行 DOM 改 flow 讓它們走到；走到之後穩的（連跑兩次都到）才加進 `must_reach.txt`，不穩的寫 decided 不加。`driver.mjs` 開頭補「寫 flow 的注意」（店面開著 `#page` hidden、鈕在 `.shop-layer`／`.horse-card`／`.board-sheet` 裡找、`CHP(\"<前綴>:\")` 會撞「‹ 出店」、兩人以上交友先跳名單）與 `--quick` 的限制（手冊 4.2 那三點）。證明：不帶 `--quick` 的八回合 base＝head exit 0、`missing_must_reach` 空，summary 裡這幾景都到。",
        "- **第 5 項 identity 開著的軌怎麼開**（只研究、寫法建議，**這一批不加軌**）：現在 `register_track(..., profile=)` 只能挑 season21／week7／test 三種設定，identity 開著要 `Config.identity.enabled`、`fake_services`、`.local/identity.json` 的固定金鑰（照 webqa `gate.seed_local` 的做法）、驗證碼要固定或從假寄送讀回。量出：harness 要加什麼（每軌 `overrides=` 或第四種設定檔）、金鑰怎麼放進兩份複本、碼怎麼固定、半舊半新切點、假人段要不要；寫成一節給 PM 定，附預估工時。",
        "- **第 6 項**：`nightly.py` 程式 diff 為空就沿用上一次閘門（每週強制一次）——只寫決定與做法進回報，不實作。",
    ])


def b206():
    return jb(206, "帳號六：註冊兩個勾選、建帳號記版本（接 Joy 的條款包）", "identity", "dev/acct-6", "8396", [
        "- 範圍照設計第五節與計畫第 206 批那一節（PM 2026-11-09 重寫）；依據是企劃者 2026-11-08 原話「使用條款是另一條線（拿資料庫第 10 版，帳號這邊接註冊的兩個勾選）」加設計第五節「記版本的函式要放核心，或由條款包掛進註冊與建角色的流程」。**條款包已經在 develop**（Joy 11/09 PR #193，`tianxia/features/terms/`：`/terms`、`/privacy` 不用登入、`GET /api/terms`／`POST /api/terms/agree` 要登入、登入後沒同意現行版的疊一層 `.terms-layer`、同意紀錄在旁檔 `<db>-terms.sqlite` 的 `consents(id, account, version, source, at)`、`store.SOURCES` 有 `register`、`routes.record_consent(shell, account_key, version, source)` 已寫好只有測試叫；**資料庫不升版**，第 10 版的說法作廢）。先讀它的 README「給註冊那一邊」那一段、`rules.py`、`store.py`、`routes.py`、`web/terms.js`。",
        "- ①**核心接縫 `tianxia/core/terms_base.py`**（新檔；照第 209 批 `identity_base.set_notifier`／`notify` 的寫法：核心只放掛鉤與純規則，包在掛路由時登記；`tianxia/core/__init__.py` 的說明與 `tests/core/boundary_tables.py` 照 `identity_base` 的樣子登記）：`on(content)`（`config.terms.enabled`）；`set_hook(obj)`，hook 要有 `version()` 與 `record(account_key, source)`；`register_check(content, body)`——開著而且 hook 在時，`terms_agree`、`age_ok` 兩個勾選都要是真、`terms_version` 等於 `hook.version()`，不然丟 `GameError` 一句（`# 待 joy 潤`，兩種情形同一句，不透露版本），關著或沒 hook 什麼都不做；`record(content, account_key, source=\"register\")`——沒 hook 回 False、不 500，`ValueError(STALE)` 吞掉只記 log。terms 包在 `routes.py` 掛路由時 `terms_base.set_hook(...)`（`version` 讀 `rules.load()[\"version\"]`，`record` 叫 `record_consent`）。",
        "- ②**殼與建角色各兩行**：`server.py` 的 `register`（約 1604 行那一支）建帳號前 `terms_base.register_check(CONTENT, body)`，`account_store().register(...)` 成功後 `terms_base.record(CONTENT, key)`；`/api/register` 的 handler 把 body 整個（或多讀 `terms_agree`、`age_ok`、`terms_version` 三欄）傳給它。identity 包 `/api/identity/character`（`routes.py:307` 那一支，建角色那一步才開帳號；設計第五節的順序：驗身分 → 建角色頁的勾選 → 建帳號記版本 → 進遊戲）同樣兩行，`web/identity.js` 建角色的送出要把表單裡多出來的欄位一起送（整張表單序列化，不要只挑名字、性別）。**terms 關著兩條路對 base 位元組一樣**（`register_check`、`record` 關著直接 return）。",
        "- ③**畫面在 terms 包的 `web/terms.js`**（Joy 的包；不改殼 `app.js`、`main.js`；它本來就用 MutationObserver 改 `.gate` 的 DOM）：登入頁註冊模式的 `#gate-form`（`.seg` 切到註冊時）與 identity 的建角色表單（`identityCreateHtml` 畫的那一張；用它的 form 或 `data-` 記號找）各插兩個勾選——「我已滿 18 歲或已得到法定代理人同意」（`name=\"age_ok\"`）、「我已讀過並同意《使用條款》與《隱私權條款》」（`name=\"terms_agree\"`，兩個書名連 `/terms`、`/privacy`，新分頁）——與 hidden `terms_version`；版本從 terms 包新加的 `GET /api/terms/version`（不用登入、第一行 gate、關著 404、只回 `{version}`）拿；沒勾就送出時前端先擋、在表單下面寫那一句（同 ①，`// 待 joy 潤`）；terms 關著不插、不問。`tests/core/shell_tables.py` 的 `NO_LOGIN_ROUTES` 加 `GET /api/terms/version` 一列寫理由（還沒註冊的人要拿得到版本號；跟 `/terms` 同一個理由）。字每句旁 `待 joy 潤`，兩個勾選的字照 Joy 的 `terms.js` 同意鈕那句（「我已滿 18 歲或已得到法定代理人同意，並同意以上條款」）拆成兩句。",
        "- ④**K 波留下的連結**：`web/identity.js` 第三方那格「隱私權說明」`href=\"#\"`（`IDENTITY_PRIVACY_LINK`）改連 `/privacy`（新分頁）；驗證碼輸入處要是已經有個資告知那段字就加同一個連結，沒有就寫 leftovers 不加。",
        "- ⑤**同意層不重問**：註冊時記了 `register` 之後進遊戲 `/api/terms` 的 `need` 是空字串、不跳層（terms 現有的 `rules.need`，不改）；測試一條走完整條路。",
        "- 測試：terms 開著——殼註冊沒勾、只勾一個、版本舊 → 同一句被拒、帳號沒建；都勾 → 建了、`consents` 多一列 `source=register`、進遊戲不跳層；identity 建角色同樣四條；terms 關著 → 兩條路對 base 位元組一樣、`/api/terms/version` 404、terms.js 不插勾選；node 測試：terms.js 註冊模式插兩個勾選與 hidden、登入模式不插、沒勾擋送出；邊界（terms 只 import 核心、identity 不 import terms）；`shell_tables` 那一列。每一條先紅後綠。",
        "- **不做**：條款內容與版本（`content/terms.json` 不動）、同意層的畫法（terms 現有）、金流、IPv6 /64、第 209 批的東西（已進 develop）。資料庫第 9 版不動；terms 旁檔的表不改（只多寫 `register` 的列）。`core_changes` 逐條列（`core/terms_base.py` 新檔、`server.py` register 兩行與 body 欄位、`shell_tables.NO_LOGIN_ROUTES` 一列、terms 包 `routes.py` 掛 hook 與新路由、`web/terms.js`、identity 包兩處），每條寫依據（上面的原話與設計第五節）。退版：換回舊程式只是註冊不記 consent、登入後由同意層補問，什麼都不丟；季中能換；緊急開關 `Config.terms.enabled`（關掉就回到 base 的註冊）。",
    ])


WEB_Q = "**這一波兩線：帳號六（註冊兩個勾選接條款包，開關預設關）與測試工具第 112 批（flow 與 covers，沒動 `web/`）**。用 head 的 `scripts/webqa/`，上面「照 tianxia-qa 並排截圖」照做。都不花 token：用 `Start-Process` 分離啟動、輸出導到檔，`docs/superpowers/pm-workflows/wait_file.py <檔> 570` 等，**不要前景跑**。不帶 `--ports`（各挑空埠，拒絕 7861）。\n1. **開關關著**：閘門帶 `--changed` 已經跑過八回合網頁比對（`.local/wave_gate/<head8>/web/report.txt`），這一關不重跑，只看它有沒有 real（有就是 blocker）、`missing_must_reach` 空（第 112 批第 4 項改了 flow，那幾景要到）。\n2. **開關開著**（head 的設定覆寫檔把 `identity.enabled`、`support.enabled`、`terms.enabled` 打開，只開 head；`fake_services: true`；`.local/identity.json` 放測試金鑰與 `notify_key`）：實機走——登入頁切到註冊：看得到兩個勾選與《使用條款》《隱私權條款》兩個連結（點開是 `/terms`、`/privacy` 兩頁）；都不勾送出被擋、表單下面有那一句；只勾一個也被擋；都勾送出 → 進遊戲，**沒有**疊同意層；登出、用 Email 驗證碼走到建角色頁：也有兩個勾選，沒勾被擋、勾了建好進遊戲不跳層；第三方那格的「隱私權說明」連到 `/privacy`；主控台 0 錯誤、沒有 `Refused to`；網路沒有 4xx／5xx（刻意的 401、404、400 除外）；375 淺、375 深、1280 各一張，存進回報。\n3. **第 112 批的工具**：`python scripts/webqa/coverage.py check` 過；`python scripts/same_behavior.py pick --covers identity` 印軌數（第 1 項歸包後應該跟 N 波量的 17 軌同一個量級）；`wave_gate.py --base <base> --head <head> --changed --dry-run` 的 decision 貼進回報。\n4. 收之前 `grep` 兩台伺服器的 log 有沒有 `ImportError`、`ModuleNotFoundError`、`AttributeError`，有就是 blocker。\n**不修工具、不修程式，整關不超過 60 分鐘**，到了就交，沒走到的寫清楚。"


WAVES["Q"] = dict(
    round2=True, feature=True, design=J_DESIGN, new_packages="identity,support,terms", new_existing=True,
    extra_lenses=[
        dict(key="feature", text=WAVES["J"]["extra_lenses"][0]["text"].replace("第 201、211 批", "第 206 批").replace("照設計 4.1、4.2、6.1、6.2", "照設計第五節、條款包 README「給註冊那一邊」與計畫第 206 批那一節（PM 11/09 重寫）") + " **另外**：terms 關著時 `/api/register` 與 `/api/identity/character` 對 base 位元組一樣、`/api/terms/version` 404、terms.js 不插勾選；開著時沒勾、只勾一個、版本舊三種都同一句被拒且帳號沒建；都勾建好之後 `consents` 多一列 `source=register`、進遊戲 `/api/terms` 的 `need` 空；核心 `terms_base` 只有掛鉤與純規則、不 import 包；identity 包沒有 import terms；`shell_tables.NO_LOGIN_ROUTES` 多的那一列有理由；新字每句旁有 `待 joy 潤`。"),
        dict(key="proof", text="**工具改了，證明力不能掉**。第 112 批。第 1 項：`decide` 對 `tianxia/core/tuning/<包>.py` 歸包有先紅後綠、K／L／M／P 四波的 dry-run 表改前改後對得上；第 2 項：假人座位的 covers 是量出來的（看 covers.json 有座位那一段）、反向驗一對真的一邊紅一邊不紅、`pick --covers` 沒挑到的座位真的不跑（看 compare 的 bots 段）；第 4 項：那九景在不帶 `--quick` 的八回合裡真的到了（summary 的 scenes），加進 `must_reach.txt` 的只有連跑兩次都到的；第 5、6 項只有文字、沒有程式。**全程只讀 repo，實驗在暫存複本做。**"),
    ],
    lines=[dict(name="帳號六", batches=[b206]), dict(name="測試工具", batches=[b112])],
    merge_port=8397, fix_port=8398,
    web_check=dict(ports="8399、8400", steps=WEB_Q),
)


def b210():
    return jb(210, "帳號十：驗證碼頁的個資告知短文、管理頁的「請用密碼重新登入」、解綁與重設密碼的通知搬出行動鎖、註冊頁的條款版號重問", "identity", "dev/acct-10", "8405", [
        "- 範圍照計畫第 210 批那一節（PM 2026-11-09 把帳號留下的小件歸成一批）；依據：企劃者 2026-11-09 對 PM 列的「帳號留下的小件一批：驗證碼頁的個資告知、管理頁的重新登入提示、解綁通知搬出行動鎖，加上面兩條 nit」答「2. ok」。五項都小，一段一筆 commit、測試先行。這一批准碰 `web/identity.js`、`web/terms.js`（Joy 的條款包那一支，只動第 4、5 項那幾行）、identity 包、核心 `tianxia/core/features.py` 的 `AdminTool` 與 `server.py` 的 `api_do`（只第 3 項那幾行）；**不碰** `web/admin.js`、admin 包、`app.js`、`main.js`、`accounts.py`、`engine.py`、`shell_tables.py`（沒有新路由）。",
        "- **第 1 項 驗證碼輸入處的個資告知短文連 `/privacy`**（第 203、206 批留下；設計第五節、個資法第 8 條）：`web/identity.js` 的 `identityCodeHtml` **寄碼前那一張**（輸入 Email、手機號碼的地方；登入 `login`、綁定 `bind` 兩種用途都要，`reauth` 也照畫）畫 `codes.NOTICE`（第 49 句，新字清單已有）加「隱私權說明」連結（沿用 `IDENTITY_PRIVACY_LINK` 那幾個字；`href` 照 `Config.identity.privacy_url`，新分頁 `rel=\"noopener\"`）。字與網址怎麼到畫面：identity 自己的 `GET /api/identity/gate`（`gate_info`）多帶 `notice`、`privacy` 兩鍵（關著照舊 404），設定抽屜綁定那一邊用它既有的回應帶同樣兩鍵；**不加新字、不改殼**。寄出之後那一張照舊（`st.notice` 現在放的是「已寄出」那一句，不動）。node 測試：寄碼前有短文與連結、連結指 `/privacy`；關著不畫。",
        "- **第 2 項 管理頁的「請用密碼重新登入」**（第 209 批留下）：`/admin` 跟江湖頁是同一張頁（admin 包 `routes.py` 回 `shell.current_page()`），`web/identity.js` 已經有 `IDP_RELOGIN`（第 17x 句）與問 `GET /api/identity/session` 的那一段（約 478～490 行，只在設定抽屜畫）。加：在 `/admin` 路徑、管理頁畫出來之後（`web/admin.js` 的 `.ad-head`／`.ad-wait` 出現時，用 MutationObserver 或殼既有的 render 事件，**不改 `web/admin.js`**）也問一次 `relogin`，真就在管理頁標題下補同一句（同一個 class `idp-relogin`，不另造字）；名單外的人、關著、404 什麼都不多畫；一頁只畫一次。node 測試：relogin 真在 `/admin` 有那一行、假沒有；江湖頁那一行照舊。admin 包一個字不動（admin 不能 import identity；這是 identity 包自己的畫面）。",
        "- **第 3 項 管理者解綁、管理者重設密碼的通知搬出行動鎖**（第 209 批留下；企劃者 11/09「2. ok」）：現在 `identity_unbind` 是 `AdminTool`，在 `server.py` `api_do` 的 `act()` 裡跑，`admin.unbind` 最後那一行 `contacts.send_all` 在鎖裡寄；`reset_password`（admin 包 `routes.py` 176 行 `identity_base.notify`）看它是不是也在鎖裡（`/api/admin/reset_password` 那條路有沒有進 `act()`／`action_lock`）。真的簡訊、Email 是 HTTP 呼叫，卡在全服的行動鎖裡會讓所有人等。**PM 傾向的做法**：核心 `tianxia/core/features.py` 的 `AdminTool` 加一個可選欄 `after: Callable[[], None] | None = None`（預設 None，現有的包一個字不改），`run` 在鎖裡做完、把要寄的（account_id、那一句、extra／skip）記在 game 的暫存或 closure；`server.py` `api_do` 在 `act()` 回來、放鎖之後叫 `tool.after()`（例外只記 log，不影響回話）；identity 的 `identity_unbind` 改成 `run` 不寄、`after` 寄。`reset_password` 在鎖裡的話也改成放鎖之後寄（admin 包經核心 `identity_base.notify` 的既有掛鉤，看怎麼延後最小）；不在鎖裡就寫一句不動。另一種做法是改走既有的 outlock 三段式（要自己做 `is_admin` 與 `admin_session_ok` 的檢查、關著 404），比較大，不選的話寫 decided 為什麼。玩家與管理者看到的回話一個字不變；寄的對象與內容照第 209 批。測試：假 sender 記下「寄的那一刻鎖有沒有被握著」（例：sender 在 `send` 裡試 `WorldStateStore.action_lock` 拿不拿得到，或 `act` 包一層記順序），解綁那一則要在放鎖之後；`test_identity_notify.py` 的 `test_admin_unbind_notifies_rest` 照過；`tests/core` 契約測試對 `AdminTool` 新欄位（有 `after` 的工具 `after` 被叫一次、沒有的照舊）一條。`core_changes` 逐條列（`core/features.py` 一欄、`server.py` 三行上下、identity `admin.py`／`routes.py`、admin 包要是改了寫哪一行），寫企劃者原話「2. ok」（2026-11-09，對 PM 列的那一句）。",
        "- **第 4 項 註冊頁的條款版號重問**（Q 波審查 nit）：`web/terms.js` 的 `termsVersion()` 把版號快取一整頁；條款改版後沒重新整理的註冊頁帶舊版號送出，被 `REGISTER_NEED` 同一句擋住、重勾也沒用。改成**送出前重問一次**：`termsBlockSubmit` 兩個勾選都勾了之後，capture 攔下這一次 submit、重新 fetch `/api/terms/version`、更新 hidden `terms_version`、再 `form.requestSubmit()`（或等值做法）放行一次（用旗標避免無窮攔；fetch 失敗照舊版號送、讓伺服器那一句擋）；不透露版本、不加新字；關著照舊不插不擋。node 測試：版號改了再送一次就過；改之前那條（沒勾擋）照過。這一支是 Joy 的條款包的檔，只動這一段，其他一行不碰。",
        "- **第 5 項 順手核對**：terms 關著時 `terms.js` 每次畫註冊表單多打一次 `/api/terms/version`（404）。能用頁面上現成的資訊判斷關著就不問（例：殼已經有的某個旗標、或 404 之後記住這一頁不再問——現在已經是 null 就不再問，看還有沒有多打的情形），沒有乾淨的做法就寫理由不做，不加路由、不改殼。",
        "- 測試：identity 包 `tests/`（py 與 node）；terms 包 node 測試；`tests/core/test_contract_features.py`（`AdminTool` 新欄位）；identity 關著時 `/api/identity/gate` 404 照舊、`web/identity.js` 不畫；terms 關著位元組一樣。每一條先紅後綠。`new_strings`：預期沒有（短文是第 49 句、提示是第 209 批那一句、連結字沿用）；真的要新字每句旁 `待 joy 潤`。",
        "- **不做**：管理者刪帳號照舊不寄；維修頁的標頭；自建形象與招式下單的 `phone_ok` 入口；IPv6 /64；金流（企劃者 11/09「先不動」）；第 113 批（測試工具）的東西。資料庫第 9 版不動；旁檔不改表、不加欄。退版：換回舊程式只是短文與提示不見、通知回到鎖裡寄、版號照舊快取，什麼都不丟；季中能換；緊急開關 `Config.identity.enabled`、`Config.terms.enabled`。",
    ])


WEB_R = "**這一波一線：帳號十（帳號留下的小件：驗證碼頁的個資告知短文、管理頁的「請用密碼重新登入」、解綁與重設的通知搬出行動鎖、註冊頁的條款版號重問；開關預設關）**。用 head 的 `scripts/webqa/`，上面「照 tianxia-qa 並排截圖」照做。都不花 token：用 `Start-Process` 分離啟動、輸出導到檔，`docs/superpowers/pm-workflows/wait_file.py <檔> 570` 等，**不要前景跑**。不帶 `--ports`（各挑空埠，拒絕 7861）。\n1. **開關關著**：閘門帶 `--changed` 已經跑過網頁比對（`.local/wave_gate/<head8>/web/report.txt`），這一關不重跑，只看它有沒有 real（有就是 blocker）、`missing_must_reach` 空。\n2. **開關開著**（head 的設定覆寫檔把 `identity.enabled`、`support.enabled`、`terms.enabled` 打開，只開 head；`fake_services: true`；`.local/identity.json` 放測試金鑰與 `notify_key`）：實機走——登入頁按 Email（或手機）：輸入號碼那一張看得到個資告知短文與「隱私權說明」連結，點開是 `/privacy`；設定抽屜的綁定那一邊按綁 Email 也看得到同一段；名單上的帳號（`config.json` 的 `admins` 裡的 `Rayal`）用 Email 驗證碼登入後開 `/admin`：看得到「請用密碼重新登入」那一句、不是只有「管理資料沒拿到」；不在名單上的人用驗證碼登入開 `/admin`：沒有那一句（看到什麼照實寫）；管理者用密碼登入，管理頁解綁某人一支 Email：回話照舊、伺服器 log 有寄給剩下那一支的通知（假寄送印的那一行），而且回應先回、寄送在後（看 log 時間或順序；量不到就寫量不到）；主控台 0 錯誤、沒有 `Refused to`；網路沒有 4xx／5xx（刻意的 401、404、400 除外）；375 淺、375 深、1280 各一張，存進回報。\n3. 註冊頁的版號重問不用實機改條款版本，看開發的 node 測試有沒有那一條、`terms.js` 送出前有沒有重問（網路面板看第二次 `/api/terms/version`）。\n4. 收之前 `grep` 兩台伺服器的 log 有沒有 `ImportError`、`ModuleNotFoundError`、`AttributeError`，有就是 blocker。\n**不修工具、不修程式，整關不超過 60 分鐘**，到了就交，沒走到的寫清楚。"


WAVES["R"] = dict(
    round2=True, feature=True, design=J_DESIGN, new_packages="identity,support,terms", new_existing=True,
    extra_lenses=[
        dict(key="feature", text=WAVES["J"]["extra_lenses"][0]["text"].replace("第 201、211 批", "第 210 批").replace("照設計 4.1、4.2、6.1、6.2", "照設計第五節、4.3、6.5 與計畫第 210 批那一節（PM 11/09 歸成一批）") + " **另外**：identity 關著時 `/api/identity/gate` 404、`web/identity.js` 不畫短文與管理頁提示、對 base 位元組一樣；terms 關著 `terms.js` 不插不擋；開著時寄碼前那一張有 `codes.NOTICE` 與連到 `/privacy` 的連結（登入與綁定兩種用途）、管理頁的提示只有名單上非密碼 session 的本人拿得到、名單外永遠沒有；管理者解綁與重設密碼的通知在放鎖之後才寄（看測試怎麼證明，不是只看有寄）、回話一個字不變；`AdminTool` 新欄位預設 None、現有的包一個字不改；註冊頁送出前重問版號、改版後再送一次就過、不透露版本；沒有新路由、`shell_tables` 不動；`web/admin.js` 與 admin 包不動（第 3 項 reset_password 那一行除外，動了要寫理由）；新字每句旁有 `待 joy 潤`（預期沒有新字）。"),
    ],
    lines=[dict(name="帳號十", batches=[b210])],
    merge_port=8406, fix_port=8407,
    web_check=dict(ports="8408、8409", steps=WEB_R),
)


def b113():
    return ib(113, "43 軌 covers 改寫、Joy 三包（結義、帖友書信、條款）加軌、webqa 補一景與三個會抖的畫面、nightly 程式沒變就沿用", "dev/gate-113", "8410", [
        "- 範圍：計畫第 113 批那一節（PM 11/09 從第 112 批留下的挑四項；企劃者 2026-11-09 傍晚原話「前四項開，A 案等要開帳號功能再做」）。動 `scripts/sb/**`（新軌只加檔；各軌的 `covers=` 由 `covers_measure.py write` 改）、`scripts/webqa/**`（flows、`must_reach.txt`、`noise.py`）、`scripts/nightly.py` 與它們的測試（`tests/core/test_same_behavior_covers.py`、`tests/web/test_webqa.py`、nightly 既有的測試檔，沒有就開一個）。**不碰 `tianxia/`、`web/`、`server.py`、`content/`、`docs/superpowers/pm-workflows/wave_gate.py`**。順序 2 → 1 → 3 → 4（先加軌再量 covers，三包才一起進表）。",
        "- **第 2 項 Joy 三包加軌**（先做）：`jieyi`（結義，Joy PR #195）、`mail`（帖友書信，PR #196）、`terms`（條款，PR #193 加第 206 批）現在沒有一軌走到（`test_same_behavior_covers.py` 的警告），開關都預設關。`scripts/sb/tracks/` 各加一檔（新軌只加檔；名字一個英文字、不跟現有的軌重複，寫進回報），照 `petition.py`、`wicket.py` 的樣子寫：**關著段**打包的路由（兩邊 404）與 `/api/main` 的鍵；**開著段**在情境裡把開關打開（既有做法：`self.tweak(self.c.config.<包>, enabled=True)` 或直接設，例 `tracks/levy.py`、`loom.py`、`relic.py`），走包的主流程——結義：邀、應、名單、解除、第 6 人被拒（最多 5 人）；帖友書信：先交換名帖再寄信、收信匣、沒交換過的被拒、小檔 `<db>-mail.sqlite` 的段落雜湊；條款：`/terms`、`/privacy`、`/api/terms/version`、`/api/register` 帶兩個勾選與版號（沒勾、只勾一個被拒）、`GET /api/terms` 的 `need`、`POST /api/terms/agree`、旁檔 `<db>-terms.sqlite`。半舊半新切在開著段寫過東西之後、重新登入之後；假人段看包的 `bots.py` 有沒有東西（沒有寫沒有）。先讀三包的 README、`routes.py`、`tests/`。`selftest --tracks <三軌>`：三設定跑兩次一樣、改一個字抓得到（`MUTANT_PROFILE` 那一種）。",
        "- **第 1 項 43 軌 covers 改寫**：第 112 批重量出來有 43 軌的 covers 跟登記的不同、這一波才改。加了三軌之後 `python scripts/sb/covers_measure.py measure --out <夾>`（三設定全軌加假人座位，約 16 分）→ `analyze <夾>`（門檻 90%，ALWAYS 不變量破了結束碼 1）→ `write <夾>`（全部，不帶 `--seats-only`）；`git diff --stat scripts/sb/tracks scripts/sb/base.py` 的軌數寫進回報（照實，不一定剛好 43）。反向驗 `verify --mutate` 抽三包（一大一小加 Joy 的一包，例 battle、support、titles）：挑到的至少一軌紅、沒挑到的一軌都不紅。`test_same_behavior_covers.py` 全過、三包的警告消失。量一次多久寫進回報。",
        "- **第 3 項 webqa 補一景與三個會抖的畫面**：①`patch_pop`：第一次 `asPlayer` 進江湖頁、點掉小窗之前先拍 Joy 的改版資訊小窗（`.sheet.patch-pop`，從沒比過）一景進 main 回合，連跑兩次都到才進 `must_reach.txt`；②`call_close`、`call_act`（人物層的 × 與護衛）：第 112 批不走的原因是 layer-open 時捲軸有沒有；在 flow 裡等 layer-open 的樣式落定（或 `noise.py` 認「只在 layer-open 的景、差在捲軸那一條」那一類，要窄），收回來走、進 must_reach；③`zh_write`（題壁寫字）base＝head 偶爾像素 REAL：查原因（字型、畫布時機、游標閃）、釘得住就釘，釘不住就寫一條只對那一景的窄 noise 規則，寫進 decided。證明：不帶 `--quick` 八回合 base＝head **連跑兩趟**都 exit 0、tool 0、`missing_must_reach` 空（兩趟都要）。`tests/web/test_webqa.py` 既有的全過，noise 規則加一條測試。",
        "- **第 4 項 nightly 沿用**：照計畫第 112 批第 6 項寫好的做法實作進 `scripts/nightly.py`：`prepare_checkout` 之後讀前一次 `<日期>.json` 的 `sha` 與最後一次真跑的日期；`git diff --name-only <前一次 sha>..<今天的 sha>` 扣掉 `docs/`、`.claude/`、根目錄 `*.md` 之後是空的、前一次跑完而且綠、離最後一次真跑不到 7 天 → 不跑 pytest，`<日期>.json` 記 `reused_from`、`last_real`，`latest.txt` 第一行「沿用 <SHA>（程式沒變）」其餘照前一次；`tests/` 變了照跑；加一個強制跑的參數（例 `--force`）。判斷寫成獨立的函式、單元測試用假的 git 輸出五種情形（空 diff 沿用、只改 docs 沿用、改 tests 要跑、超過 7 天要跑、前一次紅要跑）。`scripts/nightly.ps1` 看一眼會不會因為沿用提早結束而壞，不改它。**不要真跑整套**來驗。",
        "- **不做**：A 案 identity 開著的軌（固定金鑰、固定驗證碼、遮雜湊欄、切點）——企劃者 11/09「A 案等要開帳號功能再做」；`wave_gate.py`；一個子行程連跑多軌（第 112 批已決定不做）；`web/`、`tianxia/` 一行不動。退版：只影響測試工具與每日整套，退回第 112 批那一筆照舊。",
    ])


WEB_S = "**這一波沒動 `web/`，改的是比對工具的軌與 covers、網頁比對的 flow、每日整套。這一關不比畫面，驗工具**。都不花 token：用 `Start-Process` 分離啟動、輸出導到檔，`docs/superpowers/pm-workflows/wait_file.py <檔> 570` 等，**不要前景跑**。不帶 `--ports`（各挑空埠，拒絕 7861）。\n1. 閘門帶 `--changed` 已經跑過網頁八回合（`.local/wave_gate/<head8>/web/report.txt`），不重跑：看 real（有就是 blocker）、`missing_must_reach` 空（含新加的 `patch_pop` 與收回來的 `call_close`、`call_act`）。\n2. 用 head 的工具：`python scripts/sb/covers_measure.py --help` 不必跑量；`python scripts/same_behavior.py pick --covers jieyi`、`mail`、`terms` 各印軌數與名單（各至少一軌、含新軌）；`python -m pytest tests/core/test_same_behavior_covers.py -q` 沒有「沒有一軌走到的包」警告；`python scripts/same_behavior.py selftest --tracks <三個新軌> --base <head 解出來的夾>`（`MUTANT_PROFILE` 那一種設定）：跑兩次一樣、改一個字抓得到；量分鐘數。\n3. nightly：在暫存 out 夾造一份前一次綠的 `<日期>.json`（照開發 README 寫的格式），用判斷函式或 `--dry-run`（開發怎麼做就怎麼叫）對同一個 SHA 跑一次，印「沿用」；改一個 `tests/` 檔名進假 diff 要印「要跑」。**不要真跑整套。**\n4. 收之前 `grep` 兩台伺服器的 log 有沒有 `ImportError`、`ModuleNotFoundError`、`AttributeError`，有就是 blocker。\n**不修工具、不修程式，整關不超過 60 分鐘**，到了就交，沒走到的寫清楚。"


WAVES["S"] = dict(
    round2=True,
    extra_lenses=[
        dict(key="proof", text="**工具改了，證明力不能掉**。第 113 批。第 2 項：三個新軌真的走到包開著的主流程（看輸出段落，不是只有 404），開關在情境裡開、不改設定檔，selftest 改字抓得到；第 1 項：covers 是 `covers_measure` 量出來寫的（抽兩軌對 `analyze` 的輸出）、反向驗三對一邊紅一邊不紅、ALWAYS 不變量沒破；第 3 項：`patch_pop` 與 `call_close`、`call_act` 在不帶 `--quick` 的八回合裡真的到了而且**連跑兩趟**都到，`zh_write` 的 noise 規則窄到只對那一景、有測試；第 4 項：沿用的判斷有五種情形的單元測試、`tests/` 變了一定跑、超過 7 天一定跑、前一次紅一定跑，`latest.txt` 寫得出「沿用」。**全程只讀 repo，實驗在暫存複本做。**"),
    ],
    lines=[dict(name="測試工具", batches=[b113])],
    merge_port=8411, fix_port=8412,
    web_check=dict(ports="8413、8414", steps=WEB_S),
)


# ── T 波：客服自動受理（客服官）215～218（企劃者 2026-11-10「照計畫繼續」）──
T_DESIGN = "docs/superpowers/specs/2026-11-09-客服自動受理-design.md"
T_PLAN = "docs/superpowers/plans/2026-11-10-客服自動受理-計畫.md"
T_NOTE = [
    "- **客服自動受理這一波**：規格是設計 `" + T_DESIGN + "`（企劃者 11/10「照計畫繼續」），做法、介面、測試名與不做的照 `" + T_PLAN + "` 這一批那一節（**計畫跟設計稿對不上時照計畫**，計畫開頭「跟設計稿對不上的」列了四條）。上面「計畫不超過 120 行」照舊，寫在 `plan` 那個路徑。這一批**不做**計畫裡別批的事，碰到了寫 leftovers。四批是同一條鏈（後一批從前一批的 head 開）：前一批做好的介面照計畫的 Interfaces 用、不重做；對不上以程式為準並寫進 decided。",
    "- **畫面照 `docs/superpowers/specs/2026-11-09-介面設計規範.md`**（Joy 11/09）：只用 `web/style.css` 的 `:root` 色票、44px、第五節的元件先挑；給人看截圖前照第八節自己驗（375 淺、375 深、1280）。設計 5.6 的對比圖：程式只做計畫寫的 A 版，B、C 兩版用暫時改 css 拍完就還原（不提交），截圖存計畫寫的暫存夾、路徑寫進回報；**不等企劃者挑才做**。只動 `web/support.js`、`web/support.css`，`app.js`、`main.js`、`admin.js`、`index.html` 不碰。",
    "- **各包 README 自己填**；`docs/guide`、手冊、`CLAUDE.md` 不動，句子放回報的 docs。新字每一句旁 `待 joy 潤`，`new_strings` 逐句列。token、webhook、Discord ID 只在 `.local/support.json`，測試自己造暫存的金鑰檔（`support_kit.support_isolated` 已把 `LOCAL_DIR` 指到暫存夾）；回報與 commit 裡不出現任何真的 token。",
]


def tb(n, title, dev, ports, body):
    plan = f"docs/superpowers/plans/2026-11-10-客服自動受理-第{n}批.md"
    return batch(n, f"客服自動受理第 {n} 批：{title}", "support", dev, plan, ports, body + T_NOTE, custom=True)


def b215():
    return tb(215, "客服四：截圖（上傳、看圖、files 表、資料夾、備份還原、三句拒絕的字；畫面①③）", "dev/support-4", "8415", [
        "- 範圍照計畫第 215 批那一節（九個 task 逐個做、測試名照計畫）：`tuning/support.py` 加 `files_max` 3、`file_bytes_max` 3,000,000；`rules.image_kind`（只看檔頭：PNG、JPEG、WebP）與 `CONTENT_TYPES`、三句字；旁檔 `files` 表（`CREATE TABLE IF NOT EXISTS`，欄位照計畫）、`store.files_dir`、`add_file`（`BEGIN IMMEDIATE` 裡查主人、沒結、`< files_max`，seq 從 1）、`files`；`POST /api/support/file?id=<單號>`（內文就是位元組：async 處理函式先 `_gate_off`、再 `shell._account(request)` 認登入，然後 `async for chunk in request.stream()` **串流累計**，超過 `file_bytes_max` 立刻停止讀、拒絕；`Content-Length` 說超過的提早拒、說不超過的不信）與 `GET /api/support/file/{tid}/{seq}`（主人、客服名單上的人〔照 `_staff` 的條件〕，其他人與不存在 404 同一句；`Content-Type` 照檔頭、`Content-Disposition: inline`）；檔落地 `<db stem>-support-files/<單號>/<seq>.<png|jpg|webp>`：**先寫 `.upload-<uuid>.part`，再在 `add_file` 的交易裡算 seq、INSERT、`os.replace`**，replace 失敗 rollback；有列無檔看圖回 404 不 500；看圖路由先試主人、再試客服（第 216 批起也認 Bearer），其餘一律 `HTTPException(404, rules.NOT_FOUND)`；`_player_ticket`、`_staff_ticket` 多 `files`、`_queue` 多 `file_count`；`shell_tables.NO_LOGIN_ROUTES` 加這兩條（理由照 support 既有那幾列「關著 404、連登入都不問」——**計畫開頭第 1 條**：設計第八節寫「不進名單」是錯的，照程式）；`support_kit.ROUTES` 加看圖那一條、上傳那一條放新的 `RAW_POSTS`（現行 gate 測試對每條 POST 送壞 JSON 預期 422，上傳不解 JSON）；`backup_db.py`／`restore_db.py` 連 `<db stem>-support-files/` 一起備份、還原、輪替（`SIDE_DIRS`），主機端操作文件加一句。",
        "- 畫面：`supportNewHtml` 的表單多截圖那一格（file input 收三種格式、縮圖列、第 4 張不收、單張超過 3 MB 當場擋）；`supportForm` 先送單再**逐張** `POST /api/support/file?id=…`（一張失敗就停、單留著、訊息寫哪一張沒傳上）；`supportTicketHtml` 內文下面一列縮圖（連到看圖路由、新分頁 `rel=\"noopener\"`，`loading=\"lazy\"`）、沒結且不滿 3 張多一個補圖表單（一次一張）；`supportDeskTicketHtml` 同一列縮圖。樣式只寫 `web/support.css`（`.sup-` 前綴）。node 測試照計畫 task 6。",
        "- 測試先紅後綠，名字照計畫：`test_support_files.py`（新）九條、`test_support_web.py` 加四條、備份測試加一條（找 `test_backup_and_restore_carry_side_files` 所在的檔）。**Review Focus 1、2 那三條測試一定要有**（`test_file_too_big_is_refused_by_real_size`：假 `Content-Length: 1` 加 17 位元組對 `file_bytes_max=16`；`test_oversized_upload_stops_reading_early`：產生器內文第 3 塊會 raise、沒被讀到；`test_kind_is_by_magic_bytes_only`：`MZ` 檔頭加 `image/png` 被拒、PNG 檔頭加 `text/plain` 收）。",
        "- 對比圖①③照計畫 task 7 拍六張存 `C:\\Users\\ray61\\AppData\\Local\\Temp\\claude\\81800b313c89d0f8\\ade93b70-b3b7-42db-a8af-21f7a7cbdb16\\scratchpad\\waveT\\b215\\shots\\`，檔名寫 A／B／C 與寬度、淺深。",
        "- **不做**：壓縮、縮圖、EXIF、回覆表單附圖、客服官（216）。退版：換回第 214 批 `files` 表沒人讀、資料夾留著、新路由不在；資料庫第 9 版不動；季中能換。",
    ])


def b216():
    return tb(216, "客服五：客服官的 token 身分、自動回覆標示、「找真人」、自動結單（sweep）；畫面②", "dev/support-5", "8416", [
        "- 範圍照計畫第 216 批那一節（十個 task）。核心只動兩處：`tianxia/core/identity_base.py` 加 `SUPPORT_BOT_FILE = \"support.json\"`、`support_bot_file()`、`support_bot_token()`（只讀 `bot_token`、少於 32 字或檔壞一律 None、mtime 快取；`tests/core/test_identity_base.py` 加一條）；`tuning/support.py` 加 `bot_account` 空字串、`auto_close_days` 3。依據：設計第八節（企劃者 11/10「照計畫繼續」）。`core_changes` 逐條列、寫這一句原話與日期。",
        "- `staff.bot_account_id(config, db)`；`routes._staff(shell, request, *, allow_bot=True)`：有 `Authorization: Bearer` 就以它為準（`hmac.compare_digest` **兩邊都轉 bytes 再比**，非 ASCII 的 token 也要 404 不能 500；token 沒設、不對、`allow_bot=False`、`bot_account` 沒設或帳號不在 → 404 同一句；對了回 `by_id(bot_id)`、不看 cookie、不看 `staff_session_ok`）；`_lookup` 用 `allow_bot=False`。其他路由（`/api/do`、`/api/main`、`/api/me`、`/api/admin*`）Bearer 本來就不認——**契約測試** `test_bot_token_rejected_by_every_admin_api_and_the_shell` 照 `test_staff_rejected_by_every_admin_api` 的掃法用 Bearer 打一遍，全部不是 2xx；`test_bearer_wins_on_support_and_is_ignored_elsewhere`（Review Focus 3）。",
        "- `rules.SYSTEM_ACCOUNT = 0`、`reply_auto(reply, bot_id, relayed)`、`after_human`、字 `AUTO_CLOSED`（帶 `{days}`）；旁檔 `flags` 表（`id, ticket_id, kind, ref, created`；`human` 與 `relay`）；`store.add_human`（主人、沒結、冪等、`answered → open`）、`has_human`、`flags`；`staff_reply(..., relay_from=None)`（**`admin_flag` 改成設值：內部註記 1、否則 0**；`relay_from` 有值時同一筆交易多插一列 `flags(relay)` 與一則 `internal=1` 的「轉達自 <ID>」註記，**不經 `then='admin'`、`admin_flag` 不動**），`close` 也清 `admin_flag`；`store.sweep(now, max_age, body)`（`BEGIN IMMEDIATE` 裡重讀：只結 `answered` **且 `admin_flag = 0`** 且最後一則早於 `now - max_age` 的單，插一則 `by_account_id=0, staff=1, seen=0, journaled=1` 的系統回覆、`admin_flag=0`；**Review Focus 4** `test_sweep_rechecks_inside_the_write_lock`）。路由 `POST /api/support/human {id}`（主人）、`POST /api/support/sweep`（客服或 token；旁檔不在回空）；`_player_ticket`／`_staff_ticket` 每則多 `auto`、單多 `human`，`_staff_ticket` 與 `_queue` 多 `last_by`（值 `player`／`staff`／`desk`／`system`／null，**不用 `bot` 這個字**；`store.queue_extras` 一次查齊）、`_staff_ticket` 每則多 `system`；`answer` 在 token 身分收 `relay_from`（cookie 身分忽略）。`_staff` 怎麼告訴 `_answer` 這次是 token 身分（`request.state` 或回兩個值）寫進 decided。`NO_LOGIN_ROUTES` 加 `human`、`sweep`；`support_kit.ROUTES` 加兩條。推播照舊只在 `answer`，`sweep` 不推。",
        "- 畫面：`supportTicketHtml` 的署名（`auto` → 「客服（自動回覆）・回覆」）、「找真人」鈕（`data-act=\"support-human\"`：單沒結、有 `auto` 回覆、`!human` 才畫；按了打 `POST /api/support/human` 重畫）、`human` 的籤「已請真人處理」；`supportDeskTicketHtml` 的「客服官・自動回覆」（`system` 那一則標「系統」）與籤；清單列籤；`supportDeskReload` 先 `POST /api/support/sweep`（失敗不擋）再 `GET queue`。node 測試照計畫 task 8。對比圖②三版照 task 9 存 `…\\scratchpad\\waveT\\b216\\shots\\`，程式只做 A。",
        "- 測試名照計畫 task 1～7（`test_support_bot.py`、`test_support_flags.py` 新；`test_support_staff.py` 裡 `admin_flag` 的斷言改成「回覆就清」；另加 `test_support_json_never_contains_bot_word`、sweep 那條多「answered 但 `admin_flag=1` 的 10 天不結」）。`new_strings` 列計畫 task 10 那六句加「系統」。",
        "- **不做**：橋、CLI、Discord（217）；真人客服頁的轉達鈕；客服官的動作上限（伺服器既有的就是上限）。退版：換回第 215 批 token 路 404、`flags` 沒人讀、`auto` 看不出來、`admin_flag` 又只設不清；資料庫第 9 版不動；季中能換；緊急開關拿掉 `.local/support.json` 的 `bot_token`。",
    ])


def b217():
    return tb(217, "橋 scripts/support_bridge.py 與客服官的手 scripts/support_cli.py", "dev/support-bridge", "8417", [
        "- 範圍照計畫第 217 批那一節（四個 task）。兩支都**不 import `tianxia`**：橋照 `scripts/monitor.py` 的做法唯讀開旁檔（`sqlite3.connect(\"file:\" + path + \"?mode=ro\", uri=True)`；旁檔與圖的資料夾照 `<db stem>-support.sqlite`、`<db stem>-support-files/` 自己算），CLI 只打 HTTP（`requests`）。參數、子命令、純函式的名字與簽名照計畫的 Interfaces（`scan`、`render`、`post`、`advance`、`log_line`；CLI `main(argv, session=None)`，`session` 只用 `.request(method, url, headers=, json=)`、注入 `TestClient` 時 `--url http://testserver` 且是沒有 cookie 的新 client）。**預設路徑一律以腳本所在的 repo 根算**（兩支都從 `C:\\Ray\\tianxia-support\\` 啟動）。",
        "- 橋：每 15 秒掃 `tickets`、`replies`（只看 `staff = 0`）、`flags`（`human`）、`files`；進度 `.local/support_bridge.json` **逐張記**（`new` 是貼過的單號集合，`reply`、`flag`、`file` 是最大 id；單 12 還在等 60 秒、單 13 先貼，12 之後照樣貼）；新單等 60 秒或已有一張圖才貼，之後到的圖當補貼（`FILE`，只對貼過 `NEW` 的單）；貼 `discord_webhook`（multipart、圖一起，`payload_json` 一律帶 `allowed_mentions`：一般 `{\"parse\": []}`、`HUMAN` 只列 `mention` 兩個 ID）；**不貼 `login`、Email、手機**；`--log` 檔只有四種行（`NEW 12`、`REPLY 12`、`HUMAN 12`、`FILE 12`），`ALIVE` 每 300 秒印到 stdout 不進 log；沒有 `discord_webhook` 等同 `--dry-run`、進度照前進；貼失敗（逾時、429、5xx、`database is locked`）這一輪不前進、下一輪再試，連續 10 輪印警告不停（**Review Focus 5** `test_bridge_retries_without_advancing_state`），400／401／403／404 印警告並前進；`--once`、`--dry-run`。",
        "- CLI：`queue`（先 `POST sweep` 再 `GET queue`；標籤 `請管理者`／`等真人`／`等玩家`／`待客服官` 照計畫的順序判）、`ticket <n>`（單、每一則誰回的、帳號卡、圖存 `--inbox\\<n>\\<seq>.<ext>` 印路徑）、`answer <n> [--close] [--human <ID>]`、`note <n>`（**回覆與註記的字從 stdin 讀，沒有 `--file`**——客服官沒有寫檔權限；stdin 空的不送）、`close <n>`；**鎖定模式** `TIANXIA_SUPPORT_LOCKED=1` 時 `--config`、`--url`、`--inbox` 只從環境變數讀、命令列帶了一律拒絕結束碼 2；伺服器拒絕的句子原樣印結束碼 1、token 沒設或 404 印那一句結束碼 2；**永遠不印 token、不印 `bot`**。",
        "- 測試照計畫 task 1～3 的名字（含 `test_bridge_does_not_skip_a_ticket_still_in_grace`、`test_bridge_payload_never_lets_the_player_mention_anyone`、`test_bridge_skips_a_dead_webhook_reply`、`test_bridge_without_webhook_logs_only_and_advances`、`test_cli_locked_mode_refuses_path_flags`、`test_bridge_and_cli_do_not_import_tianxia`），放 `tianxia/features/support/tests/test_support_bridge.py`、`test_support_cli.py`（用 `support_kit` 開著的伺服器造真的旁檔與單；CLI 注入 `TestClient`）；所有輸出過 `tests/bots/test_server_bots.py` 的 `leaks()`。README 加「主機端」一節（兩支怎麼開、`.local/support.json` 的四個鍵，值不寫）；主機端操作文件加橋怎麼開、停。",
        "- **不做**：客服官 session、FAQ（218）；伺服器貼 Discord；橋寫旁檔。退版：兩支腳本刪掉就沒了，遊戲不受影響。",
    ])


def b218():
    return tb(218, "客服官 session 的範本與 init、知識匯出、FAQ 初稿、排練清單（本機那一半）", "dev/support-desk", "8418", [
        "- 範圍照計畫第 218 批那一節（五個 task）。範本進版控 `docs/support/session/`（`CLAUDE.md`：設計 6.3 的七條規矩逐條寫、頻道 ID 與白名單 ID 留 `<填>`；`settings.local.json`：`enabledPlugins` 同 `C:\\Ray\\tianxia-liaison\\.claude\\settings.local.json`，`permissions.allow` 只放 Discord 外掛的 `reply`、`cli.cmd` 的 Bash 規則、工作夾內的 Read、盯 `bridge.log` 的 Monitor 那一條；**沒有** `download_attachment`（截圖從遊戲經 CLI 來）、**沒有** `dangerously`、沒有 Edit、Write。**規則的寫法要實跑驗**：暫存夾放這份 settings，用 `claude -p` 各跑「`cli.cmd queue`」（要跑得了）、「`cli.cmd queue & dir`」與「`cli.cmd queue; dir`」（要被擋）、「讀工作夾的檔」（要讀得了）、「讀專案的 CLAUDE.md」「寫一個檔」（要被擋），結果與最後的規則字串寫進 decided；跑不起來就照 settings 文件寫、標「沒實跑」。`CLAUDE.md` 七條之外再加：醒來先 `cli.cmd queue`、每做完一張在 `#客服` 貼 `#單號・做了什麼`、要管理者時貼兩個 `<@ID>`、回覆用 `cli.cmd answer <n> <<'EOF' … EOF` 從 stdin 進。`start.cmd`：照聯絡官抄 bun 的 PATH 與 `cd /d`、`chcp 65001`、`DISCORD_STATE_DIR=%USERPROFILE%\\.claude\\channels\\discord-support`、用 `powershell -NoProfile -Command \"Start-Process …\"` 分離啟動橋（`--log %~dp0bridge.log`，stdout 導到 `bridge-out.log`、PID 記 `bridge.pid`）、再開 `claude --channels plugin:discord@claude-plugins-official`；另一支 `stop.cmd`。`cli.cmd`：`chcp 65001`、設 `TIANXIA_SUPPORT_LOCKED=1` 與 `TIANXIA_SUPPORT_CONFIG`／`URL`／`INBOX` 三個環境變數、參數含 `& | < > ^` 任何一個就拒絕、再叫那份 clone 的 venv 跑 `scripts/support_cli.py %*`）；`scripts/support_session_init.py <工作夾>` 冪等抄過去（不蓋已存在的）；`scripts/support_knowledge.py <工作夾>` 匯出 `content/patch_notes.json` 複本、`Game.howto_text()` 成 `knowledge\\howto.md`（照 `scripts/sb/base.py` 開世界的做法，`TIANXIA_DB` 先設到暫存檔）、抄 `docs/support/FAQ.md`，輸出過 `leaks()`。",
        "- `docs/support/FAQ.md` 初稿：只寫玩家看得到的（登入與帳號、體力與行動、商城與元寶、換季、常見誤會），一問一答，不寫機率、戰況、假人；每條旁 `<!-- 待 joy 潤 -->`。`docs/superpowers/discord/客服官-設定.md`：照 `中間bot-設定.md` 的寫法列企劃者要自己做的五樣（設計第十一節）與 `.local/support.json` 的格式（值用 `<填>`）。",
        "- 排練 `docs/support/排練.md`：本機那一半這一批就走（開著 support 的測試伺服器、init 到暫存夾、knowledge、橋 `--once --dry-run` 看四種行、CLI 走一張帶圖的單、玩家看到「客服（自動回覆）」、找真人後 `queue` 標等真人），結果寫進回報；Discord 那一半列成清單留給 PM 與企劃者。",
        "- 測試照計畫 task 1、2 的名字（`test_support_session.py` 新：含 `test_session_claude_md_has_the_rules` 的十個關鍵詞、`test_cli_cmd_locks_paths_and_rejects_shell_metachars`）。**不做**：真的 Discord 排練；聯絡官的任何改動；`#beta-回報`。退版：都是文件與主機腳本。",
    ])


WEB_T = "**這一波一線四批：客服的截圖、客服官的 token 身分與自動回覆標示與找真人與自動結單、橋與 CLI、客服官 session 的範本（開關預設關；`web/support.js`、`support.css` 動了）**。用 head 的 `scripts/webqa/`，上面「照 tianxia-qa 並排截圖」照做。都不花 token：用 `Start-Process` 分離啟動、輸出導到檔，`docs/superpowers/pm-workflows/wait_file.py <檔> 570` 等，**不要前景跑**。不帶 `--ports`（各挑空埠，拒絕 7861）。\n1. **開關關著**：閘門帶 `--changed` 已經跑過網頁比對（`.local/wave_gate/<head8>/web/report.txt`），這一關不重跑，只看它有沒有 real（有就是 blocker）、`missing_must_reach` 空。\n2. **開關開著**（head 的設定覆寫檔把 `support.enabled` 打開，只開 head；`.local/support.json` 在 head 複本放一個 32 字以上的測試 token，`Config.support.bot_account` 指到你用 `scripts/set_password.py` 建的帳號；客服身分用 `TIANXIA_SUPPORT=<你建的另一個帳號>`）：實機走——玩家在設定抽屜寫一張單附 2 張截圖（PNG 與 JPEG）、看單看得到兩張縮圖、點開是圖；客服身分進 `/admin` 的客服頁看得到同兩張；用 `python scripts/support_cli.py --config <那份 json> queue`、`ticket <n>`（圖存到 inbox）、`answer <n>`（一句從 stdin 餵進去）：玩家那一側那一則署名「客服（自動回覆）」、按「找真人」後籤出現、CLI `queue` 標 `等真人`；`python scripts/support_bridge.py --once --dry-run --db <head 的 db> --config <json> --log <暫存>` 印出 `NEW`、`FILE`、`HUMAN` 幾行、不貼；用錯的 token 打 `GET /api/support/queue` 是 404、用對的 token 打 `/api/main` 不是 2xx；主控台 0 錯誤、沒有 `Refused to`；網路沒有 4xx／5xx（刻意的 401、404、400 除外）；375 淺、375 深、1280 各一張，存進回報。\n3. 看三處對比圖的截圖在不在暫存夾（`scratchpad\\waveT\\b215\\shots\\`、`b216\\shots\\`），列出檔名。\n4. 收之前 `grep` 兩台伺服器的 log 有沒有 `ImportError`、`ModuleNotFoundError`、`AttributeError`，有就是 blocker。\n**不修工具、不修程式，整關不超過 75 分鐘**，到了就交，沒走到的寫清楚。"

WAVES["T"] = dict(
    round2=True, feature=True, design=T_DESIGN, new_packages="identity,support,terms", new_existing=True,
    extra_lenses=[
        dict(key="feature", text="**新功能掛開關、關著一個字不變、開著照設計、看不出假人**。第 215～218 批（計畫 " + T_PLAN + "）。親自驗：①開關關著：四條新路由 404 先於登入與參數解析、`/api/me`、`/api/main`、設定抽屜與客服頁的 HTML 對 base 位元組一樣；`compare --new support --also-existing` 其餘一樣（閘門跑，你只看結果）。②token 的邊界：`test_bot_token_rejected_by_every_admin_api_and_the_shell` 真的掃到 `FEATURE_ADMIN_ACTIONS`、`PLAYER_ADMIN_ACTIONS`、每條 `/api/admin*`、`/api/main`、`/api/me`；token 打 `lookup` 404；Bearer 與 cookie 同時帶的那一條。③假人：帳號卡、CLI 輸出、橋的字、Discord 的字都過 `leaks()`；用假人名號打新路由回話同不存在的人。④上傳：量真的位元組不信 `Content-Length`、檔頭認種類、路徑只用伺服器算的 `seq`。⑤橋：不重貼、60 秒、失敗不前進、`render` 不含 `login`；CLI 不印 token。⑥客服官 session 範本的 `settings.local.json` 沒有 `dangerously`、沒有 Edit／Write，allow 規則寫法成立。⑦殼：`shell_tables.NO_LOGIN_ROUTES` 只多四條、理由照既有；`core_changes` 只在 `identity_base.py` 與 `tuning/support.py`；包沒有 import 別包；橋與 CLI 沒有 import `tianxia`。⑧新字每一句旁有 `待 joy 潤`。**全程只讀 repo，實驗在暫存複本做。**"),
    ],
    lines=[dict(name="客服官", batches=[b215, b216, b217, b218])],
    merge_port=8419, fix_port=8420,
    web_check=dict(ports="8421、8422", steps=WEB_T),
)


# ── U 波：客服自動受理第 219 批（企劃者 2026-11-10 下午看三處對比圖答「AAC」：只有「找真人」鈕改 C 版）──
U_NOTE = [T_NOTE[1], T_NOTE[2],
          "- **這一批只改畫面**：規格是企劃者 11/10 下午的選擇「AAC」（寫單附截圖 A、客服頁的截圖 A 就是現在的程式；自動回覆署名與「找真人」挑 C）；C 版長什麼樣看第 216 批拍的對比圖 `C:\\Users\\ray61\\AppData\\Local\\Temp\\claude\\81800b313c89d0f8\\ade93b70-b3b7-42db-a8af-21f7a7cbdb16\\scratchpad\\waveT\\b216\\shots\\b216-ticket-C-375-light.png`（與 `-375-dark`、`-1280`）：鈕在玩家看到的那一則自動回覆**框裡右下**。上面「計畫不超過 120 行」照舊、寫在 `plan` 那個路徑；這一批不做別的事，碰到了寫 leftovers。"]


def b219():
    plan = "docs/superpowers/plans/2026-11-10-客服自動受理-第219批.md"
    return batch(219, "客服自動受理第 219 批：「找真人」鈕改 C 版（放進自動回覆框裡右下；企劃者 11/10 挑的）；客服官不准結找真人的單；看圖加 nosniff", "support", "dev/support-6", plan, "8423", [
        "- **伺服器兩小處（T 波合併助手與審查留下的）**：①`tianxia/features/support/routes.py::_close`：`_staff` 之後，`request.state.support_desk` 為真而且 `sidecar.has_human(tid)` 為真 → `raise shell.GameError(rules.HUMAN_WAITING)`、什麼都不寫（跟 T 波合併時加在 `_answer` 的擋同一句、同一個條件；cookie 的真人客服照舊；單不存在照舊 404）；測試加在 `tianxia/features/support/tests/test_support_bot.py`：`test_bot_cannot_close_a_ticket_waiting_for_a_human`（token 身分 close 回 400 加那一句、單還是沒結；cookie 客服 close 200；沒按找真人的單 token close 照舊 200）。②`_view_file` 回的 `Response` 加標頭 `X-Content-Type-Options: nosniff`（`test_support_files.py` 加一條 `test_file_response_says_nosniff`，順便斷 `Content-Disposition: inline` 還在）。這兩處不改 API 的長相、不加給玩家看的字、不動 `NO_LOGIN_ROUTES`、不動 rules／store／staff。",
        "- 畫面：只動 `web/support.js` 與 `web/support.css`。現況（A 版，第 216 批）：`supportAskHtml(t)`（`web/support.js` 第 147～149 行）把 `<div class=\"sup-ask-row\"><button class=\"btn small ghost sup-ask\" data-act=\"support-human\" data-id=…>找真人</button></div>` 畫在對話最下面、回覆表單上方（`supportTicketHtml` 第 162 行 `${msgs.join(\"\")}${supportAskHtml(t)}${form}`）；css 第 74～75 行 `.sup-ask-row`、`.btn.small.sup-ask`。改成 C 版：鈕畫在玩家看到的**最後一則自動回覆**（`auto` 為真、`internal` 不是）那一則的框裡右下角——鈕的 DOM 父層是那一則的框（讀 `supportTicketHtml` 裡每一則的畫法，找出框的 class 再決定插在哪），框的內距留夠、鈕不蓋到字；畫的條件一個字不變（單沒結、有自動回覆、`!t.human`），`data-act=\"support-human\"`、`data-id`、`registerClicks` 的清單、點了打 `POST /api/support/human` 重畫、按過換成 `sup-meta` 裡的「已請真人處理」籤都照舊。鈕 44px（`.btn.small.sup-ask` 那一條留著或改名，量過三個寬度都是 44）。對話最下面那一列 `.sup-ask-row` 拿掉（沒有別人用才拿；grep 一次）。",
        "- 測試先紅後綠：`tianxia/features/support/tests/test_support_web.py` 現有「找真人」那幾條照字面改（鈕的父層是最後一則自動回覆的框、不在對話尾巴；沒有自動回覆或按過就沒有鈕；點擊清單不變），新加一條 `test_ask_human_button_sits_inside_the_last_auto_reply`。`tests/bots/test_server_bots.py`、`tests/core/test_shell_stays_thin.py`、`tests/web/test_shell_web.py` 照 `scripts/test_for.py` 挑的跑。**沒有新字**（鈕的字「找真人」照舊；`HUMAN_WAITING` 是 T 波合併時加的、重用；`new_strings` 寫沒有）。`same_behavior` 自己不跑（動到 `routes.py`，閘門會照 `covers` 挑 support 的軌加網頁回合）；`scripts/test_for.py` 挑的（包的測試、`test_action_tables`、`test_outlock`、`test_server_bots`、`test_shell_stays_thin`）全綠。",
        "- 拍圖：暫存資料庫起 8423、客服開著、模型網址 127.0.0.1:9，造一張有自動回覆的單（照第 216 批拍圖的做法：`.local` 指到暫存夾、金鑰檔自造 40 字假 token、用 token 身分回一則），拍玩家看單 375 淺、375 深、1280 三張加按過之後 375 淺一張，存 `C:\\Users\\ray61\\AppData\\Local\\Temp\\claude\\81800b313c89d0f8\\ade93b70-b3b7-42db-a8af-21f7a7cbdb16\\scratchpad\\waveU\\b219\\shots\\`；照介面規範第八節自驗（沒有橫向捲動、44px、色票），跟第 216 批的 C 版對比圖對一眼、差在哪寫進回報。拍完 `taskkill /T`、刪暫存。",
        "- **不做**：寫單附截圖、客服頁的截圖（企劃者挑 A，就是現在的）；`routes.py` 只動 `_close`、`_view_file` 那兩處，rules、store、staff、橋、CLI、範本不動；前端 3 張、3 MB 跟設定走（留下）；`app.js`、`main.js`、`style.css`、`index.html` 不碰。退版：`web/` 兩個檔退回就是 A 版；`routes.py` 兩處退回就是 T 波的行為（客服官能結找真人的單、看圖沒 nosniff）；資料庫第 9 版不動、沒有新欄位、沒有新表、季中能換；緊急開關照舊 `Config.support.enabled`。",
    ] + U_NOTE, custom=True)


WEB_U = "**這一波只有一批、只動 `web/support.js`、`web/support.css`：「找真人」鈕搬進最後一則自動回覆的框裡右下（企劃者挑的 C 版）**。用 head 的 `scripts/webqa/`，上面「照 tianxia-qa 並排截圖」照做。都不花 token：用 `Start-Process` 分離啟動、輸出導到檔，`docs/superpowers/pm-workflows/wait_file.py <檔> 570` 等，**不要前景跑**。不帶 `--ports`（各挑空埠，拒絕 7861）。\n1. **開關關著**：閘門帶 `--changed` 已經跑過網頁比對（`.local/wave_gate/<head8>/web/report.txt`），這一關不重跑，只看它有沒有 real（有就是 blocker）、`missing_must_reach` 空。\n2. **開關開著**（base 與 head 的設定覆寫檔都把 `support.enabled` 打開；`.local/support.json` 兩邊都放同一個 32 字以上的測試 token、`support.bot_account` 指到同一個帳號；兩邊同樣的步驟：玩家送一張單、用 token 身分 `POST /api/support/answer` 回一則 `then=wait`、玩家點開那張單）：並排截 375 淺、375 深、1280——**唯一該有的差**是「找真人」鈕的位置（base 在對話最下面一列、head 在最後一則自動回覆框裡右下）；鈕的字、44px、籤、其他每一個像素都要一樣；按下去兩邊都要變成「已請真人處理」、鈕消失。主控台 0 錯誤、網路沒有 4xx／5xx。差在別處就是 blocker。"

WAVES["U"] = dict(
    round2=True, feature=True, design=T_DESIGN, new_packages="support", new_existing=True,
    extra_lenses=[
        dict(key="feature", text="**一小批：開關關著一個字不變、開著只差鈕的位置加兩處伺服器的擋**。第 219 批（計畫 docs/superpowers/plans/2026-11-10-客服自動受理-第219批.md）。親自驗：①`git diff <base>..<head> --stat` 只有 `web/support.js`、`web/support.css`、`tianxia/features/support/routes.py`（只有 `_close` 與 `_view_file`）、`tianxia/features/support/tests/test_support_web.py`、`test_support_bot.py`、`test_support_files.py`、計畫檔與 README；`_close` 的擋條件跟 `_answer` 那一道一樣（`support_desk`、`has_human`）、cookie 客服不受影響；`_view_file` 多的只有 `X-Content-Type-Options: nosniff` 這一個標頭；②`supportAskHtml` 的三個條件（沒結、有自動回覆、沒按過）一個都沒掉、`data-act`／`data-id` 沒變、`registerClicks` 清單沒變；③鈕的父層真的是最後一則自動回覆的框（讀 DOM 字串或 node 測試的斷言），不是第一則、不是內部註記、不是玩家自己那一則；④`.btn.small.sup-ask` 還是 44px（讀 css）；⑤`web/support.js` 裡沒有 `bot`、`假人`、`機器人`（`tests/bots/test_server_bots.py` 的字表）；⑥沒有新字（`// 待 joy 潤` 的句子沒有新增）。"),
    ],
    lines=[dict(name="找真人鈕", batches=[b219])],
    merge_port=8424, fix_port=8425,
    web_check=dict(ports="8426、8427", steps=WEB_U),
)


def leftovers_for(path):
    """上一波每一批回報的 leftovers，有寫到批號的歸給那一批（一句可以歸給好幾批）。"""
    out = {}
    for line in json.loads(Path(path).read_text(encoding="utf-8")):
        for done in line["done"]:
            for text in done.get("leftovers") or []:
                numbers = set()
                for m in re.finditer(r"(?:第\s*|[Bb]atch(?:es)?\s+)(\d+(?:\s*[、/，,和與及]\s*\d+)*)", text):
                    numbers |= {int(x) for x in re.findall(r"\d+", m.group(1))}
                for n in numbers:
                    out.setdefault(n, [])
                    if text not in out[n]:
                        out[n].append(text)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("wave")
    ap.add_argument("base")
    ap.add_argument("out")
    ap.add_argument("--scratch", default=r"C:\Users\ray61\AppData\Local\Temp\claude\81800b313c89d0f8\ade93b70-b3b7-42db-a8af-21f7a7cbdb16\scratchpad")
    ap.add_argument("--finish", default="", help="開發回來的 built（JSON 檔）；有給就只合併、閘門、審查、修正")
    ap.add_argument("--merge-base", default="")
    ap.add_argument("--merge-extra", default="", help="合併時要多合的東西（文字檔）")
    ap.add_argument("--gate-base", default="", help="閘門比對的基準；合併時又合了 develop、main 就給它們合起來那一筆")
    ap.add_argument("--after-merge", default="", help="合完、閘門之前的文件輪（文字檔）")
    ap.add_argument("--merged-head", default="", help="合併已經做完（下一波已從這一筆開工）：收尾不再合")
    ap.add_argument("--stop-after-merge", action="store_true", help="只合併就回來，閘門之後另外叫（企劃者 11/07：波與波疊著跑）")
    ap.add_argument("--docs-alongside", action="store_true", help="文件輪只動文件，跟閘門同時跑")
    ap.add_argument("--opus", action="store_true", help="每一批都用 Opus（沒有逐批審查時比較保險）")
    ap.add_argument("--leftovers", default="", help="上一波開發回來的 built（JSON 檔）：寫到某一批的 leftovers 接進那一批的派工")
    a = ap.parse_args()
    w = WAVES[a.wave]
    args = {"wave": a.wave, "scratch": a.scratch, "branch": f"wave/{a.wave}", "merge_port": w["merge_port"], "fix_port": w["fix_port"]}
    if w.get("round2"):
        args["round2"] = True
        args["master"] = R2
    if w.get("feature"):
        args["feature"] = True
        args["design"] = w["design"]
    if w.get("new_packages"):
        args["new_packages"] = w["new_packages"]
    if w.get("new_existing"):
        args["new_existing"] = True
    if a.finish:
        args["built"] = json.loads(Path(a.finish).read_text(encoding="utf-8"))
        args["merge_base"] = a.merge_base
        if w.get("web_check"):
            args["web_check"] = w["web_check"]
        if w.get("extra_lenses"):
            args["extra_lenses"] = w["extra_lenses"]
        if a.merge_extra:
            args["merge_extra"] = Path(a.merge_extra).read_text(encoding="utf-8")
        if a.gate_base:
            args["gate_base"] = a.gate_base
        if a.after_merge:
            args["after_merge"] = Path(a.after_merge).read_text(encoding="utf-8")
        if a.merged_head:
            args["merged_head"] = a.merged_head
        if a.stop_after_merge:
            args["stop_after_merge"] = True
        if a.docs_alongside:
            args["docs_alongside"] = True
        name = f"wave-{a.wave}-merge.js" if a.stop_after_merge else f"wave-{a.wave}-finish.js"
    else:
        args["stop_after_build"] = True
        args["lines"] = [dict(name=l["name"], base=a.base, batches=[f() for f in l["batches"]]) for l in w["lines"]]
        left = leftovers_for(a.leftovers) if a.leftovers else {}
        if a.opus:
            for line in args["lines"]:
                for b in line["batches"]:
                    b.pop("model", None)
        for line in args["lines"]:
            for b in line["batches"]:
                if left.get(b["n"]):
                    b["body"] += "\n- **上一波的開發留給這一批的**（他們的話，照現行程式核對，對不上以程式為準）：\n" + "\n".join("  - " + x for x in left[b["n"]])
        name = f"wave-{a.wave}.js"
    meta_end = SRC.index("}\n", SRC.index("export const meta")) + 2
    body = re.sub(r"\bargs\b", "ARGS", SRC[meta_end:])
    text = SRC[:meta_end] + "\nconst ARGS = " + json.dumps(args, ensure_ascii=False) + "\n" + body
    (Path(a.out) / name).write_text(text, encoding="utf-8", newline="\n")
    print("wrote", Path(a.out) / name, len(text))


if __name__ == "__main__":
    main()
