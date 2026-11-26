"""凌煙閣的路由（殼掛的；只在殼掛的時候才 import，engine 與假人不載入 fastapi）。開關關著回 404。

/lingyan：整頁 HTML（hall_html.page）。現在要登入（沒登入回 401 的一頁，請他去登入）；設計稿寫「沒登入也看得到」，
要不要拿掉登入等 Joy 點頭（拿掉時要加進 tests/core/shell_tables.py 的 NO_LOGIN_ROUTES、PR 寫原話）。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from . import hall, hall_html


def router(shell) -> APIRouter:
    r = APIRouter()

    @r.get("/lingyan")
    def lingyan_page(request: Request):
        """凌煙閣：收了季的每一季一卷（新的在前），只讀。"""
        try:
            shell._account(request)  # 沒登入 401（先於開關，同稱號包：關著也不讓沒登入的人試出有沒有這一頁）
        except HTTPException as exc:
            if exc.status_code != 401:
                raise
            return HTMLResponse(hall_html.missing(), status_code=401)
        if not shell.CONTENT.config.lingyan.enabled:
            raise HTTPException(404)
        scrolls, live = hall.hall(shell.open_world(), shell.CONTENT)
        return HTMLResponse(hall_html.page(scrolls, live))

    return r
