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
- 工作樹沒有 `.venv`：python 用 `C:/Ray/專案/天下大勢/.venv/Scripts/python.exe`，PowerShell 呼叫。
- **子代理的工作樹一開始停在別的分支上，技能檔是跟著分支走的**：Skill 工具回「Unknown skill: tianxia-dev」時，先 `git fetch origin '+refs/heads/dev/*:refs/remotes/origin/dev/*'`、`git switch -c <別名> origin/dev/<名字>`，再直接 Read `.claude/skills/tianxia-dev/SKILL.md`（換分支之前讀不到，2026-10-20 輿圖重製 1b）。
- 先寫計畫 `docs/superpowers/plans/<日期>-<名字>.md`（派工說「不必給企劃者審」就不審），一張回饋單不用計畫。不開子代理、不開 Workflow，除非派工明講。
- 派工若要「先合某分支」，合之前先 `git merge-base --is-ancestor <那一版> origin/feature/formal-season` 看是不是已經在功能分支上。PM 前後兩則指示衝突時照後一則；合到一半發現不對就 `git merge --abort`。
- 派工寫 `git switch -c dev/<名字> origin/dev/<名字>`，但 `git worktree list` 看得到那條本地分支已經在別的工作樹 checkout 著（上一位開發的）：同一條本地分支不能兩處同時 checkout，`switch -c` 也會說已經存在。開一條別名的本地分支（例 `conquest-1-fix`）從 `origin/dev/<名字>` 開，推的時候寫 `git push origin HEAD:dev/<名字>`，不去動別人的工作樹（2026-10-20 領地爭奪第一批修正）。

## 工作樹與指令的坑

- **檔案是 CRLF**（`core.autocrlf=true`）。用腳本改檔：讀進來 `\r\n`→`\n`，比對替換，寫回前轉回去。每一處替換都要 `assert count == 1`。一處一個腳本或一次一處，不要「多處替換、最後統一寫檔」（中途 assert 失敗會讓人以為改好了）。Edit 工具直接改 CRLF 的檔沒問題（換行照原樣留著，2026-10-20 量過 `web/app.js` 改完全是 CRLF），只有自己寫腳本才要轉。
- **Bash 在 worktree 隔離下會擋**：
  - 帶 git 的 heredoc、`git -C`、用 `$VAR` 或 `$(...)` 組出來的路徑或指令名，這幾種會被拒。不帶 git 的 heredoc（`cd … && cat > 檔 <<'EOF'`、`cat >> tests/x.py <<'EOF'`）也一樣被拒（2026-10-20）：寫檔、加測試一律用 Write／Edit 工具。
  - 繞法：git 一條一條下、路徑寫死。要改檔就用 Write 工具寫一支 Python 腳本到 scratchpad，再用 `python 腳本 .` 跑。
  - 實測（2026-10-21）：`cd <自己的工作樹> && git commit -q -F - <<'EOF' … EOF`（訊息從 stdin 進、路徑寫死）過得了；先設 `SP=…` 再 `git archive -o "$SP/…"`、`git ls-files` 配 `for` 迴圈與 `$'\r'` 的被擋。
  - 要跑 venv 的 python、讀 `$env:TEMP` 的 log，改用 PowerShell 工具。
- **中文輸出**：Python 印中文前包 UTF-8（`PYTHONIOENCODING=utf-8` 或 `sys.stdout = io.TextIOWrapper(...)`），不然 cp950 會炸（連 `print` 一個 `−` 都會）。
- **TIANXIA_DB**：每次跑測試、跑腳本都設到 repo 外一個新的暫存檔（`$env:TEMP\tx_xxx.db`）。舊的資料庫會讓測試假失敗。
- **git stash 是所有工作樹共用的**，別的 session 也在用。
  - 不要裸 `git stash` / `pop`。
  - 要用就 `git stash push -m <獨一無二的標籤> -- <檔>`，`git stash list --format='%H %gd %gs'` 找到自己那一筆，`git stash apply <sha>`，再照標籤找 `stash@{n}` 去 drop。
  - 想證明測試「修之前是紅的」，最簡單的就是這樣把改動暫時收起來跑一次。
