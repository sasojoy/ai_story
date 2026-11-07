"""手機通知的看守與 API（功能包 tianxia/features/notify/；全部拆包第 53 批照戰記的做法從 server.py 搬進來）：殼（server 模組，參數 shell）照 FEATURES 掛
路由（server 的 features_core.routers 那一行；五條 /api/push 與 /sw.js 的路徑跟別的路由不重疊，先後不影響），看守執行緒由包的 threads 掛鉤叫殼的 start_web_push 開。
殼留 state 的宣告（WEB_PUSH、NOTICE_STOP、NOTICE_THREAD、NOTICE_SENT、MAIL_DONE、VAPID_FILE 與四個測試讀的字串；tests/conftest.py 收尾認這幾個名字）與四個一行薄包裝
（start_web_push、notice_round、_notice_keys、web_push_line；same_behavior 與測試從 server. 叫）。殼的東西一律照 shell.<名字> 當下讀、當下寫（測試換掉的也看得到），
標準庫的 threading 照模組屬性當下查（測試換 server.threading.Thread），時鐘照 shell.time（測試換 time.time）。
這個檔只在殼掛路由時才 import（引擎與假人程式不碰網頁框架）。"""
from __future__ import annotations

import os
import threading
from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Request, Response

from . import notices


def push_store_path(shell) -> Path:
    """訂閱的小檔：遊戲資料庫旁邊、同名多「-push.sqlite」（TIANXIA_DB 換了檔，它跟著換）。"""
    db = shell.default_path()
    return db.with_name(f"{db.stem}-push.sqlite")


def web_push_line(shell, config) -> str:
    if not config.web_push.enabled:
        return "手機通知：關"
    if not shell.server_push.AVAILABLE:
        return "手機通知：關（這台主機沒裝 cryptography：pip install -r requirements.txt）"
    return f"手機通知：開（每 {config.web_push.watch_seconds:g} 秒看一次開了通知的人；金鑰 {shell.VAPID_FILE}）"


def start_web_push(shell, config, post=None):
    """開關開著、cryptography 在：建 WEB_PUSH、開看守執行緒（daemon）；不然什麼都不做、回 None。只有 main()（經 threads 掛鉤）與測試呼叫。
    簽名的 sub 照 TIANXIA_PUBLIC_URL（固定網域），沒設就寫固定網域本身（推送服務只認 https 或 mailto）。"""
    if not config.web_push.enabled or not shell.server_push.AVAILABLE:
        return None
    subject = os.environ.get("TIANXIA_PUBLIC_URL") or "https://tianxiadashi.com"
    shell.WEB_PUSH = shell.server_push.WebPush(shell.server_push.PushStore(push_store_path(shell)), shell.server_push.Vapid(shell.VAPID_FILE, subject), post=post)
    failures = shell._StepFailures(shell.time.monotonic, "通知的看守")

    def loop() -> None:
        while not shell.NOTICE_STOP.wait(config.web_push.watch_seconds):
            try:
                shell.notice_round()
            except Exception as e:  # noqa: BLE001  看守不能因為一輪出錯就停
                failures.failed(e)
            failures.tick()

    shell.NOTICE_THREAD = threading.Thread(target=loop, daemon=True, name="notice-watch")
    shell.NOTICE_THREAD.start()
    return shell.WEB_PUSH


def _notice_keys(shell, game, account_key: str, now: float) -> tuple[list, bool]:
    """行動鎖內：到了送信的時刻先替他送今天的信（送了就存角色；開著的分頁照常輪詢就看得到，不叫 HUB：只有動作的端點叫，
    見 _tell_tabs），回傳（五種事, 正在玩）。
    正在玩：quiet_seconds 之內同步過（分頁開著），畫面上已經看得到，不必再跳。"""
    day = shell.letters.mail_day(game.content, game.state.world, now)
    if day is not None and shell.MAIL_DONE.get(account_key) != day:
        if game.morning_mail(now):
            shell.open_characters().save(game.state)
        shell.MAIL_DONE[account_key] = day
    last = game.state.last_real
    busy = last is not None and now - last < game.content.config.web_push.quiet_seconds
    return notices.current(game.state, game.content, game.world.get_battle(), game.world.sortie_duels()), busy


def notice_round(shell, clock: Callable[[], float]) -> int:
    """看守的一輪：開了通知的每一個帳號進一次鎖（_notice_keys），鎖外比上一輪、新的才跳（一人一輪最多 per_round 則，
    多的下一輪再跳）。第一次看到這個帳號只記下、不跳。回傳跳了幾則（測試用）。"""
    push = shell.WEB_PUSH
    if push is None:
        return 0
    cfg = shell.CONTENT.config.web_push
    sent_total = 0
    for account_key in push.store.accounts():
        account = shell.account_store().get(account_key)
        if account is None or account.character is None:
            continue
        game = shell.game_for(account.character)
        with shell._locked(game):
            now = clock()
            notes, busy = shell._notice_keys(game, account_key, now)
        keys = {n.key for n in notes}
        seen = shell.NOTICE_SENT.get(account_key)
        if seen is None or busy:
            shell.NOTICE_SENT[account_key] = keys
            continue
        off = push.store.kinds_off(account_key)  # 設定頁關掉的那幾種：不跳，也記成看過（之後打開不會補跳一串舊的）
        muted = {n.key for n in notes if n.key not in seen and n.kind in off}
        fresh = [n for n in notes if n.key not in seen and n.kind not in off]
        for n in fresh[:cfg.per_round]:
            sent_total += bool(push.send(account_key, shell.NOTICE_TITLE, n.text, tag=n.kind, now=now))
        shell.NOTICE_SENT[account_key] = (keys & seen) | muted | {n.key for n in fresh[:cfg.per_round]}
    return sent_total


