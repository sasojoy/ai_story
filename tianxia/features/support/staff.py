"""客服名單（帳號與客服第 211 批；設計 6.2）：認帳號，不認名號。三個來源合起來：
- Config.support.staff（tianxia/core/tuning/support.py；設定檔寫）；
- .local/support.txt（一行一個，# 開頭是註解；照檔的修改時間重讀，不必重開伺服器）；
- 環境變數 TIANXIA_SUPPORT（逗號分開）。
每一筆是 accounts.id 的數字，或登入名（accounts.normalize：不分大小寫）。名號寫進來也不認。不動 content.py、is_admin。

第 212 批起本體在核心 tianxia/core/identity_base.py（商城的易名帖也要問：客服也不能改名，包不能 import 別包）；這裡留同名的轉手，
_cache 是同一個 dict（測試的 staff._cache.update 照用）。"""
from __future__ import annotations

from tianxia.core import identity_base

ENV_VAR = identity_base.SUPPORT_ENV
FILE_NAME = identity_base.SUPPORT_FILE

_cache: dict = identity_base._support_cache
staff_file = identity_base.support_file
names = identity_base.support_names


def is_staff(config, who) -> bool:
    """who 是 accounts_view.Who（沒有帳號是 None：假人、還沒登入的都不是）。比 id 的數字或登入名（全是數字的一筆只當 id）。"""
    return who is not None and identity_base.support_staff(config, who.id, who.login)
