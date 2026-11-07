"""條款的煙霧測試（開發規範手冊 4.1 第三級：一包一條，走一次最常見的路）：真實內容的條款檔驗得過，兩頁打得開、寫著公司。"""
import pytest
from fastapi.testclient import TestClient

import server
from tianxia.core.registry import FEATURES
from tianxia.features.terms import rules


@pytest.mark.smoke
def test_terms_pages_open_and_the_content_checks_clean(game):
    feature = next(f for f in FEATURES if f.name == "terms")
    assert feature.enabled(game) is False
    assert rules.check(rules.load()) == []
    client = TestClient(server.app)
    for path, title in (("/terms", "使用條款"), ("/privacy", "隱私權條款")):
        res = client.get(path)
        assert res.status_code == 200 and title in res.text and "蟲洞創意企業有限公司" in res.text and "{" not in res.text.split("<style>")[0]
