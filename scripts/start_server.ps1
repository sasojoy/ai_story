<#
啟動 Local Blade RPG Web UI（Gradio，share=True 對外公開）。
用 Start-Process 完全分離啟動，不掛在任何終端機或呼叫者的程序樹上，
所以呼叫者（含 Claude Code 的背景任務追蹤）結束或被回收都不會連帶關閉伺服器。
#>

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$PidFile = Join-Path $ProjectRoot "web_ui.pid"
$LogFile = Join-Path $ProjectRoot "web_ui_run.log"
$ErrLogFile = Join-Path $ProjectRoot "web_ui_run_err.log"
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

# 1. 若已經有伺服器在跑（port 7860 有人聽），不要重複啟動
$existing = Get-NetTCPConnection -LocalPort 7860 -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "伺服器已經在跑了（port 7860 由 PID $($existing.OwningProcess | Select-Object -First 1) 佔用）。" -ForegroundColor Yellow
    Write-Host "如果要重啟，請先執行 stop_server.ps1，或直接執行 restart_server.ps1。"
    exit 0
}

# 2. 檢查 Ollama 是否活著、模型是否已下載（只警告，不阻擋啟動）
$config = Get-Content (Join-Path $ProjectRoot "config\game_config.json") -Raw | ConvertFrom-Json
try {
    $tags = Invoke-RestMethod -Uri "$($config.ollama_url)/api/tags" -TimeoutSec 5
    $modelNames = $tags.models | ForEach-Object { $_.name }
    if ($modelNames -notcontains $config.model_name) {
        Write-Host "警告：Ollama 有在跑，但找不到設定的模型 '$($config.model_name)'。目前已安裝：$($modelNames -join ', ')" -ForegroundColor Yellow
    }
} catch {
    Write-Host "警告：連不上 Ollama ($($config.ollama_url))，遊戲啟動後互動可能會一直觸發保底劇情。請確認 Ollama 服務有在跑。" -ForegroundColor Yellow
}

# 3. 分離啟動 web_ui.py
$env:PYTHONUNBUFFERED = "1"
$proc = Start-Process -FilePath $Python -ArgumentList "-u web_ui.py" `
    -WindowStyle Hidden `
    -RedirectStandardOutput $LogFile `
    -RedirectStandardError $ErrLogFile `
    -PassThru
$proc.Id | Out-File -FilePath $PidFile -Encoding ascii -NoNewline
Write-Host "已啟動，啟動程序 PID: $($proc.Id)"

# 4. 等待 log 出現公開連結（最多等 60 秒）
$shareUrl = $null
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 2
    if (Test-Path $LogFile) {
        $match = Select-String -Path $LogFile -Pattern "Running on public URL:\s*(\S+)" -ErrorAction SilentlyContinue
        if ($match) {
            $shareUrl = $match.Matches[0].Groups[1].Value
            break
        }
    }
}

if ($shareUrl) {
    Write-Host ""
    Write-Host "遊戲已可外網連線：$shareUrl" -ForegroundColor Green
    Write-Host "本機連線：http://localhost:7860"
} else {
    Write-Host ""
    Write-Host "等超過 60 秒還沒看到公開連結，請檢查 $LogFile 和 $ErrLogFile 確認是否啟動失敗。" -ForegroundColor Red
}