- 背景長跑（量表）用 `run_in_background`。輸出導到檔案時 python 會緩衝，加 `-u` 才看得到進度。等它結束的通知，不要輪詢。
- **PowerShell 的 `git commit -F - @'…'@` 不會走 stdin**：here-string 被當成一個路徑參數，合併中會報 `cannot do a partial commit during a merge`（不在合併中就變成只提交那個「路徑」）。commit 訊息用 Write 寫進 scratchpad 的檔，`git commit -F <檔>`（2026-10-20）。
- **Git Bash 的 `sed -i` 會把 CRLF 的檔整個改成 LF**（2026-10-20 改 `bot_policy.py` 一行，整個檔變 LF）：改一行也用 Edit 工具，或照上面「讀進來轉 `\n`、寫回轉回去」的腳本。
- **PowerShell 5.1 讀沒有 BOM 的 `.ps1` 會把中文路徑讀成亂碼**（`Set-Location` 說找不到路徑）：長指令直接放進 PowerShell 工具的 `command`（工具會處理編碼），要一長串檔名就寫進 ASCII 的 txt、用 `Get-Content` 讀。
- **逐行改測試檔的小工具**（LF／CRLF 都通用）：`open(path, newline="").read().split("\n")`，指定行號、`assert "舊字" in 那一行` 再替換，寫回時 `"\n".join`；整段替換的版本先把 `\r\n` 轉 `\n`、每一處 `assert text.count(舊) == 次數`。次數用「出現幾次」不是 `grep -c` 的行數（同一行出現兩次會差一）。
- **Bash 的隔離檢查會擋「太複雜」的 python heredoc**（一次改兩個檔的 dict 迴圈就被擋過）：改檔腳本寫進 scratchpad 的 `.py`（裡面放一個 `edit(相對路徑, [(舊, 新, 次數)])` 的小函式，照上面 CRLF 的規矩），用 PowerShell 跑 `python 腳本 .`。
- **實機開自己的伺服器**（不碰 7861）：
  - 設定不必動 `content/profiles/`：`TIANXIA_PROFILE` 給絕對路徑（不寫 `.json`）就讀那個檔，抄一份要的設定檔到 scratchpad、打開要試的開關，順便把 `ollama_url` 指到死埠（`http://127.0.0.1:9`）。
  - 管理者的名號在 `/api/character` 取不到（玩家不能取管理者的名號）：用 `scripts/set_password.py <帳號> --character <名號> --db <暫存資料庫> --local-dir <scratchpad>` 建（密碼寫在 scratchpad 的檔），啟動伺服器前設 `TIANXIA_ADMINS=<名號>`。其他測試角色走 `/api/register`、`/api/character`，陣營與所在地可以直接寫進同一個資料庫（`open_characters()` 照 `TIANXIA_DB`），伺服器每次拿鎖都重讀角色。
  - 正式設定的排程是關的（啟動時印「排程：關」）：世界時間只在有人連線時推，集結截止、回合逾時要有人輪詢才會發生——驅動腳本要一直打 `/api/main`。
  - 長的等待：PowerShell 的 `Start-Sleep` 超過一定秒數會被擋；在瀏覽器分頁裡 `javascript_tool` 跑 `await new Promise(r => setTimeout(r, 30000))` 再抓 `/api/main`，或用 Monitor。

## 測試怎麼挑

- 平常只跑 `scripts/test_for.py --base <base>`（含 slow），或直接 `pytest 改到的那幾個檔`。整套留給合併的人。
- **base 要選對**：
  - 跟你的分支開出來的那一點比，通常是 `origin/feature/formal-season`。
  - 你自己合了別的分支進來時，base 用合完那一個 commit，只量你這一輪的改動，不然會把別人的東西全挑進來。
  - `--list` 先看挑到哪些檔。
- 改到 `tianxia/engine.py` 幾乎會挑到大半套（八千多條、約 6～8 分鐘），正常。只動內容或小模組時會少很多。
- **`test_for.py` 自己已經帶 `-q`**：`--` 後面再傳 `-q` 就變 `-qq`，跑完 exit 0 卻不印「N passed」那一行（2026-10-20 輿圖重製 1b 的前一位開發就是這樣沒留下數字）。`--` 後面只傳 `-n 6`。
- **內容的名字或位置改了（人物開季站位、地點歸屬、線名），`test_for.py` 挑不到「用真實內容、斷言寫死舊名字或舊位置」的測試**：它只挑 import 改到的模組的檔，內容改了只補 `test_content`／`test_real_content` 這幾個。輿圖重製 1b 搬七位人物、線名改「中原」，`test_for` 的 20 個檔全綠，另外 15 個檔、79 條是紅的（`test_front_lines`、`test_orders`、`test_ranks`、`test_figure_aid`、`test_precise_actions`、`test_challenge_season`……）。做法：
  - 把改到的 id 與顯示名（人物 id、中文名、地點 id、線名）列成 token，寫一支小腳本掃 `tests/test_*.py`：含 token、又用真實內容（`real_content`、`real` fixture）的檔，扣掉 `test_for` 已經跑過的，一起 `pytest -n 6 -m "slow or not slow"`（87 個檔約一分鐘多，比想的快）。
  - 紅的照「換成新位置／新名字，斷言的意思不變」改；找「剛好只有一位人物的地方」不要猜，寫小腳本對每個地點印 `_people_here()` 與交友鈕（本批：白馬寺華佗、黃巾別部營寨波才、白馬津卜己）。人物搬走後「風聞聽眾」「悲憤」這類靠大區找人的測試，要先把人物擺回原位（`figures._ensure(...).location = ...`），或換一位還站在那一區的人，不要把斷言改成沒意義的。
