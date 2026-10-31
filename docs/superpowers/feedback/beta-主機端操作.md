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

## 重啟 Ollama：一定要連 `llama-server.exe` 一起砍

2026-10-13 踩過一次，造成線上的對話、取名中斷約 25 分鐘。

砍掉 `ollama app` 與 `ollama` **不會**帶走它開出來的 runner `llama-server.exe`。留著的那一個繼續佔著顯卡與模型檔，之後每一次載入模型都失敗，而 API 回的錯誤完全看不出原因：

```
llama_init_from_model: failed to initialize the context: Gemma4Assistant requires ctx_other to be set
error loading model: vector
```

真正的原因要看 `%LOCALAPPDATA%\Ollama\server.log`：

```
common_speculative_init_result: failed to load draft model, '...blobs\sha256-491f38...'
srv  llama_server: exiting due to model loading error
```

`gemma4` 這一家是用 speculative decoding 的，本體之外還要載一個 draft model；殘留的 runner 一卡住那個檔，整個模型就起不來（API 回 500、`ollama ps` 是空的、每個請求卡快 30 秒才失敗）。

正確的重啟順序：

```powershell
Get-Process -Name "ollama app","ollama","llama-server" -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Id $_.Id -Force }
Start-Sleep -Seconds 5
Start-Process "C:\Users\User\AppData\Local\Programs\Ollama\ollama app.exe"
```

- 砍乾淨之後 `nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader` 只剩 1 GiB 左右。
- 接著**暖機**：帶 `num_ctx` 8192（跟遊戲一樣，不然遊戲第一次呼叫會整個重載）。`ollama ps` 要列出模型、`PROCESSOR` 寫 `100% GPU`。
- **改 `OLLAMA_*` 環境變數之後要另開一次 PowerShell 再重啟 Ollama**：`SetEnvironmentVariable(...,"User")` 不會改到當下這個 PowerShell 自己的環境區塊，同一次呼叫裡 `Start-Process` 起來的 Ollama 繼承的還是舊值。

## 伺服器自己的排程（2026-10-24 起打開）

打開之後，伺服器每隔幾秒自己推一次全服的事：世界時間、時刻表的大事、時間到了開決戰、決戰的集結與回合逾時、季末。沒有人開著網頁時也照樣跑。關著的時候跟以前一樣，要有人連線（或假人程式在跑）世界才會動。

- **現在是開的**（減法季批 0，設計稿第十章「伺服器排程打開」）：開關是 `world_tick_seconds`，`content/config.json` 寫 10，每一份設定（weekend、season21、week7）都照它。程式本身的預設還是 0（關），測試內容照那個。
- 要關：在用的設定檔加上 `"world_tick_seconds": 0`（例如 `content/profiles/week7.json`），重開伺服器。數字是 0（關）或至少 1 秒，寫 0.5 之類的伺服器會開不起來。
- 重開伺服器之後，啟動訊息在「設定：…」下面會多一行 `排程：每 10 秒推一次全服的事…`；關著時是 `排程：關（世界時間等有人連線才推）`。
- 假人程式照舊另外開，兩個可以同時開。
- **打開之後，有決戰的時候本機 AI（Ollama）要開著**：沒有人在線時，決戰的回合也由伺服器自己結算，結算時會請模型寫一段戰況。Ollama 沒開的話不影響勝負（戰況改用固定的文字），但決戰期間每隔幾分鐘會印一對「鎖內的模型呼叫失敗或逾時…」「…暫停滿 180 秒，下一次再試模型。」。
- 排程出錯時，伺服器會印一行「排程這一下出錯：KeyError」這樣的話，下一輪照跑。
  - 只寫錯誤的種類，不寫錯誤的內容：內容可能夾著角色的名號。主控台寫不出某個字、或寫紀錄本身出錯，也不會讓排程停下來。
  - 同一個錯一直重複時只印第一次；之後換了別的錯、或每過 10 分鐘，印一行「排程這一下又出錯 N 次：…（同一個地方，細節同上）」。
  - 在視窗裡開的：這一行和後面出錯的程式位置都在伺服器視窗。
  - 照下面「給 session 用」在背景開的：這一行在 `server_out.log`，出錯的程式位置在 `server_err.log`。
  - 看到這一行請回報：視窗就截圖，背景開的就把兩個 log 一起附上。

## 伺服器推送（預設關）

打開之後，網頁有變化時伺服器會主動通知，不用等下一次輪詢：自己的另一個分頁做了動作，1～2 秒內跟著更新；大事發生、決戰打完一回合（「世界變了」），**預設設定下反而比輪詢慢**：平均約 7.5 秒、最慢約 25 秒才更新（每 10 秒輪詢是平均 5 秒、最慢 10 秒）。要等的三段是：兩次通知至少隔 10 秒、看守每 5 秒看一次世界、各分頁再隨機等 0～10 秒才去抓（免得全服同時擠進來）。所以推送省的是**請求數**（平常每 60 秒才問一次，輪詢是每 10 秒），不是延遲；試玩要快就照下面把兩個數字調小。關著的時候跟以前一樣，每 10 秒問一次。

- **現在是關的**：開關是 `push_events`，預設 `false`。玩家用的設定（`content/config.json`、`content/profiles/weekend.json`）都還沒打開。要在哪一份打開，等驗收過了由 PM 決定。
- 怎麼打開：在用的設定檔加上 `"push_events": true`，重開伺服器（跟排程一樣：週末設定是 `content/profiles/weekend.json`；用的是預設設定，就加在 `content/config.json`）。
  - 啟動訊息在排程那一行下面會多一行 `推送：開（SSE；世界每 5 秒看一次，兩次通知至少隔 10 秒）`；關著時是 `推送：關（分頁每 10 秒輪詢）`。
  - 另外兩個數字可以不動：`push_watch_seconds`（看守每幾秒看一次世界，預設 5，要大於 0）、`push_world_min_seconds`（兩次「世界變了」的通知至少隔幾秒，也是各分頁收到之後隨機等多久才去抓，預設 10，0 是不限制）。想讓世界的變化更快出現，就把兩個都調小。**試玩建議 `push_watch_seconds` 寫 2、`push_world_min_seconds` 寫 2～3**（平均約 2.5 秒、最慢約 8 秒）；代價是同一時間更多人一起來問，所以 `push_world_min_seconds` 要大於等於開著的分頁數 ÷ 30（一百個分頁以內 2～3 秒；三百個分頁就是預設的 10 秒）。
  - **推送和排程請一起開**（兩個都加：`"push_events": true` 和 `"world_tick_seconds": 10`，排程見上一節）。看守只看世界、不推進世界；時間到了該結算的事（決戰回合與集結的期限、時刻表的大事），平常是排程或假人程式推進的。只開推送、排程關著、也沒有假人程式在跑（例如一兩個人的小型試玩）時，過了期限沒有人動作，就要等某個人的下一次輪詢才結算；推送開著時輪詢是每 60 秒一次（以前 10 秒），所以最多晚 60 秒才結算，結算之後世界的通知又晚 5～10 秒才到。排程開著，期限一到最多 10 秒內就結算，推送再把它送出去。有假人程式在跑時，假人每 20 秒一輪也會推進決戰，影響比較小，但兩個一起開還是對的。
- 推送斷了（例如伺服器重開），網頁會自動回到每 10 秒問一次，不用做什麼；重開後不必重新登入（登入狀態在資料庫，審查 S-10），推送自己再連上。
- 怎麼知道連上了：網頁開發者工具（F12）的「網路」頁，會有一個叫 `events` 的請求一直開著（類型 eventsource），點進去每 15 秒一個 `ping`。推送連著的時候，`/api/main` 大約每 60 秒才出現一次，另外加上收到通知時的幾次。
- 看不到的分頁（切到別的分頁、手機鎖屏）會自動放掉推送連線，回來的時候再連、補抓一次。
- 看到伺服器視窗印「推送的看守這一下出錯：KeyError」這樣的話，請截圖回報。
  - 那一輪沒有發出通知，下一輪照看；一直出錯的話，大事、決戰回合這類「世界變了」的通知就送不出去，網頁只能靠每 60 秒一次的慢速輪詢跟上（自己另一個分頁做的動作不受影響）。
  - 跟排程同一個規矩：只寫錯誤的種類，不寫錯誤的內容（內容可能夾著角色的名號）；同一個錯一直重複時只印第一次，之後每過 10 分鐘印一行「推送的看守這一下又出錯 N 次：…（同一個地方，細節同上）」。
  - 在視窗裡開的：這一行和後面出錯的程式位置都在伺服器視窗。照下面「給 session 用」在背景開的：這一行在 `server_out.log`，出錯的程式位置在 `server_err.log`。

