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
- **不重跑開發跑過的測試**（〈開發規範手冊〉4.2，企劃者 2026-10-30）：QA 只在實機上驗畫面與手感，只能靠引擎驗的照 `引擎驗收.md` 寫腳本驗；開發的回報寫了跑過哪些測試，就不再跑一次。學到的寫在回報的「學到的」一節，不改技能檔（手冊第十節，PM 收）。派工單點名要跑的才跑。
- **測試只跑派工單點名的檔**：`<python> -m pytest -q -m "slow or not slow" tests/a.py tests/b.py`。不跑整套；派工單沒點名就不跑（開發跑過的不重跑）。
- **兩版對照（BASE 對 HEAD）的局面要凍得住**（2026-10-31 第 1 階 QA）：week7 的管理者「繼續」會把季曆對回現實的日子，暫停凍不住時刻；管理者快轉時時刻表事件的成敗用沒種子的亂數，每次跑都不一樣。比較點放在快轉之前，時刻先換成記號再比。逐鏡記「看得到的元素的位置＋算好的樣式」再 diff，比只比像素好分辨是字還是版面真的動了。
- 無頭 Chromium 開 mobile 模擬時，CDP `Input.dispatchMouseEvent` 照樣點得到按鈕、`mouseWheel` 捲得動；點之前 `scrollIntoView({block:'center'})`，再用 `elementFromPoint` 確認點到的是那個元素（2026-10-31）。
- 不開多代理工作流程，也不要一個驗收項目開一個子代理。
- **在隔離的工作樹裡**（PM 用 Agent 派的子代理）：Bash 工具會擋帶中文路徑的 python（`C:/Ray/專案/…/python.exe`），python 一律從 PowerShell 跑，git 照樣用 Bash。PowerShell 傳 JSON 參數會壞：把 JSON 寫進腳本，或讓腳本收一般參數。
  Bash 也會擋「`cd` 到工作樹外面」或太複雜的指令（heredoc 加管線、`od` 之類，回「too complex to verify that it stays inside the worktree」）：小腳本用 Write 寫進 scratchpad、用絕對路徑跑（系統的 `python` 可以），git 一律 `git -C <自己的工作樹>`。
  - Bash 也會拒絕「看不出會不會碰到別的工作樹」的複雜指令（遇到過的：`cd` 到工作樹外面的資料夾、拿 shell 變數組出別的資料夾的路徑、awk、在 Bash 裡再叫 powershell）。腳本一律用 Write 寫成檔，再從 Bash 跑 `python3 <絕對路徑>`（系統的 python 3.14 有 requests，打 API 與唯讀讀資料庫夠用），不 `cd`、路徑寫絕對的；node 與 venv 的 python 從 PowerShell 跑。
  - Git Bash 會改參數：`rev:path`（`git show origin/develop:.claude/…`）被當成路徑清單、開頭是 `/` 的（`/api/mall/buy`）變成 `C:/Program Files/Git/api/…`。拿舊版的檔用 `git archive <sha> <檔…> -o x.tar` 再 `tar --force-local -x`；打 API 的腳本收不帶斜線的路徑。`cmd /c` 會吃掉 `^`（`8be1a6eb^1` 拿到的是別的版本），先在 PowerShell `git rev-parse` 成完整的 sha。
  - Write 寫的 `.ps1` 是沒有 BOM 的 UTF-8，PowerShell 5.1 當 ANSI 讀、中文整個壞掉：寫完用 `[IO.File]::WriteAllText(檔, 內容, (New-Object Text.UTF8Encoding($true)))` 補 BOM。
  - 長跑的 node／python 不要接 `| Select-Object -First N`：拿到 N 行 PowerShell 就收掉行程（exit 255），`finally` 裡關 chromium 那一段不會跑。輸出導進檔案再讀。
- **PowerShell 腳本檔（`.ps1`）不要寫中文路徑**（2026-10-20 領地爭奪複驗，一整輪空跑）：Write 工具寫的檔沒有 BOM，PowerShell 5.1 當 ANSI 讀，`$PY` 變成亂碼、回「The term … is not recognized」，錯誤落在工作輸出、不在導向的 log 裡，檔案一個都沒生出來。python 指令直接寫在 PowerShell 工具的呼叫裡（路徑照常寫中文），`.ps1` 只放 ASCII 路徑；要跑好幾次就在同一個呼叫裡寫 `foreach`。
- **PowerShell 5.1 叫原生程式的參數**（2026-10-22 輿圖第 4 批複驗）：空字串參數會被吞掉（profile 要空字串就傳 `default`，腳本裡再換成 `""`）、JSON 的引號被吃掉（傳 `str:值` 讓腳本自己解）；輸出檔名用 ASCII，中文檔名經 PowerShell 傳給 python 會變亂碼；`Remove-Item <scratchpad>\資料夾\*` 帶萬用字元會被擋（protected path），要換一批資料就開新的資料夾或檔名。
- **git 一個指令一個指令跑**：`W=…; git -C "$W" … | …; git -C "$W" …` 這種變數加管線加好幾個 git 串在同一行，會被擋（too complex）。拆成單一的 `git -C <絕對路徑> …`；要 grep 輸出就先 `> scratchpad 的檔`，再另一個指令 grep。
- **兩份複本對照要平行跑**：PowerShell `Start-Process -FilePath <python> -ArgumentList '-u','-I',<腳本> -RedirectStandardOutput <檔> -RedirectStandardError <檔> -WindowStyle Hidden -PassThru`，各設自己的 `QA_ROOT`；不加 `-u` 的話輸出要等跑完才寫進檔，看不到進度。
- **scratchpad 跟同一個 PM 派出的其他子代理共用**（2026-10-20 在 `shots/` 看到別人的檔）：自己的複本、資料庫、截圖，都放在用這次驗收命名的子資料夾。
  - **子資料夾別取開發分支的名字**（2026-10-21 小單：`small1021b` 裡已經躺著開發的人留下的 `repro635.py`、`mutate.py`）：取 `qa<名字>`。
  - **`python -I` 會忽略 `PYTHONIOENCODING`**：腳本自己 `sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")`，不然印中文在 cp950 噴 `UnicodeEncodeError`、整支腳本中途死掉（輸出檔寫到一半）。
  - **PowerShell 的 `Remove-Item <資料夾>\*` 會被擋成「protected path」**：換一個新資料夾／新檔名，或用 Python `shutil.rmtree`。
