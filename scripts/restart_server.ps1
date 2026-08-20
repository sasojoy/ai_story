<#
重啟 Local Blade RPG Web UI（停止舊程序 → 啟動新程序）。
在改完程式碼、要讓修改生效時用這個。
#>

$ScriptDir = $PSScriptRoot

& (Join-Path $ScriptDir "stop_server.ps1")
Start-Sleep -Seconds 2
& (Join-Path $ScriptDir "start_server.ps1")