## 手機通知（Web Push；減法季批 9，2026-10-24）

分頁關著、手機鎖著也跳一則通知：來信、約戰、決戰集結、被截殺、被〈天下形勢〉提到。跟上一節的「伺服器推送」（SSE，只叫醒開著的分頁）是兩回事。**主機的開關是開的**（`content/config.json` 的 `"web_push": {"enabled": true}`），玩家在設定頁自己打開「手機通知」（預設關；第一次有人來信時，信的小卡底下也會問一次）。

- **第一次要做**：`pip install -r requirements.txt`（這一版多了 `cryptography`，簽名與加密要它）。沒裝也開得起來，只是啟動訊息會寫「手機通知：關（這台主機沒裝 cryptography…）」，設定頁不畫那一顆。
- 啟動訊息多一行：`手機通知：開（每 30 秒看一次開了通知的人；金鑰 …\.local\webpush_vapid.pem）`。
- 金鑰：第一次開時自動產生在 `.local/webpush_vapid.pem`（不進版控）。**不要刪、不要換**；換了之後所有人要到設定頁把通知關掉再打開一次。備份 `.local/` 時一起帶走。
- 誰開了通知記在資料庫旁邊的 `saves/tianxia-push.sqlite`（`TIANXIA_DB` 換了檔，它跟著換名字）。丟了只是大家要再按一次，不影響遊戲。
- 要 https 才收得到（瀏覽器的規矩）：走固定網域 https://tianxiadashi.com 就可以，127.0.0.1 在本機也可以試；區網的 `http://192.168…` 不行。
- 09:00 來信：減法季的季（`season21`、`week7`）人物的信每天當地 09:00 起才送（`jianfa.morning_mail`、`mail_hour`）；開了通知的人，看守 9 點一到就替他送、手機跳「某某派人送來一封信」，不必等他上線。沒開通知的人照舊上線才收到。
- 正在玩的人（2 分鐘內動過、分頁開著）不跳：畫面上已經看得到。伺服器重開後第一輪只記下、不補跳停機那段時間的事。

**驗收（要真手機收到一次）**：
1. 主機 `pip install -r requirements.txt`、重開 `server.py`，確認啟動訊息有「手機通知：開」。
2. Android（Chrome）：用手機開 https://tianxiadashi.com 登入 → 右上角齒輪 → 勾「手機通知」→ 允許通知。**幾秒內手機會跳一則「手機通知開了：……」**，這一則就是驗收。
3. iPhone（iOS 16.4 以上）：Safari 開網址 → 分享 → 「加入主畫面」→ 從主畫面的圖示打開、登入 → 齒輪 → 勾「手機通知」→ 允許。一樣會跳「手機通知開了」。沒加到主畫面時設定頁會寫要先加。
4. 真的事件：關掉遊戲，等 09:00 來信，或請另一個人截殺你、等決戰集結；30 秒內跳一則。
5. 沒跳：看手機系統的通知設定有沒有擋 Chrome／這個網站；伺服器視窗印「通知的看守這一下出錯：…」請截圖回報（同排程的規矩，只寫錯誤的種類）。

## 事件旁白每週改寫（減法季批 10，2026-10-25）

減法季的季（`season21`、`week7`）裡，事件卡上那一段旁白每週由本機模型重寫一次，全服同一份；選項、檢定、效果一個字都不變。序章、開局、伏筆、晉升召見、一次性奇遇不改。模型沒開、寫壞了，照原文，遊戲不受影響。

- 啟動訊息多一行：`旁白改寫：開（每 20 秒一則，排在真人後面；寫在 …\saves\tianxia-narration.sqlite）`。關著時是 `旁白改寫：關`。
- 一週約兩百四十則短呼叫，每 20 秒一則，一個多小時寫完；排在真人後面。**省電模式開著、10 分鐘內沒人玩時不寫**，讓模型卸得掉；有人回來再接著寫。
- 改寫存在 `saves/tianxia-narration.sqlite`（跟著 `TIANXIA_DB` 換名字）。丟了只是這一週照原文、背景再寫一次，不必備份。
- 要關：在用的設定檔（`content/profiles/season21.json` 或 `week7.json`）把 `"jianfa": {"enabled": true}` 改成 `"jianfa": {"enabled": true, "rewrite_narration": false}`（`enabled` 要留著，不然整個減法季都關了），重開伺服器。

**看品質（上線前先跑一次）**：伺服器不必停，但這台的 Ollama 同時在給線上用，先少量試：

```
.venv/Scripts/python.exe scripts/try_narration.py                 # 十則
.venv/Scripts/python.exe scripts/try_narration.py -n 30 --random  # 隨機三十則
.venv/Scripts/python.exe scripts/try_narration.py --all --out narration_week.txt  # 整週，全文存檔慢慢看
```

每一則印原文、改寫、幾秒；寫壞照原文的印原因（太長太短、冒出原文沒有的名字……）。最後一行是總計：寫成幾則、照原文幾則、平均幾秒。照原文的超過三成、或讀起來走味，把 `narration_week.txt` 傳回來。

## 網址在哪、怎麼給 joy

- 伺服器視窗會先印「天下大勢：http://127.0.0.1:7861」和「資料庫：…」，**大約 7 秒後**再印：
  `公開網址：https://xxxx.trycloudflare.com（給手機用；有網址的人都進得來，不要外流）`
- 把 `https://` 開頭那一串複製給 joy。企劃者自己在這台電腦上玩，照樣開 http://127.0.0.1:7861 就好。
- **伺服器一重開，網址就會換**，要把新網址重新給 joy。舊網址在 cloudflared 跟著關掉之後就失效，打開會看到 Cloudflare 的錯誤頁（HTTP 530）。
- 伺服器重開後**每個人都要重新登入一次**。帳號、角色、進度都還在。
- 有網址的人都能進來註冊，所以網址只私下給，不要貼在公開的地方。

## 固定網域（Cloudflare 具名 Tunnel）——2026-10-13 已經做好了

**網址是 https://tianxiadashi.com**（`www.tianxiadashi.com` 指同一條），隧道叫 `tianxia`。重開伺服器網址不會變，所以 LINE、Google 登入登記的回傳網址、分享出去的連結都可以寫死它。

- **伺服器從此不要加 `--share`**。`--share` 是開 trycloudflare 臨時網址用的，每次重開都換一組；兩個一起開只是多一條沒人用的網址。
- 隧道是**獨立的行程**，跟伺服器各自開關：伺服器重開不必動隧道。
- 設定在 `C:\Users\User\.cloudflared\config.yml`（隧道 id、憑證檔、兩個 hostname 都指 `http://127.0.0.1:7861`）。`cert.pem` 與 `<UUID>.json` 是密鑰：**不要進 git、不要貼進任何對話或頻道**。
- **分享的「傳」要用這個網址**：啟動伺服器前設 `TIANXIA_PUBLIC_URL=https://tianxiadashi.com`，不然公開的傳會照「這次請求的網址」組，trycloudflare 時代那些連結過幾天就死了。

怎麼開隧道（Claude session 用 WMI 分離啟動，跟伺服器同一套做法）：

```powershell
$cf  = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
$log = "C:\Users\User\.cloudflared\tunnel.log"
$cmd = "cmd.exe /c `"`"$cf`" tunnel run tianxia > `"$log`" 2>&1`""
Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine = $cmd; CurrentDirectory = "C:\Users\User\.cloudflared"}
```

`tunnel.log` 出現四行 `Registered tunnel connection`（實測是 tpe01／khh01，台北與高雄的邊緣節點）就通了。要停：挑 `cloudflared.exe` 跑 `tunnel run tianxia` 的行程砍掉。

怎麼驗（**先看 HTTP，不要只看 HTTPS**）：

