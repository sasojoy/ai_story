# 規範盤點：之後所有人做事的規範寫齊了沒有（develop 5fccb11a，2026-10-31）

唯讀調查員，對象：開發規範手冊 `docs/superpowers/specs/2026-10-30-開發模式-design.md`、`CLAUDE.md`、`.claude/skills/` 四份技能（含 `網頁.md`、`引擎驗收.md`）、`docs/guide/*.md` 開頭與規矩段、`docs/superpowers/handoff/2026-10-30-主機側交接.md`、`scripts/new_feature.py`、`tianxia/core/`、`tianxia/features/*/README.md`、批次表 `docs/superpowers/plans/2026-10-31-主動搬六包-批次.md`。

## 結論

**還沒寫齊。** 「怎麼搬一包」寫得很細（手冊第三、四、十五節、批次表第二節、核心與存檔導覽、三包的 README），但「搬以外的日常」有四塊空著或互相打架：

1. **雲端 session、Joy 的 Claude 照什麼做事**：`CLAUDE.md` 一個字都沒寫（雲端最先讀的就是它）。手冊說「沒有人直接推 develop／main、雲端開 PR、PM QA 後合」，可是實際上是另一套：雲端的 PR #100～#110 由 `sasojoy` 在 GitHub 直接合進 develop，`68b4b8d7` 由雲端直推 main，PR #111（develop → main）10/31 17:09 也是 `sasojoy` 合的。交接第七節自己也寫「雲端常常直接推上 develop，PM 事後驗」。
2. **新功能的一包除了骨架以外怎麼長**：欄位與 `Config` 放哪（核心不准 import 包）、內容 json 怎麼載、網頁檔放哪、三段式模型呼叫怎麼接，都沒寫。`new_feature.py` 只生 `__init__`、README、煙霧、stage、導覽標題、登記這六樣，`tianxia-dev` 卻寫成會生十樣。
3. **企劃者 10/31 的決定都還沒寫回去**：手冊第十一節五件、內測在這台跑、上 main 一律從 develop 合、週末與 14 天季及三選一整套拿掉、要問 Joy 的直接問企劃者。技能、導覽、批次表裡還有六處標著「等 Joy」。
4. **「全部拆完」沒有路線**：手冊只寫了六包加碰到才搬。`Game` 現在還有 1,033 個方法、`engine.py` 17,650 行，批次表十二批大約只碰到兩成。

另外有一個流程上的坑：主 clone `C:\Ray\專案\天下大勢` 的 checkout 停在 main `4e03895b`（10/21），落後 origin/main 1,162 筆。在那裡開的新對話讀到的是 10/21 的 `CLAUDE.md` 和技能，裡面沒有手冊，這一輪的 system 給的 `CLAUDE.md` 就是那一份。`ai遊戲` 那份停在 `68b4b8d7`，也沒有手冊那一行。

標記說明：**需企劃者**＝要企劃者點頭（`CLAUDE.md` 或規則本身）；**PM 可改**＝手冊落地補註、技能、交接、導覽。

---

## 一、缺的

### G1 雲端 session 與 Joy 的 Claude 怎麼做事（需企劃者）
- **問題**：`CLAUDE.md` 沒有這一段，雲端與 Joy 的 Claude 開工讀的就是它。手冊第五、六節只寫了原則，而且跟現況不合（見矛盾 C1）。交接第三節那封給 Joy 的原稿（「一塊從開工到合進 develop 之間請不要改那一塊……Game 上那一行委派不要再加邏輯……推完告訴 PM 是哪個方法」）因為企劃者說「不用轉」，**沒有寄出去，也沒寫進任何規範**，所以雲端並不知道。
- **寫在哪**：`CLAUDE.md`「工作目錄與分支」加一條；`tianxia-flow`「分支」照抄成執行版。
- **建議的字**：
  > - **雲端 session 與 Joy 的 Claude**（企劃者 2026-10-30「只要符合開發規範，不管是本機還是雲端都沒差」；10/31）：開工先讀 develop 上的開發規範手冊與 `tianxia-flow`。在自己的分支（`claude/<名字>`）做，推上去開 PR 到 `develop`。PR 說明寫五樣：改了哪一包（或 `Game` 哪一群方法）、跑了哪些測試、幾條過、退版風險、新寫「待 joy 潤」的字。**不直接推 `main`**（10/31：上 main 一律從 develop 合）。批次表寫著「開工」到「已合進 develop」之間的那一包不要改。已經搬進 `tianxia/features/<包>/` 的功能改包裡的檔，`Game` 上的一行委派不加邏輯。新功能一律 `scripts/new_feature.py` 生一包。雲端的回饋單號用 8000～8999。Joy 的維運與緊急修正照舊可以直推 `main`，推完跟企劃者說一聲：哪一筆、改了哪個方法。PM 下一次合併先把 main 合進 develop，改到已經搬走的方法就照抄進包。

### G2 PR 怎麼開、誰合進 develop、合之前跑什麼（需企劃者）
- **問題**：手冊第五節寫「進 develop 只有 PM 合（QA 過、三級綠）」、「PM 合也走 PR（`gh pr merge`）」。可是這台沒有 `gh`（交接第三節），PM 都在本機合、推。雲端的 PR 實際上是 Joy 的帳號 `sasojoy` 在 GitHub 上合的，沒經過主機側 QA（例：`04cbff00`「正式設定打開推送與模型佇列」就這樣進了 develop）。誰合、合之前誰跑什麼，三個地方三種說法。
- **寫在哪**：手冊第十五節（第五節）；`tianxia-flow`「分支」。
- **建議的字**（請企劃者二選一）：
  > - 甲（照現況）：雲端的 PR 由企劃者或 Joy 在 GitHub 合進 `develop`。合之前雲端自己跑 `scripts/test_for.py --base origin/develop`、不含 slow 的整套、那一包相關的 slow，PR 說明寫條數。主機側 PM 不先 QA，第二天早上照每日整套（`latest.txt` 的新紅與 develop 新進的提交）事後驗，紅了開 FB 交回那條線，新紅三天沒修就 revert。
  > - 乙（照手冊原文）：雲端只開 PR、不合。PM 拉下來派 QA，三級綠、QA 過了在本機合進 develop、推，再到 GitHub 關 PR。
  > - 主機側的子代理照舊推 `dev/`、`qa/` 分支，由 PM 在本機 `git merge --no-ff` 合、推（不經 PR）。

