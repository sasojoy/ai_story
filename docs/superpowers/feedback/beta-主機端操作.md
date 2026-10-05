# 分享版試玩伺服器：主機端操作

給企劃者，也給幫忙重開伺服器的 PM session。目的是讓 joy 這種不在同一個地方的朋友，連到這台電腦上的試玩伺服器。

做法是 `server.py --share`：伺服器會叫 cloudflared 開一個 trycloudflare 臨時公開網址。不用帳號、不用設定，但**每次重開，網址都會換**。

> QA 2026-10-04 在這台電腦上實測過（main `0335664`，7890 埠、全新資料庫）。結果見下面各節，以及 [試玩回饋.md](試玩回饋.md) 的 FB-011、FB-020、FB-021。

## 第一次要先做的

1. **裝 cloudflared**：
   - 在 PowerShell 打 `winget install Cloudflare.cloudflared`。這台已經裝好了，版本 2026.9.3，裝在 `C:\Program Files (x86)\cloudflared`。
   - 裝之前就開著的 PowerShell 視窗或 Claude session 找不到它，要**另開一個新的** PowerShell 視窗，打 `cloudflared --version`，看到版本號就好了。
   - session 沒辦法重開時，在啟動伺服器之前先補一行：`$env:Path += ";C:\Program Files (x86)\cloudflared"`。
2. **電腦不能睡眠**：電腦一睡，伺服器和網址都會斷。
   - Windows 設定 → 系統 → 電源 →「螢幕、睡眠與休眠逾時」：把接上電源時的睡眠設成「永不」。螢幕關掉沒關係。
   - 筆電闔上蓋子也會睡：控制台 →「電源選項」→「選擇闔上螢幕時的行為」，接上電源時改成「不執行任何動作」。
3. **本機 AI（Ollama）要開著**：人物對話、隨口應對、煉製新配方取名都靠它。Ollama 沒開時，那一輪對話會取消。

## 開伺服器和假人

開兩個 PowerShell 視窗，兩邊都先進專案資料夾，**設同一個資料庫**。下面用企劃者現在在玩的那個資料庫當例子：照用它，角色和進度都會留著。

**視窗一：伺服器**

```powershell
cd C:\Ray\專案\天下大勢
$env:TIANXIA_DB = "C:\Ray\tianxia-play\tianxia.db"
.venv\Scripts\python.exe -u server.py --port 7861 --share
```

**視窗二：假人**

```powershell
cd C:\Ray\專案\天下大勢
$env:TIANXIA_DB = "C:\Ray\tianxia-play\tianxia.db"
.venv\Scripts\python.exe -u run_bots.py
```

- `$env:TIANXIA_DB` 只對打這行的那個視窗有效，所以兩個視窗都要打。
- 兩個程式啟動時都會印一行「資料庫：…」，**兩行要一樣**。不一樣就是設錯了，假人會跑在另一個世界。
- 假人照作息只在晚上（19～24 點）和中午前後（11:30～13:00 開始）上線，其他時間沒動靜是正常的。

## 伺服器自己的排程（預設關）

打開之後，伺服器每隔幾秒自己推一次全服的事：世界時間、時刻表的大事、時間到了開決戰、決戰的集結與回合逾時、季末。沒有人開著網頁時也照樣跑。關著的時候跟以前一樣，要有人連線（或假人程式在跑）世界才會動。

- **現在是關的**：開關是 `world_tick_seconds`，預設 0（關）。`content/config.json` 和 `content/profiles/` 裡都還沒打開；要在哪一份設定打開，等驗收過了由 PM 決定。
- 怎麼打開：在用的設定檔加上 `"world_tick_seconds": 10`。例如週末設定是 `content/profiles/weekend.json`；用的是預設設定，就加在 `content/config.json`。
- 重開伺服器之後，啟動訊息在「設定：…」下面會多一行 `排程：每 10 秒推一次全服的事…`；關著時是 `排程：關（世界時間等有人連線才推）`。
- 假人程式照舊另外開，兩個可以同時開。
- 排程出錯時，伺服器會印一行「排程這一下出錯：…」，下一輪照跑。
  - 在視窗裡開的：這一行和後面的錯誤細節（traceback）都在伺服器視窗。
  - 照下面「給 session 用」在背景開的：這一行在 `server_out.log`，錯誤細節在 `server_err.log`。
  - 看到這一行請回報：視窗就截圖，背景開的就把兩個 log 一起附上。

