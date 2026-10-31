---
name: tianxia-flow
description: 《天下大勢》的分支、測試與合併規矩（企劃者 2026-10-18 定；開發規範手冊 2026-10-30；企劃者 2026-10-31 答了合併閘門、上 main、雲端 PR、內測）。開工、派工、開發、QA 驗收、合併、推上 GitHub、部署之前都先看這一份：功能在哪一條分支做、合到哪裡、什麼時候跑哪一種整套測試、QA 要跑哪些測試。
---

# 天下大勢：分支、測試與合併

企劃者 2026-10-18 定的規矩（「這些正式賽季的項目開一個新的分支來做。未來就要有一個 develop 分支，甚至可能還會再部署 develop 做內測之後才回 master」「除非再做 branch merge 的這種時間點，不然 QA 都不要跑全部的測試，只跑最小量需求節省 token」）。跟 CLAUDE.md 或舊計畫對不上時，以這一份為準。

**2026-10-30 起照〈開發規範手冊〉**（`docs/superpowers/specs/2026-10-30-開發模式-design.md`；企劃者：「寫成開發規範手冊，讓其他人遵守，然後發給 PM 讓 PM 派工開始調整」）：三層「核心／功能包／介面殼」、一個功能一包、測試分級與每日整套。這一份是手冊的執行版；兩邊對不上時照手冊（尤其是手冊最後一節的落地補註），PM 再把這一份改齊。手冊第十一節「要 Joy 同意的」五件企劃者 2026-10-31 直接答了（「不用轉~問我就好」），這一份已照答案改。全部拆完的路線在 `docs/superpowers/plans/2026-10-31-全部拆包-總表.md`（企劃者 10/31「趕快拆」）。**技能檔只有 PM 改**（手冊第十節）：子代理學到的寫在回報的「學到的」一節，PM 收進來。

## 分支

| 分支 | 用途 | 誰合進來、什麼時候 |
|---|---|---|
| `main` | 線上正式版（tianxiadashi.com 跑的那一份） | 只有企劃者說可以上線，才從 `develop` 合進來、合之前跑整套含 slow（企劃者 2026-10-31「之後上 main 一律從 develop 合」）。Joy 的維運與緊急修正照舊可以直接推 `main`、推完說一聲 |
| `develop` | 整合與內測 | 主機側：功能分支做完（或企劃者說要內測的一段）由 PM 在本機合進來。雲端：PR 由 Joy 在 GitHub 合進來（企劃者 10/31）。內測的 `develop` 在這台主機另開一份跑（下面「內測」） |
| 功能分支 `feature/<名字>` | 一包一條（`feature/<包名>`），從 `develop` 開 | 分批開發的每一批，審查與 QA 過了由 PM 合進來 |
| 批的工作樹分支 | 開發 session 的工作樹（`dev/<名字>`）、驗收結果（`qa/<名字>`），從功能分支開 | 開發、QA 自己提交、推自己的分支；不直接推 `main`、`develop` |
| 雲端的分支 | 雲端 session、Joy 的 Claude（`claude/<名字>`），從 `develop` 開 | 開 PR 到 `develop`，Joy 在 GitHub 合 |