### G3 上 main 的步驟與證據（需企劃者）
- **問題**：企劃者 10/31 定了「之後上 main 一律從 develop 合、先跑整套含 slow」。`tianxia-flow` 的「上 main 用上線分支 `release/<日期>`」與手冊第五節還在，可是 PR #111 是 develop 直接合進 main，看不出誰跑了整套含 slow、哪一個 SHA 綠的。部署說明有沒有寫，也沒有地方記。
- **寫在哪**：手冊第十五節（第五節）；`tianxia-flow`「流程」第 6 步與「上 main 用上線分支」。
- **建議的字**：
  > - **上 main**（企劃者 2026-10-31）：一律從 `develop` 合。合之前由合的人跑整套含 slow（`scripts/test_for.py --all`，`-n 4`，`TIANXIA_DB` 用暫存檔）。結果（SHA、passed 條數）寫進 PR 說明或交接第五節，綠的 SHA 要等於要合的 develop HEAD。這一次要拿掉某一樣，才開 `release/<日期>` 做 revert（10/21 的做法）。在 GitHub 按 PR 合的人（Joy）也一樣：PM 或雲端先跑完，在 PR 留言「整套含 slow N passed @<SHA>」，SHA 對得上才按。部署說明（含〈退版風險〉，見 G13）跟 PR 同一天寫好，經企劃者給 Joy。

### G4 內測 develop 在這台主機跑（需企劃者：對外網址、埠、叫不叫模型；其餘 PM 可寫）
- **問題**：企劃者 10/31 答了「在這台主機跑（另一個資料庫、另一個埠），開一次 21 天的季試玩」。現有的規範全寫成「PM 寫部署說明給 Joy」（手冊第五節、11.5，`tianxia-flow` 第 17、27、124 行），怎麼在這台跑一個字都沒有。
- **寫在哪**：`docs/superpowers/feedback/beta-主機端操作.md` 新一節「內測 develop」；`tianxia-flow` 分支表 `develop` 那一列與「流程」第 5 步；手冊第十五節（11.5 的答案）。
- **建議的字**：
  > ## 內測 develop（企劃者 2026-10-31：在這台主機跑，另一個資料庫、另一個埠，不碰線上那一份；先開一次 21 天的季）
  > - 程式：`.local/devtest/checkout`（`git worktree add --detach`，跟 `.local/nightly/checkout` 分開），只從 `origin/develop` 更新。換到每日整套綠的那一筆（`latest.txt` 的 SHA）：先備份，再停、`git checkout --detach <SHA>`、重開。季中換程式照〈退版風險〉看能不能換。
  > - 資料庫 `TIANXIA_DB=<repo>/.local/devtest/tianxia-dev.db`，設定 `TIANXIA_PROFILE=season21`，埠【待企劃者，建議 7862】。啟動時印的資料庫路徑、設定、埠要跟線上那一份不一樣。管理者照 `.local/admins.txt`。
  > - 不開 `run_bots.py`（假人先不開）。模型【待企劃者】：照舊叫這台的 Ollama（跟線上搶顯卡）；或 `ollama_url` 指到死埠，內測不叫模型。
  > - 對外【待企劃者】：只給區網（`--lan`）；或具名 Tunnel 另開一個子網域（改 Tunnel 是持久設定，企劃者按或同意 PM 改）。
  > - 內測的回饋走試玩回饋那一串（從 1 起，來源寫「內測」）。開季、收季、換程式都記進交接第一節。

### G5 手冊第十一節的答案與 10/31 的決定寫回手冊（PM 可改）
- **問題**：第十一節還寫著「要 Joy 同意的」。第四節 4.2 的表、4.4、第五節、第六節、第十二節第 0 階那一列都還是提案的說法。
- **寫在哪**：手冊第十一節整節換掉；第十五節加一條。
- **建議的字**：
  > ## 十一、要 Joy 同意的（企劃者 2026-10-31 直接答了；「要問 Joy 的直接問企劃者」）
  > 1. develop、main **不開**分支保護，照規矩口頭遵守（第五節「強制走 PR」作廢）。
  > 2. Joy 的維運與緊急修正**照舊直推 main**，推完說一聲，PM 合回 develop。
  > 3. 合併閘門**照舊**：合進功能分支、develop 時動到 `tianxia/`、`content/`、`server.py` 就跑不含 slow 的整套，加上那一包相關的 slow（批次表第二節）。每天 03:30 另跑整套含 slow。**不改成**「合併只跑三級」（4.2 表上「合進功能分支／合進 develop」兩列作廢）。
  > 4. 03:30 可以（已註冊 `TianxiaNightly`）。
  > 5. 內測 develop **在這台主機跑**（另一個資料庫、另一個埠，不碰線上），先開一次 21 天的季（做法見 `beta-主機端操作.md`「內測 develop」）。
  > - 同一天另外定的：線上 main `68b4b8d7`（雲端與 Joy 直推的）認了；之後上 main 一律從 develop 合、先跑整套含 slow。鐵匠鋪網頁 A、C、E 三批改給主機側做。週末設定、不帶設定的 14 天季、探索三選一整套拿掉，排在搬完六包之後。

### G6 改「還沒搬的舊功能」：順手搬還是改在原位（需企劃者）
- **問題**：手冊 3.4.3 寫「碰到才搬、順手搬」，`tianxia-dev` 第 14 行寫「也可以順手搬」。可是企劃者 10/31 選的是「主動搬六包」，批次表寫「一次只做一批」，每一批都要 `same_behavior.py` 加實機逐像素才算證明，順手搬做不到這一套。沒寫的還有兩樣：什麼算「新功能」（一律新包），什麼算「舊功能的延伸」（改原位）；改還在 `engine.py` 裡的功能時能不能在 `Game` 上加新方法。
- **寫在哪**：手冊第十五節（3.4.3）；`tianxia-dev`「開工」；`CLAUDE.md`「原則」加一行。
- **建議的字**：
  > - **改哪裡**（企劃者 2026-10-31 定主動搬六包之後）：①還在 `engine.py`／舊模組的功能，修 bug 與小延伸（同一個前綴、同一個玩法）照舊改在原位，可以在那一群加方法，**不順手搬**。搬包只由批次表的批做，因為搬的那一步要 `same_behavior.py` 加實機證明。②已經搬進 `tianxia/features/<包>/` 的改包裡，`Game` 上的一行委派不加邏輯。③正在搬的那一包（批次表「開工」到「已合進 develop」）不改，非改不可推自己的分支、告訴 PM，由搬的那一批接。④全新的玩法（新的選項前綴、新的開關、新的畫面）一律 `scripts/new_feature.py` 生一包，不加進 `engine.py`。

