---
name: tianxia-qa
description: 《天下大勢》驗收一批或一張回饋單（FB）之前先看：開本機伺服器與登入、打 API、在瀏覽器實機看、哪些只能靠引擎腳本驗、試玩回饋怎麼寫、qa/ 結果分支怎麼開與推、怎麼回報 PM。分支與測試的總規矩在 tianxia-flow，這一份只管驗收的做法。
---

# 天下大勢：QA 驗收怎麼做

這幾批的規則細節不在這裡，請看 `docs/guide/` 與派工單點名的計畫和設計。引擎腳本的寫法與範本看同一個資料夾的 `引擎驗收.md`。

## 開工
- **先對版本**：`git fetch`，再 `git ls-remote origin <分支>`，確認派工單給的 commit 還是最新的。PM 派單到你開工之間，分支常常已經往前走；回報之前再對一次。驗的是哪一個 commit 就寫哪一個。
- **開結果分支**：從派工單給的那個 commit 開，`git worktree add -b qa/<名字> .claude/worktrees/qa-<名字> <sha>`。複驗如果沿用既有的 qa/ 分支，先 `git merge --ff-only origin/<修好的分支>`，快轉到修好的版本。
- **寫檔被擋**：如果 hook 擋你寫別的工作樹的檔，就在自己 session 的工作樹 `git switch` 到結果分支來做。
- 工作樹沒有 `.venv`，一律用 `C:/Ray/專案/天下大勢/.venv/Scripts/python.exe`。印中文要設 `PYTHONIOENCODING=utf-8`（或把 stdout 包成 UTF-8）。
- **測試只跑派工單點名的檔**：`<python> -m pytest -q tests/a.py tests/b.py`。不跑整套，也不用 `test_for.py`，因為 engine、content 一動，它會挑到幾乎整套。
- 不開多代理工作流程，也不要一個驗收項目開一個子代理。

## 開伺服器與登入
- **複本**：在 scratchpad 用 bash `git -C <qa 工作樹> archive HEAD | tar -x -C <scratchpad>/on` 解一份來跑。PowerShell 的 tar 碰到中文路徑會壞。不要在 repo 裡跑伺服器，也不要改 repo 的設定與 `.local/`。
- **埠與 host**：先用 `netstat -ano | grep LISTEN` 挑沒人用的埠。cookie 照 host 分、不分埠，所以每個驗收都用自己的 `<名字>.localhost`（例 `qa7check.localhost:7893`）。同一個驗收要同時登兩個帳號，也要換 host。
- **設定**：`TIANXIA_PROFILE` 是 `weekend`、`season21`，或空字串（預設，14 天的季）。`TIANXIA_DB` 指到 scratchpad 的暫存檔。伺服器、`set_password.py`、`run_bots.py` 三者要設成一樣的值。
- **帳號**：`TIANXIA_PROFILE=… <python> scripts/set_password.py <帳號> --character <名號> --db <db> --local-dir <scratchpad>/local`。
  - 密碼寫在 `local/<帳號>_password.txt`，要用就從檔案讀，不要貼進對話。
  - 這樣建的角色不走草廬序章。要驗序章，就打 `POST /api/register {login,password,again}`，再打 `POST /api/character {name,gender}`（網頁註冊的那一條路）。
  - 不同資料庫的帳號用不同的 `--local-dir`，才不會互相蓋掉。
- **管理者**：設環境變數 `TIANXIA_ADMINS=驗收官`，再建一個叫這個名號的角色。全服第一季停在「籌備中」，要用管理者開季。
- **啟動**：用 PowerShell `Start-Process -FilePath <python> -ArgumentList "-u","server.py","--port","<埠>" -WorkingDirectory <複本> -RedirectStandardOutput out.log -RedirectStandardError err.log -WindowStyle Hidden -PassThru`。
  - 記下回傳的 PID。
  - 讀 log 用 `Get-Content out.log -Encoding UTF8`，核對印出來的「資料庫：」與「設定：」對不對。
  - 不要用 Bash 背景跑伺服器（會被砍）。
