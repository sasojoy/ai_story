---
name: tianxia-dev
description: 《天下大勢》開發一批或修一張回饋單之前先看：工作樹與指令的坑（CRLF、Bash 被擋、共用的 stash）、test_for 怎麼挑測試、內容與規則改動常踩的雷（garrison 對 enemies、開關與蓋章、季種類、_record_exp）、量表怎麼讀、回報 PM 的格式。分支與合併的規矩看 tianxia-flow，各區塊的規則細節看 docs/guide/。
---

# 天下大勢：開發子代理的實務手冊

這一份只寫「怎麼做才不踩雷」。分支、合併、什麼時候跑整套：`tianxia-flow`。某一塊規則現在怎麼運作：`CLAUDE.md` 指到的 `docs/guide/` 那一份。網頁（`web/app.js`、`style.css`、店面、桌面版字級）另見同資料夾的 `網頁.md`。

## 開工

- 先 `git worktree list`、`git remote -v` 核對自己在哪一份 clone、哪一條分支（這台有 `天下大勢`、`ai遊戲` 兩份）。
- 一批一個工作樹，從派工指定的分支開（多半是 `origin/feature/formal-season`）。分支名照派工寫的。
  如果是 `git worktree add -b` 開的，要加 `--no-track`，或開完 `git branch --unset-upstream`：不然它跟著功能分支，`git push` 可能推錯地方。推的時候一律寫明 `git push origin <你的分支>`。
- 工作樹沒有 `.venv`：python 用 `C:/Ray/專案/天下大勢/.venv/Scripts/python.exe`，PowerShell 呼叫。（Bash 另外會拒絕 `git -C .`〔路徑要寫死〕與 `"...python.exe" --version` 這種「指令名算出來的」；Bash 的 heredoc 寫 python 時字串裡的反斜線 n 會變成真的換行，寫腳本一律用 Write。Git Bash 的 `git show <版本>:<路徑>` 會被 MSYS 的路徑轉換弄壞〔`ambiguous argument 'origin\dev\…;…'`〕，前面加 `MSYS_NO_PATHCONV=1`。）
- **派工要你載的技能或設計稿不在這條分支上**（2026-10-21：`tianxia-map-remake` 與 `2026-10-20-輿圖簡化-design.md` 只在 `develop`、`origin/design/map-simplify-3`，`feature/territory-conquest` 與它開出來的 `dev/blocks-2` 都沒有）：`git log --all --format='%h %ci %D' -3 -- <路徑>` 找最新的那一版，`git show <那一版>:<路徑>` 讀（設計稿存到 scratchpad 再 grep），不要為了讀它把檔加進自己的分支（之後合 `develop` 會變成兩邊都新增的衝突）。
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
- **TIANXIA_DB**：每次跑測試、跑腳本都設到 repo 外一個新的暫存檔（`$env:TEMP\tx_xxx.db`）。舊的資料庫會讓測試假失敗。
- **git stash 是所有工作樹共用的**，別的 session 也在用。
  - 不要裸 `git stash` / `pop`。
  - 要用就 `git stash push -m <獨一無二的標籤> -- <檔>`，`git stash list --format='%H %gd %gs'` 找到自己那一筆，`git stash apply <sha>`，再照標籤找 `stash@{n}` 去 drop。
  - 想證明測試「修之前是紅的」，最簡單的就是這樣把改動暫時收起來跑一次。