def _web_push(shell):
    push = shell.WEB_PUSH
    if push is None:
        raise HTTPException(404)
    return push


def router(shell) -> APIRouter:
    r = APIRouter()

    @r.get("/api/push")
    def api_push(request: Request):
        """手機通知（減法季批 9）：瀏覽器訂閱要的那一串公鑰，加上五種通知各開著沒（設定頁一種一個開關，預設全開）。開關關著 404。"""
        push = _web_push(shell)
        off = push.store.kinds_off(shell._account(request))
        return {"key": push.vapid.public, "kinds": {k: k not in off for k in notices.KINDS}}

    @r.post("/api/push/prefs")
    def api_push_prefs(request: Request, body: dict = Body(...)):
        """開或關一種通知：{kind, on}。存在這個帳號（每一台裝置一樣）。"""
        push = _web_push(shell)
        kind = str(body.get("kind", ""))
        if kind not in notices.KINDS:
            raise shell.GameError("沒有這一種通知。")
        off = push.store.set_kind(shell._account(request), kind, bool(body.get("on")))
        return {"kinds": {k: k not in off for k in notices.KINDS}}

    @r.post("/api/push/test")
    def api_push_test(request: Request, body: dict = Body(...)):
        """設定頁「傳一則測試通知」：{endpoint}。當場對這一台送一則，送不出去把原因回給畫面（{sent: false, error}）。"""
        push = _web_push(shell)
        account_key = shell._account(request)
        endpoint = str(body.get("endpoint", ""))
        device = next((d for d in push.store.devices(account_key) if d["endpoint"] == endpoint), None)
        if device is None:
            return {"sent": False, "error": shell.PUSH_NOT_HERE}
        why = push.deliver(device, shell.NOTICE_TITLE, shell.PUSH_TEST, tag="test")
        return {"sent": why is None, "error": why or ""}

    @r.post("/api/push/subscribe")
    def api_push_subscribe(request: Request, body: dict = Body(...)):
        """這台裝置開通知：{endpoint, keys: {p256dh, auth}, quiet}（瀏覽器 PushSubscription 的 JSON，多一個 quiet）。
        位址不是認得的推送服務就不收。開了先把他身上現有的事記成看過（不會一開就跳一串舊信）；不是 quiet 就送一則「開了」的通知，
        手機上當場看得到通不通（主機驗收也看這一則）。"""
        push = _web_push(shell)
        account_key = shell._account(request)
        endpoint = str(body.get("endpoint", ""))
        keys = body.get("keys") if isinstance(body.get("keys"), dict) else {}
        p256dh, auth = str(keys.get("p256dh", "")), str(keys.get("auth", ""))
        if len(endpoint) > 1024 or not shell.server_push.push_host_ok(endpoint) or not (40 <= len(p256dh) <= 200 and 8 <= len(auth) <= 64):
            raise shell.GameError("這個瀏覽器給的通知位址不對，換一個瀏覽器試試。")  # 待 joy 潤
        push.store.add(account_key, endpoint, p256dh, auth, shell.time.time(), shell.CONTENT.config.web_push.max_devices)
        game = shell._game(request)
        with shell._locked(game):
            notes = notices.current(game.state, game.content, game.world.get_battle(), game.world.sortie_duels())
        shell.NOTICE_SENT[account_key] = {n.key for n in notes}
        if not body.get("quiet"):
            threading.Thread(target=push.send, args=(account_key, shell.NOTICE_TITLE, shell.PUSH_WELCOME), kwargs={"tag": "welcome"}, daemon=True).start()
        return {"on": True}

    @r.post("/api/push/unsubscribe")
    def api_push_unsubscribe(request: Request, body: dict = Body(...)):
        """這台裝置關通知：{endpoint}。只刪得掉自己帳號的。"""
        push = _web_push(shell)
        push.store.remove(str(body.get("endpoint", "")), shell._account(request))
        return {"on": False}

    @r.get("/sw.js")
    def service_worker():
        """手機通知的 service worker：放在根目錄，管得到整個網站（/static 底下的管不到 /）。檔在 web/sw.js（留原位，不進 Feature.web：web_scripts 會把 .js 排成 script）。"""
        return Response((shell.WEB / "sw.js").read_bytes(), media_type="text/javascript", headers=shell.NO_CACHE)

    return r
