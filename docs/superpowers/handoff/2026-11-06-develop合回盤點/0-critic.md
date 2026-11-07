# develop 合回主幹盤點 0：完整性檢查與建議的分段（先讀這一份）

> 11/06 唯讀盤點（工作流程 `wf_4c64148d-820`），量的時候主幹 `0176753d`（檢查者另對 `3e2271a4`）、develop `99f6a79b`。第 27、50 批之後主幹是 `f7b17ed7`，行號開工前重量。

**develop 合回主幹：完整性檢查（11/06）**

全程只讀，沒改檔、沒 commit、沒跑測試、沒碰分支。行號是那一版的行號，標「推測」的是沒驗過的。

## 〇、基準跟四份地圖不一樣了（要先知道）

- 四份地圖都拿主幹 `0176753d` 量。fetch 之後主幹是 `3e2271a4`：第 50 批在 11/06 10:59 合進來了（`d9bb87ff`），後面接一筆文件。
- develop 是 `99f6a79b`，錨點是 `17c5199d`，沒變。
- 第 27 批還沒進主幹：`origin/dev/seal-1` 在 `bf660c67`，比主幹多 9 筆。拿它跟現在的主幹試合，撞 3 個檔：
  - `test_feature_boundaries.py`
  - `core/__init__.py`
  - `features/battle/README.md`
- 第 27 批改到的檔裡，有 11 個 develop 也改了：
  - `engine.py`、`rules.py`、`core/__init__.py`、`registry.py`、`services.py`
  - `battle/view.py`、`bout/arena_actions.py`
  - `same_behavior.py`
  - `test_contract_features.py`、`test_feature_boundaries.py`、`test_test_for.py`
- 拿 `3e2271a4` 對 develop 重跑 merge-tree（樹 `b3a9682e`）：撞檔 **32 個**，比四份地圖的 31 多一個 `tianxia/features/battle/muster.py`（只撞 import 那一行）。
- 各檔的衝突塊數（merge-tree 算法）：
  - engine 12、registry 3、server 2、content 2
  - core/__init__ 1、services 1、guide/actions 1
- 第 50 批動到的檔裡，有 19 個 develop 也改了（含 core 三檔、`guide/actions.py`、`sortie/duel_actions.py`、`conquest.py`、`models.py`、`engine.py`、`muster.py`）。下面這幾處主幹行號移了，四份地圖引用的位置要以新的主幹重量：
  - `features/explore/explore_base.py` 多了 3 行，engine 地圖寫的 `:90/:96` 現在是 `:93/:99`。
  - `guide/actions.py` 頂端的 import 拆成兩行。
- 試合清單在 `C:\Users\ray61\AppData\Local\Temp\claude\4d5f79bfb143ac0b\86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444\scratchpad\mt2.txt`。

## 一、四份都沒涵蓋到、合回時一定會碰到的事

**1. 資料庫與旁邊的小檔**
- 主資料庫兩邊都是 `SCHEMA_VERSION = 9`（`database.py:326`），不用遷移。
- develop 新加的存檔欄位都有不寫進存檔的預設：
  - `PlayerState`：`growth_preset`、`growth_custom`、`attr_event`、`attr_alloc`、`legacy`
  - `WorldState`：`places`、`attrs_v2`
  - 對打快照：`card`、`dodge`
  - `stamp_season` 蓋 `attrs_v2`（`world_state.py`）
- 小檔有變，四份都沒寫：
  - 戰記小檔 `<db>-tale.sqlite` 新開一張 `shares` 表（develop `tale.py:547`，`CREATE TABLE IF NOT EXISTS`，沒有版本號）。分享代碼是 `secrets.token_urlsafe` 隨機出的（`tale.py:574`）。
  - 新的 `<db>-talk.sqlite`，另有 `-talk-archive.sqlite`（`talk_log.py:5`）。
- 對行為比對的影響：
  - `same_behavior` 只把主資料庫轉成文字（`same_behavior.py:327 db_text`），小檔不在比對裡。
  - `run` 開頭清舊檔的清單（`:1515`）是「主檔名＋後綴」的寫法，往來紀錄的小檔名字是另一種寫法（`db.stem`），清不到。
  - 推測：同一個暫存資料夾跑第二次時，舊的往來紀錄還在；只要有回應讀到它，「同一份跑兩次一樣」就不穩。
- 戰記頁要做兩台伺服器的位元組比對（E 段）的話，要先把分享代碼的亂數固定。第 27 批認定「只在新軌固定密鹽」可以照用（記在 `0176753d` 那一列）。
- 備份要一起帶兩個小檔：`docs/superpowers/feedback/2026-11-05-上線退版風險-給joy.md` 第三節。