### G7 新包的狀態欄位與 Config 放哪（PM 可改）
- **問題**：手冊 3.2、3.5 寫包裡有 `state.py`，「新功能的欄位放進自己的子模型 `PlayerState.<包>`」。可是 `PlayerState` 在核心 `state.py`，核心不准 import 包（3.4.1、邊界測試）。照字面做，第一個有狀態的新功能就會撞牆。三包都還沒有子模型（欄位都留在原地認領），`new_feature.py` 也不生 `state.py`，只在註解寫「Config 加欄位先過 PM」。
- **寫在哪**：手冊第十五節（3.2、3.5）；`docs/guide/核心與存檔.md`「核心、功能包…」的「新的一包」；`new_feature.py` 的 docstring。
- **建議的字**：
  > - **新包的欄位**（第 3 階以前）：子模型類別寫在核心 `tianxia/state.py`（類別名帶包名，例 `TavernPlayer`、`TavernSeason`）。欄位 `PlayerState.<包>`／`WorldState.<包>` 用 pydantic 預設值，加進 `QUIET_DEFAULTS`（空的不寫鍵，舊存檔讀得進來、存檔不多一個鍵）。`Config.<包>`（含 `enabled`）寫在 `models.py`。兩樣都是改核心：派工單寫明、PM 點頭，跑一次核心測試＋煙霧（約 1,500 條）。包的 `__init__` 用 `player_fields`／`carried` 認領。包裡的 `state.py` 等第 3 階再搬。要加表或改結構才升 `SCHEMA_VERSION`（現在第 7 版，先跟 PM 對號碼）。

### G8 新包的內容 json 怎麼載（PM 可改）
- **問題**：3.6 只寫「json 照舊放 `content/`、以包名開頭、`content.py` 照舊全部載入」。可是 `content.py` 是核心、不能 import 包，包的 `content` 宣告要到第 3 階才有人讀。新包加一份 json 要動哪幾處，沒寫。
- **寫在哪**：手冊第十五節（3.6）；`docs/guide/核心與存檔.md`「新的一包」。
- **建議的字**：
  > - **新包的內容檔**：放 `content/<包>.json`（或 `<包>_*.json`）。第 3 階以前由核心載：`models.Content` 加一個欄位、`content.py` 讀那個檔，算改核心，同新包的欄位（G7）先過 PM。內容驗證寫在包的 `check_content`，不寫進 `content.validate`。包的 `content` 宣告照填（第 3 階用）。舊的內容檔搬包時不改名（批次表）。

### G9 第 3 階之前新功能的畫面放哪（PM 可改）
- **問題**：手冊 3.7 說殼化是第 3 階。第 1 階把 `mall.js`、`mall.css` 切出來當示範，契約測試也已經守著「包登記的 web 檔 `index.html` 有載、js 在 `app.js` 前、css 在 `style.css` 後、js 在 `webharness.APP_FILES`」。可是給人看的規範沒寫「新畫面寫在 `web/<包>.js`、不要寫進 `app.js`」。`網頁.md` 第 3 行還寫「一支 `web/app.js`、一支 `web/style.css`」，`地圖與介面.md` 第 18 行寫「分三個檔」。
- **寫在哪**：`tianxia-dev/網頁.md`「動手之前」；`docs/guide/地圖與介面.md`「介面」第一條；手冊第十五節（3.7）。
- **建議的字**：
  > - **新功能的畫面**（第 3 階殼化以前）：寫在 `web/<包>.js`、`web/<包>.css`，不寫進 `app.js`／`style.css`。包的 `web` 宣告這兩個檔。手動在 `index.html` 加 `<script>`（`app.js` 之前）與 `<link>`（`style.css` 之後），`tests/kit/webharness.APP_FILES` 加那支 js，`tests/core/test_contract_features.py` 守這三處一致。頂層名字跟其他檔共用同一個全域，一律帶包名前綴（`tests/server/test_server.py` 守不重名）。殼的分頁框、行動列照舊在 `app.js`／`main.js`，殼叫包的 render 函式。網頁測試放 `tianxia/features/<包>/tests/test_<包>_web.py`。對比圖照舊先出。現在 `index.html` 依序載 `main.js`、`map.js`、`outing.js`、`mall.js`、`app.js`。

### G10 新包的三段式模型呼叫接在哪（PM 可改）
- **問題**：三段式的原則寫在 `CLAUDE.md` 與「模型與假人」導覽，範例都是 `Game`＋`server.py` 的寫法。包的 A、C 段放哪、B 段放哪，鎖外那條路要加進 `test_only_the_out_of_lock_steps_enter_the_model_queue` 的名單，包的 `routes.py` 能不能直接接，都沒寫。宴客的敬酒現在是 `server.feast_text` 叫 `Game.feast_*` 的委派。
- **寫在哪**：`docs/guide/模型與假人.md`「模型呼叫」；手冊第十五節（3.3）。
- **建議的字**：
  > - **功能包的三段式**：A 段（鎖內只讀開單）與 C 段（鎖內整個重驗再套用）寫在包的 `actions.py`，由 `Game` 的一行委派交給殼叫。B 段（鎖外叫模型）寫在包的 `rules.py`（或 `llm.py`），不碰狀態、不 import fastapi。殼的接線照 `server.prepare_dialogue`／`server.feast_text` 的寫法放在 `server.py`，名字加進 `tests/server/test_server.py::test_only_the_out_of_lock_steps_enter_the_model_queue` 的名單（改核心測試算例外，回報寫明）。包的 `routes.py` 只接不叫模型的 API。鎖內還要叫模型的一律 `ctx._quick_client()`。假人不寫字（`bots.py` 不按自由文字）。