```powershell
curl -o /dev/null -w "%{http_code}`n" http://tianxiadashi.com/
```

- **200**＝伺服器也開著，整條路都通。
- **502**＝隧道通、DNS 對，只是遊戲伺服器沒開。這是伺服器停著時的正常回應，不是故障。
- 連不上、`000`＝DNS 或隧道的問題，看 `tunnel.log`。
- **新網域剛接上時 HTTPS 會先失敗**（TLS handshake 被拒）：Cloudflare 的 Universal SSL 還沒簽發，等 15 分鐘到幾小時。HTTP 已經回 502 或 200 就表示 DNS 與隧道都對了，只差憑證。一直不好就看 Cloudflare 後台 SSL/TLS → Edge Certificates 是不是 Active。**憑證還沒好之前不要把網址發給玩家**，他們只會看到連不上。
- 登入 cookie 不受影響：`server.py` 的 `tx_session` 只有 `httponly` 與 `samesite=lax`，沒有綁 scheme。

下面是當初建起來的步驟，留著備查（換網域、或要在另一台機器重建時照它做一次）。指令裡的 `tianxia-game.com` 換成你的網域。

> 這台電腦已經裝好 cloudflared（2026.9.3），下面的指令都是它內建說明裡有的。哪一步出了沒寫到的訊息，截圖給 PM。

**一、買網域，交給 Cloudflare 管**

1. 登入 Cloudflare 的網站，左邊「網域註冊」→「註冊網域」，搜尋想要的名字，照畫面付款。在 Cloudflare 買的網域，DNS 自動就在 Cloudflare，不用另外設。
2. 已經在別家買了網域：在 Cloudflare 按「新增網站」加進來，照畫面把那家的名稱伺服器（nameserver）改成 Cloudflare 給的兩個。改好之後可能要等幾小時才生效。

**二、讓這台電腦登入 Cloudflare、建隧道**（一次就好）

開一個 PowerShell 視窗：

```powershell
cloudflared tunnel login
```

- 瀏覽器會打開 Cloudflare 的授權頁，選你的網域、按「授權」。
- 回到視窗，看到檔案寫進 `C:\Users\<你>\.cloudflared\cert.pem` 就好。這個檔是你的 Cloudflare 憑證，**不要給任何人、不要放進 git 或貼在對話裡**。

```powershell
cloudflared tunnel create tianxia
```

- 會印出一串隧道編號（UUID），並在同一個資料夾寫一個 `<UUID>.json`。這也是密鑰，同樣不外流。

```powershell
cloudflared tunnel route dns tianxia tianxia-game.com
```

- 在 Cloudflare 的 DNS 加一筆紀錄，讓 `tianxia-game.com` 指到這條隧道。
- 想用子網域（例如 `play.tianxia-game.com`），就把最後那一段換成子網域。

**三、平常怎麼開**

伺服器照平常開，**不要加 `--share`**（`--share` 是開臨時網址的）：

```powershell
cd C:\Ray\專案\天下大勢
$env:TIANXIA_DB = "C:\Ray\tianxia-play\tianxia.db"
.venv\Scripts\python.exe -u server.py --port 7861
```

另開一個視窗開隧道：

```powershell
cloudflared tunnel run --url http://127.0.0.1:7861 tianxia
```

- 看到幾行「Registered tunnel connection」就通了，手機打開 `https://tianxia-game.com` 試試。
- 這個網址重開也不會變，所以 LINE、Google 的回傳網址都填它：
  - `https://tianxia-game.com/auth/line/callback`
  - `https://tianxia-game.com/auth/google/callback`
- 帳號計畫的 `.local/oauth.json` 裡，`base_url` 也寫 `https://tianxia-game.com`。
- 要停：在隧道視窗按 Ctrl+C。伺服器那個視窗照舊。

**四、（選擇性）讓隧道開機自己跑**

先用第三步的視窗方式跑順，再考慮這一步。要用系統管理員身分開 PowerShell。

1. 在 `C:\Users\<你>\.cloudflared\` 建一個 `config.yml`，內容如下：
   - `<UUID>` 換成第二步印出來的那一串；
   - 檔案路徑寫完整。

   ```yaml
   tunnel: <UUID>
   credentials-file: C:\Windows\System32\config\systemprofile\.cloudflared\<UUID>.json
   ingress:
     - hostname: tianxia-game.com
       service: http://127.0.0.1:7861
     - service: http_status:404
   ```

2. 系統服務是用系統帳號跑的，讀不到你自己資料夾的檔。所以要把 `config.yml` 與 `<UUID>.json` 兩個檔，複製到 `C:\Windows\System32\config\systemprofile\.cloudflared\`；資料夾沒有就建一個。
3. 在系統管理員的 PowerShell 打 `cloudflared service install`。
4. 到「服務」程式找 Cloudflared，確認是「執行中」、啟動類型是「自動」。
5. 服務起不來時：先 `cloudflared service uninstall`，回到第三步的視窗方式，截圖給 PM。

伺服器本身要不要也開機自動跑，是部署那一期的事；在那之前，伺服器照舊用視窗開。

## 監控頁（只給管理者看）

`scripts/monitor.py`：在線人數、賽季、行程、模型、最近的錯誤，一頁看完。跟遊戲**完全分開**（自己一個行程、自己一個埠 7899、資料庫一律唯讀），它掛了不影響遊戲。

- 本機：<http://127.0.0.1:7899>
- 外面（2026-10-14 加的，企劃者「我在外面根本看不到」）：**<https://monitor.tianxiadashi.com>**，走同一條具名 Tunnel（`~/.cloudflared/config.yml` 多一條 ingress 指 `http://127.0.0.1:7899`）。
- **要密碼**（HTTP Basic，帳號隨便打）：這一頁把真人與假人分開數，而「誰是假人」任何玩家都不能看到（伺服器假人設計第五節）。隧道來的連線在監控頁看起來跟本機一模一樣（cloudflared 跑在同一台），擋不了來源，只能擋密碼。密碼在 `.local/monitor.txt`（第一次啟動自己產生、也印在啟動訊息裡；`.local/` 不進版控）。想換密碼就改那一行、重開 monitor.py。環境變數 `TIANXIA_MONITOR_PASSWORD` 優先。
- 怎麼開（session 用，跟伺服器同一套分離啟動）：`.venv\Scripts\python.exe -u scripts/monitor.py > monitor_out.log 2> monitor_err.log`。
- 改了 `config.yml` 的 ingress 要**重開隧道**才生效（砍掉跑 `tunnel run tianxia` 的 cloudflared 再照「固定網域」那一節開起來）；遊戲網址會中斷幾秒。
- 驗法：`curl -u admin:<密碼> https://monitor.tianxiadashi.com/` 回 200，不帶密碼回 401。

## 看守：重開機、當掉都自己站起來（2026-10-14 加的）

起因：2026-10-14 11:45 Windows 更新的**強制期限**到了，`TrustedInstaller` 自己重開機（事件 1074「作業系統: 升級（計劃之中）」）——它蓋過當時設的活動時間 8–17，而且更新重開後 Windows 不會自動登回帳號，所以整台機器空著、服務斷到有人來開。

現在有一個看守工作：`C:\Users\User\tianxia-ops\watchdog.ps1`，工作排程器裡叫 **`tianxia-watchdog`**（**登入時**跑一次＋之後**每 5 分鐘**一次，無限重複；跑在 `JOY\User` 的工作階段，不必管理員權限）。每一輪看五樣，缺哪樣就補開哪樣，**不會去砍還活著的行程**：

1. `server.py`（看行程在不在；在、但 7861 沒在聽只寫一行警告，不自動重開——那通常要人看一下）
2. `run_bots.py`
3. `scripts/monitor.py`
4. `cloudflared tunnel run tianxia`
5. Ollama：API 不回應就開 `ollama app.exe`；模型不在記憶體裡就暖機（帶 `num_ctx` 8192，跟遊戲一樣）

- 做了什麼都寫在 `C:\Users\User\tianxia-ops\watchdog.log`（一切正常時它不寫東西）。補開之前會把死掉那一支的 `*_err.log` 複製成 `crash-<時間>-<名字>_err.log` 留證。
- 啟動參數在 `C:\Users\User\tianxia-ops` 的 `start_server.cmd`／`start_bots.cmd`／`start_monitor.cmd`（設定 `week7`、`TIANXIA_PUBLIC_URL=https://tianxiadashi.com`、資料庫用工作樹裡的 `saves\tianxia.db`）。**換設定或換資料庫要改這三個檔**，不然看守補開的還是舊的那一套。
- **要停服務之前先暫停看守**，不然五分鐘內它就幫你開回來：

```powershell
New-Item C:\Users\User\tianxia-ops\PAUSED -ItemType File   # 暫停看守
Remove-Item C:\Users\User\tianxia-ops\PAUSED               # 恢復看守
```

- 手動跑一次（不用等五分鐘）：`Start-ScheduledTask -TaskName tianxia-watchdog`。要拿掉：`Unregister-ScheduledTask -TaskName tianxia-watchdog`。
- **還缺一件要管理員權限的事**：更新重開之後要 Windows 自動登回帳號，看守才會在沒人的時候跑起來（設定 → 帳戶 → 登入選項 →「使用我的登入資訊在更新後自動完成裝置設定」打開；登錄檔是 `HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon` 的 `ARSOUserConsent`＝1）。沒打開的話，重開機後要有人登入，看守才會動。
- 要少挨一次強制重開（都要管理員權限，Home 版不保證每一條都生效，所以看守才是真正的保險）：活動時間拉到最大 18 小時（`HKLM\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings` 的 `ActiveHoursStart`＝9、`ActiveHoursEnd`＝3、`SmartActiveHoursState`＝0），加上 `HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU` 的 `NoAutoRebootWithLoggedOnUsers`＝1 與 `HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate` 的 `ConfigureDeadlineNoAutoReboot`＝1。大型試玩之前最穩的還是直接在設定 → Windows Update 按「暫停更新」（最多 5 週）。

