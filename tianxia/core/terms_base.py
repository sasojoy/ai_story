"""條款的核心接縫（帳號與客服第 206 批；計畫 docs/superpowers/plans/2026-11-08-帳號與客服-第206批.md）。

註冊在殼（server.register）與 identity 包（建角色那一步才開帳號），包不准 import 別包（設計第五節「記版本的函式要放核心，
或由條款包掛進註冊與建角色的流程」）：terms 包在殼掛路由那一下 set_hook，註冊那兩條路只問這裡。
照 identity_base.set_notifier／notify 的寫法：核心只放掛鉤與純規則，不 import 包、不讀時鐘（時間在 hook 那一側的 shell.time）。
開關 Config.terms.enabled 關著，或 terms 包沒掛（沒有 hook）：register_problem 回 None、record 回 False，什麼都不做。
第 249 批：gate_problem 給殼的 _game 問「會改東西的請求要不要擋」（關著或沒 hook 一樣回 None）。"""
from __future__ import annotations

import logging

REGISTER_NEED = "請先勾選滿 18 歲與同意使用條款、隱私權條款，再送出。"  # 待 joy 潤（沒勾、只勾一個、版本舊都是這一句，不透露版本）
_YES = (True, "on", "true", "1")  # 表單送 "on"，JSON 送 true
GATE_NEED = "請先看過並同意使用條款與隱私權條款，才能繼續。重新整理頁面就會看到同意頁。"  # 待 joy 潤（第 249 批：伺服器擋下會改東西的請求時回這一句；網頁不會自己重問，所以叫他重新整理）
_HOOK = None  # terms 包登記的物件：version() -> 現行版號；record(account_key, version, source)，版本不是現行版丟 ValueError；must(account_key) -> bool（第 249 批）
_log = logging.getLogger(__name__)


def on(content) -> bool:
    return bool(content.config.terms.enabled)


def set_hook(obj) -> None:
    """terms 包登記（殼掛路由那一下）；None 拿掉。"""
    global _HOOK
    _HOOK = obj


def register_problem(content, body: dict) -> str | None:
    """開新帳號之前查兩個勾選與表單帶來的版號：不合回 REGISTER_NEED（殼與 identity 自己丟 GameError），合了或不必查回 None。"""
    if _HOOK is None or not on(content):
        return None
    body = body or {}
    ticked = body.get("age_ok") in _YES and body.get("terms_agree") in _YES
    if ticked and body.get("terms_version") == _HOOK.version():
        return None
    return REGISTER_NEED


def record(content, account_key: str, version, source: str = "register") -> bool:
    """帳號建好之後記一筆同意（記表單帶來的那一版，不是當下的現行版）；版本剛好改了（hook 丟 ValueError）吞掉、記 log、
    回 False，登入後同意層會補問。不丟例外、不 500。"""
    if _HOOK is None or not on(content):
        return False
    try:
        _HOOK.record(account_key, str(version or ""), source)
    except ValueError:
        _log.warning("terms: register consent not recorded (version changed)")
        return False
    except Exception:
        # 旁檔寫不進去（鎖住、磁碟滿）也不往上丟：帳號已經開好了，登入後同意層會補問。
        _log.exception("terms: register consent not recorded (side file write failed)")
        return False
    return True


def gate_problem(content, account_key: str) -> str | None:
    """第 249 批：這個帳號會改東西的請求要不要擋（殼 server._game 在不是 GET、不是管理者時問）。
    關著或 terms 包沒掛（沒有 hook）回 None，行為不變；hook 丟任何例外（旁檔鎖住、壞掉、內容檔讀不到、舊 hook 沒有 must）
    記一行 log、回 None 放行（網頁那一層照樣會問）；必須同意而沒同意回 GATE_NEED。不看是不是假人（假人不經伺服器）。"""
    if _HOOK is None or not on(content):
        return None
    try:
        must = _HOOK.must(account_key)
    except Exception:
        _log.exception("terms: gate check failed, letting the request through")
        return None
    return GATE_NEED if must else None
