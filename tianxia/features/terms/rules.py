"""條款的規則（純函式，不讀時鐘：now 由呼叫端傳）：內容檔怎麼讀、這個帳號現在要不要按同意。"""
from __future__ import annotations

import datetime as dt
import json
from functools import lru_cache
from pathlib import Path

CONTENT_FILE = Path(__file__).resolve().parent / "content" / "terms.json"
DOCS = ("terms", "privacy")
TAIPEI = dt.timezone(dt.timedelta(hours=8))

# 這個帳號此刻的樣子（/api/terms 的 need）
NONE = ""  # 不用問
MUST = "must"  # 沒同意過任何一版：按了同意才進得去
ASK = "ask"  # 同意過舊版、新版還在考慮期：跳改版頁，可以先關掉（過了考慮期視為接受）


@lru_cache(maxsize=4)
def _read(path: str, mtime: float) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load(path: Path = CONTENT_FILE) -> dict:
    """讀內容檔（檔案改了就重讀：改條款只改內容檔，不用重開伺服器）。"""
    return _read(str(path), path.stat().st_mtime)


def fill(text: str, data: dict) -> str:
    """把 {company}、{tax_id}、{address}、{email}、{rating} 換成內容檔頂上的那幾格。"""
    c = data["company"]
    return text.format(company=c["name"], tax_id=c["tax_id"], address=c["address"], email=c["email"], rating=data["rating"])


def published_at(data: dict) -> float:
    """現行版生效那一天的 0 點（臺灣時間）。"""
    day = dt.date.fromisoformat(data["published"])
    return dt.datetime(day.year, day.month, day.day, tzinfo=TAIPEI).timestamp()


def need(agreed: str | None, data: dict, now: float, grace_days: int) -> str:
    """agreed：這個帳號最後同意的版本（沒有就是 None）。"""
    if agreed == data["version"]:
        return NONE
    if agreed is None:
        return MUST
    return ASK if now < published_at(data) + grace_days * 86400 else NONE


def check(data: dict) -> list[str]:
    """內容檔的毛病（content.validate 經 check_content 叫）。"""
    problems = []
    for key in ("version", "published", "company", "rating", "change_summary", "docs"):
        if key not in data:
            problems.append(f"terms.json 少了 {key}")
    if problems:
        return problems
    try:
        dt.date.fromisoformat(data["published"])
    except ValueError:
        problems.append("terms.json 的 published 要寫成 YYYY-MM-DD")
    for field in ("name", "tax_id", "address", "email"):
        if not data["company"].get(field):
            problems.append(f"terms.json 的 company 少了 {field}")
    for doc in DOCS:
        d = data["docs"].get(doc)
        if not d or not d.get("title") or not d.get("sections"):
            problems.append(f"terms.json 少了 docs.{doc}（title、sections）")
            continue
        for s in d["sections"]:
            for p in s.get("p", []):
                try:
                    fill(p, data)
                except (KeyError, IndexError, ValueError) as e:
                    problems.append(f"terms.json 的 {doc}「{s.get('h')}」有認不得的 {{}}：{e}")
    return problems