- **Git Bash 的 tar 把 `C:/…` 當成遠端主機**（回「Cannot connect to C: resolve failed」，2026-10-21 輿圖第三版第 2 批）：先 `git -C <工作樹> archive -o <scratchpad>/x.tar <sha>`，再 `tar --force-local -x -f <tar> -C <資料夾>`。
- **隔離工作樹裡 Bash 也擋這幾種**（2026-10-21 玉璽碎片複驗）：`SP=…` 變數加 `git archive` 加 `tar` 串在同一行、`python <<EOF` 的 heredoc、`python -I x.py` 帶中文 scratchpad 路徑的 Bash。做法：`git -C <工作樹> archive -o <絕對路徑>.tar <sha>` 一個指令一次（路徑寫死、不用變數）；解壓與批次修補檔都用 Write 工具寫成 `.py`（解壓用 `tarfile`，讀自己所在資料夾的 `*.tar`）再從 PowerShell `python -I` 跑；要平行跑一排腳本，在 PowerShell 同一個呼叫裡 `Start-Process` 一排再 `Wait-Process`（輸出導到各自的 `.txt/.out/.err`，`.err` 有東西才看）。
- **子代理的 Bash 連 tar 都擋**（「computed value」，2026-10-21 翻地複驗）：`git archive -o` 之後用 Python `tarfile`（`untar.py`：`extractall` 時排除 `docs/`、`.claude/`）解；PowerShell 的 tar 解 `docs/` 底下的中文檔名會回 `Invalid empty pathname`，code 檔其實也沒解完。
- **PowerShell 呼叫原生程式時空字串參數會被吞掉**（2026-10-22 長社火攻，`scen.py` 的「翻哪幾塊」空著、後面的參數往前補位）：腳本的選用參數用 `-` 當「沒有」，腳本裡自己轉回空的。
- **PowerShell 5.1 的 `Get-Date -UFormat %s` 把本地時間當成 UTC 算，快 8 小時**（2026-10-22 上線預演：拿它當「現在」給建存檔的腳本，整份存檔跑到 8 小時之後，只好重來）：現實的 epoch 用 `[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()` 或 python `time.time()`。
- **`.ps1` 要比對 ⚠ 就寫 `[char]0x26a0`**（2026-10-22 上線預演）：檔裡一出現 ⚠ 這種非 ASCII 字，PowerShell 5.1 當 ANSI 讀壞，回「The string is missing the terminator」、整支沒跑。
- **清暫存別讓萃取的腳本被一起刪掉**（同上）：`Remove-Item …\cmp_*` 把自己放在同一個資料夾、同樣叫 `cmp_front.py` 的腳本刪了，六個行程開不起來，錯誤只在 `.err`。複製來的腳本改一個不會被通配吃掉的名字。
- **PowerShell 工具有時把 `taskkill /PID` 的 `/PID` 當成 `Remove-Item` 的路徑擋掉**（回「Remove-Item on system path '/PID' is blocked」，2026-10-22 複驗，同一支腳本前一輪照跑）：同一個呼叫裡清檔用 `Get-ChildItem <資料夾> -Filter … | Remove-Item`、關行程用 `Stop-Process -Id`（自己開的單一行程）。
- **複驗時對方改了字，先確認自己認句子的正規式也跟著改**（2026-10-22 長社火攻複驗：`play.py` 找「戰局起點照」，新句子變成「起點偏…戰況」，認不到時輸出是 `sentence=n`、看起來像「沒有那一句」）：先拿一個一定有的局面印一次，看認不認得到，再跑整批。
- **`python -I` 連 `PYTHONHASHSEED` 一起忽略**（`-I` 含 `-E`）：要靠 `PYTHONHASHSEED=0` 逐位元組比的腳本（開發的 `cmp_front.py`）不要加 `-I`，加了集合的排列每個行程都不一樣。
- **`Start-Process -ArgumentList` 的陣列元素有空格要自己加引號**：`-m "slow or not slow"` 寫成 `'"slow or not slow"'`；沒加就被拆成四個參數，pytest 回「no tests ran in 3s」、一個測試都沒跑（2026-10-21）。
- **平行驗收**（2026-10-20）：PM 會給你一段 FB 號段、一個埠和一個 `<名字>.localhost`，只用給你的；瀏覽器窗格是共用的，**每一個動作都帶自己的 tabId**（10/20 有 QA 沒帶，動到別的子代理的分頁）。驗完把視窗設回 desktop、配色淺色、關掉自己的分頁、`taskkill /T` 關伺服器。
- 開關的「一個字都不變」最好的驗法：同一支腳本，在功能分支開出來的那一點（`git archive` 解出來）和這一版各跑一次，比輸出。
  - **`python -I` 會連 `PYTHONHASHSEED` 一起不讀**（-I 不看任何 `PYTHON*` 環境變數）：存檔裡的 set（`visited`、`revealed`、`seen_events`）每次順序不同，兩版比起來像有差。比對腳本不加 `-I` 跑（腳本放在只有自己腳本的 scratchpad 子資料夾），再把 `time.time` 換成固定值（2026-10-21 第 4 批 QA）。
  - **`python -I` 會忽略 `PYTHONHASHSEED`**（2026-10-21 玉璽碎片第 3 批）：資料庫轉成文字逐位元組比的時候，集合欄位（`visited`、`revealed`）的順序每跑一次都不同，看起來像兩版不一樣。要逐位元組比就不加 `-I`、設 `PYTHONHASHSEED=0`（腳本自己把複本的根目錄插在 `sys.path` 最前面）；畫面那一份（`main_view` 等）不受影響。
  - 子代理的 PowerShell 刪 scratchpad 裡的檔（`Remove-Item …\*`）會被擋（protected path）：重跑就寫進新的子資料夾。

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
- **`set_password.py` 的帳號只收英文數字底線（3～20 字）**，名號才能是中文；PowerShell 傳中文引數給 python 會變亂碼（2026-10-26 減法季 7b 複驗）：寫一支 python 用 `subprocess.run([py, set_password.py, 帳號, "--character", 名號, ...], env=..., encoding="utf-8")` 一個一個建（範本 `scratchpad/qajf7bb/mkacct.py`），從 PowerShell `python -X utf8` 跑。
- **管理者 `fast_forward {hours}` 推的是世界（季曆）小時**，不是現實小時：week7 開季是第 1 天 06:59，推 7 小時是第 1 天 14:00，再推 81 小時是第 4 天 23:00，再推 1 小時是第 5 天 00:00（剛好第 3 段起點，上架時刻的邊界）。
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
  - 移動是 `POST /api/travel {"place": <地點 id>, "mode": "dash"|"walk"}`，鍵是 `place`（寫成 `to` 回 200 但原地不動、體力不扣；看回傳的 `arrived`）。配點是 `POST /api/do/allocate {"stat": "str"}`。
  - PowerShell 工具的 `Set-Location` 會留到下一次呼叫（跑 `set_password.py` 時 cd 進複本，之後的 `git` 就在複本裡跑）：用完 cd 回自己的工作樹，或 python 一律寫絕對路徑、不 cd。
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
- **時刻表決戰的開法**（2026-10-22 長社火攻）：每一場一季只開得了一次，取消了也不能再開（`showdowns_opened`）——同一季要看第二種佔領就用新的資料庫，或 `end_season`＋`next_season`；`start_showdown` 的 id 是時刻表那一列（`changshe_fire`、`wancheng`、`guangzong`、`tianming`），宛城要第 3 週那件已結算；`tianming` 先 `seal_mandate when=now`（回「蓋上天命之季的章」）否則回「時刻表上沒有這一場決戰」。要驗「時間到了自己開」：`schedule {id, at}` 只會對齊到季曆整點，之後 `fast_forward hours=1` 推過去。排在後面的攻城戰書不會被 `cancel_battle` 一起取消，取消一場後下一場馬上開，連按到「沒有進行中的決戰」。
- **`/api/do/<op>` 先查 `ADMIN_ACTIONS`**：玩家動作跟管理者動作同名時，玩家打到的是管理者那一個（回「只有管理者能這麼做。」）。一批加了新動作，先看一次 `set(server.MAIN_ACTIONS) & set(server.ADMIN_ACTIONS)`，再用玩家帳號真的打一次那個路由（2026-10-21 翻地 QA，FB-609：單元測試只看兩張表各有那個鍵）。
- **實機對照「一個字都不變」**：腳本用 `subprocess.Popen` 在同一個埠輪流起兩份複本的伺服器，各用新的暫存資料庫，只打 API、印要比的欄位；把現實時刻的 `HH:MM` 換掉再 diff，結束時 `taskkill /T`。
- `status` 裡沒有的鍵就是畫面不畫。要確認某個東西在某種季、某種狀態下不出現，直接看 `status` 有沒有那個鍵，再補打一次那個動作，確認什麼都沒動。

