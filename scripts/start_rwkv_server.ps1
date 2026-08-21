<#
啟動 RWKV Runner 的 backend-python（OpenAI 相容 API server），並載入結局劇情生成用的
中文情色小說續寫模型（a686d380/rwkv-5-h-world，3B 版本）。

跟 start_server.ps1 一樣用 Start-Process 完全分離啟動，不掛在呼叫者的程序樹上。

前置需求（見 CLAUDE.md「機器升級後的模型/可靠度修復」一節）：
- tools/rwkv-runner-src/backend-python/.venv 已建立並裝好 requirements.txt
  （torch 要另外用支援目前 GPU 架構的 cu12x wheel 裝，不要用 requirements.txt 裡那行
  沒指定 index 的 torch，會裝到不支援新顯卡架構的版本）
- tools/rwkv-models/rwkv-5-h-world-3B.pth 已下載
  (https://huggingface.co/a686d380/rwkv-5-h-world)

這個腳本啟動的是「純續寫」模型的 API，不是 chat/instruct 模型，src/ending_writer.py 的
backend="rwkv" 路線才會用到；跟 Ollama（qwen 系列，chat/instruct 模型）完全是兩個獨立
服務，互不影響，可以同時跑。
#>

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $ProjectRoot "tools\rwkv-runner-src\backend-python"
$Python = Join-Path $BackendDir ".venv\Scripts\python.exe"
$ModelPath = Join-Path $ProjectRoot "tools\rwkv-models\rwkv-5-h-world-3B.pth"
$LogFile = Join-Path $BackendDir "server.log"
$RwkvUrl = "http://127.0.0.1:8000"

if (-not (Test-Path $Python)) {
    Write-Host "找不到 $Python，請先依 CLAUDE.md 的說明建立 venv 並安裝依賴。" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $ModelPath)) {
    Write-Host "找不到模型檔 $ModelPath，請先從 HuggingFace 下載。" -ForegroundColor Red
    exit 1
}

# 1. 若已經有伺服器在跑（port 8000 有人聽），不要重複啟動
$existing = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "RWKV backend 已經在跑了（port 8000 由 PID $($existing.OwningProcess | Select-Object -First 1) 佔用）。" -ForegroundColor Yellow
    exit 0
}

# 2. 分離啟動 backend-python/main.py
Push-Location $BackendDir
try {
    $proc = Start-Process -FilePath $Python -ArgumentList "main.py" `
        -WindowStyle Hidden `
        -RedirectStandardOutput $LogFile `
        -RedirectStandardError "$LogFile.err" `
        -WorkingDirectory $BackendDir `
        -PassThru
} finally {
    Pop-Location
}
Write-Host "已啟動 backend-python，PID: $($proc.Id)"

# 3. 等待 API server 起來（最多等 30 秒）
$up = $false
for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep -Seconds 2
    try {
        Invoke-RestMethod -Uri "$RwkvUrl/docs" -TimeoutSec 3 -Method Get | Out-Null
        $up = $true
        break
    } catch {}
}
if (-not $up) {
    Write-Host "等超過 30 秒 API server 還沒起來，請檢查 $LogFile 確認是否啟動失敗。" -ForegroundColor Red
    exit 1
}

# 4. 呼叫 /switch-model 載入模型（cuda fp16i8：GPU + int8 量化，實測在 12GB VRAM 上跑
#    3B 模型速度快、記憶體餘裕也夠）
Write-Host "載入模型中（第一次載入可能要一分鐘左右）..."
$body = @{
    model = $ModelPath
    strategy = "cuda fp16i8"
    deploy = $false
} | ConvertTo-Json

try {
    $result = Invoke-RestMethod -Uri "$RwkvUrl/switch-model" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 120
    Write-Host "模型載入成功，RWKV API 已就緒：$RwkvUrl" -ForegroundColor Green
} catch {
    Write-Host "模型載入失敗：$_" -ForegroundColor Red
    exit 1
}

