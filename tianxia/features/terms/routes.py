"""條款的路由（功能包 tianxia/features/terms/）：殼（server 模組，參數 shell）照 FEATURES 掛；路徑跟別的路由不重疊。
這個檔只在殼掛路由時才 import（引擎與假人程式不碰網頁框架）；殼的東西一律照 shell.<名字> 當下讀，時鐘照 shell.time（測試換 time.time）。

- GET /terms、/privacy：兩頁，不用登入、開關關著也看得到。
- GET /api/terms：這個帳號要不要按同意（沒登入 401，網頁不理它）。開關關著 404（網頁把非 200 當沒事）。
- POST /api/terms/agree：{version, source}，version 不是現行版回 409（頁面開著的時候條款改版了）。
- record_consent(shell, account_key, version, source)：給註冊那一邊叫（設計稿「請註冊那邊接的一個勾選」）。
- GET /api/terms/version（第 206 批）：註冊頁與建角色頁的勾選要帶現行版號；不用登入、開關關著 404，只回 {version}。
- router 開頭把 _Hook 登記到核心 terms_base（第 206 批）：殼的 register 與 identity 包建角色經它查兩個勾選、記 source=register。"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import HTMLResponse

from tianxia.core import terms_base

from . import audit, pages, rules
from .store import ConsentStore

STALE = "條款剛更新了，請重新整理頁面再看一次。"  # 待 joy 潤
_log = logging.getLogger(__name__)


def store_path(shell) -> Path:
    """同意紀錄的小檔：遊戲資料庫旁邊、同名多「-terms.sqlite」（TIANXIA_DB 換了檔，它跟著換）。"""
    db = shell.default_path()
    return db.with_name(f"{db.stem}-terms.sqlite")


def consent_store(shell) -> ConsentStore:
    return ConsentStore(store_path(shell))


def record_consent(shell, account_key: str, version: str, source: str = "register") -> None:
    """記一筆同意；version 不是現行版丟 ValueError（註冊那一邊回玩家 STALE）。"""
    if version != rules.load()["version"]:
        raise ValueError(STALE)
    consent_store(shell).record(account_key, version, source, shell.time.time())


def status(shell, account_key: str) -> dict:
    data = rules.load()
    cfg = shell.CONTENT.config.terms
    agreed = consent_store(shell).latest(account_key)
    need = rules.need(agreed, data, shell.time.time(), cfg.grace_days, cfg.update_must) if cfg.enabled else rules.NONE
    out = {"need": need, "version": data["version"], "email": data["company"]["email"]}
    if need == rules.MUST and agreed is not None:
        out["update"] = True  # 第 243 批：同意過別版（換版號之後），網頁開頭換成改版那一句、同意記 source=update
    if need:
        out["summary"] = data["change_summary"]
        out["deadline"] = None if need == rules.MUST else rules.dt.datetime.fromtimestamp(
            rules.published_at(data) + cfg.grace_days * 86400, rules.TAIPEI).strftime("%Y-%m-%d")
    return out


class _Hook:
    """給核心 terms_base 的掛鉤（第 206 批）：現行版號、記一筆同意（版本不是現行版丟 ValueError，terms_base 吞掉）。"""

    def __init__(self, shell):
        self.shell = shell
        self._agreed: set = set()  # 第 249 批：同意過現行版的（旁檔路徑、版號、帳號鍵）；紀錄只加不刪，這個結論不會翻

    def version(self) -> str:
        return rules.load()["version"]

    def record(self, account_key: str, version: str, source: str) -> None:
        record_consent(self.shell, account_key, version, source)

    def must(self, account_key: str) -> bool:
        """第 249 批：殼的 _game 經 terms_base.gate_problem 問「這個帳號會改東西的請求要不要擋」。照 status() 同一條路
        （rules.need，時間照 shell.time、update_must 照設定）；只快取「同意過現行版」，must 與 ask 每次重查（按了同意下一個請求就放行）。
        鍵含旁檔路徑：測試每條換一個資料庫，同名帳號不會串。例外不在這裡吞（terms_base 吞、記 log、放行）。"""
        data = rules.load()
        ver = data["version"]
        seen = (str(store_path(self.shell)), ver, account_key)
        if seen in self._agreed:
            return False
        latest = consent_store(self.shell).latest(account_key)
        if latest == ver:
            self._agreed.add(seen)
            return False
        cfg = self.shell.CONTENT.config.terms
        return rules.need(latest, data, self.shell.time.time(), cfg.grace_days, cfg.update_must) == rules.MUST


def warn_if_consents_missing(shell) -> bool:
    """第 249 批：殼掛路由那一下（伺服器啟動）看一次——開關開著、帳號表有人、同意旁檔不在或現行版一筆都沒有，就 log 一行醒目的警告
    （旁檔遺失或搬機沒帶時，全體都會變成要重新同意、會改東西的請求全被擋）。唯讀（audit 用 mode=ro），不建旁檔；任何例外吞掉。"""
    if not shell.CONTENT.config.terms.enabled:
        return False
    try:
        db = shell.default_path()
        missing = audit.consent_missing(db, rules.load()["version"])
    except Exception:  # noqa: BLE001  啟動不能因為這個警告倒
        return False
    if missing:
        _log.warning("!!! terms: %s has accounts but no consent for the current version in %s "
                     "-- side file lost or not copied? everyone must agree again before any action", db, audit.side_path(db))
    return missing


def router(shell) -> APIRouter:
    terms_base.set_hook(_Hook(shell))
    warn_if_consents_missing(shell)
    r = APIRouter()

    def doc_page(doc: str):
        def view():
            return HTMLResponse(pages.page(doc, rules.load()))
        return view

    for doc in rules.DOCS:
        r.add_api_route(f"/{doc}", doc_page(doc), methods=["GET"], response_class=HTMLResponse)

    @r.get("/api/terms/version")
    def api_terms_version():
        """第 206 批：註冊頁與建角色頁的勾選要帶現行版號；還沒有帳號，不看 cookie。關著 404（gate 先於一切）。"""
        if not shell.CONTENT.config.terms.enabled:
            raise HTTPException(404)
        return {"version": rules.load()["version"]}

    @r.get("/api/terms")
    def api_terms(request: Request):
        """關著 404（網頁把非 200 當「沒事」）；開著才問登入。"""
        if not shell.CONTENT.config.terms.enabled:
            raise HTTPException(404)
        return status(shell, shell._account(request))

    @r.post("/api/terms/agree")
    def api_terms_agree(request: Request, body: dict = Body(...)):
        if not shell.CONTENT.config.terms.enabled:
            raise HTTPException(404)
        account_key = shell._account(request)
        source = body.get("source") if body.get("source") in ("gate", "update") else "gate"
        try:
            record_consent(shell, account_key, str(body.get("version") or ""), source)
        except ValueError:
            raise HTTPException(409, STALE)
        return status(shell, account_key)

    return r