**2. 煙霧測試的數量上限（推測會紅）**
- `tests/core/test_test_for.py:669` 斷言 `100 <= len(ids) <= 150`。
- 主幹約有 148 個 `@pytest.mark.smoke`，develop 新加 3 個（招募 1、傳承 2）。
- 推測合併後到 151 條以上，這條會紅。
- 同一條測試的 `:676` 要求每一包至少一條煙霧；招募與傳承兩包都有，不會紅。

**3. test_for 的挑法**
- `attrset` 一旦進核心 `MODULES`，test_for 就把它當核心：改它要跑核心測試加煙霧（`core/__init__.py:44-47` 的說明）。
- 連帶 `tests/core/test_attrset.py`（467 行）會併進「核心測試」，改任何核心模組都會多跑它。要不要放進 `NOT_CORE_TESTS`（world、step 的前例）要 PM 定。
- test_for 預設跟 `origin/develop` 比（`scripts/test_for.py:94`）。
  - 在合併分支上跑，等於主幹的整段拆分全算「改動」，幾乎全挑，第 1 段等於整套。
  - A～D 段要設 `TIANXIA_TEST_BASE=<第 1 段結果 SHA>`。

**4. 拿 develop 當比對的 base**
- 已登記的 39 軌裡 38 軌的「改一字」跑在 week7，只有 zhuan 跑 season21；sortie、duel 與探索比對也都是 week7（`same_behavior.py:63`、`:1549`）。所以拿 develop 當 base 時，每一軌的 selftest 都在「五項屬性＋傳承」的季裡跑。
- 這點對 features 地圖第一節第 1 點（卡在開季準備卡、空驗）是好消息：真的被卡住的話，改一字抓不到，selftest 自己會紅。
- 只在主幹起得來的寫法：
  - `:17432 from tianxia.features.peers import invites`：沒有退路，develop 根一定起不來。
  - `:20768` peers 的假人：有 try/except，沒問題。
  - `:11047` explore_base：有 hasattr 退路，沒問題。
- 36 軌的改一字目標檔，我逐一對過，develop 上都有舊路徑，找得到。
- engine 地圖說 `same_behavior`「合得乾淨、不用搬」，這不完整。

**5. 功能包在 FEATURES 的位置算行為**
- develop 把 legacy、hire 緊接在 bout 後面（develop `registry.py:28-47`）。
- 主幹 bout 後面已經接了 7 包：stamina_plays、seclusion、peers、travel、map、faction、gear（`registry.py:106-114`）；第 27 批還會加 seal。
- 要逐個掛鉤驗先後：options、status、prep、on_season_start、bot_pick、check_content 的錯誤先後。
- 歷史：第 23 批認定過「bout 排最後」（手冊 `:442`）。

**6. 世界層掛鉤與換季**
- 主幹把 `world.py`（+204）、`sqlite_world.py`（+102）改成世界層的格，契約測試守 `WORLD_ORDER`（`test_contract_features.py:324-345`）。develop 沒動這兩檔。
- 傳承的結算在包的 `on_season_start`，地點的樣子（`places`）在換季時清掉。推測要靠新開的 legacy 軌才看得出先後對不對。

**7. 還沒做的批，範圍會變大（總表要重量）**
- 第 28 批（總表 `:158`）：develop 的 `seal_duel.py`（+15/−3）與玉璽那 5 個方法。
- 第 52 批（`:197`）：戰記。
- 第 55 批（`:205`）：`_reset_player_for_new_season` 帶 legacy 那一行。
- 第 66 批（`:221`）：
  - `/api/main` 多了 growth、lilian、prep、figures_here、talk、place_state 這幾個鍵；
  - 網頁 app.js、main.js 多 1,387 行。
- 第 45 批照交接排在合回之後。

**8. PM 的工作流程腳本寫死了 split/trunk**
- 寫死的地方：
  - `docs/superpowers/pm-workflows/split-batch.js`（2 處）
  - `split-merge.js`（2 處）
  - `trunk_daily.py`（1 處）
  - `paused-1104/make_more.py`（13 處）
- 要等「合回之後拆分在哪裡做」定了才能改。
- 推完之後：
  - `trunk_daily` 的 `verified.txt` 基準要重設。
  - 每天 03:30 的 `scripts/nightly.ps1` 跑的是 develop（tianxia-flow `SKILL.md:45`）。推測推完的第一次夜跑，「新紅／舊紅」那幾段整批會換。
