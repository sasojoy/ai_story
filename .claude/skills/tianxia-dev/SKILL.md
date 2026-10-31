---
name: tianxia-dev
description: 《天下大勢》開發一批或修一張回饋單之前先看：工作樹與指令的坑（CRLF、Bash 被擋、共用的 stash）、test_for 怎麼挑測試、內容與規則改動常踩的雷（garrison 對 enemies、開關與蓋章、季種類、_record_exp）、量表怎麼讀、回報 PM 的格式。分支與合併的規矩看 tianxia-flow，各區塊的規則細節看 docs/guide/。
---

# 天下大勢：開發子代理的實務手冊

這一份只寫「怎麼做才不踩雷」。分支、合併、什麼時候跑整套：`tianxia-flow`。某一塊規則現在怎麼運作：`CLAUDE.md` 指到的 `docs/guide/` 那一份。網頁（`web/app.js`、`style.css`、店面、桌面版字級）另見同資料夾的 `網頁.md`。

## 開工

- **2026-10-30 起照〈開發規範手冊〉**（`docs/superpowers/specs/2026-10-30-開發模式-design.md` 第三、四節；分支與測試的總規矩在 `tianxia-flow`）：
  - **新功能一律 `scripts/new_feature.py <包名>` 生一包**（`tianxia/features/<包>/`：`__init__.py` 登記與掛鉤、`rules.py`、`actions.py`、`state.py`、`content/`、`routes.py`、`web/`、`tests/`、`bots.py`、`README.md`；用不到的不生）。這支腳本在第 1 階（`feature/core-hooks`）合進 develop 之後才有，之前照舊寫在原本的模組。
  - **舊功能碰到才搬**：派工上哪一批要動某個功能，順手把它搬進包裡；搬的那一步是純搬——行為不變、測試只搬位置不改斷言，那一包的測試與核心契約綠。不搬的留在 `engine.py` 不動，沒有大翻修。
  - **包只 import 核心**，不 import 別的包；要用別包的東西走核心的服務（例：票的庫存與消耗走 `ctx.wallet`）。過渡期可以 import 還沒搬的舊模組，行尾註 `# 過渡：待搬`。`tests/core/test_feature_boundaries.py` 會掃。
  - **只跑那一包的測試**（`-n 4`）；slow 不自動跟，要跑就 `scripts/test_for.py --slow`。
  - **不改技能檔**：學到的寫在回報的「學到的」一節，PM 收進技能（手冊第十節）。
  - **每做完一個 Task 就推一次**自己的分支（手冊第八節）：換帳號最多丟一個 Task。
- 先 `git worktree list`、`git remote -v` 核對自己在哪一份 clone、哪一條分支（這台有 `天下大勢`、`ai遊戲` 兩份）。
- 一批一個工作樹，從派工指定的分支開（多半是 `origin/feature/formal-season`）。分支名照派工寫的。
  如果是 `git worktree add -b` 開的，要加 `--no-track`，或開完 `git branch --unset-upstream`：不然它跟著功能分支，`git push` 可能推錯地方。推的時候一律寫明 `git push origin <你的分支>`。
- 工作樹沒有 `.venv`：python 用 `C:/Ray/專案/天下大勢/.venv/Scripts/python.exe`，PowerShell 呼叫。（Bash 另外會拒絕 `git -C .`〔路徑要寫死〕與 `"...python.exe" --version` 這種「指令名算出來的」；Bash 的 heredoc 寫 python 時字串裡的反斜線 n 會變成真的換行，寫腳本一律用 Write。Git Bash 的 `git show <版本>:<路徑>` 會被 MSYS 的路徑轉換弄壞〔`ambiguous argument 'origin\dev\…;…'`〕，前面加 `MSYS_NO_PATHCONV=1`。）
- **派工要你載的技能或設計稿不在這條分支上**（2026-10-21：`tianxia-map-remake` 與 `2026-10-20-輿圖簡化-design.md` 只在 `develop`、`origin/design/map-simplify-3`，`feature/territory-conquest` 與它開出來的 `dev/blocks-2` 都沒有）：`git log --all --format='%h %ci %D' -3 -- <路徑>` 找最新的那一版，`git show <那一版>:<路徑>` 讀（設計稿存到 scratchpad 再 grep），不要為了讀它把檔加進自己的分支（之後合 `develop` 會變成兩邊都新增的衝突）。
- **派工寫的 `origin/feature/<名字>` SHA 是派工當下的**，開工 fetch 之後可能已往前走（2026-10-26 減法季 3b 修正輪：寫 `20e78b3f`，fetch 後是 `52b598a5`，多的是雲端的旁白兩筆）：合最新的、回報寫實際合了哪一版；「關著不變」的 base 也是合進來的那一版。合進來的衝突多半是同一個檔兩邊各加一段（`models.py` 的 `SortieRules` 欄位、試玩回饋檔的 FB 列與 QA 節、QA 技能檔）：scratchpad 寫一支「兩邊都留、可選擇中間補空行」的小腳本（讀進來轉 `\n`、assert 標記各 N 處、寫回轉 CRLF），比手改穩。
- 先寫計畫 `docs/superpowers/plans/<日期>-<名字>.md`（派工說「不必給企劃者審」就不審），一張回饋單不用計畫。不開子代理、不開 Workflow，除非派工明講。
- 派工若要「先合某分支」，合之前先 `git merge-base --is-ancestor <那一版> origin/feature/formal-season` 看是不是已經在功能分支上。PM 前後兩則指示衝突時照後一則；合到一半發現不對就 `git merge --abort`。
- 派工寫 `git switch -c dev/<名字> origin/dev/<名字>`，但 `git worktree list` 看得到那條本地分支已經在別的工作樹 checkout 著（上一位開發的）：同一條本地分支不能兩處同時 checkout，`switch -c` 也會說已經存在。開一條別名的本地分支（例 `conquest-1-fix`）從 `origin/dev/<名字>` 開，推的時候寫 `git push origin HEAD:dev/<名字>`，不去動別人的工作樹（2026-10-20 領地爭奪第一批修正）。

## 工作樹與指令的坑

- **檔案是 CRLF**（`core.autocrlf=true`）。用腳本改檔：讀進來 `\r\n`→`\n`，比對替換，寫回前轉回去。每一處替換都要 `assert count == 1`。一處一個腳本或一次一處，不要「多處替換、最後統一寫檔」（中途 assert 失敗會讓人以為改好了）。
  PowerShell 裡不要先 `IndexOf` 記下位置、再 `Replace`、再拿舊的位置 `Substring`（位置已經移了，會把檔切壞；2026-10-20 切壞過 `bot_policy.py`，`git checkout --` 救回）：要刪一整段就用 Python 腳本照標記找頭尾。Edit 工具直接改 CRLF 的檔沒問題（換行照原樣留著，2026-10-20 量過 `web/app.js` 改完全是 CRLF），只有自己寫腳本才要轉。
- **Bash 在 worktree 隔離下會擋**：
  - 帶 git 的 heredoc、`git -C`、用 `$VAR` 或 `$(...)` 組出來的路徑或指令名，這幾種會被拒。不帶 git 的 heredoc（`cd … && cat > 檔 <<'EOF'`、`cat >> tests/x.py <<'EOF'`）也一樣被拒（2026-10-20）：寫檔、加測試一律用 Write／Edit 工具。
  - 繞法：git 一條一條下、路徑寫死。要改檔就用 Write 工具寫一支 Python 腳本到 scratchpad，再用 `python 腳本 .` 跑。
  - 要跑 venv 的 python、讀 `$env:TEMP` 的 log，改用 PowerShell 工具。
  - 用 `;`、`&` 串起來的、`cat > 檔 <<EOF` 寫檔的，也常被當成「太複雜」拒絕：寫檔用 Write 工具，指令一條一條下。
- **在 scratchpad 解一份複本跑伺服器**（2026-10-20）：`git archive HEAD -o <scratchpad>/<名字>/src.tar`，再 `tar --force-local -x -f <tar> -C <目錄>`。不加 `--force-local` 時 Git Bash 的 tar 把 `C:/…` 的 `C:` 當成遠端主機（「Cannot connect to C: resolve failed」）。
- **中文輸出**：Python 印中文前包 UTF-8（`PYTHONIOENCODING=utf-8` 或 `sys.stdout = io.TextIOWrapper(...)`），不然 cp950 會炸（連 `print` 一個 `−` 都會）。
- **TIANXIA_DB**：每次跑測試、跑腳本都設到 repo 外一個新的暫存檔（`$env:TEMP\tx_xxx.db`）。舊的資料庫會讓測試假失敗。**每一輪都換新檔，不要沿用上一輪的**：模組範圍的 fixture 在 conftest 換成每個測試自己的檔之前就開世界（例 `tests/web/test_renown_web.py` 的 `base`，`Game.new` 沒給 world），讀到外面那個檔裡上一輪留下的季，4 條假紅、base 一樣紅，很像「別人留下的老毛病」（批 2 接線碰過，2026-10-26）。
- **git stash 是所有工作樹共用的**，別的 session 也在用。
  - 不要裸 `git stash` / `pop`。
  - 要用就 `git stash push -m <獨一無二的標籤> -- <檔>`，`git stash list --format='%H %gd %gs'` 找到自己那一筆，`git stash apply <sha>`，再照標籤找 `stash@{n}` 去 drop。
  - 想證明測試「修之前是紅的」，最簡單的就是這樣把改動暫時收起來跑一次。
- **用 `python -I` 跑腳本時 `PYTHONIOENCODING` 不生效**（`-I` 忽略所有 PYTHON 開頭的環境變數）：在腳本裡 `sys.stdout.reconfigure(encoding="utf-8")`。
  **`PYTHONHASHSEED` 也一樣不生效**（2026-10-25 減法季批 2 的關著對照）：加了 `-I` 的兩份輸出差在存檔裡集合欄位的順序（`seen_events`、`visited`、`revealed`），不是程式的差。要固定雜湊就不加 `-I`，腳本開頭 `sys.path.insert(0, 根目錄)`、`os.chdir(根目錄)` 擋掉別份；同一份程式跑兩次先確認一模一樣。
