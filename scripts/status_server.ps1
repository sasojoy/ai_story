<#
查詢 Local Blade RPG Web UI 目前的執行狀態與外網連結。
#>

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LogFile = Join-Path $ProjectRoot "web_ui_run.log"

$listeners = Get-NetTCPConnection -LocalPort 7860 -State Listen -ErrorAction SilentlyContinue

if (-not $listeners) {
    Write-Host "伺服器沒有在跑（port 7860 沒人聽）。" -ForegroundColor Yellow
    exit 0
}

$listenerPid = ($listeners | Select-Object -First 1).OwningProcess
Write-Host "伺服器正在跑，PID: $listenerPid" -ForegroundColor Green
Write-Host "本機連線：http://localhost:7860"

if (Test-Path $LogFile) {
    $match = Select-String -Path $LogFile -Pattern "Running on public URL:\s*(\S+)" -ErrorAction SilentlyContinue
    if ($match) {
        $shareUrl = $match.Matches[0].Groups[1].Value
        Write-Host "外網連結：$shareUrl" -ForegroundColor Green
    } else {
        Write-Host "外網連結尚未出現在 log 裡（可能還在啟動中，或這次沒開 share）。" -ForegroundColor Yellow
    }
}

try {
    $config = Get-Content (Join-Path $ProjectRoot "config\game_config.json") -Raw | ConvertFrom-Json
    Invoke-RestMethod -Uri "$($config.ollama_url)/api/tags" -TimeoutSec 5 | Out-Null
    Write-Host "Ollama：連線正常"
} catch {
    Write-Host "Ollama：連不上（$($config.ollama_url)），互動可能會一直觸發保底劇情。" -ForegroundColor Yellow
}
