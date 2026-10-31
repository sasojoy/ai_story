"""事件旁白每週改寫（減法季整合設計第十章，批 10）：哪些改寫、改寫的過濾、引擎照這一週的讀、伺服器的背景一輪（假的模型回答）。"""
from __future__ import annotations

import pytest

import server
from conftest import real_content
from tianxia import foreshadow, narration
from tianxia.engine import Game
from tianxia.world_state import fresh_season


@pytest.fixture
def c():
    content = real_content()
    content.config.jianfa.enabled = True
    content.config.banned_names_on = True  # 專有名詞名單正式設定關著（Joy 2026-10-31），這裡驗開著時潤色照擋
    return content


def _world(c, on=True):
    w = fresh_season(c)
    w.jianfa_on = on
    return w


def _plain(c):
    """一則可以改寫、原文沒有標記也沒有數字的事件。"""
    for eid in narration.eligible(c):
        e = c.events[eid]
        if "{" not in e.text and not any(ch.isdigit() for ch in e.text) and len(e.text) >= 40:
            return e
    raise AssertionError("找不到合用的事件")


# ── 哪些改寫 ──

def test_eligible_skips_the_story_events(c):
    found = set(narration.eligible(c))
    assert len(found) > 200  # 一週約兩、三百則
    promo = {x for p in c.promotions for x in (p.event_main, p.event_handoff) if x}
    assert not found & promo
    assert not found & foreshadow.event_ids(c)
    assert all(not c.events[e].once and not c.events[e].qiyu and not c.events[e].fortune and c.events[e].actions for e in found)
    assert c.opening.event not in found and c.tutorial.start_event not in found  # 開局、序章


# ── 過濾 ──

def test_clean_keeps_a_faithful_rewrite(c):
    e = _plain(c)
    good = "這時，" + e.text
    assert narration.clean(c, e.text, good) == good
    assert narration.clean(c, e.text, f"「{good}」") == good  # 包住整段的引號拿掉
    assert narration.clean(c, e.text, good.replace("這", "这")) == good  # 簡體轉繁體


def test_clean_rejects_what_changes_the_skeleton(c):
    e = _plain(c)
    assert narration.clean(c, e.text, e.text) is None  # 一字沒改
    assert narration.clean(c, e.text, "你到了。") is None  # 太短
    assert narration.clean(c, e.text, e.text * 2) is None  # 太長
    assert narration.clean(c, e.text, "三日後，" + e.text.replace("，", "，3", 1)) is None  # 冒出數字
    assert narration.clean(c, e.text, "OK，" + e.text) is None
    stranger = next(ch.name for ch in c.characters.values() if ch.name not in e.text and len(ch.name) >= 2)
    assert narration.clean(c, e.text, f"{stranger}看著，" + e.text) is None  # 原文沒有的人
    banned = c.banned_names[0]
    assert narration.clean(c, e.text, f"{banned}，" + e.text) is None
    assert narration.clean(c, e.text, None) is None


def test_clean_keeps_the_marks_tokens(c):
    original = "村口聚著{marks:yingchuan:refugee}流民，有人在哭，有人在罵，你走近時他們一齊抬起頭來。"
    assert narration.clean(c, original, "村口擠著{marks:yingchuan:refugee}流民，哭的哭、罵的罵，你一走近，他們一齊抬頭。")
    assert narration.clean(c, original, "村口擠著一群流民，哭的哭、罵的罵，你一走近，他們全都抬起頭來看你。") is None



