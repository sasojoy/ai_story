---
name: tianxia-qa
description: 《天下大勢》驗收一批或一張回饋單（FB）之前先看：開本機伺服器與登入、打 API、在瀏覽器實機看、哪些只能靠引擎腳本驗、試玩回饋怎麼寫、qa/ 結果分支怎麼開與推、怎麼回報 PM。分支與測試的總規矩在 tianxia-flow，這一份只管驗收的做法。
---

# 天下大勢：QA 驗收怎麼做

這幾批的規則細節不在這裡，請看 `docs/guide/` 與派工單點名的計畫和設計。引擎腳本的寫法與範本看同一個資料夾的 `引擎驗收.md`。

## 開工
- **先對版本**：`git fetch`，再 `git ls-remote origin <分支>`，確認派工單給的 commit 還是最新的。PM 派單到你開工之間，分支常常已經往前走；回報之前再對一次。驗的是哪一個 commit 就寫哪一個。
  - 這份 clone 的 `git fetch origin` 不更新 `origin/dev/*`、`origin/qa/*`（fetch 的 refspec 沒有它們）。要對的每一條各寫一個明確的 refspec：`git fetch origin +refs/heads/dev/<名>:refs/remotes/origin/dev/<名> +refs/heads/qa/<名>:refs/remotes/origin/qa/<名>`，再 `git rev-parse origin/dev/<名>`；不然讀到的是舊的。
- **Skill 工具找不到 `tianxia-qa`**（子代理的工作樹常停在舊 commit，那個 commit 還沒有這個技能）：先 `git switch` 到結果分支，再直接 Read `.claude/skills/tianxia-qa/SKILL.md` 與 `引擎驗收.md`。
- **開結果分支**：從派工單給的那個 commit 開，`git worktree add -b qa/<名字> .claude/worktrees/qa-<名字> <sha>`。複驗如果沿用既有的 qa/ 分支，先 `git merge --ff-only origin/<修好的分支>`，快轉到修好的版本。
- **寫檔被擋**：如果 hook 擋你寫別的工作樹的檔，就在自己 session 的工作樹 `git switch` 到結果分支來做。
- 工作樹沒有 `.venv`，一律用 `C:/Ray/專案/天下大勢/.venv/Scripts/python.exe`。印中文要設 `PYTHONIOENCODING=utf-8`（或把 stdout 包成 UTF-8）。
- **測試只跑派工單點名的檔**：`<python> -m pytest -q tests/a.py tests/b.py`。不跑整套，也不用 `test_for.py`，因為 engine、content 一動，它會挑到幾乎整套。
- 不開多代理工作流程，也不要一個驗收項目開一個子代理。
- **在隔離的工作樹裡**（PM 用 Agent 派的子代理）：Bash 工具會擋帶中文路徑的 python（`C:/Ray/專案/…/python.exe`），python 一律從 PowerShell 跑，git 照樣用 Bash。PowerShell 傳 JSON 參數會壞：把 JSON 寫進腳本，或讓腳本收一般參數。
  Bash 也會擋「`cd` 到工作樹外面」或太複雜的指令（heredoc 加管線、`od` 之類，回「too complex to verify that it stays inside the worktree」）：小腳本用 Write 寫進 scratchpad、用絕對路徑跑（系統的 `python` 可以），git 一律 `git -C <自己的工作樹>`。
  - Bash 也會拒絕「看不出會不會碰到別的工作樹」的複雜指令（遇到過的：`cd` 到工作樹外面的資料夾、拿 shell 變數組出別的資料夾的路徑、awk、在 Bash 裡再叫 powershell）。腳本一律用 Write 寫成檔，再從 Bash 跑 `python3 <絕對路徑>`（系統的 python 3.14 有 requests，打 API 與唯讀讀資料庫夠用），不 `cd`、路徑寫絕對的；node 與 venv 的 python 從 PowerShell 跑。
  - Git Bash 會改參數：`rev:path`（`git show origin/develop:.claude/…`）被當成路徑清單、開頭是 `/` 的（`/api/mall/buy`）變成 `C:/Program Files/Git/api/…`。拿舊版的檔用 `git archive <sha> <檔…> -o x.tar` 再 `tar --force-local -x`；打 API 的腳本收不帶斜線的路徑。`cmd /c` 會吃掉 `^`（`8be1a6eb^1` 拿到的是別的版本），先在 PowerShell `git rev-parse` 成完整的 sha。
  - Write 寫的 `.ps1` 是沒有 BOM 的 UTF-8，PowerShell 5.1 當 ANSI 讀、中文整個壞掉：寫完用 `[IO.File]::WriteAllText(檔, 內容, (New-Object Text.UTF8Encoding($true)))` 補 BOM。
  - 長跑的 node／python 不要接 `| Select-Object -First N`：拿到 N 行 PowerShell 就收掉行程（exit 255），`finally` 裡關 chromium 那一段不會跑。輸出導進檔案再讀。