- **用 `python -I` 跑腳本時 `PYTHONIOENCODING` 不生效**（`-I` 忽略所有 PYTHON 開頭的環境變數）：在腳本裡 `sys.stdout.reconfigure(encoding="utf-8")`。
- **實機看畫面**：PM 會給你一個埠與 `<名字>.localhost`（別的子代理同時在跑伺服器，cookie 照主機名分開）；瀏覽器窗格是共用的，**每一個動作都帶自己的 tabId**，看完把視窗設回 desktop、關掉自己的分頁、`taskkill /T` 關伺服器。窗格在背後時截圖可能拍到動畫中途，數字用 `javascript_tool` 量。
- **這台的 Ollama 沒有 `gemma4:12b`**（只有 26b 等舊模型，2026-10-20 查的）：真模型實測叫不動就照實回報；不要改拿 26b 代跑（17GB、keep_alive 12 小時會一直佔著顯卡）。
- **開伺服器又不能打到 11434**：模型網址（`Config.ollama_url`）沒有環境變數可改，設定覆寫檔照派工指定的（例 `week7`）就不另寫一份。在 scratchpad 寫一支包裝：`sys.path.insert(0, 工作樹)`、`import server`、`server.CONTENT.config.ollama_url = "http://127.0.0.1:9"`、`server.main(["--port", 埠])`，用 `Start-Process` 跑它（`TIANXIA_DB`、`TIANXIA_PROFILE` 照設在 PowerShell 裡，子行程繼承）。角色在每次建 `Game` 時才照設定建 client，所以先改再 `main` 就全部指到那裡（FB-490～493 這一輪）。
- **實機要某一步的角色**（例：初入江湖第一步）：`/api/register`＋`/api/character` 建一個（密碼產生後寫進 scratchpad 的檔），再用 `CharacterStore.load`／`save` 改 `tutorial_step`（與 `location`）存回去；伺服器每次進鎖都從資料庫重讀，不必重開。序章那幾步（0～10，含出師那一步）要 `location` 是 `mentor_hut`，不然 `m.prologue` 是 None、看起來像出了草廬。
- **計畫要對現行程式**：派工給的計畫可能是照 main 或更早的版本寫的；開工先核對，差異寫進計畫，前提不在了就停下來回報 PM。
- 背景長跑（量表）用 `run_in_background`。輸出導到檔案時 python 會緩衝，加 `-u` 才看得到進度。等它結束的通知，不要輪詢。
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
- **不要寫帶中文路徑的 `.ps1`**：Write 工具寫出的 .ps1 沒有 BOM，Windows PowerShell 5.1 照 ANSI 讀，`C:/Ray/專案/…/python.exe` 變亂碼、每一行都 CommandNotFound（2026-10-20 背景跑對照表踩到，log 只看得到一串錯）。要串好幾個 python 程式，就寫一支 Python 調度腳本，用 `sys.executable` 叫子程式，再從 PowerShell 跑那一支。

## 測試怎麼挑

- 平常只跑 `scripts/test_for.py --base <base>`（含 slow），或直接 `pytest 改到的那幾個檔`。整套留給合併的人。
- **base 要選對**：
  - 跟你的分支開出來的那一點比，通常是 `origin/feature/formal-season`。
  - 你自己合了別的分支進來時，base 用合完那一個 commit，只量你這一輪的改動，不然會把別人的東西全挑進來。
  - `--list` 先看挑到哪些檔。
  - **合併還沒提交時別拿 `--list` 的清單**（2026-10-21 輿圖簡化第 2 批收尾）：`test_for` 跟 base 的分岔點比，`--no-commit` 合進來的東西都還算「沒提交的改動」，合功能分支的那一下挑到 327 個檔（幾乎整套）；先跑兩批的測試檔、提交合併，再 `--list` 只剩這一批自己的 117 個。