- **實機看畫面**：PM 會給你一個埠與 `<名字>.localhost`（別的子代理同時在跑伺服器，cookie 照主機名分開）；瀏覽器窗格是共用的，**每一個動作都帶自己的 tabId**，看完把視窗設回 desktop、關掉自己的分頁、`taskkill /T` 關伺服器。窗格在背後時截圖可能拍到動畫中途，數字用 `javascript_tool` 量。
- **這台的 Ollama 沒有 `gemma4:12b`**（只有 26b 等舊模型，2026-10-20 查的）：真模型實測叫不動就照實回報；不要改拿 26b 代跑（17GB、keep_alive 12 小時會一直佔著顯卡）。
- **開伺服器又不能打到 11434**：模型網址（`Config.ollama_url`）沒有環境變數可改，設定覆寫檔照派工指定的（例 `week7`）就不另寫一份。在 scratchpad 寫一支包裝：`sys.path.insert(0, 工作樹)`、`import server`、`server.CONTENT.config.ollama_url = "http://127.0.0.1:9"`、`server.main(["--port", 埠])`，用 `Start-Process` 跑它（`TIANXIA_DB`、`TIANXIA_PROFILE` 照設在 PowerShell 裡，子行程繼承）。角色在每次建 `Game` 時才照設定建 client，所以先改再 `main` 就全部指到那裡（FB-490～493 這一輪）。
- **實機要某一步的角色**（例：初入江湖第一步）：`/api/register`＋`/api/character` 建一個（密碼產生後寫進 scratchpad 的檔），再用 `CharacterStore.load`／`save` 改 `tutorial_step`（與 `location`）存回去；伺服器每次進鎖都從資料庫重讀，不必重開。序章那幾步（0～10，含出師那一步）要 `location` 是 `mentor_hut`，不然 `m.prologue` 是 None、看起來像出了草廬。
- **唯讀的實機量測不必 `git archive` 複本，直接從工作樹開伺服器**（2026-10-22 develop 小單）：`Start-Process python -u server.py --port <埠>`、`-WorkingDirectory` 設成工作樹，`TIANXIA_PROFILE` 給 scratchpad 裡抄來的設定檔（絕對路徑、不寫 `.json`，裡面加 `"ollama_url": "http://127.0.0.1:9"`）。改 `web/` 不必重開（每次請求讀檔），改 `tianxia/` 要 `taskkill /T` 再開。無頭 Chromium 的量測沿用 PM 那一輪 scratchpad 的 `practiceqa/cdp.js`、`place_srv.py`（`start({copy: <工作樹絕對路徑>, …})`：`place_srv` 裡 `os.path.join(HERE, 絕對路徑)` 就是那個絕對路徑；`place({name, loc, faction, set: {玩家欄位: 值}})` 改存檔，`set` 可以直接塞 `duel_tally`、`stamina` 這類欄位），腳本抄一份到自己的 scratchpad 資料夾；`PYTHONIOENCODING=utf-8`，node 是 `C:\Users\ray61\AppData\Local\hermes\node\node.exe`。只有頭目的地點：官軍站長社、黃巾站鉅鹿道壇（反過來站的那一方有尋常對手，練功那一行寫打誰）；頭目名字照陣營看到另一面（官軍在長社遇到段鐵頭、黃巾在鉅鹿道壇遇到衛重）；week7 每個頭目每一段兩場，次數用完 `duel_tally["1:w1:<頭目 id>"] = 2`（`<季數>:w<段>:<id>`）。
- **「休季換程式」的畫面問題先看載入的內容是不是已經換過了**（FB-654，2026-10-22）：`content.timetable` 載入時就被 `season21_timetable` 換成新程式的週次與日子，舊季那一份（週末式、`event.week` 1～12）已經不在內容裡，沒得「照上一季自己的時刻表」。要列上一季發生過的事，看這一季存的東西：`season.timeline`（結算過的一般大事與結算那一刻）、`season.schedule`（決戰與季末的排定時刻）。測試用舊程式補算再換內容比對：`old = real_content("weekend")`＋`season_days = 7`、`auto_open_first_season`，`Game.new(old, …, world=world).sync(T0)` 開季，`world.catch_up_season(old, T0 + 天數 * DAY / old.config.time_scale, random.Random(0))` 才會一路結算大事（直接 `setattr(season, "time", …)` 不結算，timeline 是空的），`admin.admin_end_season(…)` 收季，再 `Game.for_world(real_content("week7"), world)` 跟舊程式自己的輸出逐週比（`tests/test_fb654_rest_season_map_titles.py`）。修之前用 `git stash push -m <標籤> -- <檔>` 收起來證明測試是紅的。
- **計畫要對現行程式**：派工給的計畫可能是照 main 或更早的版本寫的；開工先核對，差異寫進計畫，前提不在了就停下來回報 PM。
- **等背景測試跑完**（2026-10-21 小單，279 個檔 `-n 6` 約 10 分鐘）：`Monitor` 一啟動就回傳，接著的指令不會等它，連開幾個 `sleep` 的 Monitor 只是排通知、不是真的在等。要原地等就用前景 Bash：`until grep -qE " in [0-9.]+s" "$TEMP/xxx.log"; do sleep 5; done; tail -n 15 "$TEMP/xxx.log"`，`timeout` 給 590000（單獨一條 `sleep N` 會被擋，until 迴圈不會）。pytest 跑到 99% 之後常再等好幾分鐘（最後幾條是整季模擬），不是卡住。
- 背景長跑（量表）用 `run_in_background`。輸出導到檔案時 python 會緩衝，加 `-u` 才看得到進度。等它結束的通知，不要輪詢。
- **Bash 不要寫沒有內容的 `python - <<'EOF'`**（2026-10-26 空 heredoc 讓指令卡 120 秒被丟進背景）：要跑 python 一律 Write 一支 `.py` 到 scratchpad 再用 PowerShell 叫。
- **PowerShell 的變數名不分大小寫**（2026-10-21）：迴圈裡 `$O`（腳本資料夾）被後面的 `$o`（雜湊）蓋掉，路徑變成一串雜湊。路徑變數取長一點的名字（`$CMP`、`$SCRIPTS`）。外部程式往 stderr 印字（`2> 檔`）時 5.1 會報 NativeCommandError、整條指令退出碼非 0，但迴圈會接著跑；要看真的有沒有失敗，看輸出檔與 `.err` 的內容。
- **用 Write 寫的 `.ps1` 在 PowerShell 5.1 讀成系統編碼**（UTF-8 沒有 BOM）：腳本裡的中文路徑（`C:/Ray/專案/天下大勢/.venv/...`）變亂碼、找不到 python（2026-10-21）。迴圈直接寫在 PowerShell 工具那一行裡，不要另存 `.ps1`。
- **PowerShell 的 `git commit -F - @'…'@` 不會走 stdin**：here-string 被當成一個路徑參數，合併中會報 `cannot do a partial commit during a merge`（不在合併中就變成只提交那個「路徑」）。commit 訊息用 Write 寫進 scratchpad 的檔，`git commit -F <檔>`（2026-10-20）。
- **Git Bash 的 `sed -i` 會把 CRLF 的檔整個改成 LF**（2026-10-20 改 `bot_policy.py` 一行，整個檔變 LF）：改一行也用 Edit 工具，或照上面「讀進來轉 `\n`、寫回轉回去」的腳本。
- **Bash 的隔離檢查會擋「太複雜」的 python heredoc**（一次改兩個檔的 dict 迴圈就被擋過）：改檔腳本寫進 scratchpad 的 `.py`（裡面放一個 `edit(相對路徑, [(舊, 新, 次數)])` 的小函式，照上面 CRLF 的規矩），用 PowerShell 跑 `python 腳本 .`。
- **實機開自己的伺服器**（不碰 7861）：
  - 設定不必動 `content/profiles/`：`TIANXIA_PROFILE` 給絕對路徑（不寫 `.json`）就讀那個檔，抄一份要的設定檔到 scratchpad、打開要試的開關，順便把 `ollama_url` 指到死埠（`http://127.0.0.1:9`）。
  - 管理者的名號在 `/api/character` 取不到（玩家不能取管理者的名號）：用 `scripts/set_password.py <帳號> --character <名號> --db <暫存資料庫> --local-dir <scratchpad>` 建（密碼寫在 scratchpad 的檔），啟動伺服器前設 `TIANXIA_ADMINS=<名號>`。其他測試角色走 `/api/register`、`/api/character`，陣營與所在地可以直接寫進同一個資料庫（`open_characters()` 照 `TIANXIA_DB`），伺服器每次拿鎖都重讀角色。
  - 正式設定的排程是關的（啟動時印「排程：關」）：世界時間只在有人連線時推，集結截止、回合逾時要有人輪詢才會發生——驅動腳本要一直打 `/api/main`。
  - 長的等待：PowerShell 的 `Start-Sleep` 超過一定秒數會被擋；在瀏覽器分頁裡 `javascript_tool` 跑 `await new Promise(r => setTimeout(r, 30000))` 再抓 `/api/main`，或用 Monitor。
- **Bash 隔離會擋「`diff <(…) <(…)` 加 `git add` 串在一起」的指令**（too complex，2026-10-21）：拆成兩條，一條比檔、一條 git。
- **PowerShell 把含雙引號的字串傳給外部程式時，雙引號被吃掉**（2026-10-21 變異腳本的「舊字串」引數是 `phase == "preparing"`，到 python 手上變 `phase == preparing`，斷言「舊字串在檔裡 0 處」、什麼都沒跑）：引數用單引號、而且挑一段不含雙引號的獨特片段（例：`season.ended or phase == ` 換成 `season.ended or phase != `）。變異腳本（自己在 scratchpad 寫一支，參數 `<工作樹> <相對檔> <測試檔> <舊> <新>`）：舊字串先斷言剛好一處（換 CRLF 檔先轉 `\n`）、`finally` 寫回原檔 bytes、跑完 `git status` 確認沒留下改壞的檔。；單引號字串裡寫 `''` 是一個單引號，原始碼用的是雙引號時兩個都別放進引數（2026-10-26 變異腳本兩次「舊字串 0 處」），改挑不含引號的片段（例：`if duel else SIEGE_CONQUEST_FOE` 換成 `if False else …`）
- **「關著不變」的 base 自己 `git archive <commit>` 解一份，別借 scratchpad 裡別人開的 `fjbase` 之類的工作樹**（2026-10-26 修正輪）：那種工作樹的 HEAD 會被別的 session 挪走，名字還叫 base、內容已是更新的功能分支，關著三種季比出 90 行差（本週卡、三方卡多了雲端後來的欄位）。比之前先 `Get-Content <工作樹>/.git`＋`HEAD` 檔看它現在是哪一版，或乾脆自己解（`git archive f329d059 -o X.tar`、`tar --force-local -x -f X.tar -C 目錄`）。
- **`Start-Process -ArgumentList` 的陣列裡有空白的引數要自己加引號**：`-m "slow or not slow"` 寫成 `'"slow or not slow"'`，不然 pytest 把 `or`、`not`、`slow` 當成檔名，印「no tests ran」、結束碼 5（2026-10-26）。
- **一件事一個 commit、但共用同一個測試檔**：測試檔照 `# ── N. 標題` 的段落標記切（標頭＋第 1..k 段），引擎的 hunk 退回去用 `(最終, 修之前)` 字串對照；一支 `split_commits.py <k>` 把第 k 件放進索引、工作樹不動（本輪六件，scratchpad `jianfa-2-fix/split_commits.py`），提交完用 `git archive <commit>` 解出來各跑一次相關測試檔確認單獨一筆是綠的（`verify_each.py`）。
- **解 `git archive` 的 tar 用 Python 的 `tarfile`**（2026-10-25 減法季批 3c 接線）：Git Bash 的 `tar --force-local` 碰到 PowerShell 給的反斜線路徑照樣「Cannot open」；`python -c "import tarfile,sys; tarfile.open(sys.argv[1]).extractall(sys.argv[2])" <tar> <目錄>` 一次就好。
- **整份對照（資料庫 JSON）不要加 `-I`**（2026-10-25）：`-I` 連 `PYTHONHASHSEED` 也忽略，`WorldState.flags`／`revealed`／`fired_thresholds` 這些 set 每次寫出來順序不同，同一版跑兩次 `seasons` 那一列的雜湊就不一樣（長度一樣）。腳本自己 `sys.path.insert(0, root)`、`os.chdir(root)`，不加 `-I`、設 `PYTHONHASHSEED=0`，先跑同一版兩次確認零差異再比。
- **scratchpad 的腳本別取標準庫的名字**（2026-10-26：`inspect.py`）：Python 把腳本所在的資料夾排在 `sys.path` 最前面，`pydantic` → `typing_extensions` 的 `import inspect` 拿到自己那支，報「partially initialized module 'tianxia.characters'（circular import）」，看起來像程式壞了。取 `look_saves.py` 這種名字。
- **文件的衝突兩邊都留**：scratchpad 一支 `union.py <檔>`（照 CRLF 讀、`<<<<<<<`／`=======`／`>>>>>>>` 成對拿掉標記、HEAD 那一段在前、斷言成對），一個檔一次，跑完 `git grep -n "^<<<<<<<"` 確認沒有剩。程式的衝突照舊一處一處用 Edit 看著解。
- **不要寫帶中文路徑的 `.ps1`**：Write 工具寫出的 .ps1 沒有 BOM，Windows PowerShell 5.1 照 ANSI 讀，`C:/Ray/專案/…/python.exe` 變亂碼、每一行都 CommandNotFound（2026-10-20 背景跑對照表踩到，log 只看得到一串錯）。要串好幾個 python 程式，就寫一支 Python 調度腳本，用 `sys.executable` 叫子程式，再從 PowerShell 跑那一支。

## 測試怎麼挑

- 平常只跑 `scripts/test_for.py --base <base>`（不含 slow，要連 slow 加 `--slow`；改到的測試檔本身照舊連 slow），或直接 `pytest 改到的那幾個檔 -m "slow or not slow"`。整套留給合併的人。挑法照手冊 4.3（2026-10-31 起），細節與量到的條數在 `docs/guide/量表與教訓.md`「測試怎麼挑」。
- **base 要選對**：
  - 跟你的分支開出來的那一點比，通常是你的功能分支 `origin/feature/<名字>`（先明確 fetch）；不給 `--base` 跟 `origin/develop` 比；base 找不到分岔點會停下、結束碼 2。
  - 你自己合了別的分支進來時，base 用合完那一個 commit，只量你這一輪的改動，不然會把別人的東西全挑進來。
  - `--list` 先看挑到哪些檔、每一段為什麼挑；`--count` 數條數。量「改這一行會挑到幾條」時把檔名明確傳給它（`test_for.py tianxia/engine.py --base HEAD --count`），不然工作樹裡別的還沒提交的改動也算進來；臨時改檔量完用位元組比對確認還原（2026-10-31 第 0 階）。
  - **合併還沒提交時別拿 `--list` 的清單**（2026-10-21 輿圖簡化第 2 批收尾）：`test_for` 跟 base 的分岔點比，`--no-commit` 合進來的東西都還算「沒提交的改動」，合功能分支的那一下挑到 327 個檔（幾乎整套）；先跑兩批的測試檔、提交合併，再 `--list` 只剩這一批自己的 117 個。
- 改 `tianxia/engine.py` 照改到的 Game 方法挑那一群（方法名第一個認得的字；檔名沒有那個字的群改看內文叫最多的是哪一群）；落在共用方法（choose、_everyday_options、sync、status_data……）或核心服務（_log、_side、_pill_day……）就跑核心測試＋煙霧，約 1,500 條、`-n 4` 約一分鐘。改 `models.py`、`state.py` 也是核心測試＋煙霧，欄位名帶功能前綴的再加那一群。（第 0 階之前改 `engine.py` 會挑到八千多條。）
- **整個檔標 slow 的一般功能測試有 77 個檔**（`explore_one*`、`sortie_duel*`、`epiphany`、`errands`、`stances*`、`story_*`、`test_mall_web`……）：`test_for` 預設不跑，開跑前列出來、全被濾光時提示加 `--slow`。改的正是那一塊就加 `--slow`。
- **功能分支在你做的時候往前走了**（2026-10-21 玉璽碎片第 2 批：開工時 `feature/territory-conquest` 是 `f5686765`，做到一半合進了翻地 `90e52e9b`）：`test_for --base origin/feature/<名字>` 照分岔點比，挑到的還是只有自己的改動，照用；「關著一個位元組都不變」照派工寫的那一版比（不是新的頭）。要不要合新的頭照派工，沒說就不合，回報裡寫功能分支到了哪裡、試合（`git merge-tree --write-tree HEAD origin/feature/<名字>`）有沒有衝突。
- `test_for` 預設 `-n 4`；`--` 之後給 `-n X` 就照給的（第 0 階之前它自己補 `-n auto`、擋不住，2026-10-31 改了）。
- **兩張單的測試寫在同一個檔、又要一張一個 commit**（2026-10-21 FB-606、607 都在 `test_conquest_flip.py`）：先把第二張的測試從檔尾剪到 scratchpad（照第一個 `def` 的名字找頭、連前面的空行一起剪），提交第一張，再接回去寫第二張的實作。不要裸 `git stash`。
- 新測試超過一秒（建 `Game`、載真實內容通常就超過）標 `@pytest.mark.slow`。
  **直接 `pytest <檔>` 時 slow 預設被排除**（pyproject 的 addopts）：整個檔都是 slow 就會「no tests ran」、結束碼 5，要加 `-m "slow or not slow"`（`test_for` 只對改到的測試檔本身自動連 slow，別的要 `--slow`）。
- **新測試綠了不等於有用，拿掉實作的一個條件跑一次看會不會紅**（變異檢查，2026-10-20 領地爭奪第三批 B）：用一支腳本「換掉一處、跑那個測試檔、換回來」。三個坑：
  (1) 換回來用的反向替換要先確認「換掉之後的字串」在檔裡剛好一處，不然斷言失敗、檔案留在改壞的狀態（短字串例如 `return msgs + self._legend_find(...)` 換掉一處之後會變兩處）；
  跑之前先 `git diff --stat` 記一下，跑完再看一次；
  (2) 拿掉一個條件測試沒紅，先看是不是「兩層保護」（例：`Game._seal_find` 的藏處檢查在擲骰前、寫入重驗各一次，拿掉一層本來就不紅），是的話改拿掉兩層、或確認這兩層是故意重複；
  (3) 測試裡用的「不該發生」的前提要真的分得開兩個原因（例：天命之季不藏的測試，七片全隱沒時「沒東西可藏」也會是空的，要留一片未現世才測得到「因為天命之季」）。