### G11 `new_feature.py` 的用法與生完要做的事（PM 可改）
- **問題**：用法散在三處（`tianxia-dev` 第 13 行、核心與存檔導覽、腳本 docstring），而且 `tianxia-dev` 寫錯會生哪些檔。生完要接哪幾樣才算一包能上，沒有一張清單：`enabled`、`prefix`、`FEATURES` 的順序、換掉煙霧、`stage`、README、導覽。
- **寫在哪**：`tianxia-dev`「開工」第一條換掉；`docs/guide/核心與存檔.md`「新的一包」補。
- **建議的字**：
  > - **新功能一律生一包**：`python scripts/new_feature.py <包名> --title <中文名> --guide <導覽區塊>`（例 `tavern --title 酒肆 --guide 裝備與店面`）。只生這六樣：`tianxia/features/<包>/__init__.py`（`Feature` 子類別，`enabled` 先回 False）、`README.md`、`tests/test_<包>_smoke.py`、`tests/<包>_stage.py`、導覽最後一節的標題、`tianxia/core/registry.py` 的 `FEATURES` 一行（排最後；要排前面寫明理由，順序就是選單與分派的先後）。`rules.py`、`actions.py`、`bots.py`、`routes.py`、網頁檔用到才自己加（範本照 `features/feast/`〔有按鈕〕、`features/mall/`〔有 API 與畫面〕）。生完要做的：①`enabled` 接上 `Config.<包>.enabled`（G7）；②選項 id 一律 `<prefix>:`；③選項會被假人按的寫 `bot_pick`，永遠按得下去的寫 `bot_always`；④煙霧換成真實內容 `real_content("week7")` 走一次最常見的路，`@pytest.mark.smoke` 留著；⑤`<包>_stage.py` 擺出「有選項」的局面（契約測試靠它）；⑥README 三行寫好，設計稿寫「第 N 版」；⑦導覽那一節寫規則。跑 `scripts/test_for.py`（會挑到包的 `tests/`＋核心契約）。

### G12 合併閘門、平行數、QA 跑不跑測試，`CLAUDE.md` 跟手冊對齊（需企劃者，因為改的是 `CLAUDE.md`）
- **問題**：見矛盾 C4～C7。`CLAUDE.md` 第 70、72、73 行還是 `-n auto`、「整套約 1 分鐘」、「Joy 2026-10-26」那一版的閘門，沒有「那一包相關的 slow」。第 71 行把 QA 跟開發寫在一起，都跑 `test_for`。
- **寫在哪**：`CLAUDE.md`「指令」測試那幾條。
- **建議的字**（取代第 70 行後半與第 73 行）：
  > - 平行一律 `-n 4`（同一台同時最多兩份測試，不寫 `-n auto`）。不含 slow 的整套約 3～4 分鐘，整套含 slow 約 15～19 分鐘。
  > - **QA 不重跑開發跑過的測試**，只在實機驗畫面與手感（手冊 4.2）。
  > - **合併那一刻**（企劃者 2026-10-31：照舊）：批合進功能分支、功能分支合進 develop、main 合回 develop。只動 `web/`、文件、測試的，跑 `scripts/test_for.py --base origin/<要合進去的分支>`。動到 `tianxia/`、`content/`、`server.py` 的，再加不含 slow 的整套 `.venv/Scripts/python.exe -m pytest -q -n 4`，**加上那一包相關的 slow**（包的 README 列的那幾個檔）。develop 每天 03:30 跑一次整套含 slow。**上 main 之前一定跑整套含 slow**（`scripts/test_for.py --all`）。

### G13 資料庫結構改版與〈退版風險〉怎麼寫（PM 可改）
- **問題**：版本號寫錯了（`tianxia-flow` 第 129 行、`tianxia-dev` 第 203 行寫第 5 版，實際 `database.SCHEMA_VERSION = 7`）。「舊程式讀得進新存檔」散在 `tianxia-dev` 的兩條雷（FB-695）。部署說明的必要內容只寫了「資料庫改版、要備份、要在休季部署的都寫明」，沒有〈退版風險〉的格式。交接裡 main 那一條「心魔未破 retry 卡」就是靠 PM 記得才寫上去的。
- **寫在哪**：`tianxia-flow`「照舊的規矩」與「流程」第 6 步；`tianxia-dev`「規則改動的雷」第 203 行。
- **建議的字**：
  > - 資料庫結構現在是**第 7 版**（`tianxia/database.py` 的 `SCHEMA_VERSION`）。要升先跟 PM 對號碼；搬包不升（手冊 3.5）。
  > - **每一份要上 main 的說明都有〈退版風險〉一節**（PR 說明或 `docs/superpowers/feedback/<日期>-<名字>-給joy.md`），逐條寫：(1) 資料庫版本升不升，升了舊程式打不打得開；(2) 舊程式讀新存檔會不會讀不下或丟東西，一欄一欄寫（新的 `Literal` 值、新的子模型、季上的新章、world 那一列的新鍵）；(3) 季中能不能換（季曆換算；走到一半的一趟、還在等應戰的約戰、集結中的決戰）；(4) 要不要休季部署；(5) 備份指令與緊急開關。開發的回報與雲端的 PR 說明各寫自己那一批的。搬包的批照批次表「舊程式寫到一半、新程式接手」證明，寫「資料庫逐表一樣」。

### G14 「全部拆完」的路線（需企劃者）
- **問題**：企劃者問「整個現有的架構你都拆好了嗎」。手冊只有第 2 階「碰到才搬」（10/31 改成主動搬六包）和第 3 階「第 2 階搬了五、六包之後」做內容照包分、`app.js` 殼化。照方法名第一個字粗分（develop 5fccb11a），`Game` 還有 1,033 個方法、`engine.py` 17,650 行，五個以上方法的群有 43 個。批次表十二批碰到出陣、約戰、走一趟、探索、決戰（battle、showdown、siege、escort……）、酒肆、頭目戰與擂台；沒排的大群有 `admin_` 52 個方法 946 行、`seal_` 19／462、`parley_` 19／315、`raid_` 11、`road_` 11、`discuss_` 11、`spar_` 9、`smith_` 10（等鐵匠鋪）、`xingshi_` 8、`donate_`、`mingtie_` 各 6……。第十二批之後怎麼辦、「拆完」長什麼樣子、什麼時候開第 3 階，都沒寫。
- **寫在哪**：手冊第十五節（第十二節）；批次表最後加一節「第十二批之後」。
- **建議的字**（請企劃者三選一）：
  > - 甲：第十二批之後照改動頻率繼續主動搬（玉璽、論武 parley、截殺與設伏、路上、切磋、交友……），`admin_*` 跟著各包的 `admin_tools` 拆。「拆完」＝`engine.py` 只剩核心（`sync`、選項與分派的彙整、換季、清失效參照、管理者外殼），目標 < 3,000 行。之後開第 3 階。
  > - 乙：六包加第十二批做完就停止主動搬，其餘碰到才搬（批次表的證明照做）。第 3 階照手冊「五、六包之後」開。
  > - 丙：第十一批收接縫之後先開第 3 階（內容照包分、`app.js` 殼化），再決定剩下的怎麼搬。