## 瀏覽器（in-app）
- 用 `tabs_create` 開分頁，再 `navigate` 到自己的 host。登入用 JS：`await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({login,password})})`，然後另起一次呼叫 `location.reload()`。
- **reload 要單獨一次呼叫**：同一段 JS 裡 reload，後面的程式會被切掉。等約 2 秒之後，再在下一次呼叫裡查畫面。
- 頁面每 10 秒打一次 `/api/main`。用 API 改了狀態之後，等 11 秒或 reload 再看。
- **按鈕用 JS 的 `el.click()`**，座標點擊常常沒反應。
- **換帳號**：同一個分頁重打 `/api/login` 就換掉 cookie，再單獨一次 reload。兩個帳號要同時登著才需要換 host。
  - 分頁用的 `tx_session` 是 `requests` 登入拿的：之後腳本**再登入同一個帳號**（`session(acct)` 打管理者動作、看卡），分頁裡那一個會失效、頁面掉回登入（2026-10-21）。腳本動過那個帳號就重拿一次 token、重寫 cookie、單獨 reload。
- **不把密碼貼進對話**：用 python `requests` 登入、只印 `tx_session`（`s.cookies.get("tx_session")`），再在分頁裡 `document.cookie = "tx_session=<值>; path=/"`、另起一次呼叫 `location.reload()`。換帳號就再取一個值、再寫一次 cookie；這個 token 只在你自己的暫存伺服器上有效。
- **截圖檔**：存在 `~/.claude/projects/<session>/tool-results/`，檔名是 `mcp-Claude_Browser-blob-*-<尾碼>.jpg`，截圖結果那一行寫著。回報要附路徑時，照尾碼複製到自己的子資料夾、改成看得懂的名字。
- **量版面用 JS**：
  - 同一行：比 `getBoundingClientRect().top`。
  - 沒有橫向捲動：`scrollWidth` 等於 `clientWidth`。
  - 字被切掉：元素的 `scrollWidth` 大於 `clientWidth`。
  - 截圖與 `zoom` 拿來當證據。
