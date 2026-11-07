"""戰記包（全部拆包第 52 批）：有登記、兩條路由掛著、殼啟動時經 threads 掛鉤開寫戰記的執行緒（殼開、測試停：測試不叫 start_threads，
tests/conftest.py 收尾認 server.TALES_STOP、TALES_THREAD 這幾個名字）。寫法與存放在 test_tale.py，標記在 test_tale_page.py，畫面在 tianxia/features/tale/tests/test_tale_web.py。"""
from __future__ import annotations

import sys

import server
from tianxia import tale as old_name
from tianxia.core import features as features_core
from tianxia.features import tale as package
from tianxia.features.tale import tale


def test_the_package_is_registered_and_the_old_names_are_the_same_module():
    assert package.FEATURE in features_core.registered()
    assert package.FEATURE.name == "tale" and package.FEATURE.prefix is None
    assert old_name is tale
    import tale_html as old_html  # noqa: PLC0415  根目錄的舊名

    assert old_html is sys.modules["tianxia.features.tale.tale_html"]


def test_the_routes_are_mounted():
    paths = server.app.openapi()["paths"]
    assert "/api/tale/{battle_id}" in paths and "/zhanji/{code}" in paths


def test_main_opens_the_writing_thread_through_the_hook(monkeypatch):
    """殼開：server.main 叫 start_threads，start_threads 問包，包叫殼的 start_tales（第 53 批照同一個形狀）。"""
    import uvicorn  # noqa: PLC0415

    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: None)
    server.main([])
    assert server.TALES_THREAD is not None and server.TALES_THREAD.name == "tales"
