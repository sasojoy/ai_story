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


# ── V 波：測試去重 A 批 220～222（企劃者 2026-11-10 夜：「全做，含刪那 20 條」；閘門 8 個 worker、每日 4；B 批等 A 批量到數字）──
V_SURVEY = "docs/superpowers/plans/2026-11-10-測試去重-盤點.md"
V_NOTE = [
    "- **測試去重 A 批這一波**：範圍照盤點 `" + V_SURVEY + "` 第三、四節（A 批）這一批列的項目，每一項的證據（引用的斷言、蓋住它的那一條）都在盤點裡，動手前先打開那兩條再動。上面「計畫不超過 120 行」照舊，計畫寫在 `plan` 那個路徑。**不動 `tianxia/`、`web/`、`content/`、`server.py`、`scripts/`**，只改測試與 `tests/kit/`；不改任何斷言的意思（刪與併只照清單）；清單外的測試一條都不刪、不併。",
    "- **PM 已經改好、波末一起合的**：`dev/test-fixtures-pm`（`1302241f1`）改了 `tests/conftest.py`（每條測試從建好表的模板抄一份資料庫、複製內容時關 GC）與 `tests/server/test_backup_db.py` 一句；**這三批都不碰這兩個檔**，碰到要改寫進 leftovers。",
    "- **每一項量秒數**：改前改後各量一次（`.venv/Scripts/python.exe -m pytest --durations=0 -p no:xdist <檔>::<條>` 或整檔），寫進回報的 `decided`（表：項目、改前、改後）；刪的每一條寫「刪了哪條、蓋住它的是哪一檔哪一行」。各包 README、`docs/guide`、手冊、`CLAUDE.md` 不動，句子放回報的 `docs`。",
]


def vb(n, title, dev, ports, body):
    plan = f"docs/superpowers/plans/2026-11-10-測試去重-第{n}批.md"
    return batch(n, f"測試去重第 {n} 批：{title}", "core_shared", dev, plan, ports, body + V_NOTE, custom=True)


def b220():
    return vb(220, "網頁 harness 不再白等 app.js 的長計時器（toast 3200 ms、慢提示 12000 ms、佇列 2000 ms）；量過之後拿掉只因為等計時器才標的 slow", "dev/test-harness-220", "8428", [
        "- 範圍：盤點 3.1。**只改 `tests/kit/webharness.py` 常駐 node 的 SERVER 字串**（第 120～270 行那一段 JS）：`track()` 記下每個計時器的延遲，等待迴圈判斷「還在等」時不算延遲 ≥1000 ms 的 `setTimeout`（照排、請求結束照清；`setInterval` 與短計時器照舊）。`TIANXIA_WEB_HARNESS=process`（每請求各開一個真 node）那條路不改，寫進 decided。三位查案各自找到同一件事（webA W1、webB WB-01、artsgear ARM-1），做法照 W1。",
        "- **動手前先 grep** 全部驅動程式（`tests/**/*.py`、`tianxia/features/*/tests/*.py` 裡的 JS 字串）確認沒有測試靠 ≥1 秒的 app.js 計時器真的跑完才產生輸出或改變斷言（例：等 toast 消失、等 `busy()` 的慢提示出現、等 `watchQueue` 輪詢打到 `/api/queue`）；有就把門檻調到比那個計時器大，或在那條測試裡自己等，寫進回報。`tests/kit/jianghu_kit.py` 的 `T.ctx.setTimeout = () => 0` 留著。",
        "- **證明**：`tests/web/test_webharness.py` 加一條「長計時器不擋結束、短計時器照等」（排一個 50 ms 與一個 3000 ms 的計時器，50 ms 那個要跑到、程式在 3 秒前結束）；兩種模式（常駐、process）既有的條都過。先注入一處壞法（例：把門檻設成 0 讓短計時器也不等，那條新測試要紅）再還原，寫進回報。",
        "- **量**：改前改後各量這五條（`--durations=0 -p no:xdist`）：`tests/web/test_prologue_web.py::test_fb095_after_a_redraw_the_busy_mark_lands_on_the_button_on_the_page`（14.3 秒）、`tianxia/features/smithy/tests/test_shop_web.py::test_a_refused_forge_keeps_the_pot`（4.2）、`tianxia/features/outlets/tests/test_econ_web.py::test_a_greyed_cell_only_says_why`（3.6）、`tianxia/features/peers/tests/test_discuss.py::test_a_reply_after_the_card_was_closed_does_not_reopen_it`（3.3）、`tianxia/features/notify/tests/test_push_how_web.py::test_allowing_on_an_iphone_subscribes_and_ticks_the_box`（3.3）。",
        "- **slow 標記**：只因為等計時器才標 slow 的網頁測試（smithy `test_shop_web`、mall `test_mall_web`、seal `test_seal_acts_web` 約 18 條；自己 `grep -n \"mark.slow\"` 加旁註找）量到 <0.5 秒才拿掉標記與旁註，沒量到的留著；拿掉幾條、各幾秒寫進回報。",
        "- **全跑**：所有 import webharness 的測試檔含 slow（`grep -l webharness` 的清單，約 100 檔，`-n 4`）、`tests/web/test_webharness.py`、`tests/server/test_server.py`。**不做**：改 `web/app.js` 的 3200 ms；改任何驅動程式；動 `scripts/webqa/`（那是閘門的網頁比對，跟這個 harness 無關）。退版：只影響測試，退回就是照舊等 3.3 秒。",
    ])


def b221():
    return vb(221, "25 處沒走快取的 `load_content(正式內容)` 換成 `conftest.real_content()`；`test_set_password` 不再每條載正式內容；契約 options_carry 併進 choose；identity `_run()` 快取；刪週末設定那一條", "dev/test-cache-221", "8429", [
        "- 範圍：盤點 3.4 與 3.5 的一小部分。①全 repo 直接 `load_content(ROOT / \"content\")`／`load_content(CONTENT_DIR)`／`load_content(REAL_CONTENT)`（含帶 profile 的）換成 `conftest.real_content()`、`real_content(\"week7\")` 或 `classic_rules(real_content())`，**只換沒 patch 載入路徑的**（那條測試或它的 fixture 有 `monkeypatch`／`mock.patch` 到 `content`、`load_content`、`validate`、`_locate`、設定覆寫檔、`ADMINS_FILE` 的不換；要抄一份改檔再載入的不換）。起點清單：`tests/battle/test_followers_matter.py`、`tests/battle/test_team.py`（AB-03）、`tests/core/` 13 處（CORE-05、06、07：查案人在 `tests/core` 數到的）、`tests/arts/test_pr21_merge.py`、`tests/battle/test_trait_numbers.py`、`tests/bots/test_stamina*.py`、`tianxia/features/battle/tests/test_measure_battle.py`（4 處）；**`tests/season/test_real_content.py` 的 19 處歸第 222 批，不碰**；全 repo `grep -n \"load_content(\" tests tianxia/features/*/tests` 一次，每一處寫進回報（檔、行、換成什麼、或為什麼不能換）。",
        "- ②server S1：`tests/server/test_set_password.py` 七條各載一次正式內容（整檔 8.5 秒）：autouse fixture 或逐條 `monkeypatch.setattr(set_password, \"load_content\", lambda *a, **k: content)` 換成測試內容，只有 `test_a_character_it_creates_gets_the_same_profile_as_the_server` 不套（它要驗 week7／season21 真內容）；先確認 `set_password.py` 是從模組層的名字叫 `load_content`。",
        "- ③CORE-01：`tests/core/test_contract_features.py` 的 `test_options_carry_the_package_prefix` 三行斷言併進 `test_choose_takes_only_its_own_ids`（assert 訊息各帶標籤、保留 `[<包>]` 的 parametrize id），`tests/core/test_test_for.py` 那份逐包契約名單跟著改、`scripts/test_for.py` 若寫死這個名字也改（grep；`scripts/` 只准改這一個名字）。CORE-02（共用一個 game）**不做**，B 批。",
        "- ④WB-02：`tianxia/features/identity/tests/test_identity_web.py` 無參數的 `_run()` 加 `functools.cache`（有傳 path 的不快取），先確認各測試沒有改回傳的 dict。⑤AB-07：刪 `tests/bots/test_stamina_pill.py::test_the_weekend_profile_no_longer_refills_for_free`（週末設定 2026-10-31 第 14 批關門，`weekend` 起不來）。",
        "- **量**：每個改到的檔改前改後整檔秒數（`--durations=0 -p no:xdist`）寫進回報。**全跑**：改到的檔整檔含 slow、`scripts/test_for.py` 挑的（含 `tests/core/test_test_for.py`）。退版：只影響測試。",
    ])


def b222():
    return vb(222, "刪約 20 條確認重複的測試、slow 側六條縮短、`test_conquest_siege` 的整檔 autouse 拿掉與喊話句式縮例", "dev/test-prune-222", "8430", [
        "- 範圍：盤點 3.3 不用比對的六條、3.5 的刪除清單、AB-02、AB-04。**每一刪先打開蓋住它的那一條確認還在、斷言真的蓋住**，不在就不刪、寫進回報。這一批擁有 `tests/season/test_real_content.py`、`tests/acts/test_conquest_siege.py`、`tests/acts/test_conquest_flip.py`、`tests/season/test_sim_scripts.py`、`tests/bots/test_bot.py`、`tests/season/test_sim_season_one.py` 與下面點名的 identity、guide、admin、travel、arts 檔；第 220、221 批不碰這些檔。",
        "- slow 側：AB-01 刪 `tests/acts/test_conquest_flip.py::test_bots_never_press_it_off_own_ground`（18.5 秒；同檔與 sortie 包的假人測試蓋住）連同沒人用的 import。S1 `tests/season/test_sim_scripts.py` sanren（season_one 關）那條 argv 補 `--max-steps`、`300`（照同檔其他六支量表腳本的寫法；39.8 秒），斷言照舊、不併進第二條。S2 `tests/bots/test_bot.py` 第 973 行附近 `range(200)` 縮成 `range(5)`，斷言與 pick 呼叫的形式不變（17 秒）。S5 `tests/season/test_sim_season_one.py` 第一條 hours=8 改 6、第三條的邊界說明移到第一條 docstring、刪第三條（9 秒）。",
        "- `tests/season/test_real_content.py`：S7 `test_world_map_labels_never_collide_or_leave_the_canvas_at_the_start` 對 enemies 層的勝算算一次快取（`functools.cache` 或預先算一張表）再傳給 `render_map`（13.7 秒 → 應跟 routes 層差不多）；S10 迴圈內改成直接建 `GameState(player=PlayerState(name=\"\", location=c.scenario.start_location, stats={}, stamina=0), world=fresh_season(c))`、不再叫 `_real_s1()`（4 秒）；同檔 19 處 `load_content(CONTENT_DIR…)` 與 `_real_s1()`／`_announce()` 各自重載正式內容的，沒 patch 載入路徑的換成 `conftest.real_content(profile)` 複本（規矩同第 221 批第 ① 點），每一處寫進回報。",
        "- `tests/acts/test_conquest_siege.py`：AB-02 第 1663 行附近 `conquest_server` 的 `autouse=True` 拿掉（105 條都付、2 條要用；要用的兩條已收參數）；AB-04 NAMED 只留「一槍直取劫道響馬的咽喉」三種 build 各一例（共 3）、NOT_NAMED 只留「先斬響馬頭目」`_melee` 與 `_lone` 各一例（共 2），其餘句子由 `test_find_commander_takes_the_squad_name_and_the_full_name` 負責；NOT_NAMED 那條原有的 slow 標記留；`_single` 這個 build 維持原樣沒有 NOT_NAMED 端對端。",
        "- 刪除清單（3.5）：R-01 `tianxia/features/identity/tests/test_identity_admin_session.py` 的 `test_register_listed_login_needs_12`、`test_change_password_listed_needs_12`、`test_admin_reset_listed_needs_12`、`test_listed_short_password_still_logs_in`，與 `test_identity_password.py` 重複 12 字規則那一條（蓋住它們的是 `test_identity_strict_password.py`，第 209 批六條路一次）；R-02 `test_identity_gate_off.py::test_main_and_me_bytes_same_when_off`、`test_identity_admin.py::test_admin_tools_404_when_off`（後者是推論：非管理者已先 404；刪完跑 identity 全包）；R-03 `tianxia/features/guide/tests/test_enlist.py::test_acknowledging_the_enlistment_ending_closes_the_box`；R-04 `test_explain.py` 的 `test_the_full_stamina_note_shows_when_nearly_full_and_not_below`、`test_the_full_stamina_note_shows_when_nearly_full`（留 `test_the_full_stamina_note_says_why`）；S6 `tianxia/features/admin/tests/test_admin_routes.py::test_each_tool_lives_here_with_no_gate_and_stays_open_while_paused`（含 parametrize；`TOOLS` 常數別人還用、留）；S8 刪 `test_a_point_goes_into_lore_through_the_server`、在 `test_an_old_save_stored_without_lore_reads_as_five_through_the_server` 的 allocate 之後補 `assert r[\"main\"][\"status\"][\"stat_points\"] == 0`（檔用 grep 找）；S10 `tianxia/features/travel/tests/test_travel_routes.py::test_dashing_goes_through_the_same_door`；ARM-6 `test_practice_hardening.py`（grep 找檔）的 `test_a_hard_win_at_the_peak_can_break_through`、`test_a_missed_chance_leaves_a_soft_hint`（被 `test_cultivation.py` 逐句蓋住，其餘四條留）。",
        "- 併一條：R-07／S4 管理者路由拒絕玩家——`test_api_admin_refuses_a_player`、`test_api_admin_player_refuses_a_player`、`test_api_admin_accounts_refuses_a_player` 與 `test_each_tool_refuses_a_player[13 個 op]` 併成一條：開一個玩家後迴圈打三個路由與 13 個 `/api/do/<op>`，assert 訊息帶路由或 op；`reset_password` 那條有登入密碼的副作用，不併（檔在 `tests/server/` 或 admin 包，grep）。",
        "- **量**：AB-01、AB-02、AB-04、S1、S2、S5、S7、S10 改前改後秒數。**全跑**：改到的檔整檔含 slow（`test_sim_scripts`、`test_real_content` 含 slow 約 5 分）、identity 全包、`scripts/test_for.py` 挑的。**不做**：S3／ARM-4 bounties 併整季（要先比對，B 批）；突變併組（B 批）；`test_backup_db` 那條 33 秒的（交接留給下一個測試流程批，要先量時間花在哪）。退版：只影響測試。",
    ])


WEB_V = "**這一波沒動 `web/`，改的是測試與測試的 harness。這一關不比畫面**。都不花 token：用 `Start-Process` 分離啟動、輸出導到檔，`docs/superpowers/pm-workflows/wait_file.py <檔> 570` 等，**不要前景跑**。不帶 `--ports`（各挑空埠，拒絕 7861）。\n1. 閘門帶 `--changed` 的決定（`result.json` 的 `decision`）應該是只改測試、不比對、不走網頁回合；真的有跑就看 real（有就是 blocker）。\n2. 用 head 的 `tests/kit/webharness.py`：挑三條改前 3.3 秒的網頁測試（盤點 3.1 列的）各量一次 `--durations=0 -p no:xdist`，要掉到 0.5 秒以下；`tests/web/test_webharness.py` 兩種模式各跑一次全綠。\n3. 整套不含 slow 的 CPU 秒數（閘門 `suite.xml` 加總）跟 U 波閘門 `4f09702e` 的 1,356 秒比，寫進回報；`-n 8` 的牆鐘也寫（第一次用 8 個 worker 的閘門）。"

WAVES["V"] = dict(
    round2=True,
    extra_lenses=[
        dict(key="proof", text="**刪測試與改 harness，保護面不能掉**。第 220～222 批（盤點 " + V_SURVEY + " 第三、四節）。親自驗：①第 220 批：harness 的改動只在 `tests/kit/webharness.py` 的 SERVER 字串，門檻是延遲 ≥1000 ms 的 `setTimeout` 不等、仍照排照清，`setInterval` 與短的照舊；新加的 harness 測試兩種模式都在；拿掉的 slow 標記每一條都有量到的秒數（<0.5 秒）；沒有任何驅動程式被改。②第 221 批：每一處換成 `real_content()` 的都沒有 patch 載入路徑（對照回報的表逐處看那條測試與它的 fixture）；`test_set_password` 留下真內容那一條；契約併進去的三行斷言一行沒少、逐包 id 還在；`test_test_for.py` 的名單跟著改。③第 222 批：刪的每一條在回報寫了蓋住它的那一條哪一檔哪一行，打開看斷言真的蓋住（12 字密碼的六條路、identity 關著、guide 兩條、admin 工具、lore、travel、practice_hardening）；`test_conquest_siege` 的 NAMED／NOT_NAMED 縮例後三種 build 都還有一例；S1 只補參數沒改斷言；S2 只改 range；沒有清單外的刪除（`git diff --stat` 對清單）。④三批都沒碰 `tests/conftest.py`、`tests/server/test_backup_db.py`（PM 的分支 `dev/test-fixtures-pm` 波末合）、沒碰 `tianxia/`、`web/`、`content/`、`server.py`；第 221 批 `scripts/test_for.py` 只改契約名單那一個名字。⑤回報的 before／after 秒數表都在。"),
    ],
    lines=[dict(name="harness", batches=[b220]), dict(name="快取", batches=[b221]), dict(name="刪與縮", batches=[b222])],
    merge_port=8431, fix_port=8432,
    web_check=dict(ports="8433、8434", steps=WEB_V),
)


# ── W 波：測試去重 B 批 223～225（企劃者 2026-11-10 深夜看 A 批數字選「三項全做」）──
W_BRIEF = r"C:\Users\ray61\AppData\Local\Temp\claude\81800b313c89d0f8\ade93b70-b3b7-42db-a8af-21f7a7cbdb16\scratchpad\tq\b_batch_brief.md"
W_NOTE = [
    "- **測試去重 B 批這一波**：範圍照盤點 `" + V_SURVEY + "` 第三節 3.2～3.4 與這一批的派工單；每一筆候選的查案原文、證據、懷疑者的核對與改法在 `" + W_BRIEF + "`（只讀，派工單引用的 id 都在裡面），動手前先讀自己那幾筆。上面「計畫不超過 120 行」照舊，計畫寫在 `plan` 那個路徑。**不動 `tianxia/`、`web/`、`content/`、`server.py`、`scripts/`、`tests/conftest.py`、`tests/kit/`**，只改派工單點名的測試檔；不改任何斷言的意思（併是把同樣的斷言放在一起，不是放寬）；清單外的測試一條都不刪、不併。",
    "- **每一項量秒數**：改前改後各量一次（`.venv/Scripts/python.exe -m pytest --durations=0 -p no:xdist <檔>` 整檔，含 slow 的加 `-m \"slow or not slow\"`），寫進回報的 `decided`（表：檔、改前、改後、條數改前改後）。各包 README、`docs/guide`、手冊、`CLAUDE.md` 不動，句子放回報的 `docs`。V 波（A 批）11/10 深夜已進 develop：正式內容一律 `conftest.real_content(profile)`、harness 不等長計時器、預設資料庫從模板抄，寫新 fixture 照這些。",
]


def wb(n, title, dev, ports, body):
    plan = f"docs/superpowers/plans/2026-11-10-測試去重-第{n}批.md"
    return batch(n, f"測試去重第 {n} 批：{title}", "core_shared", dev, plan, ports, body + W_NOTE, custom=True)


def b223():
    return wb(223, "「改一個欄位、整份 validate(正式內容)、斷 ContentError」的突變測試併組：figures 與 military 九筆（MIL-01、FIG-04、FIG-01、FIG-03、MIL-02、MIL-03、MIL-05、MIL-04、FIG-05）", "dev/test-mutations-223", "8435", [
        "- 範圍：盤點 3.2 的九筆，照懷疑者「縮小」後的做法（brief 裡每一筆的「懷疑者改成」為準，查案人原本的做法只當背景）：MIL-01 `military/tests/test_opportunities_two.py` 38 組突變分組、FIG-04 `tests/figures/test_figures.py` 13 組分 3～4 組、FIG-01 `tests/figures/test_promotions_high.py` 只動兩處（free_text 五欄位併一條、event_mods 那一處）、FIG-03 `tests/figures/test_promotions_huang.py` 只併 donate_grain 兩條與 fs_fragments 一條（共 8 組）、MIL-02 `military/tests/test_rank_actions.py` 只併訊息彼此不同的約 2 組、MIL-03 與 MIL-05（brief 列的檔與條）、MIL-04 夜晨 35 組改成一條雙迴圈、FIG-05 faction×week 改成條內雙迴圈。每一筆的測試名、行號、要留哪些 parametrize id 都在 brief。這一批擁有 `tests/figures/*.py` 與 `tianxia/features/military/tests/*.py`，別批不碰。",
        "- **懷疑者定的規矩（照抄、逐條遵守）**：①`validate` 只丟前 20 筆錯（`content.py` 的 `errors[:20]`），一組最多約 8 個突變；②裸字串 `match`（`nowhere`、`nobody`、`ghost`、`13`、`fail`、`rank_actions`、`bad`）併組之前一律補成帶機緣／人物 id 與欄位的全句，同一組裡任何兩個 `match` 都不可以是對方的子字串；③正向「不丟錯」的 validate 不可併進會丟錯的組；④同一個欄位的突變分開放（會互踩）；⑤只有模組範圍 fixture 真的避開每條的 `real` 複本（50 ms）與 setup 才有省——每組套上突變後只 `validate` 一次、收下 `ContentError` 的訊息，原本的 parametrize 保留，每個 id 只對該組的訊息斷 `message in text`，紅的時候還看得出是哪一條。",
        "- **證明**：每一組併好之後做一次「少一個突變」的注入——把組裡任一個突變拿掉（或把它的 match 改成別的字），對應那個 id 的斷言要紅、別的 id 要綠；抽每一筆至少一組寫進回報（id、拿掉哪個、紅在哪一句）。`test_rank_four_needs_legs_too`（斷言不得多出別的錯誤）不在併的範圍。",
        "- **量**：`test_promotions_high.py`（改前 48 秒／161 條）、`test_promotions_huang.py`（22 秒／77 條）、`test_opportunities_two.py`（40 秒／126 條）、`test_figures.py`（16 秒／76 條）、`test_rank_actions.py`（20 秒／84 條）與 MIL-03、MIL-04、MIL-05、FIG-05 所在的檔，改前改後整檔秒數與條數（條數會因為 parametrize 保留而幾乎不變，省的是 validate 次數：改前改後各數一次 `validate(` 真的被叫幾次，用 monkeypatch 包一層計數寫進回報）。**全跑**：改到的檔整檔含 slow、`scripts/test_for.py` 挑的。**不做**：FIG-02（懷疑者駁回）、改成直接叫 `check_figures` 不走整份 validate（駁回）、`test_promotions_high` 與 `test_promotions_huang` 之外的檔。退版：只影響測試。",
    ])


