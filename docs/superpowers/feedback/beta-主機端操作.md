# 分享版試玩伺服器：主機端操作

給企劃者，也給幫忙重開伺服器的 PM session。目的是讓 joy 這種不在同一個地方的朋友，連到這台電腦上的試玩伺服器。

做法是 `server.py --share`：伺服器會叫 cloudflared 開一個 trycloudflare 臨時公開網址。不用帳號、不用設定，但**每次重開，網址都會換**。

> 標「待實測」的地方，QA 還沒在這台電腦上試過。cloudflared 裝好後會實測，再改成確定的說法。

## 第一次要先做的

1. **裝 cloudflared**：在 PowerShell 打 `winget install Cloudflare.cloudflared`。裝完**另開一個新的** PowerShell 視窗，打 `cloudflared --version`，看到版本號就好了。
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

## 網址在哪、怎麼給 joy

- 伺服器視窗會先印「天下大勢：http://127.0.0.1:7861」和「資料庫：…」，過幾秒再印：
  `公開網址：https://xxxx.trycloudflare.com（給手機用；有網址的人都進得來，不要外流）`
- 把 `https://` 開頭那一串複製給 joy。企劃者自己在這台電腦上玩，照樣開 http://127.0.0.1:7861 就好。
- **伺服器一重開，網址就會換**，要把新網址重新給 joy。舊網址會不會失效：待實測。
- 伺服器重開後**每個人都要重新登入一次**。帳號、角色、進度都還在。
- 有網址的人都能進來註冊，所以網址只私下給，不要貼在公開的地方。

## 怎麼停

在兩個視窗各按一次 **Ctrl+C**。cloudflared 會不會跟著關：待實測。

## 怎麼備份資料庫

1. 先把伺服器和假人**兩個都停掉**。
2. 把資料庫的三個檔一起複製到別的資料夾：`tianxia.db`、`tianxia.db-wal`、`tianxia.db-shm`。後兩個有時候不存在，有就一起帶。

```powershell
$dst = "C:\Ray\tianxia-play\backup\$(Get-Date -Format yyyyMMdd-HHmm)"
New-Item -ItemType Directory -Force $dst | Out-Null
Copy-Item C:\Ray\tianxia-play\tianxia.db* $dst
```

要還原時，一樣先停掉兩個程式，再把這三個檔複製回去。

## 給 session 用：不開視窗的啟動與停止

Claude session 不能開互動視窗，改用 `Start-Process` 在背景啟動，輸出寫進 log：

```powershell
cd C:\Ray\專案\天下大勢
$env:TIANXIA_DB = "C:\Ray\tianxia-play\tianxia.db"
Start-Process .venv\Scripts\python.exe -ArgumentList "-u","server.py","--port","7861","--share" -RedirectStandardOutput server_out.log -RedirectStandardError server_err.log -WindowStyle Hidden
Start-Process .venv\Scripts\python.exe -ArgumentList "-u","run_bots.py" -RedirectStandardOutput bots_out.log -RedirectStandardError bots_err.log -WindowStyle Hidden
```

- 公開網址印在 `server_out.log`，要等幾秒才會出現。
- `-u` 一定要加。沒加的話，Python 寫檔時會先存在緩衝裡，伺服器其實已經開好了，log 卻一直是空的。
- 停的時候：用 `netstat -ano | findstr :7861` 找出真正在聽這個埠的 PID，`taskkill /PID <pid> /F` 關掉。`Start-Process` 回傳的 PID 常常不是這一個。
- cloudflared 是伺服器開出來的子程式，伺服器被強制關掉時，它可能還留著（待實測）。留著的話要另外關：

```powershell
Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" | Where-Object CommandLine -match '127.0.0.1:7861' | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

## 已知限制

- trycloudflare 是 Cloudflare 給測試用的免費服務，不保證不斷線。斷了就重開伺服器，再給一次新網址。
- 本機 AI 回得慢時（煉製新配方取名實測過 27～83 秒），經過公開網址會不會逾時：待實測。