- **變異清單寫成 .py 檔**（2026-10-24 減法季批 2）：`MUTATIONS = [(舊, 新), …]`，變異腳本用 `runpy.run_path` 讀、一處換一次跑 `pytest <檔> -x`、`finally` 寫回原 bytes——舊字串裡的雙引號、換行都不必經過 PowerShell 的引數。純規則檔一個變異約 2 秒（腳本在 PM scratchpad 的 `jianfa-2/mutate.py`）。綠的那一條先看是不是被別的參數蓋住（`growth.capped_exp` 的「到 45 級全換」被測試裡一律 `room=0` 蓋住），補一條只差那個條件的斷言再跑一次。
- **`--durations` 第一個測試的 setup 一秒多**是整個工作階段的 fixture（內容母本、序章母本），不是那個測試慢；工作樹第一次跑 pytest 四十幾秒是在編 pyc，第二次兩三秒。要不要標 slow 看 call 那一欄（2026-10-24）。
- **證明「祕密沒漏出去」用差異測試**：建兩個只差那個祕密的世界（例：碎片藏在 A 或藏在 B），比畫面、API、江湖史、傳聞、管理者的回話與玩家的存檔是不是一個字不差；不要在輸出裡找祕密字串（地名到處都有，找不到也不代表沒漏）。
  同一條測試裡把開關關掉再比一次、斷言「關著時看得出差別」（列出哪幾項不一樣），才證明這條測試抓得到漏（玉璽碎片改版第 1 批 `test_two_worlds_that_differ_only_in_the_holder_look_the_same`）。要找名號字串時，名號別跟固定的字撞（拿「懷璽」當持有者的名號，會撞到「懷璽之人」），用「甲客」「持璽客」這種。
- **差異測試要讓「世界差在祕密、後面的步驟不被結果帶開」**（玉璽碎片改版第 1 批修正，側門）：兩個世界裡誰贏誰輸、誰掉了氣血會不同，之後算威力的步驟（氣血係數 `condition` 也在 `_spar_power` 裡）就跟著差，測試紅了不是漏而是被結果帶開。做法：先把所有「看」的畫面讀完再打；每個人至多打一場有損耗的仗（截殺各挑沒打過的人）；擂台挑了就認輸（`arena:yield`，結果固定是落敗、名次不動）；只比「對手那一格」的數字，不比勝負與氣血。
- **差異測試抓不抓得到，用「還原漏洞」證明**：當祕密只在子開關開著時存在（關著本來就看不出差別），不能靠「關著看得出差別」那招，改成 `monkeypatch` 把防線拆掉（例：`Game._spar_power` 不理 `seal`、`_arena_bare` 回 None），斷言兩個世界在該有的鍵上真的不一樣（`test_the_side_door_guard_has_teeth`）。另外對實作做變異檢查：一處一處換掉、跑那組測試、看會紅；腳本把原檔 bytes 存在記憶體、`finally` 寫回，比反向替換安全（不會因為換回去的字串不唯一而卡在改壞的狀態）。
- **差異測試的「旁觀者」要站在看得到的位置**（FB-643，2026-10-21）：第 2 批的不具名守門有比「酒肆查兩人」，可是旁觀客在別處、兩人名望 0，打聽度只到 3，「近來的事」根本不列，漏了也比不出來。照被測的那個門檻擺人：同陣營、同一間酒肆（地頭熟）、名望第一段（打聽度 4 才列近來的事）、份量 4 的舊事湊到差一件就加名氣、舊事的時刻挪到兩天前（近況只看新的那一件），再斷言「看得到的那一行真的有出現」（`tests/seal/test_seal_fb643_tavern.py`）。
- **要對某些讀者藏起來的資料，先找現成的分類欄位**（FB-643：起用碎片的行狀不給酒肆讀）：`AnnalEntry` 加一個布林欄位會讓每個人每一則行狀的 JSON 都多一個鍵（`model_dump_json` 不省預設值，資料庫對照會整片不一樣）；改用新的 `kind`（`annals.SEAL`），顯示的地方給同一個標籤（`KINDS`）、季末的傳照舊歸段（`GROUPS`），讀者那幾處問 `annals.heard`。資料庫只有那幾則的 `kind` 變。
- **假瀏覽器的點擊不管 `disabled`**（`test_seal_acts_web.CLICK` 直接呼叫 click 的監聽器）：灰掉的鈕在真的瀏覽器按不到，在測試裡按得到。動作的處理要自己再驗一次（`seal-pick` 只收按得下去、那一列沒灰的），不要只靠 `disabled`。
- **給別人看的數字（勝算、身手、戰報的「對手威力」）每一處都要走同一個「給別人看的那一份」**：選單、玩家卡、頁面（`shopview`）、戰報兩邊各一份（發的與收的、守的與挑的）、假人讀的勝算清單；寫在存檔裡的快照（擂台分身）要另記一份，欄位加預設 `None`（舊存檔讀得進來、沒碎片時狀態不多一個字）。算這個數字的時機要排在記戰報之前：第一邊的記帳可能升級，第二邊再算就變了（`_spar`、`raid`、`_ambush_fight` 都在算 `ours`／`theirs` 的同一處先算好）。
- **一包 `**kwargs` 的標記（`Game._battle_marks` 這種）加新鍵**：有舊測試斷言整包一字不差（`test_joining_snapshots_turncoat_and_newbie`）。新鍵只在有值時才放進去，關著的季那一包一個字不變。
- **「關著一個字不變」的畫面對照，探針只問兩版都有的東西**：問到新版才有的效果鍵，舊版當成加的（中性值 0）、新版當成乘的（中性值 1），雜湊就不一樣，但那不是畫面。改問掛點本身的輸出（扣血、內傷、價錢、回話）。玉璽碎片改版第 1 批的腳本在當時 scratchpad 的 `sealcmp/cmp_seal_off.py`（七片各一個持有者、第一個是假人；三種季各 204 行）。第 3 批 QA 的 `seal3qa/cmp3.py`＋`kit3.py`（PM 這個 session 的 scratchpad；`QA_ROOT=<archive 根> python cmp3.py <weekend|none|season21|conquest> <畫面檔> <資料庫檔>`，`PYTHONHASHSEED=0`、不加 `-I`）更完整：兩份 archive × 四種用一支 Python 調度腳本開八個子行程平行跑，約十分鐘（2026-10-21 碎片第 3 批修正：子開關關著跟 `a46ac1dc` 比四種畫面一樣，資料庫只差翻地帳的 `flipped_from`；把 `revamp=False` 換成 True 跟合進來那一版比，畫面一樣、資料庫只差那一則行狀的 `kind`）。
- **修 bug 先寫會紅的測試**：先確認它在修之前真的失敗、失敗的數字跟 QA 回報的一樣，再修。回報時寫「修前重現了什麼」。
- **「確認並守住」的測試**（程式沒改、一寫就綠，例：假人不買商城的東西）：要證明它抓得到退步，另寫一個暫時的測試檔 import 它，monkeypatch 一個退步（例 `bot_policy.take_turn` 先叫 `mall_buy`、`social.card` 多塞一個「元寶」），跑一次看它紅，再刪掉那個暫時的檔（不提交）。
- 用正式內容測舊規則的測試，要在 helper 裡把新開關關掉（例 `c.config.precise_actions = False`、`four_tiers.enabled = False`）。新規則另開一個測試檔，不要改寫舊的斷言去迎合新規則。
  - **領地爭奪沒有開關**（2026-10-27 舊的地盤拔河、出陣推線、攪局、修築工事連開關與 `no_conquest` 一起拿掉）：`real_content("season21"/"week7")` 就是領地爭奪；出陣要打一場的測試用 `conquest_kit.conquest_rules`（約戰關掉）、站中立地（汝南荒野），敵方的大本營不給攻。
  例外：PM 的裁決直接推翻還沒上線的這一批的做法（不是開關後面的舊季）時，鎖住舊做法的那一條斷言照裁決翻過來，註明哪一條裁決、新規則的測試在哪一個檔（例：裁決 19 之後 `test_siege_void_when_no_attacker` 改成「沒有作罷的天下大事」，新的在 `test_conquest_siege.py`）。
- **週末季封存之後（測試整理批 1，2026-10-25），正式內容的測試一律 `real_content("week7")`，門檻有倍數、功能有週次**（2026-10-26 `test_renown_web.py` 紅 4 條就是這個）：
  - 名聲的測試寫的是門檻原數（名望 10／25／50／90、「再 23 到威震州郡」），以前週末季倍數剛好是 1；現在要 `renown_unscaled(real_content("week7"))`，不然名望 27 沒到第一段、名號行只剩善名那一個。同一個檔裡別的測試有 `renown_unscaled` 就是這個理由。
  - 開季第一天就要進擂台、懸賞榜的舊測試要 `no_week_unlock(...)`（那兩樣第 2 週才開；鐵匠鋪 2026-10-27、自創 2026-10-28 起開季就有，不必再叫）。兩個常一起疊：`renown_unscaled(no_week_unlock(real_content("week7")))`。
  - 批量把 `weekend` 換成 `week7` 的 commit 容易漏掉只有斷言字串、沒有 `renown_unscaled` 的檔；整批合進來之後有紅，先 `git log --oneline -- <那個測試檔>` 看最後一個改它的是不是這種整理批，再用 `git worktree add --detach <scratchpad>/bis <commit>^` 與 `<commit>` 各跑一次釘死是哪一筆（用完 `git worktree remove --force`）。
- 江湖紀錄 `state.journal` 新的在前（index 0）。找某一則照標題找，不要拿 `[-1]`。`_write` 寫的那一則，「銀兩 +N」這種數值變化在 `entry.changes`、不在 `entry.lines`。
- **兩個人的測試**（截殺、領地爭奪的混戰，2026-10-20 翻地與爭搶）：`Game.new` 不存角色，另一個人要被 `_load_kin` 讀到就先 `CharacterStore(world.db).save(game.state)`；
  照伺服器的做法每一個動作從資料庫重讀自己（`tests/ranger/test_raid.py::_do`、`tests/acts/test_conquest_flip.py::_do`）。season21 的新手期看 `newbie_real_hours`（現實 48 小時），
  只設 `newbie_days = -1` 擋不掉，要一起設 `newbie_real_hours = 0`。
- **證明開關關著一個字都不變**：一條條「關著不變」的測試之外，最省事的是拿 QA 的整份畫面對照（`tianxia-qa/引擎驗收.md` 第 7 節；scratchpad 裡 QA 留過 `conqqa/cmp_off.py`）：開這一批之前那一版與 HEAD 各 `git archive` 一份跑，比雜湊。腳本 `import server`，所以要連頂層的 `server.py server_push.py zhuan_html.py llm_queue.py console.py` 一起 archive（只 archive `tianxia content` 會 `No module named 'server_push'`），**`web` 也要**（`server` 載入時讀 `web/index.html`，沒有就 `FileNotFoundError`）。領地爭奪第一批修正：season21／week7／weekend 三種季 573／569／567 行一個位元組都一樣。
  **base 選對**：派工寫的對照版（例 `98c1c0f5`）之後，功能分支又合進了別的批（輿圖 v3 第 2 批 `b9ee3c9c`）時，你合進來之後拿舊版比，畫面會差在那一批動的東西（小地圖多一條路，不是你的改動）。先拿合進來的功能分支 tip 當 base 比到一個位元組不差，再另外拿派工寫的版本比一次、把差異歸給那一批（`diff` 看出差的位置）。玉璽碎片改版第 1 批修正：側門整條（卡、勝算、擂台選單與頁面、切磋、截殺、擂台各打一輪的整份戰報與回合演出）45 行、三種季，`98c1c0f5`／`b9ee3c9c`／HEAD 三版雜湊一樣；碎片全套 204 行，`b9ee3c9c` 對 HEAD 一樣，`98c1c0f5` 對 HEAD 只差輿圖 v3 那條路。
  - **改內容的地理（`locations.json` 的路、描寫）不看任何開關**：加一條路，三種季的輿圖、小地圖、那兩處的「前往」鈕與路程、描寫全都跟著變（輿圖簡化第 2 批的宛城—綠林山寨：開關關著的三種季每一季 85 行不一樣）。對照腳本要多擺人站在路的兩頭、把 `g.options()` 也寫出來才看得到；兩份輸出比對時長的那幾行（svg 十幾萬字）用「去掉共同的頭尾」印差的那一段，`difflib` 會跑好幾分鐘。這種差異是內容的決定，寫進計畫交 PM，不要自己加開關擋。
    要證明「除了那條路一個位元組都不差」：把新版的 `content/locations.json` 抄進舊版解出來的那一份（只換這一個檔），拿它跟新版比雜湊（2026-10-21 develop 合進領地爭奪：四種季、碎片改版關著，新版跟「develop＋那條路」雜湊一樣）。
  - 更完整的一支是 flip-1 QA 留的 `qa_cmp.py`（八個人、兩軍同地出陣、十二輪同步、快轉跨過 22:00、一場決戰、截殺帳、季的 conquest 與 xingshi；PM 這個 session 的 scratchpad `flip1qa/`），用法 `python -I qa_cmp.py <archive 根> <輸出檔>`，兩份平行背景跑各約 5 分鐘。2026-10-21 `b9ee3c9c` 與 dev/flip-1 QA 修正都是 6697 行、12,153,874 位元組。
  - 輿圖 QA 的 `cmp_off.py`（第 4 批複驗那一份，`main_view`、`map_state`、`map_base`、存檔，三種季各約 50 萬位元組、一支一分鐘內）**不含玩法說明**：動到 `howto` 的批另跑一支只印 `Game.howto_text()`（散人、官軍、黃巾各一份）的對照（輿圖第三版第 5 批，`95096217` 對 HEAD 三種季都一樣）。
- **一個測試只開一季**：conftest 每個測試給一個 `TIANXIA_DB`，同一個測試裡 `open_world()` 兩次開的是同一份資料庫，第二個 `Game` 讀到第一季的章（7 天季的測試裡 21 天季的 `season_length_days` 變成 7）。要比幾種季就 `parametrize`，一種季一個測試。
- **「舊季一字不變」用對照證明**（2026-10-20，7 天季 FB-500／501）：
  - 引擎：`git archive <開工那一點> | tar -x` 解到 scratchpad，同一支腳本在舊程式與 HEAD 各跑一次、diff 輸出。腳本開季後一路 `catch_up_season`＋`Game.for_world(...).world_tick`＋`sync` 到收季，印要比的字（狀態列、軍令、懸賞的 `due_short`／`due_text`、傳聞、玩法說明、名聲、`server.admin_choices`）；照 `time.time()` 算的（時刻表的 `at_real`）先抹掉，新加的鍵印之前拿掉。
  - 網頁：`webharness.run(DRIVER, {..., "app": <舊 app.js 的路徑>})` 用同一份伺服器資料、舊新兩份 app.js 各畫一次比字串；`wholeApp` 的名單只放兩版都有的函式。
    **伺服器送的資料形狀也改了時這樣比會比出假差異**（2026-10-20 FB-502：21 天季多送 `words`，舊 app.js 拿到新資料就把 21 天季當 7 天季）：改成兩邊各用自己的伺服器＋app.js——在舊程式的根目錄用它自己 `tests/` 的 `_render` 跑一次、寫成 JSON，再比。
  - 兩份輸出行數一樣時照行號比：`difflib` 遇到一大段相似的行會錯配，報出其實沒變的行。
  - Windows 的 `tar -xf` 解 `git archive` 會在中文檔名（`docs/`）噴「Invalid empty pathname」，程式碼目錄照樣解得出來；比一次 `tianxia/`、`content/` 的檔數確認。
  - 回報寫「差異只有哪幾行」，不是只寫「測試過了」。