## 網址在哪、怎麼給 joy

- 伺服器視窗會先印「天下大勢：http://127.0.0.1:7861」和「資料庫：…」，**大約 7 秒後**再印：
  `公開網址：https://xxxx.trycloudflare.com（給手機用；有網址的人都進得來，不要外流）`
- 把 `https://` 開頭那一串複製給 joy。企劃者自己在這台電腦上玩，照樣開 http://127.0.0.1:7861 就好。
- **伺服器一重開，網址就會換**，要把新網址重新給 joy。舊網址在 cloudflared 跟著關掉之後就失效，打開會看到 Cloudflare 的錯誤頁（HTTP 530）。
- 伺服器重開後**每個人都要重新登入一次**。帳號、角色、進度都還在。
- 有網址的人都能進來註冊，所以網址只私下給，不要貼在公開的地方。

## 怎麼停

在兩個視窗各按一次 **Ctrl+C**。伺服器和 cloudflared 會一起關掉，不會留下東西。直接關掉視窗也可以。

## 怎麼備份資料庫

1. 先把伺服器和假人**兩個都停掉**。
2. 把資料庫的三個檔一起複製到別的資料夾：`tianxia.db`、`tianxia.db-wal`、`tianxia.db-shm`。後兩個有時候不存在，有就一起帶。

```powershell
$dst = "C:\Ray\tianxia-play\backup\$(Get-Date -Format yyyyMMdd-HHmm)"
New-Item -ItemType Directory -Force $dst | Out-Null
Copy-Item C:\Ray\tianxia-play\tianxia.db* $dst
```

要還原時，一樣先停掉兩個程式，再把這三個檔複製回去。

## 換成第一季濃縮版的那一天

企劃者定了「換季重來、不開新資料庫」：帳號和江湖史留著，beta 這一季收掉，開新的一季。順序照下面走（PM 2026-10-04 定）。

> QA 2026-10-04 演練過全部五步：先用舊程式建一份 beta 季、跑了 3 天，再換新程式收季、套週末設定、開季（第 1、2、4、5 步在 main `94a93ce`，第 3 步在 `8d34ea3`）。結果見 [濃縮版-驗收清單.md](濃縮版-驗收清單.md) 的 T0、T2。

0. **先備份資料庫**（上一節）。
1. **換程式，先不套週末設定**：照平常的方式開伺服器。
   - 這時第一季的開關還是關的，beta 這一季照原本 14 天的規則跑，角色、進度都在。
   - 週末試玩**不開假人**（企劃者 2026-10-04），只開伺服器那個視窗。
2. **立刻收季**：用 `Rayal` 登入，右上角 ⚙ → 管理者工具 →「⚠ 立刻收季」→「確定收季」。
   - 畫面變成「休季中，等待管理者開啟下一季」；管理者的江湖紀錄多一則「收季」，裡面是結局與武學榜。
   - 有決戰正在集結或在打，會直接收掉、不算結果。
3. **套週末設定再開伺服器**：停掉伺服器，在同一個視窗多打一行再開：

   ```powershell
   $env:TIANXIA_PROFILE = "weekend"
   .venv\Scripts\python.exe -u server.py --port 7861 --share
   ```

   - 它會一次換掉三個值：第一季開關、一季 2.5 天、人數上限 2（`content/profiles/weekend.json`）。
   - 啟動時「資料庫：…」下面會印 `設定：weekend（第一季濃縮版規則開啟、季長 2.5 天、人數上限 2）`。沒設的時候印 `設定：預設`。
   - 建議先做完第 2 步（收季）再設這一行，但順序弄反也不會出事：現在這一季是舊版開的，沒有記下季長，新程式一律照它開季時的 14 天算，不會因為週末設定變成 2.5 天而自己收掉，也不會跑時刻表（FB-037，QA 2026-10-04 在 main `610174e` 複測過）。
   - QA 2026-10-04 在 main `8d34ea3` 演練過這一步：收季後帶設定重開、開下一季，新的一季記下「濃縮版、2.5 天」，照季曆跑。