## 怎麼停

> **先暫停看守**：`New-Item C:\Users\User\tianxia-ops\PAUSED -ItemType File`。不然 `tianxia-watchdog` 會在五分鐘內把你剛停掉的東西全部開回來（見上一節）。事情做完記得把 `PAUSED` 刪掉。

在兩個視窗各按一次 **Ctrl+C**。伺服器和 cloudflared 會一起關掉，不會留下東西。直接關掉視窗也可以。

伺服器關機時最多等 3 秒，讓還沒結束的連線收掉才結束。推送開著、網頁還開著的時候，每個網頁都有一條一直開著的推送連線，所以 Ctrl+C 之後多等幾秒是正常的，不必再按一次。還在處理的請求會先做完；等到時間才被取消的連線，伺服器視窗可能多印一行「Cancel N running task(s)…」，只是個數，不是錯誤。

- **換成決戰改版 1（強攻、固守、奇襲三招）之前，先確認沒有決戰在集結或在打。** 有的話，先用 `Rayal` 登入，⚙ → 管理者工具 →「⚠ 取消決戰」→「確定取消」，再停伺服器換版。
  - 原因：換版前就加入的人沒有三招的份量快照，跨過換版的那一場由「哪一邊的人先連線補上」決定勝負（實測：只有一個玩家連線補上時，第 6 回合官軍就大勝到 92）。
  - 取消的是時刻表上的決戰時，那一場不會自己再開，要用「定結果」收尾（見上面「換成第一季濃縮版的那一天」第 4 步）。

## 要停很久的時候：先讓賽季時鐘暫停

伺服器關著的那段時間，賽季照樣在算：開回來之後第一個連上的人，會把整段停機時間一次補進賽季（大事照時間結算、決戰照時間開打或判掉）。要停一兩個鐘頭以上（大改版、搬電腦），**關伺服器之前先暫停賽季時鐘**，伺服器開回來之後再讓它繼續：停的那一段不算進賽季，季末跟著往後延。

- 遊戲裡：用管理者登入，⚙ → 管理者工具 →「⏸ 暫停賽季時鐘」→「確定暫停」。開回來之後同一個地方按「▶ 繼續」。
- 主機上（不用登入；伺服器開著或關著都可以，但 `resume` 請等伺服器開回來再跑：時間已經過了的決戰會在那一刻開始集結）：

  ```powershell
  $env:TIANXIA_DB = "C:\Ray\tianxia-play\tianxia.db"
  $env:TIANXIA_PROFILE = "weekend"   # 跟伺服器同一份設定；伺服器沒設就不要設
  .venv\Scripts\python.exe scripts\season_clock.py pause     # 關伺服器之前
  .venv\Scripts\python.exe scripts\season_clock.py resume    # 伺服器開回來之後
  .venv\Scripts\python.exe scripts\season_clock.py status    # 看現在是停著還是在走
  ```

- 暫停中玩家看得到畫面，江湖頁只剩一顆灰的「賽季暫停中（停機維護）」，按什麼都回這一句；假人程式不出手。
- 決戰打到一半暫停：集結、這一回合剩下的時間停住，繼續之後接著倒數。
- **排好的三場決戰照原本約好的現實時間開**，不用重排。原本的時間落在停機那段裡的，按「繼續」（或跑 `resume`）的那一刻就開始集結。停得很久（週末那季 7 個多鐘頭以上）時，決戰不會搶在原本排在它前面的大事之前，那時會晚一點開。
- 季末與一般的大事往後延停的長度（照季曆的整點算：週末那季不足 1 分 47 秒的零頭照算進賽季）。所以停得比一個季曆鐘頭短（週末那季不到 1 分 47 秒、12 週的正式季不到 1 小時）的話，什麼都不會另外扣、季末也不延——繼續那一行會直接這麼說。
- `resume` 讀的設定要跟伺服器同一份。對不上這一季開季時蓋的章（第一季規則開／關、季長）的話它會拒絕、時鐘還停著：先確認 `--profile` 或 `TIANXIA_PROFILE` 跟伺服器開的一樣；已經一樣的話（開季之後設定改過），改在遊戲裡用管理者工具的「▶ 繼續」，那一個用的是伺服器自己那一份設定，沒有這個問題。
- 玩家自己的體力、氣血照現實時間回，停機期間也回，這不算在賽季裡。
- 忘了按繼續，賽季就一直停著：設定頁的管理者工具會寫「已暫停 N 分鐘」。

## 這台電腦還要做別的事：省電模式與睡／醒（2026-10-18）

量過了（線上 1 個真人、近一小時 3 個）：**吃掉這台機器的不是遊戲程式，是常駐的模型。**

| | CPU（單核％，12 核） | RAM | VRAM |
|---|---|---|---|
| `server.py` | 1.7%（8.8 小時平均） | 151 MB | – |
| `run_bots.py` | 0.7% | 97 MB | – |
| `monitor.py`、`warm_keeper.py`、隧道 | ~0.1% | 各 30～45 MB | – |
| **gemma4:12b（`llama-server.exe`）** | 0.7%（閒置） | 10.5 GB | **約 9.1 GiB** |

所以**不要去砍假人、調巡邏頻率**（量到省不了，只會讓江湖變冷清）。要省就省模型那一塊。

### 省電模式：遊戲照開，模型只在有人玩的時候佔 VRAM

開關是旗標檔 `.local/power_save`（`tianxia/power_save.py`）：在的時候模型的 `keep_alive` 改成檔裡寫的（預設 `5m`），沒人玩就讓 Ollama 卸掉模型。**不必重開伺服器、玩家不必重新登入**——`OllamaClient.keep_alive` 是個 property，每次模型呼叫都問一次旗標檔，所以 `server.py` 與 `run_bots.py` 兩個行程、每個角色那一份 client 都當場跟著換。

```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\User\.claude\tianxia-powersave.ps1 on      # 開（順手請 Ollama 現在就卸掉模型）
powershell -ExecutionPolicy Bypass -File C:\Users\User\.claude\tianxia-powersave.ps1 off     # 關（順手把模型暖回來）
powershell -ExecutionPolicy Bypass -File C:\Users\User\.claude\tianxia-powersave.ps1 status  # 看現在開著沒、VRAM 多少、模型載著沒
```

配套的是 `scripts/warm_keeper.py`（ensure-up 會一起開）：**有真人在線就每分鐘替模型續一次命**，沒人在線就不送、省電模式下還請 Ollama 現在就卸掉。有它才不會踩 2026-10-10 那個坑（模型卸掉之後第一個要模型的動作撞上冷啟動）——連「只走路、半小時沒叫過模型」的人也一直是熱的。登入那一下另外由 `server.py::_warm_model` 預熱（射後不理，登入請求不等）。

代價寫清楚：模型真的卸掉之後，下一次載回來**實測 11.4 秒**（`num_ctx` 8192，2026-10-18 的 Ollama 版本；CLAUDE.md 記的 24 秒與 10-10 記的 89 秒是舊版與別的 ctx）。遊戲的讀取逾時 30 秒、鎖內 15 秒、斷路器 180 秒，所以 11.4 秒撐得過去，但鎖內那 15 秒沒有太多餘裕——這就是為什麼要有暖機看守與登入預熱。

### 睡的時候外面看到「江湖暫歇」，不是 502（2026-10-18）

Joy：「這可以線上不要 502，顯示伺服器維修中嗎」。做法是 `scripts/maintenance.py`：**在同一個埠（7861）上接管**，
於是隧道連得到來源、回的是我們自己的頁面——Cloudflare 只有在「連不到來源」時才塞它自己的 502，
來源真的回應了就原樣送出去。驗過（拿監控頁那條路試，不動遊戲）：外面收到的是 `HTTP/1.1 503`、
`retry-after: 30`、我們那一頁的 HTML，整份裡沒有 cloudflare 字樣。

- 狀態碼是 **503 ＋ Retry-After**，不是 200：這才是「暫時不能服務」，瀏覽器與爬蟲不會把它當成正式內容。
- `/api/` 回 JSON（`{"maintenance": true}`），其餘回那一頁：網頁每 10 秒打 `/api/main` 並解析 JSON，回 HTML 會在那邊炸開。
- 頁面每 30 秒自己探一次，伺服器一回來就跳回江湖，玩家不必自己重整。
- `--note "換電腦，約一小時"` 多寫一句給玩家看。
- **埠被佔著它就起不來**（`allow_reuse_address = False`）：Windows 的 SO_REUSEADDR 允許綁上一個已經有人在聽的埠、
  兩個行程分著收請求——維修頁要是這樣綁上 7861，玩家的請求會一半進遊戲、一半看到「維修中」（實機踩到：
  監控頁跟維修頁同時聽著 7899，外面看到的是維修頁）。寧可起不來，也不能從活著的伺服器手上偷走流量。