- **寬度與深色**：用 `resize_window` 設 375×812、360×780，`colorScheme` 設 dark 或 light。窗格寬度一變、回合結束，這些設定都會被重設，要再設一次。做完設回 `preset: desktop`。
- **窗格比模擬的視窗矮時，照截圖點會點歪**（2026-10-26 map-6）：375×812 縮進 800×600 的窗格，截圖是等比縮在左邊，`computer` 的座標卻是把整個截圖框拉伸成 375×812（x×0.469、y×1.353）。先在頁面掛一個 `click` 監聽記 `clientX/Y`、點一下對出比例；截圖框變成 375×812（窗格放大之後）就一對一。點完的截圖常常慢一拍，狀態用 JS 讀。
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
  - **輿圖第三版第 4 批起**（區圖與卡）上面幾條的 ⚔、小牌子、放大縮小、圓盤 `g[data-loc]` 都拿掉了，路也不再烤進點陣（`#map .tx-roads path`）。區圖：名字框 `#mk g.r-label[data-id]`（`rect.r-frame` 的 fill／stroke＝框色、第一個 `text`＝名字、`.r-seal` 寶、`rect.r-bar`／`.r-bar-fill[data-side]` 進度、`text.r-ins` 悟字、`text.r-cool`），小圖 `g.r-icon`，鄰區出口 `g.r-exit[data-id=大區]`，換區是 `select.r-pick` 設 value 再 `dispatchEvent(new Event("change", {bubbles: true}))`，塗層 `.r-wash`，選了的那一圈在 `#msel`；卡在 `#mbody`（`.m-h1`、`.m-line`、`.m-flip`、`.m-yield`、`.m-acts button`）。**天下圖的 `.w-top` 與區圖的 `.r-top` 都在 DOM 裡、藏的那一層在前**：`querySelector('.mapx.region [data-act="map-world"]')` 拿到的是藏起來的那一顆（0×0），要寫 `.r-top [data-act="map-world"]`、`.r-top .w-tl`。
  - **自動點區圖上的地點之前先看 `elementFromPoint`**（2026-10-21 第 4 批 QA 踩到）：半開的卡會蓋住區圖下緣，照名字框的座標點下去點到的是卡上的「疾行」，角色當場被送走、體力扣掉；點之前確認拿到的是 `[data-act="region-place"]`，不是就先按卡的 ✕ 收起來再點。
  - **名字框互壓用開發自己的量法重現最快**：`import test_region_map_web as T`（`sys.path` 加 `tests/`），`T._game(profile=…, at=…)` 之後照要的局面 `conquest.push(...)`，再 `T.run(game, T.OVERLAP.replace("VW", …).replace("VH", …))`；`textW` 是估的、node 與瀏覽器擺出來一樣，幾秒一組，比開瀏覽器量快，修的人也能直接寫成測試。
  - **實機量區圖的互壓，照畫出來的量**（2026-10-22 複驗，FB-651）：開發的 `OVERLAP` 用模型的列（意境字那一列從框的左緣起、高度照字級估），別處的「寶」緊貼意境字這種它量不到；實機讀每一個 `rect.r-frame`、`.r-seal rect`、`text.r-ins` 的 `getBoundingClientRect` 自己算，朱圈照真的圓（`#mkt circle.r-you`：半徑 17×倍率＋線寬一半）量框到圓心最近那一點。翻地前後比位置：同一個帳號、同一個地圖框，先量沒人推、再用引擎 `conquest.push` 推、再量，逐框比 `getBoundingClientRect`。
  - **湊指定的地圖框**（開發的 `PHONES` 是 `#map` 的大小，不是視窗）：讀 `#map` 的 clientWidth／Height，差多少就把視窗高度加減多少再載入一次；狀態列的行數照帳號不同（多一行提示、下一件），同一個 375×812 視窗地圖框有 604／624／651。
- **新加一段字會不會把第一屏擠爆**（2026-10-22 長社火攻，FB-685）：同一份程式、開關關著當對照，量 `#page > .act-bar`（閒著）或 `#page > .options > :last-child`（決戰回合）的下緣對 `.tabs` 的頂；`fitFirstScreen` 的 `fitClip` 對「句尾是數字」的句子不收（`fitDigitsShown`），所以尾巴是數字的長句永遠佔滿行數。截兩張同一視窗的 viewport 並排最看得出哪顆鈕被蓋住。
  - JS 範本字串（反引號）裡的 `\b` 是退格字元、不是字界：在 `Runtime.evaluate` 的字串裡找英文字用 `(^|[^a-z])bot([^a-z]|$)`。
