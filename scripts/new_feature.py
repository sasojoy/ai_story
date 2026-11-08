"""生一個功能包的骨架（開發規範手冊 3.4 第 2 條）：python scripts/new_feature.py <包名> --title <中文名> --guide <導覽區塊>

做的事：
- tianxia/features/<包名>/__init__.py：登記用的 Feature（name、prefix、enabled 讀 Config.<包名>.enabled〔預設 False〕，其餘掛鉤都是預設的空的）
- tianxia/features/<包名>/README.md：這一包做什麼、導覽在哪一節、設計稿（三行，等著填）
- tianxia/features/<包名>/tests/test_<包名>_smoke.py：一條煙霧測試（登記了、關著一個選項都不給）
- tianxia/features/<包名>/tests/<包名>_stage.py：契約測試擺局面用的（tests/core/test_contract_features.py；先什麼都不擺）
- tianxia/core/tuning/<包名>.py：這一包的 Config 子模型（enabled 先是 False；這一包的數字加在這裡，手冊第十五節「波次 B、C」第 15 條）
- tianxia/models.py：照標記接兩行（import 與 Config.<包名> 一格）
- docs/guide/<導覽區塊>.md 最後加一節的標題
- tianxia/core/registry.py 的 FEATURES 登記（照標記加 import 與清單各一行，排在最後）
- tests/core/test_test_for.py 的 STAGE_PACKAGES 接一行（有 <包名>_stage.py 的包都要登記；--root 的資料夾沒有這個檔就不做）

內容檔與畫面檔不生，用到才加（開發規範手冊第十五節 G8、G9）：
- 內容檔放 tianxia/features/<包名>/content/、寫進 Feature.content；測試內容放同一包的 tests/content/（同一個相對路徑）。不放 repo 的 content/。
- 畫面寫 web/<包名>.js、web/<包名>.css、寫進 Feature.web。js 的 script 標籤由伺服器照它生成，不要手改 index.html 的 script；
  新鈕在 web/<包名>.js 寫 <包名>Click 加 registerClicks(<包名>Click, ["動作", …])（表單、change 走 registerForms、registerChanges），不加進 app.js；
  css 的 link 手寫在 index.html，接在最後一行 link 之後，不要排到 map.css、shop.css 前面（同權重蓋不過店面與輿圖）；
  js 手加進 tests/kit/webharness.APP_FILES（跟頁面同一個先後）；tests/core/test_contract_features.py 守。

包名：小寫英文字母開頭、只有小寫英數與底線；不能跟已經有的包、tianxia/ 底下的模組、任何測試檔、tuning 檔、Config 已有的格撞名。
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
TUNING_IMPORT_MARK = "# ── tuning import（new_feature.py 接在這一行前面）──"
TUNING_FIELD_MARK = "    # ── tuning 欄位（new_feature.py 接在這一行前面：新包的子模型在 tianxia/core/tuning/<包>.py）──"


def _camel(name: str, suffix: str = "Feature") -> str:
    return "".join(part.capitalize() for part in name.split("_")) + suffix


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


def _add_stage(root: Path, name: str, title: str) -> Path | None:
    """生出來的 <包>_stage.py 要登記，不然 test_the_stage_packages_are_every_package_with_a_stage_file 紅。
    接在最後一行 STAGE_PACKAGES 後面、不改前面的行（並行的線各寫各的一行）。"""
    path = root / "tests" / "core" / "test_test_for.py"
    if not path.exists():
        return None
    raw = path.read_bytes().decode("utf-8")
    crlf = "\r\n" in raw
    lines = raw.replace("\r\n", "\n").split("\n")
    spots = [i for i, line in enumerate(lines) if line.startswith("STAGE_PACKAGES")]
    if not spots:
        raise SystemExit(f"{path} 裡找不到 STAGE_PACKAGES")
    lines.insert(spots[-1] + 1, f'STAGE_PACKAGES += ["{name}"]  # {title}（scripts/new_feature.py 生的 {name}_stage.py）')
    text = "\n".join(lines)
    path.write_bytes((text.replace("\n", "\r\n") if crlf else text).encode("utf-8"))
    return path


def _models_problem(root: Path, name: str) -> str | None:
    """models.py 接得上去嗎：兩個標記都在、class <Camel>Tuning 與 Config 的 <包>: 那一格都還沒有（生到一半才發現就留下半套了）。"""
    path = root / "tianxia" / "models.py"
    text = path.read_bytes().decode("utf-8").replace("\r\n", "\n") if path.exists() else ""
    for mark in (TUNING_IMPORT_MARK, TUNING_FIELD_MARK):
        if text.count(mark) != 1:
            return f"tianxia/models.py 裡找不到（或不只一個）標記：{mark}"
    if f"class {_camel(name, 'Tuning')}" in text:
        return f"tianxia/models.py 已經有 class {_camel(name, 'Tuning')}"
    body = text[text.index("\nclass Config("):text.index(TUNING_FIELD_MARK)]
    if f"\n    {name}: " in body:
        return f"Config 已經有 {name} 這一格（換個包名）"
    return None


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
    if (root / "tianxia" / "core" / "tuning" / f"{name}.py").exists():
        return f"已經有 tianxia/core/tuning/{name}.py"
    return _models_problem(root, name)


def make(root: Path, name: str, title: str, guide: str) -> list[Path]:
    """生骨架、登記；回生了哪些檔。"""
    why = problem(root, name, guide)
    if why:
        raise SystemExit(why)
    pkg = root / "tianxia" / "features" / name
    cls = _camel(name)
    tuning = _camel(name, "Tuning")
    made = {
        pkg / "__init__.py": f'''"""{title}（功能包；開發規範手冊 3.2）。這一包做什麼、導覽在哪一節、設計稿是哪一份：README.md。