- `tianxia-sleep.ps1` 停完伺服器就把它開起來，`tianxia-wake.ps1` 與 `tianxia-ensure-up.ps1` 都會**先把它收掉**再開伺服器
  （兩個都要聽 7861，順序弄反伺服器綁不上）。
- 行程比對一律用「`-u <腳本>`」這個樣式，**不要加工作樹路徑**：`.venv` 的 `python.exe` 是啟動器，
  它開出來的真行程命令列寫的是基礎安裝那個 python 的路徑，要求路徑會整個漏掉（實機踩到：維修頁沒被收掉）。

### 睡／醒：要打遊戲、算圖，整疊停乾淨

```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\User\.claude\tianxia-sleep.ps1   # 暫停賽季時鐘 → 停四支 python → 卸模型
powershell -ExecutionPolicy Bypass -File C:\Users\User\.claude\tianxia-wake.ps1    # 繼續賽季時鐘 → ensure-up → 暖機看守 → 驗證
```

- 睡的時候**隧道刻意留著**（44 MB／0.1%）：網址還在，外面看到的是維修頁（上一段），醒來不必重設。
- 賽季時鐘由腳本 pause／resume（見上一節），停的那一段不算進賽季。
- **公告要自己發**（Discord 中繼在 session 裡，腳本不碰它）。

## 怎麼備份資料庫

伺服器開著也可以備份。備份腳本用 SQLite 內建的線上備份，做出來的是一個獨立的 `.db` 檔，先驗過才放上去。備份先放在這台電腦的資料夾 `C:\Ray\tianxia-play\backup`，不上雲端（企劃者 2026-10-06 定）；之後要上雲，看下面「之後要上雲時怎麼改」。

**封存檔**（2026-10-31，審查 S-12）：開下一季時，上上季的傳聞與決戰回合紀錄會搬到資料庫旁邊的 `tianxia-archive.sqlite`（跟著 `TIANXIA_DB` 換名字），遊戲本身不再讀它、是備用的。備份腳本只備份主檔，要留著封存的資料就把這個檔一起複製走（換季之後做一次就好，它只在換季時變）。

**手動備份**：換程式、收季、出事之前做。手動備份永遠留著，不會被刪。

```powershell
cd C:\Ray\專案\天下大勢
$env:TIANXIA_DB = "C:\Ray\tianxia-play\tianxia.db"
.venv\Scripts\python.exe scripts\backup_db.py --dest C:\Ray\tianxia-play\backup
```

成功會印：`已備份：C:\Ray\tianxia-play\backup\tianxia-manual-20261006-050000.db（結構第 2 版、帳號 3、角色 5、季 2、江湖史 120）`。失敗會印「備份失敗：…」，原因寫在後面。備份先寫成 `.partial`，驗過才改成正式的檔名，所以資料夾裡看到 `tianxia-…db` 的，都是驗過的。

**每天自動備份**：企劃者自己設一次就好。下面的 `schtasks` 是**給企劃者自己貼的**：它會改這台電腦的排程設定，PM 和其他 Claude session 不要代貼、不要代跑。

1. 開一個 PowerShell 視窗，貼下面這一段。排程設在每天早上 5 點，備份放 `C:\Ray\tianxia-play\backup`：

   ```powershell
   $py = "C:\Ray\專案\天下大勢\.venv\Scripts\python.exe"
   $script = "C:\Ray\專案\天下大勢\scripts\backup_db.py"
   $taskArgs = "`"$script`" --db C:\Ray\tianxia-play\tianxia.db --dest C:\Ray\tianxia-play\backup --tag daily --prune"
   schtasks /Create /TN "天下大勢每日備份" /SC DAILY /ST 05:00 /TR "`"$py`" $taskArgs" /F
   ```
2. 馬上試跑一次：`schtasks /Run /TN "天下大勢每日備份"`。然後到 `C:\Ray\tianxia-play\backup`，看有沒有一個 `tianxia-daily-…db`。
3. 之後在「工作排程器」程式裡，可以看到這個工作的「上次執行結果」：`0x0` 是成功，`0x1` 是失敗。
4. 在「工作排程器」找到這個工作，雙擊打開，**改兩個預設值**（`schtasks` 建出來的工作，預設在沒插電、或錯過時間的時候都不會跑）：
   - 「條件」分頁 →「電源」：取消勾選「只有在電腦使用 AC 電源時，才啟動這個工作」（英文介面：Start the task only if the computer is on AC power），也取消「電腦改用電池電源時停止」（Stop if the computer switches to battery power）。新建的工作預設兩個都是勾著的，筆電沒插電那天就不備份；中文字樣可能和這裡寫的略有出入，認得出電源那兩條就是。
   - 「設定」分頁：勾「若錯過排定的開始時間，儘快啟動工作」。電腦在 5 點關機或睡眠，那一天就不會備份，勾了之後開機會補跑。

- **只在這個使用者登入時才會跑**：上面的指令沒有 `/RU`，工作是用目前這個使用者的身分建的，登出或鎖在登入畫面時不會執行。這台試玩主機要一直保持登入。要改成沒登入也跑，得在工作的「一般」分頁選「不論使用者登入與否，都要執行」，會要你輸入 Windows 密碼，自己決定要不要。
- 每日備份只留最近 14 天每天一份，加最近 8 週每週一份，其餘自動刪掉；最新的一份不管多舊都會留著。手動備份和資料夾裡別的檔都不會被刪。
- 某一份舊備份刪不掉（被別的程式開著）時，其他能刪的照刪，腳本最後把刪不掉的檔一份一份列出來、印「刪舊備份失敗」，「上次執行結果」會是 `0x1`；今天的備份已經做好，隔天會再試。
- 資料夾裡有 `.bad` 結尾的檔，是驗證沒通過的備份，留著給人查原因（把檔案和那次印出的訊息給開發的人），不會被自動刪。資料庫自己壞掉時（腳本印「資料庫本身壞了」），複製到一半的檔也會留成 `.bad`，每天跑一次就多一份，壞掉修好之後記得自己清掉。
- 遊戲的資料庫換了位置（例如換到線上版資料夾），第 1 步要重貼一次，`/F` 會蓋掉舊的。
- 備份和遊戲資料在同一顆硬碟：硬碟壞掉時兩份一起沒。在還沒上雲之前，偶爾把 `C:\Ray\tianxia-play\backup` 整個資料夾複製到隨身碟或別台電腦。

### 之後要上雲時怎麼改

腳本不用動，只要把每天備份的目的地換成雲端硬碟的同步資料夾：

1. 決定同步資料夾，例如 `C:\Users\<你>\OneDrive\tianxia-backup`，或 Google 雲端硬碟電腦版的資料夾。
2. 自己貼下面這一段（一樣是企劃者自己貼）。雲端資料夾的路徑常常有空白（例如 `OneDrive - 公司`），**一定要照這個寫法**，把 `<你>` 換成你的使用者名稱：

   ```powershell
   $py = "C:\Ray\專案\天下大勢\.venv\Scripts\python.exe"
   $script = "C:\Ray\專案\天下大勢\scripts\backup_db.py"
   $taskArgs = "\`"$script\`" --db C:\Ray\tianxia-play\tianxia.db --dest \`"C:\Users\<你>\OneDrive - 公司\tianxia-backup\`" --tag daily --prune"
   schtasks /Create /TN "天下大勢每日備份" /SC DAILY /ST 05:00 /TR "\`"$py\`" $taskArgs" /F
   ```

   - 字串裡的雙引號要寫成 ``\`"``（反斜線、反引號、雙引號，三個字元連在一起）。這台電腦的 Windows PowerShell 5.1 把字串交給 `schtasks` 之前，會吃掉只寫 `` `" ``（反引號加雙引號）的那種引號，路徑就在空白處被切成好幾段，工作建得起來、每天卻跑錯；寫成 ``\`"`` 才會原封不動送到（2026-10-06 在這台電腦上，用一支只把收到的引數印出來的小程式代替 `schtasks` 試過：三種寫法裡只有這一種收到的 `/TR` 是完整、引號都在的）。
   - 上面「每天自動備份」那段本機指令的路徑沒有空白，引號被吃掉也不影響，所以不用改；只有目的地有空白才要用這個寫法。
   - `/F` 會蓋掉舊的排程，不會多出第二個。重貼之後，「工作排程器」裡的「條件」「設定」兩個勾（第 4 步）要再確認一次。
   - 貼完先看一眼：在「工作排程器」雙擊這個工作 →「動作」，「新增引數」裡 `--dest` 後面的路徑要有雙引號包著。