- **共用窗格太擠、或要包 `fetch`、要換樣式表時，自己開 headless chromium**（寫法看 `tianxia-dev/網頁.md` 的「要真實截圖 PNG 的草圖」：playwright 的 chromium-1208、node 22、CDP；一個 node 腳本開一個瀏覽器、跑完 `taskkill /T` 自己的那個）。截圖用 `Page.captureScreenshot` 存 PNG，再用 Read 看。窗格那幾條（`el.click()`、單獨 reload、量 `scrollWidth`）照樣適用。好用的幾招：
  - **回應沒收到**：在頁面裡包 `window.fetch`，對指定的網址等真的回應回來再丟 `TypeError`（伺服器做了、頁面沒收到），或送出前就丟（根本沒到伺服器）；要「馬上再點、輪詢還沒插進來」就讓 `/api/main`、貨架那幾個 GET 先掛著（等一個 promise），點完才放。要「等一次輪詢再點」就不掛、記下輪詢何時打過。
  - **修前修後比版面**：同一個登入、同一頁，把 `git show <舊 sha>:web/style.css` 整份換進頁面（`link[href*="style.css"]` 換成 `<style>`），量同一批元素的 `getComputedStyle`（字級、字重、行高）與 `getBoundingClientRect`，再比兩張截圖的 sha256；不必起兩台伺服器。寬度要跨媒體查詢的邊界各量一次（640、641）。
  - **換整份 `app.js` 看舊版的畫法**：CDP `Fetch.enable({patterns: [{urlPattern: "*/app.js*", requestStage: "Request"}]})`，收到 `Fetch.requestPaused` 就 `Fetch.fulfillRequest`（200、`application/javascript`、body 是舊版檔案的 base64），同一台伺服器、同一個登入就能比修前修後的區圖（2026-10-22 用來確認 FB-651 第 4 批就有）。
  - `clickSel` 拿的是第一個符合的元素：先確認它的框不是 0×0（藏起來的那一層在前，見上面 `.r-top`），不然點到別的東西、什麼都沒發生。
  - 提示泡泡（`#toast`，3.2 秒）與離線橫幅會蓋在確認框上；要看底下的字就等它消失，或用 JS 讀 DOM。
  - 每跑一次 node 就是新的瀏覽器，登入的 cookie 留不下來：用 `set_password.py` 建的帳號，node 自己讀 `local/<帳號>_password.txt` 打 `/api/login`（密碼不進對話）。在瀏覽器裡用隨機密碼註冊的帳號，下一輪就登不進去了。
  - **平行開好幾個無頭 Chromium 時，偵錯埠照帳號寫死、不要隨機挑**（2026-10-22 輿圖第 5 批 QA）：七支腳本各挑 `9200＋亂數` 撞到同一個埠，第二支連到第一支的瀏覽器、共用 cookie，量到的其實是另一個帳號（看起來像「名字挪了」）。寫死之後重跑就沒了；量到怪的先看那一份的「你」在哪。
  - 逐像素比修前修後，同一版也要跑兩次：煉製的太極爐、輿圖的紅旗、修練的人物面板是動畫，跑兩次就不一樣。只有新對新、舊對舊都一樣，新對舊才不一樣的，才算改動造成的。
  - **改版面的修前修後：兩份複本、同埠輪流起、同一個資料庫**（2026-10-21 FB-663／664）：`git archive -o <檔>.tar <sha> tianxia content web server.py server_push.py zhuan_html.py llm_queue.py console.py scripts run_bots.py`（只要這幾樣；解 `docs/`、`.claude/` 的中文檔名會壞），修前、修後各一份，`content/config.json` 只在複本裡加 `ollama_url`；用 Python `tarfile` 解、用 `filecmp` 逐檔比（只該差 `web/app.js`、`web/style.css`：伺服器端一個位元組都一樣，兩邊的 `/api/main` 就一樣，差的只會是網頁怎麼畫）。解出來的檔是 CRLF（autocrlf），拿它的 hash 去對 `git show <sha>:<檔>` 要先 `tr -d '\r'`。
  - **一個 node 迴圈掃全部地點**：`node:sqlite`（node 22.23 不必加旗標，要 `node --no-warnings`）`new DatabaseSync(<db>)`、`PRAGMA busy_timeout=30000`，`UPDATE characters SET data = json_set(data, '$.player.location', ?, '$.player.journey', json('null'), '$.player.stamina', 250) WHERE name = ?`，改完 `page.goto` 重載、抓 `.act-bar` 的 `outerHTML` 與 `.act-notes` 的 `innerHTML`、每一格小字的 Range 矩形對格子矩形；43 個地點約 2.5 分鐘。修前一份、修後一份，Python 逐地點比 HTML：不一樣的地點應該只差要改的那一格（這次是 21 處交友灰格，其餘 22 處逐字一樣）。陣營改 `characters.faction` 與 `$.player.faction` 兩處。
  - **序章的畫面要同時清 `$.pending_event`**：只改 `$.player.tutorial_step` 不夠，新人還掛著開場事件（遇險那三個選項），江湖頁只畫那三顆、行動列根本不畫，量到的全是空的。步驟 0～10 的行動列（草廬）、11～14（初入江湖）都要 `'$.pending_event', json('null')` 加 `tutorial_step`；`m.prologue.reveal`／`m.onboard` 看得出現在是哪一段。
  - **「點了之後捲到哪」要等 2 秒以上再量，而且要找得到壞掉的版面**：`scrollIntoView({block:'nearest'})` 只在卡的底緣落在「視窗內、分頁列底下」那一條 56px 帶時才不捲；自然底緣（`scrollY` 0 時的位置）超出視窗的版面，修前也捲得對，量不出毛病。要重現就把視窗高度掃過那一帶（卡的自然底緣 y0，高度 H 落在 y0 到 y0+56 之間；375 寬、按掉師父那張「知道了」之後，潁川郡探索卡 y0 約 838）。量法：`.tabs` 的 top、`#top`（狀態列）的 bottom、卡與最後一顆鈕的矩形，再用 `document.elementFromPoint` 點最後一顆鈕的中心與底緣上 3px，真的點到那顆鈕才算沒被蓋住。「師父說過」那張卡的「知道了」是存在伺服器（`guide_ack`）的：按一次，那個角色以後的江湖頁就一直短一截，同一個角色修前修後要在同一種狀態下比（或另建一個角色專門量按掉之後）。
  - **Monitor 的 until 迴圈不要每圈印一行**：每一行都是一則通知（印進度的迴圈洗了十幾則）。等檔案出現就 `for i in $(seq 1 N); do [ -f <檔> ] && break; sleep 4; done; ls <檔>` 結尾只印一次；Bash 前台的 `timeout N bash -c` 與 `sleep` 一樣被擋。
  - **等背景的 node／python 跑完**：PowerShell 先 `Get-CimInstance Win32_Process -Filter "Name='node.exe'"` 照命令列找出 PID，再 `Wait-Process -Id <pid> -Timeout 170`（Start-Sleep 與 Bash 的 sleep 都被擋，Wait-Process 不被擋，一個呼叫最多撐 170 秒左右、不夠就再呼叫一次）。一輪量測最好一個腳本跑完一整批（一個瀏覽器掃全部地點、全部視窗高度），不要一個情況開一個瀏覽器：後者每個約 10 秒、27 個情況要 5 分鐘。
  - **新測試對修前的程式有沒有牙**：`git archive -o tests.tar <修後 sha> tests pyproject.toml`，`shutil.copytree` 修前複本再把 tar 解進去，在那裡跑新測試檔。抓行為的測試（這次的 `test_fb664_*`）會失敗，只驗新函式的測試（`test_fb663_*` 切 `REVEAL_GAP`）會因為「找不到 const」整個失敗、說明不了行為，行為的證據要靠實機。
  - **CDP 送觸控與滾輪的坑**（2026-10-22 輿圖拖縮 QA）：`Input.dispatchTouchEvent` 的 `touchMove` 少列一指**不會**放開那一指（照舊按著、變成兩指捏）；要「放開一指、另一指接著拖」就送 `touchEnd`、`touchPoints` 只列要放開的那一指，其餘照舊按著。`Emulation.setDeviceMetricsOverride` 兩倍像素（手機）時 `mouseWheel` 的 `deltaY` 到頁面只剩一半（60 → 30），算縮放倍率要照頁面收到的值。驗「跟著手指走」「以中點為中心」之前先算內容框對可見區還有沒有空隙：夾邊會合法地吃掉位移（1 倍區圖往上、放大後貼邊），先放大到四邊都有空隙再量；點東西之前先 `elementFromPoint`（放大後名字框可能跑到分頁列底下，點到的是分頁）。同一個帳號在兩個無頭瀏覽器同時登入會互相踢掉，量測腳本照順序跑。
  - **常駐擺位小幫手 + node CDP 掃全部地點 × 身分 × 寬度**（2026-10-22 練功入口，258 次量測約 11 分鐘）：node 用 `child_process.spawn` 起一個常駐的 venv python 小幫手（從 stdin 一行一個 JSON `{name, loc, faction, stamina, tutorial_step, set, state}`，`import server` 之後用 `open_characters().load/save` 改存檔、印一行 ok；`state` 設 `GameState` 的欄位，例 `pending_event: null`），比每個場景開一個 python 快得多（不必 `node:sqlite` 寫 JSON 路徑）。一個場景＝擺位、導覽、等 `.act-bar`、依序 `Emulation.setDeviceMetricsOverride` 換寬度（不必重載，CSS 重排就好）、跑一段量測 JS 回傳每格的 `b`／`small` Range 寬與格子內寬（`clientWidth` 扣 padding）、被切的旗標、`document.documentElement.scrollWidth` 對 `innerWidth`、`.act-notes p` 的 `scrollWidth`；結果寫成 JSON，再用 Python 總結「每種小字出現幾次、最寬幾 px、有幾個被切」。注意：`*.localhost` 只有 Chromium 認得，系統 Python 的 `requests` 解不出來（回 `getaddrinfo failed`）：打 API 的腳本一律用 `127.0.0.1:<埠>`（cookie 不跨用，各自登入），瀏覽器才用 `<名字>.localhost`。
  - **同一支腳本跑不同的季＝不同的設定檔 + 不同的複本**：`TIANXIA_PROFILE`（`week7`、`weekend`、`season21`、空字串＝14 天）各一個暫存資料庫、各一組 `set_password.py` 帳號；`.ps1` 傳空字串引數會被吃掉，用 `default` 這種記號再在腳本裡換回空字串；`"-"` 也不行（被當成參數名）。要驗的開關不在設定檔切得到時，另解一份複本、只改複本的 `content/config.json`（在最上面加一行，例 `{"precise_actions": false,` 或把 `"conquest": {"enabled": false}` 換成 true；領地爭奪開著才有「出陣（不在爭奪之列）」，一類一顆關著才有四格行動列）。新舊對照：兩份複本各跑一次，比量測 JSON（格子鍵、文字、寬高、底下每一行的文字）與伺服器掃描（`/api/main` 的選項標籤、`action_notes`）。
  - **PowerShell 的 `| Select-Object -First N` 也會砍掉子行程**：`& powershell -File start_variant.ps1 ... | Select-Object -First 3` 拿到 3 行就把整串（包括後面要跑的 node）收掉、exit 255，工作被標成 failed、但伺服器（`Start-Process` 起的）還活著。要截輸出就導進檔案再讀。前台最多 600 秒，再久的（變體整輪約 5～10 分鐘）一律 `Start-Process powershell -File` 丟背景、`Wait-Process -Timeout` 等。