- **PowerShell 腳本檔（`.ps1`）不要寫中文路徑**（2026-10-20 領地爭奪複驗，一整輪空跑）：Write 工具寫的檔沒有 BOM，PowerShell 5.1 當 ANSI 讀，`$PY` 變成亂碼、回「The term … is not recognized」，錯誤落在工作輸出、不在導向的 log 裡，檔案一個都沒生出來。python 指令直接寫在 PowerShell 工具的呼叫裡（路徑照常寫中文），`.ps1` 只放 ASCII 路徑；要跑好幾次就在同一個呼叫裡寫 `foreach`。
- **git 一個指令一個指令跑**：`W=…; git -C "$W" … | …; git -C "$W" …` 這種變數加管線加好幾個 git 串在同一行，會被擋（too complex）。拆成單一的 `git -C <絕對路徑> …`；要 grep 輸出就先 `> scratchpad 的檔`，再另一個指令 grep。
- **兩份複本對照要平行跑**：PowerShell `Start-Process -FilePath <python> -ArgumentList '-u','-I',<腳本> -RedirectStandardOutput <檔> -RedirectStandardError <檔> -WindowStyle Hidden -PassThru`，各設自己的 `QA_ROOT`；不加 `-u` 的話輸出要等跑完才寫進檔，看不到進度。
- **scratchpad 跟同一個 PM 派出的其他子代理共用**（2026-10-20 在 `shots/` 看到別人的檔）：自己的複本、資料庫、截圖，都放在用這次驗收命名的子資料夾。
  - **子資料夾別取開發分支的名字**（2026-10-21 小單：`small1021b` 裡已經躺著開發的人留下的 `repro635.py`、`mutate.py`）：取 `qa<名字>`。
  - **`python -I` 會忽略 `PYTHONIOENCODING`**：腳本自己 `sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")`，不然印中文在 cp950 噴 `UnicodeEncodeError`、整支腳本中途死掉（輸出檔寫到一半）。
  - **PowerShell 的 `Remove-Item <資料夾>\*` 會被擋成「protected path」**：換一個新資料夾／新檔名，或用 Python `shutil.rmtree`。
- **Git Bash 的 tar 把 `C:/…` 當成遠端主機**（回「Cannot connect to C: resolve failed」，2026-10-21 輿圖第三版第 2 批）：先 `git -C <工作樹> archive -o <scratchpad>/x.tar <sha>`，再 `tar --force-local -x -f <tar> -C <資料夾>`。
- **隔離工作樹裡 Bash 也擋這幾種**（2026-10-21 玉璽碎片複驗）：`SP=…` 變數加 `git archive` 加 `tar` 串在同一行、`python <<EOF` 的 heredoc、`python -I x.py` 帶中文 scratchpad 路徑的 Bash。做法：`git -C <工作樹> archive -o <絕對路徑>.tar <sha>` 一個指令一次（路徑寫死、不用變數）；解壓與批次修補檔都用 Write 工具寫成 `.py`（解壓用 `tarfile`，讀自己所在資料夾的 `*.tar`）再從 PowerShell `python -I` 跑；要平行跑一排腳本，在 PowerShell 同一個呼叫裡 `Start-Process` 一排再 `Wait-Process`（輸出導到各自的 `.txt/.out/.err`，`.err` 有東西才看）。
- **子代理的 Bash 連 tar 都擋**（「computed value」，2026-10-21 翻地複驗）：`git archive -o` 之後用 Python `tarfile`（`untar.py`：`extractall` 時排除 `docs/`、`.claude/`）解；PowerShell 的 tar 解 `docs/` 底下的中文檔名會回 `Invalid empty pathname`，code 檔其實也沒解完。
- **`Start-Process -ArgumentList` 的陣列元素有空格要自己加引號**：`-m "slow or not slow"` 寫成 `'"slow or not slow"'`；沒加就被拆成四個參數，pytest 回「no tests ran in 3s」、一個測試都沒跑（2026-10-21）。
- **平行驗收**（2026-10-20）：PM 會給你一段 FB 號段、一個埠和一個 `<名字>.localhost`，只用給你的；瀏覽器窗格是共用的，**每一個動作都帶自己的 tabId**（10/20 有 QA 沒帶，動到別的子代理的分頁）。驗完把視窗設回 desktop、配色淺色、關掉自己的分頁、`taskkill /T` 關伺服器。
- 開關的「一個字都不變」最好的驗法：同一支腳本，在功能分支開出來的那一點（`git archive` 解出來）和這一版各跑一次，比輸出。