3. 馬上試跑一次：`schtasks /Run /TN "天下大勢每日備份"`，到雲端資料夾看有沒有 `tianxia-daily-…db`，再等雲端程式顯示同步完成。
4. 本機 `C:\Ray\tianxia-play\backup` 裡原本的備份留著，之後不會再被自動刪（保留規則只看目的地那個資料夾），要清就自己清。想兩邊都留，就另外建一個工作：`/TN` 換一個名字、`--dest` 各填各的。
5. 備份檔是單一個 `.db`、先寫成 `.partial` 驗過才改名，所以雲端程式不會同步到寫到一半的檔。雲端程式正在同步舊檔時，刪舊備份可能失敗：今天的備份已經做好，腳本會印「刪舊備份失敗」、「上次執行結果」是 `0x1`，隔天會再刪一次。

## 怎麼還原

1. **先停掉伺服器和假人程式**，兩個視窗各按 Ctrl+C。沒停掉的話，還原腳本會拒絕，什麼都不動。
   - 這個保護**只在 Windows 有用**：它靠的是 Windows 上還開著的檔案改不了名。在 Linux 或 macOS 上，改名不管檔案有沒有被打開都會成功，腳本攔不住，會把還開著的資料庫搬走。這台試玩主機是 Windows，沒問題；之後資料庫搬到別的系統上，要自己先確定兩個程式都停了。
2. 找到要還原的備份檔，然後：

   ```powershell
   cd C:\Ray\專案\天下大勢
   .venv\Scripts\python.exe scripts\restore_db.py <備份檔> --db C:\Ray\tianxia-play\tianxia.db
   ```
3. 成功會印「已還原：…」，以及「還原前的資料庫留在：…pre-restore-…」。原本的檔改了名留著。如果舊的資料庫旁邊還有 `-wal`、`-shm`、`-journal`（伺服器當機留下的），它們也一起改了名，腳本會把這些檔的路徑一個一個印出來。複製不過去（例如磁碟滿了）會印「還原失敗」，現在的資料庫一點都沒動。
4. 照平常的方式開伺服器和假人。所有人都要重新登入一次。

**還原錯了、要退回去**：先停掉伺服器和假人，再把還原出來的檔移開，把舊的改名回去，**舊的 `-wal`、`-shm`、`-journal` 有印出來的也要一起改回去**（不然舊的資料庫會少掉還沒寫進主檔的最後一段）。以腳本印出的檔名為準，下面是例子：

```powershell
cd C:\Ray\tianxia-play
Rename-Item tianxia.db tianxia.db.restored
Rename-Item tianxia.db.pre-restore-20261006-050000 tianxia.db
Rename-Item tianxia.db.pre-restore-20261006-050000-wal tianxia.db-wal   # 腳本有印出 -wal 才做
Rename-Item tianxia.db.pre-restore-20261006-050000-shm tianxia.db-shm   # 腳本有印出 -shm 才做
```

**還原前的舊檔（`tianxia.db.pre-restore-…`）什麼時候可以清**：
- 確定還原回來的資料庫沒問題就可以清：大家照常玩過一天，而且還原之後的每日備份至少成功一次（備份資料夾裡有一份時間在還原之後的 `tianxia-daily-…db`）。
- 清的時候連它旁邊同名的 `-wal`、`-shm`、`-journal` 一起刪，例如 `Remove-Item C:\Ray\tianxia-play\tianxia.db.pre-restore-20261006-050000*`。
- 這些舊檔不在備份資料夾裡，保留規則不會自動刪它們，不清就會一直留著。

**每個月實際還原一次**，確認備份真的能用（線上架構設計 8.5）：

1. 拿最新的一份每日備份，還原到一個**練習用的檔**，不要還原到正式的那一份：

   ```powershell
   .venv\Scripts\python.exe scripts\restore_db.py <最新的每日備份> --db C:\Ray\tianxia-play\restore-drill.db
   ```
2. 再用這個練習檔開一個伺服器，看角色在不在。**另開一個新的 PowerShell 視窗**，三行都要打：

   ```powershell
   cd C:\Ray\專案\天下大勢
   $env:TIANXIA_DB = "C:\Ray\tianxia-play\restore-drill.db"
   .venv\Scripts\python.exe -u server.py --port 7899
   ```

   - 第二行一定要打。如果在剛做過手動備份的同一個視窗開，`$env:TIANXIA_DB` 還指著正式的 `tianxia.db`，開起來的就是正式資料庫。
   - 啟動時印的「資料庫：…」要是 `restore-drill.db`，不是就馬上 Ctrl+C。
   - 不加 `--share`：只在這台電腦上看，不開公開網址。
   - 正式的伺服器（7861）可以照常開著，兩邊用的是不同的檔、不同的埠。
   - 打開 http://127.0.0.1:7899，用平常的帳號登入（練習檔是正式資料的複本，帳號密碼都一樣），看角色、江湖史都在。
3. 看完在這個視窗按 Ctrl+C 停掉伺服器，再把練習檔刪乾淨：

   ```powershell
   Remove-Item C:\Ray\tianxia-play\restore-drill.db*
   ```

   - 結尾的 `*` 會一起刪掉 `restore-drill.db-wal`、`restore-drill.db-shm`（直接關視窗時常常留著），以及之前演練留下的 `restore-drill.db.pre-restore-…`。
   - 要先按 Ctrl+C 停掉，檔案還開著時刪不掉，會出現「正由另一個處理程序使用」。
   - 這個指令只會刪檔名開頭是 `restore-drill.db` 的檔，正式的 `tianxia.db` 不受影響。

**裝備一上線之後要退回舊程式**：先停伺服器和假人，再拿上線前的備份照上面還原。舊程式會把裝備庫裡的防具當成種類空白的兵器讀（畫面當兵器列、換得上手），身上的防具（`armor`）會被略過、下次存檔就丟了；資料庫版本沒變，所以舊程式打得開檔、不會報錯——不還原就退版，玩家的防具會悄悄不見。

**裝備二（坐騎）上線之後要退回舊程式**：同裝備一，先停伺服器和假人，再拿上線前的備份照上面還原。要退回的是裝備一那一版（`9c87ed96`）：它的 `Equipment.slot` 認得「mount」，但欄位表 `SLOTS` 只有武器、防具，表外的欄位一律當關著。所以身上騎著的那一匹（`PlayerState.mount`）、飽足提醒（`hunger_warned`）、馬市選單的旗標（`picking_market`）舊程式不認得，讀檔時略過、下次存檔就丟了——騎著的馬就這樣不見；裝備庫裡的馬不會丟，存檔照留，但舊程式不列、換不上、拆不了，看不見卻照樣佔裝備庫的格子（`rack_full` 算整個裝備庫的長度，滿了會擋住新東西）；路上的人照存檔裡排好的抵達時刻走到，抵達的時間不變；但出發時騎的馬的步調（`Journey.pace`）舊程式不認得、略過，它的 `atlas.road_spot` 反推位置時照沒騎馬的整段時間算，所以那一趟還在路上的人，輿圖上的路上標記會比實際位置靠前一些，中途改道、折返時算的半段路也會跟著歪——只影響那一趟，走完就沒事，不傷存檔。資料庫版本沒變，舊程式打得開檔、不會報錯——不還原就退版，玩家騎著的馬會悄悄不見、裝備庫裡的馬看不見又佔格子。

**裝備三（寶物與好馬）上線之後要退回舊程式**：同裝備一、二，先停伺服器和假人，再拿上線前的備份照上面還原。舊程式會略過身上的寶物（`treasure`）、寄放的東西（`held_gear`）與掉過寶物的人物，下次存檔就丟了；裝備庫裡的寶物看不到、但照樣佔格子（裝備一已經寫齊四種 `slot`，舊程式照欄位過濾；裝備二開發時實際驗過退回裝備一的情形，PM 2026-10-12 照它改正）；全服的名將贈禮名單（`general_gifts`）、天機蓋章（`tianji`）與懸賞榜上還沒交差的重賞（`Bounty.prize`，那幾張討伐交差時就不給寶物、良駒了）也會在下一次存季時丟掉。資料庫版本沒變，舊程式打得開檔、不會報錯——不還原就退版，玩家的寶物會悄悄不見。

