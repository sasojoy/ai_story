@echo off
rem Start the support desk: the bridge (detached, no window) and then the Claude session (support desk batch 218).
rem Filled in by scripts/support_session_init.py; TIANXIA_DB stays a fill-in until the planner sets it to the live server's database.
rem Paths must not contain spaces (Start-Process joins the arguments with spaces).
rem Bun was installed by winget; put it on PATH in case this window has an old PATH (same as the liaison).
set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Packages\Oven-sh.Bun_Microsoft.Winget.Source_8wekyb3d8bbwe\bun-windows-x64;%PATH%"
cd /d "%~dp0"
chcp 65001 >nul
rem A second Discord bot on this machine: its own token and access.json.
set "DISCORD_STATE_DIR=%USERPROFILE%\.claude\channels\discord-support"
rem The bridge reads the same database as server.py (the side file sits next to it).
set "TIANXIA_DB=<填：線上伺服器的資料庫>"
if "%TIANXIA_DB:~0,1%"=="<" (
  rem 待 joy 潤
  echo start.cmd 的 TIANXIA_DB 還沒填：照 docs/superpowers/discord/客服官-設定.md 填好再開。
  exit /b 2
)
powershell -NoProfile -Command "$p = Start-Process -PassThru -WindowStyle Hidden -FilePath '{{PYTHON}}' -ArgumentList '-u','{{REPO}}\scripts\support_bridge.py','--config','{{CONFIG}}','--log','%~dp0bridge.log' -RedirectStandardOutput '%~dp0bridge-out.log' -RedirectStandardError '%~dp0bridge-err.log'; Set-Content -Path '%~dp0bridge.pid' -Value $p.Id"
claude --channels plugin:discord@claude-plugins-official