- 改到 `tianxia/engine.py` 幾乎會挑到大半套（八千多條、約 6～8 分鐘），正常。只動內容或小模組時會少很多。
- **`test_for.py -- -n 4` 擋不住 `-n auto`**（2026-10-20 領地爭奪第三批 A）：挑到三個檔以上它自己在最後補 `-n auto`，排在 `--` 之後的參數後面，pytest 照最後一個算。派工要 `-n 4`（同時有好幾個子代理在跑）時，在 scratchpad 寫一支小腳本 `import test_for`、拿 `test_for.pick(test_for.changed_files(base))` 的清單自己叫 pytest（`-q -m "slow or not slow" -n 4`，`TIANXIA_DB` 設新的暫存檔），背景跑、輸出導到檔。PowerShell 一行就夠：`$line = (& $py scripts/test_for.py --base <base> --list | Where-Object { $_ -like '要跑：*' }) -replace '^要跑：',''; $files = $line.Trim() -split '\s+'; & $py -u -m pytest @files -q -n 6 -m "slow or not slow" | Out-File $env:TEMP\x.log`（2026-10-21 玉璽碎片改版修正：改 `engine.py`＋`state.py`，挑到 303 個檔）。
- **兩張單的測試寫在同一個檔、又要一張一個 commit**（2026-10-21 FB-606、607 都在 `test_conquest_clash.py`）：先把第二張的測試從檔尾剪到 scratchpad（照第一個 `def` 的名字找頭、連前面的空行一起剪），提交第一張，再接回去寫第二張的實作。不要裸 `git stash`。
- 新測試超過一秒（建 `Game`、載真實內容通常就超過）標 `@pytest.mark.slow`。
  **直接 `pytest <檔>` 時 slow 預設被排除**（pyproject 的 addopts）：整個檔都是 slow 就會「no tests ran」、結束碼 5，要加 `-m "slow or not slow"`（`test_for` 自己會加）。
- **新測試綠了不等於有用，拿掉實作的一個條件跑一次看會不會紅**（變異檢查，2026-10-20 領地爭奪第三批 B）：用一支腳本「換掉一處、跑那個測試檔、換回來」。三個坑：
  (1) 換回來用的反向替換要先確認「換掉之後的字串」在檔裡剛好一處，不然斷言失敗、檔案留在改壞的狀態（短字串例如 `return msgs + self._legend_find(...)` 換掉一處之後會變兩處）；
  跑之前先 `git diff --stat` 記一下，跑完再看一次；
  (2) 拿掉一個條件測試沒紅，先看是不是「兩層保護」（例：`Game._seal_find` 的藏處檢查在擲骰前、寫入重驗各一次，拿掉一層本來就不紅），是的話改拿掉兩層、或確認這兩層是故意重複；
  (3) 測試裡用的「不該發生」的前提要真的分得開兩個原因（例：天命之季不藏的測試，七片全隱沒時「沒東西可藏」也會是空的，要留一片未現世才測得到「因為天命之季」）。
- **證明「祕密沒漏出去」用差異測試**：建兩個只差那個祕密的世界（例：碎片藏在 A 或藏在 B），比畫面、API、江湖史、傳聞、管理者的回話與玩家的存檔是不是一個字不差；不要在輸出裡找祕密字串（地名到處都有，找不到也不代表沒漏）。
  同一條測試裡把開關關掉再比一次、斷言「關著時看得出差別」（列出哪幾項不一樣），才證明這條測試抓得到漏（玉璽碎片改版第 1 批 `test_two_worlds_that_differ_only_in_the_holder_look_the_same`）。要找名號字串時，名號別跟固定的字撞（拿「懷璽」當持有者的名號，會撞到「懷璽之人」），用「甲客」「持璽客」這種。