- 現在有哪幾條功能分支、各自推到哪，看 `docs/superpowers/handoff/` 最新那一份的第一節（這裡不列，免得過期）。
- **功能分支照功能包開**（手冊第五節）：`feature/<包名>`；一個包同一時間只有一條功能分支，兩條線不碰同一包。跨包的功能開一條線、在線上一次改兩包。還沒搬成包的功能用 `Game` 方法前綴當名字（`feature/tavern`、`feature/sortie`），撞線照方法前綴群看。**現有的分支名不改**（`feature/formal-season`、`feature/map-view`、`feature/smithing-flow`、`feature/core-hooks`）。
- **並行拆包**（全部拆包總表 5.0，企劃者 10/31「趕快拆」）：不同包、彼此不等（總表「等什麼」欄裡沒有對方）、都不是核心批的，最多三～四條同時跑（看機器負載）；核心批（總表 5.2 第 3 條列的）單獨跑。同時跑的測試最多兩份、各 `-n 4`，合併閘門排在另一條沒在跑測試的時候。共用的登記檔（`services.py`、`FEATURES`、邊界測試的名單、`same_behavior.py` 的 `PHASES`、`conftest`、`docs/guide`）每條線把自己加的集中成一段、前面一行 `# <包>`；契約測試 `_dirty` 一律 cherry-pick 第 2 批那一筆。先做完的先合；後合的先把 develop 合進來、重跑 Task 1 的核心測試與那一包的測試、用新的 develop 當 base 重比前後對照，才合。同一包相鄰、合計約 900 行內的批併成一批；工作流程跑完就合、合完就派下一批。
- **誰合進 `develop`、`main`**（企劃者 2026-10-30「只要符合開發規範，不管是本機還是雲端都沒差」；2026-10-31 照現況定）：
  - **主機側的子代理**推 `dev/`、`qa/` 分支，PM 在本機 `git merge --no-ff` 合進功能分支、再合進 `develop`，推上去（不經 PR；這台沒有 `gh`）。
  - **雲端 session 與 Joy 的 Claude**（規矩在 `CLAUDE.md`「工作目錄與分支」）：在自己的分支（`claude/<名字>`）做，開 PR 到 `develop`，**由 Joy 在 GitHub 合**。PR 說明寫：改了哪一包（或 `Game` 哪一群方法）、跑了哪些測試幾條過、〈退版風險〉（下面「照舊的規矩」）、這一批新寫「待 joy 潤」的字。批次表「搬包中」的那幾包不改；已經搬進 `tianxia/features/<包>/` 的改包裡的檔，`Game` 上的一行委派不加邏輯；新功能用 `scripts/new_feature.py`；回饋單號用 8000～8999。主機側 PM 不先 QA，第二天早上照每日整套（`latest.txt` 的新紅與 develop 新進的提交）事後驗，紅了開單交回那一線，新紅三天沒修 PM revert 那一筆合併。
  - **上 `main`** 一律從 `develop` 合、合之前跑整套含 slow（下面「上 main」）。**Joy 的維運與緊急修正**照舊可以直推 `main`、推完跟企劃者說一聲（哪一筆、改了哪個方法）；PM 下一次合併先把 `main` 合進 `develop`，改到已經搬走的方法就照抄進包（搬包中的那一批重跑前後對照）。
  - `develop`、`main` **不開** GitHub 分支保護，照規矩口頭遵守（企劃者 10/31，手冊第十一節第 1 題）。
- 流向只有一條：批的工作樹分支 → 功能分支 → `develop` →（內測）→ `main`。**不要從功能分支或工作樹直接合 `main`。**
- `main` 有新東西（Joy 推的）時，下一次合併的人先把 `main` 合進 `develop`、再把 `develop` 合進功能分支（`git merge --no-ff`，不 rebase 已經推上去的分支）。衝突照「程式為準」解，解不了的問 PM。
- 每次推上去都確認推到了：`git merge-base --is-ancestor HEAD origin/<分支>`（別的 session 也會動同一份 clone）。
- 線上伺服器照舊跑 `main`（Joy 部署）。**內測 `develop` 在這台主機跑**（企劃者 2026-10-31，手冊第十一節第 5 題）：另一個資料庫、另一個埠，不碰線上那一份；先開一次 21 天的季（`season21`）試玩。程式只從 `origin/develop` 更新、換到每日整套綠的那一筆。對外網址、埠、叫不叫模型**待定**（企劃者還沒定）。做法在 `docs/superpowers/feedback/beta-主機端操作.md`「內測 develop」；開季、收季、換程式都記進交接第一節。

## 測試：平常只跑最小量

**手冊 4.2 的表**（企劃者 2026-10-30：「小功能平常只跑自己那一塊的測試」「整套集中在某個時間點跑」「偶爾晚一點才知道別處壞了，可以接受」）：

