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
    ap.add_argument("--opus", action="store_true", help="每一批都用 Opus（沒有逐批審查時比較保險）")
    ap.add_argument("--leftovers", default="", help="上一波開發回來的 built（JSON 檔）：寫到某一批的 leftovers 接進那一批的派工")
    a = ap.parse_args()
    w = WAVES[a.wave]
    args = {"wave": a.wave, "scratch": a.scratch, "branch": f"wave/{a.wave}", "merge_port": w["merge_port"], "fix_port": w["fix_port"]}
    if w.get("round2"):
        args["round2"] = True
        args["master"] = R2
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
        name = f"wave-{a.wave}-finish.js"
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
