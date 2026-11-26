"""宴客自己寫的敬酒詞走真路由 /api/do/feast_text（第 271 批；企劃者 2026-11-26「兩處都修 (Recommended)」）：
C 段的回話經 g._log，跟固定敬酒（feast:toast:<i> 走 choose）一樣——情誼跨過 biography.affinity_marks 的那一筆行狀
這一下就寫、不必等下一個請求；沒跨段回話一字不變，只多寫進 GameState.log；被擋下照舊。把 routes.py 的 g._log 拿掉 (a)(b) 會紅。"""
import pytest
import server
from tianxia import journal
from tianxia.characters import open_characters
from tianxia.features.feast import rules as feasts
from tianxia.sqlite_world import open_world
from tianxia.state import Feast
# autouse 的 fixture 要明列出來，不然只 import 用得到的那幾個會漏掉（同 battle 包的 test_battle_shell.py）
from server_kit import (  # noqa: F401
    _journal_titles, _no_landing, _no_preset_recipes, _player, cheap_password_hashing,
    client, fresh_server_memory, game, model_breaker_closed, save_dir, scheduler_off, season_already_open,
)

pytestmark = pytest.mark.whole_content

NAME = "沈青衫"
TEXT = "願天下太平"


@pytest.fixture(autouse=True)
def _feasts_on(monkeypatch):
    monkeypatch.setattr(server.CONTENT.config.figure_life, "enabled", True)


def _seated(client, affinity: int, seat: bool = True) -> int:
    """略過序章站在潁川，許劭在這裡擺一場宴（同 relay 軌 feast 那一段），坐上去；跟許劭的情誼先擺 affinity。回那一場的 id。"""
    _player(client)
    s = server.game_for(NAME).state  # 改伺服器手上那一份再存（同 battle 包第 270 批）
    seats = {}

    def open_feast(w) -> None:
        w.feast_seq += 1
        seats["id"] = w.feast_seq
        w.feasts.append(Feast(id=w.feast_seq, host="xushao", place=s.player.location, start=w.time, end=w.time + 2 * feasts.HOUR))

    open_world().mutate_season(open_feast)
    s.player.affinities["xushao"] = affinity
    if seat:
        s.player.feasting = seats["id"]
    open_characters().save(s)
    return seats["id"]


def _toasts(feast_id: int) -> list:
    return [t.text for f in open_world().get_season().feasts if f.id == feast_id for t in f.toasts]


def _affinity_lines(saved) -> list[str]:
    return [a.text for a in saved.player.annals if "情誼到了" in a.text]


def test_my_own_toast_that_crosses_an_affinity_mark_writes_the_deed_in_the_same_request(client, monkeypatch):
    """(a) 情誼 18 敬到 23：這一下的存檔就有「跟許劭的情誼到了 20。」、annals_mark 記的是 23，不必再打一個請求；回話也寫進 GameState.log。"""
    feast_id = _seated(client, 18)
    monkeypatch.setattr(feasts, "score", lambda client, req: 100)
    before = open_characters().load(NAME)
    assert before.player.annals_mark is not None and _affinity_lines(before) == []
    out = client.post("/api/do/feast_text", json={"text": TEXT}).json()
    saved = open_characters().load(NAME)  # 這一下的存檔（不再打 /api/main）
    value = saved.player.affinities["xushao"]
    assert 20 <= value < 40 and f"許劭情誼 +{value - 18}" in out["message"]
    assert _affinity_lines(saved) == ["跟許劭的情誼到了 20。"]
    deed = next(a for a in saved.player.annals if a.text == "跟許劭的情誼到了 20。")
    assert deed.figure == "xushao" and deed.time == saved.last_world  # 這一下的世界時間（不是下一次同步的）
    assert saved.player.annals_mark["aff"]["xushao"] == value
    assert saved.log[-2:] == [f"許劭情誼 +{value - 18}", journal.LOG_BREAK]
    assert saved.log[-3].startswith(f"你舉杯：「{TEXT}」")
    assert _toasts(feast_id) == [TEXT]


def test_my_own_toast_that_crosses_no_mark_replies_the_same_and_is_logged(client, monkeypatch):
    """(b) 情誼 0 敬到 5：回話一字不變（修之前量的）、照舊寫一則「宴客・許劭」、沒有情誼那一筆行狀；GameState.log 尾巴多這兩句。"""
    _seated(client, 0)
    monkeypatch.setattr(feasts, "score", lambda client, req: 100)
    titles = _journal_titles()
    out = client.post("/api/do/feast_text", json={"text": TEXT}).json()
    saved = open_characters().load(NAME)
    moved = saved.player.affinities["xushao"]
    said = feasts.TOASTED.format(text=TEXT, reaction=feasts.REACTIONS[0][1].format(host="許劭"))
    assert out["message"] == f"<p>{said}</p>\n<p>許劭情誼 +{moved}</p>\n"
    assert _journal_titles() == [f"{feasts.TITLE}・許劭"] + titles
    assert _affinity_lines(saved) == []
    assert saved.player.annals_mark["aff"]["xushao"] == moved
    assert saved.log[-3:] == [said, f"許劭情誼 +{moved}", journal.LOG_BREAK]


def test_a_toast_turned_away_before_the_model_says_the_same_line_and_writes_nothing(client):
    """(c-1) A 段擋下（沒坐在席上）：回「你不在宴席上。」，江湖紀錄、行狀、GameState.log、那一場的敬酒都不多（到不了 C 段）。"""
    feast_id = _seated(client, 18, seat=False)
    before = open_characters().load(NAME)
    out = client.post("/api/do/feast_text", json={"text": TEXT}).json()
    assert out["message"] == f"<p>{feasts.NOT_HERE}</p>\n"
    saved = open_characters().load(NAME)
    assert [e.title for e in saved.journal] == [e.title for e in before.journal]
    assert saved.player.annals == before.player.annals and saved.log == before.log
    assert _toasts(feast_id) == []


def test_a_toast_turned_away_after_the_model_says_the_same_line_and_only_logs_it(client, monkeypatch):
    """(c-2) C 段重驗擋下（評分的時候那一場散了）：回的那一句照舊，江湖紀錄、行狀、那一場的敬酒都不多；那一句也寫進 GameState.log。"""
    feast_id = _seated(client, 18)

    def score(client, req):
        def close(w) -> None:
            for f in w.feasts:
                if f.id == feast_id:
                    f.end = w.time - 1
        open_world().mutate_season(close)
        return 100

    monkeypatch.setattr(feasts, "score", score)
    before = open_characters().load(NAME)
    out = client.post("/api/do/feast_text", json={"text": TEXT}).json()
    assert out["message"] == f"<p>{feasts.NOT_HERE}</p>\n"
    saved = open_characters().load(NAME)
    assert [e.title for e in saved.journal] == [e.title for e in before.journal]
    assert saved.player.annals == before.player.annals and saved.player.affinities["xushao"] == 18
    assert saved.log[-2:] == [feasts.NOT_HERE, journal.LOG_BREAK]
    assert _toasts(feast_id) == []
