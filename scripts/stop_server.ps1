<#
停止 Local Blade RPG Web UI。
不能只信任 web_ui.pid 裡記的那個 PID：Start-Process 啟動 venv 的 python.exe
時，真正佔用 port 7860 的程序 PID 觀察到會跟 Start-Process 回傳的 PID 不同
（python.exe 啟動器 exec 出實際直譯器子程序），所以改成優先找「誰在聽 7860」
直接關閉，PID 檔只是輔助、兩邊都殺一次確保乾淨。
#>

$ErrorActionPreference = "Continue"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PidFile = Join-Path $ProjectRoot "web_ui.pid"

$killed = @()

$listeners = Get-NetTCPConnection -LocalPort 7860 -State Listen -ErrorAction SilentlyContinue
foreach ($conn in $listeners) {
    $listenerPid = $conn.OwningProcess
    if ($listenerPid -and ($killed -notcontains $listenerPid)) {
        Stop-Process -Id $listenerPid -Force -ErrorAction SilentlyContinue
        $killed += $listenerPid
    }
}

if (Test-Path $PidFile) {
    $savedPid = Get-Content $PidFile -Raw
    if ($savedPid -match '^\d+$') {
        $savedPid = [int]$savedPid
        if ($killed -notcontains $savedPid) {
            $p = Get-Process -Id $savedPid -ErrorAction SilentlyContinue
            if ($p) {
                Stop-Process -Id $savedPid -Force -ErrorAction SilentlyContinue
                $killed += $savedPid
            }
        }
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

if ($killed.Count -gt 0) {
    Write-Host "已停止程序：$($killed -join ', ')" -ForegroundColor Green
} else {
    Write-Host "沒有找到正在跑的伺服器（port 7860 沒人聽，也沒有 PID 檔）。" -ForegroundColor Yellow
}