- 這台機器的限制：
  - 同一台最多兩份測試（`trunk_daily.py` 開頭的說明）；
  - 全面檢查約 25 分鐘（交接 `:68`）；
  - 主機也是企劃者的遊戲電腦，說暫停就要停。

**9. 推上 develop 要是快轉，main 也要看一眼**
- 交接 `0176753d` 記的企劃者答覆：推上去的那一筆 develop 是快轉；Joy 與雲端不通知。
- 現在 main 比 develop 多 2 筆（`9a4ce175`、`7e623376`），都是合併提交，內容差是空的（`git diff develop...main` 沒有東西）。
- develop 的 CLAUDE.md 寫 Joy 可以直推 main，所以推之前要再看一次 `origin/develop..origin/main` 有沒有實際內容。

**10. 還在送的 PR 與分支**
- 這台的 Bash 和 PowerShell 都找不到 `gh`，查不了 PR 開沒開著。
- refs 上看得到：`refs/pull` 最大到 #175；#164～#175 的 head 都在 develop 裡。
- 不在 develop 的遠端分支有 4 條：
  - `claude/admin-gallery`（11/04，2 筆）：改形象包的 actions、測試、`app.js`、`mall.js`。主幹沒動形象包，推測合得進。
  - `claude/project-thread-lufhry-firstscreen`（10/31）：改網頁與 `test_jianghu_page_web.py`、`test_opening_web.py`。這兩檔 develop `51787b33` 重寫過，主幹也改了 −58 行，推測已經過時。
  - `claude/project-thread-elv46w`：沒有內容差。
  - `claude/sleepy-shannon-glqkoc`：只有文件。

**11. develop 上有標「不合 main」的東西**
- `4de6fb28`（PR #173）的提交訊息寫「介面重整四塊（分支試用，不合 main）」；`51787b33` 後來拿掉了舊版面的開關。
- 寫 CLAUDE.md 與交接時要記上。這影響的是之後 develop 上 main，不影響這次合併。

**12. 腳本讀設定的慣例**
- 主幹第 14 批把腳本的預設改成 `serving_profile()`（沒帶設定就套 season21），例：`scripts/season_clock.py:21`。
- develop 新加的 `scripts/measure_legacy.py:23`、`:92` 用的是 `env_profile()`。推測要照主幹改。

**13. 另外查過、沒問題的**
- `pyproject.toml`、兩份 requirements 兩邊都沒動；沒有 CI，`.github` 只有 PR 範本。
- develop 沒改 `content/config.json`；`tests/fixtures` 只動到 develop 的 `traits.json` 和主幹的 `config.json`，不撞。
- develop 新增的測試、包、腳本，沒有叫到主幹 Game 已經拿掉的 168 個成員（我用語法樹掃的）。
- develop 新增的測試沒有 import 主幹已經刪掉的模組。
- develop 改到的 8 個 server 函式，主幹的 server 都還在。
- 主幹沒有新寫的網頁測試，搬家的只有 M、D、R 三種，所以新版面（`51787b33`）不會打到主幹自己寫的版面斷言。

## 二、四份地圖之間的矛盾與數字

1. **基準與撞檔數**
   - 四份都用 `0176753d`；features 第六節寫「撞檔 29」，是舊數。
   - engine 寫 engine.py 14 塊、core/__init__ 2 塊（diff3 算法）；files 寫 12、1（merge-tree）。
   - 現在是 32 檔；engine 12、core/__init__ 1。
2. **第 50 批**
   - features 說「跟 develop 沒有交集」，錯：實際有 19 個檔重疊，muster.py 撞。
   - engine 說「dev/map-2（`251df23a`）是主幹的祖先、查不到它的程式」，也錯：它不是 `0176753d` 的祖先，現在已經合進來了。
   - files 說它會改到 muster 等檔，是對的。
3. **9 個新方法有幾個要離開 Game**
   - features 第〇節寫 6 個、約 80 行；它自己的 A 段（2 個）加 D 段（3 個，place_state_view 待定）是 5～6 個。
   - engine 是 5 個（place_state_view 留核心）。
4. **pick_growth 的寫法**
   - features 寫「Game 留一行委派」。
   - engine 寫「Game 自己保留三步」：籌備中擋、這一季沒有配比、已經定了回 `Refused`。理由是 `Refused` 只在 `engine.py:287`，包拿不到（前例 `bout/arena_actions.py:494`）。
   - 照 engine 的寫法，它就不是一行委派：`GAME_DELEGATES` 不加，`("choose","pick_growth")` 也不用進 `GAME_DELEGATE_CALLERS`。兩份卻都寫要加。
