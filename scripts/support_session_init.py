"""客服官 session 的工作夾（客服自動受理第 218 批；設計 6.3，企劃者 2026-11-10「照計畫繼續」）：
把 docs/support/session/ 的五個範本抄進工作夾（settings.local.json 進 .claude\\），建 inbox\\、knowledge\\，填好佔位。

    python scripts/support_session_init.py C:\\Ray\\tianxia-support [--url U] [--config C] [--python P]

- **冪等**：目的檔已經在就不蓋（企劃者填過的 <填>、改過的規矩都留著），印「留著」；要換新範本先自己刪那個檔。
- 佔位：{{DIR}} 工作夾、{{READ}} 工作夾的 POSIX 寫法（許可規則用）、{{REPO}} 這支腳本所在的 repo 根、
  {{PYTHON}}（預設 <repo>\\.venv\\Scripts\\python.exe，不在就用跑這支的 python：工作樹沒有 venv）、
  {{CONFIG}}（預設 <repo>\\.local\\support.json）、{{URL}}（預設 http://127.0.0.1:7861）。
- .cmd 一律寫 CRLF、cli.sh 一律寫 LF（git 裡都存 LF；工作樹抽出來是 CRLF，這裡照副檔名換）；其餘照範本、寫 UTF-8。
- 客服官 session 的 Bash 放行的是 cli.sh（直接叫 python）；cli.cmd 留給人在 cmd、PowerShell 用。Git Bash 叫 .cmd 時參數不加引號
  交給 cmd，"R&D" 的 & 會被 cmd 當成下一個指令（第 218 批實跑過），所以 cli.cmd 不進許可白名單。
- 不 import tianxia（主機上的工具，遊戲不知道它）。退版：刪掉這支就沒了，工作夾裡抄過去的檔留著。"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path, PureWindowsPath

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "docs" / "support" / "session"
DEFAULT_URL = "http://127.0.0.1:7861"
# (範本, 工作夾裡的位置)
FILES = (
    ("CLAUDE.md", "CLAUDE.md"),
    ("settings.local.json", ".claude/settings.local.json"),
    ("cli.sh", "cli.sh"),
    ("cli.cmd", "cli.cmd"),
    ("start.cmd", "start.cmd"),
    ("stop.cmd", "stop.cmd"),
)
WROTE = "寫了 {path}"  # 待 joy 潤（主機端）
KEPT = "留著 {path}（已經在，不蓋）"  # 待 joy 潤（主機端）
INSIDE = "金鑰檔不能放在客服官的工作夾裡（客服官讀得到）；--config 指到工作夾外面。什麼都沒寫。"  # 待 joy 潤（主機端）
SPACES ="注意：工作夾、repo、python 或金鑰檔的路徑有空白或單引號，start.cmd 與 cli.sh 會出錯；換一個沒有空白的位置。"  # 待 joy 潤（主機端）


def posix_form(path: Path) -> str:
    """許可規則的絕對路徑寫法：C:\\Ray\\x → //c/Ray/x（Claude Code 在 Windows 上把路徑換成 POSIX 再比）。"""
    win = PureWindowsPath(str(path))
    drive = win.drive.rstrip(":").lower()
    rest = "/".join(win.parts[1:])
    return f"//{drive}/{rest}" if drive else "//" + rest


def default_python() -> Path:
    venv = ROOT / ".venv" / "Scripts" / "python.exe"
    return venv if venv.is_file() else Path(sys.executable)


def fill(text: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="抄客服官 session 的範本進工作夾（已經在的不蓋）")
    p.add_argument("folder")
    p.add_argument("--url", default=DEFAULT_URL)
    p.add_argument("--config", default=str(ROOT / ".local" / "support.json"))
    p.add_argument("--python", default=None)
    args = p.parse_args(argv)
    desk = Path(args.folder).resolve()
    values = {
        "DIR": str(desk),
        "READ": posix_form(desk),
        "REPO": str(ROOT),
        "PYTHON": str(args.python or default_python()),
        "CONFIG": str(args.config),
        "URL": args.url,
    }
    if Path(args.config).resolve().is_relative_to(desk):
        print(INSIDE)  # 工作夾裡的唯讀指令 Claude Code 本來就放行（第 218 批實跑），金鑰檔放進去客服官就讀得到 token
        return 2
    if any(" " in values[key] or "'" in values[key] for key in ("DIR", "REPO", "PYTHON", "CONFIG")):
        print(SPACES)  # start.cmd 的 Start-Process 與 cli.sh 的單引號都經不起；照樣寫，讓人自己決定換不換位置
    for sub in ("", ".claude", "inbox", "knowledge"):
        (desk / sub).mkdir(parents=True, exist_ok=True)
    for source, place in FILES:
        target = desk / place
        if target.exists():
            print(KEPT.format(path=target))
            continue
        text = fill((TEMPLATES / source).read_text(encoding="utf-8").replace("\r\n", "\n"), values)
        if target.suffix == ".cmd":
            text = text.replace("\n", "\r\n")
        target.write_bytes(text.encode("utf-8"))
        print(WROTE.format(path=target))
    return 0


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.exit(main())
