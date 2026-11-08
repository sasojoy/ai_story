"""客服名單（帳號與客服第 211 批；設計 6.2）：認帳號，不認名號。三個來源合起來：
- Config.support.staff（tianxia/core/tuning/support.py；設定檔寫）；
- .local/support.txt（一行一個，# 開頭是註解；照檔的修改時間重讀，不必重開伺服器）；
- 環境變數 TIANXIA_SUPPORT（逗號分開）。
每一筆是 accounts.id 的數字，或登入名（accounts.normalize：不分大小寫）。名號寫進來也不認。由這一包自己讀，不動 content.py、is_admin。"""
from __future__ import annotations

import os
from pathlib import Path

from tianxia import content as content_module
from tianxia.accounts import normalize

ENV_VAR = "TIANXIA_SUPPORT"
FILE_NAME = "support.txt"

_cache: dict = {"path": None, "mtime": None, "names": frozenset()}


def staff_file() -> Path:
    return content_module.LOCAL_DIR / FILE_NAME


def _file_names(path: Path) -> frozenset[str]:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return frozenset()
    if _cache["path"] == path and _cache["mtime"] == mtime:
        return _cache["names"]
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return frozenset()
    names = frozenset(normalize(line) for line in lines if line.strip() and not line.strip().startswith("#"))
    _cache.update(path=path, mtime=mtime, names=names)
    return names


def names(config) -> frozenset[str]:
    """名單上每一筆（小寫、去空白）。"""
    listed = {normalize(x) for x in config.support.staff}
    listed |= {normalize(x) for x in os.environ.get(ENV_VAR, "").split(",")}
    listed |= _file_names(staff_file())
    listed.discard("")
    return frozenset(listed)


def is_staff(config, who) -> bool:
    """who 是 accounts_view.Who（沒有帳號是 None：假人、還沒登入的都不是）。比 id 的數字或登入名。"""
    if who is None:
        return False
    listed = names(config)
    return str(who.id) in listed or (bool(who.login) and normalize(who.login) in listed)
