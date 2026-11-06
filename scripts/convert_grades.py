"""一次性轉換：內容的檢定難度換成難度等級、獎勵換成獎勵等級（屬性與跨季架構 v2 第五節；第十節 ① 骨架，2026-11-04）。

用法：
  python scripts/convert_grades.py checks [--root content] [--apply]    檢定：difficulty N → grade ＋ shift（不寫 --apply 只出分布）
  python scripts/convert_grades.py rewards [--root content]             獎勵：只出報告（換成四級一定會改數字，等第 ② 階段跟經濟表一起換）

檢定照企劃者 2026-11-04「照建議」的帶子分級：3～4 易、5～6 尋常、7～8 難、9～12 極難、13 以上傳說；每一級的 dc 是
Config.checks.grades 的那一格，shift ＝ 原本的難度 − dc，所以換算回來的難度跟原本一模一樣（--apply 之後載入內容逐條比對，不一樣就還原）。
只改看得出是檢定的物件（有 stat、difficulty，其餘的鍵都是 Check 的欄位）；只換 `"difficulty": N` 那一段字，檔案其餘的排版不動。
可以重跑：已經換過的檢定不再碰。
"""
from __future__ import annotations

import argparse
import collections
import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tianxia.models import CheckRules, RewardRules  # noqa: E402

CHECK_KEYS = {"stat", "difficulty", "by", "practice", "stats", "tier"}
BANDS = ((3, 4, "easy"), (5, 6, "normal"), (7, 8, "hard"), (9, 12, "harsh"), (13, 99, "legend"))  # 企劃者 2026-11-04「照建議」
KEY = re.compile(r'(?<!\\)"difficulty"\s*:\s*(-?\d+)')


def grade_of(difficulty: int) -> tuple[str, int]:
    dc = {g.key: g.dc for g in CheckRules().grades}
    for low, high, key in BANDS:
        if low <= difficulty <= high or (key == "easy" and difficulty < low):
            return key, difficulty - dc[key]
    raise ValueError(difficulty)


def _walk(obj, out: list):
    """照文件順序收每一個有 difficulty 鍵的物件：是不是檢定（json 的鍵順序＝檔案裡的順序，跟正規式找到的順序一一對應）。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "difficulty":
                out.append(isinstance(v, int) and "stat" in obj and set(obj) <= CHECK_KEYS)
            _walk(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _walk(v, out)


def convert_text(text: str) -> tuple[str, collections.Counter]:
    marks: list[bool] = []
    _walk(json.loads(text), marks)
    found = list(KEY.finditer(text))
    if len(found) != len(marks):
        raise SystemExit(f"difficulty 的個數對不上（字 {len(found)}、JSON {len(marks)}），這個檔要手改")
    tally: collections.Counter = collections.Counter()
    pieces, last = [], 0
    for match, is_check in zip(found, marks):
        if not is_check:
            continue
        old = int(match.group(1))
        key, shift = grade_of(old)
        tally[(old, key, shift)] += 1
        new = f'"grade": "{key}"' + (f', "shift": {shift}' if shift else "")
        pieces += [text[last:match.start()], new]
        last = match.end()
    pieces.append(text[last:])
    return "".join(pieces), tally


def _check_difficulties(root: Path) -> list[tuple[str, int]]:
    from tianxia.content import load_content  # noqa: PLC0415
    from tianxia.models import Check  # noqa: PLC0415

    content = load_content(root)
    out: list[tuple[str, int]] = []
    seen: set[int] = set()

    def visit(obj, where: str) -> None:
        if hasattr(obj, "model_fields") and id(obj) not in seen:
            seen.add(id(obj))
            if isinstance(obj, Check):
                out.append((where, obj.difficulty))
            for name in type(obj).model_fields:
                if name != "config":
                    visit(getattr(obj, name), f"{where}.{name}")
        elif isinstance(obj, dict):
            for k, v in obj.items():
                visit(v, f"{where}[{k}]")
        elif isinstance(obj, (list, tuple)):
            for i, v in enumerate(obj):
                visit(v, f"{where}[{i}]")

    visit(content, "")
    return out


def _json_files(root: Path) -> list[Path]:
    """這個根底下每一個 json，排好。真實內容走 real_files：各包宣告的檔不在 content/ 底下（全部拆包第 62 批）；其他的根攤平。"""
    from tianxia.content import REAL_ROOT, real_files  # noqa: PLC0415

    return sorted(real_files().values() if root.resolve() == REAL_ROOT else root.rglob("*.json"))


def checks(root: Path, apply: bool) -> None:
    before = _check_difficulties(root) if apply else []
    total: collections.Counter = collections.Counter()
    originals: dict[Path, bytes] = {}
    for path in _json_files(root):
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        new, tally = convert_text(text)
        if not tally:
            continue
        total += tally
        if apply:
            originals[path] = raw
            path.write_bytes(new.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8") if b"\r\n" in raw else new.encode("utf-8"))
    names = {g.key: g.name for g in CheckRules().grades}
    by_grade: collections.Counter = collections.Counter()
    for (old, key, shift), n in sorted(total.items()):
        by_grade[key] += n
        print(f"  難度 {old:>2} → {names[key]}{'' if not shift else f'（{shift:+d}）'}：{n} 條")
    print("分布：" + "、".join(f"{names[k]} {by_grade[k]}" for k in names) + f"，合計 {sum(by_grade.values())} 條")
    if apply:
        after = _check_difficulties(root)
        if after != before:
            for path, raw in originals.items():
                path.write_bytes(raw)
            raise SystemExit("換算回來的難度跟原本不一樣，已經還原")
        print(f"已改 {len(originals)} 個檔；載入後 {len(after)} 個檢定的難度逐條跟原本一樣")


def rewards(root: Path) -> None:
    cfg = RewardRules()
    names = [g.name for g in cfg.grades]
    for kind, row in cfg.amounts.items():
        values: collections.Counter = collections.Counter()

        def walk(obj) -> None:
            if isinstance(obj, dict):
                stats = obj.get("stats")
                if isinstance(stats, dict) and isinstance(stats.get(kind), int) and stats[kind] > 0:
                    values[stats[kind]] += 1
                for v in obj.values():
                    walk(v)
            elif isinstance(obj, list):
                for v in obj:
                    walk(v)

        for path in _json_files(root):
            walk(json.loads(path.read_text(encoding="utf-8")))
        changed = 0
        print(f"{kind}（{'、'.join(f'{n} {a}' for n, a in zip(names, row))}）：")
        for value, n in sorted(values.items()):
            i = min(range(len(row)), key=lambda j: (abs(row[j] - value), j))
            changed += n if row[i] != value else 0
            print(f"  {value:>4} → {names[i]}（{row[i]}）：{n} 條")
        print(f"  合計 {sum(values.values())} 條，換了數字會變的 {changed} 條")


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("what", choices=("checks", "rewards"))
    parser.add_argument("--root", default=str(ROOT / "content"))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.what == "checks":
        checks(Path(args.root), args.apply)
    else:
        rewards(Path(args.root))


if __name__ == "__main__":
    main()