## 存檔、資料庫與假人
- 換季之後、玩家第一次同步之前改的存檔，會被換季重設洗掉。要等他同步完再改。
- **在路上做「擋路」（`travel_block`）**：`player.picking_*` 旗標同步時會被收掉；改 `GameState.pending_event = <任何事件 id>`（`state` 那一層，不是 player）就會擋，畫面寫「先回江湖頁處理「事件名」」，驗完設回 None（2026-10-22，FB-649 複驗）。
- **改存檔不驗型別**：list 欄位寫成 None（例 `duel_last = None`），`CharacterStore.save` 照樣存進去，讀的時候才炸：伺服器 `_reload` 回 500，網頁掉回登入頁。清空一律用欄位的預設值（`[]`、`{}`）；已經壞了，就直接改 `characters` 那一列的 JSON。
- **讀資料庫只開唯讀**：`sqlite3.connect("file:<db>?mode=ro", uri=True)`。`characters` 有 `is_bot` 和 `data`（JSON，`player`、`journal`），江湖紀錄只留最近 30 則。
- **伺服器開著也能改存檔與掛軍令**（伺服器每次動作都重讀資料庫）：角色用 `CharacterStore(open_database(db))` 的 `load`／`save`；軍令用 `open_world(db)`、`with w.db.transaction(): w.mutate_season(fn)`（`s.orders` 加一筆 `Order`）。21 天季的軍令 `Order.week` 是季曆第幾天，不是週：`calendar.point(season.time, c, season).cal_day`。改完讓角色的頁面 reload 一次就看得到。
- **籌備中管理者動作都不能用**（`seal_assign` 回「賽季沒有在進行，無法觸發」，2026-10-21）：要驗籌備中的碎片卡，登記上直接給：`open_world(db)`、`w.mutate(lambda st: …)`，`s = seal.filled(st.seal, c).shards[片 id]; s.state, s.holder, s.since_season = "held", 名號, 0`（伺服器開著也能改）。
- **在預覽行程裡關掉模型**（不改複本的檔）：包一支 `serve.py`，`import server` 之後 `server.CONTENT.config.ollama_url = "http://127.0.0.1:9"` 再 `server.main(["--port", …])`；領地爭奪沒有開關（2026-10-27），用 week7 或 season21 設定開就是。`Start-Process` 回的 PID 是 venv 的 launcher，底下還有子行程，`taskkill /PID <回傳的> /T /F` 一次關乾淨，再用 `netstat` 確認埠沒人聽。
- **湊「每一塊都灰」**：鎮地要全部冷卻——對每一塊搶得下來的區塊 `conquest._fight(s, c, loc).flipped_at = s.time`（`w.mutate_season`，31 塊；伺服器開著也能改）；補缺要「這一季補過一次、隔 3 天、又被翻走」——管理者 `conquest_progress` 定到 100 翻、`seal_use` 補、`fast_forward 73` 小時、再定到 100 翻；再翻一塊並 `admin_conquest_letter` 讓它進集結，就是兩列各寫一種原因。快轉 73 小時會碰到長社火攻，不礙事。
- **複製資料庫**用 sqlite 的 `backup()`，不要只複製 `.db`，WAL 裡的資料會漏掉。
- **商城的帳**：資料表 `mall_purchases`、`mall_ledger`、`mall_entitlements`，`owner` 是名號不是帳號。`scripts/mall_ledger.py --db <db> --out <csv>` 對帳（只讀，印錢包數與餘額合計，沒有負的餘額、exit 0）。
- `battles` 是最新的在前（`battles[0]`）。腳本移動角色之前先略過序章（`skip_tutorial` 會重設地點）。自動選事件的迴圈要排除 `choice:free`（那一顆要打字）。
- 決戰的「定結果」只能定還沒開打的。要驗發獎勵就實際打完：用腳本把 `muster_deadline_real` 和 `round.opened_real` 拉到過去。
- **假人**：只在台灣時間 11:30～13 與 19～24 上線，懶的有些日子整天不上線。
  - 其他時段：把資料庫複製一份，用 `BotRunner(content, client=None, clock=lambda: 假時間)` 一輪一輪 `tick()`。
  - 正式驗「看不出是假人」：查角色存檔以外的每一張表，加上 `status`、玩家卡、傳聞、江湖史。
  - `battles` 表的 JSON 有欄位名 `is_bot`（`BattleParticipant`：決戰補位的機器人才是 true，伺服器假人一律 false）：掃字樣時它一定會中，要找的是 `"is_bot":true`，欄位名本身不算透露（2026-10-21）。
  - 時段之外要跑真的 `run_bots.main(ticks=N)`（跟伺服器同一個資料庫）：包一支腳本，把 `tianxia.server_bots.is_online` 換成永遠在線、`load_content` 之後設 `bot_tick_seconds = 1000`（在線就一定做事），`run_bots.time.sleep` 縮短。`_wait` 每一輪還是要照 `bot_tick_seconds ÷ BATTLE_TICK_SECONDS` 一步一步查決戰，40 輪約 12 分鐘；要更快，就把 `run_bots._wait` 也換掉。
  - 包一層的 `run_bots.main` 把 `time.sleep` 換成 `min(s, nap)` 時，`nap` 用 0.02：`_wait` 每一輪要走 `bot_tick_seconds ÷ BATTLE_TICK_SECONDS` 步，nap 0.5 一輪要 100 秒（2026-10-22 上線預演二，30 輪跑了五分鐘才 1 輪）。真的時鐘下假人在路上要走現實的幾分鐘，40 輪看不到推地；要看假人推地，複製資料庫、`BotRunner` 假時鐘 300 步×60 秒，在 `Game.choose` 外面包一層數 `act:train`（範本 `scratchpad/qa-rel1022b/s/botpush.py`）。
  - 假人跑完多半在路上（`player.journey` 不是 null），「此地還有」與玩家卡都找不到他。要驗他的卡，就改存檔把 `journey` 清成 null。
  - **驗「假人／整季機器人照舊按得到某個選項」**（2026-10-22 練功入口，選項 id 不變）：跟伺服器同一個資料庫（伺服器開著，共用行動鎖）跑一支 venv python：`server_bots.is_online = lambda profile, now: True`、`content.config.bot_tick_seconds = 1000.0`、`bot_fill_seconds = 1.0`，`BotRunner(content, client=None, rng=random.Random(7), clock=lambda: base + i * 40)` 逐輪 `tick()`（假時鐘每輪往前 40 秒，week7 一小時是季曆 12 小時，80 輪才三小時、不會把 7 天季跑完），並把 `Game.choose` 換成先記 `option_id` 再呼叫原本的（數 `explore:practice` 之類）；80 輪約 1 分鐘補到 13 個假人、動 1018 次、0 個 failed。整季機器人：`bot.play_season(content, seed, max_steps=1500, now=time.time())`，`TIANXIA_DB` 指到 repo 外的暫存檔、`load_content(Path("content"), os.environ.get("TIANXIA_PROFILE") or None)`。事後唯讀開資料庫，在假人的 `data.journal` 找練功開打那一句（`找上…練手`）當真的有打的證據；玩家那邊把 `/api/main` 的 JSON 與頁面 DOM（`outerHTML` 拿掉 `<script>`、`innerText`）掃「假人／機器人／bot」，再把角色擺到假人站的地方看「此地還有」。注意 `web/app.js` 的註解也會送到每個玩家的瀏覽器：新加的註解寫了「假人、整季機器人」（舊的一處在「真人假人是同一份名單」）。
  - **做出「已談滿」「頭目冷卻」「頭目次數用完」的畫面**：已談滿＝`server.game_for(名號)` 拿 `Game`，`p.stats["fame"] = 999`、對 `game._figures_here()` 每位呼叫 `game._count_talk(cid)` 共 `game._talk_cap()` 次，`server.open_characters().save(game.state)`（孟津渡單人地點只有董卓）；頭目＝角色擺在只有頭目的地點、`POST api/choose {"id": "explore:practice"}` 再一直按 `duel:*`（`duel:flee` 除外）到選單上沒有為止（約 4 回合；week7 每個頭目一段只打兩場，`per_boss_week` 2）；冷卻是現實 2 小時，管理者 `api/do/fast_forward {"hours": 3}` 清掉、再打第二場，再快轉 3 小時就是「這一段頭目段鐵頭不再現身，第 3 天 00:00 再來」（week7；FB-672 起帶頭目的名字，21 天季「這一週頭目…不再現身」，週末與 14 天「這一季頭目…不再現身」；冷卻中「頭目約 2 小時後才會再現身」不帶名字）。week7 的段界是現實天：跨到第 2 段（第 3 天）要快轉 48、再跨到第 3 段（第 5 天）再 48，快轉 4 只推 4 小時、句子不變。