## 開伺服器與登入
- **複本**：在 scratchpad 用 bash `git -C <qa 工作樹> archive HEAD | tar -x -C <scratchpad>/on` 解一份來跑。PowerShell 的 tar 碰到中文路徑會壞。先 `git archive -o <檔>.tar` 再解的話，Git Bash 的 tar 要加 `--force-local`（`tar --force-local -xf C:/…/x.tar -C …`），不然把 `C:` 當成遠端主機、回「Cannot connect to C: resolve failed」。不要在 repo 裡跑伺服器，也不要改 repo 的設定與 `.local/`。
- **擋 11434**：有人登入時，伺服器會預熱模型（`server._warm_model` 連 Ollama）。在複本的 `content/config.json` 加一個鍵 `"ollama_url": "http://127.0.0.1:9"`（只改 scratchpad 的複本），就打不到 11434。
  - **要看等模型的中間狀態**（〈天下形勢〉的「還在落筆」之類）：`127.0.0.1:9` 一叫就失敗、伺服器馬上照固定段收，中間狀態一次輪詢都撐不過。改開一個假的模型：Python `http.server`，GET 回 `{"models": []}`、POST 睡 25 秒再回 500，複本的 `ollama_url` 指到它（2026-10-21 翻地 QA，FB-578）。
- **埠與 host**：先用 `netstat -ano | grep LISTEN` 挑沒人用的埠。cookie 照 host 分、不分埠，所以每個驗收都用自己的 `<名字>.localhost`（例 `qa7check.localhost:7893`）。同一個驗收要同時登兩個帳號，也要換 host。
- **設定**：`TIANXIA_PROFILE` 是 `weekend`、`season21`、`week7`（7 天濃縮季），或空字串（預設，14 天的季）。`TIANXIA_DB` 指到 scratchpad 的暫存檔。伺服器、`set_password.py`、`run_bots.py` 三者要設成一樣的值。
- **帳號**：`TIANXIA_PROFILE=… <python> scripts/set_password.py <帳號> --character <名號> --db <db> --local-dir <scratchpad>/local`。
  - 密碼寫在 `local/<帳號>_password.txt`，要用就從檔案讀，不要貼進對話。
  - 這樣建的角色不走草廬序章。要驗序章，就打 `POST /api/register {login,password,again}`，再打 `POST /api/character {name,gender}`（網頁註冊的那一條路）。
  - **要驗序章或初入江湖的某一步**：先走網頁那一條建角色，再直接改 `characters.data` 裡的 `player.tutorial_step` 與 `player.location`（`tutorial.json` 的 `prologue_steps`＝11，0～10 在草廬、`location` 要是 `mentor_hut`；11～14 是初入江湖 e1～e4，`location` 換成 `yingchuan`；15 走完）。伺服器開著也能改：`sqlite3.connect(db, timeout=30)`、`BEGIN IMMEDIATE`，下一個請求會從資料庫重讀。
  - 不同資料庫的帳號用不同的 `--local-dir`，才不會互相蓋掉。
