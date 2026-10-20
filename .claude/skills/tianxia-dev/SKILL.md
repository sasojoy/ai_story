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
- 先寫計畫 `docs/superpowers/plans/<日期>-<名字>.md`（派工說「不必給企劃者審」就不審），一張回饋單不用計畫。不開子代理、不開 Workflow，除非派工明講。
- 派工若要「先合某分支」，合之前先 `git merge-base --is-ancestor <那一版> origin/feature/formal-season` 看是不是已經在功能分支上。PM 前後兩則指示衝突時照後一則；合到一半發現不對就 `git merge --abort`。

## 工作樹與指令的坑

- **檔案是 CRLF**（`core.autocrlf=true`）。用腳本改檔：讀進來 `\r\n`→`\n`，比對替換，寫回前轉回去。每一處替換都要 `assert count == 1`。一處一個腳本或一次一處，不要「多處替換、最後統一寫檔」（中途 assert 失敗會讓人以為改好了）。
- **Bash 在 worktree 隔離下會擋**：
  - 帶 git 的 heredoc、`git -C`、用 `$VAR` 或 `$(...)` 組出來的路徑或指令名，這幾種會被拒。
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
- 背景長跑（量表）用 `run_in_background`。輸出導到檔案時 python 會緩衝，加 `-u` 才看得到進度。等它結束的通知，不要輪詢。

## 測試怎麼挑

- 平常只跑 `scripts/test_for.py --base <base>`（含 slow），或直接 `pytest 改到的那幾個檔`。整套留給合併的人。
- **base 要選對**：
  - 跟你的分支開出來的那一點比，通常是 `origin/feature/formal-season`。
  - 你自己合了別的分支進來時，base 用合完那一個 commit，只量你這一輪的改動，不然會把別人的東西全挑進來。
  - `--list` 先看挑到哪些檔。
- 改到 `tianxia/engine.py` 幾乎會挑到大半套（八千多條、約 6～8 分鐘），正常。只動內容或小模組時會少很多。
- 新測試超過一秒（建 `Game`、載真實內容通常就超過）標 `@pytest.mark.slow`。
- **修 bug 先寫會紅的測試**：先確認它在修之前真的失敗、失敗的數字跟 QA 回報的一樣，再修。回報時寫「修前重現了什麼」。
- **「確認並守住」的測試**（程式沒改、一寫就綠，例：假人不買商城的東西）：要證明它抓得到退步，另寫一個暫時的測試檔 import 它，monkeypatch 一個退步（例 `bot_policy.take_turn` 先叫 `mall_buy`、`social.card` 多塞一個「元寶」），跑一次看它紅，再刪掉那個暫時的檔（不提交）。
- 用正式內容測舊規則的測試，要在 helper 裡把新開關關掉（例 `c.config.precise_actions = False`、`four_tiers.enabled = False`）。新規則另開一個測試檔，不要改寫舊的斷言去迎合新規則。
- 江湖紀錄 `state.journal` 新的在前（index 0）。找某一則照標題找，不要拿 `[-1]`。

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
  - 看的人不同說法不同（散人不出陣）：要看身分就把 state 傳進去。
- **給獎勵的路徑很多條**：打仗、出陣攻、出陣守與攪局、守勢行動、操練、挑戰本人的僵持、頭目戰、切磋、決戰軍餉、懸賞。改一種獎勵規則要逐條查。
  - 戰報的得失從 `record.exp/xinde/silver/materials` 來，江湖紀錄的數值從回傳的訊息來，「剛剛」卡片把兩邊相減畫剩下的。兩邊對不上，就會多一顆紅的「心得 -N」或算兩次。
  - **`_record_exp` 回的「心得 +N」只能進回傳的訊息，不能進 `record.notes`**：notes 會和得失再接一次，同一份算兩次（FB-451、FB-453）。
  - 戰報欄位用加的（`record.xinde = (record.xinde or 0) + x`），不要覆蓋，前面可能已經加了別的（FB-450）。
- 會不會先升級再轉換這類順序問題（例：滿級換心得要在 `add_exp` 之前判），寫一條「剛好升到頂的那一下」的測試。
- 擲骰一律用自己的亂數（`random.Random("用途|季數|名號|戰報流水號")`），不碰 `Game.rng`：整季測試與量表的序列才不會位移。
- 資料庫結構（第 5 版）不改，要改先問 PM。新狀態欄位加在 `PlayerState`／`WorldState`，舊存檔讀得進來。

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
- 回報寫：
  - 每張的 commit 與一兩句怎麼修。修前重現了什麼。
  - 跑了哪些測試、幾條過。
  - 順手改的東西另列，讓 PM 決定留不留。
  - 數字照實寫，有疑慮直接講。
  - 只做被要求的事；看到別的問題先報，不自己擴大範圍。
- 收尾交接：分支與 HEAD、沒提交或沒推的、開著的伺服器或背景程式（埠、PID，關掉）、還開著的 FB、踩過的坑、這一路改了 CLAUDE.md 或 `docs/guide/` 的哪幾條。