## 只能靠引擎腳本驗的（寫法看 `引擎驗收.md`）
- **角色存檔不含賽季**（2026-10-26）：腳本裡 `CharacterStore.load(名號).world` 永遠是空的預設值，「全服的東西有沒有送」（`signature_arms`、名將贈禮）要讀 `open_world(db).get_season()`；不然「沒送」的斷言假過。對話要走真伺服器時，開一個假 Ollama（`引擎驗收.md` 第 12 節）。
- 跟開季時刻有關的：伺服器開季用真實時間，例如週三開季。
- 沒有設定檔可切的開關：例如素材四階關掉。
- **機率**：一種跑幾千次，報次數與百分比；也要跑「不該發生」的那幾種，確認是 0。
- 滿級換心得、頭目戰、切磋、決戰軍餉、求援傳聞。
- **不具名（「兩個只差誰做的世界」）要連酒肆一起比**（FB-643）：`tavern_do("ties", 名號)` 打聽交情在打聽度 4 以上會列那個人份量 3 以上的最近三件行狀，`tavern.fresh`（24 小時內有份量 4 的行狀）打聽度 +1、`seek` 的回話跟著變。名望 0 的陣營中人碰不到門檻：把兩人的 `stats["fame"]` 拉到「小有名氣」、看客同陣營站同一間酒肆（`picking_tavern = True`、銀兩給夠），另跑一份兩人是散人（沒有「投靠」那一筆行狀蓋過 `fresh`）。
  - **旁觀客只站同一間酒肆是不夠的，沒有牙**（2026-10-21 FB-643 複驗：同一間酒肆查人本來就問得確切，託酒家留意根本沒託成，修前修後都過）：另放旁觀客在別的城（`yingchuan`、`market_town`、`wan_city`、`zhuo_county`，打聽度落在 2～3 的邊上），修前一版 32 組全敗、修後全過。名望要掃 0／小有名氣／名動一方三段（`renown.fame_bars(c, world)[tier - 1]`），份量 4 的舊事各兩件挪到兩天前（再多算一件就多一點名氣）。
  - **反查**要換成「甲或乙去打聽看客、看客再 `tavern_do("trace")`」：反查讀的是**打聽的人**的名氣（`person_fame(asker)`），所以旁觀客站的位置不重要，要讓打聽的人名望 0（風聲不具名）、打聽度剛好在 2／3 的界線上。
  - **買兇找人整條路**：兩個敵陣營的人各 `tavern_do("seek", 目標)` 再 `tavern_do("hit", 目標, "0")` 雇（散人沒有仇、雇不成，兩個世界回同一句拒絕），目標走到城外（`location = "runan_wilds"`），每隔 600 秒叫一次 `g._tavern_hit_check()`，比每一次擲「找到／沒找到」的序列；**不要比找到之後的戰報字**：持有者本人的威力含碎片（戰力 ×1.1），同一組亂數也會打出不同的結果，那是設計，旁人看不到。