- **把規則分支合進新地理分支**（2026-10-21，領地爭奪 97567ff0 合進輿圖 1）：兩邊碰的是不同批檔（輿圖只動內容與測試、領地爭奪只動程式與測試），git 的衝突只有 3 個（一份指南、兩個測試檔），**但自動合進來、沒衝突的新測試會因舊地點整批紅**（55 條，4 個檔，沒有一條是規則壞了）。流程：
  - 合完先 commit 衝突的解法，再跑 `tests/test_conquest_*.py` 全部（PowerShell 呼叫 pytest 不展開萬用字元，整串會當成一個不存在的檔名、`no tests ran`、exit 5：`$f = @(Get-ChildItem tests -Filter "test_conquest_*.py" | % { "tests/" + $_.Name }); pytest @f`），把舊地點換成新的另開一個 commit，merge commit 保持乾淨；
  - 借舊地點當「有某隊守軍的中立地」的測試：查 `content.scenario.territory.neutral_garrison`（地點 → 隊伍 id）找守軍隊伍相同的新中立地（南陽官道的劫道響馬 → 潁川郊野），戰報裡的地名斷言跟著換——**先替換舊地名、最後才插入含舊地名的註解**，不然 `assert count` 會數到註解；
  - 借舊地點當「線上的敵方陣營區塊」的，用 `conquest_game_with({"runan_wilds": ("huang", "yingru")})`（1b 的做法），不要改成中立地；舊的南陽／冀州線沒有區塊，要一條有區塊的線一律用 `yingru`；
  - `test_for` 紅的幾條，先到**合併前那一版**（`git archive <SHA> -o 檔.tar`，另一步 `tar --force-local -x -f 檔.tar -C 目錄`，兩步不能併成一條指令；在解出來的目錄跑那幾條）看是不是原本就紅：這次 4 條（`test_onboard` 投靠點、`test_fb_batch_c` 線名、`test_say_web` 盧植搬家）在 `dev/map-1` 就是紅的，1b 的 token 掃描沒掃到，不是這次合併造成的——回報要分開寫，照同一個原則（意思不變）換新地點。
  - 順手量：每塊中立地的 `conquest.sortie_foes(world, content, loc, 陣營)`；新地理上潁川郡（沒有 `enemies`、`neutral_garrison` 沒有它）是空的，它會被公告成目標卻打不起來（回報 PM，沒動）。
- 新測試超過一秒（建 `Game`、載真實內容通常就超過）標 `@pytest.mark.slow`。
- **修 bug 先寫會紅的測試**：先確認它在修之前真的失敗、失敗的數字跟 QA 回報的一樣，再修。回報時寫「修前重現了什麼」。
- 用正式內容測舊規則的測試，要在 helper 裡把新開關關掉（例 `c.config.precise_actions = False`、`four_tiers.enabled = False`）。新規則另開一個測試檔，不要改寫舊的斷言去迎合新規則。
  例外：PM 的裁決直接推翻還沒上線的這一批的做法（不是開關後面的舊季）時，鎖住舊做法的那一條斷言照裁決翻過來，註明哪一條裁決、新規則的測試在哪一個檔（例：裁決 19 之後 `test_siege_void_when_no_attacker` 改成「沒有作罷的天下大事」，新的在 `test_conquest_void_quiet.py`）。