def test_clean_rejects_the_tics_measured_on_the_host(c):
    """2026-10-26 主機拿真模型整週實測（243 則）抓到的三種毛病：自己加一行標題、把對話的引號吃掉、把同一句寫兩次。"""
    e = _plain(c)
    good = "這時，" + e.text
    assert narration.clean(c, e.text, "【壕溝之外】" + good) == good  # 模型照著餵進去的格式加的標題：拿掉，後面照用
    talk = e.text + "他說：「跟我來。」"
    assert narration.clean(c, talk, "這時，" + talk) == "這時，" + talk  # 引號齊的照過
    assert narration.clean(c, talk, "這時，" + e.text + "他說：跟我來。") is None  # 引號被吃掉
    assert narration.clean(c, talk, "這時，" + talk + "「再說一次。」") is None  # 多一對引號也不行
    twice = [s for s in e.text.split("。") if len(s) >= 8][0]
    assert narration._repeats(e.text + twice + "。", e.text)  # 搬句子搬成同一句兩次
    assert not narration._repeats(good, e.text)


# ── 引擎照這一週的讀 ──

def test_text_of_follows_the_switch_and_the_week(c):
    e = _plain(c)
    asked = []

    def lookup(season, week, eid):
        asked.append((season, week, eid))
        return "改寫好的。"

    w = _world(c)
    assert narration.text_of(c, w, e, 3, lookup) == "改寫好的。"
    assert asked == [(3, narration.period(c, w), e.id)]
    assert narration.text_of(c, _world(c, on=False), e, 3, lookup) == e.text  # 這一季沒蓋章
    assert narration.text_of(c, w, e, 3, None) == e.text  # 沒有查詢（假人程式）
    assert narration.text_of(c, w, e, 3, lambda *a: None) == e.text  # 這一週還沒寫到
    assert narration.text_of(c, w, e, 3, lambda *a: 1 / 0) == e.text  # 小檔讀不到
    promo = c.events[c.promotions[0].event_main]
    assert narration.text_of(c, w, promo, 3, lookup) == promo.text  # 晉升奇遇不改寫
    c.config.jianfa.rewrite_narration = False
    assert narration.text_of(c, w, e, 3, lookup) == e.text


def test_the_scene_and_the_journal_show_this_weeks_text(c):
    e = _plain(c)
    game = Game.new(c, "沈青衫")
    game.state.world.jianfa_on = True
    game.narration = lambda season, week, eid: "改寫好的旁白，照樣是這一件事。" if eid == e.id else None
    lines = game._present(e)
    assert "改寫好的旁白，照樣是這一件事。" in lines
    assert "改寫好的旁白，照樣是這一件事。" in game._own_scene_text()


# ── 伺服器的背景一輪 ──

def echo(prompt: str) -> str:
    """假的改寫：把 user 訊息裡的原文抄回來，前面加兩個字。訊息是「標題（參考，不要寫進旁白）：…（換行）原文（N 字）：原文」，
    原文在第二行的第一個全角冒號之後（旁白的提示詞 2026-10-26 改過格式，這裡跟著改）。"""
    return "這時，" + prompt.split(chr(10), 1)[1].split("：", 1)[1]


class FakeClient:
    def __init__(self, reply):
        self.reply, self.calls = reply, 0
        self.timeout = 30

    def chat_text(self, messages, temperature=0.8, num_predict=120):
        self.calls += 1
        return self.reply(messages[-1]["content"])


class FakeWorld:
    def __init__(self, season, phase="running"):
        self.season, self.phase = season, phase

    def season_phase(self):
        return self.phase

    def get_season(self):
        return self.season

    def get_season_number(self):
        return 2


@pytest.fixture
def round_kit(monkeypatch, tmp_path):
    content = real_content()
    content.config.jianfa.enabled = True
    monkeypatch.setattr(server, "CONTENT", content)
    world = FakeWorld(_world(content))
    monkeypatch.setattr(server, "open_world", lambda: world)
    monkeypatch.setattr(server, "NARRATION", narration.NarrationStore(tmp_path / "n.sqlite"))
    monkeypatch.setattr(server, "QUEUE", None)
    monkeypatch.setattr(server, "within_budget", lambda client, left: client)
    return content, world


def test_a_round_rewrites_the_next_event_once(round_kit, monkeypatch):
    content, world = round_kit
    client = FakeClient(echo)
    monkeypatch.setattr(server, "NARRATION_CLIENT", client)
    first = narration.eligible(content)[0]
    assert server.narration_round() == first
    week = narration.period(content, world.season)
    assert server.NARRATION.get(2, week, first) == "這時，" + content.events[first].text
    second = server.narration_round()
    assert second == narration.eligible(content)[1] and client.calls == 2  # 寫過的不再寫


