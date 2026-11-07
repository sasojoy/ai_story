"""條款的路由（功能包 tianxia/features/terms/）：殼（server 模組，參數 shell）照 FEATURES 掛；路徑跟別的路由不重疊。
這個檔只在殼掛路由時才 import（引擎與假人程式不碰網頁框架）；殼的東西一律照 shell.<名字> 當下讀，時鐘照 shell.time（測試換 time.time）。

- GET /terms、/privacy：兩頁，不用登入、開關關著也看得到。
- GET /api/terms：這個帳號要不要按同意（沒登入 401，網頁不理它）。開關關著 need 是空字串。
- POST /api/terms/agree：{version, source}，version 不是現行版回 409（頁面開著的時候條款改版了）。
- record_consent(shell, account_key, version, source)：給註冊那一邊叫（設計稿「請註冊那邊接的一個勾選」）。"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import HTMLResponse

from . import pages, rules
from .store import ConsentStore

STALE = "條款剛更新了，請重新整理頁面再看一次。"  # 待 joy 潤


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
    need = rules.need(agreed, data, shell.time.time(), cfg.grace_days) if cfg.enabled else rules.NONE
    out = {"need": need, "version": data["version"], "email": data["company"]["email"]}
    if need:
        out["summary"] = data["change_summary"]
        out["deadline"] = None if need == rules.MUST else rules.dt.datetime.fromtimestamp(
            rules.published_at(data) + cfg.grace_days * 86400, rules.TAIPEI).strftime("%Y-%m-%d")
    return out


def router(shell) -> APIRouter:
    r = APIRouter()

    def doc_page(doc: str):
        def view():
            return HTMLResponse(pages.page(doc, rules.load()))
        return view

    for doc in rules.DOCS:
        r.add_api_route(f"/{doc}", doc_page(doc), methods=["GET"], response_class=HTMLResponse)

    @r.get("/api/terms")
    def api_terms(request: Request):
        return status(shell, shell._account(request))

    @r.post("/api/terms/agree")
    def api_terms_agree(request: Request, body: dict = Body(...)):
        account_key = shell._account(request)
        source = body.get("source") if body.get("source") in ("gate", "update") else "gate"
        try:
            record_consent(shell, account_key, str(body.get("version") or ""), source)
        except ValueError:
            raise HTTPException(409, STALE)
        return status(shell, account_key)

    return r