## 內容改動的雷

- 內容載入時 `tianxia/content.py::validate` 會擋很多東西，改完一定要至少載一次正式內容（`real_content()` 或跑相關測試）。
  名字還要過命名過濾：不能跟素材、人物、隱藏配方、四階名器表、寶物撞名（新加的名器撞到 `tier4_named.json` 會整個載不起來）。
- **地點的 `enemies` 與地盤的 `garrison` 是兩回事**：
  - `Location.enemies` 是靜態的。探索事件的 `combat` 必須是那個地點 enemies 裡的隊伍（`test_explore_variety` 守），所以改 enemies 可能撞到別人寫好的事件。
  - 戰線地點實際站的隊伍看 `scenario.json` 的 `territory.garrison`（`territory.squads_at`），照控制方換。
  - 要調練功、出陣對手，優先改 garrison。
- 練功、找素材撞上的對手是「這裡不是自己陣營、難度最低的那一路」（`Game._gather_foe`），出陣守拿的是「經驗最高的那一路」（`_sortie_host`）。換一路隊伍兩邊都會動，回報時寫出連帶。
- 改了 `content/forge_secrets.json`、`per_season` 這類「池子大小」，會有測試與量表腳本寫死數量（配方總數、每季條數、`/13（` 這種字）。用 grep 找出來一起改。
- 新寫給玩家看的字一律標「待 joy 潤」，數字標【預設】或【暫】。不要改 joy 寫好的事件文字；真的非動不可先問 PM。
- 內容裡要照季換的字用插槽（`content/orders.json` 的 `{本週}`、`content/tutorial.json` 引薦人的 `{本週}`／`{每週}`，FB-502），填字的函式一個、載入時驗插槽；週末填完要跟原句一字不差。加了插槽，`test_real_content` 這類照原文寫死的斷言要一起改。
- **草稿 JSON 別留在 `content/` 底下**（2026-10-24 減法季批 4）：`tests/core/test_explain.py`、`test_explain2.py` 用 `content/` 的 `rglob("*.json")` 掃每一份內容檔（名望只准 `events/` 底下給、舊詞），設計分支帶來的草稿（`content/events_outcomes.json`）一放進來 `test_only_events_and_the_first_echo_give_fame_in_the_code` 就紅；併完就刪，還沒併的放計畫文件。
- **用腳本改 `content/events/*.json`**：這幾份是 `json.dumps(indent=2, ensure_ascii=False)`＋結尾換行（CRLF 轉 LF 之後一個位元組不差），讀成 dict 改完照原樣寫回是安全的；先驗「寫得回原樣」再寫（`scripts/merge_outcomes.py::_read`），`git diff` 看刪掉的行只該是被接上逗號的那一行。`locations.json` 不是這個寫法，別這樣改。
- **加新事件先看那個檔的結構測試**（2026-10-26 批 6 修正輪）：`explore_*.json` 一則只准一個地點、不准寫 condition（`test_explore_variety`）；`<大區>.json` 每個地點 1～2 則、整檔有事件數上下限、選項 2～3 顆（`test_events_new_regions`）；每個地點恰好一則有隨口應對的探索事件（加 `free_text` 就多一則）。要多地點、又不想動這幾條的新事件另開一個檔（`content/events/stances.json`），檔名補進 `tests/bots/test_silver_gates.py` 開頭的清單（`test_this_file_names_every_event_file`）。
- **一般選項（choices 的 effect）寫的痕跡要有說書段子轉述**（`test_socialize_variety::test_storytellers_retell_every_location_trace`：每一個都要在某則交友事件的 `any_of[].marks_min` 裡）；分岔後果（`free_text.outcomes`）寫的不算。沒有段子就別在一般選項寫痕跡，或另補一則交友段子。不經 `check_effect` 寫的痕跡（勸降的 `PersuadeDef.marks`）`content.validate` 不知道有人寫它，補痕跡規則時要自己登記進 `marks_written`（不然「沒有任何效果寫它」）；`test_marks_visible` 的「規則＝分岔痕跡、96 條」也要跟著算。
- **`zh.to_traditional` 退回手寫表時把「台」換成「臺」**：拿它驗「有沒有簡體」會把原事件的「灶台」誤判成簡體；比之前兩邊都把臺換回台。

## 規則改動的雷

- **一個動作同時寫全服登記與季**（2026-10-21 玉璽碎片第 2 批 `Game.seal_use`）：登記（`SharedWorldState.seal` 這種 world 那一列的東西）在 `self.world.mutate` 裡改、裡面整個重驗；季的東西（`WorldState` 的欄位、人物所在、天下大事）改在 `self.state.world` 上、最後 `self._save_season()`。不要在 mutate 裡改 `shared.season` 之後又拿著同步時讀的 `self.state.world` 繼續做事：之後誰叫 `_save_season()` 都會把 mutate 寫的季整份蓋掉（傳聞與江湖史例外，它們照流水號新增）。
- **開關還沒到就先做純規則**（2026-10-24 減法季批 2：批 0 的 `Config.jianfa` 在雲端側手上，兩邊各建一份一定撞）：數字放一個獨立的 pydantic 模型（新模組 `tianxia/jianfa_numbers.py`，自己的 `_Strict`、**不 import `models`**，之後 `models.py` 繼承或掛它才不會循環），純函式 duck-typed 收 cfg，測試直接建模型；不碰 `Config`、`content/config.json`、設定檔、`engine.py`。欄位名照計畫；計畫裡同一個名字既是子開關又是數字（`stat_milestones`、`explore_one`）的，數字那一邊改名，寫進計畫的 x.0。純規則要讀遊戲本身的升級表時（`team.level_cost`）在函式裡延後 import：team 之後會反過來 import 它。
- **開關與蓋章**：
  - 新規則多半是 `Config` 開關＋開季時蓋在 `WorldState` 的章（例 `precise.on(content, world)` 同時看設定、章、探索三選一）。
  - 判斷開沒開一定走那個 `on()`，要把 world/state 傳進去。只傳 content 時它會回假，悄悄退回舊說法（FB-435 就是這樣：傳聞沒給 world，寫回舊句）。
  - 改函式簽名加 world/state 時，grep 所有呼叫點一起改，包括 letters、figure_life、shopview、engine。
- **季種類對照**（週末 `weekend`、14 天＝不帶設定檔、21 天 `season21`）：
  - 新數字通常只寫在 `content/profiles/season21.json` 或 `Config` 預設。
  - 改之前想清楚三種季各會怎樣。派工沒說要動週末與 14 天就不動。
  - 測試用 `real_content("weekend")`／`("season21")` 各驗一次。7 天濃縮季是 `week7`（`season21` 骨架＋`season_segments`），只在那一季換的東西問 `calendar.week7_on`，寫「週／段」的字走 `calendar.week_word`／`week_label`，不要各處自己判斷。
  - **「段」與「每天」是兩個開關**（FB-502）：季曆有段只有 7 天季（`week7_on`）；軍令每天一道是照現實天的季（`calendar.orders_daily`，21 天季也是）。軍令的字放 `calendar.ORDER_KEYS`，其他「週」的字照段。網頁 `calWords()` 有值不代表 7 天季（21 天季也送軍令那幾個字）：段問 `wk7()`、軍令問 `ordersDaily()`。
  - **照現實天的季有開季偏移**：名義季末一律 `calendar.nominal_end`（不是季長 × DAY，FB-500、FB-505）；時刻表某一件「到了沒」一律 `timetable.when_in`（決戰照 `schedule`），不要用 `calendar.event_time`——決戰只寫星期鐘點、`day` 是 0，會被當成那一週第一天就到了（FB-504）。
  - **設定覆寫檔是淺層合併**（`content._config` 是 `{**config.json, **profile}`）：profile 寫 `"figure_life": {"revenge_cal_days": 2}` 會把 config.json 裡整塊 `figure_life` 換掉，沒寫的鍵回到 `Config` 預設。寫巢狀的覆寫之前先看 config.json 有沒有那一塊；測試驗一次「這一塊跟別種季只差這幾個鍵」（例 `test_week7_shortens_the_calendar_day_spans_pm_ruling_5`）。
- **說法要跟規則一起改**：
  - 規則換了，玩法說明（`howto.py`）、按鈕、懸賞說明、傳聞、書信裡的同一件事都要跟著改。舊季要一個字都不變，照開關分兩版。
  - 改完 grep 舊句子的關鍵字，找漏掉的地方。
  - 看的人不同說法不同（散人不出陣）：要看身分就把 state 傳進去。同一個「攻」也分站的地方（還沒人佔的中立地不是「這裡歸別人」、自家的大本營守不接「量是攻的一半」，FB-532、FB-533）：寫行動列底下那一行時，把每一種「這一塊此刻歸誰、搶不搶得下來」的組合各印一次看。
  - 鈕寫什麼就要給什麼（PM 裁決 18）：一個地方搶不下來卻標「攻」、畫 ⚔，就是鈕在騙人。要拿掉一種行動，從最底下回對手的那個函式（`conquest.sortie_foes`）擋，攻守、⚔、輿圖的出陣、攻城地點一起跟著變；有一種東西舊規則還靠它（截糧的運糧隊在長社），列出來留著、回報時寫明。
  - 灰掉的鈕括號裡那一句，網頁拿最後一小句當行動列格子的小字（不換行、10 px、格子約 60 px）：**最多六個字**（同「散人不能出陣」），八個字剛好頂到格子兩邊，320 寬就切掉。長的原因寫在行動列底下那一行（`action_notes`）。
- **新開關讓某個函式回空的，呼叫它的人可能把「空」讀成「做不了」**（領地爭奪第一批）：`Game.sortie_push` 開著時回 `{}`，行動列底下出陣那一行（`_sortie_line`）就寫成「今天這條線推滿了，推不動」；`sortie.ranger_here`、戰況圖卡與主線小標的說明還照 `territory.line_of` 判「這裡有沒有出陣」。換掉一個規則的計算時，grep 那個函式與它判斷用的舊條件（`line_of`、`train_trend`……）的每個呼叫點，連說明與按鈕的字一起看。
- **「基準＋偏移、顯示時夾 0～100」這種值，推的時候不要從夾過的值重錨偏移**（FB-530）：基準本身出得了牆時（領地爭奪分母只算中立，打進敵方陣營區塊基準就過 100），「新值＝夾過的值＋推量、偏移＝新值－基準」會讓每一推（連往同一邊推）都把偏移往回扣，基準越出牆扣越多；四捨五入過的值重錨也會讓偏移每推一下多走或少走半格。偏移照未夾的值加減，推過牆的那一截才丟（往牆推時最多推到 max(原本, 牆)），夾只在算顯示的值時做（`conquest.apply_push`）。測試要造一個「基準在牆外」的局面，推一下、再易手讓基準回到牆內，看值差多少。
- **畫面上列「去哪裡做會記到」的清單，跟真的記功要問同一個判斷函式**（FB-531）：軍令卡列攻城地點照「此刻歸敵方」，記功照「打贏的隊伍是敵方陣營」，兩個條件在大多數地方一樣、在被佔下的中立地（站的是沒有陣營的中立駐軍）不一樣，卡上就列了記不到的地方、假人也被它帶過去。把判斷抽成一個函式（`orders.siege_win`），記功與列清單（對那裡出陣會打的每一路都成立才列）都叫它；同一份清單假人（`win_counts`／`targets`）、發不發軍令、輿圖標記也都讀它，修一處就全對。守城同理（FB-565）：`orders.defend_places` 是唯一的查法，記功、`duty_counts`、`targets`、軍令卡、輿圖標記都問它；測試寫一條「每個地點上這幾個說法的集合要一樣」的迴圈（`tests/acts/test_conquest_flip.py` 的 `_agree`），別只測某一處的字。行動列底下那種「寫給玩家的原因」（FB-552 的「今天沒有公告攻城」）也是：原因要照規則真正的狀態分（沒排過、集結中、開打中、打完、作罷），不要拿一個布林（推不推得動）寫成一句，不然規則是對的、字不對。
- **「列與記同一個判斷」在這一下自己讓那一塊離開清單時會破**（FB-608，2026-10-21）：清單照「此刻推得動、進度最高」列，推滿易手、拉到零的那一下推完那一塊就不在清單上，先推後記就記不到最關鍵的那一下。記功照動作**之前**的清單判（先算好記功、那一句照舊排在推的那一句後面）；只在新規則的季挪，舊季（地盤照控制方判、先推線再記）順序不動，不然開關關著的對照會變。
- **清單上有「在那裡做 A 不算、做 B 才算」的地方**（FB-605：被戰書凍結的自家那一塊列進守城，只認攻城戰守住）：記功用不同的 kind 分（`orders.SIEGE_GUARD` 對 `duty`），`_counts` 照那一塊的狀態只認其中一種；一致性測試改成「清單＝各 kind 記得到的聯集、彼此不交」，卡上照 kind 分兩句寫。替一群人記功（攻城戰收場）時人不在動作裡：在 `mutate_season` 裡用 `_season_vehicle` 記，記之前讀他們的存檔確認是哪一邊（臨時投效、助守的不算），那一句訊息送不到本人。
- **不在選單上的玩家動作**（本週卡「換一件事」`step:next`，減法季批 3c）：`Game.choose` 先照選單重驗，不在選單上的一律「（此刻無法這麼做。）」；放進選單又會變成行動列一顆鈕、整季機器人「永遠按得下去」。做法：在 `choose` 最前面接走，而且要問那條規則的 `on()`——關著的季照舊落到「此刻無法這麼做」，不然關著的季回話變了。要灰鈕＋原因的（`faction:lean:<side>`）照舊放選單、`bot.pick` 與 `bot_policy` 的排除前綴各加一個。
  - **「選單上沒有也收」的動作**（減法季批 3c 修正輪 FB-812「改幫」隨時換）：在 `choose` 算出 `option` 之後、`None` 時補一條 `self._lean_anytime(option_id)`——從同一份 `_lean_options()` 撈那一顆（條件跟選單上的一樣），再加「賽季在跑」（籌備中、休季、時鐘暫停不收，這三種選單本來就只剩一顆灰的）。**兩層擋會回同一句**：第一層（選單那一關）回「此刻無法這麼做」不寫江湖紀錄，放進去之後被動作自己的檢查（`_lean_step`）擋，同一句話但多寫一則紀錄、`_begin_enlistment` 這些後續也會跑；測試不能只比回話，要比江湖紀錄筆數與狀態（`tests/map/test_four_wins_lean_anytime.py::_refused`），不然拿掉第一層沒有任何測試會紅。
  - **假人要走跟真人不同的值，但選單不能多一顆只有假人看得到的鈕**（FB-810，豪強假人全幫官軍）：選單上沒得挑，就在動作最後一步的引擎函式裡讀 `state.player.bot`（`Game._bot_lean`，確認那一下才數人，不是第一下按鈕；兩個假人先後按了還沒確認會挑同一邊），純規則放在 `wins.bot_lean`（雜湊鍵 名號＋季＋那一軍，不碰亂數）。伺服器假人整季跑的測試只要 `server_bots.is_online` 換成永遠在線（`bot_runner` 模組沒有 `is_online`），迴圈在豪強假人都投靠了就收（約 40 輪，不必 120 輪、省 70 秒）。