- **差異測試要讓「世界差在祕密、後面的步驟不被結果帶開」**（玉璽碎片改版第 1 批修正，側門）：兩個世界裡誰贏誰輸、誰掉了氣血會不同，之後算威力的步驟（氣血係數 `condition` 也在 `_spar_power` 裡）就跟著差，測試紅了不是漏而是被結果帶開。做法：先把所有「看」的畫面讀完再打；每個人至多打一場有損耗的仗（截殺各挑沒打過的人）；擂台挑了就認輸（`arena:yield`，結果固定是落敗、名次不動）；只比「對手那一格」的數字，不比勝負與氣血。
- **差異測試抓不抓得到，用「還原漏洞」證明**：當祕密只在子開關開著時存在（關著本來就看不出差別），不能靠「關著看得出差別」那招，改成 `monkeypatch` 把防線拆掉（例：`Game._spar_power` 不理 `seal`、`_arena_bare` 回 None），斷言兩個世界在該有的鍵上真的不一樣（`test_the_side_door_guard_has_teeth`）。另外對實作做變異檢查：一處一處換掉、跑那組測試、看會紅；腳本把原檔 bytes 存在記憶體、`finally` 寫回，比反向替換安全（不會因為換回去的字串不唯一而卡在改壞的狀態）。
- **給別人看的數字（勝算、身手、戰報的「對手威力」）每一處都要走同一個「給別人看的那一份」**：選單、玩家卡、頁面（`shopview`）、戰報兩邊各一份（發的與收的、守的與挑的）、假人讀的勝算清單；寫在存檔裡的快照（擂台分身）要另記一份，欄位加預設 `None`（舊存檔讀得進來、沒碎片時狀態不多一個字）。算這個數字的時機要排在記戰報之前：第一邊的記帳可能升級，第二邊再算就變了（`_spar`、`raid`、`_ambush_fight` 都在算 `ours`／`theirs` 的同一處先算好）。
- **一包 `**kwargs` 的標記（`Game._battle_marks` 這種）加新鍵**：有舊測試斷言整包一字不差（`test_joining_snapshots_turncoat_and_newbie`）。新鍵只在有值時才放進去，關著的季那一包一個字不變。
- **「關著一個字不變」的畫面對照，探針只問兩版都有的東西**：問到新版才有的效果鍵，舊版當成加的（中性值 0）、新版當成乘的（中性值 1），雜湊就不一樣，但那不是畫面。改問掛點本身的輸出（扣血、內傷、價錢、回話）。玉璽碎片改版第 1 批的腳本在當時 scratchpad 的 `sealcmp/cmp_seal_off.py`（七片各一個持有者、第一個是假人；三種季各 204 行）。
- **修 bug 先寫會紅的測試**：先確認它在修之前真的失敗、失敗的數字跟 QA 回報的一樣，再修。回報時寫「修前重現了什麼」。
- **「確認並守住」的測試**（程式沒改、一寫就綠，例：假人不買商城的東西）：要證明它抓得到退步，另寫一個暫時的測試檔 import 它，monkeypatch 一個退步（例 `bot_policy.take_turn` 先叫 `mall_buy`、`social.card` 多塞一個「元寶」），跑一次看它紅，再刪掉那個暫時的檔（不提交）。
- 用正式內容測舊規則的測試，要在 helper 裡把新開關關掉（例 `c.config.precise_actions = False`、`four_tiers.enabled = False`）。新規則另開一個測試檔，不要改寫舊的斷言去迎合新規則。
  例外：PM 的裁決直接推翻還沒上線的這一批的做法（不是開關後面的舊季）時，鎖住舊做法的那一條斷言照裁決翻過來，註明哪一條裁決、新規則的測試在哪一個檔（例：裁決 19 之後 `test_siege_void_when_no_attacker` 改成「沒有作罷的天下大事」，新的在 `test_conquest_void_quiet.py`）。
- 江湖紀錄 `state.journal` 新的在前（index 0）。找某一則照標題找，不要拿 `[-1]`。`_write` 寫的那一則，「銀兩 +N」這種數值變化在 `entry.changes`、不在 `entry.lines`。
- **兩個人的測試**（截殺、領地爭奪的混戰，2026-10-20 翻地與爭搶）：`Game.new` 不存角色，另一個人要被 `_load_kin` 讀到就先 `CharacterStore(world.db).save(game.state)`；
  照伺服器的做法每一個動作從資料庫重讀自己（`tests/test_raid.py::_do`、`tests/test_conquest_clash.py::_do`）。season21 的新手期看 `newbie_real_hours`（現實 48 小時），
  只設 `newbie_days = -1` 擋不掉，要一起設 `newbie_real_hours = 0`。