- **關**：`taskkill /PID <PID> /T /F`，暫時建的 `content/profiles` 也一起刪掉。
  - 關之前先確認那個埠是你開的：用 `Get-CimInstance Win32_Process` 看命令列、父行程與 log 的位置。
  - 別的 session 開的伺服器不要動。

## API
- 打 API 的腳本從 **bash** 跑，PowerShell 會把 JSON 參數弄壞。用 `requests.Session()`，先 `POST /api/login {login,password}`。
- **玩家**：`GET /api/main` 會同步並回 `status`／`options`／`latest`；按選項是 `POST /api/choose {id}`；其他動作走 `POST /api/do/<op>`。回傳的 `message` 是 HTML，`main` 是畫面。
- **管理者**也走 `POST /api/do/<op>`，不是 `/api/admin`。常用的：
  - `open_season`、`end_season`、`next_season`
  - `fast_forward {hours}`
  - `schedule {id, at:<現實 epoch>}`
  - `start_showdown {id}`
  - `resolve_event`
- **快轉的限制**：快轉只推世界時間。看現實時間的東西（出陣的每日次數 `PlayerState.sorties_today`、回體丹換日）快轉沒用，要改存檔。季曆的時刻夾在季末那一刻：把季末往後排，畫面照樣寫「週日 23:59」。
- `status` 裡沒有的鍵就是畫面不畫。要確認某個東西在某種季、某種狀態下不出現，直接看 `status` 有沒有那個鍵，再補打一次那個動作，確認什麼都沒動。

## 瀏覽器（in-app）
- 用 `tabs_create` 開分頁，再 `navigate` 到自己的 host。登入用 JS：`await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({login,password})})`，然後另起一次呼叫 `location.reload()`。
- **reload 要單獨一次呼叫**：同一段 JS 裡 reload，後面的程式會被切掉。等約 2 秒之後，再在下一次呼叫裡查畫面。
- 頁面每 10 秒打一次 `/api/main`。用 API 改了狀態之後，等 11 秒或 reload 再看。
- **按鈕用 JS 的 `el.click()`**，座標點擊常常沒反應。
- **量版面用 JS**：
  - 同一行：比 `getBoundingClientRect().top`。
  - 沒有橫向捲動：`scrollWidth` 等於 `clientWidth`。
  - 字被切掉：元素的 `scrollWidth` 大於 `clientWidth`。
  - 截圖與 `zoom` 拿來當證據。
- **寬度與深色**：用 `resize_window` 設 375×812、360×780，`colorScheme` 設 dark 或 light。窗格寬度一變、回合結束，這些設定都會被重設，要再設一次。做完設回 `preset: desktop`。

## 存檔、資料庫與假人
- 換季之後、玩家第一次同步之前改的存檔，會被換季重設洗掉。要等他同步完再改。
- **讀資料庫只開唯讀**：`sqlite3.connect("file:<db>?mode=ro", uri=True)`。`characters` 有 `is_bot` 和 `data`（JSON，`player`、`journal`），江湖紀錄只留最近 30 則。
- **複製資料庫**用 sqlite 的 `backup()`，不要只複製 `.db`，WAL 裡的資料會漏掉。
- `battles` 是最新的在前（`battles[0]`）。腳本移動角色之前先略過序章（`skip_tutorial` 會重設地點）。自動選事件的迴圈要排除 `choice:free`（那一顆要打字）。
- 決戰的「定結果」只能定還沒開打的。要驗發獎勵就實際打完：用腳本把 `muster_deadline_real` 和 `round.opened_real` 拉到過去。
- **假人**：只在台灣時間 11:30～13 與 19～24 上線，懶的有些日子整天不上線。
  - 其他時段：把資料庫複製一份，用 `BotRunner(content, client=None, clock=lambda: 假時間)` 一輪一輪 `tick()`。
  - 正式驗「看不出是假人」：查角色存檔以外的每一張表，加上 `status`、玩家卡、傳聞、江湖史。