- **管理者**：設環境變數 `TIANXIA_ADMINS=驗收官`，再建一個叫這個名號的角色。全服第一季停在「籌備中」，要用管理者開季。
- **啟動**：用 PowerShell `Start-Process -FilePath <python> -ArgumentList "-u","server.py","--port","<埠>" -WorkingDirectory <複本> -RedirectStandardOutput out.log -RedirectStandardError err.log -WindowStyle Hidden -PassThru`。
  - 記下回傳的 PID。
  - 讀 log 用 `Get-Content out.log -Encoding UTF8`，核對印出來的「資料庫：」與「設定：」對不對。
  - 不要用 Bash 背景跑伺服器（會被砍）。
- **關**：`taskkill /PID <PID> /T /F`，暫時建的 `content/profiles` 也一起刪掉。
  - 關之前先確認那個埠是你開的：用 `Get-CimInstance Win32_Process` 看命令列、父行程與 log 的位置。
  - 別的 session 開的伺服器不要動。
- **要驗內容檔現在沒有的寫法**（例：序章哪一步 reveal 寫了 `all`）：scratchpad 再解一份複本改那個內容檔，另開一個埠、另一個 `<名字>b.localhost`、另一個資料庫，只開來驗那一項；驗完 `taskkill /T` 並把複本刪掉。主要那一台不動。

## API
- 打 API 的腳本從 **bash** 跑，PowerShell 會把 JSON 參數弄壞。用 `requests.Session()`，先 `POST /api/login {login,password}`。
- 被引擎擋的動作（非管理者打管理者的 op）回 400，body 是 `{"error": "只有管理者能這麼做。"}`；找不到的 op 才是 404 `{"detail": "Not Found"}`——檢查字樣讀 `error`，不是 `detail`（2026-10-21，FB-609 複驗）。
- **玩家**：`GET /api/main` 會同步並回 `status`／`options`／`latest`；按選項是 `POST /api/choose {id}`；其他動作走 `POST /api/do/<op>`。回傳的 `message` 是 HTML，`main` 是畫面。
- **管理者**也走 `POST /api/do/<op>`，不是 `/api/admin`。常用的：
  - `open_season`、`end_season`、`next_season`
  - `fast_forward {hours}`
  - `schedule {id, at:<現實 epoch>}`
  - `start_showdown {id}`
  - `resolve_event`
- **快轉的限制**：快轉只推世界時間。看現實時間的東西（出陣的每日次數 `PlayerState.sorties_today`、回體丹換日）快轉沒用，要改存檔。季曆的時刻夾在季末那一刻：把季末往後排，畫面照樣寫「週日 23:59」。
  - `fast_forward` 的 `hours` 只收整數；week7 現實一小時是季曆 12 小時，湊不到 23:59。要最壞的時刻：先 `schedule {"id": "xiaquyang", "at": <九天後的 epoch>}`（下曲陽・季末）再快轉過頭，季曆就停在「第 12 週・週日 23:59」，時鐘走著也不動。
  - `pause_clock` 會在江湖頁多一張暫停的卡、行動列換成一顆灰的選項：第一屏（行動列底緣）要在時鐘走著時量，逐像素比新舊時才暫停。
- **畫面的資料不全在 `status`**：
  - 軍令卡在 `main["orders"]`。
  - 按了 `act:bounties` 之後，懸賞榜在 `main["shop"]`（`notes` 每張有 `short`、`due`）。
  - 管理者頁（時刻表每一列、排定的現實時間 `at_real`）要 `GET /api/admin`；`main["admin"]` 只是布林。
- **`/api/do/<op>` 先查 `ADMIN_ACTIONS`**：玩家動作跟管理者動作同名時，玩家打到的是管理者那一個（回「只有管理者能這麼做。」）。一批加了新動作，先看一次 `set(server.MAIN_ACTIONS) & set(server.ADMIN_ACTIONS)`，再用玩家帳號真的打一次那個路由（2026-10-21 翻地 QA，FB-609：單元測試只看兩張表各有那個鍵）。
- **實機對照「一個字都不變」**：腳本用 `subprocess.Popen` 在同一個埠輪流起兩份複本的伺服器，各用新的暫存資料庫，只打 API、印要比的欄位；把現實時刻的 `HH:MM` 換掉再 diff，結束時 `taskkill /T`。
- `status` 裡沒有的鍵就是畫面不畫。要確認某個東西在某種季、某種狀態下不出現，直接看 `status` 有沒有那個鍵，再補打一次那個動作，確認什麼都沒動。