### G15 PM 的派工模式（開發 → 唯讀審查 → 修 → QA）與 `same_behavior.py` 寫進技能（PM 可改）
- **問題**：第 0、1 階與搬包的每一批，PM 都用工作流程跑「開發 → 兩三位唯讀審查員（證明誠實度、照不照手冊、回歸與 slow）→ 修 → 實機 QA」。`tianxia-flow`「流程」只有六步，沒有審查這一步。`scripts/same_behavior.py` 只在手冊第十五節與批次表提到，技能與導覽沒有指過去，接手搬包的開發看不到用法。
- **寫在哪**：`tianxia-flow`「流程」第 2、3 步之間；`tianxia-dev`「開工」搬包那一條。
- **建議的字**：
  > - 2b. **唯讀審查**（2026-10-30 起 PM 的做法）：開發回報之後，PM 派兩三位唯讀審查員（自己重跑證明、照不照手冊與批次表、回歸與相關 slow）。有 blocker／should 就派一個修的，修完才派 QA。審查員不改檔、不推。
  > - （`tianxia-dev`）搬包的批用 `scripts/same_behavior.py` 證明行為一個字不變：`selftest --base` 先證明同一份跑兩次一樣、前半＋後半＝整段、改一個字抓得到；`compare --base --head` 比五種設定。每一批在 `PHASES` 後面加自己的情境。用法在腳本開頭的 docstring。

### G16 內容檔歸誰、內容 id 改名（PM 可改：企劃者 10/03 已定）
- **問題**：企劃者 2026-10-03 定「設計 session 不直接改 `content/*.json`，寫成文件裡對應 JSON 的表交開發轉檔；內容檔只有開發 session 與 Joy 在動」。這一條只在 PM 的記憶裡，手冊第六節的角色表沒寫。內容 id 上線後能不能改、要改怎麼辦，哪裡都沒寫。
- **寫在哪**：手冊第十五節（第六節的角色表）；`tianxia-dev`「內容改動的雷」第一條之前。
- **建議的字**：
  > - **內容檔歸誰**（企劃者 2026-10-03）：`content/*.json` 只有開發（含雲端開發）與 Joy 改。討論對話、設計 session 把內容寫成「欄位對應 JSON 的表」交開發轉檔。Joy 寫好的事件文字不改，非改不可先問企劃者。
  > - **內容 id 不改**：上線後武學、物品、地點、事件、商品、配方的 id 不改，要換名改 `name`。真的要拿掉某個 id，`_drop_stale_references`（或包的 `on_drop_stale`）要清得掉，〈退版風險〉寫明。搬包不改舊檔名；新包的檔以包名開頭（手冊 3.6）。

### G17 主 clone 的 checkout 過期、技能清單有兩份（PM 可改）
- **問題**：`C:\Ray\專案\天下大勢` 停在 main `4e03895b`（10/21），落後 1,162 筆，那裡的 `CLAUDE.md` 與 `tianxia-flow` 一個「開發規範手冊」都沒有。`ai遊戲` 停在 `68b4b8d7`，也沒有。Skill 清單裡同時有 `tianxia-flow` 與 `ai遊戲:tianxia-flow`，後者是舊版（「測試規矩 Joy 2026-10-26 改」）。`tianxia-flow` 第 91 行只寫了「不要切主 clone 的分支」，沒寫要保持更新。
- **寫在哪**：`tianxia-flow`「PM 平行派工」；交接第七節。
- **建議的字**：
  > - **主 clone 的 checkout 要跟上**：在 `C:\Ray\專案\天下大勢`、`C:\Ray\專案\ai遊戲` 開的新對話讀的是那裡 checkout 的 `CLAUDE.md` 與技能。PM 每次 main 往前（合 main、Joy 直推之後），在 checkout 乾淨時 `git -C <clone> pull --ff-only`，不切分支。Skill 清單裡 `ai遊戲:tianxia-*` 是那一份 clone 的版本，派工單一律寫「讀 develop 上的 `.claude/skills/<技能>/SKILL.md`（Read 工作樹裡的檔）」。

### G18 回饋單號：雲端與內測（PM 可改）
- **問題**：`tianxia-flow` 第 68 行有號段（雲端 8000～8999），可是 `試玩回饋.md` 一張 8000 號都沒有。雲端用自己的自檢編號（`208b667d`「U-04、06…」、`22a24ee5`「S-07」），沒進回饋單；內測的回饋從哪裡起編也沒寫。
- **寫在哪**：`tianxia-flow`「回饋單號段」。
- **建議的字**：
  > - 雲端的自檢清單（U-、S- 這種）留在它自己的文件。驗完還開著、要別人接手的，開進 `試玩回饋.md`，編號 8000～8999，來源寫「雲端」。內測的回饋照試玩回饋從 1 起的那一串，來源寫「內測」。