掛鉤照 tianxia/core/features.py 的表；用得到哪一個才寫哪一個。功能包只 import 核心（tianxia/core/ 與手冊 3.1 的核心模組）、共用規則層（registry.SHARED）與自己這一包。
玩家動作（main_actions、menxia_actions）、管理者工具（admin_tools）、API（routes）、鎖外三段式（outlock）寫在包的 routes.py，掛鉤裡才 from . import routes（手冊第十五節 G10）；路由第一行要有開關的 gate，關著丟 404（例 features/heroines/routes.py，test_shell_stays_thin 逐包打）。
新寫給玩家看的字標「待 joy 潤」。
"""
from __future__ import annotations

from tianxia.core.features import Feature


class {cls}(Feature):
    name = "{name}"
    prefix = "{name}"  # 選項 id 的前綴：{name}:…（核心只把這個前綴的 id 交給這一包）
    web: tuple[str, ...] = ()  # 畫面（手冊 G9）：web/ 底下的檔名，例 ("{name}.js", "{name}.css")。js 的 script 由伺服器照這裡生成，不要手改 index.html 的 script；新鈕在 web/{name}.js 寫 {name}Click 加 registerClicks，不加進 app.js；css 的 link 接在 index.html 最後一行 link 之後（不要排到 map.css、shop.css 前面），它與 tests/kit/webharness.APP_FILES 手寫
    content: tuple[str, ...] = ()  # 內容檔（手冊 G8）：相對於 tianxia/features/{name}/content/，例 ("{name}.json",)、("events/{name}.json",)；宣告了就要有那個檔，不放 repo 的 content/
    player_fields: tuple[str, ...] = ()  # 認領的 PlayerState 欄位（新欄位加在核心 state.py、名字帶包名前綴，標 Field(<預設>, json_schema_extra=QUIET)，不標 test_shell_stays_thin 紅，先過 PM：手冊第十五節 G7）
    carried: tuple[str, ...] = ()  # 上面那些裡換季照帶走的

    def enabled(self, ctx) -> bool:
        return ctx.content.config.{name}.enabled  # 預設關：讀 Config.{name}.enabled，tuning 的 enabled: bool = False；數字在 tianxia/core/tuning/{name}.py


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
        root / "tianxia" / "core" / "tuning" / f"{name}.py": f'''"""{title}的數字（Config.{name}；手冊第十五節「波次 B、C」第 15 條）。不 import models（models 引用這裡），所以不繼承 _Strict，自己寫 extra="forbid"。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class {tuning}(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
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
    models = root / "tianxia" / "models.py"
    _edit(models, TUNING_IMPORT_MARK, f"from .core.tuning.{name} import {tuning}  # {title}")
    _edit(models, TUNING_FIELD_MARK, f"    {name}: {tuning} = Field(default_factory={tuning})  # {title}（tianxia/core/tuning/{name}.py）")
    stage = _add_stage(root, name, title)
    return [*made, guide_path, registry, models, *([stage] if stage else [])]


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
    print("生完要接的：開發規範手冊第十五節「new_feature.py 生什麼、生完做什麼」；內容檔、畫面、玩家動作放哪：同一節 G8、G9、G10。")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
