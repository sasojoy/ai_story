"""凌煙閣的路由（殼掛的；只在殼掛的時候才 import，engine 與假人不載入 fastapi）。開關關著回 404。

/lingyan：整頁 HTML（hall_html.page），沒登入也看得到（Joy 2026-11-26 在決定卡上選「沒登入也看得到」），
可以直接貼網址給朋友；只寫名號與事蹟，登入的人多一顆「回江湖」，沒登入的是「也去江湖走一遭」。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from . import hall, hall_html


def router(shell) -> APIRouter:
    r = APIRouter()

    @r.get("/lingyan")
    def lingyan_page(request: Request):
        """凌煙閣：收了季的每一季一卷（新的在前），只讀、不用登入。"""
        if not shell.CONTENT.config.lingyan.enabled:
            raise HTTPException(404)
        try:
            shell._account(request)
            logged_in = True
        except HTTPException as exc:
            if exc.status_code != 401:
                raise
            logged_in = False
        scrolls, live = hall.hall(shell.open_world(), shell.CONTENT)
        return HTMLResponse(hall_html.page(scrolls, live, logged_in=logged_in))

    return r