### G19 週末、14 天季、三選一「整套拿掉」之前怎麼對待（PM 可改：企劃者 10/31 已定）
- **問題**：決定只寫在交接第三節「（還沒問、PM 記著）」，那一條本身也還停在「要不要」。`CLAUDE.md` 第 44、69、77 行、`tianxia-qa` 的設定說明、`引擎驗收.md` 範本、`same_behavior.py` 的五種設定都還把它們當現役。新寫的測試與功能要不要照顧它們，沒說。
- **寫在哪**：手冊第十五節；`tianxia-dev`「開工」；`tianxia-qa`「開伺服器與登入」的設定那一條。
- **建議的字**：
  > - **企劃者 2026-10-31**：現役只有 week7 與 season21。`weekend` 設定、不帶設定的 14 天季、探索三選一（`explore_modes.py`、`gather_llm.py`）整套拿掉，排在搬完六包之後（一批，PM 派）。在那之前：新功能、新測試只照顧 week7、season21，測試內容照用，不為 weekend 與不帶設定另寫分支或測試。三選一只修 bug、不搬（批次表第 9 批不做）。`same_behavior.py` 與「關著不變」的對照照舊比四種設定加測試內容，直到拿掉那一批為止。

### G20 誰能改 `CLAUDE.md`（需企劃者）
- **問題**：手冊第十節只寫「技能檔只有 PM 改、導覽由做那一批的開發改」。`CLAUDE.md` 誰改沒寫清楚：雲端 `febfcf21` 改了「名字原創」那一行（Joy 交代的）；`tianxia-dev`「回報 PM」又要開發寫「這一路改了 `CLAUDE.md` 的哪幾條」。
- **寫在哪**：手冊第十五節（第十節）；`CLAUDE.md`「功能區塊」第二條之後加一行。
- **建議的字**：
  > - `CLAUDE.md`：PM 提、企劃者點頭才改。企劃者或 Joy 直接交代的一行（例 2026-10-31 禁用名單開關，雲端 `febfcf21`），改的人在 PR 或 commit 寫出處，PM 合的時候核對、跟企劃者說。開發與 QA 不改 `CLAUDE.md`，要改的寫在回報。導覽由做那一批的開發改，技能只有 PM 改。

### G21 「待 joy 潤」怎麼追（PM 可改）
- **問題**：規矩只有「新寫的字標『待 joy 潤』」。標在哪（json 不能寫註解）、誰收、潤過怎麼拿掉，都沒寫。交接第四節的清單只收主機側的，雲端新寫的字沒有人收。
- **寫在哪**：`tianxia-flow`「照舊的規矩」。
- **建議的字**：
  > - 新寫的字在程式旁註解 `# 待 joy 潤`（js 寫 `// 待 joy 潤`；json 寫不了註解，就列在回報或 PR 說明）。開發與雲端在回報或 PR 列出這一批新加的，PM 收進交接第四節「待 joy 潤」。潤過就拿掉標記、從清單劃掉。

---

## 二、互相矛盾的