| 時刻 | 跑什麼 | 誰跑 |
|---|---|---|
| 開發中 | 那一包自己的測試（單元、功能包兩級）；還沒搬成包的照 `scripts/test_for.py` 挑的 | 開發自己 |
| QA 驗收 | **不重跑開發跑過的測試**，只在實機上驗畫面與手感；只能靠引擎驗的照 `tianxia-qa/引擎驗收.md` | QA |
| 合進功能分支 | 企劃者 2026-10-31 定照舊：動到 `tianxia/`、`content/`、`server.py` 跑不含 slow 的整套＋那一包相關的 slow；只動 `web/`、文件、測試跑 `test_for` 挑的（下面「合併時跑哪一種」）。手冊 4.2 原本提的「只跑三級」作廢 | 合併的人（PM） |
| 合進 develop | 同上；內容跟測過的一樣（`git diff --quiet`）就不再跑 | 合併的人（PM） |
| 每天一次 | 整套含 slow（`scripts/nightly.ps1`，每天 03:30——企劃者 10/30「03:30，PM 註冊」；結果在 `.local/nightly/latest.txt`，有新紅、舊紅、轉綠三段；紅了開 FB 交回那一線，新紅三天沒修 PM revert 那一線的合併；develop 上的紅不擋開工，只擋上 main） | 排程（手冊 4.4） |
| 上 main 前 | 整套含 slow | 合進 main 的人 |

- pytest 一律 `-n 4`（同一台同時最多兩份測試；不寫 `-n auto`）。
- **`scripts/test_for.py` 照手冊 4.3 挑**（第 0 階 2026-10-31 合進 develop；手冊最後一節寫了落地時跟原文不同的地方）：
  - 照功能群挑，「import 了 engine」不再算相關：`engine.py` 看改到 Game 的哪個方法（改酒肆的方法 43 條）；核心改了（`models.py`、`state.py`、核心模組、`engine.py` 的共用方法與核心服務）跑核心測試＋`-m smoke`（約 1,500 條、約一分鐘；欄位名帶功能前綴的再加那一群）；`tianxia/features/<包>/` 跑那一包的 `tests/`＋核心契約。
  - **slow 不自動跟，`--slow` 才加**；改到的測試檔本身照舊連 slow。開跑前會列出「整個檔標 slow、這一次不跑」的檔：那些正是你這一包的，加 `--slow`。
  - 預設 `-n 4`，`--` 之後給的 `-n X` 照給的；`--list` 每一段寫為什麼挑，`--count` 數條數。
- **開發中**：只跑跟這一次改動直接相關的測試，**不跑整套**。（**QA 不重跑開發跑過的測試**，只在實機驗畫面與手感；派工單點名的才跑：手冊 4.2、`tianxia-qa`。）
  - 在批的工作樹裡：`.venv/Scripts/python.exe scripts/test_for.py --base origin/feature/<名字>`（只跟功能分支比；不給 `--base` 跟 `origin/develop` 比；base 沒 fetch 過、找不到分岔點會停下、結束碼 2，第一行印要下的 fetch）。也可以設環境變數 `TIANXIA_TEST_BASE`，或直接給檔名（`scripts/test_for.py tianxia/fusion.py`）、直接跑 `pytest tests/test_x.py -m "slow or not slow"`。
  - QA 不重跑；派工單點名要跑的那幾個檔才跑，其餘靠實機（瀏覽器）驗；不要為了「保險」跑整套。純搬、`web/` 沒動的批，QA 改成兩台真伺服器逐位元組比（總表 5.0，`tianxia-qa`）。
  - 修回饋單的測試寫進那個模組的測試檔，不開 `test_fb…` 新檔（2026-10-27 測試整理 1b 併掉了 53 個）；派工單寫「測試寫進 `tests/test_<模組>.py`」。
  - 改到 `tests/conftest.py` 的批：`test_for` 照改到的 fixture、函式挑用到它的測試檔；autouse 的、最外層的、或用到它的超過 50 個檔就跑煙霧。改 `tests/fixtures/`、`pyproject.toml` 時只跑那幾個改到的測試檔與直接相關的，整套留到合併那一刻。