- 江湖紀錄 `state.journal` 新的在前（index 0）。找某一則照標題找，不要拿 `[-1]`。
- **證明開關關著一個字都不變**：一條條「關著不變」的測試之外，最省事的是拿 QA 的整份畫面對照（`tianxia-qa/引擎驗收.md` 第 7 節；scratchpad 裡 QA 留過 `conqqa/cmp_off.py`）：開這一批之前那一版與 HEAD 各 `git archive` 一份跑，比雜湊。腳本 `import server`，所以要連頂層的 `server.py server_push.py zhuan_html.py llm_queue.py console.py` 一起 archive（只 archive `tianxia content` 會 `No module named 'server_push'`）。領地爭奪第一批修正：season21／week7／weekend 三種季 573／569／567 行一個位元組都一樣。

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

## 規則改動的雷

- **開關與蓋章**：
  - 新規則多半是 `Config` 開關＋開季時蓋在 `WorldState` 的章（例 `precise.on(content, world)` 同時看設定、章、探索三選一）。
  - 判斷開沒開一定走那個 `on()`，要把 world/state 傳進去。只傳 content 時它會回假，悄悄退回舊說法（FB-435 就是這樣：傳聞沒給 world，寫回舊句）。
  - 改函式簽名加 world/state 時，grep 所有呼叫點一起改，包括 letters、figure_life、shopview、engine。
- **季種類對照**（週末 `weekend`、14 天＝不帶設定檔、21 天 `season21`）：
  - 新數字通常只寫在 `content/profiles/season21.json` 或 `Config` 預設。
  - 改之前想清楚三種季各會怎樣。派工沒說要動週末與 14 天就不動。
  - 測試用 `real_content("weekend")`／`("season21")` 各驗一次。
- **說法要跟規則一起改**：
  - 規則換了，玩法說明（`howto.py`）、按鈕、懸賞說明、傳聞、書信裡的同一件事都要跟著改。舊季要一個字都不變，照開關分兩版。
  - 改完 grep 舊句子的關鍵字，找漏掉的地方。
  - 看的人不同說法不同（散人不出陣）：要看身分就把 state 傳進去。同一個「攻」也分站的地方（還沒人佔的中立地不是「這裡歸別人」、自家的大本營守不接「量是攻的一半」，FB-532、FB-533）：寫行動列底下那一行時，把每一種「這一塊此刻歸誰、搶不搶得下來」的組合各印一次看。
  - 鈕寫什麼就要給什麼（PM 裁決 18）：一個地方搶不下來卻標「攻」、畫 ⚔，就是鈕在騙人。要拿掉一種行動，從最底下回對手的那個函式（`conquest.sortie_foes`）擋，攻守、⚔、輿圖的出陣、攻城地點一起跟著變；有一種東西舊規則還靠它（截糧的運糧隊在長社），列出來留著、回報時寫明。
  - 灰掉的鈕括號裡那一句，網頁拿最後一小句當行動列格子的小字（不換行、10 px、格子約 60 px）：**最多六個字**（同「散人不能出陣」），八個字剛好頂到格子兩邊，320 寬就切掉。長的原因寫在行動列底下那一行（`action_notes`）。
- **新開關讓某個函式回空的，呼叫它的人可能把「空」讀成「做不了」**（領地爭奪第一批）：`Game.sortie_push` 開著時回 `{}`，行動列底下出陣那一行（`_sortie_line`）就寫成「今天這條線推滿了，推不動」；`sortie.ranger_here`、戰況圖卡與主線小標的說明還照 `territory.line_of` 判「這裡有沒有出陣」。換掉一個規則的計算時，grep 那個函式與它判斷用的舊條件（`line_of`、`train_trend`……）的每個呼叫點，連說明與按鈕的字一起看。
- **「基準＋偏移、顯示時夾 0～100」這種值，推的時候不要從夾過的值重錨偏移**（FB-530）：基準本身出得了牆時（領地爭奪分母只算中立，打進敵方陣營區塊基準就過 100），「新值＝夾過的值＋推量、偏移＝新值－基準」會讓每一推（連往同一邊推）都把偏移往回扣，基準越出牆扣越多；四捨五入過的值重錨也會讓偏移每推一下多走或少走半格。偏移照未夾的值加減，推過牆的那一截才丟（往牆推時最多推到 max(原本, 牆)），夾只在算顯示的值時做（`conquest.apply_push`）。測試要造一個「基準在牆外」的局面，推一下、再易手讓基準回到牆內，看值差多少。
- **畫面上列「去哪裡做會記到」的清單，跟真的記功要問同一個判斷函式**（FB-531）：軍令卡列攻城地點照「此刻歸敵方」，記功照「打贏的隊伍是敵方陣營」，兩個條件在大多數地方一樣、在被佔下的中立地（站的是沒有陣營的中立駐軍）不一樣，卡上就列了記不到的地方、假人也被它帶過去。把判斷抽成一個函式（`orders.siege_win`），記功與列清單（對那裡出陣會打的每一路都成立才列）都叫它；同一份清單假人（`win_counts`／`targets`）、發不發軍令、輿圖標記也都讀它，修一處就全對。
- **給獎勵的路徑很多條**：打仗、出陣攻、出陣守與攪局、守勢行動、操練、挑戰本人的僵持、頭目戰、切磋、決戰軍餉、懸賞。改一種獎勵規則要逐條查。
  - 戰報的得失從 `record.exp/xinde/silver/materials` 來，江湖紀錄的數值從回傳的訊息來，「剛剛」卡片把兩邊相減畫剩下的。兩邊對不上，就會多一顆紅的「心得 -N」或算兩次。
  - **`_record_exp` 回的「心得 +N」只能進回傳的訊息，不能進 `record.notes`**：notes 會和得失再接一次，同一份算兩次（FB-451、FB-453）。
  - 戰報欄位用加的（`record.xinde = (record.xinde or 0) + x`），不要覆蓋，前面可能已經加了別的（FB-450）。