| # | 一邊 | 另一邊 | 怎麼收 |
|---|---|---|---|
| C1 | 手冊第五節「**沒有人直接推 `develop`、`main`**……進 `develop` 只有 PM 合（QA 過、三級綠）」；第六節雲端「不推 `develop`、`main`」 | 交接第七節「雲端常常直接推上 develop（不經 QA、只跑不含 slow），PM 事後驗」；git：PR #100～#110（`claude/project-thread-*`）由 `sasojoy` 合進 develop，`68b4b8d7` 雲端直推 main | 企劃者照 G2 甲／乙定，寫回手冊第十五節、`tianxia-flow`、交接第七節 |
| C2 | 手冊第五節「GitHub 分支保護：`develop`、`main` 強制走 PR」；`tianxia-flow` 第 23 行「分支保護強制走 PR：等 Joy」 | 企劃者 10/31 (1)：不開分支保護，照規矩口頭遵守 | 照 G5 寫回；`tianxia-flow` 第 23 行刪掉那半句 |
| C3 | 手冊第五節「進 `main` 只有上線步驟（`release/<日期>`）」；`tianxia-flow`「上 main 用上線分支」 | PR #111：develop 直接合進 main（`sasojoy`，10/31 17:09）；企劃者 10/31「上 main 一律從 develop 合、先跑整套含 slow」 | 照 G3 寫：從 develop 合，要拿掉某一樣才開 release；整套含 slow 的證據寫進 PR |
| C4 | 手冊 4.2「合進功能分支｜那一包＋核心契約＋每包煙霧（三級）」、第十一節 3 | 企劃者 10/31 (3)：照舊，不含 slow 的整套＋那一包相關的 slow；`tianxia-flow` 第 37、52 行與 `量表與教訓.md` 第 8 行還標「等 Joy」 | 照 G5 寫回手冊；`tianxia-flow` 第 37、52 行、`量表與教訓.md` 第 8 行、批次表第 55 行把「等 Joy／Joy 回之前」改成「企劃者 10/31 定：照舊」 |
| C5 | `CLAUDE.md` 第 73 行合併閘門：只有不含 slow 的整套、`-n auto`、標「Joy 2026-10-26」，只寫「動到 `tianxia/`、`content/`」 | 批次表第 55 行、`features/sortie/README.md`：「加上那一包相關的 slow」；`tianxia-flow` 第 55 行多寫了 `server.py` | 照 G12 改 `CLAUDE.md` |
| C6 | `-n 4`：手冊 4.5「派工單寫明 `-n 4`，不寫 `-n auto`」、`tianxia-flow` 第 42 行、`量表與教訓.md` 第 8 行 | `-n auto`：`CLAUDE.md` 第 70、72、73 行；`tianxia-flow` 第 55、57、115 行；`tianxia-flow` 第 102 行「`-n 6`～`-n 8`」 | `CLAUDE.md` 照 G12；`tianxia-flow` 的 55、57、102、115 行改 `-n 4`（第 102 行整條刪） |
| C7 | 手冊 4.2「QA 驗收｜**不重跑測試**」；`tianxia-qa` 第 14 行 | `CLAUDE.md` 第 71 行「開發中與 QA……`test_for`」；`tianxia-flow` 第 47～49 行「開發中、QA 驗收：只跑跟這一次改動直接相關的測試……QA 只跑它驗的那幾樣的測試檔」 | `tianxia-flow` 第 47～49 行改成只講開發，QA 那一句換成「QA 不重跑，派工單點名的才跑」；`CLAUDE.md` 照 G12 |
| C8 | 手冊第十節「技能檔只有 PM 改」；`tianxia-qa` 第 14 行「不改技能檔」 | `tianxia-qa` 第 228 行「qa/ 分支只 commit 試玩回饋（**順手更新這個技能時，同一個 commit 帶上**）」 | 第 228 行刪掉括號 |
| C9 | 手冊 3.5、交接第七節「資料庫第 7 版」；`tianxia/database.py:301` `SCHEMA_VERSION = 7` | `tianxia-flow` 第 129 行「目前第 5 版，下一版是第 6 版」；`tianxia-dev` 第 203 行「資料庫結構（第 5 版）不改」 | 照 G13 改成第 7 版 |
| C10 | 手冊 3.4.2 與 `new_feature.py` docstring：只生 `__init__`、README、煙霧、stage、導覽標題、登記 | `tianxia-dev` 第 13 行「（`tianxia/features/<包>/`：`__init__.py`…`rules.py`、`actions.py`、`state.py`、`content/`、`routes.py`、`web/`、`tests/`、`bots.py`、`README.md`；用不到的不生）」 | 照 G11 換掉 `tianxia-dev` 第 13 行 |
| C11 | `CLAUDE.md` 第 63 行「新增『永遠按得下去』的選項要一併改 `bot.py::pick()`」 | 手冊 3.3 `bot_pick`；`核心與存檔.md`「`bot_pick`＋`bot_always`……取代『新增永遠按得下去的選項要改 `bot.py::pick()`』」 | `CLAUDE.md` 那一行改成「包裡的選項在 `bot_always` 宣告；還在 `engine.py` 的照舊改 `bot.py::pick()`」（需企劃者） |
| C12 | `CLAUDE.md` 第 75 行「檔名全 `tests/` 不能重複……新測試放它測的模組那一塊」 | 手冊 4.6「功能包的測試在 `tianxia/features/<包>/tests/`……檔名全 repo 不能重複」 | `CLAUDE.md` 第 75 行補「功能包的測試在 `tianxia/features/<包>/tests/`；檔名全 repo 不能重複」（需企劃者） |
| C13 | `docs/guide/地圖與介面.md` 第 18 行「分三個檔……`index.html` 照 main、map、app 的順序載入」；`tianxia-dev/網頁.md` 第 3 行「一支 `web/app.js`、一支 `web/style.css`」 | `web/index.html`：`main.js`、`map.js`、`outing.js`、`mall.js`、`app.js`，css 有 `style.css`、`mall.css`、`zhuan.css`；契約測試守包的 web 檔 | 照 G9 改兩處 |
| C14 | `CLAUDE.md` 第 15 行「`C:\Ray\專案\天下大勢` 是主要的那份」 | `tianxia-flow` 第 89 行「新對話常常開在主 clone（`C:\Ray\專案\ai遊戲`）」 | `tianxia-flow` 第 89 行改成「主 clone（`C:\Ray\專案\天下大勢`）或 `ai遊戲`」，再接 G17 |
| C15 | 手冊第六節企劃者「需要 Joy 決定的由他轉」；第十一節「企劃者轉」；交接第七節「寄給 Joy 的東西一律經企劃者同意、由企劃者轉」 | 企劃者 10/31「不用轉~問我就好」：要問 Joy 的直接問企劃者（批次表第四節已寫） | 手冊第十五節記一條：問題直接問企劃者、照他的答案做；部署說明照舊經企劃者給 Joy |
| C16 | 手冊 3.4.3「舊功能碰到才搬……順手把酒肆搬進包裡」；`tianxia-dev` 第 14 行「也可以順手搬」 | 手冊第十五節「3.9 不是碰到才搬，PM 主動……一批搬一包」；批次表「一次只做一批」，每批要 `same_behavior.py`＋實機證明 | 照 G6 定（需企劃者） |
| C17 | 手冊第五節與 11.5、`tianxia-flow` 第 17、27、124 行「要內測時寫部署說明給 Joy」 | 企劃者 10/31 (5)：內測在這台主機跑 | 照 G4、G5 |
| C18 | `tianxia-map-remake` 說它管「輿圖」的工作：「分支：領地爭奪第一、二批在 `feature/territory-conquest`（不在 develop）；新工作從它開」、第 3 批動 `mapview.py`／`mapart.py` | 交接第二節之一：輿圖表現第二版照 `docs/superpowers/specs/2026-10-30-輿圖表現-design.md`（`feature/map-view`），取代第一版 S1＋W1～W5；S1 把 terrain 整串拿掉、`mapart.py` 回到 develop 的樣子 | 技能開頭加一段：「2026-10-30 起輿圖的畫面照 `2026-10-30-輿圖表現-design.md`（`feature/map-view`）；這份只留翻地與爭搶的規則（『不准再談的』），『分批與檔案』與分支那一條作廢」；`description` 拿掉「天下圖」「區圖」兩個字，免得做 W3、W4 的人載到 |
| C19 | `tianxia-flow` 第 103 行「派工單裡每一行 pytest 都寫 `-m "slow or not slow"`」 | 手冊 4.3「slow 不自動跟，`--slow` 才加」；4.2「開發中：那一包自己的測試（一、二級）」 | 改成「直接點名測試檔的 pytest 那一行寫 `-m "slow or not slow"`；`test_for` 那一行不帶，要 slow 加 `--slow`」 |
| C20 | 手冊第十節「導覽由做那一批的開發改……`CLAUDE.md` 只留……」（開發不改 `CLAUDE.md`） | `tianxia-dev`「回報 PM」最後一條：「這一路改了 `CLAUDE.md` 或 `docs/guide/` 的哪幾條」 | 改成「改了 `docs/guide/` 的哪幾條；要改 `CLAUDE.md` 的寫在這裡」（配 G20） |
| C21 | 手冊 3.3 表「`bot_pick`……也在這裡宣告哪些選項是永遠按得下去的」 | 實作與導覽：另一個掛鉤 `bot_always`（殼啟動時叫，不看開關） | 第十五節 3.3 那一條補一句「永遠按得下去的是另一個掛鉤 `bot_always`」 |

---

## 三、過期的