- **用自己亂數的掉落**（名號＋戰報流水號）：先照種子挑出擲得中的名號建角色，再實打。
- **減法季（`Config.jianfa`）顯示字小修的驗法**（2026-10-26 2c 複驗，`a772b958` 對 `7791d2ff`）：
  - **「得：」帳對存檔差額**：每一趟快照前後的經驗、心得、銀兩、丹、素材，逐項對帳上的數字；兩版（`git archive` 各解一份、同一組亂數）各跑一次再逐趟比。**每個新角色第一趟的存檔差額一定多 +2 顆回體丹**（新手目標 `level5`、`side` 各 +1，第一次 `choose` 就發），不是漏帳，先動作一趟再量或把它排除。判「多出一則單獨的『心得 +N』訊息」要排除戰報卡片明細（`⚔` 那一則後面緊跟的得失行），不然每場仗都誤報。
  - **一個行程只 `boot` 一種設定**：同一個行程連叫兩次 `qc.boot`（兩種 profile）會把 stdout 包兩次（`I/O operation on closed file`）、第二個資料庫 `open_season` 的 assert 也會掛；每種設定一個行程，PowerShell 同一個呼叫裡 `Start-Process` 一排再 `Wait-Process`。
  - **開著的那一份對照要分類，不是看總差**：關著的季 0 行差就過；開著的季用 token diff 把每一對不同的行切成片段彙整（按 `，、。「」（）|` 切 token 再 `difflib`；直接字元層級 `SequenceMatcher` 在幾 KB 的行上會跑好幾分鐘），每一類都要對得上這一批改的東西；存檔另外逐欄走 JSON 比，**江湖紀錄與滾動 `log` 會因為訊息變少而整串位移，要排除它們**才看得出實際入帳（心得、經驗、素材、丹、銀兩）有沒有動。
  - **探索一顆開著時城裡操練（`act:drill`）不畫、直叫回「（此刻無法這麼做。）」**：只有操練會叫的事件型提示（`h_drill_done`）在那種季玩不到，只能用 `hints.note_for(state, content, id)` 驗字（四種身分、六種季各印一次，兩版逐字比），可達性另外按按看。
  - **開實機看**：`/api/main` 有 `mostly` 與 `options`（`act:explore` 的 `label`＝「探索（體力 18・野外多料）」），行動列的格子是 `button.act-ink`（小字在 `small`），「剛剛」那張卡是 `.now-one`（拿 `innerText` 就有「得：…」那一行與底下的標籤）；讓角色在同一個頁面按鈕、用頁面自己的 `fetch('/api/main')` 前後各讀 `status.xinde`／`status.exp.have` 對帳，不必再用 `requests` 登入（再登入同一帳號會把分頁的 session 踢掉）。出門一趟抽到「有悟」那一拍會把選單換成 `sense:0..3`，要先按掉才能再按探索。
- **列傳、評曰、商城的票**（2026-10-26 批 7b，`cb202c8c` 對 `9f68f257`；範本 scratchpad `qajf7b\`：`kit.py`、`v2_annals.py`、`v3_mall.py`、`cmpq\cmp_qa.py`）：
  - **腳本 `import server` 之後先 `server.CONTENT = c`**：`server.zhuan_extras`（公開頁的紀念印與插畫）照模組層的 `CONTENT` 判開關，那一份照啟動時的環境變數載；腳本沒設 `TIANXIA_PROFILE` 就是不帶設定、減法季關著，回 `{}`，看起來像「公開頁沒蓋印」。
  - **收季要哪一軍贏就自己給結局**：`store.mutate_season(lambda s: end_season(_season_vehicle(c, s), c, store, ending=<scenario.endings 裡 winner 是那一軍的>))`（`from tianxia.world import end_season, _season_vehicle`），角色要先存進資料庫（論功讀 `CharacterStore.books`）；之後每人同步一次才記論功的行狀。
  - **假模型**：一個物件有 `chat_structured(messages, schema, **kw)`，照系統提示第一句裡的人物名回 `schema(verdict="…")` 或丟例外；`game.client = fake`、`server.QUEUE = None` 再叫 `server.verdict_text(game, job)`，B 段清理（假名、數字、太長、簡轉繁）都驗得到。實機模型擋掉時 `/api/zhuan/write` 背景十幾秒照備援寫成（`by: rule`、評曰全照固定句），輪詢 `/api/zhuan?season=N` 的 `written`。
  - **季中上架照季曆的週**：把季的 `time` 改成 `calendar.week_start(k, c, s) ± 600` 再讓角色同步，讀 `g._mall_moment()` 與 `g.mall_view()`；week7 的週是段（第 3 段＝第 5 天）。退款是管理者 `/api/do/mall_refund {name, id, note}`，編號從 `/api/admin/mall {name}` 的 `purchases[].id` 拿。
  - 公開頁有額外樣式時 `<style>` 裡本來就有 `.zh-art`，判有沒有插畫要找 `<figure class="zh-art"`；要看有圖的樣子，在複本放一個假的 `web/img/zhuan/<鍵>.webp`（驗完刪掉）。
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