def b224():
    return wb(224, "bounties 的整季併進 `test_bot_plays_a_full_season[1]`（S3／ARM-4）：先用一次性腳本比對同種子兩種夾具是不是同一季，一樣才併，不一樣就放棄", "dev/test-season-224", "8436", [
        "- 範圍：盤點 3.3 的 S3（＝artsgear 的 ARM-4，同一件事）。`tianxia/features/bounties/tests/test_bounties.py::test_a_whole_beta_season_posts_one_batch_a_week`（20 秒 slow）跟 `tests/season/test_real_content.py::test_bot_plays_a_full_season[1]`（閘門的整季冒煙，21 秒）都跑種子 1 的一整季，只差觀察器與斷言。這一批擁有這兩個檔，別批不碰。",
        "- **第一步，一次性比對（不進版控）**：`TIANXIA_DB` 設到暫存檔，照兩條測試各自的內容與夾具（bounties 那條的 content 設定、`test_real_content` 的 `season_of(1)`／`_real_s1()`）各跑一季種子 1，逐項比：結局、結束時間、江湖紀錄的標題清單、`world.bounties`（每週貼的那一批）、玩家最後的等級與地點。**一樣**才做第二步；**不一樣**（連一欄都算）就不併：把比對結果（哪一欄、兩邊各是什麼）寫進回報的 `decided` 與 `stopped`，這一批到此為止、什麼都不改。",
        "- **第二步（只在一樣時）**：把 bounties 的 observe（與 `_batch` 之類的輔助，連同 import）與斷言併進 `test_bot_plays_a_full_season[1]` 本體（照第 108 批把 `_idle_observer` 併進種子 2 的做法；`play_season` 的 `observe` 介面），保證併入後那一季的 `step` 計數、結局、紀錄跟併之前一模一樣（比對腳本再跑一次）；刪 bounties 那條整季；bounties 包的 README「另外要跑的」若列了它，句子放 `docs`。`tests/core/test_test_for.py` 若數 smoke 或 slow 的條數，照改。",
        "- **量**：併之前 `test_bot_plays_a_full_season[1]` 單跑秒數、併之後單跑秒數（它是閘門的冒煙，變慢多少寫清楚）、bounties 整檔含 slow 改前改後。**全跑**：`test_real_content.py` 整檔含 slow（約 5 分）、`test_bounties.py` 整檔含 slow、`scripts/test_for.py` 挑的。**不做**：別的整季（faction 豪強假人、sortie 假人、bot_runner 整季：設定不同，不併）、量表腳本。退版：只影響測試。",
    ])


def b225():
    return wb(225, "核心契約逐包三條共用一個 game（CORE-02）：先對 28 個有 stage 檔的包確認輸出沒變，有一包變了就整條放棄", "dev/test-contract-225", "8437", [
        "- 範圍：盤點 3.4 的 CORE-02（CORE-01 第 221 批做完了：`options_carry` 已併進 `test_choose_takes_only_its_own_ids`）。`tests/core/test_contract_features.py` 逐包的 `_game()`（`real_content('week7')` 複本加 `Game.new` 加 skip_tutorial 加 sync 加三選一迴圈）在 `test_choose_takes_only_its_own_ids` 與 `test_a_closed_package_gives_nothing`（含 prep card 那條）各建一次：改成每包只建一個 game，先 `own = _own_ids(feature, game)`，再取 shown 與做關閉斷言（brief 的 CORE-02）。這一批只擁有 `tests/core/test_contract_features.py`（與 `tests/core/test_test_for.py` 若名單要改；不改名就不碰）。",
        "- **先驗再改**：一次性腳本（不進版控）對 28 個有 stage 檔的包各算一次改前的 `own`、`shown`、關閉後的選項集合，改完再算一次，逐包逐集合比對；**有一包任何一個集合變了就整條放棄**，寫進 `decided` 與 `stopped`，程式退回不改。`_ids_on_a_fresh_game` 這種行程內快取照舊（xdist 每個 worker 各算一遍是已知、不在這一批）。",
        "- **量**：整檔 `-p no:xdist --durations=0` 改前（25 秒／256 條）改後；`_game()` 被叫的次數改前改後（計數寫進回報）。**全跑**：`tests/core/test_contract_features.py`、`test_contract_core.py`、`test_feature_boundaries.py`、`test_test_for.py` 整檔，`scripts/test_for.py` 挑的。**不做**：改契約驗的東西、改 `_game()` 建法、動 `test_for` 的挑法。退版：只影響測試。",
    ])


WEB_W = "**這一波沒動 `web/`，改的是測試。這一關不比畫面**。都不花 token：用 `Start-Process` 分離啟動、輸出導到檔，`docs/superpowers/pm-workflows/wait_file.py <檔> 570` 等，**不要前景跑**。不帶 `--ports`（各挑空埠，拒絕 7861）。\n1. 閘門帶 `--changed` 的決定應該是只改測試、不比對、不走網頁；真的有跑就看 real（有就是 blocker）。\n2. 用 head 的測試：`tests/figures/test_promotions_high.py`、`tianxia/features/military/tests/test_opportunities_two.py` 各量一次整檔 `--durations=0 -p no:xdist`，跟回報的改後秒數對；`tests/core/test_contract_features.py` 整檔一次全綠。\n3. 第 224 批若併了：`tests/season/test_real_content.py::test_bot_plays_a_full_season[1]` 單跑一次，秒數跟回報對、全綠；沒併（比對不同）就看 `stopped` 寫了哪一欄不同。\n4. 整套不含 slow 的牆鐘（閘門 `-n 8`）跟 V 波閘門 `edd4826f` 的 206 秒比，寫進回報。"

WAVES["W"] = dict(
    round2=True,
    extra_lenses=[
        dict(key="proof", text="**併測試，保護面不能掉**。第 223～225 批（盤點 " + V_SURVEY + " 3.2～3.4；候選原文 " + W_BRIEF + "）。親自驗：①第 223 批：每一組併進同一次 validate 的突變不超過約 8 個、同組 match 互不為子字串、裸字串 match 都補成了帶 id 的全句、正向 validate 沒跟會丟錯的併在一起、同欄位的突變沒放同組；parametrize 的 id 還在、每個 id 的斷言只對自己那句訊息；回報有「少一個突變」的注入證明（每一筆至少一組）；`test_rank_four_needs_legs_too` 沒被動；只改了 `tests/figures/` 與 `military/tests/` 的檔。②第 224 批：回報的 `decided` 有逐欄的比對結果；併了的話 `test_bot_plays_a_full_season[1]` 的 step 計數、結局、紀錄跟併前一樣（回報要有再跑一次比對的證據）、bounties 的斷言一句沒少地搬過去；沒併的話程式一行沒改。③第 225 批：回報有 28 包改前改後三個集合逐包比對的結果；`_own_ids` 在 shown 之前算；契約驗的東西沒變。④三批都沒碰 `tianxia/`、`web/`、`content/`、`server.py`、`scripts/`、`tests/conftest.py`、`tests/kit/`；清單外沒有刪、沒有併（`git diff --stat` 對清單）。⑤每一批的 before／after 秒數表都在。"),
    ],
    lines=[dict(name="突變併組", batches=[b223]), dict(name="整季共乘", batches=[b224]), dict(name="契約", batches=[b225])],
    merge_port=8438, fix_port=8439,
    web_check=dict(ports="8440、8441", steps=WEB_W),
)


# ── X 波：客服自動受理收尾 226～228、Y 波：測試去重收尾 229～231（企劃者 2026-11-19「客服自動受理和測試去重 繼續做完」）──
# 兩波分開開發（X 是新功能模式、Y 是只改測試），合併與閘門一次：finish 用 X，built 是兩邊接起來。
X_SCOPE = r"C:\Users\ray61\AppData\Local\Temp\claude\81800b313c89d0f8\ade93b70-b3b7-42db-a8af-21f7a7cbdb16\scratchpad\waveX\scope.json"
X_SHOTS = r"C:\Users\ray61\AppData\Local\Temp\claude\81800b313c89d0f8\ade93b70-b3b7-42db-a8af-21f7a7cbdb16\scratchpad\waveX"
X_NOTE = [
    "- **客服自動受理收尾這一波**（企劃者 2026-11-19「客服自動受理和測試去重 繼續做完」）：PM 11/19 把這條線留下的項目對現行程式重新查過一輪（每項一位查案、一位懷疑者），結果在 `" + X_SCOPE + "`（只讀；`items[].key` 是項目名，`found` 是查案、`verdict` 是懷疑者的核對與比較保守的做法）。**動手前先讀派工單點名的那幾個 key**，兩邊說法不一樣時照懷疑者的 `safer_way`，再對不上以現行程式為準、寫進 decided。原設計 `" + T_DESIGN + "`、原計畫 `" + T_PLAN + "`。上面「計畫不超過 120 行」照舊，寫在 `plan` 那個路徑。這一批不做派工單沒寫的事，碰到了寫 leftovers。",
    "- **開關 `Config.support.enabled` 預設關、week7 與 season21 也還關著，這一批不開它**。核心（`tianxia/core/`）、殼（`server.py`、`web/app.js`、`web/main.js`、`web/shell.js`、`web/style.css`、`index.html`）、`tests/core/shell_tables.py`、資料庫結構（第 9 版）一個字不動；要動才做得完就停下來寫 stopped。",
    T_NOTE[1].replace("設計 5.6 的對比圖：程式只做計畫寫的 A 版，B、C 兩版用暫時改 css 拍完就還原（不提交），截圖存計畫寫的暫存夾、路徑寫進回報；**不等企劃者挑才做**。", "這一批沒有要挑的版型：照現有的樣子接著畫，拍圖只為自驗，存 `" + X_SHOTS + "\\b<批號>\\shots\\`、路徑寫進回報。"),
    T_NOTE[2],
]


def xb(n, title, dev, ports, body):
    plan = f"docs/superpowers/plans/2026-11-19-客服收尾-第{n}批.md"
    return batch(n, f"客服自動受理收尾第 {n} 批：{title}", "support", dev, plan, ports, body + X_NOTE, custom=True)


def b226():
    return xb(226, "上限跟設定走（截圖張數與大小、沒結的單與一天幾張）、客服桌面讀不到時說一句、鎖兩件現有行為的測試", "dev/support-7", "8442", [
        "- 先讀 scope 的 `sup-limits`、`sup-relogin`、`sup-critic`。",
        "- **①上限跟設定走**。`tianxia/features/support/routes.py::_mine()` 的**每一個** return（含旁檔不在那一個）多回四個鍵：`files_max`、`file_bytes_max`、`open_max`、`daily_max`（值照 `Config.support`；先看 `tianxia/core/tuning/support.py` 這四個欄位真的叫什麼，名字照它）。測試加在現在斷言 `body_max` 的那一條旁邊（`test_support_tickets.py`）：`test_mine_carries_the_limits`（monkeypatch 成 0 與 5 都跟著變，旁檔不在時也有）。`web/support.js`：`SUPPORT_FILES_MAX`、`SUPPORT_FILE_BYTES` 兩個常數改成讀 `S.supportMine` 的函式，缺鍵（舊回應、讀取失敗）退回 3 與 3000000；三句提示（`SUPPORT_FILE_NOTE`、`SUPPORT_FILE_BIG`、`SUPPORT_FILE_FULL`）與 `SUPPORT_NOTE`（檔裡有兩處寫「同時最多 3 張沒結的單，一天最多送 5 張」，兩處都改）用數字組出來（MB 的寫法跟 `routes._mb` 一樣；預設值下組出來的句子**跟現在逐字一樣**）；`files_max` 是 0 時 `supportPickHtml()` 回空字串（按鈕、說明列、空位格整塊不畫）、送單不走上傳那一段。補圖那一格在 0 時本來就不出現，只換讀法。現有網頁測試（寫死 3 張、3000001 位元組、mine 假資料沒有新鍵的那幾條）**不改、要照樣綠**（它們就是「缺鍵退回預設」的證明）；新加 `test_support_web.py` 三條：`test_no_picker_when_files_max_is_zero`、`test_picker_follows_the_server_limits`（5 張與 1000000：第 6 張不收、1000001 位元組當場擋、提示寫 1 MB）、`test_note_follows_open_and_daily_max`。**不做**：`POST /api/support/file` 在 0 時提早拒（懷疑者判 drop）。",
        "- **②客服桌面讀不到時說一句**。現況：`supportDeskReload` 的 catch 把 `S.supportDesk` 退成全 0，畫出四個 0 的磚，之後不再重讀。改成：catch 記一個失敗旗標，`supportDeskHtml` 這時不畫四個磚、畫一行 `p.muted`「讀不到客服單，請按重新整理；剛用驗證碼登入的話，請改用帳號密碼重新登入。」（新字，旁註 `// 待 joy 潤`，列進 new_strings）；按「重新整理」清旗標重讀，讀到了就照常畫。`api()` 自己跳的那一則 toast 不管（在殼裡，不碰）。測試 `test_desk_says_so_when_the_queue_cannot_be_read`、`test_desk_refresh_recovers_after_a_failed_read`。",
        "- **③鎖兩件現有行為（只加測試，紅了才動程式）**。(a) 客服桌面的「請用密碼重新登入」那一行：identity 開著、帳號在客服名單上但不是管理者、這次 session 不是密碼登入時，客服桌面標題下要有那一行，桌面重畫之後還在（仿 `tianxia/features/identity/tests/test_identity_web.py` 管理頁那幾條的 mock 寫法，加在同一個檔：`test_support_desk_shows_the_relogin_line`、`test_support_desk_keeps_the_relogin_line_after_a_redraw`）。先確認客服進桌面的入口是不是都落在 `/admin`（`identity.js` 的觀察器只在那個路徑補）；**紅了**就是真的缺：最小改法只在 `web/identity.js` 的觀察器條件，不准包對包、不碰殼，改了什麼寫進 decided。(b) 按過「找真人」、之後被真人客服回成已回覆的單，玩家 3 天沒再回照樣自動結（PM 11/10 認定維持、企劃者看過沒反對）：`test_support_flags.py` 加 `test_a_human_answered_ticket_still_auto_closes_after_three_days`。",
        "- 拍圖自驗：暫存資料庫起 8442、客服開著、模型網址 127.0.0.1:9；寫單頁 `files_max` 預設與 0 各一組、客服桌面讀不到那一行，375 淺、375 深、1280。拍完 `taskkill /T`、刪暫存。",
        "- 比對：`compare --new support --also-existing` 的清單裡會多 `web/support.js`（它不管開關都送給每個瀏覽器），其餘一樣；清單抄進回報。退版：`web/support.js` 與 `_mine` 兩處退回就是寫死的舊樣子；沒有新欄位、沒有新表、季中能換；緊急開關照舊 `Config.support.enabled`。",
    ])


def b227():
    return xb(227, "主機端：客服官白名單的許可實跑與兩條自動測試、知識匯出驗一次並鎖住、FAQ 補到 11/19、排練清單更新", "dev/support-8", "8443", [
        "- 先讀 scope 的 `sup-rehearsal`、`sup-howto`、`sup-critic`。這一批**不動 `tianxia/`、`web/`、`content/`、`server.py`**，只動 `scripts/support_*.py`、`docs/support/`、`docs/superpowers/discord/客服官-設定.md`、包的 `tests/` 與 README。",
        "- **①許可實跑（T 波審查留下的唯一安全缺口）**。用 `scripts/support_session_init.py` 把客服官 session 範本裝到暫存夾（`" + X_SHOTS + "\\b227\\desk\\`，**不是** `C:\\Ray\\tianxia-support\\`），`settings.local.json` 拿掉 `enabledPlugins`（不接 Discord），金鑰檔自造 40 字亂數假 token，`cli.sh` 指到一台你自己起的暫存伺服器（8443、客服開著）或不存在的埠都行。用 `claude -p --output-format json`（模型用最小的那一顆；**絕不帶 `--dangerously-skip-permissions`、不帶任何放寬權限的參數**）各跑一次，看輸出的 `permission_denials`（**不是看結束碼**：展開之後 `cli.sh` 多半回 2，被擋與被放行但沒做事分不出來）：要放行的 `./cli.sh queue`；要被擋的 `./cli.sh queue \"$(whoami)\"`、反引號寫法、`./cli.sh queue $(ls ..)`、`./cli.sh ticket 1 \"$(cat ../.local/support.json)\"`、`./cli.sh answer 1 \"$(echo x)\"`、`./cli.sh queue; dir`、讀工作夾外的檔、寫一個檔。記下 `claude --version`。結果逐條寫進 decided 與 `docs/support/排練.md`。**有任何一條該擋而沒擋**：不要放寬任何規則、不要自己猜著改白名單；可以收緊（例：`cli.sh` 的 `case` 多擋展開後才會出現的字元，同步改 `test_support_session.py` 逐字比對那一條），收緊後重跑那一條；仍擋不住就寫 stopped，開頭寫「安全：」。跑不起來（沒有 `claude` 指令、要登入）就寫「沒實跑」與原因，不硬做。",
        "- **②兩條自動測試**（`test_support_session.py`；要 Git Bash，沒有就 skip，照檔裡現有那一條的寫法）：`test_expanded_arguments_never_reach_the_server`（把「展開之後會長成的字」——帶空白的使用者名稱、一串檔名、一段 JSON——直接當參數給真的 `cli.sh`＋真的 `support_cli.py`：結束碼 2、零個 HTTP 請求、輸出不含 token）、`test_every_command_in_the_session_rules_exists`（`docs/support/session/CLAUDE.md` 裡每一個 `cli.sh <子指令>` 都是 `support_cli.py` 的 argparse 子指令）。不開埠、不起假的 webhook 伺服器。",
        "- **③知識匯出**。交接寫「`howto.md` 從籌備中世界匯出沒有收季那句」，查案員讀程式認為這句是錯的（籌備中的季種下去就蓋過章）。實跑定案：`TIANXIA_DB` 指到暫存檔，`scripts/support_knowledge.py --profile season21` 與 `--profile week7` 各匯一次，看 `howto.md` 有沒有收季那一句（兩種設定的句子可能不同）。有：加回歸測試 `test_knowledge_export_with_real_content_carries_the_season_end_rule`（兩種設定一條迴圈，輸出過 `tests/bots/test_server_bots.py` 的 `leaks()`；單條超過 1 秒就標 slow），並把 `support_knowledge.py` 檔頭那句不對的說明改對（真正匯不出來的是什麼照實寫）。沒有：寫清楚少的是哪一句、為什麼，最小修法只在 `scripts/support_knowledge.py`（不開季、不碰 `tianxia/`），加同一條測試。檔頭再加一句：換了設定或改版之後要重匯。",
        "- **④FAQ 補到 11/19**（`docs/support/FAQ.md`）：11/10～11/16 上線的東西各補一兩題——親衛隊長、江湖錄與江湖頁的「進行中」、門派、結義、帖友書信、稱號、馬的來路、意境合成改版、開局前導、紅點、捐軍備關了、村鎮營地不再教下品武學、武學成數只靠戰鬥、21 天季擂台與懸賞榜不再等第 2 週。**只寫 `content/patch_notes.json`、各包 README、`docs/guide` 查得到的**，查不到的不寫；不寫機率、戰況、任何跟假人有關的字；每條旁 `<!-- 待 joy 潤 -->`。舊題跟現況對不上的（例：寫了擂台第 2 週才開）一起改。",
        "- **⑤排練清單**（`docs/support/排練.md`）：本機這一輪的結果填進去；Discord 那一半還沒走的每一項標清楚卡在企劃者五樣裡的哪一樣；「三種都要被擋」那一項補上讀工作夾外金鑰檔的那一種。`ALIVE`、`start.cmd`／`stop.cmd`（用假的 `claude.cmd`，`TIANXIA_DB` 填暫存庫）本機能走的走一次，等 300 秒的用參數縮短、沒有參數就讀程式確認不乾等；收尾確認橋與假 session 的行程都沒殘留。設計稿寫 `ALIVE` 會進 log、程式照計畫只印 stdout：不改程式，句子放回報的 docs（PM 改設計稿）。",
        "- **不做**：真的 Discord 排練；橋打 HTTP 或寫旁檔；`monitor.py`；自動結單誰來掃（第 228 批另派）；`_wipe_db`（懷疑者判現在沒有東西可做）。退版：都是主機腳本、測試與文件。",
    ])


WEB_X = "**這一波動到畫面的只有第 226 批的 `web/support.js`：寫單頁的截圖與提示改讀伺服器給的上限、`files_max` 是 0 時整塊不畫、客服桌面讀不到時畫一行字**（開關預設關）。用 head 的 `scripts/webqa/`，上面「照 tianxia-qa 並排截圖」照做。都不花 token：用 `Start-Process` 分離啟動、輸出導到檔，`docs/superpowers/pm-workflows/wait_file.py <檔> 570` 等，**不要前景跑**。不帶 `--ports`（各挑空埠，拒絕 7861）。\n1. **開關關著**：閘門帶 `--changed` 已經跑過網頁比對（`.local/wave_gate/<head8>/web/report.txt`），這一關不重跑，只看它有沒有 real（有就是 blocker）、`missing_must_reach` 空。\n2. **開關開著**（base 與 head 的設定覆寫檔都把 `support.enabled` 打開，客服身分用 `TIANXIA_SUPPORT=<你用 scripts/set_password.py 建的帳號>`，兩邊同樣的步驟）：玩家在設定抽屜開客服、開寫單頁——預設值下 base 與 head 的寫單頁**逐像素一樣**（提示字逐字一樣）；玩家附 2 張圖送一張單、看單有兩張縮圖。再只對 head：設定覆寫檔把 `support.files_max` 設 0 重起，寫單頁沒有「附截圖」那一塊、送單正常；設回 5 與 `file_bytes_max` 1000000，提示寫 5 張、1 MB。客服桌面：客服身分開 `/admin` 的客服桌面照常列單；把伺服器停掉再按「重新整理」，畫出「讀不到客服單…」那一行、不是四個 0；伺服器起回來再按，恢復。375 淺、375 深、1280 各拍。主控台 0 錯誤。"

X_FEATURE_LENS = dict(key="feature", text="**客服收尾：關著一個字不變、開著照派工、看不出假人、沒碰不該碰的**。第 226、227 批（與第 228 批，如果這一波有）；查案原文 " + X_SCOPE + "。親自驗：①開關關著：`/api/support/*` 照舊 404、`/api/me`、`/api/main` 對 base 位元組一樣；變的只有 `web/support.js` 這個檔本身。②預設值下 `web/support.js` 組出來的四句提示跟 base 逐字一樣（把兩邊的字串抓出來比）；缺鍵退回 3、3000000；現有寫死 3 張與 3000001 的網頁測試一條沒改。③`_mine` 每一個 return 都帶四個鍵。④客服桌面讀不到那一行只在失敗時出現、重新整理會清；新字旁有待 joy 潤。⑤第 227 批沒有動 `tianxia/`、`web/`；許可實跑的指令沒有任何放寬權限的參數、暫存夾不在 `C:\\Ray\\tianxia-support\\`、回報與 commit 裡沒有真的 token；FAQ 新題沒有機率、戰況、假人字樣，每條有待潤標記，內容在 patch_notes 或 README 查得到（抽五題對）。⑥核心、殼、`shell_tables`、資料庫結構沒有動；包沒有 import 別包。⑦`leaks()` 掃得到新加的輸出。")

WAVES["X"] = dict(
    round2=True, feature=True, design=T_DESIGN, new_packages="identity,support,terms", new_existing=True,
    extra_lenses=[X_FEATURE_LENS],
    lines=[dict(name="客服收尾", batches=[b226, b227])],
    merge_port=8447, fix_port=8448,
    web_check=dict(ports="8449、8450", steps=WEB_X),
)