- **合進功能分支之後，別人的「測試整理」可能把舊規則的測試搬到你的開關開著的季**（2026-10-25 減法季批 3c：雲端的測試整理批 1 把 `test_gentry_allied`、`test_sortie`、`test_core_loop_*` 從週末搬到 `week7`，減法季開著，挑邊、改依附算叛投、攪局那幾條就被四勝利改掉、紅了 15 條）：照「舊規則的測試在 helper 裡把新開關關掉」補一行（`c.config.jianfa.four_wins = False`），斷言不動、註明為什麼。先在合進來的那一版 `git archive` 跑一次同樣的檔，分清哪些本來就紅（`test_renown_web` 四條在 `e13b7bff` 本身就紅，不是這一批）。
- **兩邊各做一份同一個畫面的資料**（2026-10-25：雲端批 1 已經用 `main.sides_card`、`main.week_card.steps` 送自己的形狀，這一批照計畫的欄位表又送 `main.step`、`main.sides`、另一個形狀的 `main.sides_card`，後者把前者蓋掉、網頁 `sc.cols.map` 直接壞）：合進來先 grep `server.main_view` 與 `web/*.js` 讀哪些鍵，撞名或重複的一律改成補在已經在畫的那一份裡（雲端留的位子，例 `HAOQIANG_NOW_PENDING`、`lean: None`、`week_unlock.win_gap`），欄位表改成實際的鍵；內部要帶參考資料就掛一個送出去之前一定拿掉的私有鍵（`_ref`，關著的季拿掉後一個字不變）。
- **pydantic 欄位的型別在檔案後面才定義**（2026-10-25：`JianfaRules.tiers: TierRules`，`TierRules` 在 `models.py` 檔尾）：把那個類別搬到用它的類別前面（接在別的類別後面、隔兩個空行，跟同時在改那個類別的批不相鄰），不要靠 forward reference 的延後重建。
- **管理者動作跟玩家動作不能同名**（FB-609）：`/api/do` 先查 `ADMIN_ACTIONS`，同名的玩家動作永遠走不到（玩家回 400「只有管理者能這麼做。」）；`tests/acts/test_conquest_siege.py` 鎖住兩張表與 `api_do` 先接走的那幾個不重名。新加管理者救場一律跟 `Game.admin_*` 同名。
- **拿掉一顆不靠對手的行動（守勢行動、第 2～4 階行動這類）：灰鈕＋一個 `*_problem` 函式**（領地爭奪裁決 24）：原因寫成純規則裡的一個函式（`sortie.duty_problem`：回灰掉的原因，給得了是空字串，關著也是空字串），選單那個函式（`Game._duty_option`）最先問它，灰著寫「{名字}（{原因}）」，跟用完次數同一種寫法。不用另外擋動作本身：`Game.choose` 照選單重驗，灰的按下去回「（此刻無法這麼做。）」、什麼都不扣；假人（`bot_policy.take_turn` 只收 `enabled`）、入伍段發光（`enlist.glow`，`server` 只傳 `enabled` 的 id）自然碰不到。測試三件：每一種「不是自家」的地方各一個（敵方大本營、敵方區塊、還沒佔下的中立地、廣宗）、按下去前後的快照要一樣（體力、出陣次數、戰線偏移、貢獻、軍令進度、江湖紀錄的筆數）、關著的季（週末、14 天、21 天）標籤一個字不變。
- **QA「順帶」寫的是那一輪 QA 的版本**：開工先用一支探索腳本（`tests/kit/conquest_kit.py` 的 `conquest_game`／`join`／`go` 擺人，印每個地點的 `game.options()`、按一下看快照）重現，再改。領地爭奪裁決 24 的順帶第 4 點（守城軍令把整條線算成目標、假人被帶去敵營）第二批就已經改掉了，只有第 1 點（守勢行動在敵營按得下去）還在；沒先重現會白寫一段已經對的程式。
- **給獎勵的路徑很多條**：打仗、出陣攻、出陣守與攪局、守勢行動、操練、挑戰本人的僵持、頭目戰、切磋、決戰軍餉、懸賞。改一種獎勵規則要逐條查。
  - 戰報的得失從 `record.exp/xinde/silver/materials` 來，江湖紀錄的數值從回傳的訊息來，「剛剛」卡片把兩邊相減畫剩下的。兩邊對不上，就會多一顆紅的「心得 -N」或算兩次。
  - **`_record_exp` 回的「心得 +N」只能進回傳的訊息，不能進 `record.notes`**：notes 會和得失再接一次，同一份算兩次（FB-451、FB-453）。
  - 戰報欄位用加的（`record.xinde = (record.xinde or 0) + x`），不要覆蓋，前面可能已經加了別的（FB-450）。