**打造第一批（隱藏配方與防具）上線之後要退回舊程式**：資料庫版本沒變（第 4 版），舊程式打得開檔、不會壞檔：隱藏配方的發現記在 `gear_recipes` 裡「鑄|」開頭的列，舊程式不讀（名字欄是鍵本身，不佔名字空間）；角色存檔多的 `forge_manual`、裝備上的 `secret` 舊程式略過；名器照存檔裡的名字照穿照用，只是加成變回一般的；打出來的防具照穿（減損照算淬煉次數），打到一半的防具單子在讀檔時被舊程式當成不認識的種類清掉。退回去之後打造會照舊叫模型取名、登記一般配方。照慣例先停伺服器和假人、拿上線前的備份還原最乾淨，不還原也不會丟玩家的東西。

**打造第二批（神器）上線之後要退回舊程式**：這一批沒改資料庫結構（維持第 5 版；第 5 版是玩家傳第一批升的，要退到那一批之前看那一段），退回打造第二批之前的程式打得開檔、不會壞檔：神器原品的主人、定的名字、仿品數記在 `gear_recipes` 裡「鑄|」那幾列的 `data`，舊程式讀成名器那一筆、不認得神器；定了名的那一列名字欄是定的名字，舊程式照樣當它被佔，不會撞名。手上的原品、仿品照存檔的名字照用，只是加成變回一般三階上品，原品也拆得掉、交得了（舊程式不認 `original`）。三階素材的新來源跟著沒了，已經拿到的照留。照慣例先停伺服器和假人、拿上線前的備份還原最乾淨，不還原也不會丟玩家的東西。

**打造第三批（名將本命兵器）上線之後要退回舊程式**：這一批沒改資料庫結構（維持第 5 版），退回打造第二批的程式打得開檔、不會壞檔：本命兵器變成沒有 `secret` 的神器原品（舊程式不認 `Equipment.signature`，讀檔時略過），手上的那一把加成、「・神器」的階品、拆不得、交不得照舊（舊程式的 `original` 那幾支），名字照存檔寫的（舊程式不重寫它，joy 之後改的名字跟不上）；舊程式的 `forge_secrets.unnamed_originals`、`refresh_names` 都先看 `secret`，本命兵器沒有 `secret`，所以不會出現在「等著定名」裡、名字也不會被神器那一列改掉。本命兵器的歸屬（`WorldState.signature_arms`）與這一季打贏名將的次數（`PlayerState.figure_wins`）舊程式不認得，下一次存季、存角色就丟了：這一季那位名將可能再給一次，已經收了的季（`seasons` 表裡舊的那幾列）不受影響，只是神器譜上本命兵器那幾行（舊程式不讀）看不到。照慣例先停伺服器和假人、拿上線前的備份還原最乾淨，不還原也不會丟玩家手上的東西。

**玉璽一（玉璽碎片）上線之後要退回舊程式**：資料庫版本沒變（第 5 版），舊程式打得開檔，但**會丟碎片**：舊程式讀 world 那一列時略過不認得的 `seal`、`seal_duels`，下一次寫入就整個沒了（誰持有哪一片、密鹽、單挑都不在了）；角色身上的 `heirloom`、`seal_seen`、`seen_real` 也一樣。**更糟的是拿過「奪璽」戰報的角色**（戰報的 kind 是 `seal`，舊程式不認得）：舊程式讀不進他的存檔，會把它備份起來、替他開一個新角色（「舊存檔的格式已不相容」）——人整個重來，不只是丟碎片。所以退版一定要停伺服器和假人、拿上線前的備份還原；不還原的話，再升回新程式時七片全部回到未現世。

**大勢平衡（trend-balance）上線之後要退回舊程式**：不改資料庫結構、不改內容，退回去打得開檔。規則關著的季照舊：遊歷打贏推的大勢不照季長縮放、黃巾聲勢推過 60 當下就開黃巾決戰；已經累積的零頭（`trend_accum`）照舊留著用。週末設定（第一季規則開著）兩邊一樣。

**玉璽二（天命之爭）上線之後要退回舊程式**：資料庫版本沒變（第 5 版），但舊程式會丟天命之季的章（`mandate`、`mandate_result`、登記的 `mandate_season`、`mandate_pending`）：正在跑的天命之季會變回一般季（提前收季、璽動照 7%、天命之爭從時刻表消失）。退版一定要停伺服器和假人、拿上線前的備份還原。

**挑戰大勢人物每季都有上線之後要退回舊程式**：先試緊急開關——`content/config.json` 加一行 `"figure_challenge_every_season": false`，兩個程式重開：第一季以外的季沒有挑戰鈕、不閉門、求見照 `talk_at`、聲威不回、虛擬玩家照常出手、輿圖跟以前一樣（已經記下的 `bocai_defeated` 留著）。真的要退版：資料庫結構沒變（第 5 版），舊程式打得開檔；`PlayerState.figure_rare_drops`、`trend_accum` 的 `regen:`、`lost:` 鍵、14 天的季寫進去的 `WorldState.figures` 舊程式都不讀或略過；退版前先把 `content/config.json` 裡這一批新的設定（`figure_challenge_every_season`、`figure_prestige_regen`、`figure_daily_loss_cap`、`figure_rare_cap`、`figure_treasure_cap`）拿掉，`content/figures.json` 的 `out_flag` 跟著程式一起退——舊程式的 `Config`、`FigureDef` 不認得這些欄位，讀設定就會報錯。`tier3_per_figure` 退回 2 照舊程式的值。照慣例先停伺服器和假人、拿上線前的備份還原最乾淨。

## 商城上線：資料庫升到第 6 版（2026-10-20）

商城（元寶、回體丹、月卡；規則見 `docs/guide/商城.md`）是這一版的程式第一次改資料庫結構：新程式第一次打開資料庫（伺服器、假人程式、`set_password.py` 誰先開都一樣），會把第 5 版的檔就地升到第 6 版——多三張表：元寶的帳 `mall_ledger`、購買紀錄 `mall_purchases`、月卡 `mall_entitlements`。升級在同一筆交易裡做完，中途出錯整筆撤回、檔還是第 5 版。原本的角色、帳號、江湖史一筆都不動。

**升上去就回不去**：舊程式（第 5 版）打開第 6 版的檔，會直接報「資料庫結構是第 6 版，這版程式只認得第 5 版」、開不起來。要退版只能拿升級前的備份還原（上面「怎麼還原」）。所以這一次**部署前一定先手動備份**：

1. 先停伺服器和假人（上面「怎麼停」；記得先放 `PAUSED` 暫停看守）。
2. 手動備份（新舊程式的備份腳本都認得第 5 版，用哪一份都可以）：

   ```powershell
   cd C:\Ray\專案\天下大勢
   $env:TIANXIA_DB = "C:\Ray\tianxia-play\tianxia.db"
   .venv\Scripts\python.exe scripts\backup_db.py --dest C:\Ray\tianxia-play\backup
   ```

   要看到「已備份：…tianxia-manual-…db（**結構第 5 版**、帳號 N、角色 N、季 N、江湖史 N）」才往下走。手動備份永遠留著，不會被每日備份的保留規則刪掉。這一份就是退版要用的那一份，檔名記下來。
3. 換程式，照平常的方式開伺服器和假人。開機印的「資料庫：…」兩邊要一樣。
4. 驗：再做一次手動備份（同上），這一次印的要是「**結構第 6 版**」，帳號、角色、季、江湖史的數字跟第 2 步一樣。

全新的資料庫（例如七天封測另開一份）一開始就直接建成第 6 版，不必備份也沒有升級這一步。

**元寶只在 `TIANXIA_PROFILE=week7` 發**：

- 封測的 5000 元寶寫在 `content/profiles/week7.json` 的 `"mall": {"enabled": true, "beta_grant": 5000}`。兩個程式啟動前都設 `$env:TIANXIA_PROFILE = "week7"`，開機印的「設定：week7（第一季濃縮版規則開啟、季長 7 天、人數上限 20）」兩邊要一樣。
- 每個角色第一次進來（登入之後第一次讀到江湖畫面；假人是它自己那一輪）發一次、江湖紀錄一則「商城」；之後再開新的一季、重新登入都不再發。還沒建角色的帳號要等建了角色才發。
- 其他設定（不設、`weekend`、`season21`）照 `content/config.json` 的 `"mall": {"enabled": true}`：商城照樣開著、看得到，但**不發元寶**（大家都是 0，買不了東西）。
- 要臨時關掉商城：沒設 `week7` 時改 `content/config.json` 的 `"mall"` 成 `{"enabled": false}`；設了 `week7` 時改的是 `content/profiles/week7.json` 那一段的 `"enabled"`（設定覆寫檔是整段蓋過去的，改 `config.json` 沒用）。兩個程式一起重開。關著時沒有入口、商城的網址都回 404、月卡不加回體丹上限、也不發元寶；帳都還在資料庫裡，開回來照舊。

