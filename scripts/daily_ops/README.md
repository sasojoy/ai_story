# 每日備份與每日數字：主機安裝步驟（2026-11-25）

正式站那台主機每天做兩件事：

| 時間（台北） | 做什麼 | 指令 |
|---|---|---|
| 05:00 | 線上備份主資料庫、所有旁檔、客服截圖夾，另開一份讀一次，記下成敗 | `scripts/backup_db.py --tag daily --prune --drill --status .local/backup_status.json` |
| 08:00 | 讀資料庫（唯讀）算昨天的玩家數字，存全文，短報經主機的 Discord 機器人貼出 | `scripts/daily_report.py` |

兩支都**不停站、不進行動鎖**：備份用 SQLite 的線上備份，數字用唯讀模式開檔。伺服器開著、省電模式睡著都可以跑。

- 備份帶：主資料庫，加上旁檔 identity、support、terms、yiwen、mail、mail-archive、talk、talk-archive、archive、push、tale（名單是 `backup_db.py` 的 `SIDE_FILES`），還有 `<db>-support-files\` 截圖夾。narration 不帶（丟了背景再寫）。
- 保留：每日備份留最近 14 天每天一份，加最近 8 週每週一份，最多約 22 份；手動備份與部署前的備份永遠不刪。
- 驗：每一份先驗 integrity_check、結構版本、列數才換上正式檔名；`--drill` 再把它複製到暫存資料夾，用這版程式真的打開、每個角色的存檔讀一次，做完刪掉複本。
- 短報：只有數字與鈕的名稱，不印名號、帳號、IP；假人只給總數。備份失敗或超過 36 小時沒成功，短報第一行就是「⚠ 備份失敗」。
- `.local/` 不進版控：`backup_status.json`、`daily_report.json`（轉送設定）、`daily_report\<日期>.txt` 都在這裡。

## 安裝（PM 遙控主機做；在跑正式站的那份 clone 裡）

先確認是對的那份 clone：它正在跑 `server.py`，`saves\` 裡有線上的資料庫。資料庫路徑照看守的 `start_server.cmd` 裡的 `TIANXIA_DB` 為準（沒設就是 clone 裡的 `saves\tianxia.db`）。

1. **先查有沒有舊的排程**，有就記下來回報，不要直接蓋掉：
   ```powershell
   schtasks /Query /FO LIST | Select-String "天下大勢" -Context 0,3
   ```
2. **在 clone 的根目錄開 PowerShell**，算好路徑（不要手打路徑）：
   ```powershell
   $repo = (git rev-parse --show-toplevel) -replace '/', '\'
   $py   = "$repo\.venv\Scripts\python.exe"
   $db   = "$repo\saves\tianxia.db"          # 跟 start_server.cmd 的 TIANXIA_DB 不同就改成那一個
   $dest = "$repo\saves\backups\daily"
   Test-Path $py, $db                         # 兩個都要是 True
   ```
3. **先手動跑一次**，兩支都要成功：
   ```powershell
   & $py "$repo\scripts\backup_db.py" --db $db --dest $dest --tag daily --prune --drill --status "$repo\.local\backup_status.json"
   & $py "$repo\scripts\daily_report.py" --db $db --no-post
   ```
   備份要看到「已備份：…tianxia-daily-…db（結構第 9 版、帳號 N、角色 N…）」、每個旁檔一行「已備份旁檔」、「還原演練：另開一份讀得回來，角色 N 個」。數字那支印出短報，第三或第一行的備份要是「成功」。
4. **接主機現有的 Discord 機器人**（Joy 2026-11-25 選的，不用 webhook）：`.local\daily_report.json` 寫
   ```json
   {"relay": {"script": "<使用者資料夾>\\.claude\\discord-relay\\relay.py 的完整路徑", "channel": "<頻道的數字代號>"}}
   ```
   代號用管理員頻道的；路徑和代號只寫在這個檔，不寫進任何文件。python 預設用遊戲的 `.venv`（要換就多寫 `"python": "<路徑>"`）。
   再跑一次 `daily_report.py`（不加 `--no-post`），結束碼要是 0、頻道裡看得到一則短報。
   - 短報超過 2,000 字會截短並寫「全文在主機」，所以一定是一則；失敗會再試一次，兩次都失敗結束碼 1，全文照樣存在 `.local\daily_report\`。
   - 舊的寫法 `{"discord_webhook": "<網址>"}` 還認得；兩個都寫時走 relay。
5. **排兩個工作**：
   ```powershell
   $bk = "`"$repo\scripts\backup_db.py`" --db `"$db`" --dest `"$dest`" --tag daily --prune --drill --status `"$repo\.local\backup_status.json`""
   schtasks /Create /TN "天下大勢每日備份" /SC DAILY /ST 05:00 /TR "`"$py`" $bk" /F
   $rp = "`"$repo\scripts\daily_report.py`" --db `"$db`""
   schtasks /Create /TN "天下大勢每日數字" /SC DAILY /ST 08:00 /TR "`"$py`" $rp" /F
   ```
   路徑有空白時 `/TR` 的引號容易被吃掉：建好之後用 `schtasks /Query /TN "天下大勢每日備份" /V /FO LIST` 看「要執行的工作」那一行完整不完整。
6. **兩個工作都改兩個設定**（工作排程器 → 內容；或 PowerShell）：
   ```powershell
   foreach ($t in "天下大勢每日備份", "天下大勢每日數字") {
     $s = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
     Set-ScheduledTask -TaskName $t -Settings $s
   }
   ```
   錯過時間（關機、睡著）開機後補跑；筆電沒插電也照跑。
7. **試跑**：`schtasks /Run /TN "天下大勢每日備份"`，等一分鐘，再 `schtasks /Run /TN "天下大勢每日數字"`。`.local\backup_status.json` 的 `ok` 要是 `true`，Discord 要收到短報，`.local\daily_report\latest.txt` 有今天的全文。
8. 回報：兩個工作的「上次執行結果」（要是 `0x0`）、備份檔名與大小、短報全文（只有數字，可以直接貼）。

## 出事時

- 「上次執行結果」是 `0x1`：備份失敗或刪舊檔失敗，原因在 `backup_status.json` 的 `error`，或手動跑一次看印什麼。短報也會在第一行寫失敗。
- 還原照 `docs/superpowers/feedback/beta-主機端操作.md`「怎麼還原」：`restore_db.py <備份檔> --db <資料庫>`，旁檔與截圖夾一起回來。**先停伺服器和假人**。
- 備份跟資料在同一顆硬碟：之後要上雲端，把 `$dest` 換成雲端硬碟的同步資料夾，重建「天下大勢每日備份」那個工作就好，腳本不用動。
- 不要了：`schtasks /Delete /TN "天下大勢每日備份" /F`、`"天下大勢每日數字"` 同樣。遊戲不受影響。
