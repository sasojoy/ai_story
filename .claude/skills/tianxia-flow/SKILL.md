---
name: tianxia-flow
description: 《天下大勢》的分支、測試與合併規矩（企劃者 2026-10-18 定）。開工、派工、開發、QA 驗收、合併、推上 GitHub、部署之前都先看這一份：功能在哪一條分支做、合到哪裡、什麼時候才跑整套測試、QA 要跑哪些測試。
---

# 天下大勢：分支、測試與合併

企劃者 2026-10-18 定的規矩（「這些正式賽季的項目開一個新的分支來做。未來就要有一個 develop 分支，甚至可能還會再部署 develop 做內測之後才回 master」「除非再做 branch merge 的這種時間點，不然 QA 都不要跑全部的測試，只跑最小量需求節省 token」）。跟 CLAUDE.md 或舊計畫對不上時，以這一份為準。

## 分支

| 分支 | 用途 | 誰合進來、什麼時候 |
|---|---|---|
| `main` | 線上正式版（tianxiadashi.com 跑的那一份） | 只有企劃者說可以上線，才從 `develop` 合進來。Joy 的維運與緊急修正照舊可以直接推 `main` |
| `develop` | 整合與內測 | 功能分支做完（或企劃者說要內測的一段）由 PM 合進來；之後可能另外部署一份 `develop` 給內測，內測過了才合回 `main` |
| 功能分支 `feature/<名字>` | 一個大功能一條，從 `develop` 開 | 分批開發的每一批，QA 過了由 PM 合進來 |
| 批的工作樹分支 | 開發 session 的工作樹，從功能分支開 | 開發自己提交；不直接推 `main`、`develop` |

- 現在的功能分支：`feature/formal-season`＝正式季整合（21 天的季、行動精準化、素材四階；設計 `docs/superpowers/specs/2026-10-17-正式季整合-design.md`，十批照第十一章的順序）。
- 流向只有一條：批的工作樹分支 → 功能分支 → `develop` →（內測）→ `main`。**不要從功能分支或工作樹直接合 `main`。**
- `main` 有新東西（Joy 推的）時，下一次合併的人先把 `main` 合進 `develop`、再把 `develop` 合進功能分支（`git merge --no-ff`，不 rebase 已經推上去的分支）。衝突照「程式為準」解，解不了的問 PM。
- 每次推上去都確認推到了：`git merge-base --is-ancestor HEAD origin/<分支>`（別的 session 也會動同一份 clone）。
- 線上伺服器照舊跑 `main`；內測的 `develop` 怎麼部署，等第一次要內測時由 PM 寫部署說明給 Joy（另開一個資料庫、另一個埠，不碰線上那一份）。

## 測試：平常只跑最小量

- **開發中、QA 驗收**：只跑跟這一次改動直接相關的測試，**不跑整套**。
  - 在批的工作樹裡：`.venv/Scripts/python.exe scripts/test_for.py --base origin/feature/<名字>`（只跟功能分支比；不給 `--base` 會跟 `origin/main` 比，把整條功能分支以前的改動都算進來）。也可以設環境變數 `TIANXIA_TEST_BASE`，或直接給檔名（`scripts/test_for.py tianxia/fusion.py`）、直接跑 `pytest tests/test_x.py`。
  - QA 只跑它驗的那幾樣的測試檔，其餘靠實機（瀏覽器）驗；不要為了「保險」跑整套。
  - 改到 `tests/conftest.py`、`tests/fixtures/`、`pyproject.toml` 的批，開發跑 `test_for.py` 會挑到整套：這時只跑那幾個改到的測試檔與直接相關的，整套留到合併那一刻。
- **整套（含 slow）只在分支合併的那一刻跑一次**，由做合併的人（PM）跑：
  `.venv/Scripts/python.exe -m pytest -q -n auto -m "slow or not slow"`（`TIANXIA_DB` 設到 repo 外的暫存檔；不寫 `-m ""`）。
  - 時機：批合進功能分支、功能分支合進 `develop`、`develop` 合進 `main`、`main` 合進 `develop`／功能分支。
  - 整套綠了才推；紅了把失敗的那幾條交回開發，修好之後再跑那幾條就好，推之前再跑一次整套。
- 不要為了預先判斷平衡跑模擬或量表（企劃者 2026-10-14「給玩家實際體驗回饋最準」）；計畫本身寫了要量的照量。
- 開發、QA 自己不再開多代理工作流程（Workflow），也不一項一個子代理（PM 派出來的那一個子代理就是開發或 QA 本人）。

## 一件事一個新的對話（企劃者 2026-10-19）

企劃者 2026-10-19「現在這些老 session 都不要當主要驗證或開發，要多利用新派 session 或者 agent 的方式精準化」。量到的原因：連跑好幾天的開發、QA 對話每一則長到約 95 萬 token，每回一句話都把整串重讀一遍，重讀佔了花費的八成。