**對帳：`scripts/mall_ledger.py`**（只讀；伺服器開著也可以跑）

```powershell
cd C:\Ray\專案\天下大勢
.venv\Scripts\python.exe scripts\mall_ledger.py --db C:\Ray\tianxia-play\tianxia.db --out C:\Ray\tianxia-play\ledger-20261025.csv
```

- **`--db` 一定要寫**：不寫就照這個視窗的 `$env:TIANXIA_DB`，沒設是 repo 裡的 `saves\tianxia.db`（不是線上那一份）。
- 它用 SQLite 的唯讀模式開檔：不升級、不拿寫入權、不改任何一筆。伺服器沒開著時資料庫旁邊會多出空的 `-wal`、`-shm`，是 SQLite 自己的，不用管。
- `--out` 寫成 CSV（utf-8-sig，Excel 直接開不亂碼）；不給 `--out` 就印在畫面上。一筆帳一列：編號、時間（台灣）、名號、錢包、增減、原因（封測發放／購買／退款／補發／扣回）、單號、購買（連著哪一筆購買）、經手（補發、扣回、退款的管理者）、說明、那一筆之後這個錢包的餘額。
- 畫面最後兩行是總結：

  ```
  帳 128 筆、錢包 25 個；發出 125000、花掉 9600、餘額合計 115400
  負的餘額：沒有
  ```

  怎麼看：封測期間「發出」大約是 5000 × 錢包數，再加補發與退款；「花掉」是購買加扣回。「負的餘額」照理永遠是「沒有」（程式擋著扣到負的）；寫了名號就是出事了，結束碼是 1，把 CSV 和這兩行一起交給開發。
- 檔案還是第 5 版（新程式還沒開過它）：印「這份資料庫還是第 5 版（還沒升級），沒有商城的帳」，不寫 CSV。路徑打錯、不是資料庫：印「打不開資料庫檔：…」，結束碼 1。
- 個別一個人的帳、補發、扣回、退一筆購買在遊戲裡做：用管理者登入，⚙ → 管理者工具 →「商城」那一組（每一筆都寫進帳：誰、何時、為什麼）。

正式開服時整份資料庫換新，元寶、購買紀錄、月卡一起清掉。

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

   - 它會一次換掉四個值：第一季開關、一季 2.5 天、人數上限 2，外加測試期間的「一鍵補滿體力」開關（狀態列體力條上的鈕寫「補滿」、按一下直接補滿、不花丹；`content/profiles/weekend.json`）。
   - 啟動時「資料庫：…」下面會印 `設定：weekend（第一季濃縮版規則開啟、季長 2.5 天、人數上限 2）　測試期一鍵補滿體力：開`。沒設的時候印 `設定：預設`。最後那句「測試期一鍵補滿體力：開」就是補滿開著的記號；測試期結束把 `weekend.json` 的 `beta_free_refill` 拿掉之後，這句不再印。
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

## 截殺太兇時：緊急開關

懸賞榜第一批起，截殺、通緝、懸賞榜、遊俠名號每一季都有（不只週末設定）。上線之後要是假人截殺真人太兇（假人每一輪有一成機會截殺此地勝算「穩勝」「有把握」的敵對陣營玩家），不必退版：

1. 在 `content/config.json` 最外層加一段 `"raid": {"enabled": false}`（已經有 `"raid"` 就在裡面加 `"enabled": false`）。
2. 照上面「怎麼停」把 `server.py` 與 `run_bots.py` 都停掉，再照「開伺服器和假人」一起重開（兩邊啟動時印的「設定：…」要一樣）。

關著時：玩家卡上沒有「截殺」，假人也不截殺；通緝一起收——卡上沒有「通緝」、押不了，已經押的不在懸賞榜上、揭了的人手上不算它，到期照退押金給掛單的人。要再打開就把那一行刪掉、兩個程式一起重開，還沒到期的通緝照常出現。開關關了又開之後，同一個人手上可能暫時超過 3 張（關著時通緝不佔格）；拒絕句照實寫手上幾張，交掉之前不能再揭。整個懸賞榜也有一個開關（`"bounties": {"enabled": false}`），一般用不到。

**要退回懸賞榜第一批之前的程式時**，先把 `content/config.json` 裡這兩個開關的 `"enabled": false` 拿掉：舊程式不認得 `enabled` 這個欄位，啟動時讀設定就報錯、開不起來。

## 給 session 用：不開視窗的啟動與停止

Claude session 不能開互動視窗，改用 `Start-Process` 在背景啟動，輸出寫進 log。**記下回傳的 PID**，停的時候要用：

> **2026-10-14 這台機器的實際位置**：工作樹是 `C:\Users\User\Documents\ai_story-tianxia`（`.venv` 也在裡面），資料庫就用它的 `saves\tianxia.db`（**不必設 `TIANXIA_DB`**），設定是 `TIANXIA_PROFILE=week7`（第一季規則開、季長 7 天、人數上限 20）。下面指令裡的 `C:\Ray\專案\天下大勢` 與 `TIANXIA_DB` 是舊的那份 clone，照抄會開到另一個世界——**開工前先用 `git worktree list` 核對，並且比對 `server_out.log` 的「資料庫：…」「設定：…」兩行**。
> Windows 自動更新重開機之後，四樣都要重開：隧道、`server.py`、`run_bots.py`、`scripts/monitor.py`，再把 Ollama 暖機（`ollama ps` 要寫 `100% GPU`）。


```powershell
cd C:\Ray\專案\天下大勢
$env:TIANXIA_DB = "C:\Ray\tianxia-play\tianxia.db"
$env:TIANXIA_PUBLIC_URL = "https://tianxiadashi.com"   # 分享的「傳」用固定網域
$srv = Start-Process .venv\Scripts\python.exe -ArgumentList "-u","server.py","--port","7861" -RedirectStandardOutput server_out.log -RedirectStandardError server_err.log -WindowStyle Hidden -PassThru
$bots = Start-Process .venv\Scripts\python.exe -ArgumentList "-u","run_bots.py" -RedirectStandardOutput bots_out.log -RedirectStandardError bots_err.log -WindowStyle Hidden -PassThru
"server $($srv.Id)  bots $($bots.Id)"
```

- **2026-10-13 起不加 `--share`**：網址是固定的 https://tianxiadashi.com（見上面「固定網域」），隧道另外開一個行程，伺服器重開網址不變、不必再等 log 印網址、也不必重新發給玩家。還要臨時網址時才加 `--share`（公開網址印在 `server_out.log`，大約 7 秒後出現；用 `Get-Content server_out.log -Encoding UTF8` 讀，不加 `-Encoding UTF8` 中文會變亂碼）。
- 啟動訊息還是要對：`server_out.log` 與 `bots_out.log` 的「資料庫：…」「設定：…」兩行要一樣。
- `-u` 一定要加。沒加的話，Python 寫檔時會先存在緩衝裡，伺服器其實已經開好了，log 卻一直是空的。
- **停的時候用 `/T` 關整棵**：`taskkill /PID <server 的 PID> /T /F`，假人也一樣。實測這樣會連 cloudflared 一起關掉。
- **不要只關「正在聽 7861 的那個 PID」**：`.venv` 的 python.exe 會再開一個真正的 python，cloudflared 是那個 python 開出來的。只關它的話，cloudflared 會留著、繼續連 7861，**重開後舊網址照樣進得到新伺服器**（FB-021）。
- 不確定有沒有殘留時，先停掉伺服器，再跑下面這行清掉，**最後才重開**。順序不能倒過來：這行會把連到 7861 的 cloudflared 全部關掉，包括新開的那個。

```powershell
Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" | Where-Object CommandLine -match '127.0.0.1:7861' | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

## 已知限制

- 推送開著、而且是直接用 `http://127.0.0.1` 或 `--lan` 連（不是經過 trycloudflare 的 https）時，瀏覽器對同一個網址最多同時開 6 條連線，每個看得到的分頁佔一條推送連線：同一個瀏覽器同時看著 6 個以上的視窗，請求會卡住。背景的分頁會自動放掉連線，所以只有同時看得到的才算；經過 trycloudflare（HTTP/2）沒有這個問題。
- trycloudflare 是 Cloudflare 給測試用的免費服務，不保證不斷線。斷了就重開伺服器，再給一次新網址。實測開著 22 分鐘，每分鐘從外面打一次，都正常（每次 0.4～1.5 秒）。
- Cloudflare 對單一請求大約只等 100 秒。實測本機 AI 都遠低於這個數字（模型 `gemma4:26b` 已載入時），經過公開網址也一樣：
  - 求見人物：11.5 秒；交談一輪：11～12 秒。
  - 隨口應對：9 秒；5 個人同時送，最慢 27 秒。
  - 煉製新配方取名：4 秒。