5. **legacy、hire 排在哪**
   - files 寫「要定」；engine 寫「接在 gear 後面」，沒驗；features 也寫 gear 後面，但標了「推測、要驗」。
   - develop 實際是緊接 bout（見一之 5）。
6. **GROWTH_* 三個常數**：files 寫「放哪要 PM 定」；engine、features 都說留在 engine（bot.py:20 從 engine import）。
7. **place_state_view**：engine、features 建議留核心；files 引 11/05 稽核，歸大勢人物包。
8. **epiphany 的插入點**
   - files 寫「:176 前」（那是 develop 的行號）；engine 寫「174 那行之後」，描述是對的，行號是錯的。
   - 主幹上，172～173 是 `if rng.random() < odds * boost: return True`，174 是 `p.epiphany_dry += 1`，所以要插在 173 與 174 之間。
9. **same_behavior 要不要改**：features 說要補「開季準備卡那一步」和 roadmate 那一行 import；engine 說合得乾淨、不用動；files 推測基準要重抓。實際是 features 對（見一之 4）。
10. **talk_log**
    - engine、features 都說進人物情誼包，features 另說舊名留別名；docs 寫「位置待定」。
    - 留別名的話，主幹 `test_feature_boundaries.py:1800` 寫死的別名對照表要加一筆；`tests/server/test_talk_log.py:60-65` 直接叫 `server.api_talk_log`，也要改（engine 第三節第 6 點）。
11. **features 第五節「主幹 41 軌」**：對得上。已登記 39 軌，加 sortie、duel；探索比對另算。

## 三、建議的做法與分段

**第 0 段（PM 準備，可以跟第 27 批並行）**
- a. 先把第 27 批合進主幹（撞 3 檔）。主幹 SHA 定了之後，重跑 merge-tree，四份地圖的行號重量一次。
- b. 一次問企劃者四題：
  - 合回之後拆分在哪裡做（繼續 `split/trunk`，還是直接在 develop）；
  - 「搬包中」的規矩選甲還是乙；
  - 戰記現在拆（E 段），還是照第 52 批；
  - 招募的內容檔只改名，還是拆出人物表（後者行為會變）。
- c. PM 自己定、寫進手冊第十五節的認定：
  - `attrset` 進 `MODULES`
  - `prep` 掛鉤留不留，補上真正點頭的人
  - `place_state` 進 `SHARED`
  - legacy、hire 是獨立包，排在 FEATURES 的哪裡
  - `growth:` 前綴留核心
  - pick_growth 的寫法（見二之 4）
  - GROWTH_* 常數、place_state_view、talk_log 的歸屬
  - `figures.side_name`
- d. 補強 same_behavior。這支腳本是拿同一份去跑兩個根，所以在合併分支上改就好：
  - 開季準備卡出現時，照預設配比按 `growth:`，識海按 `legacy:skip`；
  - roadmate 那一行補退路；
  - 推測要補：清掉往來紀錄的小檔；
  - 先對 develop 根跑 `selftest`：所有軌、探索比對、假人，起不來、改一字抓不到的都修到過。
- e. 先寫新軌 `growth`、`legacy`，在 develop 上 selftest 過。第 1 段就要靠它們驗 FEATURES 位置與換季帶走的東西。
- 量：中。推測每軌 300～600 行（features 估的）。

**第 1 段（單獨、照順序、最大）：合併加照新位置搬**
- 要做的：
  - 32 個撞檔，加上第 27 批跟 develop 重疊的那幾處；
  - engine 12 塊；9 個委派方法的改動改寫進 7 個包檔；8 個別名模組；`rules._fx_stats`；核心三檔；
  - `guide/actions.py` 的 `_more_triggers` 改走 `services.checkin_on`、`seal_base`，加一個新委派；
  - 兩處相對 import 改絕對；
  - `figures_here_view` 的 `_talkable`、`_why_not_talk`（不改會丟 AttributeError）；
  - `test_attributes.py` 的 ALLOWED 改新路徑；`test_hints.py` 換掉的目標改；
  - 煙霧上限；
  - 主幹那 55 個沒在五項屬性下跑過的測試，預期一批紅（develop 自己打開時修了 24 條，`e9907a84`）。
