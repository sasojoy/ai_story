"""一次性：把隨口應對分岔的草稿（content/events_outcomes.json，減法季整合設計 5.1、5.9）併進 content/events/*.json 各自的
free_text.outcomes（主機側計畫 Task 4-1）。2026-10-24 dev/jianfa-4 跑過一次，併了 29 則；草稿與 scripts/check_outcomes.py 跑完刪掉，
規則搬進 content.validate 的 check_outcomes。

- 只併「事件本來就有 free_text」的那幾則：outcomes 接在 free_text 最後一個鍵後面，其餘一個位元組都不動（照原檔的縮排、CRLF、結尾換行寫回；
  寫不回原樣的檔整支停下來，不寫任何檔）。
- 草稿標了 needs_free_text 的（yc_wilds_plow）不併、印出來：補 free_text 會讓關著的季也多一顆「隨口應對」，要跟開關一起接（計畫 6.0 第 9 條、6.5）。
- 已經有 outcomes 的事件不覆蓋（再跑一次什麼都不改）。
- 寫完照每一份設定覆寫檔各載一次內容（content.validate 擋的這裡就擋）。

用法：python scripts/merge_outcomes.py [草稿路徑]
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _read(path: Path):
    """讀一個 JSON 檔與它的寫法（縮排、CRLF、結尾換行）；json.dumps 寫不回原樣就回 None。"""
    raw = path.read_bytes().decode("utf-8")
    text = raw.replace("\r\n", "\n")
    data = json.loads(text)
    for indent in (1, 2, 4):
        dumped = json.dumps(data, ensure_ascii=False, indent=indent)
        for tail in ("", "\n"):
            if dumped + tail == text:
                return data, (indent, tail, "\r\n" in raw)
    return data, None


def _write(path: Path, data, fmt) -> None:
    indent, tail, crlf = fmt
    text = json.dumps(data, ensure_ascii=False, indent=indent) + tail
    path.write_bytes((text.replace("\n", "\r\n") if crlf else text).encode("utf-8"))


def merge(draft_path: Path, events_dir: Path) -> tuple[list[str], list[dict]]:
    """併進去的事件 id、沒併的草稿（needs_free_text）。"""
    draft = json.loads(draft_path.read_bytes().decode("utf-8"))
    files = {}
    where = {}
    for path in sorted(events_dir.glob("*.json")):
        data, fmt = _read(path)
        files[path] = (data, fmt)
        for event in data:
            where[event["id"]] = (path, event)
    merged, deferred, touched = [], [], set()
    for entry in draft["events"]:
        found = where.get(entry["id"])
        if found is None:
            raise SystemExit(f"content/events 裡沒有 {entry['id']}")
        path, event = found
        if entry.get("needs_free_text") or event.get("free_text") is None:
            deferred.append(entry)
            continue
        if event["free_text"].get("outcomes"):
            continue
        if files[path][1] is None:
            raise SystemExit(f"{path.name} 寫不回原樣（縮排或換行跟 json.dumps 不同），沒有改任何檔")
        event["free_text"]["outcomes"] = entry["outcomes"]
        merged.append(entry["id"])
        touched.add(path)
    for path in sorted(touched):
        _write(path, *files[path])
    return merged, deferred


def main(argv: list[str]) -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    draft_path = Path(argv[0]) if argv else ROOT / "content" / "events_outcomes.json"
    merged, deferred = merge(draft_path, ROOT / "content" / "events")
    print(f"併進 {len(merged)} 則：{'、'.join(merged)}")
    for entry in deferred:
        print(f"沒併（事件沒有 free_text，要跟開關一起補）：{entry['id']}")
        print(json.dumps(entry, ensure_ascii=False, indent=1))
    from tianxia.content import load_content  # noqa: PLC0415  寫完才載：載入要讀剛寫好的檔

    for profile in [None, *sorted(p.stem for p in (ROOT / "content" / "profiles").glob("*.json"))]:
        load_content(ROOT / "content", profile)
        print(f"載入 {profile or '預設'}：過")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