Y_NOTE = [
    "- **測試去重收尾這一波**（企劃者 2026-11-19「客服自動受理和測試去重 繼續做完」）：PM 11/19 把盤點 `" + V_SURVEY + "` 留下的每一項對現行程式重新查過（每項一位查案、一位懷疑者），結果在 `" + X_SCOPE + "`（只讀；`items[].key` 是項目名，`found` 是查案、`verdict` 是懷疑者）。**動手前先讀派工單點名的 key**；兩邊說法不一樣時照懷疑者的 `safer_way`，再對不上以現行程式為準、寫進 decided。上面「計畫不超過 120 行」照舊，計畫寫在 `plan` 那個路徑。**不動 `tianxia/`、`web/`、`content/`、`server.py`**，`scripts/` 只有派工單明寫的才碰；不改任何斷言的意思（併是把同樣的斷言放在一起，不是放寬）；**一條測試都不刪**（刪除候選只列在回報，企劃者點頭才刪）；清單外的測試不動。",
    "- **秒數怎麼量**：junit（每日整套 11/19，`-n 4` 含 slow）在 `" + X_SHOTS + "\\junit_1119.json`，只能當線索；要下判斷的一律自己量：`.venv/Scripts/python.exe -m pytest --durations=0 -p no:xdist -m \"slow or not slow\" <檔>`，**跑兩次取大的**（別的線同時也在跑測試，機器不安靜）。改前改後寫進回報的 `decided`（表：檔或條、改前、改後）。各包 README、`docs/guide`、手冊、`CLAUDE.md` 不動，句子放回報的 `docs`。怎麼寫測試照 V、W 波定的：正式內容一律 `conftest.real_content(profile)`、harness 不等 ≥1 秒的計時器、預設資料庫從模板抄。",
]


def yb(n, title, dev, ports, body):
    plan = f"docs/superpowers/plans/2026-11-19-測試收尾-第{n}批.md"
    return batch(n, f"測試去重收尾第 {n} 批：{title}", "core_shared", dev, plan, ports, body + Y_NOTE, custom=True)


def b229():
    return yb(229, "備份大資料庫那一條的判準不靠牆鐘；conftest 的 real／on 建法收成一處；江湖錄網頁測試不真等計時器；過時的註解", "dev/test-tidy-229", "8444", [
        "- 先讀 scope 的 `t-backup`、`t-critic`、`t-new`、`t-appjs`。",
        "- **①`tests/server/test_backup_db.py::test_backup_of_a_big_database_finishes_while_writes_never_stop`**（11/10 03:30 紅過一次，判是四個 worker 搶磁碟）。現在 writer 靠 20 秒 monotonic deadline 自己停，備份拖過 20 秒或 writer 被 `database is locked` 打死，同一句 `assert` 倒、分不出原因。改成（照懷疑者的 `safer_way`）：writer 只由 `stop` 事件停（另留一個很長的保險期限，例 120 秒，只防測試自己卡死）、例外收進 `errors`、數 commit 次數；斷言的順序：先 `errors` 是空的（訊息寫「寫入的那一邊被鎖死」）、備份沒丟例外（訊息寫「備份被擋」）、備份回來之後 writer 還活著而且**之後**還會再 commit 至少一次（等事件、逾時 10 秒；**不比備份期間 commit 了幾次**——快機器上備份幾十毫秒就做完，期間可能 0 次）、備份檔 `integrity_check` 與筆數。**加一道結構護欄**抓「改回分步複製」的回歸（照 scope 裡寫的做法；它才是快速抓回歸的主力，不是選做）。**2 萬筆不縮**。證明：暫時把 `scripts/backup_db.py` 改回分步複製（不提交），新測試要紅，而且紅在護欄或「備份被擋」那一句；還原後綠；兩次都寫進回報。同檔 `test_backup_while_someone_keeps_writing` 的 writer 沒有 try/except 的話，同樣收 `errors`、先斷它是空的。`scripts/backup_db.py` 不改。",
        "- **②conftest 的 real／on 建法**：W 波第 223 批在 `test_rank_actions.py`、`test_opportunities.py`、`test_promotions_huang.py` 各照抄了一份 `tests/conftest.py` 的 `real`／`on` 建法（docstring 自己寫是抄本）。在 `tests/conftest.py` 加純函式（名字你定，例 `make_real()`、`make_on(real)`），`real`、`on` 兩個 fixture 改成叫它，**fixture 的行為不變**；三個檔的抄本改叫同一個函式。換之前用一次性腳本比：舊抄本與新函式建出來的內容 `model_dump_json()` 逐字一樣（三個檔各比一次），結果寫進回報。",
        "- **③江湖錄網頁測試**（`tianxia/features/codex/tests/test_codex_web.py` 裡 junit 1.9 秒那一條）：它真的在等 4×400 ms。只改**那一條測試自己的 script**（照懷疑者的寫法：把長延遲的 `setTimeout` 在那條 script 裡縮掉、再等一次 microtask），`tests/kit/webharness.py` 不碰；送出與重抓的斷言一句不少。改前改後秒數寫進回報。",
        "- **④過時的註解，順手**：`tests/conftest.py` `LONG_FIRST` 上面那段註解跟 `tests/core/test_test_for.py` 現在斷的對不上的地方改對（名單本身不動）；`bounties` 測試檔開頭重複的 import 拿掉；`test_app_js_parses` 的 docstring 還寫「三個檔」（實際是 `APP_FILES` 五十幾個）改對，**測試名不改**；`test_codex_smoke.py` 檔頭骨架留下的範本註解清掉（`@pytest.mark.smoke` 與斷言不動）。",
        "- **不做**（scope 裡懷疑者判 drop 的，不要撿回來）：`load_content(FIXTURE)` 換快取（省不到 1 秒）、`test_app_js_parses` 改成一次 node、identity notify 併對、`_live_db` 換模板、`test_real_content` 的 `_real_s1`／`_announce` 共用、`test_sim_scripts` 縮範圍、fb095。這幾項與理由抄一行進回報的 leftovers 開頭寫「查過不做：」，PM 寫回盤點。",
    ])


def b230():
    return yb(230, "還標 slow 的網頁測試照第 220 批的 0.5 秒規則重量，量得過的拿掉標記", "dev/test-slowweb-230", "8445", [
        "- 先讀 scope 的 `t-slowweb`、`t-s21frame`、`t-critic`，與 `docs/superpowers/plans/2026-11-10-測試去重-第220批.md` 裡拿掉 slow 的規則原文（0.5 秒那一條與怎麼量）。第 220 批改了常駐 harness 之後，只因為等計時器才標 slow 的可以放回平常的整套（企劃者 11/10：不把慢測試一律標 slow 藏起來；反過來，量得過的就放回來）。",
        "- **先列全**：全 repo 用常駐 node harness 的網頁測試裡還標 slow 的（`git grep -l webharness -- tests tianxia/features` 再對每個檔 grep `mark.slow`／`pytestmark`；查案員的清單被截斷過，不要只看 scope 列的五個檔）。已知：sortie `test_core_loop_web`（單條標）、`test_sortie_report`（整檔）、territory_acts `test_conquest_web`（單條標）、`tests/web/test_jianghu_page_web.py`（單條標）、sense `test_epiphany_name_web`（整檔）、companions `test_errands_web`（整檔）、map、peers、socialize 各有零星一兩條。",
        "- **逐檔量**（照上面「秒數怎麼量」，兩次取大的；整檔 `pytestmark` 的檔第一條會吃到載內容，照實量）：單跑 **< 0.5 秒**的拿掉 slow；**0.4 以上**的預設留著，除非兩次都明顯低於 0.5；≥0.5 的留著。整檔 `pytestmark = pytest.mark.slow` 的檔如果只有幾條要留，改成那幾條單條標；別的標記（`whole_content` 等）與旁註的其他內容不動。`tests/figures/test_season21_frame.py` 的兩條純函式測試（`test_the_warning_function_itself_knows_the_phase`、`…matching_programs_and_ended_seasons_stay_quiet`）照同一條規則量、量得過就拿掉 slow；這個檔啟動類那幾條**不動、不刪**（刪除候選抄進回報）。",
        "- **連動**：`tests/core/test_test_for.py` 有拿這些檔當「整檔 slow」或數 slow 條數的例子，拿掉標記之後照新的事實改（例子換成還是整檔 slow 的別的檔，或改數字；**不改它在驗的規則**）；`scripts/test_for.py` 裡點名這些檔的註解跟著改（這一批只准動這個檔的註解）。`tests/conftest.py` 不碰（第 229 批在改）。",
        "- 回報：一張表（檔、測試、第一次、第二次、決定），拿掉幾條、留幾條；平常的整套（不含 slow）因此多跑幾條、多幾秒（照你量的加總，寫【量】不是【估】）。跑一次 `scripts/test_for.py` 確認挑到的都綠。",
    ])


def b231():
    return yb(231, "tests/core/test_content.py：先量；單條 1 秒上下、「改一個欄位再整份 validate 正式內容」的突變測試照第 223 批的規矩併組，省不到 8 秒就放棄", "dev/test-content-231", "8446", [
        "- 先讀 scope 的 `t-critic`（最後兩項）與 `docs/superpowers/plans/2026-11-10-測試去重-第223批.md`（第 223 批怎麼併、怎麼證明）、`docs/superpowers/plans/2026-11-10-波次W紀錄.md` 第 223 批「開發定的」。`tests/core/test_content.py` 是不含 slow 的整套裡最大的一個檔（370 條、junit 51.5 秒）；裡面約 11 條各 1.2～1.7 秒（`test_orders_escort_must_end_at_a_base_of_its_side`、`test_orders_text_slots_must_be_known`、`test_stance_fields_only_on_season_one_endings`、`test_promote_only_on_promotion_scenes`……），其餘中位數 0.1 秒。",
        "- **第一段只量、定組**：整檔單跑量每條；≥0.6 秒的每一條讀它做什麼（載哪一份內容、改幾個欄位、validate 幾次、斷哪一句）。**只收這一種**：改正式內容（或它的複本）的一個欄位、整份 `validate`、斷 `ContentError` 的某一句。照第 223 批的規矩定組：一組不超過約 8 個突變；同組的 match 互不為子字串；裸字串的 match 補成帶 id 的全句（先用探針把每個突變單獨丟的全句抄下來）；正向的 validate 不跟會丟錯的併；同一個欄位的突變不放同組；改掉別的突變要靠的物件的不併。算併完省幾秒（validate 次數 × 單次秒數）：**省不到 8 秒 CPU 就放棄**，回報寫量表與理由，第二段不做（照第 225 批放棄的前例，`stopped` 留空、`decided` 寫「放棄」）。0.1 秒那三百多條（各抄一份測試內容夾再載）不動。",
        "- **第二段**：照第 223 批的寫法併——原本的 parametrize 與測試名都留著（每一筆還是自己的 id），module 範圍的 fixture 懶算、一組 validate 一次、每個 id 只斷自己那一句全句；整組套上卻沒丟錯要有帶組名的 assert。**每一筆做注入證明**：拿掉一個突變，只有它自己的 id 紅（至少每一組做一次，結果進回報）。只改 `tests/core/test_content.py` 一個檔。改前改後整檔秒數與 validate 次數寫進回報。",
    ])


Y_PROOF_LENS = dict(key="proof", text="**改測試，保護面不能掉**。第 229～231 批；查案原文 " + X_SCOPE + "。親自驗：①第 229 批：備份那一條改完之後，把 `scripts/backup_db.py` 暫時改回分步複製（解到暫存夾做、不提交）它真的會紅，而且訊息分得出「寫入被鎖死」與「備份被擋」；2 萬筆沒縮；沒有比「備份期間 commit 幾次」這種快機器會誤報的判準；conftest 新函式建出來的內容跟三個檔原本的抄本逐字一樣（回報要有比對，抽一個自己比）、`real`／`on` fixture 行為沒變；江湖錄那一條的斷言一句沒少、`tests/kit/webharness.py` 沒動。②第 230 批：每一條被拿掉 slow 的在回報的表裡有兩次量到的秒數且都 < 0.5；整檔 `pytestmark` 拿掉後該留的單條標記都在；`whole_content` 等別的標記沒被順手拿掉；`test_test_for.py` 改的是例子與數字、沒有改它在驗的規則；`scripts/test_for.py` 只動註解。③第 231 批（沒放棄的話）：每組不超過約 8 個突變、同組 match 互不為子字串、裸字串都補成帶 id 的全句、正向 validate 沒跟會丟錯的併、parametrize 的 id 與測試名都在、回報有每組的注入證明；放棄的話量表與理由在。④三批都沒有刪任何測試（`git diff --stat` 與收集條數對 base 比：只准第 230 批因為標記變動而「不含 slow」的條數變多，總條數不變）、沒有動 `tianxia/`、`web/`、`content/`、`server.py`。")

WEB_Y = "**這一波沒動 `web/`，改的是測試**。這一關不比畫面：只看閘門的 `.local/wave_gate/<head8>/web/report.txt`（有跑的話）沒有 real、`missing_must_reach` 空；沒跑就回 same、寫「沒動畫面」。"

WAVES["Y"] = dict(
    round2=True,
    extra_lenses=[Y_PROOF_LENS],
    lines=[dict(name="測試小件", batches=[b229]), dict(name="慢網頁測試", batches=[b230]), dict(name="內容驗證", batches=[b231])],
    merge_port=8452, fix_port=8453,
    web_check=dict(ports="8454、8455", steps=WEB_Y),
)
WAVES["X"]["extra_lenses"].append(Y_PROOF_LENS)  # 合併與閘門一次：finish 用 X，built 是 X、Y 兩邊接起來


# ── Z 波：比對與走查工具修到在現在的 develop 上跑得起來 232、233（PM 2026-11-19：X、Y 兩波的閘門要用；Joy 11/12 #243 在 week7、season21 打開條款之後，情境照舊的方式註冊建不出玩家）──
Z_LOG = r"C:\Users\ray61\AppData\Local\Temp\claude\81800b313c89d0f8\ade93b70-b3b7-42db-a8af-21f7a7cbdb16\scratchpad\waveX\sbdbg"
Z_NOTE = [
    "- **這一批修的是工具，不是遊戲**。11/12～11/16 Joy 的 46 個 PR（#235～#281）直接合進 develop、上了 main，那段時間主機側沒跑過閘門與比對，只有每日整套 pytest（綠）。11/19 PM 要驗新的一波時發現比對情境在現在的 develop 上跑不起來。**上面波次模式寫的「你不跑 same_behavior compare」「不跑 selftest」對這一批不適用**：把工具跑起來、跑到穩，就是這一批的工作。上面「計畫不超過 120 行」照舊，計畫寫在 `plan` 那個路徑。",
    "- **只准動 `scripts/`（派工單點名的那一塊）與它的測試**；`tianxia/`、`web/`、`content/`、`server.py`、設定覆寫檔、`tests/conftest.py` 一個字不動。情境跑不下去是因為遊戲的規則變了（Joy 改的，是要的），**改情境去配合遊戲，不改遊戲去配合情境**；不准為了跑得過而在情境裡把正式設定打開的包關掉（那樣比的就不是線上的樣子），除非那一軌本來就註明在比「關著」。判斷拿不準選最保守的，寫進 decided。",
    "- 這台同時有別的線在跑測試：重的全軌跑一次就好，要重跑先只跑壞的那幾軌。跑的時候**環境裡不要有 `TIANXIA_DB`**（`same_behavior` 自己管暫存庫；設了連好的軌都會紅），暫存夾用 `--tmp` 給、放你的暫存底下，跑完刪大檔。各包 README、`docs/guide`、手冊、`CLAUDE.md` 不動，句子放回報的 `docs`。",
]


def zb(n, title, dev, ports, body):
    plan = f"docs/superpowers/plans/2026-11-19-工具修復-第{n}批.md"
    return batch(n, f"工具修復第 {n} 批：{title}", "core_shared", dev, plan, ports, body + Z_NOTE, custom=True)


def b232():
    return zb(232, "same_behavior 的情境在現在的 develop 上跑得起來、跑得穩（條款開著的註冊；其餘壞掉的軌逐軌修），covers 重量", "dev/tools-sb-232", "8456", [
        "- **已經知道的**：`PYTHONHASHSEED=0 python scripts/same_behavior.py run --tmp <夾> --track talk . season21 <輸出>`（還有 `switchboard`）在 develop `b0a70f841` 上丟 `AttributeError: 'NoneType' object has no attribute 'player'`（`scripts/sb/base.py` 的 `edit`，從 `place` 進來；PM 跑的紀錄在 `" + Z_LOG + "\\talk.log`、`switchboard.log`）。PM 讀程式的判斷（**你要自己證實**）：`scripts/sb/base.py` 的 `setup`、`newcomer` 與 `scripts/sb/tracks/switchboard.py` 自己的 `setup` 用 `POST /api/register` 只送 `login`、`password`、`again`；#243 之後 week7、season21 的條款開著，註冊要帶「滿 18 歲」「同意條款」兩個勾選與版號（`tianxia/core/terms_base.py::register_problem`、`web/terms.js` 怎麼送就怎麼送、版號從 `GET /api/terms/version` 拿），不帶就被拒、帳號沒建、後面全倒。`facade`、`drape` 兩軌沒壞。",
        "- **①修註冊**：所有經 API 註冊的地方（`git grep -n '/api/register' -- scripts/sb`）改成條款開著時照前端的送法帶上勾選與版號；條款關著時（test 設定、`config.json` 那一層）送出去的請求**位元組不變**（那邊的輸出不能因此改）。寫成一個共用的小函式，不要每個軌各抄一份。",
        "- **②全軌跑一遍找出其餘壞的**：三種設定（season21、week7、test）每一軌用現在的程式自己對自己跑（`selftest` 或 `compare --base <develop 解開的樹> --head <同一棵樹>`，看工具哪一個快；`--base`、`--head` 要的是解開的樹，用 Python 的 tarfile 解 `git archive`）。分三堆寫進回報的表：跑得完而且兩次一樣的；丟例外的；跑得完但兩次不一樣的（不穩）。丟例外與不穩的逐軌修情境（多半是五包打開、江湖錄、親衛隊長、開局前導、新的鎖與灰鈕讓原本那一步按不到）：修法是讓情境照現在的遊戲走得到它原本要走的東西；真的走不到了（那個玩法被拿掉或被取代）就把那一步拿掉並在軌的說明字裡照實寫，**不要留一步靜靜地什麼都沒做**。",
        "- **③修完驗**：`ALWAYS_TRACKS`（`scripts/sb/harness.py`）六軌加你動過的每一軌，三種設定各跑 `selftest`：跑兩次一樣、前半加後半等於整段、改一個字抓得到。全軌三設定自己對自己 `compare` 全部一樣。`tests/core/` 裡守 `scripts/sb` 的測試（邊界、covers 那 15 條、`test_test_for` 裡點到 sb 的）照 `scripts/test_for.py` 挑的跑過。",
        "- **④covers 重量**（五包打開、多了 codex 包，11/10 量的已經過時）：`scripts/sb/covers_measure.py` measure → analyze → write 照檔頭的做法在修好的程式上重量一次（三設定約 20 分鐘 CPU）；analyze 結束碼要 0（ALWAYS 的不變量沒破）；covers 測試有警告就照實抄進回報（例：codex 沒有任何軌碰到）。**不加新軌**（codex、guard 之外新包要不要補軌寫進 leftovers，PM 定）。",
        "- **⑤確認閘門拿誰的情境**：讀 `docs/superpowers/pm-workflows/wave_gate.py` 與 `scripts/same_behavior.py compare`：比 base 與 head 時，跑 base 那一側用的是 head 的 `scripts/sb` 還是 base 自己的？寫進回報（PM 要知道這一批合進去之後，拿修之前的 develop 當 base 比不比得起來；比不起來的話寫出 PM 該拿哪一筆當 base）。`wave_gate.py` 不改。",
        "- 時間上限：這一批（兩段合計）不超過 3 小時；到了就把修好的推上去、交，沒修完的軌列在 leftovers（哪一軌、哪個設定、倒在哪一步、你的判斷）。",
    ])


def b233():
    return zb(233, "網頁走查與網頁比對（scripts/webqa）在現在的 develop 上跑得起來：條款開著的註冊、江湖錄開著、其餘走不到的景", "dev/tools-webqa-233", "8457", [
        "- 背景同第 232 批：#243 之後 week7、season21 的條款開著，註冊表單多兩個勾選（`web/terms.js` 註冊模式才插、沒勾擋送出），進遊戲後沒同意現行版的會疊一層；江湖錄 `codex` 11/13 起在 week7、season21 開著（俠客頁多一顆分頁、江湖頁狀態列底下多「進行中」一行、已投靠的人上面那一大塊收進「事」清單）；`scripts/webqa/serve.py` 只把開局前導 `intro` 關掉。`scripts/webqa/gate.py` 把 `web/codex.js` 登記成走查不碰，理由寫「codex 在走查跑的每個設定都是關的」——這句跟現況對不上。**PM 沒實跑過 webqa，壞不壞、壞在哪由你量**。",
        "- **①量現況**：照 `.claude/skills/tianxia-qa/SKILL.md` 與 `scripts/webqa/` 的 README／檔頭，用 develop 現在的程式自己對自己跑一次網頁比對的全回合（`wave_gate.py` 怎麼叫 webqa 就怎麼叫；`Start-Process` 分離啟動、輸出導到檔、`docs/superpowers/pm-workflows/wait_file.py` 等，不要前景跑；不帶 `--ports`，拒絕 7861；模型網址 127.0.0.1:9）。回報表：每一回合跑不跑得完、`real` 幾張、`missing_must_reach` 有哪些、主控台錯誤。全部好的話這一批到此為止，寫「沒壞」與證據，第二段只做②。",
        "- **②修**：只改 `scripts/webqa/`（flow、stage、serve、gate 的登記）。註冊那一步照真人會做的勾兩個勾選；疊的同意層照真人會做的按同意。江湖頁改版之後原本靠「上面那一大塊」找的鈕，改成現在真人找得到的路（「事」清單、「進行中」那一行）。走不到的 must_reach 逐個判：是景還在、flow 要改路；還是景被 Joy 拿掉了（那就從 must_reach 拿掉並在回報寫是哪個 PR 拿的）。`gate.py` 對 `web/codex.js` 的登記改成跟現況一致：江湖錄開著，改到 `web/codex.js` 要挑得到至少一個走得到江湖錄分頁與「進行中」那一行的回合；現有回合走不到就在現有 flow 加最短的幾步（點開江湖錄分頁、點「事」印），加的景進 must_reach。**不准**為了跑得過在 `serve.py` 把正式設定開著的包關掉（intro 已經關的照舊：那是動畫，比不了）。",
        "- **③修完驗**：全回合自己對自己再跑一次：每一回合跑得完、0 real、`missing_must_reach` 空、主控台 0 錯誤；`tests/web/test_webqa.py` 與 `scripts/test_for.py` 挑的跑過。跑兩次結果一樣（至少挑兩個回合跑第二次）。",
        "- 時間上限：兩段合計不超過 3 小時（全回合一次約一小時，別重跑第三次）；到了就把修好的推上去、交，沒修完的列在 leftovers（哪一回合、哪一景、你的判斷）。",
    ])