def test_a_bad_reply_is_tried_twice_then_left_as_written(round_kit, monkeypatch):
    content, world = round_kit
    client = FakeClient(lambda prompt: "壞了")
    monkeypatch.setattr(server, "NARRATION_CLIENT", client)
    first, second = narration.eligible(content)[:2]
    assert server.narration_round() is None and server.narration_round() is None
    assert client.calls == 2
    client.reply = echo
    assert server.narration_round() == second  # 第一則這一週照原文，換下一則
    assert server.NARRATION.get(2, narration.period(content, world.season), first) is None


def test_no_model_call_when_off_resting_or_saving_power(round_kit, monkeypatch):
    content, world = round_kit
    client = FakeClient(echo)
    monkeypatch.setattr(server, "NARRATION_CLIENT", client)
    world.phase = "resting"
    assert server.narration_round() is None
    world.phase = "running"
    world.season.jianfa_on = False
    assert server.narration_round() is None
    world.season.jianfa_on = True
    monkeypatch.setattr(server.power_save, "on", lambda: True)
    monkeypatch.setattr(server, "LAST_HUMAN", float("-inf"))
    assert server.narration_round() is None  # 省電模式、沒人在線：讓模型卸掉
    monkeypatch.setattr(server, "LAST_HUMAN", server.time.time())
    assert server.narration_round() is not None  # 有人在線就照寫
    assert client.calls == 1


def test_game_for_hands_the_lookup_to_each_game(tmp_path, monkeypatch):
    store = narration.NarrationStore(tmp_path / "n.sqlite")
    monkeypatch.setattr(server, "NARRATION", store)
    server.GAMES.clear()
    try:
        game = server.game_for("沈青衫")
        assert game.narration == store.get
    finally:
        server.GAMES.clear()


def test_the_store_keeps_the_first_text_and_drops_old_weeks(tmp_path):
    store = narration.NarrationStore(tmp_path / "n.sqlite")
    store.put(1, 1, "a", "甲")
    store.put(1, 1, "a", "乙")
    assert store.get(1, 1, "a") == "甲"  # 同一週大家看同一段
    store.put(1, 3, "b", "丙")
    assert store.get(1, 1, "a") is None and store.done(1, 3) == {"b"}  # 兩週以前的清掉
    store.put(2, 1, "c", "丁")
    assert store.done(1, 3) == set()  # 換季清掉上一季


def test_cleaning_markdown_keeps_the_underscores_inside_marks(c):
    """清 markdown 的那一步（拿掉 * _ ` #）不准動到 {marks:...} 裡的底線：標記的 id 多半帶底線
    （yingchuan_academy、zhuo_county……），吃掉之後跟原文比標記永遠不相等，改寫永遠退回原文。
    2026-10-26 主機整週實測抓到：241 則退回 25 則，其中 22 則是這樣來的，模型其實一字不差地照抄了標記。
    順便守住原本的用意：真的 markdown 強調符號還是要清掉。"""
    original = "前後有{marks:yingchuan_academy:密告}把壁上的字送了進去，郡吏堵在書院門口。"
    rewritten = "先前有{marks:yingchuan_academy:密告}將牆上的文字送入，郡吏封鎖了書院門口。"
    out = narration.clean(c, original, rewritten)
    assert out == rewritten  # 標記完整，過得了
    assert "{marks:yingchuan_academy:密告}" in out  # 底線沒被吃掉

    emphasised = "先前有{marks:yingchuan_academy:密告}將*牆上*的文字送入，郡吏封鎖了書院門口。"
    cleaned = narration.clean(c, original, emphasised)
    assert cleaned is not None and "*" not in cleaned  # 真的強調符號照樣清掉
    assert "{marks:yingchuan_academy:密告}" in cleaned