- **合併時跑哪一種**（企劃者 2026-10-31 定「照舊」，手冊第十一節第 3 題；手冊原本提的「合併只跑三級」作廢。Joy 2026-10-26「只有上 main 跑整套 slow」、10-27「改UI也需要跑那麼多那麼久是不是有什麼問題？」之後 PM 收的這一套照用，另加那一包相關的 slow）：
  - **批合進功能分支、功能分支合進 `develop`、`main` 合回 `develop`／功能分支**：
    - 只動 `web/`、文件、測試：只跑 `scripts/test_for.py --base origin/<要合進去的分支>` 挑的相關測試，**不跑整套**。
    - 動到 `tianxia/`、`content/`、`server.py`：相關測試＋**不含 slow 的整套** `.venv/Scripts/python.exe -m pytest -q -n 4`（`pyproject.toml` 預設就擋掉 slow；約 3～4 分鐘）＋**那一包相關的 slow**（包的 README 列的那幾個檔、批次表第二節：例如出陣的 `test_bot_policy_conquest`、`test_conquest_flip`、`test_core_loop_web`、`test_econ_gather_sortie`）。
    - 整套含 slow 每天 03:30 由排程跑一次（`scripts/nightly.ps1`，上面那張表）。
  - **`develop` 合進 `main`（上線）之前一定跑整套含 slow**：`.venv/Scripts/python.exe -m pytest -q -n 4 -m "slow or not slow"`（或 `scripts/test_for.py --all`；不寫 `-m ""`；約 15～19 分鐘）。
  - 都由做合併的人跑，`TIANXIA_DB` 設到 repo 外的暫存檔。綠了才推；紅了把失敗的那幾條交回開發，修好之後再跑那幾條就好，推之前再跑一次同一種。
- 不要為了預先判斷平衡跑模擬或量表（企劃者 2026-10-14「給玩家實際體驗回饋最準」）；計畫本身寫了要量的照量。
- 開發、QA 自己不再開多代理工作流程（Workflow），也不一項一個子代理（PM 派出來的那一個子代理就是開發或 QA 本人）。

## 一件事一個新的對話（企劃者 2026-10-19）

企劃者 2026-10-19「現在這些老 session 都不要當主要驗證或開發，要多利用新派 session 或者 agent 的方式精準化」。量到的原因：連跑好幾天的開發、QA 對話每一則長到約 95 萬 token，每回一句話都把整串重讀一遍，重讀佔了花費的八成。

- **一批開發、一次驗收，各開一個新的對話或子代理**（PM 用 Agent 工具派，或開新的 session）；做完回報就收，不接下一件。修正一輪也是一件：修的人與驗的人都重新開。
- **派工單寫明**（手冊第七節）：包名與設計稿版本（「照 `<設計稿>` 第 N 版」，開工第一步核對版本，變了就停下來回報）、要讀哪幾塊導覽（`CLAUDE.md` 的區塊表，`docs/guide/`；只讀那幾塊，不整批讀、不整份讀設計文件，用 `grep -n '^#'` 看大綱）、分支（從哪開、推到哪）、FB 號段、埠與 `<名字>.localhost`、scratchpad 子資料夾、跑哪些測試（那一包；`-n 4`）、「做完就停、不要接著做」、**「每做完一個 Task 就推一次」**、「學到的寫在回報裡，不改技能檔」。
- **回饋單號段**（企劃者 2026-10-31 照這個）：試玩回饋從 1 起（照舊）；主機側 PM 線從 9000 起；雲端 8000～8999；PM 派工時每個 QA 給 10 個一段、不重疊。號段與埠記在交接第六節。PM 線的埠 8150～8199，用到底之後回收已經收掉的；雲端不開本機伺服器。
  - 雲端的自檢清單（U-、S- 這種）留在它自己的文件；驗完還開著、要別人接手的，開進 `試玩回饋.md`，編號 8000～8999，來源寫「雲端」。
  - 內測（這台主機跑的 `develop`）的回饋照試玩回饋那一串接著編，來源寫「內測」。
- **規則改了寫進那一塊的導覽檔**，不要寫回 `CLAUDE.md`（它只留跨區塊的原則、分支、指令與區塊表，上限約 1 萬 token）。
- **要停下來等很久之前**（例如等凌晨 03:00 token 刷新）先把進度寫進計畫或交接，回來時開新的對話接著做：長對話停太久，整串要按兩倍價錢重寫快取。
- 交接寫在 `docs/superpowers/handoff/`：分支與 HEAD、還沒提交的東西、開著的伺服器與埠、還開著的 FB、踩過的坑。
- 開發照技能 `tianxia-dev`（改網頁另看同資料夾的 `網頁.md`），QA 照技能 `tianxia-qa`（只能靠引擎驗的看同資料夾的 `引擎驗收.md`）；派工單寫明要用哪一個技能。這兩個技能是 10/19 收工的四個老對話寫的。