**`CLAUDE.md`**（都要企劃者點頭）
- 第 14 行「功能分支（現在是 `feature/formal-season`，正式季整合）」。現在是一包一條（`feature/sortie`、`feature/map-view`、`feature/smithing-flow`……），現況看交接第一節。
- 第 15 行「`ai遊戲`……地圖擴充開發在它的 `.worktrees/` 裡做」：地圖擴充早就收了。
- 第 70 行「這台 16 核整套約 1 分鐘，單一行程約 3 分 40 秒」：手冊第一節量的是不含 slow 3～4 分鐘、含 slow 14.9～19 分鐘（`-n 4`）。
- 第 73 行標「Joy 2026-10-26：只有上 main 跑整套含 slow」：企劃者 10/31 已經重定（見 G12）。
- 功能區塊表：`sortie` 還列成「行動與地盤」的模組（現在是 `tianxia/features/sortie/`，`tianxia/sortie.py` 只是別名）；`mall`、`rename` 已經在 `features/mall/`；宴客（`features/feast/`）不在表上。建議加一欄或一句「已搬成功能包：商城 `features/mall`、宴客 `features/feast`、出陣 `features/sortie`」。
- 第 44 行（探索三選一開著時的入口）、第 69 行（週末設定）、第 77 行（`classic_rules` 與三選一）：企劃者 10/31 定整套拿掉，等那一批落地再刪，在那之前加註「整套拿掉，排在搬完六包之後」。

**手冊 `2026-10-30-開發模式-design.md`**（PM 在第十五節補註）
- 4.4「跑的時間等企劃者定（第十四節）」「由企劃者按一次（或 PM 徵得同意後註冊）」：03:30 已定，`TianxiaNightly` 已註冊。
- 第五節「強制走 PR……【Fable 定，要 Joy 同意（第十一節）】」、「內測部署 develop：第一次要內測時 PM 寫部署說明給 Joy」。
- 第六節企劃者那一列「需要 Joy 決定的由他轉」。
- 第十一節整節（見 G5）。
- 第十二節第 0 階那一列「合併閘門那一條標『等 Joy』」。
- 3.4.3「舊功能碰到才搬」與 3.9「之後照改動頻率」已經被第十五節取代，建議原文加刪除線或「→ 見第十五節」。

**技能**（PM 可改）
- `tianxia-flow`：description「測試規矩 Joy 2026-10-26 改」；第 10 行「標『等 Joy』的那幾條，Joy 回之前照舊」；第 23 行「分支保護……等 Joy」；第 37 行「等 Joy 回之前」；第 52 行「手冊提議……等 Joy；回之前照下面這一段」；第 17、27、124 行內測寫部署說明給 Joy；第 102 行 `-n 6`～`-n 8`；第 129 行第 5 版；第 89 行主 clone 寫成 `ai遊戲`；第 113 行「不帶設定、weekend、season21、week7 各載一次」（整套拿掉之後只剩兩種）。
- `tianxia-dev`：第 21 行「多半是 `origin/feature/formal-season`」、第 27 行 `origin/feature/formal-season`；第 13 行 `new_feature.py` 會生的東西；第 203 行第 5 版；`網頁.md` 第 3 行「一支 app.js、一支 style.css」。
- `tianxia-qa`：第 224 行標題範本「### 正式季第 N 批……QA」；第 228 行「順手更新這個技能」；第 58 行（「開伺服器與登入」的設定）還把 `weekend` 與空字串（14 天的季）當現役。
- `tianxia-map-remake`：整份停在 10/20～10/22 的輿圖第三版（見 C18）。

**導覽**（PM 可改）
- `量表與教訓.md` 第 8 行「Joy 回覆手冊十一之 3 以前，合併閘門照技能檔舊的寫法」。
- `地圖與介面.md` 第 18 行「分三個檔」。

**批次表 `2026-10-31-主動搬六包-批次.md`**（PM 可改）
- 第 26 行「戰記……這一輪不搬：Joy 還有三件沒定」：企劃者 10/31 答了「近期會叫雲端做」（第 15 行已經這樣寫）。
- 第 55 行「合併閘門（Joy 回第十一節第 3 題之前）」：改成「企劃者 10/31 定：照舊」。
- 第 12 行第 2 批「開工」：工作流程 H 跑完要更新。

**交接 `2026-10-30-主機側交接.md`**（PM 可改）
- 第一節表：`main` `a1b755b4`、`develop` `22e7ad0d`。現在 origin/main 是 `41ccbb9e`（PR #111，`sasojoy` 10/31 17:09 把 develop `5fccb11a` 合進 main），develop 是 `5fccb11a`。
- 第三節「要 Joy 同意的五件」：10/31 答了。
- 第三節第 1 條「main `a1b755b4` 這一次上線同不同意」：企劃者 10/31 認了 `68b4b8d7`，之後 main 又被 PR #111 推到 `41ccbb9e`，這一次的整套含 slow 與部署說明要補記。
- 第三節「（還沒問、PM 記著）weekend……要不要整套拿掉」：10/31 答了，整套拿掉，排在搬完六包之後。
- 第三節第 7 條「『主機側 FB 從 9000 起編』要不要寫進 `tianxia-flow`」：已經寫進去了（第 68 行）。
- 第二節之 2 鐵匠鋪「雲端 A、C、E 三批由企劃者轉」：10/31 改成網頁三批 A、C、E 由主機側做。
- 第七節「寄給 Joy 的東西一律經企劃者同意、由企劃者轉」：問題改成直接問企劃者（C15）。
- 第七節「雲端常常直接推上 develop……PM 事後驗」：等 G2 定了改成定案的說法。

**PM 的記憶**（不在 repo 裡，順帶）：`joy-deploys-test-build.md`（測試版由 Joy 部署）跟 10/31「內測在這台跑」對不上；`pm-parallel-sessions.md` 的「文件只 commit 到本地」早就被「交接推上 develop」取代。

---

## 四、順帶看到的事實（給 PM 判斷）

- origin/main `41ccbb9e`＝develop `5fccb11a`＋PR #111 的合併。線上下一次部署會換上第 0、1 階與出陣包第 1 批。看不出這一次上 main 之前誰跑了整套含 slow。`.local/nightly/latest.txt` 還是 10/31 10:03 `fdae7c81` 那一次（11524 passed），不是 `5fccb11a`。
- 這台沒有 `gh`，手冊第五節寫的 `gh pr merge` 在主機側做不到。
- 雲端這兩天在 develop 上的實質改動（例：`04cbff00` 正式設定打開推送與模型佇列、`febfcf21` 禁用名單開關）都沒經過主機側 QA，只有每日整套會碰到。