- 會不會先升級再轉換這類順序問題（例：滿級換心得要在 `add_exp` 之前判），寫一條「剛好升到頂的那一下」的測試。
- 擲骰一律用自己的亂數（`random.Random("用途|季數|名號|戰報流水號")`），不碰 `Game.rng`：整季測試與量表的序列才不會位移。
- **改一個會被 monkeypatch 的函式的參數**（2026-10-25 減法季批 2：`team.add_exp` 多一個 `source`）：`tests/seal/test_seal.py` 用四個參數的 lambda 換掉它、`scripts/measure_exp_pace.py` 的 Ledger 包著它，`grant_team_exp` 一傳五個參數兩邊都炸（只在跑到那幾條時才紅）。新參數放在有預設值的尾巴、內部呼叫照舊用舊的個數（來源先在別處驗），改之前 grep `mock.patch.object(<模組>, "<函式>"` 與 scripts 裡 `<模組>.<函式> =`，包裝的函式一律收 `*args, **kw`。
- **每季不同的數字要穿過一串不收 state 的函式**（減法季每點加倍：`team.neili_cap`、`_cap_of`、`neili_ceiling`、`member_neili`、`regen_neili`、`_apply_toll`）：加 `season=None`（`state.world`），沒給照舊；每一個呼叫端都要給，漏一個在新規則的季就是「狀態列寫的上限跟打起來的不一樣」。寫一條測試把狀態列、角色卡、決戰的池子、本人氣血幾個數比在一起（`tests/battle/test_stat_milestones_engine.py::test_hp_cap_is_one_number_everywhere`），再拿新開關關著的整份畫面對照證明舊季一個位元組不變。
- **`PlayerState` 加進 `QUIET_DEFAULTS` 的欄位**：`tests/core/test_gentry_ledgers.py::test_new_fields_add_no_keys_until_used` 現在照整個 `QUIET_DEFAULTS` 減（以前寫死只少兩個鍵），之後加欄位不必再改它；自己那一批另寫一條「預設不寫、有值寫得回來、舊存檔讀得進來」。
- **動作中間要改全服狀態**（例：探索撿到碎片，`Game._seal_find`）：用一次 `self.world.mutate(...)`，寫入時整個重驗；只想補天下大事或江湖史就寫在 mutate 裡的 `shared.season`（傳聞與江湖史只增不減，動作結束的 `_save_season` 不會蓋掉）。**不要**在動作中間把 `self.state.world = self.world.get_season()` 換掉：這個動作前面對 `self.state.world` 的就地修改還沒存，會一起丟掉（決戰收場那幾處這樣換是因為前面沒有未存的修改）。
- **新的全服登記欄位（`SealRegistry` 這類）在開季才寫**：寫的地方有三個進入點——`seed_first_season`（自動開季）、`open_season`、`next_season`；沒蓋章的季連登記都不要碰（`filled(...)` 也會改登記），舊的季才一個字不變。
- 資料庫結構（第 5 版）不改，要改先問 PM。新狀態欄位加在 `PlayerState`／`WorldState`，舊存檔讀得進來。
- **`PlayerState` 新欄位要「關著的季存檔一個鍵都不多」**（減法季批 3c，2026-10-24）：`CharacterStore.save` 是 `state.model_dump_json()`，每個欄位都寫，加一個有預設值的欄位，每個角色的 JSON 就多一個鍵。`PlayerState` 有一個 wrap serializer（`_drop_quiet_defaults`），把欄位名加進 `state.QUIET_DEFAULTS`，空的、0、None 的時候就不寫那個鍵（讀檔沒有這個鍵就是預設值）。測試照 `tests/core/test_gentry_ledgers.py::test_new_fields_add_no_keys_until_used`：預設時 JSON 的鍵＝`model_fields` 減掉這幾個與 `exclude=True` 的、有值時寫得出來讀得回去、拿掉鍵的舊存檔讀得進來；拿掉 serializer 裡那一行跑一次看會紅。
- **也要讓舊程式讀得進新存檔**（FB-695，2026-10-22：上線之後出事要退回上一版）：加欄位沒事（模型沒設 `extra`，舊程式略過、寫回時丟掉），**往舊程式也有的 `Literal` 加值不行**（碎片登記 `SealEvent.kind` 加 `use`，舊程式讀 world 那一列就 `ValidationError`，伺服器、假人程式都起不來）。新的種類另開一欄、空的時候用 wrap serializer 把鍵拿掉（**不用 `Field(exclude_if=…)`**：Pydantic 2.11 才有，`requirements.txt` 是 `pydantic>=2.6`，舊版略過它、空的照寫）、讀檔時 before 驗證器搬舊資料（見 `docs/guide/核心與存檔.md`）。查有沒有這種改動：`git grep -n "Literal\[" <舊版> -- tianxia/` 與 HEAD 各存一份、去掉行號 diff。實測退回：`git archive <舊版>` 解到 scratchpad，包一支 `serve.py`（`sys.path.insert`、`os.chdir` 到那一份、`server.CONTENT.config.ollama_url` 指死埠、`server.main(["--port", 埠])`）與 `bots.py`（`run_bots._wait` 換成不等、`run_bots.main(ticks=N)`），新程式寫的資料庫抄一份給舊程式開；**抄之前先 `PRAGMA wal_checkpoint(TRUNCATE)`**（`taskkill` 掉的伺服器留著 `-wal`，只抄 `.db` 會少掉最近寫的）。假人程式要另外拿一份「舊伺服器還沒碰過的」抄本先開（舊伺服器一啟動就把 world 那一列寫回去了，之後才開的假人程式讀到的已經是舊程式的樣子）。腳本在 PM 那個 session 的 scratchpad `fb695/`（`setup_roll.py`、`serve.py`、`bots.py`、`probe.py`、`inspect_db.py`）。
- **全服戰鬥不只一場了**（領地爭奪第二批：攻城戰跟時刻表決戰同時打，`SharedWorldState.sieges`）：引擎裡讀「這個人的那一場」用 `Game._battle_now()`（假人程式、bot_policy 用 `game.battle_now()`），改它用 `_mutate_battle_of(battle, fn)`，全部列出來用 `battles_now()`；**不要再寫 `world.get_battle()`／`world.mutate_battle()`**，除非真的只講時刻表決戰（璽動、管理者的決戰工具、`_settle_showdown`）。新的 `SharedWorldState`／`BattleInstance` 欄位照舊要分進 `tests/server/test_server.py` 的推送指紋表。
- **存進全服狀態的「現實時間」一律用 `self.now`，不要用 `pill_now()`**（FB-577，2026-10-21）：`pill_now()`＝`now`＋`advanced_real`，管理者快轉推的 `advanced_real` 只活在那一個 `Game` 物件的記憶體裡；拿它寫進共用狀態的時刻（`XingshiTicket.opened_real`、`retry_at`），別的 `Game`（伺服器排程 `world_tick`、別的玩家）拿自己的 `now` 比，會差上快轉的那十幾個小時。換天、回體丹換日這種「快轉跨過了就該算」的判斷才用 `pill_now()`（`conquest_day.day_key` 有「日子只准往前走」擋著）。測試：一個 `Game` 先 `advance` 跨過換天開單，另一個 `Game.for_world` 照現實時鐘 `world_tick`，看單有沒有照寬限收。
- **「設定裡有、章上沒有」的值（`season_weeks`、`season_segments`）：畫一季的時刻、週數、季曆長度時，函式要收 `season`**（FB-635，2026-10-21）：上一季是舊程式的週末式季曆（章上 `season21` false），新程式的設定已經是照現實天的，直接讀 `content.config.season_weeks` 會把上一季的每個時刻照新季曆寫（休季換程式、開下一季之前才看得到：開了季就蓋新章）。`calendar.weekend_style(season, content)` 判斷（只管休季；還在跑的舊季時刻表與曆時交界仍照新設定走，只換畫面會跟大事對不上，不換）、`calendar.weeks/total_days/cal_scale/point/week_start/calendar_end` 都收 `season`；新寫「按季曆算」的函式照辦，不要再讀 `content.config.season_*`。測試用差異法：同一季（舊內容開的）、同一個世界秒，新內容與舊內容各算一次要一字不差（`tests/test_fb635_rest_season_calendar.py`）；重現要走「舊內容開季→`admin_end_season`→新內容 `Game.for_world` 讀同一份資料庫」整條，單看 `stamp_text` 看不出狀態列的 `weeks` 與輿圖 `weeks_total`。還讀設定沒動的：`rules.decisive_week`、`stance_rule_note`、`checkin.last_day`、`timetable.finale_default`（跑著的舊季本來就不該換程式，PM 定的是休季才換）。
- **啟動時印的警告（`server.main`、`run_bots.main`）的測試**：`uvicorn.run` monkeypatch 掉、`server.PROFILE`／`server.CONTENT` 換成要試的設定、`server.main([])`；假人用 `monkeypatch.setenv("TIANXIA_PROFILE", …)`＋`run_bots.main(ticks=0)`；`capsys` 看輸出。要試的狀態有四種：全新資料庫（什麼都沒種，`open_world().season_phase()` 是 preparing）、`seed_first_season` 種好沒開、`open_season` 用另一份設定開了、同一份設定開了；警告函式收的是 `season_phase()`，不是從 `WorldState` 猜（全新資料庫讀回來的季是沒蓋章的空殼，章上 `season21` false，會跟任何 season21 的設定對不上；`tests/figures/test_season21_frame.py`）。
- **加 `WorldState` 的欄位也要分進 `tests/server/test_server.py` 的 `FINGERPRINTED`／`NOT_IN_THE_FINGERPRINT`**（2026-10-24 減法季批 4 `marks_fired`；不只 SharedWorldState、BattleInstance，`test_every_shared_world_field_is_classified_for_the_push_fingerprint` 三個模型都守）。空的時候不寫進 JSON 用 wrap serializer（`WorldState._drop_empty_marks_fired`）；內容模型的新欄位同理（`models._drop_unset`：`Effect.contribution`、`Check.stats`、`FreeTextChoice.outcomes`、`Location.desc_marks`、`Content.mark_rules`）。
- **新的模型呼叫要「怪值一趟就收」，用 `schema_required=`、不用 `required_fields=`**（減法季批 4 `event_llm.classify_outcome`）：`chat_structured` 的 `required_fields` 把 `null` 當成被截斷、會重問一趟（假的 `requests.post` 量到兩趟）；`schema_required` 只寫進送出去的 schema、不進缺欄位檢查。要模型只填清單上的 id：`create_model("X", __base__=X, outcome=(str, Field(default="", json_schema_extra={"enum": ids})))`（`event_llm._judgment_for`），讀回來照舊再認一次清單（`outcome_of`）。
- **變異檢查別寫等價的變異**：整數的 `a < b` 換成 `a <= b - 1` 是同一件事，測試當然不紅；換邊界就寫 `<` → `<=`。
- **給三段式加一條新路（`server.py`）**（2026-10-25 減法季批 4 接線）：`tests/server/test_server.py::test_only_the_out_of_lock_steps_enter_the_model_queue` 靜態檢查**只准名單上那十幾個函式**叫 `model_call`，抽一個 `_answer_branch` 輔助函式就紅——新的 B 段寫在原本那個函式裡（`if request.outcomes: … else: …`）。同一個檔有好幾條測試把 `Game.answer_event` 換成固定三個參數的 lambda：C 段**只在新路上**多傳參數，舊的那一行呼叫一個字不動（也順便讓「關著不變」不必另證）。
- **「關著不變」的對照腳本要證明抓得到**（同批 4 接線）：同一支探針把開關打開跑一次，確認跟 base 差得出來（這一輪關著三種季各 594～607 行一個位元組不差、打開 season21 差 608 行），不然雜湊一樣只代表探針沒走到改的地方。探針只印兩版都有的欄位（新加的 `FreeTextOutcome.outcome` 不印、`FreeTextRequest` 只印 `event_id`、`text`），內容的新痕跡（人拉犁那三條）不放進季上，不然季的 JSON 一定不同。腳本在 PM 這個 session 的 scratchpad `jianfa-4-wire/cmp_off.py`＋`cmp_run.py`（`python cmp_run.py [none weekend season21-off season21]`，兩份 archive × 每種季平行跑，約三分鐘）。
- **兩層保護的變異會存活**（同批 4 接線）：善惡只在歸到最後一種時看——`moral` 先換成「中」、`evil = fallback and moral == 惡` 再擋一次，拿掉後一層測試不紅；確認是故意的兩層就寫進回報，不必硬補測試。
- **「上一篇以來」的事用「讀到第幾條」記起點，不要用世界秒**（減法季批 4 修正輪，〈天下形勢〉的痕跡那一類）：拿 `at >= 上一篇的世界秒` 切，同一個世界秒發生的兩件事（開單與過門檻、測試的固定時鐘）邊界上不是重複就是漏；起點記成「那時清單有幾條」（`XingshiMark.fired`，同 `log`、`rumors`），切 `list(marks_fired)[起點:]`。拿掉一條「補漏」的路（世界層傳聞）時，先想清楚它原本補的是哪一段（開單到收下之間），改起點到「開單那一刻」。新欄位 0 的時候用 wrap serializer 不寫鍵（嵌在 `xingshi_mark` 裡的小模型也行）。鎖測試要同時跑「世界秒不動」與「世界秒往前」兩種；每一條要斷言「出現在所有篇裡的總次數剛好 1」。**一天的事實超過 `facts_max`（30）時尾巴會被切掉、起點照樣往前**：這一類跟其他類一樣沒有補送，要補得另外記「實際寫進去幾條」。
- **一件事拆成幾個 commit，檔案卻有幾件共用時，不要動工作樹**：寫一支 scratchpad 腳本，每個 commit 從「工作樹的最終版」把別件的幾處換回舊字（每處 `assert count == 1`）、`git hash-object -w --stdin --path` ＋ `git update-index --add --cacheinfo` 放進索引，commit 後工作樹照舊；提交前 `git write-tree` 取出索引的 tree，`git archive` 解到 scratchpad 跑那幾個測試檔，確認單獨一筆也是綠的（2026-10-25 批 4 修正輪，`engine.py`、`models.py`、導覽、`test_outcomes_answer.py` 都三件共用）。
- **`branch_game(faction="guan")` 之類的測試會多一則 `annals.DEED`「投靠官軍。」**：斷言行狀的字要先篩「隨口應對」，不然 `== [..]` 多一筆。
- **QA 的 `qcmp.py` 比的是行號**：上游少了幾十行（例：拿掉 93 則傳聞）後面的表（chronicle、seasons）整片位移、全算差；先看差的行數是不是剛好等於少掉的行數，再用 tag 與內容確認，不要把位移當成真的差異。
- **新模組的名字撞到 `from .rules import` 的函式，模組會被靜靜蓋掉**（2026-10-26 減法季批 6）：`engine.py`、`world.py` 都 `from .rules import (…, stances, …)`（陣營的態勢），新模組 `tianxia/stances.py` 用 `from . import stances` 匯進來，排在後面的 rules 那一行把它換成函式，`stances.figure_of` 就是 AttributeError。這兩個檔裡新模組一律取別名（`from . import stances as stance_rules`），加之前 `grep -n "\b<名字>\b"` 看一次。
- **給共用函式加參數，舊的呼叫一個字不動**（同批 6，跟批 4 接線的 `answer_event` 同一個坑）：`tests/server/test_server.py` 好幾條把 `companion_agent.generate_turn` 換成只收三個參數的假函式，`prepare_turn` 一律多傳 `stances=` 就紅 11 條。新參數只在有值時才傳（`generate_turn(..., stances=ids) if ids else generate_turn(...)`）。`chat_structured` 的呼叫點也一樣：`tests/bots/test_schema_required.py` 照原始碼的字掃每一個呼叫點（第二個引數要寫得出類別名），把 `CompanionTurn` 改成 `X if … else CompanionTurn` 就紅——新的回答格式另開一個呼叫點（`if stances: … else: <原本那一個>`）。
- **測試開季之後先推一個小時再擺季上的東西**（同批 6）：`open_season` 那一刻世界秒是 0、`hooked_week`／`hooked_day` 都是 0，第一次補算才跑第 1 週與第 1 天的掛鉤——在那之前寫進季的東西會被第 1 週的歸零清掉（要連「這是哪一週」的記號一起寫），每天的掛鉤也會多跑一次（量到拉了兩次）。測掛鉤的效果前先 `at(g, g.now + HOUR)`，斷言 `hooked_day == 1`。
- **`GameState` 的 JSON 不含季**（同批 6）：季另存（`world.save_season`），`GameState.model_validate_json(state.model_dump_json()).world` 是空殼；季的新欄位拿 `WorldState` 自己序列化、讀回來驗。
- **給玩家的情誼走 `_apply(Effect(affinity=…))` 會照 `affinity_gain_scale` 放慢**（同批 6：託付寫 +5、實得 +4）：要跟事件給的同一條就照用，測試寫 `renown.warmed(c, 5)`；要給整數就另寫，回報寫明。
- **「關著不變」連送給模型的東西一起比**（同批 6，`scratchpad/jianfa-6/cmp6.py`＋`run6.py`）：探針裡放一個假 client，`prepare_turn` 時記下 `model.model_json_schema()` 與 kwargs 印出來——提示詞一樣不代表 schema 一樣（加一個有預設值的欄位，schema 就多一個 property）。新欄位只在開著時用 `create_model(__base__=…)` 的子類別加（`companion_agent.turn_model`），關著送出去的一個位元組都不多。批 6：不帶設定 923 行、season21 關兩個子開關 508 行逐位元組一樣，全開差 511 行。
- **合功能分支的語意撞點：一邊的「收尾」函式改寫另一邊塞進來的東西**（2026-10-26 批 6 修正輪合批 3c）：3c 的 `step.finish` 照每一件的 `_ref` 補 `target`、沒有 `_ref` 的寫 null，批 6 的託付那一件自己帶了 `target`、沒掛 `_ref`，四勝利開著就被洗成 null。文字沒撞、自動合併，只有跑兩邊的測試才紅（`test_errands_weekcard`）。合之前把兩邊各自往同一份輸出加東西的地方（本週卡 steps、`main_view` 的鍵）列出來對一次。
- **「關著不變」要分清楚每一件修正掛在哪個開關**（同一輪）：FB-820 掛在 `four_wins`，不在 `stances`／`errands` 後面，所以「season21 關這兩個子開關」那一份照樣差那幾行（探針放了「豪強事件待選時改幫」）；再跑一次連 `four_wins` 也關，證明差的只有它。探針要另放一段專打那一處，不然雜湊一樣只代表沒走到。
- **有一個「另外擲的」對手（頭目）不要算進「這裡有沒有對手」**（減法季批 2 修正輪 FB-815，2026-10-26）：`_outing_plan` 把頭目也算 `has_foes`，只有頭目的地點遭遇那一格就留著、遭遇拍一定撞上他（長社官軍 400 趟 387 趟）。唯讀的計畫（比重、鈕上的小字、假人打分數）只看一般對手；頭目在做動作時另擲一次（亂數用「頭目」這個新用途，不動別的序列），擲中才把遭遇拍放進這一趟（`explore_one.draw(bounty_here=True)` 的「第一拍就是遭遇」，比重改回 `has_foes=True` 那一份）。測試兩條：一趟的機會約 5%（`_duel_start` 換成只記一筆、連出 400 趟、斷言落在一個帶子裡），以及把倍數拉到一定擲中（`renown.duel_chance` 回 20）斷言**每一趟**都有頭目——只有後一條抓得到「擲中了卻沒有遭遇拍」的變異。
- **新規則改了一句話，用正式內容 week7／season21 斷言舊句子的舊測試會紅**（同批 `test_core_loop_fb.py::test_fb250`）：`test_for` 挑得到、grep 舊常數名（`RANGER_LINE_PRECISE`）也找得到；在那一條測試開頭叫 `jianfa_kit.classic_explore(game.content)` 鎖舊句子，新句子的斷言放在新規則自己的測試檔，不改舊斷言。
- **兩局測試各有一份內容**：`conquest_kit.conquest_game()`（同 `test_territory._game`）每一局各載一份 `real_content` 的複本，同一個資料庫開兩局時，在測試裡往內容加東西（例：借一份戰鬥範本）要兩局都加，不然第二局找不到、畫面靜靜地沒有那一場。
- **輿圖上標的「攻」「推薦」要跟按鈕問同一個函式，測試逐處站過去**（減法季 3b 修正輪 FB-855，2026-10-26）：`Game.map_state` 的 `mode()` 以前只問 `sortie.mode`，約戰開著時貼不貼得了要問 `conquest.push_problem`（跟 `sortie_go_problem` 同一個）；開季推薦的三處，兩處站過去那一格是灰的。測試別只比 `places[*].sortie` 的字，迴圈把人 `seat` 到每一處推薦（與每一處標攻的地方），斷言 `sortie_go_problem() is None` 且 `act:train` 的 `enabled`（兩軍 × week7／season21）；另擺一條「有截糧運糧隊經過的照舊是攻」（`Order(template="intercept")` 掛在不相連的敵方地方）。
- **約戰結算的帳照貼（應）那一刻的陣營，不照結算那一刻的傾向**（FB-856）：`SortieSide.side` 已經是快照（同去要同一軍，`join_problem`），夠用就不加欄位；`wins.credit(side=)`、`_order_credit(side=)` 都要帶（豪強窗內 `faction:lean:<side>`，結算時 `p.ally` 已是新的那一軍）。測試的順序：貼→（應）→改幫→`tick`，斷言 `p.ledgers`、兩軍同種軍令的 `progress` 一起比成一個元組，修之前才看得到每一項都錯（攻城軍令要兩軍在 LOC 的進度一樣高、守城軍令要黃巾在官軍的涿郡推過一截，`_today` 才認那一處）。
- **`SharedWorldState` 加欄位**（2026-10-25 減法季 3b-1 的 `sorties`）：world 那一列是 `model_dump_json(exclude={"season", "active_battle", "sieges"})` 整份寫，加欄位不必改 `sqlite_world._load`／`_save`；「空的時候不寫鍵」在 `SharedWorldState._drop_empty_sorties`（wrap serializer）多判一個鍵就好。另外三件一起想：換季要不要清（`next_season`）、暫停繼續要不要把現實時刻往後挪（`resume_clock`，同 `seal_duels`）、輪詢要不要只讀那一格（`json_extract`，同 `seal_state`）。`tests/server/test_server.py` 的 `NOT_IN_THE_FINGERPRINT` 裡 `SharedWorldState` 那一組到 `siege_records` 就結束，緊接著是 `WorldState` 那一組（`seal_acts`、`xingshi_*` 是季的）——加在 `seal_acts` 後面會進錯組，分類測試報「沒分類」。
- **招名是中文**：`tactics.counter`／`best_against`、`models.MOVES`／`BEATS` 認的是強攻、固守、奇襲（選項 id 也是 `duel:強攻`）；設計稿寫的「以巧破力」就是奇襲。撤退不在 `BEATS`，`tactics.counter("撤退", …)` 會 `KeyError`，有撤退的回合要自己判 0。
- **欄位表上的鍵先 grep 畫面在讀什麼**（2026-10-26 減法季 3b 接線）：計畫寫「出陣前那張卡放 `main.sortie`」，可是 `main_view` 早就有 `"sortie": sortie.on(content)`（布林，`web/main.js` 拿 `m.sortie` 把行動列那一格叫「出陣」）。換成 dict 雖然還是真值，型別就變了——卡改放新鍵 `main.sortie_card`，欄位表那一列改成實際的鍵、回報寫給雲端。行動列那一格的選項 id 也一樣：網頁 `ACT_CELLS` 認 `act:train`，新規則沿用它（按了只回一句、不花體力，同探索的入口），不另開 `sortie:card`。
- **從 `CharacterStore` 讀出來的別人沒有季**（`GameState.world` 是 `exclude=True`，讀回來是空的 `WorldState`）：拿別人的存檔問跟季有關的規則（`allied.side_of` 判豪強依附哪一軍、`team._fighters` 算威力）之前先 `state.world = self.state.world`（`_kin` 就是這樣做的）。3b 接線第一版漏了，豪強的假人一個都補不上約戰（`allied.on` 讀到空季回假，side 變成 `haoqiang`）；`tests/acts/test_sortie_duel.py::test_a_gentry_bot_leaning_on_the_other_army_fills_in` 守。
- **`BattleRecord.kind` 是 Literal，新的一種戰報不要加值**（FB-695：舊程式讀不進新存檔）：照舊用現成的 kind（例 `sortie`），種類的字寫在 `BattleRecord.label`（戰報上寫的種類，空的照 `battlelog.KIND_WORDS`）。
- **照現實秒走的規則，整季機器人推不動**（`Game.advance` 只加 `advanced_real`、不動 `now`）：約戰的窗、冷卻照 `self.now`（FB-577：存進全服的時刻不用 `pill_now`），`bot.play_season` 裡永遠不到時，貼了就等季末作廢。量表與測試照伺服器的做法一步一步 `sync(now)`（`scripts/measure_conquest.py`）。
- **參數放不進選單的玩家動作**（約戰封三招有 64 種組合，2026-10-26）：同 `step:next`，在 `Game.choose` 最前面接走（先問那條規則的 `on()`，關著照舊「此刻無法這麼做」），各自在 `world.mutate` 裡重驗；伺服器另開 `MAIN_ACTIONS` 走同一組 `Game` 方法。整季機器人與假人挑到的是選單上那一格（`act:train`），在 `bot.pick`／`bot_policy.take_turn` 最後換成帶參數的 id（`bot.duel_go`），不然按了那一格什麼都不做、每一步都白按。
- **拿掉一顆行動，輿圖的疊層也要跟著拿**（2026-10-26 3b 收尾：約戰開著時沒有「守」）：行動列那一格、行動說明、玩法說明都改了，`Game.map_state` 傳給 `mapdata.state` 的 `sortie_mode` 還照 `sortie.mode` 回 `"hold"`，地點卡就畫「出陣・守」、「今天去哪裡出陣」照樣推薦、還寫「軍令・守城」。grep 那個規則函式（`sortie.mode`）的每一個呼叫點，輿圖那一處也要問新開關。
- **別的批的計畫可能把一件事記在你這一批頭上**（2026-10-26 3b 收尾：7b 的計畫 8.0 寫「各批的寫入點：3b 約戰結算 → `DUEL`」，3b 自己的那幾節沒寫，約戰一直記 `annals.FIGHT`）：收尾前 grep 整份計畫的批號（`3b`、`約戰`），不只看自己那一節；功能分支合進了別批，再 grep 一次合進來的那幾節。
- **伺服器排程的實機（窗、逾時這種現實時間）**：抄一份設定檔到 scratchpad、把那個窗改短（約戰 `"sortie": {…, "window_minutes": 1}`，`sortie` 這一塊在 `config.json` 沒有，淺層合併不會蓋掉別的），先在 `TIANXIA_DB` 用一支小腳本 `seed_first_season`＋`open_season(now=time.time())`，再 `Start-Process` 開伺服器；兩個帳號用 httpx 各一個 Client 走 API，**中間不輪詢**等窗滿，直接讀 world 那一列看是不是排程收的（2026-10-26 3b 收尾，scratchpad `jf3b/live/`）。
- **結算時替好幾個人寫紀錄**（約戰的攻方、同去、應戰的人）：每個人一份 `Draft` 掛在他那一份 Game 上（`_order_credit` 的引導、`_file_battle` 的結果標記都寫進它），做完 `journal.add_entry(g.state, g._draft.entry(...))`、`finally` 還原；自己就是其中一方時用自己（不要另讀一份，不然存檔會被蓋掉），別人 `_load_kin` 改完 `_save_kin`。掉落用這一場自己的亂數：暫時把那一份 Game 的 `rng` 換掉、`finally` 換回。
- **同一筆數值同時放進回傳訊息與 `Draft.changes` 的 helper，呼叫端又兩邊加總就會兩倍**（減法季批 2 小修 FB-830，2026-10-26）：`_drill_gains`／`_town_drill` 慣例是「訊息放『心得 +N』、`_draft.hide(那一行)`、`_draft.changes.append(那一行)`」（江湖紀錄的標籤由草稿記、敘事裡收掉那一行），`_outing_ledger` 卻把 `msgs` 與 `_draft.changes[since:]` 都加進去，比劃那一趟「得：」寫 +22（實際 +11）。修法是給 helper 一個 `echo` 旗標（出門一趟的比劃傳 False：只由草稿記；沒有草稿時照樣放進訊息，直接叫的人才不漏帳），別的呼叫端不動。**網頁不畫回傳的訊息清單（`web/` 沒有讀 `log`），玩家看到的是江湖紀錄**：QA 說「多一則單獨的訊息」是看回傳清單看到的；測試要同時斷言訊息清單、帳那一行、`journal[0].changes` 三處，並加一條通則「帳上的數值＝紀錄標籤」跑每一種拍（`tests/battle/test_explore_one_polish.py::test_the_ledger_numbers_are_the_numbers_the_journal_chips_show`）。
- **「獲得 …」開頭的訊息不全是東西**（FB-831）：素材、拾遺囊、伏筆物品是「獲得 名 ×N」，破境丹與回體丹是「獲得 【名】一枚／一顆——說明」加一行「名 +1」；帳上只列「名 ×N」的（`explore_one.is_item`），其餘用「名 +1」那一行。新加一種稀有掉落照這兩行的寫法，帳不必改。
- **把畫面上的字改成照規則的實際比重寫，會連帶改到別的地點**（FB-832）：`plan.weights` 已經夾過危險度，一律照「最重的一類」寫，不只 QA 抓到的兩處（長社官軍、洛陽官道黃巾）變，寺類（事件 50 > 感悟 30）、危險度高的山與渡口也變（46 組）。改之前用一支「每一處 × 四種身分」的前後對照腳本（scratchpad `jianfa-2c/s/hints_all.py`，base 與 HEAD 各解一份）列出所有變動的組合，再回報 PM。PM 的裁決是以地點種類的字為主（跟輿圖名字旁的 `MOSTLY`、玩法說明的 `HINTS` 一致），只有招牌類（`explore_one.SIGNATURE`）此刻的比重是 0 才改寫，最後只變兩組；測試用「每處 × 四種身分，變動的集合正好是這兩處」鎖住。
- **`HintDef` 加一種變體句**（例 `explore_one`）：`hints.note_for` 取 `rules.jianfa` 要在函式裡延後 import（`rules` 很大，`content` 也 import `hints`）；`content.validate` 的 `{名字}` 檢查那一串與「引薦人的條不寫」要一起加；`tests/season/test_real_content.py` 的 `_hint_cells`、`PLACEHOLDER_LINES`、句數（37→38）要一起改。
- **測伺服器的背景執行緒（`server.write_zhuan` 這種三段式）**（減法季批 7b，2026-10-26）：A、C 段進 `server._locked` 會照 `open_characters()`（`TIANXIA_DB`）重讀角色，測試裡同步記下的東西（季末論功那一則行狀）沒先 `CharacterStore(...).save` 就丟了，`biography_request` 回 None、執行緒安靜結束、沒有 traceback。`jianfa_kit.jianfa_game` 開的是自己的暫存資料庫（不是 `TIANXIA_DB`），走伺服器那一條的測試改用 `wins_kit`（世界照 conftest 的 `TIANXIA_DB`）。新的背景模型呼叫要當假人排（`QUEUE.run(..., bot=True)`）時，`tests/server/test_server.py::test_only_the_out_of_lock_steps_enter_the_model_queue` 鎖著誰碰 `QUEUE`，函式名要加進那一張表。
- **商城的 `MallItem.draft` 只是給作者的備註，不擋上架**（同批）：要某一種季才賣，用 `MallWindow.rule`（子開關名）＋`phases`／`from_week`，引擎照 `Game._mall_moment()` 傳 `mall.Moment`；不加 `mall_entitlements` 的種類（CHECK 只有 card／pass／look，加了就是改結構），票就是購買那一列，用了記在那一列的 `data`（`Wallet.mark_used(pid, t, **extra)`）。
- **「有沒用的票」＋「這一季用過了」兩層擋的變異會存活**（同批）：一季限購 1，測試只買一張，用完票就沒了，拿掉「這一季用過了」那一層沒有測試會紅；用 `Wallet.add_purchase` 直接塞一列「上一季剩下的票」再看鈕有沒有出來。
- **內容模型加欄位**（`FactionDef.verdict_by`、`Content.verdicts`）：照 `models._drop_unset` 的 wrap serializer 把空的拿掉（`Content._drop_new_defaults` 的鍵表加一個），測試內容序列化一個鍵都不多。
- **接手一批被停掉的半成品，先找上一位的暫存資料夾**（減法季批 7b 收尾，2026-10-26）：交接寫的「停在哪」是 PM 從上一位最後一則訊息摘的，可能已經過時（7b 寫「停在列傳請求的接線」，其實那一段已經提交，上一位停在跑 `test_for`）。`ls -d /c/Users/ray61/AppData/Local/Temp/claude/*/*/scratchpad/<派工寫的暫存名>` 找得到它（不一定在 PM 這個 session 底下），裡面的 `picked.txt`、跑到一半的 log、`head.tar` 的時間對 `git log` 的提交時間，就看得出做到哪一步；對照腳本照抄來用。核對還是照派工的每一條 Task 對程式一條一條看。
- **事後夾的上限（`Game._log` 裡才夾的情誼這種）會在「一過門檻當下就給東西」的地方漏**（同批：深交上限）：動作中途就看門檻給獎勵的（對話裡 70 教本命武學 `companion_agent._maybe_grant_signature_skill`、80 送名將本命兵器 `Game._signature_arms`），在 `_log` 之前就給了，之後才被夾回去。加這種上限時 grep 那個門檻的每個讀者（`signature_affinity`、`weapons.signature_affinity`），在讀之前先夾一次（`Game._deep_cap_now`，句子留到 `_log` 才說）；共用函式加的回呼照「舊的呼叫一個字不動」那一條，只在新規則的呼叫點傳。測試照真的路走（`choose("talk:0", prepared=PreparedTurn(...))`、動作前把情誼直接寫過門檻再 `choose`），修前要紅。
- **`test_explain` 連交給模型的字串也掃**（同批）：「好感」「交情」在 `tianxia/`、`server.py` 的任何字串常數都不准（說明字串與 `companion_agent.build_system_prompt` 例外），`content/` 只准名單上那兩處；新寫的模型提示、商城說明一律寫「情誼」。`test_for` 挑得到它（改了 `tianxia/` 就挑），挑到了才知道。
- **購買那一列就是票的東西，「綁季」看購買的 `season` 欄位，不是 `data.season`**（減法季批 7b 修正，FB-845）：`data.season` 是用掉的那一季（`mark_used` 才寫），沒用的票沒有。`mall.tokens(season=)`、`zhuan_end.unused(season=)` 篩 `Purchase.season`，用票也拿同一季的那一張，不然舊季的票排在前面（`tokens` 舊的在前）會被先用掉。測試塞一張 `season=0` 的舊票再買一張新的，斷言用掉的是新的。
- **「這個人這一季用不上就不賣」走 `mall.Moment.blocked`**（商品 id → 原因，`Game._mall_moment` 算；同批 FB-845）：`buy_problem`（排在限購後面，已經買了的人聽到的是限購）和 `view`（灰掉寫原因、`max` 0）都讀它，貨架與購買才一致。季中看不出的事（第幾階）不擋，只擋看得出的（沒陣營）。
- **派生的名單能從「寫成的正文」認就別另存**（FB-847）：評曰名單改從傳的段首（`zhuan_end.VERDICT_HEAD`，產段落與認段落共用同一個常數）認，退款、重修自動對得上，資料庫結構（第 7 版）不動；還沒寫成時才用票預告。
- **固定句要「整篇一起挑」**（FB-848）：每位各自雜湊挑，撞句機率擋不掉（池子 3 句、4 位一定撞）；改 `fixed_verdicts(writers)` 同理由輪著挑、用過的跳過、不夠往別組借、全用過才重複；`check_verdicts` 加「各組不重複」，池子夠不夠用測試鎖（深交三位加名額一位＝4）。
- **內容說明裡照季換字的插槽**（FB-849 的 `{上架}`，同軍令的 `{本週}`）：填字函式一個（`mall.note_text`，7 天季用 `calendar.segment_days`、其他季照舊的字），`item_problems` 驗插槽認得、需要的欄位有寫；測試把「說明寫的那一天」跟真的上架那一刻（前 10 分鐘沒有、後 10 分鐘有）綁在一起。
- **一批好幾張小單、測試各一個檔最省拆 commit**（減法季批 7b 修正）：每張自己一個測試檔＋一個共用 kit（`tests/kit/zhuan_fix_kit.py`），照「寫測試→看紅→修→變異→commit」一張一張來，不必拆 hunk。變異腳本 `scratchpad/jf7bfix/mutate.py <根> <檔> <測試檔,…> '<舊>' '<新>'`（舊字串單引號、挑不含雙引號的片段，斷言剛好一處、`finally` 寫回）；關著對照 `scratchpad/jf7bfix/cmp_driver.py <base.tar> <head.tar> <資料夾>`（兩份 `git archive` 用 QA 的 `qajf7b/cmpq/cmp_qa.py` 五種平行跑，約十幾分鐘）。
- **「買來的東西不給數值」不另存欄位，用名單位置判**（減法季批 7c，FB-860；深交名額 2026-10-28 下架、這段程式拿掉了，做法留著參考）：靠買來的深交名額進名單的人＝`zhuan_end.deep_list` 裡排在 `deep_figures` 之後的（`zhuan_end.by_slot`）。存下來的名單（`PlayerState.deep_order`）只在有人新過門檻時才整理，中間有人掉下去它就是舊的，所以**讀的地方照此刻的條件再濾一次**（`deep_list` 濾掉情誼已經掉下 70 的），不要直接讀存檔裡的順序；名單裡有人讓出位子，後面的人自動遞補成「名單內」。要擋的讀者還是 grep 那個門檻的每一處（對話教本命武學 `companion_agent._maybe_grant_signature_skill`、名將本命兵器 `signature_arms.due`，奪走那條路跟情誼無關、別擋）。擋了不記旗標（`學會本命:`），位子讓出來之後才教得成；說明那一句放在**進名單那一下**（`enforce_deep_cap`，只會跑一次），不放在每輪對話的路上，也不要放進 `_gift_entry` 這種把第一句當標題的列表。
- **驗「動作最後那幾步」不要連按同一個動作**（同批）：`choose("act:explore")` 常撞上事件，下一個 `choose("act:explore")` 只回「（此刻無法這麼做。）」、什麼都沒跑，測試看起來像規則沒作用。要在同一局連驗兩次「動作尾端的檢查」，直接叫尾端的函式（`game._deep_cap_now(); game._signature_arms()`，就是 `Game.choose` 在 `_log` 前叫的那兩步），或按完事件的選項再按。
- **變異檢查抓不到的，補一條會抓的測試再比一次**（同批）：「進名單那一下的說明連免費那幾位也說」一開始沒被抓到（測試只斷言靠名額的那一位有說），補「名單內三位不說」的斷言就紅了；「`withheld` 永遠 True」要補「沒東西可扣的人物不說」才抓得到。變異腳本在這一輪 scratchpad 的 `mutate7c.py <工作樹> <相對檔> <測試檔> '<舊>' '<新>'`，一行一個、舊字串必須剛好一處、`finally` 寫回；PowerShell 傳多行舊字串直接寫單引號跨行就行。
- **關著對照的腳本可以重用上一批的**（同批）：`Get-ChildItem C:\Users\ray61\AppData\Local\Temp\claude -Recurse -Include cmp7b.py,cmp_qa.py` 找得到前幾輪留下的（`jf7b/cmp/cmp7b.py` + `cmp_run.py`：解兩份 tar、五種平行跑、逐行比）；抄到自己的 scratchpad，只改要比的東西（這一批多印商城每一列的說明，免得說明字串在關著時漏出來）。**全開那一種行數不同時逐行 zip 比會整片錯位**（報 460 行不同其實只差十幾處）：另寫一支 `difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()` 分塊（800 行幾秒就好），逐塊看是不是預期的差。