## PM 平行派工（2026-10-20 這一輪學到的）

- **交接是活的**：企劃者 2026-10-20「token 到上限我可能換帳號，要能接續開發」。PM 每合一次、派一次工、企劃者每定一件事，就更新 `docs/superpowers/handoff/` 最新那一份（分支與 HEAD、進行中的子代理與它們推到哪、下一步、等企劃者決定的、FB 號段與埠）並推上 develop。
- **派工前先核對現行程式**：計畫寫的「現在的程式」常常已經過時（例如計畫照 main 寫、develop 多了正式季十批）。派工單第一步寫「核對現行程式，差異寫進計畫第六節；前提不在了就停下來回報」。
- **平行的子代理**：
  - 每個 QA 給一段不重疊的 FB 號段（例：FB-460～469、470～479）。
  - 每個要開伺服器的給一個埠、一個 `<名字>.localhost`；瀏覽器一律帶自己的 tabId（10/20 有 QA 沒帶 tabId，動到另一個子代理的分頁）。
  - 小的修正與複驗可以派 `model: sonnet`。
- **疊批**：趕時間時，下一批可以接在還在 QA 的上一批上面開（例：`dev/shop-2` 從 `dev/shop-1` 開）；上一批的修正推回上一批的分支，下一批合進來再推。
- **暫停與用量上限**：企劃者喊暫停就用 TaskStop 停掉全部子代理，再查每個工作樹留下什麼：已推的記下來，沒推的由 PM 提交成 WIP 推上去，再派新的子代理接手。子代理撞到用量上限時，用 SendMessage 叫它從中斷的地方接著做，不要重派。
- **換帳號、對話斷掉，子代理全部停**（不是暫停，不會自己接回來；10/20 下午換帳號那一次三個都停在半路）。新的 PM：
  1. 兩份 clone 的 `.claude/worktrees/agent-*` 都看（工作樹開在派工那個 PM 對話所在的 clone），`git -C <工作樹> status`、`git log origin/<分支>..HEAD` 找沒提交、沒推的東西；
  2. 半成品由 PM 提交成 WIP 推上它的分支（commit 訊息寫停在哪一步）；
  3. 重派新的子代理（Agent 工具、`isolation: "worktree"`），派工單寫「從 `origin/<分支>` 開 `git switch -c <分支> origin/<分支>`，舊的工作樹不要用」，再把那一步之前做完的寫清楚；
  4. 交接第二節改成新派的這幾個。
  - **派之前先看自己的對話在哪個目錄**（2026-10-20 晚學到的）：新對話常常開在主 clone（`C:\Ray\專案\天下大勢`）或另一份 clone `C:\Ray\專案\ai遊戲`，那裡停在 `main` 的某一筆：CLAUDE.md 與技能可能是舊的（10/20 時是舊的大份、也沒有 `tianxia-dev`／`tianxia-qa` 技能；10/31 時兩份都還沒有指到開發規範手冊的那一行），從這裡派的子代理（`isolation: "worktree"`）兩樣都拿錯。先開自己的 PM 工作樹（`git worktree add <主 clone>/.claude/worktrees/pm-<名字> -b pm/<名字> origin/develop`），用 `mcp__ccd_directory__change_directory` 把對話搬過去（這一輪結束才生效：開一個很短的背景指令〔例如 fetch〕讓自己被叫回來），Bash 也 `cd` 過去，確認 `pwd` 是那個工作樹再派。
  - 半成品的 WIP 推到 `dev/<x>b` 這種另開的分支，不直接推回原本的 `dev/<x>`（QA 會從那裡開）；接手的子代理收尾之後再 fast-forward 推進 `dev/<x>`。
