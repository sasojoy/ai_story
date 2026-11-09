"""條款的核心接縫（帳號與客服第 206 批；計畫 docs/superpowers/plans/2026-11-08-帳號與客服-第206批.md）。

註冊在殼（server.register）與 identity 包（建角色那一步才開帳號），包不准 import 別包（設計第五節「記版本的函式要放核心，
或由條款包掛進註冊與建角色的流程」）：terms 包在殼掛路由那一下 set_hook，註冊那兩條路只問這裡。
照 identity_base.set_notifier／notify 的寫法：核心只放掛鉤與純規則，不 import 包、不讀時鐘（時間在 hook 那一側的 shell.time）。
開關 Config.terms.enabled 關著，或 terms 包沒掛（沒有 hook）：register_problem 回 None、record 回 False，什麼都不做。"""
from __future__ import annotations

import logging

REGISTER_NEED = "請先勾選滿 18 歲與同意使用條款、隱私權條款，再送出。"  # 待 joy 潤（沒勾、只勾一個、版本舊都是這一句，不透露版本）
_YES = (True, "on", "true", "1")  # 表單送 "on"，JSON 送 true
_HOOK = None  # terms 包登記的物件：version() -> 現行版號；record(account_key, version, source)，版本不是現行版丟 ValueError
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
    return True