WAVES["Z"] = dict(
    round2=True,
    lines=[dict(name="比對工具", batches=[b232]), dict(name="走查工具", batches=[b233])],
    merge_port=8461, fix_port=8462,
)
Z_TOOL_LENS = dict(key="tools", text="**工具修復：改情境去配合遊戲，沒有反過來；修完真的在比東西**。第 232、233 批。親自驗：①`git diff --stat` 對 base：只動了 `scripts/sb/`、`scripts/webqa/` 與它們的測試、計畫檔；`tianxia/`、`web/`、`content/`、`server.py`、設定覆寫檔一個字沒動。②條款關著的設定（test）下，註冊送出去的請求跟修之前位元組一樣（讀程式；挑一軌在 test 設定跑修前修後的情境，輸出要一樣）。③沒有任何一軌、任何 `serve.py` 的設定把正式設定打開的包偷偷關掉（grep `enabled`、`old_packs`、`terms`、`zongmen`、`jieyi`、`mail`、`titles`、`codex` 在 `scripts/sb`、`scripts/webqa` 的每一處，逐處看是誰加的、為什麼）。④被拿掉的步驟與 must_reach 每一個在回報都有理由（哪個 PR 拿掉那個玩法）；沒有「靜靜地什麼都沒做」的步驟（挑三軌讀輸出，確認情境說明字寫「走到」的在輸出裡真的有）。⑤covers 重量的結果寫回了登記、analyze 結束碼 0。⑥`gate.py` 對 `web/codex.js` 的登記跟現況一致，改 `web/codex.js` 挑得到回合。")
WAVES["X"]["extra_lenses"].append(Z_TOOL_LENS)


# ── AA 波：打開真人客服 228；AB 波：客服的比對軌 235、客服的走查景 236（企劃者 2026-11-19「這一波落地後先開真人客服」）──
# 兩波分開開發（AA 是新功能模式、AB 是只改工具），合併與閘門一次：finish 用 AA，built 是兩邊接起來。
# 基準不是 develop，是 PM 在 develop 上先放的「開關那一筆」（兩份設定覆寫檔打開客服＋煙霧測試那一行）：閘門拿它當 base，兩邊客服都開著，其餘才比得出一樣（W 波 craft、horses 打開那次的做法）。
AA_SCOPE = r"C:\Users\ray61\AppData\Local\Temp\claude\81800b313c89d0f8\ade93b70-b3b7-42db-a8af-21f7a7cbdb16\scratchpad\waveX\scope228.json"
AA_SHOTS = r"C:\Users\ray61\AppData\Local\Temp\claude\81800b313c89d0f8\ade93b70-b3b7-42db-a8af-21f7a7cbdb16\scratchpad\waveX"
AA_BACKGROUND = (
    "- **背景（三批共用）**：企劃者 2026-11-19 決定「這一波落地後先開真人客服」。**你的分支是從 PM 放好的「開關那一筆」開的**：`content/profiles/week7.json`、`season21.json` 已經各有 `\"support\": {\"enabled\": true}`，"
    "`test_support_smoke.py` 已經改成斷言開著（`git log -1` 看得到那一筆）。**只開真人那一半**：`Config.support.bot_account` 照舊空字串（客服官 token 那條路一律 404，沒有自動回覆）、帳號綁定 identity 照舊關著、"
    "客服名單由企劃者放在主機的 `.local/support.txt`（你不讀、不寫任何 `.local/`）。截圖照預設收（一張單 3 張、一張 3 MB；PM 量過主機那顆碟還剩 377 GB）。"
    "PM 11/19 派了七位查案員、七位懷疑者、一位最後一關把「打開之後會怎樣」查過一輪，結果在 `" + AA_SCOPE + "`（只讀；`items[].key` 是角度名，`found` 是查案、`verdict` 是懷疑者；`gaps` 是最後一關，**說法互相打架時照 `gaps`**，再對不上以現行程式為準、寫進 decided）。"
    "**動手前先讀派工單點名的那幾個 key**。上面「計畫不超過 120 行」照舊，寫在 `plan` 那個路徑。這一批不做派工單沒寫的事，碰到了寫 leftovers。"
)
AA_FENCE = (
    "- **不准動**：核心（`tianxia/core/`）、殼（`server.py`、`web/app.js`、`web/main.js`、`web/shell.js`、`web/style.css`、`index.html`）、`tests/core/shell_tables.py`、`tests/conftest.py`、資料庫結構（第 9 版）、"
    "identity 與 terms 兩包、兩份設定覆寫檔（開關那一筆已經放好，不再改）。要動才做得完就停下來寫 stopped。任何畫面、API 回應、主控台輸出都不能讓人分出誰是假人（`tests/bots/test_server_bots.py` 的 `leaks()` 掃得到你新加的輸出）。"
    "各包 README 自己填；`docs/guide`、手冊、`CLAUDE.md`、主機端操作文件不動，句子放回報的 docs。新字每一句旁 `待 joy 潤`，`new_strings` 逐句列（改舊句的寫「舊 → 新」）。"
    "這台同時有別的線在跑：重的東西跑一次就好；起伺服器一律暫存資料庫、模型網址 127.0.0.1:9、不碰 7861；跑 `same_behavior`、`webqa` 時環境裡不要有 `TIANXIA_DB`、`TIANXIA_SUPPORT`、`TIANXIA_PROFILE`。"
)


def ab(n, title, pkg, dev, ports, body):
    plan = f"docs/superpowers/plans/2026-11-20-客服上線-第{n}批.md"
    return batch(n, f"客服上線第 {n} 批：{title}", pkg, dev, plan, ports, body + [AA_BACKGROUND, AA_FENCE], custom=True)


def b228():
    return ab(228, "管理者帳號列在名單上也進得了客服頁、上傳先擋再讀、兩句在只開真人時說不對的字、改版資訊、鎖設定的測試", "support", "dev/support-on-228", "8467", [
        "- 先讀 scope 的 `staff-desk`、`player-surface`、`abuse-and-data` 與 `gaps`。這一批動 `tianxia/features/support/`（含它的 `tests/`）、`web/support.js`、`web/support.css`、`web/admin.js`（只為①，PM 准這一次）、`content/patch_notes.json`、`tests/core/test_content.py`（只加⑤那一條）。",
        "- **①管理者帳號列在客服名單上，也進得了客服頁**。現況（先自己證實）：伺服器那一側 `_staff` 不排除管理者；主機文件也寫「管理者本人不自動算客服，要列在名單上才是」。但畫面上 `web/admin.js` 的 `renderAdmin` 只在 `!S.main.admin && S.main.support_staff` 時畫客服頁，設定抽屜（`web/app.js`，殼，不准動）對管理者只給「管理者工具 ›」——所以企劃者本人（管理者）列進名單也沒有任何入口看單。"
        "要的結果：`S.main.admin && S.main.support_staff` 的人有一個入口進客服頁，進去之後重新整理、點單、回覆、結單、查帳號都留在客服頁（重畫之後不會掉回管理者頁）、有路回管理者工具；**管理者不在名單上時管理頁一個位元組都不變**；不是管理者的客服照舊。"
        "最小做法由你定（不碰殼）：例如管理頁頂上那一列在 `support_staff` 時多一顆「客服單 ›」（連到 `/admin#support`），`renderAdmin` 在網址帶這個錨點時畫客服頁，客服頁頂上對管理者多一顆回管理者工具；用什麼做法、為什麼寫進 decided。"
        "測試（node 的網頁測試，加在 support 包現有的網頁測試檔）：`test_admin_on_the_staff_list_reaches_the_desk`、`test_desk_stays_the_desk_for_an_admin_after_refresh_and_actions`、`test_admin_not_on_the_list_sees_the_same_admin_page`（管理頁的 html 跟改之前逐字一樣）、`test_staff_who_is_not_admin_still_lands_on_the_desk`。`web/admin.js` 是 admin 包的檔：改完跑 `scripts/test_for.py` 挑到的 admin 測試。",
        "- **②截圖上傳在讀本體之前先擋**（`routes.py::api_support_file`）。現況：認了登入就開始串流讀，最多讀到 `file_bytes_max`，之後 `_upload` 才看單在不在、是不是自己的、結了沒、張數滿了沒——沒有單的人、張數滿了的單、`files_max` 是 0 時，照樣讓伺服器整張讀進記憶體。"
        "改成讀本體之前先做一次便宜的預檢（sqlite 那一下丟執行緒池）：`files_max` 是 0、單號不是數字、旁檔不在、單不在或不是自己的、單結了、張數已滿，各回**跟現在 `_upload` 與 `add_file` 回的同一句、同一個狀態碼**（逐一對現在的回應，位元組一樣；別人的單與不存在的單照舊同一句 404）。預檢過了才讀本體；`add_file` 交易裡原本的檢查原樣留著（兩個請求同時來時靠它）。Content-Length 說超過就提早拒的那一段照舊、順序你定但要寫進 decided。"
        "測試（`test_support_files.py` 或現有測上傳的那個檔）：每一種拒絕各一條 `test_upload_refuses_<原因>_before_reading_the_body`，用一個會記下「有沒有被讀」的本體產生器證明沒讀；一條 `test_upload_replies_are_the_same_sentences_as_before`（六種拒絕的狀態碼與內文對改之前的字面）；現有上傳測試一條不改就綠。",
        "- **③兩句在「只開真人」時說不對的字**（都標 `待 joy 潤`、進 new_strings 寫舊 → 新；斷言舊字的測試跟著改）：(a) `rules.TOO_MANY_OPEN`「已經有 {n} 張還沒結的單，等客服回覆或結單之後再送。」——已回覆的單也算沒結（`store` 數的是 `status != closed`），玩家自己結不了，「等客服回覆」這半句不對。改成「已經有 {n} 張還沒結的單，等其中一張結了再送。」"
        "(b) `web/support.js` 客服頁讀不到那一行（第 226 批）「…剛用驗證碼登入的話，請改用帳號密碼重新登入。」——identity 關著時沒有驗證碼登入，真正的原因多半是客服這次登入超過 `identity.staff_hours`（6 小時）。改成「讀不到客服單，請按重新整理；還是讀不到，請登出再用帳號密碼登入一次（客服的登入每隔幾小時要重來）。」`git grep` 這兩句舊字在 `docs/support/`、README、測試、`scripts/` 還有沒有別處抄著，測試與 README 一起改，`docs/` 的寫進回報的 docs。",
        "- **④改版資訊**：`content/patch_notes.json` 最前面加一筆（格式照檔頭 `_說明` 與現有幾筆；日期寫 `11/20`，回報的 docs 寫一句「日期照 Joy 實際部署那天改」）：`new` 一行「客服：設定裡多一個「客服」，可以寫單、附截圖，客服回覆了會通知你。」（進 new_strings，待 joy 潤）。先 `git grep patch_notes` 看哪些測試鎖最新一筆的日期或條數（客服單的版本欄讀最新日期），照著改到綠；`scripts/test_for.py` 會帶真實內容那幾條。",
        "- **⑤鎖設定的測試**：`tests/core/test_content.py` 的 `ONLINE_PROFILES` 那幾條旁邊加 `test_online_profiles_open_only_the_human_half_of_support`：week7、season21 兩份 `support.enabled` 是 True、`support.bot_account == \"\"`、`identity.enabled` 是 False；`config.json` 那一層 `support.enabled` 是 False。docstring 寫明：客服官 token 那條路一律 404 靠 `bot_account` 空著；之後要開客服官或帳號綁定的那一批改這一條。",
        "- **拍圖自驗**（照介面設計規範第八節：375 淺、375 深、1280；存 `" + AA_SHOTS + "\\b228\\shots\\`、路徑寫進回報）：暫存資料庫起 8467、`TIANXIA_PROFILE=week7`、模型網址 127.0.0.1:9；客服名單只對這一個暫存行程用環境變數 `TIANXIA_SUPPORT` 給（測完那個行程就關，不寫進任何檔）。拍：玩家的設定抽屜（多「客服 ›」）、寫單頁、看單；不是管理者的客服的客服頁；**管理者列在名單上**的入口與客服頁；管理者不在名單上的管理頁（對改之前要一樣）；客服頁讀不到的那一行。拍完 `taskkill /T`、刪暫存。",
        "- **不做**：自動結單排程（只開真人時靠客服開客服頁那一下掃，企劃者知道）、「再回一句」的頻率上限、identity 關著時名號可以取「客服」、條款第十節的字、`staff_hours`、名單檔的 BOM（在核心）、`scripts/sb`、`scripts/webqa`（另外兩批在做）。退版：沒有新欄位、新表；`web/admin.js`、`web/support.js`、`routes.py` 三處退回就是舊樣子；季中能換；緊急開關 `support.enabled` 設 false 重開兩個程式（旁檔與截圖留著不讀），只停截圖是 `support.files_max` 設 0。",
    ])


AB_NOTE = [
    "- **這一批改的是工具，不是遊戲**：只准動派工單點名的 `scripts/` 那一塊與它的測試；`tianxia/`、`web/`、`content/`、`server.py`、設定覆寫檔一個字不動。**上面波次模式寫的「你不跑 same_behavior compare」「不跑 selftest」對這一批不適用**：把工具跑到穩就是這一批的工作。改情境去配合遊戲，不改遊戲去配合情境；除了派工單明寫的「關著段」，不准在情境或 `serve.py` 把正式設定開著的包關掉。",
]


def b235():
    return ab(235, "same_behavior 的 petition 軌：關著段在記憶體關、加開著段真的走到寫單、回覆、客服看單與結單", "core_shared", "dev/tools-petition-235", "8468", [
        "- 先讀 scope 的 `compare-tracks` 與 `gaps`。**PM 已定，不照查案員的「`Scenario.__init__` 一律把客服關掉」**（懷疑者說得對：那樣線上開著的樣子只剩一軌在比）。做法是閘門拿「開關那一筆」當 base、兩邊客服都開著，其他軌就照線上的樣子（season21、week7 客服開著）在比；所以這一批**只動 `scripts/sb/tracks/petition.py`**（與 `tests/core/` 裡守它的測試、covers 的登記），`scripts/sb/base.py`、`harness.py` 不動（`_wipe_db` 少 `mail` 是舊洞，寫進 leftovers）。",
        "- **①關著段**照第 232 批定的規矩（讀 `charter`、`letter`、`oath` 三軌怎麼寫的，照樣）：setup 先在記憶體把 `Config.support.enabled` 關掉，再走現在那一段（登入的人打十三條、沒登入的人打 `mailbox`、`/api/main`、`/api/push`）。三種設定走出來都是「關著」，test 設定的輸出跟改之前逐位元組一樣（改前改後各跑一次 test 設定對 sha）。",
        "- **②開著段**（在記憶體打開；客服名單只用記憶體裡的 `Config.support.staff` 指到情境裡一個不是管理者的帳號，段落結束還原；這一軌從頭到尾把另外兩個名單來源隔掉——環境變數 `TIANXIA_SUPPORT` 拿掉、`tianxia.content.LOCAL_DIR` 指到不存在的資料夾〔`identity_base.support_file` 每次現讀它〕，結束還原）。照真人會走的順序，每一步把狀態碼與回應寫進輸出："
        "玩家寫單（每種類別至少一張）、`/mine`、再回一句；被擋的每一種（空的、太長、沒有這種類別、第 4 張沒結的單）；`/api/main` 的 `support_unread`；不是客服的人打客服那幾條（要 404）；客服（**先重新密碼登入**：identity 關著時 `staff_session_ok` 看這次登入多久以前，情境的假時鐘每步 60 秒，超過 6 小時會靜靜變成 404——所以每次客服動作前先印 `queue` 的狀態碼，不是 200 就讓情境直接丟錯，不要空走）看佇列、看單、回覆並等玩家、內部註記、回覆並結單、查帳號（查得到、查無）、`sweep`；玩家這邊看到未讀、輪到自己那一回合江湖紀錄多一則、讀了之後歸零；玩家對自己的單打 `/api/support/human`（沒有客服官時會怎樣照實印）；帶 `Authorization: Bearer x` 打任何一條（要 404）；上傳只打一次「不是圖」的小本體看拒絕（**不真的存圖**：存了會多一個 `-support-files/` 資料夾，`_wipe_db` 不清它）。"
        "段落結束把旁檔 `<db stem>-support.sqlite` 每張表的內容算進輸出（仿 `charter` 的段落收尾；不在就寫「不在」）。",
        "- **③輸出要穩**：客服單的時間用的是 `shell.time.time()`——先看情境的假時鐘蓋不蓋得到它（`letter` 軌的信也有時間，看它怎麼辦）；蓋不到的欄位照別的軌的做法處理，寫進 decided。前半停點與後半接續（`resume`）照 `charter` 的寫法：開關與名單在 resume 之後要重新設。",
        "- **④驗**：`petition` 三種設定各跑 `selftest`（跑兩次一樣、前半加後半等於整段、改一個字抓得到；「改一個字」的目標句要落在開著段走得到的句子上）。`ALWAYS_TRACKS` 六軌在 season21 各跑一次 `selftest`——**這是客服開著之後這六軌第一次跑**，紅了先分清楚是情境要跟著改還是遊戲真的壞了（後者停下回報，不改遊戲）。`covers`：`scripts/sb/covers_measure.py measure` 只量 `petition`（三設定）→ analyze 結束碼 0 → 寫回；守 covers 的那幾條測試跑過。docstring 與軌的說明字改成現在走的東西，寫明走不到什麼（截圖、客服官）。",
        "- 時間上限兩段合計 2.5 小時；到了就把修好的推上去、交，沒做完的寫 leftovers（哪一步、倒在哪、你的判斷）。",
    ] + AB_NOTE)


def b236():
    return ab(236, "網頁走查：客服開著之後 main 回合照樣穩，加客服的景（我的單、寫新單、看單、客服頁）", "core_shared", "dev/tools-webqa-236", "8469", [
        "- 先讀 scope 的 `web-walkthrough` 與 `gaps`，再讀第 233、234 批的計畫與回報（`docs/superpowers/plans/2026-11-19-工具修復-第233批.md`；第 234 批：`flow` 用 `fast_forward` 推時鐘之前要 `c.leave()`、收養之後的「接著走」）。只動 `scripts/webqa/` 與 `tests/web/test_webqa.py`。",
        "- **①先量**：基準已經把客服打開，所以每一個開著設定抽屜的景都多一行「客服 ›」、推播設定多一個「客服」勾選。要確定兩件事：(a) main 回合的 `crawl`（開抽屜之後照畫面上的鈕走的那一段）會不會自己點進客服頁——讀 `driver.mjs`／`flows/main.mjs` 的 crawl 怎麼挑鈕、排除哪些；(b) 客服頁上有沒有每次跑都不一樣的字（單的時間 `supportWhen`、版本欄）。用 `--only` 加 `--quick` 只跑到抽屜那幾景（第 234 批的跑法），不要一上來就跑整回合。",
        "- **②讓它穩＋加景**：crawl 會點進客服頁的話，照工具現有的做法把它定下來（排除或固定走法，寫進 decided）。在 main 回合開抽屜之後加最短的幾步：點「客服 ›」拍「我的單」（空的）、切到「寫新單」拍、送一張文字單（不附圖）之後拍看單；客服那一側：比照 `common.mjs` 設管理者的做法，**只在走查自己起的兩個伺服器行程裡**把一個不是管理者的走查帳號放進客服名單（記憶體裡的 `Config.support.staff`；base、head 兩邊同樣做；不寫任何檔、不設環境變數），用它登入（密碼登入、剛登入）到 `/admin` 拍客服頁（四格數字加清單）、點那張單拍、回覆之後回玩家那邊拍抽屜的紅點。會變的字（時間）照工具現有的遮法處理，**不改 `web/`**。景名加進 `must_reach.txt`（用 `gate.py` 現成的寫法產生，不手改——先看第 234 批怎麼加的）。`coverage.py check` 要過；`web/support.js`、`support.css` 的登記跟現況一致。",
        "- **③驗**：main 回合整回合自己對自己跑一次（`gate.py --base <head> --head <head> --rounds main --ports 8474,8475 --cdp-ports 8476,8477 --jobs 1`，`Start-Process` 分離啟動、輸出導到檔、`docs/superpowers/pm-workflows/wait_file.py` 等）：exit 0、0 real、`missing_must_reach` 空、主控台 0 錯誤。x 回合（也開抽屜）用 `--only` 跑到抽屜那幾景確認穩。`tests/web/test_webqa.py` 跑過。第 234 批留下的 c 回合 `029_bt_watch_shut` 偶發 1 張：有剩時間才看（先讀 `flows/c.mjs` 那一段推時鐘之前有沒有 `c.leave()`），沒時間就照舊留在 leftovers。",
        "- **不做**：week7 的走查（工具只走 season21，寫進 leftovers）；管理者列在名單上的入口（第 228 批同時在做，下一次再加景）；截圖上傳的景。時間上限兩段合計 3 小時（整回合一次約 37 分鐘，別跑第三次）；到了就把修好的推上去、交。",
    ] + AB_NOTE)


WEB_AA = (
    "**這一波把真人客服打開（week7、season21；identity 關、沒有客服官）**。用 head 的程式起暫存伺服器實機看，不是只看比對。都不花 token：`Start-Process` 分離啟動、輸出導到檔，`docs/superpowers/pm-workflows/wait_file.py <檔> 570` 等，**不要前景跑**；暫存資料庫、模型網址 127.0.0.1:9、拒絕 7861；客服名單只用環境變數 `TIANXIA_SUPPORT` 給那一個暫存行程，不寫任何 `.local/`。\n"
    "1. 閘門的網頁比對（`.local/wave_gate/<head8>/web/report.txt`）：這一關不重跑，只看 real 是 0、`missing_must_reach` 空；有 real 逐張判是不是工具的事。\n"
    "2. `TIANXIA_PROFILE=season21` 起一台（做完再用 `week7` 起一台走同樣的步驟）：(a) 一般玩家：設定抽屜有「客服 ›」；我的單是空的；寫新單頁的類別、字數、截圖提示（3 張、3 MB）；附一張小圖送出，看單有縮圖；通知設定多一個「客服」勾選。(b) 不是管理者的客服帳號（密碼登入）：抽屜頂上「客服單 ›」、客服頁四格數字與清單、點單、回覆並等玩家、回覆並結單、用帳號查帳號；回到玩家：⚙ 與「客服 ›」有紅點、點進去歸零。(c) 管理者帳號列在名單上：有入口進客服頁、回覆之後還在客服頁、回得去管理者工具；管理者不在名單上：管理頁沒有任何客服的東西。(d) 不在名單上的帳號直接打 `/api/support/queue` 回 404；帶 `Authorization: Bearer x` 打 `/api/support/queue` 回 404；登入頁沒有客服信箱那一行。(e) 整個過程畫面上沒有「找真人」鈕、沒有「客服官」「自動回覆」字樣（自動結單那一則除外，這一關不會出現）。\n"
    "3. 設定覆寫暫時把 `support.files_max` 設 0 重起（只改你暫存的那份樹，不提交）：寫新單頁沒有「附截圖」，送單正常；直接打上傳那條路被拒。\n"
    "4. 每一頁照介面設計規範第八節看 375 淺、375 深、1280：字不擠出框、可點的至少 44px、深色看得清；截圖存你的暫存夾、路徑寫進回報。任何一頁、任何回應分得出誰是假人就是 blocker。"
)