- **PM 不能寫別的工作樹的檔**（有 hook 擋）：PM 要改 develop 上的文件，在 scratchpad 開一個自己的工作樹（`git worktree add <scratchpad>/pmwt -b pm/<名字> origin/develop`；不要切主 clone 的分支，主 clone 是大家讀 `CLAUDE.md` 的地方），改完 `git push origin HEAD:develop`（快轉）。git 指令可以 `git -C` 別的工作樹。
- **主 clone 的 checkout 要跟上**（規範盤點 G17，PM 2026-10-31）：在 `C:\Ray\專案\天下大勢`、`C:\Ray\專案\ai遊戲` 開的新對話讀的是那裡 checkout 的 `CLAUDE.md` 與技能。PM 每次 `main` 往前（合 main、Joy 直推之後），在那份 checkout 乾淨時 `git -C <clone> pull --ff-only`，不切分支。Skill 清單裡的 `ai遊戲:tianxia-*` 是那一份 clone 的版本：派工單一律寫「讀 develop 上的 `.claude/skills/<技能>/SKILL.md`（Read 工作樹裡的檔）」。
- **這份 clone 的 `git fetch origin` 不會更新 `origin/dev/*`、`origin/feature/*`、`origin/qa/*`**（refspec 只有一部分）：核對推送、挑測試的 base、算 diff 之前，明確 fetch 那個分支（`git fetch origin +refs/heads/dev/x:refs/remotes/origin/dev/x`，或 `+refs/heads/dev/*:refs/remotes/origin/dev/*`），或直接看 `git ls-remote`。不然會把「推到了」誤判成「沒推到」、拿舊的 base 跑測試。
- **提前做（企劃者 2026-10-20「能提前先做的部分就加開任務」）**：
  - 下一批的引擎那一半疊在還沒 QA 完的上一批上開（`dev/<x>-2` 從 `dev/<x>-1`），派工單寫「每做完一個 Task、推之前先 `git merge --no-ff origin/dev/<x>-1`」；要等企劃者挑圖的網頁那一段留到最後。
  - 對比圖另開一條只放圖的分支（`dev/<x>-mock`），跟正在推程式的分支分開，合併時不會撞。
  - 要一起部署的幾條線，在正式合併之前先派一個 QA 做**整合預演**（`qa/integ-<名字>`，從 develop 開、把幾條線此刻的 HEAD 合進來）：衝突、整套、資料庫升級預演、部署說明草稿。正式合併時照它的紀錄解衝突。10/20 第一次做（`qa/integ-7day`）學到的：
    - 合的當下用 `git rev-parse` 記下每一條的 SHA（同一份 clone 別人會 fetch，`origin/*` 做到一半就往前走）；
    - 整套紅了，到那條線自己的 commit 上單獨重跑紅的那幾條，判斷是「合起來才壞」還是「原本就紅」；
    - 線後來又動了，用 `git merge-tree` 試合新的 HEAD，不動分支；
    - 資料庫升級預演：舊程式（`origin/main`）在暫存資料庫開季、建幾個角色、做幾個動作 → 備份 → 新程式開同一份 → 驗版本、資料都在、發放、對帳 → 舊程式開新版會擋 → 還原備份舊程式打得開；季中那一份另外試（季曆換算會不會錯）。
  - PM 用 Bash heredoc 跑 Python 改中文路徑時，一般字串裡的 `\a`（例 `專案\ai遊戲`、`worktrees\agent-*`）會變成響鈴字元：路徑一律用 raw string，寫完 `assert '\x07' not in s`。Windows 路徑（`C:\Users\...`）寫在一般字串裡是 `\U` 跳脫，整支腳本直接 SyntaxError——**改檔的腳本與後面的 `git add`／`commit`／`push` 一定用 `&&` 串**（2026-10-21 PM 用 `;` 串，腳本失敗了提交照跑，`main` 上多了一筆只改檔名的提交）；中文多、反斜線多的替換，寫成 scratchpad 裡的 .py 檔（Write 工具）再跑，不要塞進 heredoc。
  - 派工單寫 pytest 一律 `-n 4`、不要 `-n auto`（手冊 4.5：同一台同時最多兩份測試）。
  - **派工單裡直接點名測試檔的那一行 pytest 寫 `-m "slow or not slow"`**（2026-10-20 小單 QA：`pyproject.toml` 的 `addopts` 預設擋掉 slow，整個檔都標 slow 的 `test_fb504_*` 一條都沒跑，合併那一刻的整套才會紅）。`scripts/test_for.py` 那一行不帶它：`test_for` 不帶 slow（改到的測試檔本身除外），要連 slow 就加 `--slow`（手冊 4.3）。
  - **子代理共用 PM 的 scratchpad**（2026-10-20 有一個的 `edit_guide.py` 被另一個蓋掉）：派工單寫明暫存檔放在 scratchpad 底下自己的子資料夾（用分支名，例 `qa-small-1020/`）。
  - 子代理（尤其 sonnet）有時用 Skill 工具找不到 `tianxia-dev`／`tianxia-qa`（2026-10-21 有一個回報「這份 checkout 沒有這個技能」，其實檔案在）：派工單寫「Skill 工具找不到就直接 Read 工作樹裡的 `.claude/skills/<技能>/SKILL.md`」。
  - 派工單要開的本地分支名，可能已經被別的工作樹佔著（舊的子代理留下的同名本地分支，`git switch -c` 會失敗）：寫明「同名本地分支已存在就開 `<分支>-work`，推的時候照樣推到 `origin/<分支>`」。
