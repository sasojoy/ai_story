<#
每日整套（開發規範手冊 4.4，docs/superpowers/specs/2026-10-30-開發模式-design.md）：排程每天叫這一支。
- 行程優先權 BelowNormal（子行程 python 與 pytest 的 -n 4 工作行程都繼承），不搶線上伺服器的 16 核。
- 真正做事的是同一個資料夾的 nightly.py：明確 fetch origin/develop、把 <主要 clone>\.local\nightly\checkout 重設成
  它的乾淨一份、整套含 slow（-n 4）、寫 .local\nightly\<日期>.log 與 latest.txt（新紅、舊紅、轉綠、develop 新進的提交）。
- 不推任何東西；資料庫用系統暫存資料夾的暫存檔，不碰 saves\ 與線上。
- 怎麼註冊排程（企劃者定時間後）見 docs/guide/量表與教訓.md「每日整套」。
這個檔存成 UTF-8 含 BOM：Windows PowerShell 5.1 沒有 BOM 會照 ANSI 讀，中文全變亂碼。
#>
param(
    [string]$Branch = "develop",
    [int]$Workers = 4
)
$ErrorActionPreference = "Stop"
(Get-Process -Id $PID).PriorityClass = [System.Diagnostics.ProcessPriorityClass]::BelowNormal

# 主要的 clone：scripts\ 的上一層有 .git 資料夾就是它；是工作樹（.git 是檔案，例如 .local\nightly\checkout）就照 gitdir 找回去
$top = Split-Path $PSScriptRoot -Parent
$dotgit = Join-Path $top ".git"
if (Test-Path $dotgit -PathType Container) {
    $repo = $top
} elseif (Test-Path $dotgit -PathType Leaf) {
    $gitdir = ((Get-Content $dotgit -Encoding UTF8 -TotalCount 1) -replace '^gitdir:\s*', '').Trim()
    # gitdir 是 <主要 clone>/.git/worktrees/<名字>
    $repo = Split-Path (Split-Path (Split-Path $gitdir -Parent) -Parent) -Parent
} else {
    throw "找不到 .git：$top"
}
$python = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "找不到 venv 的 python：$python" }
$env:PYTHONIOENCODING = "utf-8"
& $python -u (Join-Path $PSScriptRoot "nightly.py") --repo $repo --branch $Branch --workers $Workers
exit $LASTEXITCODE