## 量表怎麼讀

- 量表只量不改，數字照實報，不為了好看調參數。PM 說「量一次就好」就量一次。
- `scripts/measure_exp_pace.py`：
  - 量的是「最認真、不合成不修練」的人，威力一路停在 35 上下，練功一點體力只換 2～3 經驗。
  - 它挑的練功點偏弱（對強的對手勝率太低），所以看不出「最好的練功點」差多少，也會低估會合成的玩家。
  - 看結果要連它印的每天威力一起看。要比練功點，另外照威力 60／90／120／160 算「對手經驗 × 勝率」。
  - 回報時兩種讀法都寫，讓 PM 定。
- 一次跑很多組要很久（21 天 × 四方約 25 分鐘），背景跑。跑的時候不要改它會讀的內容檔（每一組重新載內容）。
- **量表跑之前擋模型**：scratchpad 寫一支包裝（把 `socket.socket.connect`／`socket.create_connection` 對 11434 的連線改成拒絕、`OllamaClient.from_config` 換成回 None，再 `runpy.run_path` 那支量表），量表的 `print` 包在 TextIOWrapper 裡，導到檔案時跑完才看得到（減法季批 2 的 `run_blocked.py`）。
- **新規則多了一種「要選」的狀態，量表的迴圈要跟著了結**（減法季批 2：出門一趟的感悟拍會進有所感的「畫一筆」）：`measure_exp_pace._settle` 以前按選單第一顆，碰到 `sensing.DRAW` 只回「在畫布上畫」、迴圈空轉到上限，一天只出門兩趟；改成照整季機器人 `bot.sense_pick`／`bot.sense_draw`。先跑一天看一眼數字合不合理再背景跑整季。
- `measure_difficulty` 的練功走法在減法季可能卡死：銀兩花光、內傷疊到氣血不到一半就不出門、付不起醫館，整季停在第 6 級（2026-10-25 season21 solo 種子 1，季在第 17.7 天收了，一個停點都沒量到）。照實報那一組，不要為了好看換種子不說。
- **`scripts/measure_conquest.py`（約戰開著的季 20 人一季易手幾次）很慢**（2026-10-26 3b 收尾）：week7 一季一個種子單獨跑約 5 分鐘一天、整季 55～70 分鐘（八個平行時也是），season21 整季 2.5～4 小時（看同時開幾個）。從 `git archive HEAD` 解到 scratchpad 的那一份跑（量表跑的時候你還要改工作樹、合分支），一支 Python 調度腳本平行開好幾個種子與倍數（`PYTHONHASHSEED=0`，每個子行程自己的 `TIANXIA_DB`），先拿 `--days 1` 看一眼合不合理。同一個種子同一份程式結果一樣（不設雜湊種子也一樣），種子之間差很大（week7 倍數 30：6～11 次），一個倍數至少三到五個種子才下結論。
- **接手暫停的批，先找上一位開發的 scratchpad**（2026-10-26 3b 收尾）：`ls -d /c/Users/ray61/AppData/Local/Temp/claude/*/*/scratchpad/<批名>*`，探針（`cmp_off.py`）、量表的半成品（空的輸出檔就是被暫停打斷的那幾組）都在，照用、不必重寫。
- **量貢獻別用 `measure_exp_pace` 的「最認真」**（2026-10-25 減法季批 3c）：它每一下挑經驗最多的（出陣守、練功），領地爭奪的季守推不動就不記，三天量出來是 0；只挑「攻」又常常打不贏（估的勝率偏高）。要量「認真玩幾天累積多少貢獻」改用假人的打分：建角色、`p.bot = BotProfile(personality="積極", …)`、每次同步之後一直叫 `bot_policy.take_turn` 到它回空的，貢獻照每一下前後的 `contrib` 差、記到那一下江湖紀錄的標題（腳本在當時 scratchpad 的 `jianfa-3c-wire/measure_contrib2.py`）。