- **分支名字別撞**：同一個字已經有別的意思時換個寫法並在交接註明（例：正式季第七批的 `qa/season-7` 與 7 天季的 `qa/season7`）。
- **合併的衝突**：
  - `試玩回饋.md` 兩邊都留，表格照 FB 編號排，檔尾的驗收紀錄照時間排。
  - `CLAUDE.md` 一律留瘦身版，對方新加的那一行搬進對應的 `docs/guide/`。
  - 用腳本解衝突時保留檔案原本的換行（`newline=""`），每一處 assert。
- **合併的順序**：功能分支合進 develop 之前，先把 develop（與 main 的新東西）合進功能分支，在那裡照上面「合併時跑哪一種」跑；合進 develop 時內容跟測過的一樣（`git diff --quiet HEAD <功能分支>`）就不必再跑一次。
- **git 沒衝突不代表合得起來**（10/21）：develop 與 main 各自都過，合起來正式內容載入就炸（main 給學來的武學掛小戰法、develop 讓同伴拿它們當起始武學；名品撞新招名）。合 main 之後先在 `season21`、`week7` 各載一次內容、起一次伺服器（總表第 14 批拿掉週末與不帶設定以前，不帶設定與 `weekend` 也各載一次），再跑整套。`git merge-tree --write-tree --name-only A B` 可以先看會不會有文字衝突。
- **上 main**（企劃者 2026-10-31：「之後上 main 一律從 develop 合、先跑整套含 slow」）：
  - 一律從 `develop` 合。合之前由合的人跑整套含 slow（`scripts/test_for.py --all`，`-n 4`，`TIANXIA_DB` 用暫存檔），結果（SHA、passed 條數）寫進 PR 說明或交接第五節，**綠的 SHA 要等於要合的那一筆 develop**。在 GitHub 按 PR 合的人（Joy）也一樣：先有人跑完、寫出條數與 SHA，對得上才按。
  - 部署說明（含〈退版風險〉，下面「照舊的規矩」）跟合 main 同一天寫好，經企劃者給 Joy。
  - 這一次要拿掉某一樣，才照下面 10/21 的做法開上線分支。
- **上 main 要拿掉某一樣時用上線分支**（10/21）：從 develop 開 `release/<日期>`，企劃者說「這一樣不放」就在上線分支 `git revert -m 1 <那個合併>`；合 main 之前每次 `ls-remote origin main`，Joy 又推了就先合進上線分支、整套。合進 main 之後把 main 合回 develop，再在 develop `git revert <那筆 revert>` 把功能還回來，整套、推，接著 develop 合進功能分支。合進 main 的時機跟部署一起排：一進 main，Joy 下一次照常部署就會換上它（資料庫改版回不去、季中換季曆會跳）。部署說明寫在 `docs/superpowers/feedback/`，經企劃者同意、由企劃者轉給 Joy。
- **跑整套的指令**：`TIANXIA_DB=<scratchpad>/db/x.db PYTHONIOENCODING=utf-8 C:/Ray/專案/天下大勢/.venv/Scripts/python.exe -m pytest -q -n 4 -p no:cacheprovider > log 2>&1; echo EXIT=$? >> log`（不含 slow，動到 `tianxia/`、`content/`、`server.py` 時才跑，另跑那一包相關的 slow；上 main 之前加 `-m "slow or not slow"`），背景跑，看最後那一行「N passed」與 EXIT 再推。
- **設計稿請人審**：寫完設計稿派一個子代理用「拿這份能不能開工」讀一遍，只把「只有企劃者能答」的問題一次問完，其餘 PM 自己定、標【PM】。