- **證明開關關著一個字都不變**：一條條「關著不變」的測試之外，最省事的是拿 QA 的整份畫面對照（`tianxia-qa/引擎驗收.md` 第 7 節；scratchpad 裡 QA 留過 `conqqa/cmp_off.py`）：開這一批之前那一版與 HEAD 各 `git archive` 一份跑，比雜湊。腳本 `import server`，所以要連頂層的 `server.py server_push.py zhuan_html.py llm_queue.py console.py` 一起 archive（只 archive `tianxia content` 會 `No module named 'server_push'`），**`web` 也要**（`server` 載入時讀 `web/index.html`，沒有就 `FileNotFoundError`）。領地爭奪第一批修正：season21／week7／weekend 三種季 573／569／567 行一個位元組都一樣。
  **base 選對**：派工寫的對照版（例 `98c1c0f5`）之後，功能分支又合進了別的批（輿圖 v3 第 2 批 `b9ee3c9c`）時，你合進來之後拿舊版比，畫面會差在那一批動的東西（小地圖多一條路，不是你的改動）。先拿合進來的功能分支 tip 當 base 比到一個位元組不差，再另外拿派工寫的版本比一次、把差異歸給那一批（`diff` 看出差的位置）。玉璽碎片改版第 1 批修正：側門整條（卡、勝算、擂台選單與頁面、切磋、截殺、擂台各打一輪的整份戰報與回合演出）45 行、三種季，`98c1c0f5`／`b9ee3c9c`／HEAD 三版雜湊一樣；碎片全套 204 行，`b9ee3c9c` 對 HEAD 一樣，`98c1c0f5` 對 HEAD 只差輿圖 v3 那條路。
  - **改內容的地理（`locations.json` 的路、描寫）不看任何開關**：加一條路，三種季的輿圖、小地圖、那兩處的「前往」鈕與路程、描寫全都跟著變（輿圖簡化第 2 批的宛城—綠林山寨：開關關著的三種季每一季 85 行不一樣）。對照腳本要多擺人站在路的兩頭、把 `g.options()` 也寫出來才看得到；兩份輸出比對時長的那幾行（svg 十幾萬字）用「去掉共同的頭尾」印差的那一段，`difflib` 會跑好幾分鐘。這種差異是內容的決定，寫進計畫交 PM，不要自己加開關擋。
    要證明「除了那條路一個位元組都不差」：把新版的 `content/locations.json` 抄進舊版解出來的那一份（只換這一個檔），拿它跟新版比雜湊（2026-10-21 develop 合進領地爭奪：四種季、碎片改版關著，新版跟「develop＋那條路」雜湊一樣）。
  - 更完整的一支是 flip-1 QA 留的 `qa_cmp.py`（八個人、兩軍同地出陣、十二輪同步、快轉跨過 22:00、一場決戰、截殺帳、季的 conquest 與 xingshi；PM 這個 session 的 scratchpad `flip1qa/`），用法 `python -I qa_cmp.py <archive 根> <輸出檔>`，兩份平行背景跑各約 5 分鐘。2026-10-21 `b9ee3c9c` 與 dev/flip-1 QA 修正都是 6697 行、12,153,874 位元組。
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