- **一批開發、一次驗收，各開一個新的對話或子代理**（PM 用 Agent 工具派，或開新的 session）；做完回報就收，不接下一件。修正一輪也是一件：修的人與驗的人都重新開。
- **派工單寫明三樣**：要讀哪幾塊導覽檔（`CLAUDE.md` 的區塊表，`docs/guide/`）、要改或要驗的範圍、要跑哪幾個測試檔。接手的人只讀那幾塊，不整批讀導覽檔、不整份讀設計文件（用 `grep -n '^#'` 看大綱，只讀相關的節）。
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
- **PM 不能寫別的工作樹的檔**（有 hook 擋）：PM 要改 develop 上的文件，在 scratchpad 開一個自己的工作樹（`git worktree add <scratchpad>/pmwt -b pm/<名字> origin/develop`；不要切主 clone 的分支，主 clone 是大家讀 `CLAUDE.md` 的地方），改完 `git push origin HEAD:develop`（快轉）。git 指令可以 `git -C` 別的工作樹。
- **這份 clone 的 `git fetch origin` 不會更新 `origin/dev/*`、`origin/feature/*`、`origin/qa/*`**（refspec 只有一部分）：核對推送、挑測試的 base、算 diff 之前，明確 fetch 那個分支（`git fetch origin +refs/heads/dev/x:refs/remotes/origin/dev/x`，或 `+refs/heads/dev/*:refs/remotes/origin/dev/*`），或直接看 `git ls-remote`。不然會把「推到了」誤判成「沒推到」、拿舊的 base 跑測試。
- **提前做（企劃者 2026-10-20「能提前先做的部分就加開任務」）**：
  - 下一批的引擎那一半疊在還沒 QA 完的上一批上開（`dev/<x>-2` 從 `dev/<x>-1`），派工單寫「每做完一個 Task、推之前先 `git merge --no-ff origin/dev/<x>-1`」；要等企劃者挑圖的網頁那一段留到最後。
  - 對比圖另開一條只放圖的分支（`dev/<x>-mock`），跟正在推程式的分支分開，合併時不會撞。
  - 要一起部署的幾條線，在正式合併之前先派一個 QA 做**整合預演**（`qa/integ-<名字>`，從 develop 開、把幾條線此刻的 HEAD 合進來）：衝突、整套、資料庫升級預演、部署說明草稿。正式合併時照它的紀錄解衝突。10/20 第一次做（`qa/integ-7day`）學到的：
    - 合的當下用 `git rev-parse` 記下每一條的 SHA（同一份 clone 別人會 fetch，`origin/*` 做到一半就往前走）；
    - 整套紅了，到那條線自己的 commit 上單獨重跑紅的那幾條，判斷是「合起來才壞」還是「原本就紅」；
    - 線後來又動了，用 `git merge-tree` 試合新的 HEAD，不動分支；
    - 資料庫升級預演：舊程式（`origin/main`）在暫存資料庫開季、建幾個角色、做幾個動作 → 備份 → 新程式開同一份 → 驗版本、資料都在、發放、對帳 → 舊程式開新版會擋 → 還原備份舊程式打得開；季中那一份另外試（季曆換算會不會錯）。
  - PM 用 Bash heredoc 跑 Python 改中文路徑時，一般字串裡的 `\a`（例 `專案\ai遊戲`、`worktrees\agent-*`）會變成響鈴字元：路徑一律用 raw string，寫完 `assert '\x07' not in s`。
  - 同時跑很多子代理時，派工單寫 pytest 用 `-n 6`～`-n 8`、不要 `-n auto`，免得互相搶 CPU。
- **分支名字別撞**：同一個字已經有別的意思時換個寫法並在交接註明（例：正式季第七批的 `qa/season-7` 與 7 天季的 `qa/season7`）。
- **合併的衝突**：
  - `試玩回饋.md` 兩邊都留，表格照 FB 編號排，檔尾的驗收紀錄照時間排。
  - `CLAUDE.md` 一律留瘦身版，對方新加的那一行搬進對應的 `docs/guide/`。
  - 用腳本解衝突時保留檔案原本的換行（`newline=""`），每一處 assert。
- **合併的順序**：功能分支合進 develop 之前，先把 develop（與 main 的新東西）合進功能分支，在那裡跑整套；合進 develop 時內容跟測過的一樣（`git diff --quiet HEAD <功能分支>`）就不必再跑一次。
- **跑整套的指令**：`TIANXIA_DB=<scratchpad>/db/x.db PYTHONIOENCODING=utf-8 C:/Ray/專案/天下大勢/.venv/Scripts/python.exe -m pytest -q -n auto -m "slow or not slow" -p no:cacheprovider > log 2>&1; echo EXIT=$? >> log`，背景跑，看最後那一行「N passed」與 EXIT 再推。
- **設計稿請人審**：寫完設計稿派一個子代理用「拿這份能不能開工」讀一遍，只把「只有企劃者能答」的問題一次問完，其餘 PM 自己定、標【PM】。

## 流程

1. **設計定了**：開發 session 照設計寫這一批的計畫（superpowers:writing-plans，存 `docs/superpowers/plans/`，不必給企劃者審），再照計畫在 session 裡一步一步做（executing-plans，不開子代理）。
2. **開發做完**：回報 commit、跑了哪些測試。不跑整套。
3. **PM 派 QA**：只驗這一批，只跑最小量測試；回饋單編號 PM 派工時給。
4. **QA 過了**：PM 把批合進功能分支 → 跑整套 → 綠了推上 → 更新架構圖（`docs/superpowers/architecture/三國篇架構.html`，重新發佈 artifact）。
5. **功能做完（或企劃者說要內測的一段）**：PM 合進 `develop` → 整套 → 推上；要內測時寫部署說明給 Joy。
6. **企劃者說可以上線**：PM 把 `develop` 合進 `main` → 整套 → 推上 → 寫部署說明給 Joy（資料庫改版、要備份、要在休季部署的都寫明）。

照舊的規矩：
- 畫面改動先出 2～3 張對比圖給企劃者挑（企劃者 2026-10-15）。
- 資料庫結構改版先跟 PM 對版本號（目前第 5 版，下一版是第 6 版）。
- 新寫的字標「待 joy 潤」，先做、之後再回頭潤字（企劃者 2026-10-14）。
- 假人與整季機器人不另外設計、不量，但任何畫面都不能透露誰是假人。