AA_FEATURE_LENS = dict(key="feature", text=(
    "**打開真人客服：開的只有真人那一半、沒碰不該碰的、看不出假人**。第 228 批與 PM 的「開關那一筆」（這條線 base 那一筆：`git show <line base>`）；查案原文 " + AA_SCOPE + "。親自驗："
    "①開關那一筆只動兩份設定覆寫檔（各一個 `support` 鍵、只有 `enabled`）與 `test_support_smoke.py`；用一行 Python（`TIANXIA_DB` 設到你的暫存檔）載 season21、week7：`support.enabled` True、`bot_account` 空字串、`identity.enabled` False，`config.json` 那一層 `support.enabled` False。"
    "②核心、殼、`shell_tables`、`conftest`、資料庫結構、identity、terms 沒有動；`web/admin.js` 的改動只為了管理者進客服頁，**管理者不在名單上時 `renderAdmin` 畫出來的 html 跟 base 逐字一樣**（讀程式並看那條測試真的在比）。"
    "③上傳預檢：六種拒絕的狀態碼與內文跟 base 的字面一樣（別人的單與不存在的單同一句 404，不洩漏單在不在）；`add_file` 交易裡的檢查還在；預檢沒有開新的旁檔、沒有在行動鎖裡做慢事。"
    "④改的兩句字與改版資訊那一句旁有待 joy 潤、進了 new_strings；改版資訊沒有寫機率、戰況、任何跟假人有關的字。"
    "⑤客服頁（含管理者進去的那一種）與查帳號的卡，沒有任何欄位、任何缺欄位分得出假人；`leaks()` 掃得到新加的輸出。"
    "⑥鎖設定的那一條測試真的會紅：暫時把 week7 的 `support` 加上 `bot_account` 跑一次看它紅（看完還原，不提交）。"
))
AA_TOOL_LENS = dict(key="tools", text=(
    "**客服的比對軌與走查景：改情境去配合遊戲，沒有反過來；真的在比東西**。第 235、236 批。親自驗："
    "①兩批只動 `scripts/sb/tracks/petition.py`、`scripts/webqa/` 與它們的測試、計畫檔。"
    "②petition 的關著段在 test 設定的輸出跟改之前一樣；開著段每一個客服動作前都印了 `queue` 的狀態碼而且是 200（挑一種設定讀輸出，確認「寫單、回覆、客服看單、結單、查帳號、未讀歸零」每一步的回應真的在輸出裡，不是 404 空走）。"
    "③客服名單只在記憶體裡設、段落結束有還原；`TIANXIA_SUPPORT` 與 `LOCAL_DIR` 的隔離有還原；沒有任何地方寫 `.local/`。"
    "④除了 petition 的關著段，沒有任何一軌、`serve.py` 的任何設定把正式設定開著的包關掉（grep `enabled` 在兩批的 diff 裡的每一處）。"
    "⑤走查加的景都在 `must_reach.txt`、`coverage.py check` 過；會變的字是用工具的遮法處理，不是改 `web/`；crawl 的走法是定下來的（讀程式）。"
    "⑥`ALWAYS_TRACKS` 六軌在客服開著的 season21 跑得過（開發的回報裡有證據；沒有就自己挑兩軌跑 `selftest`）。"
))

WAVES["AA"] = dict(
    round2=True, feature=True, design=T_DESIGN, new_packages="identity,support,terms", new_existing=True,
    extra_lenses=[AA_FEATURE_LENS, AA_TOOL_LENS],
    lines=[dict(name="開客服", batches=[b228])],
    merge_port=8470, fix_port=8471,
    web_check=dict(ports="8472、8473", steps=WEB_AA),
)
WAVES["AB"] = dict(
    round2=True,
    lines=[dict(name="客服比對軌", batches=[b235]), dict(name="客服走查景", batches=[b236])],
    merge_port=8478, fix_port=8479,
)


# ── AC 波：客服上線之後的工具批（PM 2026-11-20；企劃者 11/20「繼續」）：重放的假紅 237、走查補客服兩景 238、比對工具清旁檔與上傳 239 ──
# 三條線都只改工具（scripts/webqa、scripts/sb 與它們的測試），基準是 develop；收尾一次合、一次驗。
AC_PROBE = r"C:\Users\ray61\AppData\Local\Temp\claude\81800b313c89d0f8\ade93b70-b3b7-42db-a8af-21f7a7cbdb16\scratchpad\waveAA"
AC_NOTE = [
    "- **背景（三批共用）**：AA 波 2026-11-20 把真人客服在 week7、season21 打開（`support.enabled` 開、`bot_account` 空、identity 關），進了 `develop`。那一波閘門的網頁比對紅了 3 張，PM 查證後認定是工具的假紅才放行；"
    "經過在 `docs/superpowers/plans/2026-11-20-波次AA紀錄.md` 最後一節「PM 的認定」與手冊第十五節「AA 波的 PM 認定」，留下的小件在交接第八節「AA 波留下的」。**動手前先讀紀錄最後一節**。"
    "查證留下的材料（只讀，不要改、不要刪）：`" + AC_PROBE + r"\probe-replay\`（單景重放的小腳本 `probe.py`、`analyze.py`、每一組的 `result-*.json`、只有鐵匠鋪幾景的小語料 `corpus-*`）、`" + AC_PROBE + r"\probe-live\`（真頁面的實拍與放大圖）。"
    "上面「計畫不超過 120 行」照舊，寫在 `plan` 那個路徑。這一批不做派工單沒寫的事，碰到了寫 leftovers。",
    "- **這台同時有另外兩條工具線在跑**：重的東西（整回合走查、全量重放、全軌比對）跑一次就好，不要為了保險再跑；起伺服器一律暫存資料庫、模型網址 127.0.0.1:9、只用派工單給的埠、不碰 7861；"
    "跑 `same_behavior`、`webqa` 時環境裡不要有 `TIANXIA_DB`、`TIANXIA_SUPPORT`、`TIANXIA_PROFILE`；不讀不寫任何 `.local/` 的檔（閘門結果夾 `.local/wave_gate/<head8>/` 只准讀）。"
    "長的指令用 `Start-Process` 分離啟動、輸出導到檔、`docs/superpowers/pm-workflows/wait_file.py <檔> 570` 等，不要前景跑。任何輸出都不能讓人分出誰是假人。",
]


def ac(n, title, dev, ports, body):
    plan = f"docs/superpowers/plans/2026-11-20-工具批-第{n}批.md"
    return batch(n, f"工具批第 {n} 批：{title}", "core_shared", dev, plan, ports, body + AC_NOTE + AB_NOTE, custom=True)


def b237():
    return ac(237, "網頁比對的重放：同一景自己的畫法抖動不再算成真的差（鐵匠鋪打造那幾景的假紅），紅景留原圖", "dev/tools-replay-237", "8488～8491", [
        "- **只動** `scripts/webqa/replay.py`、`replay.mjs`、`compare.py`、`noise.py`、`gate.py`、`selftest.py` 與 `tests/web/test_webqa.py`、計畫檔。**不動** `flows/`、`driver.mjs`、`must_reach.txt`、`coverage.json`（第 238 批同時在改）；`tests/web/test_webqa.py` 的新測試放在現有重放／雜訊那幾條旁邊，不放檔尾（兩批同時改這個檔，放檔尾會撞）。",
        "- **起因（PM 查證過的事實，數字在紀錄裡）**：重放（同一份 DOM 快照分別套 A、B 兩邊的樣式表、不跑頁面腳本、dpr 1 重畫）在鐵匠鋪打造那幾景（main 回合 044～047）每個視窗有兩三種畫法、隨機出現：圓鈕上緣的弧線差 1 級、素材小圖的邊差到 40 級。"
        "045 的 375 深色那一種剛好 102 px（門檻 100 px）、375 淺色 40 級（門檻 12 級），所以兩次閘門都紅在同一格。兩邊套**同一份**樣式表（A 對 A）也紅（5 次 3 次）；兩邊 367 個元素 × 413 項計算樣式 0 差；真頁面逐像素 0 差。044、046、047 也抖，只是沒過門檻。",
        "- **①判法**：重放裡「`clean`（DOM 與計算樣式兩邊一致）、不 `unstable`、只差像素、超過 aa 門檻」的那種差，不直接算 REAL，先分清楚是不是這一景自己的畫法抖動。PM 建議的判法（你讀完程式有更穩的可以換，寫進 decided 說為什麼）："
        "對這一張，兩邊各自重新載入重畫幾次（次數上限寫成常數，例 4 次），收集每一邊出現過的圖的雜湊；兩邊的集合有交集（A 邊畫得出 B 那一張，或反過來）就歸成新的一類雜訊（取個名字，例 `render-variants`，補進 `noise.py` 檔頭那張表、`summary.json` 的 noise 計數與 `report.txt`）；重畫完仍然不相交才是 REAL。"
        "**不准做的**：放寬 aa 門檻（100 px、12 級一個字不動）、把鐵匠鋪的景列成白名單或例外、改走查（真伺服器那一段）的判法、把有樣式差（`clean` 不成立）的差也拿去重畫——那種照舊直接 REAL。",
        "- **②紅景留原圖**：REAL 的像素差在 `red/` 除了現在那張縮小的 A|B 拼圖，另外存 A、B 原尺寸各一張（檔名看得出哪一邊）；`report.txt` 那一行後面帶檔名。查證時發現 `report.txt` 不列每一條雜訊是哪一景：看 `summary.json` 有沒有逐景的雜訊列，有就在 `report.txt` 的 noise 那一行後面寫一句去哪裡看，沒有就補上（景名、視窗、類別、像素數、級數）。",
        "- **③說清楚重放看不到什麼**：重放的 DOM 快照來自 base 那一邊的走查，head 才畫得出來的元素（AA 波的 `.sup-admin-entry`）不在快照裡，針對它寫的樣式重放驗不到。這件不修，只在 `gate.py` 檔頭那段說明與 `report.txt` 的 replay 那一行各補一句（英文，照檔裡現有的口氣）。",
        "- **④驗**：(a) 用查證留下的小語料或自己走一小段（`gate.py --rounds main --only gate,accounts,prep,opening,rich,week1,battle,week2,news2,smith --no-replay --keep-corpus <你的暫存夾>`，約 10 分鐘；base `3a6af3ac1c7494773598b3a0b7a722c994888a9f`、head `b1f86defbe388ab38dc844bfa857ac8bd7725654`，兩邊只差 `web/support.css` 三行）對 044～047 四景做 A 對 A、A 對 B 各至少 10 次：改之前會紅的（把次數寫進回報），改之後 0 REAL、歸到新的那一類。"
        "(b) **靈敏度不能掉**：`selftest.py` 現有的每一種突變（`--mutate card-padding`、`css-last`、`pkg-css`、`css-comment`、`page-hang`、`page-alert`）改前改後結果一樣，該紅的照紅；另外自己做一個「計算樣式不變、像素真的變」的突變在重放驗一次（例：把一張素材圖檔換成另一張的內容、或把 `@font-face` 的檔換掉）——要判 REAL；真的做不出這種突變就寫進 leftovers 說試了什麼。"
        "(c) 量重放多花多少：只有紅候選才重畫，整趟應該只多幾十秒以內；超過就說明。(d) `tests/web/test_webqa.py` 補純函式那一層的測試（集合有交集 → 雜訊；不相交 → REAL；`clean` 不成立 → 不重畫直接 REAL）。`scripts/test_for.py` 挑的跑過。",
        "- 時間上限兩段合計 3 小時（全量重放不要跑超過一次）；到了就把修好的推上去、交，沒做完的寫 leftovers。",
    ])


def b238():
    return ac(238, "網頁走查補客服兩段：名單上的管理者從管理頁進客服頁、寫單附截圖；名單的放與還包起來；c 回合觀戰那一張偶發差", "dev/tools-webqa-238", "8492～8495", [
        "- **只動** `scripts/webqa/flows/`、`driver.mjs`、`snippets.mjs`、`must_reach.txt`、`coverage.json`（真的要才動）與 `tests/web/test_webqa.py`、計畫檔。**不動** `replay.py`、`replay.mjs`、`compare.py`、`noise.py`、`gate.py`、`selftest.py`（第 237 批同時在改）；`tests/web/test_webqa.py` 的新測試放在現有客服那一條（`test_main_walks_support…`）旁邊，不放檔尾。",
        "- 先讀第 236 批的計畫與回報（`docs/superpowers/plans/2026-11-20-客服上線-第236批.md`）與 `flows/main.mjs` 客服那一段（約第 780～815 行：`sup_mine`…`sup_ticket_read` 十景，客服是 `qaplayer4`，用 `c.py` 只在走查伺服器的記憶體裡放進 `content.config.support.staff`、做完還原）。",
        "- **①名單上的管理者從管理頁進客服頁**（第 228 批做的入口，還沒有景）：在客服那一段後面加——把走查的管理者帳號也放進名單（同樣只在記憶體）、用密碼重新登入（`ctx.relogin`；客服權限看這次登入多久以前）、載 `/admin`：拍頂列有「客服單 ›」的管理頁（**375 寬是重點**：第 228 批在 `web/support.css` 加的兩條 `.ad-head:has(.sup-admin-entry)` 只在這個畫面生效，讓「管理者工具」不折行；重放的快照來自 base、看不到它，只有這一景拍得到）、"
        "點進客服頁拍（網址變成 `/admin#support`）、點「‹ 管理者工具」回管理頁拍。另外拍一張「管理者不在名單上」的管理頁頂列（沒有入口）如果現有的管理頁景已經涵蓋就不重拍、寫進 decided。",
        "- **②寫單附截圖**：寫新單頁挑一張小圖（走查裡現場生成固定內容的小 PNG；用 CDP 的 `DOM.setFileInputFiles` 或 driver 已有的做法——先看 `driver.mjs` 有沒有現成的），拍「挑了圖、還沒送」、送出後拍「單內有縮圖」，客服那一側看單拍「客服看得到縮圖」。圖存在走查伺服器暫存資料庫旁邊的資料夾，回合結束整個暫存夾本來就會清；縮圖的網址（單號、檔號）兩邊要一樣，不一樣就照工具現有的遮法處理、寫進 decided。注意玩家同時最多 3 張沒結的單（現有的景已經送過一張）。",
        "- **③放名單與還原之間包起來**（AA 波審查的小件）：`c.py` 把人放進名單之後、還原之前任何一步丟例外，還原那一行現在不會跑；包成 try/finally（①加的管理者也一樣）。`tests/web/test_webqa.py` 現有那一條守「名單有還原」的測試跟著改成看得出 finally。",
        "- **④登記**：新景手加進 `must_reach.txt`（照第 236 批放的位置接著放），`coverage.py check` 過；`tests/web/test_webqa.py` 守景名與順序的那一條補上新景。",
        "- **⑤驗**：main 回合整回合自己對自己跑一次（`gate.py --base <你的 head> --head <你的 head> --rounds main --ports 8492,8493 --cdp-ports 8494,8495 --jobs 1`）：exit 0、0 real、`missing_must_reach` 空、主控台 0 錯誤；新景每一張自己看一眼（375 淺、375 深、1280），截圖裡看得到該有的東西（頂列的鈕、縮圖），路徑寫進回報。",
        "- **⑥還有時間才做**：c 回合 `029_bt_watch_shut`（`flows/c.mjs` 約第 234 行）偶發 1 張像素差（X 波第 234 批留的；景與景之間沒有推時鐘，原因不明）：`--rounds c` 自己對自己跑 3 次，記重現幾次、哪一張、差在哪個框；看得出原因（動畫沒凍住、倒數的字、捲動位置）就改走法，看不出就寫 leftovers，不要為了它超時。",
        "- **不做**：week7 的走查（工具只走 season21）；改 `web/` 的任何檔（客服頁小鈕 38px 那些是畫面的事，不在這一批）。時間上限兩段合計 3 小時（整回合一次約 40 分鐘，main 不要跑第三次）；到了就把修好的推上去、交。",
    ])


def b239():
    return ac(239, "前後比對：重跑前把帖友書信的旁檔與客服截圖夾清掉；petition 軌走到上傳截圖與自動結單", "dev/tools-wipe-239", "8496", [
        "- **只動** `scripts/sb/harness.py`（只准動 `_wipe_db` 與它旁邊的註解）、`scripts/sb/tracks/petition.py`、`tests/core/` 裡守它們的測試、covers 的登記、計畫檔。`scripts/sb/base.py` 與別的軌不動；`scripts/webqa/` 不動（另外兩批在改）。",
        "- 先讀第 235 批的計畫與回報（`docs/superpowers/plans/2026-11-20-客服上線-第235批.md`）：petition 軌現在有關著段與開著段，名單只認記憶體裡的 `Config.support.staff`，`TIANXIA_SUPPORT` 與 `LOCAL_DIR` 整軌隔掉；它留下的：`_wipe_db` 沒清帖友書信的旁檔與截圖夾、截圖真的存檔、3 天自動結單、一天幾張的上限、客服官 token 都走不到。",
        "- **①`_wipe_db`**（`harness.py` 約第 507 行）：那張 `sides` 清單少了帖友書信（mail 包）的旁檔與它的封存、客服的截圖資料夾（`<db stem>-support-files/`，是資料夾，用 `rmtree`）。先 grep `tianxia/features/*/` 與核心，把「會在資料庫旁邊建檔或建資料夾」的地方全部列出來對一次清單（列進計畫），該清的補齊；"
        "`_db_files` 上面那段註解說 `-vapid.pem` 與 `.db.<軌>.json` 為什麼不在清單，照它的理由判斷新找到的要不要清，寫進 decided。能寫一條測試鎖住「清單跟包實際會建的對得上」就寫（對不上就紅），寫不出來就照名字列、說明為什麼。",
        "- **②petition 開著段加上傳截圖**：玩家對自己的單傳一張固定內容的小 PNG（位元組直接寫在軌裡）、傳到超過張數被擋、不是圖的檔被擋、傳到別人的單與不存在的單（同一句 404）；`/mine` 與看單回應裡的檔案欄位；客服看圖那一條的狀態碼、`Content-Type` 與 `X-Content-Type-Options`；不是客服也不是主人的人看圖（要被擋）。每一步的狀態碼與回應寫進輸出；段落收尾把旁檔的 `files` 表與截圖夾裡的檔名、大小算進輸出。輸出要穩：檔名或欄位帶隨機字、時間的，照別的軌現有的做法處理，寫進 decided。",
        "- **③自動結單與一天上限**（走得到才做）：情境的假時鐘推得到「客服答覆之後 3 天」就加一步——客服打開佇列的那一下掃到、單變成已結、多一則系統回覆、不推播；一天幾張的上限同理（送到被擋的那一句）。假時鐘蓋不到客服單用的時間（第 235 批回報有寫它怎麼處理時間）就不硬做，寫進 leftovers 說卡在哪。客服官 token 這一軌照舊不走（`bot_account` 空著是線上的樣子）。",
        "- **④驗**：`petition` 三種設定各跑 `selftest`（跑兩次一樣、前半加後半等於整段、改一個字抓得到）；**同一個暫存資料夾連跑兩次**確認第二次不會讀到第一次留下的截圖與信（這就是①要修的洞，改之前先重現一次、把現象寫進回報）。`harness.py` 每一軌都用：`ALWAYS_TRACKS` 六軌加 `letter`（帖友書信）在 season21 各跑一次 `selftest`，再隨機挑 3 軌跑；紅了先分清楚是①改壞的還是本來就有的。"
        "`covers`：`scripts/sb/covers_measure.py measure` 只量 `petition`（三設定）→ analyze 結束碼 0 → 寫回；守 covers 與邊界的測試（`tests/core/test_feature_boundaries.py`、`test_same_behavior_gate.py` 等 `scripts/test_for.py` 挑到的）跑過。",
        "- 時間上限兩段合計 2.5 小時；到了就把修好的推上去、交，沒做完的寫 leftovers（哪一步、倒在哪、你的判斷）。",
    ])


AC_TOOL_LENS = dict(key="tools", text=(
    "**工具批：比對沒有變鈍、改情境去配合遊戲沒有反過來**。第 237、238、239 批。親自驗："
    "①三批的 `git diff --stat` 對 base：只動 `scripts/webqa/`、`scripts/sb/harness.py`、`scripts/sb/tracks/petition.py`、它們的測試、covers 登記與計畫檔；`tianxia/`、`web/`、`content/`、`server.py`、設定覆寫檔一個字沒動。"
    "②第 237 批：`noise.py` 的 aa 門檻（100 px、12 級）沒動；沒有任何景名、檔名的白名單；新的那一類雜訊只收「DOM 與計算樣式兩邊一致、而且兩邊重畫的結果有交集」的差，樣式有差的照舊直接 REAL（讀程式逐個分支看）；`selftest.py` 每一種突變改前改後結果一樣（開發的回報要有證據，沒有就自己挑 `card-padding` 與 `pkg-css` 各跑一次）；重畫的次數有上限、不會卡住。"
    "③第 238 批：新景都在 `must_reach.txt`、`coverage.py check` 過；名單只在走查伺服器的記憶體裡放、放與還原之間有 finally；沒有在 `serve.py` 或 flow 裡把正式設定開著的包關掉；上傳的圖是流程裡現生成的固定內容，沒有讀這台機器上別的檔。"
    "④第 239 批：`_wipe_db` 只多清資料庫旁邊、以資料庫檔名開頭的檔與資料夾，不會刪到別的路徑（讀它怎麼組路徑；`rmtree` 的對象逐個看）；petition 加的每一步在輸出裡真的有回應、不是 404 空走；沒有寫任何 `.local/`。"
    "⑤三批的輸出、截圖、報告裡沒有任何一處分得出誰是假人。"
))
WAVES["AC"] = dict(
    round2=True,
    extra_lenses=[AC_TOOL_LENS],
    lines=[dict(name="重放假紅", batches=[b237]), dict(name="走查補景", batches=[b238]), dict(name="比對清旁檔", batches=[b239])],
    merge_port=8497, fix_port=8498,
)