- 9 個新方法這一段先修到能跑。暫時進 `GAME_DIRECT` 的要寫明「第 2 段 X 收」，最後的閘門要確認一條都不剩，才符合企劃者的「一併拆進包、不記過渡」。
- 招募改內容檔名那 10 行碰到核心的 `content.py`，建議併進這一段。
- 7 個撞檔文件照 docs 地圖解掉就好；CLAUDE.md 這一段只解撞，不重寫。
- 證明：
  - `same_behavior compare`，base＝`origin/develop`（記下 SHA），head＝這一段的結果；
  - 所有軌 × season21、week7、test 三種設定，加假人、探索比對、兩條新軌；
  - 再跑 `docs/superpowers/pm-workflows/undef_scan.py tianxia server.py`；
  - 整套含 slow 跑一次：A～D 都從這一段開分支，底要穩。
- 量：核心批以上。交接 `:78` 記核心批 184 萬 token、2 小時 19 分；這一段推測 3～5 小時、200～400 萬 token。

**第 2 段（並行，各從第 1 段的結果開分支）**
- A 屬性 v2 的動作進修練包：小，約等於一般一批（60～90 分）。
- B 傳承補規矩：中。
  - 從 app.js 切約 130 行到 `web/legacy.js`；
  - 改 `index.html`、`webharness.APP_FILES`、README；
  - 局面檔、契約的 `prep` 兩條。
- D 人物與地點畫面加往來紀錄：中。
  - 4 個方法；`talk_log` 119 行加路由 19 行；
  - 新軌 `here`、`places`，往來紀錄用兩台伺服器的 HTTP 比對。
- E 戰記：大，可選，建議照第 52 批。
- C 招募：沒併進第 1 段的話，排在第 1 段之後，不要並行。
- 會撞的熱點：
  - `test_feature_boundaries.py` 的 `GAME_DELEGATES`（A、D 都改）；
  - `same_behavior.py` 檔尾（每一段都加一軌）；
  - `engine.py`（A、D）；`server.py`（D、E）。
- 每一段：
  - test_for 用第 1 段的 SHA 當 base；
  - 跑自己的新軌和碰到那一包的軌，base 一樣是第 1 段用的那個 develop SHA；
  - 照 A→B→D（→C、E）的順序合，後合的照字面解，合的時候只跑相關的軌（同一件事只驗一次）。

**第 3 段（PM）：CLAUDE.md 與文件**
- 等 A～D 的落點定了，照 docs 地圖起草：
  - develop 的 CLAUDE.md、tianxia-flow／dev／qa 三份技能檔；
  - 手冊 G19 與各批認定；
  - 總表第 28、52、55、66 批重量；
  - 交接第六節的分支表；docs/guide 的路徑；PR 範本。
- **在最後再合一次 develop 之前給企劃者看**，回饋才來得及收進去。
- 第 0 段 b 那兩題沒答之前，L18、L19 和 tianxia-flow `:27/:28/:58` 寫不下去。

**第 4 段（最後一次坐完）：再合 develop、總閘門、推**
- fetch。develop 有動，就再合一次 `origin/develop`。只對差的那一段（第 1 段用的 develop SHA 到新的 develop）重做掃描：
  - 改到主幹已是別名的檔；
  - 改到主幹已是委派的 Game 方法；
  - 新增的 `self.`／`ctx.` 有沒有叫到主幹 Game 已經沒有的成員；
  - 搬進包的檔有沒有相對 import；
  - `undef_scan`。
- 閘門：
  - same_behavior 所有軌加新軌，base＝新的 `origin/develop`；
  - 整套含 slow 一次（交接寫「全面檢查在合回 develop 那一段的整套裡一起跑」）；
  - season21、week7、test 三種設定各載內容、各起伺服器（第 13、14 批合併閘門的前例）。
- 推之前：
  - 看 `origin/develop..origin/main` 有沒有實際內容，有就先把 main 合回來；
  - 確認 `git merge-base --is-ancestor origin/develop <最後那一筆>`，推上去要是快轉；
  - 推完確認那一筆真的在 `origin/develop`。
- 閘門跑到一半 develop 又動了：推測只對新多的那幾筆跑掃描、test_for、碰到的軌，不重跑整套。要 PM 定。
- 推完之後：
  - `C:\Ray\專案\ai遊戲` 那份在乾淨時 `pull --ff-only`（G17）；
  - 重設 trunk_daily 的 `verified.txt` 和夜跑的基準；
  - 改工作流程腳本裡寫死的 split/trunk；
  - 更新架構流程圖；
  - 開第 45 批。
- 時間：避開 03:30 的夜跑和企劃者用顯卡的時段；每週額度到 85% 就停。