## 規則改動的雷

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
- **畫面上列「去哪裡做會記到」的清單，跟真的記功要問同一個判斷函式**（FB-531）：軍令卡列攻城地點照「此刻歸敵方」，記功照「打贏的隊伍是敵方陣營」，兩個條件在大多數地方一樣、在被佔下的中立地（站的是沒有陣營的中立駐軍）不一樣，卡上就列了記不到的地方、假人也被它帶過去。把判斷抽成一個函式（`orders.siege_win`），記功與列清單（對那裡出陣會打的每一路都成立才列）都叫它；同一份清單假人（`win_counts`／`targets`）、發不發軍令、輿圖標記也都讀它，修一處就全對。守城同理（FB-565）：`orders.defend_places` 是唯一的查法，記功、`duty_counts`、`targets`、軍令卡、輿圖標記都問它；測試寫一條「每個地點上這幾個說法的集合要一樣」的迴圈（`tests/test_conquest_fb565_defend.py` 的 `_agree`），別只測某一處的字。行動列底下那種「寫給玩家的原因」（FB-552 的「今天沒有公告攻城」）也是：原因要照規則真正的狀態分（沒排過、集結中、開打中、打完、作罷），不要拿一個布林（推不推得動）寫成一句，不然規則是對的、字不對。
- **「列與記同一個判斷」在這一下自己讓那一塊離開清單時會破**（FB-608，2026-10-21）：清單照「此刻推得動、進度最高」列，推滿易手、拉到零的那一下推完那一塊就不在清單上，先推後記就記不到最關鍵的那一下。記功照動作**之前**的清單判（先算好記功、那一句照舊排在推的那一句後面）；只在新規則的季挪，舊季（地盤照控制方判、先推線再記）順序不動，不然開關關著的對照會變。
- **清單上有「在那裡做 A 不算、做 B 才算」的地方**（FB-605：被戰書凍結的自家那一塊列進守城，只認攻城戰守住）：記功用不同的 kind 分（`orders.SIEGE_GUARD` 對 `duty`），`_counts` 照那一塊的狀態只認其中一種；一致性測試改成「清單＝各 kind 記得到的聯集、彼此不交」，卡上照 kind 分兩句寫。替一群人記功（攻城戰收場）時人不在動作裡：在 `mutate_season` 裡用 `_season_vehicle` 記，記之前讀他們的存檔確認是哪一邊（臨時投效、助守的不算），那一句訊息送不到本人。
- **管理者動作跟玩家動作不能同名**（FB-609）：`/api/do` 先查 `ADMIN_ACTIONS`，同名的玩家動作永遠走不到（玩家回 400「只有管理者能這麼做。」）；`tests/test_conquest_fb609_letter_route.py` 鎖住兩張表與 `api_do` 先接走的那幾個不重名。新加管理者救場一律跟 `Game.admin_*` 同名。
- **拿掉一顆不靠對手的行動（守勢行動、第 2～4 階行動這類）：灰鈕＋一個 `*_problem` 函式**（領地爭奪裁決 24）：原因寫成純規則裡的一個函式（`sortie.duty_problem`：回灰掉的原因，給得了是空字串，關著也是空字串），選單那個函式（`Game._duty_option`）最先問它，灰著寫「{名字}（{原因}）」，跟用完次數同一種寫法。不用另外擋動作本身：`Game.choose` 照選單重驗，灰的按下去回「（此刻無法這麼做。）」、什麼都不扣；假人（`bot_policy.take_turn` 只收 `enabled`）、入伍段發光（`enlist.glow`，`server` 只傳 `enabled` 的 id）自然碰不到。測試三件：每一種「不是自家」的地方各一個（敵方大本營、敵方區塊、還沒佔下的中立地、廣宗）、按下去前後的快照要一樣（體力、出陣次數、戰線偏移、貢獻、軍令進度、江湖紀錄的筆數）、關著的季（週末、14 天、21 天）標籤一個字不變。
- **QA「順帶」寫的是那一輪 QA 的版本**：開工先用一支探索腳本（`tests/conquest_kit.py` 的 `conquest_game`／`join`／`go` 擺人，印每個地點的 `game.options()`、按一下看快照）重現，再改。領地爭奪裁決 24 的順帶第 4 點（守城軍令把整條線算成目標、假人被帶去敵營）第二批就已經改掉了，只有第 1 點（守勢行動在敵營按得下去）還在；沒先重現會白寫一段已經對的程式。
- **給獎勵的路徑很多條**：打仗、出陣攻、出陣守與攪局、守勢行動、操練、挑戰本人的僵持、頭目戰、切磋、決戰軍餉、懸賞。改一種獎勵規則要逐條查。
  - 戰報的得失從 `record.exp/xinde/silver/materials` 來，江湖紀錄的數值從回傳的訊息來，「剛剛」卡片把兩邊相減畫剩下的。兩邊對不上，就會多一顆紅的「心得 -N」或算兩次。
  - **`_record_exp` 回的「心得 +N」只能進回傳的訊息，不能進 `record.notes`**：notes 會和得失再接一次，同一份算兩次（FB-451、FB-453）。
  - 戰報欄位用加的（`record.xinde = (record.xinde or 0) + x`），不要覆蓋，前面可能已經加了別的（FB-450）。