# ── AD 波：企劃者 2026-11-20 傍晚答的三題（PM 用選單問，引號裡是他選的選項原字）：擋冒充客服的名號 240「現在就擋」、條款新版 241「現在就出新版條款」、刪四條啟動測試 242「四條都刪」──
# 三條線互不相干，基準是 develop；收尾一次合、一次驗。條款改版會讓 charter 軌有預期的差：收尾時 PM 另做一筆比對基準（develop 加第 241 批的 terms.json），照 W、AA 波的先例。
AD_SCOUT = r"C:\Users\ray61\AppData\Local\Temp\claude\81800b313c89d0f8\ade93b70-b3b7-42db-a8af-21f7a7cbdb16\tasks\wn60ui6k4.output"
AD_NOTE = [
    "- **背景（三批共用）**：真人客服 AA 波 2026-11-20 在 week7、season21 打開（進了 `develop`、還沒上 `main`）。企劃者 11/20 傍晚答了三題，這一波就是那三題。PM 先派了三位唯讀調查員，結果在 `" + AD_SCOUT + "`（JSON；`result.names`、`result.terms`、`result.tests` 各有 `facts`〔每條附檔名行號與原文〕、`plan`、`risks`）。**動手前先讀你那一批的那一段**；它是讀程式的結論，跟現行程式對不上時照程式、寫進 decided。派工單寫的是 PM 看完調查之後定的做法，跟調查的 `plan` 不一樣的地方照派工單。"
    "上面「計畫不超過 120 行」照舊，寫在 `plan` 那個路徑。這一批不做派工單沒寫的事，碰到了寫 leftovers。",
    "- **這台同時有另外兩條線在跑**：重的東西跑一次就好；起伺服器一律暫存資料庫、模型網址 127.0.0.1:9、只用派工單給的埠、不碰 7861；跑 `same_behavior` 時環境裡不要有 `TIANXIA_DB`、`TIANXIA_SUPPORT`、`TIANXIA_PROFILE`；不讀不寫任何 `.local/` 的檔。任何畫面、API 回應、主控台輸出、腳本輸出都不能讓人分出誰是假人。"
    "各包 README 自己改；`docs/guide`、手冊、`CLAUDE.md`、交接、架構圖不動，要改的句子放回報的 docs。新字每一句旁 `待 joy 潤`（json 裡的字列在回報的 `new_strings`），改舊句寫「舊 → 新」。",
]


def ad(n, title, pkg, dev, ports, body):
    plan = f"docs/superpowers/plans/2026-11-20-客服上線補件-第{n}批.md"
    return batch(n, f"客服上線補件第 {n} 批：{title}", pkg, dev, plan, ports, body + AD_NOTE, custom=True)


def b240():
    return ad(240, "名號不准冒充官方：含「客服」「官方」「管理員」「GM」這類字的名號，取名與易名帖一律擋（不再只在帳號綁定開著時擋）", "core_shared", "dev/names-staff-240", "8507", [
        "- **點頭（動核心）**：企劃者 2026-11-20，PM 問「帳號綁定關著時名號可以取成客服、官方、GM，帖友書信開著有人能冒充客服寄信，要不要現在就擋（擋要動核心取名檢查的一小段，需要你點頭）」，他選「現在就擋」。回報的 `core_changes` 逐檔寫、附這句原話。",
        "- **現況（調查員查的，先自己對一次）**：`tianxia/core/identity_base.py::blocked_name` 已經會擋 `name_base.STAFF_NAMES`（客服、官方、管理員、GM）與 `id:` 開頭，但**只在 identity 開著時**、而且是**全等**（「客服小美」「客 服」「官方客服」都過）。玩家的名號走三條路：殼的 `server.create_character`（`/api/character`）、identity 包建角色（同一支）、商城易名帖（`mall/actions.py::rename_self`，路由傳 `shell.name_taken`；沒傳時的後備 lambda 也叫 `blocked_name`）——三條都經 `server.name_taken` 或那個後備，所以改 `blocked_name` 就全擋到，**`server.py` 與各包的程式不用動**。名號只做 NFKC 與 strip，不限中文（`naming.name_problem` 只管武學、意境的名字）。主機的 `scripts/set_password.py --character` 直接 `Game.new`、不經這條檢查。",
        "- **①`tianxia/core/name_base.py`**：加保留字表 `STAFF_WORDS`（PM 定：`客服`、`官方`、`管理員`、`管理员`、`管理者`、`系統`、`系统`、`營運`、`运营`、`運營`、`营运`）與純函式 `staff_like(name) -> bool`：先 NFKC、casefold，只留 Unicode 類別 L 與 N 開頭的字（空白、標點、符號去掉，所以「客 服」「客．服」「G.M」現形），中文詞用**包含**比對；`gm` 用「前後不接英文字母」的比對（擋 `GM`、`ＧＭ`、`gm小美`、`小美GM`、`G M`；不擋 `Sigmund`、`Dogma`、`Magma`）。不讀設定、不查資料庫。`STAFF_NAMES` 還有人 import 就留著（值不變）、沒人用就併掉不留別名；異聞設計稿之後會讀 `STAFF_NAMES`，留著比較穩，你看現況定、寫進 decided。",
        "- **②`tianxia/models.py`**：`Config` 在 `banned_names_on` 旁邊加 `staff_names_on: bool = True`（註解：冒充官方的名號擋不擋；企劃者 2026-11-20「現在就擋」；主機緊急時在設定覆寫檔關掉、重開生效）。預設開，兩份設定覆寫檔與 `config.json` 都不用寫。先看 `Config` 的新欄位有沒有測試要登記（`tests/core/` 裡守設定欄位的），照著補。",
        "- **③`tianxia/core/identity_base.py::blocked_name`**：保留字那一半不再看 identity（`content.config.staff_names_on and name_base.staff_like(name)`），`id:` 開頭那一半照舊只在 identity 開著時擋。docstring 改成現在的意思。拒絕句**沿用** `accounts.NAME_TAKEN`「這個名號已有人使用。」（PM 定：不加新字、殼不動；跟撞名、管理者名號、名號被別的角色用掉同一句，試不出名單也分不出對方是誰）。",
        "- **④已經叫這類名號的人不動**：登入、玩、被人看見都照舊（確認 `open_game` 那條路不叫 `blocked_name`，寫一條測試：資料庫裡已有名號「客服」的角色照樣登入進得去）；他只是不能再用易名帖改成另一個這類名字。",
        "- **⑤主機用的唯讀清單** `scripts/list_staff_like_names.py <資料庫檔>`：用 sqlite 的 `mode=ro` 開（照 `scripts/mall_ledger.py` 的開法，不走 `open_database`、不觸發遷移），`SELECT name FROM characters`，逐筆 `name_base.staff_like`，**只印名號**（一行一個，最後一行印幾個；不印是不是假人、陣營、帳號），給企劃者在主機上對線上資料庫跑、決定要不要請那些人改名。stdout 包成 UTF-8。寫一條測試（暫存資料庫放三個角色，其中一個叫「客服小美」）。`tests/core/test_feature_boundaries.py` 有守 `scripts/*.py` 的規矩，改完跑過。",
        "- **⑥測試**（調查的 `plan` 第 5 點列了要改的四處，照著改，舊的「關著照舊能取」「只擋全等」斷言換成新規矩）：`tests/core/test_identity_base.py`（`id:` 只在開著時擋；保留字不管 identity 都擋——逐一列：客服、客服小美、官方客服、客 服、ＧＭ、gm、G.M、小美GM、管理员、系統、管理者、營運；不擋：官府、官軍、沈浪、Sigmund、Dogma、方官；`staff_names_on=False` 時保留字全部不擋）；"
        "`tests/bots/test_server_bots.py` 加 `test_bot_name_pool_cannot_spell_staff_words`（假人取名的字表組不出任何一個 `STAFF_WORDS`、字表裡沒有 ASCII 字母；以後字表加字這條會紅）；`tianxia/features/identity/tests/test_identity_server.py` 與 `tianxia/features/mall/tests/test_mall_card_daily.py` 寫死舊行為的那幾行；`tests/server/test_server.py` 加一條走 HTTP 的（註冊後 `/api/character` 用「ＧＭ」「客服小美」「官 方」回 400 與 `NAME_TAKEN`，「官府中人」建得成）；`scripts/set_password.py --character 客服小天` 照舊建得出來（有現成測試就加一個 case，沒有就在 decided 寫你怎麼確認的）。",
        "- **不加比對軌、不改情境**：調查員 grep 過 `scripts/sb`、`scripts/webqa` 沒有任何情境的名號命中新規則，全軌輸出應該一個位元組不變（閘門會驗）；你自己只跑 `scripts/test_for.py` 挑的、上面點名的檔、`tests/core/test_shell_stays_thin.py`、邊界與契約，再跑一次不含 slow 的整套（改到核心與 `Config`）。",
        "- **不做**：同形字（西里爾 М、希臘 Μ）、拆字、同音字（課服）——這一版不擋，寫進 leftovers；改帖友書信的寄件人顯示；改線上資料庫裡任何人的名號；`reserved_names`；`naming.name_problem`。退版：沒有存檔欄位、沒有資料庫改動；換回舊程式就是不擋；緊急開關 `staff_names_on: false`。",
    ])


def b241():
    return ad(241, "使用條款出新版（2026-11-v2）：第十條寫明客服管道是遊戲內的客服頁", "terms", "dev/terms-v2-241", "8508", [
        "- **點頭**：企劃者 2026-11-20，PM 問「條款第十條現在寫『客服管道（另案建置）』，真人客服這次就要上線，這句什麼時候改」，他選「現在就出新版條款」。內容檔自己的 `_說明` 把「聯絡方式」歸成小改（不換版號）；這一次照企劃者的決定換版號——回報與計畫都寫這句原話，免得審查的人照 `_說明` 退回。條款包是 Joy 2026-11-09 PR #193 做的，新句全部列進 `new_strings` 給 Joy 潤。",
        "- **只動兩個檔**：`tianxia/features/terms/content/terms.json`、`tianxia/features/terms/README.md`。程式、測試、`content/patch_notes.json`、設定都不動（調查員查過：沒有任何測試寫死版號或第十條的字；`check_content` 只驗 `published` 的格式、公司欄位、佔位填不填得進去）。",
        "- **①`terms.json`**：(a) `version` 改 `2026-11-v2`。(b) `published` 與 `docs.terms.updated` 寫 `2026-11-21`（PM 定的預定日；**Joy 部署當天改成真的上線那一天**——改版頁的期限是 `published` 0 點加 `grace_days` 15 天，填早了期限縮短、上線比它晚超過 15 天就沒有人會被問；這句話寫進 README 與回報的 docs）。`docs.privacy.updated` 不動（隱私權的字這次不改）。"
        "(c) 第十條「十、客服與申訴」的 `p` 換成：`客服管道為遊戲內「設定」裡的「客服」頁：可以寫單、附上截圖，全天 24 小時受理，客服的回覆在同一頁看。無法登入時，請寫信到 {email}。申訴處分於 15 日內回覆。`（PM 擬的，待 joy 潤；拿掉了原句的「回覆時限依客服管道公告」——客服頁與 FAQ 都沒有公告回覆時限。佔位只准 `{email}`，不能出現別的大括號。）"
        "(d) `change_summary` **最前面加一句**、原本三句留著（新玩家第一次同意看的也是這幾句）：`客服上線：遊戲內「設定 › 客服」可以寫單、附截圖、看回覆（使用條款第十條）。`（待 joy 潤）。(e) 全文其他寫「透過客服管道」的句子不動（現在指得到客服頁了）。",
        "- **②README**：第 5 行附近「條款裡寫客服管道（另案建置）」那半句改成現況（2026-11-v2 第十條改字、真人客服 AA 波打開）；講改版的那一段補一句「大改時 `published` 填上線那一天，期限從它起算」；加一小段「2026-11-v2 上線時會怎樣」：同意過 v1 的人登入後看到改版頁（開頭一句加 `change_summary`，三顆鈕：同意、稍後再看、我不同意），`published` 起 15 天內每次進遊戲都會再跳、過了就視為接受而且旁檔不寫紀錄；從沒同意過的人一定要按；註冊頁的勾選帶的版號是現問的。**這不是強制重新同意**——照程式寫（`rules.need`），不要寫成每個人都要按。",
        "- **③驗**：`scripts/test_for.py` 挑的（terms 包的 tests、`tests/core/test_content.py`、`test_content_packs.py`、真實內容不含 slow）、`tests/core/test_terms_base.py`、`tianxia/features/identity/tests/test_identity_terms.py`。起一台暫存伺服器（8508、`TIANXIA_PROFILE=season21`、暫存資料庫、模型 127.0.0.1:9）實看一次：`/terms` 頁第十條是新句、頁上「版本 2026-11-v2」、沒有殘留的 `{`；`/api/terms/version` 回新版號；用一個「同意過 v1」的帳號（先在改之前的版本註冊、或直接在暫存的條款旁檔寫一列 v1 的同意）登入看 `/api/terms` 回 `need: ask`、`summary` 第一句是客服那一句、`deadline` 是 `published` 加 15 天。回報寫每一步看到的回應。看完 `taskkill /T`、刪暫存。",
        "- **④比對會差的地方先寫出來**（閘門由 PM 處理，你不用放行）：只跑 `scripts/same_behavior.py selftest --tracks charter`（三種設定，確認這一軌自己還穩），並在回報的 decided 逐項列 charter 輸出裡會跟 develop 不一樣的行（`/api/terms/version` 的版號、`/terms` 與 `/privacy` 兩頁的長度與雜湊、`/api/terms` 的 `version` 與 `summary`、條款旁檔的雜湊），PM 做比對基準時拿來對。",
        "- **不做（寫進 leftovers，附調查員 `result.terms.risks` 的原文出處）**：隱私權條款對客服單只有一句「客服往來內容…結案後 1 年」，沒寫截圖、沒寫客服看得到的帳號資料，程式也沒有一年後自動刪；第三條「你打的字不送到外部 AI 服務」與之後要開的客服官、Discord 的橋衝突；第七、九條寫「以電子郵件提供」「依你留下的聯絡方式通知」但 identity 關著玩家留不了 Email；條款的 `{email}` 是公司信箱、客服設定的 `mailbox` 是另一個（登入頁現在不畫）。這幾件是法律條文，要企劃者與 Joy 定，不要自己擴寫。改版資訊這一批不加。退版：資料庫不升版、沒有新欄位、季中可以換；換回舊程式時 v2 的同意紀錄留著，舊程式只會把它當「同意過別版」。",
    ])


def b242():
    return ad(242, "刪掉 test_season21_frame 啟動類四條慢測試（企劃者點頭）與只有它們在用的 helper", "core_shared", "dev/tests-drop-242", "8509", [
        "- **點頭（刪測試）**：企劃者 2026-11-20，PM 問這四條刪不刪（PM 建議留部分重複的那一條），他選「四條都刪」。回報與計畫寫這句原話。",
        "- **刪的**（`tests/figures/test_season21_frame.py`，行號以 develop 現況為準、先自己對）：`test_a_fresh_database_still_in_preparation_prints_no_mismatch`、`test_a_seeded_but_unopened_season_prints_nothing_either`、`test_a_running_season_opened_with_another_calendar_still_prints_the_fb520_warning`、`test_a_running_season_with_the_matching_calendar_prints_nothing`（各 `slow`＋兩種設定，8 個 case、16 次啟動）連同裝飾器；只有它們在用的 `_start_server`、`_start_bots`、`NOW`、`import run_bots`、`import server`、`open_world` 的 import 一起刪。**留著** `test_the_warning_function_itself_knows_the_phase` 與它用的 `MARK`、`WorldState`。那一段開頭的說明註解改成兩三行：啟動時印不印警告的接線現在沒有自動測試，靠純函式那一條加 QA 手動起程式看。",
        "- 刪完：`pytest --collect-only -q tests/figures/test_season21_frame.py` 應該是 23 條（含 slow 也是 23）；整檔跑過；用 `python -m pyflakes`（沒有就用 `python -W error -c \"import ast…\"` 自己掃）確認沒有殘留沒用到的 import 與常數；`scripts/test_for.py` 挑的跑過。",
        "- **跟著改的字**：`docs/superpowers/plans/2026-11-10-測試去重-盤點.md` 第 140、164 行附近（刪除候選 → 2026-11-20 企劃者「四條都刪」、第 242 批刪了）並寫**刪掉之後少守什麼**四點：`server.main`／`run_bots.main` 啟動時真的把 `profile_warning` 印出來的接線；`seed_first_season` → `season_phase()` → 警告函式這一串資料庫接線（純函式版用空殼 `WorldState`，沒蓋到）；兩支程式印的一致；FB-520（季中換設定要印）與 FB-636（籌備中不印）的端到端回歸。`.claude/skills/tianxia-dev/SKILL.md` 提到「啟動警告的測試」當範例的那一行補一句現在沒有自動測試；`.claude/skills/tianxia-qa/` 講引擎驗收手動起程式看警告的那一格若寫著「有自動測試守」就改掉。其他文件（交接、架構圖、手冊）PM 改。",
        "- **不做**：不補新的測試來取代（企劃者要的是刪）；不動 `server.py`、`run_bots.py`、`calendar.py`。退版：只動測試與文件。",
    ])


AD_NAMES_LENS = dict(key="names", text=(
    "**冒充官方的名號真的擋住了、沒有誤傷、分不出假人**。第 240 批（動核心 `name_base.py`、`identity_base.py`、`models.py`；企劃者 2026-11-20「現在就擋」）。親自驗（解一份 head 到你的暫存夾，`TIANXIA_DB` 指到暫存檔，寫小腳本直接叫函式與打 HTTP）："
    "①三條路都擋到：`/api/character`、identity 建角色、易名帖（路由那條與 `rename_self` 沒傳 `taken` 的後備那條）。自己想二十個繞法逐個試（全形、大小寫、夾空白與各種標點、零寬字元、前後加字、簡繁、`G M`、`gm` 前後接數字或中文），列出哪些擋了、哪些沒擋；沒擋而且一眼看得出是在冒充的算 should，同形字、拆字、同音字派工單明寫不擋、不算。"
    "②誤傷：隨手取五十個正常的武俠名號（含姓官、姓方、姓管的；含「官府」「官軍」「客棧」「服」字、「系」字、「營」字、「統領」「理事」）全部過；英文名 Sigmund、Dogma、Magma、Enigma 過。"
    "③回的句子與狀態碼跟「名號被別的角色用掉」逐字一樣（`NAME_TAKEN`）；判斷只看字串、不查資料庫，所以試不出對方是不是假人；假人取名的字表組不出任何保留字（看那條新測試真的在比字表）。"
    "④`staff_names_on=False` 時回到改之前（identity 關著一律不擋；開著照舊只擋全等四個與 `id:`）——對 base 的 `blocked_name` 逐個輸入比。`id:` 開頭那一半一個字沒變。"
    "⑤已經叫「客服」的角色照樣登入、照樣玩；`scripts/set_password.py --character` 照樣建得出含保留字的名號；`scripts/list_staff_like_names.py` 用 `mode=ro` 開、只印名號、不印任何分得出假人的欄位、不 import 會觸發遷移的東西。"
    "⑥`server.py`、`web/`、`content/`、設定覆寫檔沒有動；`tests/core/shell_tables.py` 沒有多一筆。"
))
AD_TERMS_LENS = dict(key="terms", text=(
    "**條款新版只改了該改的字、頁面畫得出來、說明沒有講錯行為**。第 241 批（企劃者 2026-11-20「現在就出新版條款」）。親自驗："
    "①`git diff` 對 base：只動 `tianxia/features/terms/content/terms.json` 與包的 README；json 裡只有 `version`、`published`、`docs.terms.updated`、第十條的 `p`、`change_summary` 多一句這五處變了，其他條文、隱私權全文、公司資料一個字沒動（把兩份 json 載進來逐鍵比）。"
    "②新句裡除了 `{email}` 沒有別的大括號；真實內容跑 `rules.check` 是空的；解一份 head 起得來、`/terms`、`/privacy` 兩頁 200、頁上版本是 `2026-11-v2`、第十條是新句（或直接叫 `pages` 的畫法函式）。"
    "③README 新寫的「上線時會怎樣」逐句對 `rules.need`、`routes.py`、`web/terms.js`：同意過舊版的人是「可以稍後再看、15 天後視為接受」，不是強制；`published` 決定期限。寫錯一句就是 should。"
    "④全文再找一次「另案」「建置中」這類跟現況對不上的字，有漏的列出來。⑤新句都進了 `new_strings`。"
    "另外看第 242 批：刪的只有派工單點名的四條與只有它們在用的 helper，`test_the_warning_function_itself_knows_the_phase` 還在而且會跑；盤點文件寫了「刪掉之後少守什麼」。"
))
WAVES["AD"] = dict(
    round2=True,
    extra_lenses=[AD_NAMES_LENS, AD_TERMS_LENS],
    lines=[dict(name="擋冒充名號", batches=[b240]), dict(name="條款新版", batches=[b241]), dict(name="刪啟動測試", batches=[b242])],
    merge_port=8510, fix_port=8511,
)


# ── AE 波：企劃者 2026-11-21 凌晨答的三題（PM 用選單問，引號裡是他選的選項原字）：條款改版「改成強制按同意」243、隱私權「這一版一起補」244、複姓上官被「官方」誤擋「放行」245 ──
# 243、244 都動 terms 包，排在同一條線一前一後；245 自己一條線。基準是 develop；收尾一次合、一次驗。
# 收尾時 PM 另做比對基準：develop 加最終的 terms.json 加新的 Config 欄位本身（AD 波的認定：加 Config 欄位 shelf 軌那一行一定差）。
AE_NOTE = [
    "- **背景（三批共用）**：AD 波 2026-11-21 凌晨進了 `develop`（擋冒充官方的名號第 240 批、條款 `2026-11-v2` 第 241 批、刪啟動測試第 242 批；紀錄 `docs/superpowers/plans/2026-11-20-波次AD紀錄.md`，最後一節是 PM 的認定與留下的）。真人客服（AA 波）與這些都還沒上 `main`。企劃者 11/21 凌晨又答了三題，這一波就是那三題。**動手前先讀 AD 紀錄最後一節與你那一批前一批的計畫**（`docs/superpowers/plans/2026-11-20-客服上線補件-第240批.md`、`…第241批.md`）。"
    "上面「計畫不超過 120 行」照舊，寫在 `plan` 那個路徑。這一批不做派工單沒寫的事，碰到了寫 leftovers。",
    "- **這台同時有別的線在跑**：重的東西跑一次就好；起伺服器一律暫存資料庫、模型網址 127.0.0.1:9、只用派工單給的埠、不碰 7861；跑 `same_behavior` 時環境裡不要有 `TIANXIA_DB`、`TIANXIA_SUPPORT`、`TIANXIA_PROFILE`；不讀不寫任何 `.local/` 的檔。任何畫面、API 回應、主控台輸出都不能讓人分出誰是假人。"
    "**包的 README 自己改到跟程式一致**（AD 波派工單這一句前後寫得不一樣，這一次講清楚：README 你改；`docs/guide`、手冊、`CLAUDE.md`、交接、架構圖、主機端操作文件你不動，要改的句子放回報的 docs）。新字每一句旁 `待 joy 潤`（json 裡的字列在回報的 `new_strings`），改舊句寫「舊 → 新」。",
]


def ae(n, title, pkg, dev, ports, body):
    plan = f"docs/superpowers/plans/2026-11-21-客服上線補件-第{n}批.md"
    return batch(n, f"客服上線補件第 {n} 批：{title}", pkg, dev, plan, ports, body + AE_NOTE, custom=True)


