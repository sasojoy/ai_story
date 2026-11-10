"""客服官 session 的工作夾（客服自動受理第 218 批；設計 6.3，企劃者 2026-11-10「照計畫繼續」）：
把 docs/support/session/ 的五個範本抄進工作夾（settings.local.json 進 .claude\\），建 inbox\\、knowledge\\，填好佔位。

    python scripts/support_session_init.py C:\\Ray\\tianxia-support [--url U] [--config C] [--python P]

- **冪等**：目的檔已經在就不蓋（企劃者填過的 <填>、改過的規矩都留著），印「留著」；要換新範本先自己刪那個檔。
- 佔位：{{DIR}} 工作夾、{{READ}} 工作夾的 POSIX 寫法（許可規則用）、{{REPO}} 這支腳本所在的 repo 根、
  {{PYTHON}}（預設 <repo>\\.venv\\Scripts\\python.exe，不在就用跑這支的 python：工作樹沒有 venv）、
  {{CONFIG}}（預設 <repo>\\.local\\support.json）、{{URL}}（預設 http://127.0.0.1:7861）。
- .cmd 一律寫 CRLF（git 裡存 LF）；其餘照範本、寫 UTF-8。
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
    ("cli.cmd", "cli.cmd"),
    ("start.cmd", "start.cmd"),
    ("stop.cmd", "stop.cmd"),
)
WROTE = "寫了 {path}"  # 待 joy 潤（主機端）
KEPT = "留著 {path}（已經在，不蓋）"  # 待 joy 潤（主機端）


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