4. **開啟下一季**：⚙ → 管理者工具 →「⚠ 開啟下一季」→「確定開啟下一季」。
   - 這一句確認會提醒排時間（FB-050，main `4b643ee` 複測過），記得接著排。
   - **排三場大戲與季末**：同一個抽屜往下是「時刻表」，十二件各一列。
     - 長社火攻、宛城之戰、廣宗決戰、下曲陽・季末四列，各有一個日期時間欄和「排定」。
     - 預設排在第 6、9、11 週中與第 12 週末，也就是開季後 60 小時收季。不改就照預設跑。
     - 要改：填現實的日期時間 → 按「排定」→ 確認。回覆會寫排在季曆的哪一刻；決戰會對齊到下一個整點（季曆），那一刻剛好有別的大事就再往後挪一個時辰。
     - 不能排在已經過去的時間；四件要照順序；宛城要排在第 3 週（張曼成攻殺南陽太守）之後。
   - 救場工具（跳到下一件大事、定戰況、定結果、清鎖定、取消決戰）怎麼用，見驗收清單 T10。
     - **決戰要換時間，在集結開始之前改排**。集結開始之後按「取消決戰」，那一場就不會再開、也排不了，只能用「定結果」收尾（QA 10/5 演練過）。
     - 豪強割據的漲速照這一季投靠的人數算（15 人才是全速），兩個人時漲得很慢，不會再在第 10 週以群雄並起提早收季（FB-053，main `4b643ee`）。
   - QA 2026-10-05 在 main `d45b9cc` 照第 1～5 步加排時間演練過一次（驗收清單 T10）。
5. **大家重新登入**：
   - 帳號、密碼照舊。
   - 角色重來：陣營、武學、素材、銀兩、心得都回到新角色的樣子。
   - 跟人物的好感度只帶一成（80 變 8），對話紀錄與引導進度留著；上一季的江湖史看得到。

## 給 session 用：不開視窗的啟動與停止

Claude session 不能開互動視窗，改用 `Start-Process` 在背景啟動，輸出寫進 log。**記下回傳的 PID**，停的時候要用：

```powershell
cd C:\Ray\專案\天下大勢
$env:TIANXIA_DB = "C:\Ray\tianxia-play\tianxia.db"
$srv = Start-Process .venv\Scripts\python.exe -ArgumentList "-u","server.py","--port","7861","--share" -RedirectStandardOutput server_out.log -RedirectStandardError server_err.log -WindowStyle Hidden -PassThru
$bots = Start-Process .venv\Scripts\python.exe -ArgumentList "-u","run_bots.py" -RedirectStandardOutput bots_out.log -RedirectStandardError bots_err.log -WindowStyle Hidden -PassThru
"server $($srv.Id)  bots $($bots.Id)"
```

- 公開網址印在 `server_out.log`，大約 7 秒後出現。用 `Get-Content server_out.log -Encoding UTF8` 讀，不加 `-Encoding UTF8` 中文會變亂碼。
- `-u` 一定要加。沒加的話，Python 寫檔時會先存在緩衝裡，伺服器其實已經開好了，log 卻一直是空的。
- **停的時候用 `/T` 關整棵**：`taskkill /PID <server 的 PID> /T /F`，假人也一樣。實測這樣會連 cloudflared 一起關掉。
- **不要只關「正在聽 7861 的那個 PID」**：`.venv` 的 python.exe 會再開一個真正的 python，cloudflared 是那個 python 開出來的。只關它的話，cloudflared 會留著、繼續連 7861，**重開後舊網址照樣進得到新伺服器**（FB-021）。
- 不確定有沒有殘留時，先停掉伺服器，再跑下面這行清掉，**最後才重開**。順序不能倒過來：這行會把連到 7861 的 cloudflared 全部關掉，包括新開的那個。

```powershell
Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" | Where-Object CommandLine -match '127.0.0.1:7861' | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

## 已知限制

- trycloudflare 是 Cloudflare 給測試用的免費服務，不保證不斷線。斷了就重開伺服器，再給一次新網址。實測開著 22 分鐘，每分鐘從外面打一次，都正常（每次 0.4～1.5 秒）。
- Cloudflare 對單一請求大約只等 100 秒。實測本機 AI 都遠低於這個數字（模型 `gemma4:26b` 已載入時），經過公開網址也一樣：
  - 求見人物：11.5 秒；交談一輪：11～12 秒。
  - 隨口應對：9 秒；5 個人同時送，最慢 27 秒。
  - 煉製新配方取名：4 秒。