## 只能靠引擎腳本驗的（寫法看 `引擎驗收.md`）
- 跟開季時刻有關的：伺服器開季用真實時間，例如週三開季。
- 沒有設定檔可切的開關：例如素材四階關掉。
- **機率**：一種跑幾千次，報次數與百分比；也要跑「不該發生」的那幾種，確認是 0。
- 滿級換心得、頭目戰、切磋、決戰軍餉、求援傳聞。
- **用自己亂數的掉落**（名號＋戰報流水號）：先照種子挑出擲得中的名號建角色，再實打。
- **注意**：
  - 腳本用暫存的 `TIANXIA_DB`；設定檔要用 `load_content(Path("content"), profile)` 傳進去，環境變數讀不到。
  - 超過兩分鐘的跑法放背景。
  - 回報時寫清楚哪幾項是引擎驗的、哪幾項是實機。

## 試玩回饋（`docs/superpowers/feedback/試玩回饋.md`）
- **只改這一個檔。** 檔案是 CRLF，用 Python 改：
  1. 讀進來，把 `\r\n` 轉成 `\n`。
  2. 找錨點那一列，並 assert 下一行是空行。
  3. 在表格最後一張 FB 後面插新的列。
  4. 在檔尾加一段驗收紀錄。
  5. assert 都過了才寫回 `\r\n`，寫完才印 ok，再用 `git diff --stat` 確認。
- 不要用 sed 改，`\|` 會被當成「或」。
- **表格一列八格**：`| FB-編號 | 日期 | 來源 | **一句話標題**：內容 | 類別 | 嚴重 | 狀態 | 位置 |`。
  - 來源寫「QA 驗正式季第 N 批（host:埠，設定，分支 `sha`）」，接著同一來源的幾列寫「同上」。
  - 內容寫實機怎麼重現、量到的數字、程式在哪、建議怎麼改。
  - 類別用介面、字、體驗、規則等；嚴重用小、中、大；位置寫函式名或檔名。
  - FB 編號從派工單給的號碼開始編。
- **狀態只留一段**：
  - 新開的寫 `新`。
  - 開發修好寫 `已修好待複測（分支 `sha`：改了什麼）`。
  - 複驗通過就把整格**換成** `✅ 已驗證（日期 複驗，分支 `sha`，見「段落名」）`，不要接在舊狀態後面。合併時兩邊接起來的（「✅…；新」），看到就清掉後半。
- **驗收紀錄**接在檔尾：
  - 標題：`### 正式季第 N 批「名稱」QA（日期，分支 `sha`；host、暫存資料庫、設定、寬度）`；複驗寫成 `### …複驗：FB-xxx～yyy（…）`。
  - 條列：**測試**（跑了哪幾個檔、幾個 passed）、**做法**、**1.～N.** 每一項怎麼驗、看到什麼（照實寫數字與畫面上的原字）、**順帶**（看到但不是這一批的）、**新開的 FB**、**沒驗到的**（一定要寫，含只在引擎驗的）。

## 結果分支
- qa/ 分支只 commit 試玩回饋，一個 commit。commit 訊息用英文一行，說驗了什麼、開了哪幾張 FB，結尾空一行加 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。
- `git push -u origin qa/<名字>`，接著 `git ls-remote origin qa/<名字>`，確認遠端那一個跟本機的 commit 一樣。
- 不合併，合併是 PM 的事。

## 回報 PM
- 用 SendMessage 回派工的那個 session（照訊息的 `from`），用繁體中文。
- **第一行**寫結論，加 commit，例如「第 7 批 QA 完成：九項照設計，新開 FB-436～438，結果在 qa/season-7 `3cbaea20`（已推）」。
- **接著**：驗的分支與 commit、測試結果、每一項一兩句（照派工單的編號）、新開 FB 一張一句、順帶看到的、沒驗到的。
- **最後**：伺服器和假人程式關了沒有。
- 長度照 PM 的要求。不要寫「應該沒問題」，沒驗到就寫沒驗到。