def b243():
    return ae(243, "條款換版號之後，同意過舊版的人也要按過同意才能進遊戲（不再是「稍後再看、15 天後視為接受」）", "terms", "dev/terms-must-243", "8512", [
        "- **點頭**：企劃者 2026-11-21，PM 問「條款改版上線後，同意過舊版的玩家登入會看到改版頁，但可以按『稍後再看』，生效日起 15 天後就視為接受、不再問。要維持這樣，還是改成每個人都得按過同意才能進遊戲」，他選「改成強制按同意」（選項寫的是：沒按過新版同意的人進不了遊戲，跟新玩家一樣；上線那一刻所有人都會被擋一次）。動到核心的設定檔 `tianxia/core/tuning/terms.py`，回報的 `core_changes` 寫這句原話。條款包是 Joy 2026-11-09 PR #193 做的。",
        "- **現況（先自己讀一次）**：`tianxia/features/terms/rules.py::need`——同意的版號等於現行版回空、從沒同意過回 `must`、同意過別版的在 `published` 加 `grace_days` 天內回 `ask`（改版頁有「稍後再看」）、過了回空（視為接受，旁檔不寫紀錄）。`routes.py` 的狀態回 `need`、`summary`、`deadline`；`web/terms.js` 照 `need` 畫兩種層（`must` 沒有「稍後再看」；同意時 `source` 是 `gate` 或 `update`）。**先弄清楚 `must` 現在到底擋了什麼**：只是網頁上蓋一層，還是伺服器也擋（哪些路由在沒同意時拒絕）——照實寫進計畫與 decided；這一批的目標是「同意過舊版的人，跟從沒同意過的新玩家受到同樣的擋法」，**不另外加比新玩家更嚴的擋法**（現況只是蓋一層的話，把這件事寫進 leftovers 給 PM，不要自己擴大）。",
        "- **①規則**：`tianxia/core/tuning/terms.py` 加 `update_must: bool = True`（註解：換版號之後同意過舊版的人要不要按過同意才能進；企劃者 2026-11-21「改成強制按同意」；設 false 回到考慮期的做法——`grace_days` 天內問、過了視為接受）。`rules.need`：同意過別版時，`update_must` 開著回 `must`，關著照舊（`ask`／空）。`grace_days` 留著（`update_must` 關著時才用）。",
        "- **②讓畫面分得出「新玩家第一次」與「舊玩家碰到新版」**：狀態回應多帶一個旗標（例 `\"update\": true`，名字你定：這個帳號同意過別的版）。`web/terms.js`：`must` 而且帶這個旗標時，開頭那一句換成改版的說法（新字，待 joy 潤，例：「使用條款與隱私權條款有新版，請看過這次改了什麼，同意後繼續。」），底下照樣列 `change_summary`；按同意時 `source` 記 `update`（稽核要分得出是改版時同意的）；沒有「稍後再看」；「我不同意」照 `must` 現在的行為。新玩家第一次的那一層一個字不變。`deadline` 在 `must` 時畫面不用（回應裡照舊帶不帶你定、寫進 decided）。",
        "- **③內容檔的說明與 README**：`terms.json` 的 `_說明` 那一句講改版的（「…換了之後 published 起 grace_days 天內上線的人會看到改版頁…」）改成現在的行為（換了 `version` 之後所有人下次進遊戲都要按過同意；`Config.terms.update_must` 關著才是考慮期）。README「2026-11-v2 上線時會怎樣」那一段（第 241 批寫的）整段照新行為重寫；講 `published` 的那幾句照實改（強制時期限不再用得到，`published` 仍是頁上印的生效日）。**不改條款與隱私權的條文**（第 244 批改）。",
        "- **④測試**（terms 包的 tests 與 `tests/core/test_terms_base.py`；網頁測試在包現有的網頁測試檔）：同意過 v1、現行 v2、`update_must` 開著 → `need` 是 `must`、回應帶改版旗標、`summary` 有；同意之後 `need` 空、旁檔多一列 `source=update`；`update_must` 關著 → 跟改之前逐一樣（現有測 `ask` 與考慮期的那幾條改成先把 `update_must` 關掉，斷言不動）；新玩家第一次照舊 `must`、不帶改版旗標、`source=gate`；terms 關著一切照舊（路由 404）。網頁：`must` 帶旗標時開頭是改版那一句、沒有「稍後再看」；不帶旗標時跟改之前的 html 逐字一樣。假人沒有帳號，不受影響（確認一下 `need` 對沒有帳號鍵的呼叫照舊）。",
        "- **⑤比對與走查會差的地方先寫出來**（閘門由 PM 處理）：跑 `scripts/same_behavior.py selftest --tracks charter`（三種設定）看這一軌還穩，並在 decided 逐項列 charter 輸出裡會跟 develop 不一樣的行（預期：`/api/terms` 的回應多一個旗標欄位；charter 走不走得到「同意過舊版」那一種照實寫）。新加的 `Config.terms.update_must` 會讓 shelf 軌「內容 config」那一行變（整份設定的雜湊），這是預期的，寫進 decided。`scripts/webqa` 的走查帳號註冊時就帶現行版號，不會出現同意層——確認一下、寫一句。",
        "- **⑥實看一次**：起暫存伺服器（8512、`TIANXIA_PROFILE=season21`、暫存資料庫、模型 127.0.0.1:9），用一個「同意過 v1」的帳號登入（照第 241 批計畫的做法造），看 `/api/terms` 回 `must` 與旗標、畫面那一層的字（375 淺、深各一張，照介面設計規範第八節自己看一眼，路徑寫進回報）、按同意之後進得去、旁檔多一列 `update`；再用新註冊的帳號看一切照舊。看完 `taskkill /T`、刪暫存。",
        "- **不做**：改條文；改 `grace_days` 的預設；比新玩家更嚴的伺服器端擋法；改版資訊。退版：資料庫不升版、沒有存檔欄位；換回舊程式回到考慮期的做法（v2 的同意紀錄留著）；季中可以換；緊急開關 `terms.update_must: false`（設定覆寫檔、重開生效）。",
    ])


def b244():
    return ae(244, "隱私權條款補上客服單：會保存什麼、誰看得到、保存多久（放進還沒上線的 2026-11-v2）", "terms", "dev/terms-privacy-244", "8513", [
        "- **點頭**：企劃者 2026-11-21，PM 問「隱私權條款現在對客服單只寫一句『客服往來內容，結案後 1 年』，沒寫會存截圖、也沒寫客服看得到帳號資料與元寶帳本；新版條款還沒上線，上線前補字不用再多出一版。要不要這一版一起補」，他選「這一版一起補」。**這是法律條文**：你擬的每一句都列進 `new_strings`（待 joy 潤），回報裡寫明「上線前請企劃者與 Joy 找法律專業看過」（包的 README 本來就有這一句）。",
        "- **只動** `tianxia/features/terms/content/terms.json`（隱私權那一份 `docs.privacy` 的條文、`docs.privacy.updated`、`change_summary`）與包的 README。程式、測試、設定不動；版號不動（還是 `2026-11-v2`，它還沒上線）。這一批接在第 243 批後面、同一條線：第 243 批改過的 `_說明` 與 README 段落不要改回去。",
        "- **①先把事實查清楚（列進計畫，每一條附檔名行號）**——只寫程式真的在做的事：(a) 一張客服單存什麼（`tianxia/features/support/store.py` 的表與欄位：類別、內文、回覆、內部註記、時間、當時的版本、帳號鍵……）；截圖（幾張、多大、哪些格式、存在哪、檔名帶不帶個資）。(b) 客服看得到什麼：客服頁的佇列、單、查帳號那張卡（`routes.py` 的 lookup 回哪些欄位：帳號、名號、建立時間、元寶餘額與帳本？綁定的 Email／手機遮不遮？逐欄列）。誰算客服（名單上的帳號，含列在名單上的管理者）。(c) 保存多久：現在條文寫「結案後 1 年」；程式有沒有任何刪除（調查員先前查到只有 `pending_notes` 的刪除，沒有到期刪單或刪截圖——自己再確認）。(d) 會不會送到外面：`support.bot_account` 空著時沒有任何外送；`scripts/support_bridge.py`（往 Discord 貼單）與客服官現在都沒開——**現在的條文「你打的字不送到外部 AI 服務」目前是對的，不要改它**。(e) 備份：每日備份會整夾複製旁檔與截圖夾（`scripts/backup_db.py`）。",
        "- **②擬字**：照隱私權條款現有的章節與語氣（先讀全文；看它「蒐集哪些資料與用途」「保存期限」「誰看得到／提供給誰」各在哪一條），把客服單補進對的那幾條，**每一句都要對得上①查到的事實**，不寫程式沒做的事、也不寫得比程式做的少。至少涵蓋：你寫的內容與附上的截圖會保存、用來處理你的問題；處理的客服人員看得到這張單與你的帳號資料（照 (b) 查到的逐項寫成玩家看得懂的話，例：名號、帳號建立時間、元寶餘額與紀錄——以查到的為準）；截圖請不要包含別人的個資或你的密碼（提醒句）；保存期限照現有那一句「結案後 1 年」（**不改這個承諾**）。佔位只准用檔裡已經有的那幾個，新句不能出現別的大括號。`docs.privacy.updated` 改成跟 `published` 同一天（2026-11-21，Joy 部署當天一起改）。`change_summary` 加一句講隱私權這次補了什麼（放在客服那一句後面；待 joy 潤）。",
        "- **③「結案後 1 年」程式沒有做的事寫清楚**：條文承諾一年、程式現在不會刪。這一批**不做**自動刪除，寫進 leftovers 與回報的 docs：最早的客服單結案後滿一年是 2027 年 11 月，在那之前要有到期刪單與刪截圖（含備份怎麼辦）的批；PM 會記進交接。",
        "- **④驗**：`rules.check` 對真實內容是空的；`scripts/test_for.py` 挑的與 `tianxia/features/terms/tests` 跑過；起暫存伺服器（8513）看 `/privacy` 頁新句都在、沒有殘留的 `{`、頁上的版本與最後更新；`/terms` 頁沒被動到（對第 243 批之後的那一筆逐字比）。把兩份 json（第 243 批之後的那一筆與你改完的）逐鍵比一次，回報列出變了哪幾個鍵。",
        "- **不做**：使用條款（`docs.terms`）的條文；第三條「不送到外部 AI 服務」；第七、九條的電子郵件通知；兩個信箱的事（都在 AD 紀錄的「留下的」，等企劃者與 Joy）。退版：只是內容檔的字；資料庫不升版、季中可以換。",
    ])


def b245():
    return ae(245, "複姓上官加上以方開頭的名字（上官方宇）不再被「官方」誤擋", "core_shared", "dev/names-shangguan-245", "8514", [
        "- **點頭（動核心 `tianxia/core/name_base.py`）**：企劃者 2026-11-21，PM 問「擋冒充名號的規則裡『官方』是包含比對，所以複姓上官加上以方開頭的名字（例：上官方宇、上官方正）也會被擋，玩家只會看到『這個名號已有人使用』。要不要放行這種名號」，他選「放行」。回報的 `core_changes` 寫這句原話。",
        "- **只動** `tianxia/core/name_base.py::staff_like`（與它上面的註解、docstring）、`tests/core/test_identity_base.py`，計畫檔。做法：「官方」這個詞前面緊接著「上」的時候不算（正規化、去掉空白與符號之後再判；其他保留字照舊包含比對）。寫法你定（例：對「官方」用 `(?<!上)官方` 找），但要守住：`官方`、`官方客服`、`真官方`、`官 方`、`我是官方` 照擋；`上官方宇`、`上官方正`、`上官方` 不擋；`上官方客服`、`上官GM` 照擋（別的保留字照樣生效）；`上上官方`、`官方上官方` 各自該怎樣寫進測試與 decided（原則：只要還有一處「官方」前面不是「上」就擋）。",
        "- 測試加在 `test_staff_like_is_pure` 與 `test_blocked_name_staff_words_regardless_of_identity` 旁邊（上面那幾個例子逐一列）；AD 波修正輪加的那幾個（`GM Tom`、`gm_bob`、`gmail`、`Big Mac`、開關關掉時的四個全等名）一個都不能壞。跑 `scripts/test_for.py` 挑的、`tests/core/test_identity_base.py`、`tianxia/features/identity/tests`、`tianxia/features/mall/tests/test_mall_card_daily.py`、`tests/server/test_server.py`、邊界與契約；改到核心，再跑一次不含 slow 的整套。",
        "- 不加比對軌、不改情境（沒有任何情境的名號含「上官」或「官方」——自己 grep `scripts/sb`、`scripts/webqa` 確認，寫一句）。README：identity、mall 兩包講 `staff_like` 的那一句若列了規則細節，補「上官後面的方不算」；沒列細節就不動。退版：沒有存檔欄位、沒有資料庫改動。",
    ])


AE_TERMS_LENS = dict(key="terms", text=(
    "**條款：強制同意真的照「跟新玩家一樣」做到了、沒多沒少；隱私權補的每一句對得上程式**。第 243、244 批（企劃者 2026-11-21「改成強制按同意」「這一版一起補」）。親自驗（解一份 head 到你的暫存夾，`TIANXIA_DB` 指到暫存檔，寫小腳本直接叫函式）："
    "①`rules.need` 的四種人（同意過現行版、從沒同意、同意過舊版而且 `update_must` 開、同意過舊版而且 `update_must` 關〔考慮期內、考慮期外〕）逐一叫，結果對；`update_must` 關著時跟 base 的 `need` 逐個輸入一樣。"
    "②同意過舊版的人受到的擋法跟從沒同意過的新玩家**一樣**——不比它鬆（有沒有哪條路新玩家被擋、他沒被擋），也不比它嚴；`must` 現在到底擋什麼（只是網頁蓋一層還是伺服器也擋）照程式寫出來。按同意之後旁檔那一列的 `source` 是 `update`、版號是現行版；新玩家照舊 `gate`。"
    "③`web/terms.js`：不帶改版旗標的 `must` 層畫出來的 html 跟 base 逐字一樣（看那條測試真的在比）；帶旗標時沒有「稍後再看」；新字旁有待 joy 潤。"
    "④terms 關著時四條路由照舊 404、註冊照舊；假人（沒有帳號）不受影響；回應裡沒有任何欄位分得出誰是假人。"
    "⑤隱私權新加的每一句逐句對程式：存什麼對 `support/store.py` 的欄位、截圖的張數與格式對 `core/tuning/support.py` 與上傳那條路、客服看得到什麼對 `routes.py` 的 lookup 與看單回應**逐欄**（條文寫了程式沒給的、或程式給了條文沒寫的，各列一條 should）；沒有改「不送到外部 AI 服務」與「結案後 1 年」這兩句；新句沒有 `{email}` 那幾個以外的大括號、`rules.check` 是空的；兩份 json 逐鍵比，使用條款（`docs.terms`）的條文一個字沒動。"
    "⑥第 245 批：`上官方宇`、`上官方正` 過；`官方`、`官方客服`、`官 方`、`上官方客服`、`上官GM` 照擋；AD 波的那些例子（`GM Tom`、`gm_bob`、`gmail`、`Big Mac`、`客 服`、`ＧＭ`）結果跟 base 一樣；自己再想十個「上」字開頭的繞法試（例：`上官方`後面接符號再接`客服`、`上.官方`、`丄官方`）。"
    "**PM 看開發回報時想到的一個洞，請親手驗**：例外現在是「官方前面緊接著上就不算」（`(?<!上)官方`），所以 `線上官方`、`網上官方`、`以上官方公告`、`馬上官方` 這種「上」不是複姓的名號也被放行了——這幾個一眼看得出是在冒充，應該照擋。企劃者要放行的只是複姓上官（PM 問的例子是上官方宇、上官方正）。屬實就列成 should，建議的修法：例外只給**名號開頭**的「上官」（正規化之後整個字串以「上官」開頭時，開頭那一處「官方」不算；其餘位置的「官方」照擋），`上官方宇`、`上官方正`、`上官方` 照過，`線上官方`、`小上官方宇` 照擋。"
))
WAVES["AE"] = dict(
    round2=True,
    extra_lenses=[AE_TERMS_LENS],
    lines=[dict(name="條款強制與隱私權", batches=[b243, b244]), dict(name="放行上官", batches=[b245])],
    merge_port=8515, fix_port=8516,
)


# ── AF 波：異聞一（骨架、不叫模型的發掘、重放）。設計稿企劃者 2026-11-21 審過（「看過了，十題都照建議做」）；五處核心改動 11/21 下午點頭（「五處都可以」）；畫面照他挑的版（撞見卡乙、全圖丙、異聞錄甲）──
# 一條線兩批一前一後：247 規則與資料、248 畫面。新包 yiwen，開關預設關。
YW_DESIGN = "docs/superpowers/specs/2026-11-20-異聞-design.md"
YW_PLAN = "docs/superpowers/plans/2026-11-21-異聞-計畫.md"
YW_MOCK = "docs/superpowers/specs/2026-11-21-異聞-畫面"  # 企劃者挑的三版原始檔（card-b、map-c、book-a），進了版控
YW_SHOTS = r"C:\Users\ray61\AppData\Local\Temp\claude\81800b313c89d0f8\ade93b70-b3b7-42db-a8af-21f7a7cbdb16\scratchpad\yiwen\shots248"
YW_NOTE = [
    "- **異聞這一波**：規格是設計 `" + YW_DESIGN + "`（企劃者 2026-11-21 審過：PM 用選單問「你看過了嗎？要怎麼往下走」，他選「看過了，十題都照建議做」），做法照總計畫 `" + YW_PLAN + "`：先讀「全域限制」「跟設計稿對不上的（對程式）」「批〇」與**「異聞一」整節**（介面、表、測試名都定在那裡；批與批之間靠它對名字，不要自己另取）。計畫與設計稿對不上的照計畫（計畫寫了理由）；計畫與現行程式對不上的照程式、寫進 decided。這一批**不做**異聞二、三、四的事，碰到了寫 leftovers。上面「計畫不超過 120 行」照舊，寫在 `plan` 那個路徑（寫這一批自己怎麼切 commit、先對程式確認了什麼）。",
    "- **五處核心改動的點頭**（計畫批〇那張表；動到的每一處在回報的 `core_changes` 逐一列、附這句原話）：企劃者 2026-11-21 下午，PM 用選單問「異聞開工前要動五處核心（都有前例，親衛隊長與意境合成改版做過同樣的事）：①探索收尾的那張順序表加一格（撞見）；②世界每一步的順序表加一格（定論、兆頭、收逾時的則）；③路由名單多三條（異聞錄、全圖、回報；開關關著一律 404）；④存檔加三個欄位（玩家眼前的那一則、這一季有沒有異聞、全服的名額與定論記號；空的不寫進存檔）；⑤開季蓋章多一行。開關預設關，關著時一個位元組都不變。可以嗎」，他選「五處都可以」。**這一波只用得到其中幾處**（探索收尾那一格、存檔欄位、開季蓋章；世界那一格與三條路由是異聞四的事，這一波不加）。五處以外要動核心、殼、`shell_tables` 才做得完的，停下來寫 stopped。",
    "- **企劃者另外定的**：發掘開到開季第 18 天（PM 問要不要提早一天，他選「維持第 18 天」；季末還沒到時間的則照計畫寫「季末未定」）。**PM 定的**（計畫回報的幾條 open）：撞見與順逆的種子用公開值、第一版先認了；首創一律具名（照程式，不做「某位少俠」）；問路香只上單支（異聞三的事）。",
    "- 各包 README 自己填（新包的 README 是你的）；`docs/guide`、手冊、`CLAUDE.md`、交接不動，句子放回報的 docs。新字每一句旁 `待 joy 潤`（內容檔 json 裡的字列在回報的 `new_strings`）。任何畫面、API 回應、主控台輸出都不能讓人分出誰是假人（假人不撞見、不走；`tests/bots/test_server_bots.py` 掃得到你新加的 `web/` 檔）。起伺服器一律暫存資料庫、模型網址 127.0.0.1:9、只用派工單給的埠、不碰 7861；不讀不寫任何 `.local/` 的檔。",
]


def yw(n, title, dev, ports, body):
    plan = f"docs/superpowers/plans/2026-11-21-異聞-第{n}批.md"
    return batch(n, f"異聞第 {n} 批：{title}", "yiwen", dev, plan, ports, body + YW_NOTE, custom=True)


def b247():
    return yw(247, "異聞一之一：新包 yiwen 的骨架——開關與蓋章、存檔欄位、內容檔與驗證、旁檔、撞見與名額、不叫模型的發掘三幕、重放、走完與獎勵、比對軌", "dev/yiwen-1", "8517、8518", [
        "- **範圍**：總計畫「異聞一」那一節裡**畫面以外**的全部——`scripts/new_feature.py` 生包（照計畫寫的參數）；`Config.yiwen`（`tianxia/core/tuning/yiwen.py`，數字照設計第十三節的設定表、標草案；`discover_until_day` 18）；開季蓋章；`PlayerState.yiwen`、`WorldState.yiwen_on`、`WorldState.yiwen`（都 QUIET、`None` 起家，計畫寫了為什麼不能用 `default_factory`）；兩個內容檔（正式檔放設計 3.1 的五句樣例與 3.3 的模板句，包自己讀、`Content` 不加欄位）與 `check_content`；測試用的十八句（放計畫指定的位置，不放 `tests/content/`）；旁檔 `<db>-yiwen.sqlite` 與計畫定案的表；`scripts/backup_db.py` 的 `SIDE_FILES` 加 `yiwen`、`restore_db.py` 跟著；`scripts/sb/harness.py::_wipe_db` 的清單補這個旁檔（`tests/core/test_same_behavior_wipe.py` 會守）；事件 `outing` 那一格（撞見：發掘或重走、名額、全服每天上限、一人一季上限、假人不撞、這一趟別的事已經接管就不撞——計畫寫了怎麼判，先照它跑一次確認不會遞迴）；`menu` 接管與 `yiwen:` 前綴的鈕；`/api/do/yiwen_step` 這個 op（**這一批不叫模型**：每一幕先放模板的替身與退路做法，走通發掘三步；A、C 兩段的形狀照計畫，B 段留空殼給異聞二）；重放、走完、獎勵（走核心 `apply_effect`；素材與名望核心給不了的先查服務清單，沒有現成服務就回報、不新增）、江湖紀錄、行狀與江湖史那一行；放下與逾時眼前那一則不見了的處理；易名帖改名時旁檔的鍵。在別人的則上，沒人走過的鈕這一批一律 `locked`（開岔路是異聞三）。",
        "- **畫面這一批只做「走得通」的最小樣子**（`web/yiwen.js`、`web/yiwen.css`：撞見卡、每一幕、收尾卡各一個函式，資料形狀照計畫的 `main.yiwen`；樣式先求不破版、44px、淺深都看得清），**不照對比圖細修**——那是第 248 批。畫法集中在各自一個函式，下一批好換。",
        "- **測試、契約、比對**：照計畫「異聞一」列的測試檔名與每一條的名字與斷言寫（包的 `tests/`、`yiwen_kit`）；核心測試的逐字表照計畫列的改（`test_contract_core.py` 的 `BUS_ORDER`、`tests/server/test_outlock.py` 的 `OP_OWNERS`……每改一處在回報寫明）；契約 `[yiwen]`、邊界、`test_shell_stays_thin`、`test_content_packs`、`test_same_behavior_wipe` 都要過。新軌 `scripts/sb/tracks/yiwen.py`（新軌只加檔）走計畫寫的那一段：一個人撞見、發掘三步（替身）、另一個人重走；三種設定 `selftest` 穩、改一個字抓得到；`covers` 照量的寫。**開關關著一個位元組不變**：`scripts/same_behavior.py compare --new yiwen` 所有軌、三種設定跑一次（這一批自己跑，結果與工具印的「新包帶來的清單」貼進回報；base 用你開工的那一筆 develop）。動到核心（`state.py`、`world_state.py`、`core/features.py`），跑一次不含 slow 的整套 `-n 4`。",
        "- **先對程式確認的事**（計畫「異聞一」那一小節與設計 9.3）：探索「走一趟」撞見那一段會不會停下來（照親衛隊長的路跑一次）；`QUIET` 加 `None` 的欄位空著時存檔真的不多一個鍵（寫成測試）；測試設定走舊探索、撞不到異聞（經過探索的測試用正式內容 season21 的做法）。結果寫進批計畫與 decided。",
        "- 時間上限兩段合計 5 小時。到了就把做好的推上去、交：哪些測試還沒寫、哪一步倒在哪、你的判斷，寫進 leftovers；**不要為了趕完跳過「關著一個位元組不變」那一次比對**。退版風險照 PR 範本逐欄寫（新欄位換回舊程式會丟什麼、旁檔、季中能不能開、緊急開關）。",
    ])