## 流程

1. **設計定了**：開發 session 照設計寫這一批的計畫（superpowers:writing-plans，存 `docs/superpowers/plans/`，不必給企劃者審），再照計畫在 session 裡一步一步做（executing-plans，不開子代理）。
2. **開發做完**：回報 commit、跑了哪些測試。不跑整套。
3. **唯讀審查**（2026-10-30 起 PM 的做法，手冊第十五節）：PM 派兩三位唯讀審查員（證明誠實度〔自己重跑〕、照不照手冊與批次表、回歸與相關 slow；300 行以下的純搬批兩位）。有 blocker／should 就派一個修的，修完才派 QA。審查員不改檔、不推。搬包的批用 `scripts/same_behavior.py` 證明行為一個字不變（`selftest --base`、`compare --base --head`；用法在腳本開頭的 docstring）。
4. **PM 派 QA**：只驗這一批，不重跑開發跑過的測試；純搬、`web/` 沒動的批改成兩台真伺服器逐位元組比（總表 5.0）；回饋單編號 PM 派工時給。
5. **QA 過了**：PM 把批合進功能分支 → 相關測試（動到 `tianxia/`、`content/`、`server.py` 再加不含 slow 的整套＋那一包相關的 slow）→ 綠了推上 → 更新架構圖（`docs/superpowers/architecture/三國篇架構.html`，重新發佈 artifact）。
6. **功能做完（或企劃者說要內測的一段）**：PM 合進 `develop` → 同上的閘門（內容跟測過的一樣〔`git diff --quiet`〕就不再跑）→ 推上；要內測就照「內測 develop」在這台主機換上那一筆。
7. **企劃者說可以上線**：PM 把 `develop` 合進 `main` → 整套含 slow（綠的 SHA＝合的那一筆）→ 推上 → 寫部署說明給 Joy（含〈退版風險〉），經企劃者給 Joy。

照舊的規矩：
- 畫面改動先出 2～3 張對比圖給企劃者挑（企劃者 2026-10-15）。
- 資料庫結構改版先跟 PM 對版本號（目前**第 9 版**，`tianxia/database.py` 的 `SCHEMA_VERSION`；下一版是第 10 版）。搬包不升（手冊 3.5）。
- **〈退版風險〉**（規範盤點 G13，PM 2026-10-31）：每一份要上 `main` 的說明（PR 說明或 `docs/superpowers/feedback/<日期>-<名字>-給joy.md`）都有這一節，逐條寫：(1) 資料庫版本升不升，升了舊程式打不打得開；(2) 舊程式讀新存檔會不會讀不下或丟東西，一欄一欄寫（新的 `Literal` 值、新的子模型、季上的新章、world 那一列的新鍵；FB-695，寫法見 `tianxia-dev`「也要讓舊程式讀得進新存檔」）；(3) 季中能不能換（季曆換算；走到一半的一趟、還在等應戰的約戰、集結中的決戰）；(4) 要不要休季部署；(5) 備份指令與緊急開關。開發的回報與雲端的 PR 說明各寫自己那一批的；搬包的批寫「舊程式寫到一半、新程式接手」那一步的結果與「資料庫逐表一樣」。
- 新寫的字標「待 joy 潤」，先做、之後再回頭潤字（企劃者 2026-10-14）。程式旁註解 `# 待 joy 潤`（js 寫 `// 待 joy 潤`；json 寫不了註解，就列在回報或 PR 說明）；開發與雲端在回報或 PR 說明列出這一批新加的，PM 收進交接「待 joy 潤」，潤過就拿掉標記、從清單劃掉。
- 要問 Joy 的直接問企劃者（企劃者 2026-10-31「不用轉~問我就好」），照他的答案做。
- **週末、14 天季、三選一**（企劃者 2026-10-31「現在只有7天跟21天兩種版本」）：整套拿掉，排在搬完六包之後（總表第 13、14 批）。在那之前新功能、新測試只照顧 `week7`、`season21` 與測試內容，不為 `weekend` 與不帶設定另寫分支或測試；三選一只修 bug、不搬；`same_behavior.py` 與「關著不變」的對照照舊比四種設定加測試內容。
- 假人與整季機器人不另外設計、不量，但任何畫面都不能透露誰是假人。
