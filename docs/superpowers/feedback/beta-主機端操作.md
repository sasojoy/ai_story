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

- **現在是關的**：開關是 `world_tick_seconds`，預設 0（關）。玩家用的設定（`content/config.json`、`content/profiles/weekend.json`）都還沒打開；只有壓測用的設定（壓測計畫的 `loadtest`）會打開。要在哪一份玩家用的設定打開，等驗收過了由 PM 決定。
- 怎麼打開：在用的設定檔加上 `"world_tick_seconds": 10`。例如週末設定是 `content/profiles/weekend.json`；用的是預設設定，就加在 `content/config.json`。數字是 0（關）或至少 1 秒，寫 0.5 之類的伺服器會開不起來。
- 重開伺服器之後，啟動訊息在「設定：…」下面會多一行 `排程：每 10 秒推一次全服的事…`；關著時是 `排程：關（世界時間等有人連線才推）`。
- 假人程式照舊另外開，兩個可以同時開。
- **打開之後，有決戰的時候本機 AI（Ollama）要開著**：沒有人在線時，決戰的回合也由伺服器自己結算，結算時會請模型寫一段戰況。Ollama 沒開的話不影響勝負（戰況改用固定的文字），但決戰期間每隔幾分鐘會印一對「鎖內的模型呼叫失敗或逾時…」「…暫停滿 180 秒，下一次再試模型。」。
- 排程出錯時，伺服器會印一行「排程這一下出錯：KeyError」這樣的話，下一輪照跑。
  - 只寫錯誤的種類，不寫錯誤的內容：內容可能夾著角色的名號。主控台寫不出某個字、或寫紀錄本身出錯，也不會讓排程停下來。
  - 同一個錯一直重複時只印第一次；之後換了別的錯、或每過 10 分鐘，印一行「排程這一下又出錯 N 次：…（同一個地方，細節同上）」。
  - 在視窗裡開的：這一行和後面出錯的程式位置都在伺服器視窗。
  - 照下面「給 session 用」在背景開的：這一行在 `server_out.log`，出錯的程式位置在 `server_err.log`。
  - 看到這一行請回報：視窗就截圖，背景開的就把兩個 log 一起附上。

## 網址在哪、怎麼給 joy

- 伺服器視窗會先印「天下大勢：http://127.0.0.1:7861」和「資料庫：…」，**大約 7 秒後**再印：
  `公開網址：https://xxxx.trycloudflare.com（給手機用；有網址的人都進得來，不要外流）`
- 把 `https://` 開頭那一串複製給 joy。企劃者自己在這台電腦上玩，照樣開 http://127.0.0.1:7861 就好。
- **伺服器一重開，網址就會換**，要把新網址重新給 joy。舊網址在 cloudflared 跟著關掉之後就失效，打開會看到 Cloudflare 的錯誤頁（HTTP 530）。
- 伺服器重開後**每個人都要重新登入一次**。帳號、角色、進度都還在。
- 有網址的人都能進來註冊，所以網址只私下給，不要貼在公開的地方。

## 換成自己的網域（Cloudflare 具名 Tunnel）

封測要用固定的網址：LINE、Google 登入只認事先登記好的網址；trycloudflare 每次重開都換，不能用（線上架構帳號計畫開頭的清單第 1、2 項）。下面是企劃者自己做一次的步驟。指令裡的 `tianxia-game.com` 換成你買的網域，`tianxia` 是隧道的名字，照用就好。

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

## 怎麼停

在兩個視窗各按一次 **Ctrl+C**。伺服器和 cloudflared 會一起關掉，不會留下東西。直接關掉視窗也可以。

## 怎麼備份資料庫

伺服器開著也可以備份。備份腳本用 SQLite 內建的線上備份，做出來的是一個獨立的 `.db` 檔，先驗過才放上去。備份先放在這台電腦的資料夾 `C:\Ray\tianxia-play\backup`，不上雲端（企劃者 2026-10-06 定）；之後要上雲，看下面「之後要上雲時怎麼改」。

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