def b248():
    return yw(248, "異聞一之二：撞見卡、每一幕、收尾卡的畫面照企劃者挑的乙版（頁邊朱批）", "dev/yiwen-2", "8519、8520", [
        "- **範圍**：只動 `web/yiwen.js`、`web/yiwen.css`、包的網頁測試（`tianxia/features/yiwen/tests/` 裡整檔跑 node 的那一個，照別包的寫法）、包的 README 畫面那一段、批計畫。規則、旁檔、路由、資料形狀都不動（第 247 批定的 `main.yiwen` 不夠畫才動，動了寫進 decided 與 `core_changes` 以外的說明）。",
        "- **照哪一版**：企劃者 2026-11-21 下午在對比頁（https://claude.ai/artifact/K9ivGDPrdtbhKixhgVN6MW ）「撞見卡與每一幕」那一處選了「乙」——**頁邊朱批**。原始檔 `" + YW_MOCK + "/card-b.html`（靜態 HTML＋CSS，選擇器前綴 `.yw-card`；**先完整讀它**，樣式的數值照它搬成 `web/yiwen.css` 裡 `.yw-` 開頭的規則，色票用 `web/style.css` 的變數、不寫死色值）。乙版的樣子：一幕畫成一頁書，發掘者的朱批**直書在右邊頁邊**、底下蓋名號小印（像眉批）；順逆章蓋在正文末尾；做法排成一塊路牌——左邊做法、右邊一欄狀態（足跡數字大字；沒人走過的是「免費開」或「問路香 1」的籤，這一批一律畫成鎖著、灰的，籤照畫），有人走過的排前面；「這一段讀不通」是頁下一行（這一批只畫位置、按了回一句「還沒開放」或先不放——回報的事是異聞四，你定、寫進 decided）；檢舉收在頁頂「⋯」（同上）。",
        "- **四個畫面都要做到**（資料從第 247 批的 `main.yiwen` 來）：①撞見卡（發掘者：朱印「異聞」、「你是全服第一個撞見這件事的人」；後來的人：朱印「舊腳印」、「已有 N 人走過」；懸念楷書大字；三顆猜法加發掘者自己填的那一句加「自己說」；這一則岔路開滿時的灰字）；②說了那是什麼之後、每一幕（重放時最上面一行引擎的回聲句；**走到發掘者那一步時省掉回聲句、只留朱批**——PM 定的，對比圖的設計者指出兩句會重複）；③等說書人寫的那一刻（這一波不叫模型，替身當場就有；但畫面要做好，第 249 批接模型時直接用——用假資料的網頁測試畫出來）；④收尾卡（收場句、得失一行；「看這一則的全圖 ›」這一批不放，全圖是異聞三）。江湖頁「進行中」那一行露「異聞・〈…〉（第幾幕）」照設計 10.1（走包的 `status`，不動殼）。",
        "- **乙版的代價要處理**（對比圖的設計者寫的）：頁邊直書吃掉正文約 58px 寬——360 寬時正文一行至少要放得下 14 個字，放不下就把頁邊收窄或朱批改成頁頂橫排（門檻你定、寫進 decided）；朱批最長三十字，直書排不下時分兩行直書、再排不下才縮字，不准比正文那一頁還高出框；名號最長 16 字，小印只放前兩字、全名用小字橫排在印下。別人自己說開的路（下一個人的做法清單裡）另外一列、朱色、帶名號（照 card-b 畫的）。",
        "- **規矩**：照介面設計規範 `docs/superpowers/specs/2026-11-09-介面設計規範.md`（楷書寫名字與故事、sans 寫規則與按鈕、可點的至少 44px、一張卡一顆主鈕、說明收進「？」、按完不跳頂、輪詢重畫不掉輸入中的字）；新按鈕用 `registerClicks`、表單用 `registerForms`，不加進 `app.js` 的 switch；紅點用殼的 `registerDot`（這一批用得到才加）；樣式只寫在 `web/yiwen.css`；`web/` 檔連註解都不准出現「假人」「機器人」「bot」。新字每句旁 `// 待 joy 潤`。",
        "- **拍圖自驗**（照規範第八節；存 `" + YW_SHOTS + "`，路徑寫進回報）：起暫存伺服器（8519、`TIANXIA_PROFILE=season21`、暫存資料庫、模型 127.0.0.1:9；用設定覆寫或測試的做法把 `yiwen.enabled` 打開並開一季——只改你暫存的那份，不提交），用管理者工具或直接擺狀態讓一個角色撞見，走完發掘三步；再用第二個帳號重走。每個畫面 375 淺、375 深、1280 各一張，**另加 360 寬一張看頁邊直書擠不擠**；跟 `card-b.html` 並排看一眼，差太多的地方寫進回報。拍完 `taskkill /T`、刪暫存。",
        "- 測試：網頁測試照計畫「異聞一」列的名字（撞見卡兩種身分、每一幕、發掘者那一步不重複回聲句、朱批超長不破版的 class、跳脫 HTML——玩家自己說的字裡的 `<`、`{}` 原樣顯示）；`tests/bots/test_server_bots.py`、`tests/core/test_shell_stays_thin.py`、`scripts/test_for.py` 挑的跑過。`scripts/webqa` 的走查這一波不加景（開關關著，走不到；等異聞在走查設定打開的那一批）。時間上限兩段合計 3.5 小時。",
    ])


WEB_AF = (
    "**這一波加了新包 yiwen（異聞；開關 `Config.yiwen.enabled` 預設關）**。用 head 的程式實機看，都不花 token：`Start-Process` 分離啟動、輸出導到檔，`docs/superpowers/pm-workflows/wait_file.py <檔> 570` 等，**不要前景跑**；暫存資料庫、模型網址 127.0.0.1:9、拒絕 7861、不寫任何 `.local/`。\n"
    "1. **開關關著**：閘門的網頁比對（`.local/wave_gate/<head8>/web/report.txt`）這一關不重跑，只看 real 是 0、`missing_must_reach` 空（新包的 js、css 多出來的 script 與 link 行工具自己放行）。\n"
    "2. **開關開著**（只在你暫存的 head 複本上用設定覆寫把 `yiwen.enabled` 打開、`TIANXIA_PROFILE=season21`、開一季）：照包的 README 或第 248 批計畫寫的做法讓一個角色撞見（發掘），走完三步；第二個帳號到同一處重走。逐畫面對企劃者挑的乙版 `" + YW_MOCK + "/card-b.html`（頁邊朱批）：撞見卡（兩種身分）、每一幕（朱批直書在右邊頁邊、名號小印、順逆章在正文末尾、做法路牌右邊一欄狀態、鎖著的岔路是灰的）、走到發掘者那一步沒有重複的回聲句、收尾卡、江湖頁「進行中」那一行。375 淺、375 深、1280、**360** 各一張：360 寬正文一行放得下 14 個字、朱批不高出那一頁、沒有橫向捲動；可點的至少 44px；深色看得清。主控台 0 錯誤、網路沒有 4xx／5xx（刻意的除外）。\n"
    "3. 自己說那一格打 `<b>x</b>`、`{name}`、三十個字、三十一個字各一次：前兩個原樣顯示成字、不變粗不被填空，第四個被擋。\n"
    "4. 用假人不會出現的角度看一遍：撞見卡、每一幕、進行中那一行、任何回應，沒有任何欄位或缺欄位分得出誰是假人；`web/yiwen.js`、`yiwen.css` 沒有那三個字。\n"
    "5. 開關開著但這一季沒蓋章（季中才打開）：探索不會撞見、沒有任何異聞的鈕。\n"
    "截圖存你的暫存夾、路徑寫進回報。**不修程式，整關不超過 75 分鐘**，到了就交，沒走到的寫清楚。"
)
AF_FEATURE_LENS = dict(key="feature", text=(
    "**新包 yiwen（異聞一）：掛開關、關著一個位元組不變、開著照設計與總計畫、看不出假人、數值全由引擎**。第 247、248 批；設計 `" + YW_DESIGN + "`、總計畫 `" + YW_PLAN + "`「異聞一」。親自驗（解一份 head 到你的暫存夾，`TIANXIA_DB` 指到暫存檔）："
    "①開關關著：新路由／op 關著的行為照計畫；`PlayerState`、`WorldState` 新欄位空著時存檔一個鍵都不多（自己建一個新角色、存、讀出 JSON 看）；`compare --new yiwen` 的結果開發有貼（沒有就自己挑 `ALWAYS_TRACKS` 六軌 season21 跑一次）。開關開著但季沒蓋章：不撞見。"
    "②照設計第二節 2.1、2.2 與計畫「異聞一」逐條對程式與測試：少做的、做錯的、做多的都列（這一波不該有模型呼叫、不該有開岔路、不該有定論與世界那一格、不該有三條路由——有就是做多了）；挑三條測試把程式改壞跑、看它紅。"
    "③數值全由引擎：撞見、順逆、獎勵的擲骰與種子照計畫（hashlib、不碰 `Game.rng`、不讀時鐘）；獎勵走核心 `apply_effect`；一人一則一季只領一次「走完」（放下再撞見、重整、連點都試）；全服每天與每季的名額在同一筆交易裡數（兩個人同時撞見最後一個名額，只會有一個拿到——讀程式看是不是在行動鎖裡）。"
    "④假人：假人探索不撞見、選單沒有異聞的鈕、足跡不算；任何回應與畫面只露總數與真人做的事。"
    "⑤核心改動只有點頭過的那幾處而且照計畫的寫法（`BUS_ORDER[\"outing\"]` 排在 `guard` 後、欄位 `QUIET` 加 `None`、蓋章一行）；包只 import 核心、共用層、自己（沒有 import 探索包、商城包）；`shell_tables` 沒有多一筆；`server.py`、`engine.py`、`web/app.js`、`main.js`、`style.css` 沒動。"
    "⑥旁檔：建表都是 `CREATE TABLE IF NOT EXISTS`；備份、還原、`_wipe_db` 三處都接到；旁檔寫了而主交易撤回時留下什麼（照計畫的風險那一條）有測試。"
    "⑦玩家自己說的字：HTML 跳脫、大括號不被模板填空、三十字上限、`naming` 與 `speech` 的擋法照計畫；新字都有待 joy 潤、內容檔的字列在 new_strings。"
))
WAVES["AF"] = dict(
    round2=True, feature=True, design=YW_DESIGN, new_packages="yiwen",
    extra_lenses=[AF_FEATURE_LENS],
    lines=[dict(name="異聞一", batches=[b247, b248])],
    merge_port=8521, fix_port=8522,
    web_check=dict(ports="8523、8524", steps=WEB_AF),
)


# ── AG 波：伺服器端擋條款同意（第 249 批）。企劃者 2026-11-21 傍晚「要，另開一批」；PM 查好做法給他看，他選「照這個做，兩處可以動」──
AG_SCOUT = r"C:\Users\ray61\AppData\Local\Temp\claude\81800b313c89d0f8\ade93b70-b3b7-42db-a8af-21f7a7cbdb16\tasks\wg2f2hwzr.output"


def b249():
    plan = "docs/superpowers/plans/2026-11-22-條款-第249批.md"
    return batch(249, "條款第 249 批：必須同意而沒同意的帳號，會改遊戲狀態的請求由伺服器拒絕（不再只靠網頁那一層）", "terms", "dev/terms-gate-249", plan, "8525", [
        "- **點頭（動殼 `server.py` 的 `_game` 與核心 `tianxia/core/terms_base.py`）**：企劃者 2026-11-21 傍晚，PM 問「條款同意那一層現在只是網頁上蓋一層……要不要連伺服器也擋」，他選「要，另開一批」；PM 查好做法之後用選單問「伺服器端擋條款同意，要照我查好的做法做嗎？做法：在所有遊戲動作都會經過的那一個地方加檢查，必須同意而沒同意的帳號，會改東西的動作（選項、出陣、購買、寄信…）一律拒絕並提示『重新整理、按同意』。讀取不擋（不然同意那一層底下畫不出畫面）、管理者不擋（不然會把自己鎖在管理頁外）、登入登出與客服不擋。要動兩處：外殼取角色的那一支函式加一個檢查、核心條款那一小半加一個函式」，他選「照這個做，兩處可以動」。回報的 `core_changes` 逐一列這兩處、附這句原話；**這兩處以外要動殼、核心或 `tests/core/shell_tables.py` 才做得完，停下來寫 stopped**。",
        "- **先讀調查結果**：`" + AG_SCOUT + "`（JSON；`result.a` 是採用的做法〔`proposal`、`gated`、`exempt`、`core_or_shell_changes`、`tests`、`risks`，`facts` 每條附檔名行號〕，`result.verdict` 是懷疑者對著程式找的洞與一定要補的事；`result.b` 是沒採用的做法，不照它做）。調查讀的是 `wave/AE` 的 `1ca6d90b3`，現在都在 develop；跟現行程式對不上的照程式、寫進 decided。上面「計畫不超過 120 行」照舊，寫在 `plan` 那個路徑。",
        "- **①核心 `tianxia/core/terms_base.py`**：加常數 `GATE_NEED`（被擋時回的那一句，新字、旁註待 joy 潤；意思：要先同意使用條款與隱私權條款才能繼續，請重新整理頁面、按過同意——網頁不會自己重問，所以句子要叫他重新整理）與 `gate_problem(content, account_key) -> str | None`：掛鉤沒登記或條款關著回 `None`；否則問掛鉤 `must(account_key)`，任何例外（旁檔鎖住、壞掉、內容檔讀不到）記一行 log、回 `None`（放行：網頁那一層照樣會問）；`must` 為真回 `GATE_NEED`。核心照舊不 import 包、不讀時鐘。",
        "- **②條款包 `tianxia/features/terms/routes.py` 的掛鉤**加 `must(account_key) -> bool`：照 `status()` 同一條路算（`rules.need(...) == rules.MUST`；時間用殼那一側的 `shell.time`；`update_must` 照設定——預設關，所以現在只有「從沒同意過現行版以外任何一版也沒同意過」的人是 `must`，考慮期內的 `ask` 不擋）。快取只放「同意過現行版」（紀錄只加不刪，這個結論不會翻），鍵含旁檔路徑、版號、帳號鍵，放在掛鉤的實例上（測試每條換一個資料庫，不能串）；`must`、`ask` 不快取（按了同意下一個請求就放行）。",
        "- **③殼 `server.py` 的 `_game(request)`**：把帳號鍵留成變數；拿到 `game` 之後、回傳之前加一個檢查——請求不是 GET、`terms_base.gate_problem(CONTENT, key)` 回了字、而且 `game.is_admin()` 為假，就 `HTTPException(403, 那一句)`。只改這一支函式：不加路由、不加頂層名字、不加 middleware，`tests/core/shell_tables.py` 不動（`tests/core/test_shell_stays_thin.py` 要照舊綠）。403 的 `detail` 是字串（網頁的 `api()` 會把它用吐司跳出來，不登出、不跳建角色——先讀 `web/app.js` 的 `api()` 確認）。條款關著時 `gate_problem` 第一行就回 `None`，行為不變。",
        "- **④不擋的要有測試守住**（每一種一條，名字看得出在守什麼）：所有 GET（`/api/main` 輪詢照回 200）；`/api/me`、登入、登出、`/api/terms`、`/api/terms/agree`（按了同意之後原本被擋的 POST 下一次就過）、`/api/terms/version`；客服 `/api/support/*`（沒同意的玩家照樣能寫單）；管理者（名單上的角色沒同意過照樣打得了管理者工具）；`ask`（同意過舊版、考慮期內）的人不擋、考慮期過了也不擋；`update_must` 打開時同意過舊版的人被擋；條款關著全部放行而且回應跟改之前逐字一樣；旁檔讀不到時放行並記 log；註冊時勾過同意的新帳號不擋；假人程式那一側（`run_bots.py` 不 import `server`，掛鉤是 `None`）不受影響。**擋的**至少各一條：`/api/choose`、`/api/do/<op>`（一個 MAIN_ACTIONS、一個鎖外的 op）、`/api/menxia/<op>`、商城購買、帖友書信、移動。測試放 terms 包的 `tests/`（走 HTTP 的照包裡現成的寫法）與 `tests/core/test_terms_base.py`。被擋的回應與畫面沒有任何一處分得出誰是假人。",
        "- **⑤比對情境與測試夾具**：調查查到兩軌直接用 `AccountStore.register` 建一般玩家帳號（`scripts/sb/tracks/abacus.py` 的 LATE、`scripts/sb/tracks/battle.py` 的那一位），在 season21、week7 會落在 `must`、從此 POST 全被擋——在建帳號之後補記同意（經核心 `terms_base.record`；條款關著時它什麼都不做，所以 test 設定與比對基準那一邊不變），這兩軌加 `charter`、`amend` 跑 `selftest`（三種設定）要穩；自己再 grep 一次 `scripts/sb`、`scripts/webqa` 還有沒有別的直接建玩家帳號又去 POST 的（各軌的管理者帳號靠 `is_admin` 放行，確認那個名號真的在 `config.admins`）。把 `server.CONTENT` 換成 week7 或 season21 真內容、又直接建帳號去 POST 的測試（調查列了 `tests/server/test_server.py`、`tests/figures/test_week7_season.py` 幾處）照樣補記同意或改用夾具；改動到核心與殼，跑一次不含 slow 的整套 `-n 4`，紅的逐條分清楚是「這個測試的帳號沒同意過」（補記同意）還是真的壞了。",
        "- **⑥主機用的三樣**：(a) 唯讀清單 `scripts/list_terms_must.py <主資料庫檔>`（`mode=ro` 開主資料庫與條款旁檔、不觸發遷移、不寫任何東西；用條款包同一支判斷算出「現在會被擋」的帳號，只印登入名或帳號鍵與最後同意的版號、最後一行印幾個；管理者名單上的另外標「管理者，不擋」；不印是不是假人——假人沒有帳號，本來就不在表裡）；測試一條。(b) 啟動時的警告：`server.py` 啟動印設定的那一段**不准動殼**——改成條款包自己在掛路由（`router(shell)`）那一下檢查「條款開著、帳號表有人、同意旁檔裡現行版一筆都沒有」就 log 一行醒目的警告（旁檔遺失或搬機沒帶時全體會變成要重新同意）；做不到不動殼就寫進 leftovers、不要硬做。(c) 包的 README 寫清楚：擋什麼、不擋什麼、緊急怎麼關（`terms.enabled` 設 false 重開，網頁那一層與註冊勾選會一起收掉；或退這一批）、旁檔一丟的後果。`docs/guide`、主機端操作文件、`CLAUDE.md` 你不動，句子放回報的 docs。",
        "- **⑦實看一次**：起暫存伺服器（8525、`TIANXIA_PROFILE=season21`、暫存資料庫、模型 127.0.0.1:9、手機通知關掉免得在工作樹生金鑰），用一個沒同意過的老帳號（直接建的）登入：網頁同意那一層照樣出現；不按同意、用瀏覽器主控台或 curl 直接打一個 POST 動作，回 403 與那一句；按同意之後同一個動作過。再用新註冊的帳號確認一切照舊。375 淺、深各拍一張被擋時吐司的樣子，路徑寫進回報。看完 `taskkill /T`、刪暫存。",
        "- **不做**：擋 GET；讓網頁碰到 403 自動重問 `/api/terms`（動 `web/terms.js` 是另一批）；另加獨立的開關或 Config 欄位（跟著 `terms.enabled`）；改條文；identity 開著時帳號鍵一致的問題（寫進 leftovers，開 identity 那一批驗）。退版：資料庫不升版、沒有存檔欄位；換回舊程式就是不擋。新字每句旁待 joy 潤、列進 new_strings。任何輸出都不能分得出誰是假人；不讀不寫任何 `.local/`；不碰 7861。",
    ], custom=True)


AG_GATE_LENS = dict(key="gate", text=(
    "**伺服器端擋條款同意：擋得住、不會把人鎖在外面、關著不變**。第 249 批（企劃者 2026-11-21「照這個做，兩處可以動」）；調查原文 " + AG_SCOUT + "。親自驗（解一份 head 到你的暫存夾，`TIANXIA_DB` 指到暫存檔，用 TestClient 或小腳本打；條款用正式內容 season21 打開）："
    "①**找洞**：grep `server.py` 與每一包 `routes.py` 的每一條非 GET 路由與 `/api/do` 的每一個 op，列出**沒有**經過 `_game` 而又會改遊戲狀態（角色存檔、全服狀態、錢包）的——每找到一條就是 blocker 或 should；只動帳號、客服旁檔、推播裝置的不算。用一個沒同意過的帳號實際打十條不同包的 POST，全部 403。"
    "②**鎖在外面**：沒同意過的帳號登入、`/api/me`、`/api/main`（GET）、`/api/terms`、`/api/terms/agree`、登出、寫客服單都通；按了同意之後原本 403 的那一條馬上過（快取不會卡住）；管理者名單上的角色沒同意過照樣開季、用管理者工具；客服名單上的帳號回單不受影響；剛註冊還沒建角色的人照舊 409 不是 403。"
    "③**不多擋**：同意過現行版的人、考慮期內同意過舊版的人（`ask`）、考慮期過後的人，一條都不擋；`update_must` 打開時同意過舊版的人才擋。"
    "④**關著不變**：條款關著（測試內容、`config.json` 那一層）時 `_game` 的行為對 base 逐字一樣；殼的 diff 只有 `_game` 那一支函式；`tests/core/shell_tables.py` 沒動；核心沒有 import 包、沒有讀時鐘。"
    "⑤旁檔讀不到（把旁檔換成一個壞檔、或讓掛鉤丟例外）時放行而且有 log、不 500；快取鍵含旁檔路徑（換一個資料庫、同名帳號不會被前一個庫的同意放行）。"
    "⑥比對軌補記同意的那兩處在條款關著時真的什麼都不做（test 設定的輸出對 base 一樣）；`scripts/list_terms_must.py` 用 `mode=ro`、不寫、不印任何分得出假人的欄位。"
    "⑦403 的句子有待 joy 潤；被擋的回應裡沒有任何欄位分得出誰是假人。"
))
WAVES["AG"] = dict(
    round2=True,
    extra_lenses=[AG_GATE_LENS],
    lines=[dict(name="伺服器擋同意", batches=[b249])],
    merge_port=8526, fix_port=8527,
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
