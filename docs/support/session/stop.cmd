@echo off
rem Stop the bridge that start.cmd detached (the whole tree), then forget its PID (support desk batch 218).
cd /d "%~dp0"
chcp 65001 >nul
if not exist bridge.pid (
  rem 待 joy 潤
  echo 沒有 bridge.pid：橋沒有在跑（或已經停了）。
  exit /b 0
)
set /p PID=<bridge.pid
taskkill /PID %PID% /T /F
del bridge.pid