- 會不會先升級再轉換這類順序問題（例：滿級換心得要在 `add_exp` 之前判），寫一條「剛好升到頂的那一下」的測試。
- 擲骰一律用自己的亂數（`random.Random("用途|季數|名號|戰報流水號")`），不碰 `Game.rng`：整季測試與量表的序列才不會位移。
- **動作中間要改全服狀態**（例：探索撿到碎片，`Game._seal_find`）：用一次 `self.world.mutate(...)`，寫入時整個重驗；只想補天下大事或江湖史就寫在 mutate 裡的 `shared.season`（傳聞與江湖史只增不減，動作結束的 `_save_season` 不會蓋掉）。**不要**在動作中間把 `self.state.world = self.world.get_season()` 換掉：這個動作前面對 `self.state.world` 的就地修改還沒存，會一起丟掉（決戰收場那幾處這樣換是因為前面沒有未存的修改）。
- **新的全服登記欄位（`SealRegistry` 這類）在開季才寫**：寫的地方有三個進入點——`seed_first_season`（自動開季）、`open_season`、`next_season`；沒蓋章的季連登記都不要碰（`filled(...)` 也會改登記），舊的季才一個字不變。
- 資料庫結構（第 5 版）不改，要改先問 PM。新狀態欄位加在 `PlayerState`／`WorldState`，舊存檔讀得進來。
- **全服戰鬥不只一場了**（領地爭奪第二批：攻城戰跟時刻表決戰同時打，`SharedWorldState.sieges`）：引擎裡讀「這個人的那一場」用 `Game._battle_now()`（假人程式、bot_policy 用 `game.battle_now()`），改它用 `_mutate_battle_of(battle, fn)`，全部列出來用 `battles_now()`；**不要再寫 `world.get_battle()`／`world.mutate_battle()`**，除非真的只講時刻表決戰（璽動、管理者的決戰工具、`_settle_showdown`）。新的 `SharedWorldState`／`BattleInstance` 欄位照舊要分進 `tests/test_server.py` 的推送指紋表。
- **存進全服狀態的「現實時間」一律用 `self.now`，不要用 `pill_now()`**（FB-577，2026-10-21）：`pill_now()`＝`now`＋`advanced_real`，管理者快轉推的 `advanced_real` 只活在那一個 `Game` 物件的記憶體裡；拿它寫進共用狀態的時刻（`XingshiTicket.opened_real`、`retry_at`），別的 `Game`（伺服器排程 `world_tick`、別的玩家）拿自己的 `now` 比，會差上快轉的那十幾個小時。換天、回體丹換日這種「快轉跨過了就該算」的判斷才用 `pill_now()`（`conquest_day.day_key` 有「日子只准往前走」擋著）。測試：一個 `Game` 先 `advance` 跨過換天開單，另一個 `Game.for_world` 照現實時鐘 `world_tick`，看單有沒有照寬限收。
- **兩局測試各有一份內容**：`conquest_kit.conquest_game()`（同 `test_territory._game`）每一局各載一份 `real_content` 的複本，同一個資料庫開兩局時，在測試裡往內容加東西（例：借一份戰鬥範本）要兩局都加，不然第二局找不到、畫面靜靜地沒有那一場。

## 量表怎麼讀

- 量表只量不改，數字照實報，不為了好看調參數。PM 說「量一次就好」就量一次。
- `scripts/measure_exp_pace.py`：
  - 量的是「最認真、不合成不修練」的人，威力一路停在 35 上下，練功一點體力只換 2～3 經驗。
  - 它挑的練功點偏弱（對強的對手勝率太低），所以看不出「最好的練功點」差多少，也會低估會合成的玩家。
  - 看結果要連它印的每天威力一起看。要比練功點，另外照威力 60／90／120／160 算「對手經驗 × 勝率」。
  - 回報時兩種讀法都寫，讓 PM 定。
- 一次跑很多組要很久（21 天 × 四方約 25 分鐘），背景跑。跑的時候不要改它會讀的內容檔（每一組重新載內容）。

## 回報 PM

- 一張回饋單一個 commit；commit 訊息一句英文，結尾 `Co-Authored-By:`（照當時 system 給的那一行）。
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
