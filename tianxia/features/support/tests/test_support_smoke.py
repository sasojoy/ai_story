"""客服的煙霧測試（開發規範手冊 4.1 第三級：一包一條，走一次最常見的路）：真實內容關著、不給選項；旁檔送一張單、客服回一則、玩家有一則未讀。"""
import pytest
from conftest import real_content

from tianxia.core.registry import FEATURES
from tianxia.features.support import rules, store


@pytest.mark.smoke
def test_support_is_registered_and_quiet_while_closed(game):
    feature = next(f for f in FEATURES if f.name == "support")
    assert feature.enabled(game) is False
    assert not any(o.id.startswith("support:") for o in game.options())


@pytest.mark.smoke
def test_support_files_and_answers_a_ticket(tmp_path):
    cfg = real_content("week7").config.support
    assert cfg.enabled is False and (cfg.body_max, cfg.open_max, cfg.daily_max) == (1000, 3, 5)
    s = store.SupportStore(store.store_path(tmp_path / "x.db"))
    assert s.path.name == "x-support.sqlite"
    tid = s.add_ticket(account_id=1, account_created=1.0, login="shen_01", character="沈青衫", version="", category="account", body="登不進去",
                       now=10.0, open_max=cfg.open_max, daily_max=cfg.daily_max)
    assert s.staff_reply(tid, 2, "好了", "wait", 20.0)["status"] == rules.ANSWERED
    assert s.unread(1, 1.0) == 1 and s.unread(1, 2.0) == 0