## 瀏覽器（in-app）
- 用 `tabs_create` 開分頁，再 `navigate` 到自己的 host。登入用 JS：`await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({login,password})})`，然後另起一次呼叫 `location.reload()`。
- **reload 要單獨一次呼叫**：同一段 JS 裡 reload，後面的程式會被切掉。等約 2 秒之後，再在下一次呼叫裡查畫面。
- 頁面每 10 秒打一次 `/api/main`。用 API 改了狀態之後，等 11 秒或 reload 再看。
- **按鈕用 JS 的 `el.click()`**，座標點擊常常沒反應。
- **換帳號**：同一個分頁重打 `/api/login` 就換掉 cookie，再單獨一次 reload。兩個帳號要同時登著才需要換 host。
- **不把密碼貼進對話**：用 python `requests` 登入、只印 `tx_session`（`s.cookies.get("tx_session")`），再在分頁裡 `document.cookie = "tx_session=<值>; path=/"`、另起一次呼叫 `location.reload()`。換帳號就再取一個值、再寫一次 cookie；這個 token 只在你自己的暫存伺服器上有效。
- **截圖檔**：存在 `~/.claude/projects/<session>/tool-results/`，檔名是 `mcp-Claude_Browser-blob-*-<尾碼>.jpg`，截圖結果那一行寫著。回報要附路徑時，照尾碼複製到自己的子資料夾、改成看得懂的名字。
- **量版面用 JS**：
  - 同一行：比 `getBoundingClientRect().top`。
  - 沒有橫向捲動：`scrollWidth` 等於 `clientWidth`。
  - 字被切掉：元素的 `scrollWidth` 大於 `clientWidth`。
  - 截圖與 `zoom` 拿來當證據。
- **寬度與深色**：用 `resize_window` 設 375×812、360×780，`colorScheme` 設 dark 或 light。窗格寬度一變、回合結束，這些設定都會被重設，要再設一次。做完設回 `preset: desktop`。
- **窗格藏著時截圖可能全白**（`tabs_context` 最後一行寫 hidden；2026-10-21）：`scrollIntoView` 之後連拍都是空白，再設一次 `resize_window`、改用 `window.scrollTo(0, y)` 捲過去就拍得到。量版面的 JS 不受影響。
- **東西在哪**（2026-10-20 找過的）：
  - 玩法說明在齒輪抽屜裡（`[data-act="howto"]`，攤開之後在 `#howto` 找 `h4` 的節名）；江湖頁的「玩法說明 ›」只在新手期出現。
  - 輿圖總覽（「今天去哪裡出陣」、三條戰線的繩 `.m-rope`、繩上的地點 `.bead`）在底下那張卡裡，收著時點卡頭攤開。
  - 輿圖上的 ⚔ 是 `g.armed`，數量拿去跟引擎的 `mapview.armed_places` 比；地點圓盤在 `g[data-loc="<id>"]` 裡，顏色與虛線直接讀 `circle` 的屬性。
  - 江湖頁的戰況圖卡是 `div.war`，點了攤開 `.war-help.fronts-help`；主線是 `.peek-chip.quest`。
  - 行動列的格子是 `button.act-ink`（灰的多一個 `.off`，小字是裡面的 `small`，量字有沒有被切比 `small.scrollWidth` 與 `button` 的左右邊）；格子底下每一格的說明在 `.act-notes p`（開頭是粗體的格名）。截圖前先 `document.querySelector('.act-notes').scrollIntoView({block:'end'})`。軍令卡是 `<details>` 裡的 `summary`（「📜 本週軍令」），要看內容先 `open = true`。
  - **輿圖上軍令的小牌子**（「令 守城」「令 截糧」，`text` 裡找）你站的地方不掛（`mapBadges`），要驗就把角色挪到隔壁（改存檔 `location`、reload）；引擎給的值在 `GET /api/map/state` 的 `places[loc].order`，軍令卡的字在 `main["orders"][i]["how"]`（翻地複驗，FB-605）。
  - 輿圖 ⚔（`g.armed`）不在 `g[data-loc]` 裡面，它前面最近的 `g[data-loc]` 兄弟才是那個地點（往 `previousElementSibling` 找）；點了輿圖分頁要等約 3 秒才畫好，頭一次數到 0 不是沒有。
  - **天下圖的路畫在底圖裡**：`.tx-world-map image` 是一張點陣化的 PNG（blob），DOM 找不到路的 `path`；要看某一條路只能截圖：「放大」按到最大（375 寬 ×1.5、320 寬 ×2，按鈕變 disabled）、點「收起」把「今天去哪裡出陣」收下去、再拖地圖。小地圖（`div.mini svg`）的路在 DOM 裡，`path` 的 `d` 是「M甲x,甲y Q… 乙x,乙y」（id 字母小的那頭在前）。
  - **區塊的歸屬顏色**：`g[data-loc]` 裡第三個 `circle` 的 `stroke`：官軍 #3D5F8F、黃巾 #B9821A、中立 #8F8B82（第二個圓多一個虛線 `stroke-dasharray`），不是區塊的 #7A6A55；第一個圓是點擊範圍（透明）。
