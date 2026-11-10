@echo off
rem The support desk's only hand: run scripts/support_cli.py with the paths locked (support desk batch 218).
rem Filled in by scripts/support_session_init.py. Keep this part ASCII: cmd reads the file in the old code page until chcp runs.
setlocal DisableDelayedExpansion
chcp 65001 >nul
set "TIANXIA_SUPPORT_LOCKED=1"
set "TIANXIA_SUPPORT_CONFIG={{CONFIG}}"
set "TIANXIA_SUPPORT_URL={{URL}}"
set "TIANXIA_SUPPORT_INBOX=%~dp0inbox"
set RAW=%*
setlocal EnableDelayedExpansion
rem With delayed expansion on, this second copy loses every exclamation mark; if the two differ the arguments had one.
set EAT=%*
if not "!RAW!"=="!EAT!" goto refuse
if not defined RAW goto run
if not "!RAW!"=="!RAW:&=!" goto refuse
if not "!RAW!"=="!RAW:|=!" goto refuse
if not "!RAW!"=="!RAW:<=!" goto refuse
if not "!RAW!"=="!RAW:>=!" goto refuse
if not "!RAW!"=="!RAW:^=!" goto refuse
:run
endlocal
"{{PYTHON}}" "{{REPO}}\scripts\support_cli.py" %*
exit /b %errorlevel%
:refuse
rem 待 joy 潤
echo cli.cmd 的參數不收 ^& ^| ^< ^> ^^ 與驚嘆號（回覆與註記的字從 stdin 進）。
exit /b 2
