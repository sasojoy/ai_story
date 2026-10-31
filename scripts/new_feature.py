"""生一個功能包的骨架（開發規範手冊 3.4 第 2 條）：python scripts/new_feature.py <包名> --title <中文名> --guide <導覽區塊>

做的事：
- tianxia/features/<包名>/__init__.py：登記用的 Feature（name、prefix、enabled 先回 False，其餘掛鉤都是預設的空的）
- tianxia/features/<包名>/README.md：這一包做什麼、導覽在哪一節、設計稿（三行，等著填）
- tianxia/features/<包名>/tests/test_<包名>_smoke.py：一條煙霧測試（登記了、關著一個選項都不給）
- tianxia/features/<包名>/tests/<包名>_stage.py：契約測試擺局面用的（tests/core/test_contract_features.py；先什麼都不擺）
- docs/guide/<導覽區塊>.md 最後加一節的標題
- tianxia/core/registry.py 的 FEATURES 登記（照標記加 import 與清單各一行，排在最後）

包名：小寫英文字母開頭、只有小寫英數與底線；不能跟已經有的包、tianxia/ 底下的模組、任何測試檔撞名。
--root 給別的資料夾就在那裡生（測試用）。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = re.compile(r"[a-z][a-z0-9_]*")
IMPORT_MARK = "# ── import（new_feature.py 接在這一行前面）──"
LIST_MARK = "    # ── 清單（new_feature.py 接在這一行前面）──"


def _camel(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_")) + "Feature"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.replace("\n", "\r\n"), encoding="utf-8", newline="")  # 工作樹是 CRLF（core.autocrlf）


def _edit(path: Path, mark: str, line: str) -> None:
    raw = path.read_bytes().decode("utf-8")
    crlf = "\r\n" in raw
    text = raw.replace("\r\n", "\n")
    if text.count(mark) != 1:
        raise SystemExit(f"{path} 裡找不到（或不只一個）標記：{mark}")
    text = text.replace(mark, f"{line}\n{mark}")
    path.write_bytes((text.replace("\n", "\r\n") if crlf else text).encode("utf-8"))


def problem(root: Path, name: str, guide: str) -> str | None:
    if not NAME.fullmatch(name):
        return f"包名「{name}」要是小寫英文字母開頭、只有小寫英數與底線"
    if (root / "tianxia" / "features" / name).exists():
        return f"已經有 tianxia/features/{name}/"
    if (root / "tianxia" / f"{name}.py").exists() or (root / "tianxia" / name).exists():
        return f"tianxia/ 底下已經有叫 {name} 的模組（換個包名，免得 import 的時候看錯）"
    taken = {p.name for p in root.rglob(f"test_{name}_smoke.py")} | {p.name for p in root.rglob(f"{name}_stage.py")}
    if taken:
        return f"測試檔名撞了：{sorted(taken)}（檔名全 repo 不能重複）"
    if not (root / "docs" / "guide" / f"{guide}.md").exists():
        return f"沒有 docs/guide/{guide}.md（--guide 給 CLAUDE.md 區塊表上那一塊的名字）"
    return None


def make(root: Path, name: str, title: str, guide: str) -> list[Path]:
    """生骨架、登記；回生了哪些檔。"""
    why = problem(root, name, guide)
    if why:
        raise SystemExit(why)
    pkg = root / "tianxia" / "features" / name
    cls = _camel(name)
    made = {
        pkg / "__init__.py": f'''"""{title}（功能包；開發規範手冊 3.2）。這一包做什麼、導覽在哪一節、設計稿是哪一份：README.md。

掛鉤照 tianxia/core/features.py 的表；用得到哪一個才寫哪一個。功能包只 import 核心（tianxia/core/ 與手冊 3.1 的核心模組）。
新寫給玩家看的字標「待 joy 潤」。
"""
from __future__ import annotations

from tianxia.core.features import Feature


class {cls}(Feature):
    name = "{name}"
    prefix = "{name}"  # 選項 id 的前綴：{name}:…（核心只把這個前綴的 id 交給這一包）
    player_fields: tuple[str, ...] = ()  # 認領的 PlayerState 欄位（新欄位放自己的子模型，手冊 3.5）
    carried: tuple[str, ...] = ()  # 上面那些裡換季照帶走的

    def enabled(self, ctx) -> bool:
        return False  # 接上 Config.{name}.enabled（Config 加欄位先過 PM：手冊 3.5）


FEATURE = {cls}()
''',
        pkg / "README.md": f"""# {title}（`tianxia/features/{name}/`）

- 做什麼：（一句話）
- 導覽：`docs/guide/{guide}.md` 的「{title}」那一節
- 設計稿：（`docs/superpowers/specs/<日期>-<名字>-design.md` 第 N 版）
""",
        pkg / "tests" / f"test_{name}_smoke.py": f'''"""{title}的煙霧測試（開發規範手冊 4.1 第三級：一包一條，走一次最常見的路）。骨架生的這一條只驗登記與關著不出聲；
功能做出來之後換成真的那一條（真實內容 real_content("week7")）；標記 @pytest.mark.smoke 留著（每一包至少一條，test_test_for 守）。"""
import pytest

from tianxia.core.registry import FEATURES


@pytest.mark.smoke
def test_{name}_is_registered_and_quiet_while_closed(game):
    feature = next(f for f in FEATURES if f.name == "{name}")
    assert feature.enabled(game) is False
    assert not any(o.id.startswith("{name}:") for o in game.options())
''',
        pkg / "tests" / f"{name}_stage.py": f'''"""契約測試（tests/core/test_contract_features.py）把{title}擺進「有選項」的局面：每擺好一種 yield 一個名字。"""


def stages(game):
    yield "平常"
''',
    }
    for path, text in made.items():
        _write(path, text)
    guide_path = root / "docs" / "guide" / f"{guide}.md"
    raw = guide_path.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    tail = "" if raw.endswith(("\n", "\r\n")) else nl
    section = f"{tail}{nl}## {title}（功能包 `tianxia/features/{name}/`）{nl}{nl}- （規則與模組照這一包寫；新規則寫在這一節）{nl}"
    guide_path.write_bytes((raw + section).encode("utf-8"))
    registry = root / "tianxia" / "core" / "registry.py"
    _edit(registry, IMPORT_MARK, f"from ..features import {name}  # {title}")
    _edit(registry, LIST_MARK, f"    {name}.FEATURE,")
    return [*made, guide_path, registry]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生一個功能包的骨架並登記進 FEATURES")
    parser.add_argument("name", help="包名（小寫英數與底線，例：tavern）")
    parser.add_argument("--title", required=True, help="中文名（例：酒肆）")
    parser.add_argument("--guide", required=True, help="導覽區塊（docs/guide/ 底下的檔名，不寫 .md；例：大勢人物與賽季）")
    parser.add_argument("--root", default=str(ROOT), help="在哪一份 repo 生（預設這一份）")
    args = parser.parse_args(argv)
    root = Path(args.root)
    for path in make(root, args.name, args.title, args.guide):
        print(path.relative_to(root).as_posix())
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