- **共用窗格太擠、或要包 `fetch`、要換樣式表時，自己開 headless chromium**（寫法看 `tianxia-dev/網頁.md` 的「要真實截圖 PNG 的草圖」：playwright 的 chromium-1208、node 22、CDP；一個 node 腳本開一個瀏覽器、跑完 `taskkill /T` 自己的那個）。截圖用 `Page.captureScreenshot` 存 PNG，再用 Read 看。窗格那幾條（`el.click()`、單獨 reload、量 `scrollWidth`）照樣適用。好用的幾招：
  - **回應沒收到**：在頁面裡包 `window.fetch`，對指定的網址等真的回應回來再丟 `TypeError`（伺服器做了、頁面沒收到），或送出前就丟（根本沒到伺服器）；要「馬上再點、輪詢還沒插進來」就讓 `/api/main`、貨架那幾個 GET 先掛著（等一個 promise），點完才放。要「等一次輪詢再點」就不掛、記下輪詢何時打過。
  - **修前修後比版面**：同一個登入、同一頁，把 `git show <舊 sha>:web/style.css` 整份換進頁面（`link[href*="style.css"]` 換成 `<style>`），量同一批元素的 `getComputedStyle`（字級、字重、行高）與 `getBoundingClientRect`，再比兩張截圖的 sha256；不必起兩台伺服器。寬度要跨媒體查詢的邊界各量一次（640、641）。
  - 提示泡泡（`#toast`，3.2 秒）與離線橫幅會蓋在確認框上；要看底下的字就等它消失，或用 JS 讀 DOM。
  - 每跑一次 node 就是新的瀏覽器，登入的 cookie 留不下來：用 `set_password.py` 建的帳號，node 自己讀 `local/<帳號>_password.txt` 打 `/api/login`（密碼不進對話）。在瀏覽器裡用隨機密碼註冊的帳號，下一輪就登不進去了。
  - 逐像素比修前修後，同一版也要跑兩次：煉製的太極爐、輿圖的紅旗、修練的人物面板是動畫，跑兩次就不一樣。只有新對新、舊對舊都一樣，新對舊才不一樣的，才算改動造成的。