- 會不會先升級再轉換這類順序問題（例：滿級換心得要在 `add_exp` 之前判），寫一條「剛好升到頂的那一下」的測試。
- 擲骰一律用自己的亂數（`random.Random("用途|季數|名號|戰報流水號")`），不碰 `Game.rng`：整季測試與量表的序列才不會位移。
- 資料庫結構（第 5 版）不改，要改先問 PM。新狀態欄位加在 `PlayerState`／`WorldState`，舊存檔讀得進來。
- **全服戰鬥不只一場了**（領地爭奪第二批：攻城戰跟時刻表決戰同時打，`SharedWorldState.sieges`）：引擎裡讀「這個人的那一場」用 `Game._battle_now()`（假人程式、bot_policy 用 `game.battle_now()`），改它用 `_mutate_battle_of(battle, fn)`，全部列出來用 `battles_now()`；**不要再寫 `world.get_battle()`／`world.mutate_battle()`**，除非真的只講時刻表決戰（璽動、管理者的決戰工具、`_settle_showdown`）。新的 `SharedWorldState`／`BattleInstance` 欄位照舊要分進 `tests/test_server.py` 的推送指紋表。
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
- **疊批合回上一批的修正**（`dev/<x>-2` 合 `dev/<x>-1` QA 之後的 FB 修正；2026-10-20 領地爭奪第二批合第一批修正）：
  - 衝突多半是同一個判斷兩邊各改一半：上一批的修正收緊條件（攻城只算打贏敵方陣營的隊伍，FB-531），這一批換掉來源（攻城地點改成今天公告的目標，還放寬成「中立駐軍也算」）。照 PM 定的疊法，兩個條件都套在**列清單**與**記功**兩邊（同一個判斷函式），不要只把兩段文字接起來。疊出來的代價（例：只公告中立地的那一天攻城軍令記不到、也不發）寫進計畫交 PM。
  - 上一批修正帶進來的測試是照上一批的前提寫的（任何搶得下來的區塊都推得動進度、攻城地點不看時程表），**自動合併、沒有衝突標記，照樣會紅**：合完、提交合併之前先跑兩批的測試檔。補上這一批的前提（例 `conquest_kit.announce` 先公告那一塊），不改斷言，測試檔開頭寫一句為什麼。
  - 兩邊各寫了同一個節號（兩個「6.2」）：都留、照 commit 時間排（`git log -1 --format=%ci <sha>`），不重新編號（回饋單寫著「計畫 6.2」），合併怎麼解另起一段接在最後。
- 回報寫：
  - 每張的 commit 與一兩句怎麼修。修前重現了什麼。
  - 跑了哪些測試、幾條過。
  - 順手改的東西另列，讓 PM 決定留不留。
  - 數字照實寫，有疑慮直接講。
  - 只做被要求的事；看到別的問題先報，不自己擴大範圍。
- 收尾交接：分支與 HEAD、沒提交或沒推的、開著的伺服器或背景程式（埠、PID，關掉）、還開著的 FB、踩過的坑、這一路改了 CLAUDE.md 或 `docs/guide/` 的哪幾條。
