"""手機通知包（全部拆包第 53 批）：有登記、五條 /api/push 與 /sw.js 掛著、舊名是同一個模組物件、殼啟動時經 threads 掛鉤開看守的執行緒
（殼開、測試停：測試不叫 start_threads，tests/conftest.py 收尾認 server.NOTICE_STOP、NOTICE_THREAD 這幾個名字）。
加密、五種事、訂閱與看守的行為在 test_web_push.py。"""
from __future__ import annotations

import server
import server_push
from tianxia.features.notify import notices as old_name
from tianxia.core import features as features_core
from tianxia.features import notify as package
from tianxia.features.notify import notices, webpush


def test_the_package_is_registered_and_the_old_names_are_the_same_objects():
    assert package.FEATURE in features_core.registered()
    assert package.FEATURE.name == "notify" and package.FEATURE.prefix is None
    assert old_name is notices
    for name in ("AVAILABLE", "PUSH_HOSTS", "RECORD_SIZE", "TTL_SECONDS", "VAPID_SECONDS", "PushStore", "Vapid", "WebPush",
                 "_hkdf", "_public_bytes", "b64url", "encrypt", "push_host_ok", "unb64url"):
        assert getattr(server_push, name) is getattr(webpush, name)


def test_the_routes_are_mounted():
    paths = server.app.openapi()["paths"]
    for path in ("/api/push", "/api/push/prefs", "/api/push/test", "/api/push/subscribe", "/api/push/unsubscribe"):
        assert path in paths
    assert "/sw.js" in paths


def test_main_opens_the_watcher_through_the_hook(monkeypatch):
    """殼開：server.main 叫 start_threads，start_threads 問包，包叫殼的 start_web_push。正式內容的 web_push 開著（測試內容關著，這裡換成開著）。"""
    import uvicorn  # noqa: PLC0415

    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(server.CONTENT.config.web_push, "enabled", True)
    server.main([])
    assert server.NOTICE_THREAD is not None and server.NOTICE_THREAD.name == "notice-watch"