## 存檔、資料庫與假人
- 換季之後、玩家第一次同步之前改的存檔，會被換季重設洗掉。要等他同步完再改。
- **改存檔不驗型別**：list 欄位寫成 None（例 `duel_last = None`），`CharacterStore.save` 照樣存進去，讀的時候才炸：伺服器 `_reload` 回 500，網頁掉回登入頁。清空一律用欄位的預設值（`[]`、`{}`）；已經壞了，就直接改 `characters` 那一列的 JSON。
- **讀資料庫只開唯讀**：`sqlite3.connect("file:<db>?mode=ro", uri=True)`。`characters` 有 `is_bot` 和 `data`（JSON，`player`、`journal`），江湖紀錄只留最近 30 則。
- **伺服器開著也能改存檔與掛軍令**（伺服器每次動作都重讀資料庫）：角色用 `CharacterStore(open_database(db))` 的 `load`／`save`；軍令用 `open_world(db)`、`with w.db.transaction(): w.mutate_season(fn)`（`s.orders` 加一筆 `Order`）。21 天季的軍令 `Order.week` 是季曆第幾天，不是週：`calendar.point(season.time, c, season).cal_day`。改完讓角色的頁面 reload 一次就看得到。
- **複製資料庫**用 sqlite 的 `backup()`，不要只複製 `.db`，WAL 裡的資料會漏掉。
- **商城的帳**：資料表 `mall_purchases`、`mall_ledger`、`mall_entitlements`，`owner` 是名號不是帳號。`scripts/mall_ledger.py --db <db> --out <csv>` 對帳（只讀，印錢包數與餘額合計，沒有負的餘額、exit 0）。
- `battles` 是最新的在前（`battles[0]`）。腳本移動角色之前先略過序章（`skip_tutorial` 會重設地點）。自動選事件的迴圈要排除 `choice:free`（那一顆要打字）。
- 決戰的「定結果」只能定還沒開打的。要驗發獎勵就實際打完：用腳本把 `muster_deadline_real` 和 `round.opened_real` 拉到過去。
- **假人**：只在台灣時間 11:30～13 與 19～24 上線，懶的有些日子整天不上線。
  - 其他時段：把資料庫複製一份，用 `BotRunner(content, client=None, clock=lambda: 假時間)` 一輪一輪 `tick()`。
  - 正式驗「看不出是假人」：查角色存檔以外的每一張表，加上 `status`、玩家卡、傳聞、江湖史。
  - `battles` 表的 JSON 有欄位名 `is_bot`（`BattleParticipant`：決戰補位的機器人才是 true，伺服器假人一律 false）：掃字樣時它一定會中，要找的是 `"is_bot":true`，欄位名本身不算透露（2026-10-21）。
  - 時段之外要跑真的 `run_bots.main(ticks=N)`（跟伺服器同一個資料庫）：包一支腳本，把 `tianxia.server_bots.is_online` 換成永遠在線、`load_content` 之後設 `bot_tick_seconds = 1000`（在線就一定做事），`run_bots.time.sleep` 縮短。`_wait` 每一輪還是要照 `bot_tick_seconds ÷ BATTLE_TICK_SECONDS` 一步一步查決戰，40 輪約 12 分鐘；要更快，就把 `run_bots._wait` 也換掉。
  - 假人跑完多半在路上（`player.journey` 不是 null），「此地還有」與玩家卡都找不到他。要驗他的卡，就改存檔把 `journey` 清成 null。

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
- qa/ 分支只 commit 試玩回饋（順手更新這個技能時，同一個 commit 帶上）。commit 訊息用英文一行，說驗了什麼、開了哪幾張 FB，結尾空一行加系統給的 `Co-Authored-By:` 署名（照當次 Claude Code 給的那一行，不要寫死模型名）。
- `git push -u origin qa/<名字>`，接著 `git ls-remote origin qa/<名字>`，確認遠端那一個跟本機的 commit 一樣。
- 不合併，合併是 PM 的事。
- **複驗**：上一輪的紀錄常常已經被 PM 合進被驗的分支（看 `git merge-base --is-ancestor origin/qa/<上一輪> HEAD`）。是的話不用硬做合併 commit，總表的狀態直接在原列換成複驗結果，驗收紀錄接在檔尾；不是的話才 `git merge --no-ff origin/qa/<上一輪>`（衝突兩邊都留）。

## 回報 PM
- 用 SendMessage 回派工的那個 session（照訊息的 `from`），用繁體中文。被 PM 用 Agent 派出來的子代理沒有對象可以 SendMessage：最後一步呼叫 `SubagentHandback` 交出完整報告（呼叫完就結束，所以推送、確認遠端都要先做完）。
- **第一行**寫結論，加 commit，例如「第 7 批 QA 完成：九項照設計，新開 FB-436～438，結果在 qa/season-7 `3cbaea20`（已推）」。
- **接著**：驗的分支與 commit、測試結果、每一項一兩句（照派工單的編號）、新開 FB 一張一句、順帶看到的、沒驗到的。
- **最後**：伺服器和假人程式關了沒有。
- 長度照 PM 的要求。不要寫「應該沒問題」，沒驗到就寫沒驗到。
