"""客服官的三樣知識（客服自動受理第 218 批；設計 6.3 第 4 條、6.4，企劃者 2026-11-10「照計畫繼續」）：
匯出到工作夾的 knowledge\\：

- `patch_notes.json`：`content/patch_notes.json` 的複本（改版資訊，玩家本來就看得到）；
- `howto.md`：遊戲裡設定抽屜「玩法說明」的公開版（`Game.howto_text()`；開一個新世界、建一個角色拿它的字）；
- `FAQ.md`：`docs/support/FAQ.md` 的複本。

    python scripts/support_knowledge.py C:\\Ray\\tianxia-support [--profile season21] [--content <內容資料夾>]

- 開世界之前先把 `TIANXIA_DB` 設到自己的暫存檔（`tempfile.mkdtemp`，用完刪、環境變數還原）：不碰任何真的資料庫；
  `tianxia` 都在函式裡 import（設好之後）。模型一律不叫（`OllamaClient.from_config` 回 None）。
- 三個檔寫之前都過 `tests/bots/test_server_bots.py` 的 `leaks()` 同一張字表（`FORBIDDEN`，測試鎖兩邊一樣）：
  有一個命中就印出來、一個檔都不寫、結束碼 1。
- 新世界停在「籌備中」：`howto.md` 沒有「這一季在打什麼」的收季規則那一句（要開季才有）。
- 改版、改 FAQ、改玩法說明之後重跑。退版：刪掉這支就沒了，工作夾裡匯出的檔留著。"""
from __future__ import annotations

import argparse
import io
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATCH_NOTES = ROOT / "content" / "patch_notes.json"
FAQ = ROOT / "docs" / "support" / "FAQ.md"
NAME = "說明"  # 拿玩法說明用的角色名號（只活在暫存的世界裡）

# 同 tests/bots/test_server_bots.py 的 FORBIDDEN（「bot」不分大小寫，只放行 bottom 與 both）。
BOT_WORD = re.compile(r"bot(?!tom|h\b)", re.IGNORECASE)
FORBIDDEN = (re.compile("假人"), re.compile("機器人"), BOT_WORD)

LEAK = "{name} 第 {line} 行有不能給玩家看的字：{hit}"  # 待 joy 潤（主機端）
WROTE = "寫了 {path}（{size} 位元組）"  # 待 joy 潤（主機端）
NOT_WRITTEN = "一個檔都沒寫。"  # 待 joy 潤（主機端）


def leaks(text: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), 1):
        for pattern in FORBIDDEN:
            for hit in pattern.finditer(line):
                found.append((number, line[max(0, hit.start() - 8) : hit.end() + 8]))
    return found


def howto_markdown(content_root: Path, profile: str | None) -> str:
    """開一個暫存的世界、建一個角色，拿設定抽屜「玩法說明」的字。TIANXIA_DB 在 import tianxia 之前就指到暫存檔。"""
    tmp = Path(tempfile.mkdtemp(prefix="support-knowledge-"))
    old = os.environ.get("TIANXIA_DB")
    os.environ["TIANXIA_DB"] = str(tmp / "knowledge.db")
    try:
        from tianxia import ollama_client
        from tianxia.content import load_content, serving_profile
        from tianxia.engine import Game
        from tianxia.sqlite_world import open_world

        real = ollama_client.OllamaClient.__dict__["from_config"]
        ollama_client.OllamaClient.from_config = classmethod(lambda cls, cfg: None)
        world = None
        try:
            if profile is None and content_root.resolve() == (ROOT / "content").resolve():
                profile = serving_profile()  # 同伺服器；別的內容資料夾（測試內容）不套設定覆寫
            content = load_content(content_root, profile=profile)
            world = open_world(tmp / "knowledge.db")
            game = Game.new(content, NAME, world=world)
            return game.howto_text()
        finally:
            ollama_client.OllamaClient.from_config = real
            close = getattr(getattr(world, "db", None), "close", None)
            if callable(close):
                close()
    finally:
        if old is None:
            os.environ.pop("TIANXIA_DB", None)
        else:
            os.environ["TIANXIA_DB"] = old
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="匯出客服官的三樣知識到工作夾的 knowledge\\")
    p.add_argument("folder")
    p.add_argument("--profile", default=None, help="設定覆寫（預設照 TIANXIA_PROFILE，沒帶是 season21）")
    p.add_argument("--content", default=str(ROOT / "content"), help="內容資料夾（測試給 tests/fixtures/content）")
    args = p.parse_args(argv)
    howto = howto_markdown(Path(args.content), args.profile).encode("utf-8")
    files = {"patch_notes.json": PATCH_NOTES.read_bytes(), "howto.md": howto, "FAQ.md": FAQ.read_bytes()}
    texts = {name: data.decode("utf-8") for name, data in files.items()}
    bad = [(name, line, hit) for name, text in texts.items() for line, hit in leaks(text)]
    if bad:
        for name, line, hit in bad:
            print(LEAK.format(name=name, line=line, hit=hit))
        print(NOT_WRITTEN)
        return 1
    out = Path(args.folder).resolve() / "knowledge"
    out.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        target = out / name
        target.write_bytes(data)
        print(WROTE.format(path=target, size=len(data)))
    return 0


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.exit(main())
