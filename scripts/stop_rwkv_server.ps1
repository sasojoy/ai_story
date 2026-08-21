<#
停止 RWKV backend-python API server（見 start_rwkv_server.ps1）。
比照 stop_server.ps1 的做法：直接找「誰在聽 port 8000」關閉，不依賴 PID 檔。
#>

$ErrorActionPreference = "Continue"

$killed = @()
$listeners = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
foreach ($conn in $listeners) {
    $listenerPid = $conn.OwningProcess
    if ($listenerPid -and ($killed -notcontains $listenerPid)) {
        Stop-Process -Id $listenerPid -Force -ErrorAction SilentlyContinue
        $killed += $listenerPid
    }
}

if ($killed.Count -gt 0) {
    Write-Host "已停止程序：$($killed -join ', ')" -ForegroundColor Green
} else {
    Write-Host "沒有找到正在跑的 RWKV backend（port 8000 沒人聽）。" -ForegroundColor Yellow
}