## 回報 PM

- 一張回饋單一個 commit；commit 訊息一句英文，結尾 `Co-Authored-By:`（照當時 system 給的那一行）。
  - **幾張單改在同一個檔、甚至同一個函式裡**（2026-10-21 玉璽碎片改版第 3 批：批本身與 FB-627 都改 `seal_acts.view`）：不必把工作樹改回去再改回來。寫一支 scratchpad 腳本：讀工作樹的檔（CRLF→LF）、照「拿掉哪幾處」換掉（每一處 `assert count == 1`）、`git hash-object -w --stdin --path <檔>` 寫成 blob、`git update-index --add --cacheinfo 100644,<blob>,<檔>` 放進索引——工作樹一個位元組不動，`git diff` 剩下的就是下一張單。先提交最大的那一批，再一張一張 `git add`。每一筆提交之後 `git archive HEAD` 解到 scratchpad 跑那幾個測試檔，確認單獨一筆也是綠的。
  - 同一個檔裡有兩張單的改動：先用 Edit 把第二張的那一段暫時改回去、`git add` 只放第一張的檔、提交，再把那一段改回來提交第二張（備份一份完整檔到 scratchpad，改回來之後 `diff` 對一次）。
  - **整批做完才拆成每個 Task 一筆**（2026-10-25 減法季批 3c 接線：`engine.py`、`server.py`、`state.py` 三個 Task 都改）：寫一支 `stage.py <工作樹> <階段>`，每一階段的檔＝工作樹的最後版本拿掉後面幾階段的段落（`cut(頭標記, 尾標記)` 整段、`sub(舊, 新)` 一行，每一處斷言剛好一處），`git hash-object -w --stdin --path` 寫 blob、`git update-index --add --cacheinfo` 放進索引；照順序提交，每一筆之後 `git archive HEAD` 解到 scratchpad 跑那一階段的測試檔。最後一階段提交完 `git diff HEAD -- tianxia server.py tests` 要是空的。
  - 提交完才發現前一張要補（例：測試完決定收窄範圍）：補的檔 `git commit --fixup <那張的 hash>`，其餘沒提交的先提交成一個 docs commit（工作樹不乾淨 rebase 會拒絕），再 `GIT_SEQUENCE_EDITOR=true git rebase -i --autosquash <base>`（沒推出去才這樣做；hash 全變，回饋單的「已修 `<commit>`」等重寫完才填）。
- 推之前合派工指定的分支（衝突兩邊都留）。推完用 `git merge-base --is-ancestor HEAD origin/<分支>` 確認推到了。
  - `天下大勢` 這份 clone 的 `remote.origin.fetch` 只寫了 main 等三條，**`git fetch origin` 不會更新 `origin/dev/*`、`origin/feature/*`**（2026-10-20：推上去了，`origin/dev/conquest-1` 還停在舊的那一版，上面那一行就判成沒推到）。推完先 `git fetch origin refs/heads/<分支>:refs/remotes/origin/<分支>` 再比，或直接看 `git ls-remote origin refs/heads/<分支>`。拿 `origin/feature/<名字>` 當 `test_for` 的 base 之前也照這樣更新一次。
  - 這份 clone 的 `remote.origin.fetch` 只列 `tianxia`、`feature/sanguo-companions`、`main`：`git fetch origin`（或 `git fetch origin <分支>`）**不會**更新 `origin/dev/*`、`origin/develop`，推完馬上比會假失敗、開工時讀到的也可能是舊的。要比之前先 `git fetch origin +refs/heads/<分支>:refs/remotes/origin/<分支>`，或直接 `git ls-remote origin refs/heads/<分支>` 對 `git rev-parse HEAD`（2026-10-20 商城第二批修正那一次）。
- **疊批合回上一批的修正**（`dev/<x>-2` 合 `dev/<x>-1` QA 之後的 FB 修正；2026-10-20 領地爭奪第二批合第一批修正）：
  - 衝突多半是同一個判斷兩邊各改一半：上一批的修正收緊條件（攻城只算打贏敵方陣營的隊伍，FB-531），這一批換掉來源（攻城地點改成今天公告的目標，還放寬成「中立駐軍也算」）。照 PM 定的疊法，兩個條件都套在**列清單**與**記功**兩邊（同一個判斷函式），不要只把兩段文字接起來。疊出來的代價（例：只公告中立地的那一天攻城軍令記不到、也不發）寫進計畫交 PM。
  - 上一批修正帶進來的測試是照上一批的前提寫的（任何搶得下來的區塊都推得動進度、攻城地點不看時程表），**自動合併、沒有衝突標記，照樣會紅**：合完、提交合併之前先跑兩批的測試檔。補上這一批的前提（例 `conquest_kit.announce` 先公告那一塊），不改斷言，測試檔開頭寫一句為什麼。
  - 兩邊各寫了同一個節號（兩個「6.2」）：都留、照 commit 時間排（`git log -1 --format=%ci <sha>`），不重新編號（回饋單寫著「計畫 6.2」），合併怎麼解另起一段接在最後。
- **換掉一套機制的批合回還照舊機制往前做的功能分支**（2026-10-21 輿圖第三版第 1 批 dev/flip-1 合 feature/territory-conquest：這一批拿掉投票與 22:00 公告、改成戰書；功能分支那邊同時做了第三批 A、B、FB-552、FB-565）：
  - 文字衝突照新機制解，但**沒衝突的那幾處更要看**：功能分支新加的程式可能 import 已經拿掉的東西（`state.Pick`、`howto.SORTIE_SIEGE`、`conquest.progress_open`），合完先 `python -c "import server"`、再 grep 拿掉的名字（`progress_open|conquest_vote|SORTIE_NOT_TODAY|…`）。
  - 功能分支帶進來的測試拿舊機制當前提（`conquest_kit.announce` 當「這一塊被公告要攻」；翻地之後它等於那一塊被戰書凍結、守不動）：前提換成新機制的等價（`conquest_kit.press`：對面在那裡推了一截），斷言不動、檔頭寫一句為什麼；斷言本身鎖的是舊機制的字（FB-552 的「今天沒有公告攻城」）就照新機制改寫那一檔，檔頭寫原本鎖什麼、現在鎖什麼。
  - **反過來，功能分支帶進來的是內容的地理改動（區塊表、路）**（2026-10-21 dev/flip-1 QA 修正合輿圖第三版第 2 批區塊表 v3）：這一批自己的測試寫死了舊表的地點 id 與種類（嵩山深處是中立、汝南荒野是黃巾的、黃巾碰得到荒丘），自動合併沒有衝突、照樣紅一片。合完先印一份每一塊的種類與兩邊開季的 `conquest.targets`（scratchpad 的小腳本），紅的照新表換成同樣形狀的地點（兩邊都碰得到的中立地、對面開季的陣營區塊），斷言不動、檔頭寫一句。
  - 合併提交只放「解衝突＋讓帶進來的測試照新前提跑」；計畫裡寫好「合進來時接上」的介面（〈天下形勢〉的新句型、碎片問冷卻）各一個 commit、先寫會紅的測試。合併提交當下還紅、要下一個 commit 才綠的測試，寫在合併的 commit 訊息裡。
- 回報寫：
  - 每張的 commit 與一兩句怎麼修。修前重現了什麼。
  - 跑了哪些測試、幾條過。
  - 順手改的東西另列，讓 PM 決定留不留。
  - 數字照實寫，有疑慮直接講。
  - 只做被要求的事；看到別的問題先報，不自己擴大範圍。
- 收尾交接：分支與 HEAD、沒提交或沒推的、開著的伺服器或背景程式（埠、PID，關掉）、還開著的 FB、踩過的坑、這一路改了 CLAUDE.md 或 `docs/guide/` 的哪幾條。
