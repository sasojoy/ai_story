"""名帖（tianxia/mingtie.py、mingtie_card.py；Joy 2026-10-19）與審一句話（speech.py）。"""
from __future__ import annotations

import random

from test_social import NOW, _as, _done, _player

from tianxia import mingtie, speech
from tianxia.engine import Game

DOT = [[0, 0, 10, 10, 60, 60]]


def _swap(content, a, b_name="乙"):
    a.peer_act(b_name, "mingtie", {"arg": "send"})
    _done(a)
    b = _as(content, a.world, b_name, NOW + 5)
    b.peer_act(a.state.player.name, "mingtie", {"arg": "yes"})
    _done(b)
    return _as(content, a.world, a.state.player.name, NOW + 6), b


def test_making_a_card_is_free_and_checked(content):
    a = _player(content, "甲")
    silver = a.state.player.stats.get("silver", 0)
    assert a.make_mingtie([], [], "") == [mingtie.EMPTY]
    assert a.make_mingtie([[9, 0, 1, 1, 2, 2]], [], "") == [mingtie.BAD_DRAWING]  # 沒有這種墨色
    assert a.make_mingtie([[0, 0, 1, 1, 999, 2]], [], "") == [mingtie.BAD_DRAWING]  # 出了畫布
    assert a.make_mingtie(DOT, ["天下第一"], "") == [mingtie.BAD_TITLE]  # 沒掙到的頭銜
    assert a.make_mingtie(DOT, [], "字" * 17) == [speech.TOO_LONG.format(n=16)]
    assert a.make_mingtie(DOT, [], "加我 line 好友") == [speech.BLOCKED]
    assert a.make_mingtie(DOT, [], "清風明月", verdict="bad") == [speech.BLOCKED]
    assert a.state.player.mingtie is None
    assert a.make_mingtie(DOT, [], "清風明月") == [mingtie.MADE]
    card = a.state.player.mingtie
    assert (card.strokes, card.motto, card.version) == (DOT, "清風明月", 1)
    assert a.state.player.stats.get("silver", 0) == silver


def test_titles_come_from_what_you_did(content):
    a = _player(content, "甲")
    a.state.player.top_merits = 2
    a.state.player.title_book = ["第1季 天下第一"]
    pool = mingtie.earned(a.state, content, a.world, {"名人": [("甲", (9,), "名望 9")]})
    assert "決戰首功二次" in pool and "第1季 天下第一" in pool and "名人榜第一" in pool
    assert a.make_mingtie([], ["決戰首功二次", "第1季 天下第一"], "") == [mingtie.MADE]
    assert a.make_mingtie([], ["名人榜第一"], "") == [mingtie.BAD_TITLE]  # 沒給榜單就沒有榜單的頭銜
    assert a.make_mingtie([], ["名人榜第一"], "", board={"名人": [("甲", (9,), "")]}) == [mingtie.MADE]


def test_only_so_many_finals_a_day(content):
    content.config.mingtie.made_per_day = 2
    a = _player(content, "甲")
    a.make_mingtie(DOT, [], "")
    a.make_mingtie(DOT, [], "一")
    assert a.make_mingtie(DOT, [], "二") == [mingtie.MADE_FULL.format(n=2)]
    a.sync(NOW + 24 * 3600)
    assert a.make_mingtie(DOT, [], "二") == [mingtie.MADE] and a.state.player.mingtie.version == 3


def test_you_need_a_card_to_hand_one_and_he_needs_one_to_answer(content):
    a = _player(content, "甲")
    _player(content, "乙")
    send = next(x for x in a.peer_card("乙")["actions"] if x["action"] == "mingtie")
    assert (send["label"], send["enabled"], send["note"]) == ("遞名帖", False, mingtie.NO_CARD)
    a.make_mingtie(DOT, [], "")
    assert a.peer_act("乙", "mingtie", {"arg": "send"}) == ["你遞上名帖，等乙回帖。"]
    assert a.peer_act("乙", "mingtie", {"arg": "send"}) == [mingtie.WAITING.format(him="他")]
    _done(a)
    b = _as(content, a.world, "乙", NOW + 5)
    [call] = b.calls_here()
    assert call["text"] == "甲遞上一張名帖，等你回帖。"
    assert [(o["label"], o["enabled"]) for o in call["options"]] == [("回帖", False), ("婉拒", True)]


def test_swapping_files_both_cards_and_a_second_swap_needs_a_new_card(content):
    a = _player(content, "甲")
    b = _player(content, "乙")
    b.make_mingtie(DOT, [], "乙的帖")
    _done(b)
    a.make_mingtie(DOT, [], "甲的帖")
    a, b = _swap(content, a)
    assert [(x.name, x.card.motto) for x in a.state.player.mingtie_box] == [("乙", "乙的帖")]
    assert [(x.name, x.card.motto) for x in b.state.player.mingtie_box] == [("甲", "甲的帖")]
    assert a.peer_act("乙", "mingtie", {"arg": "send"}) == [mingtie.SAME_CARD.format(him="他")]
    a.make_mingtie(DOT, [], "新帖")
    assert next(x for x in a.peer_card("乙")["actions"] if x["action"] == "mingtie")["label"] == "換新帖"
    a, b = _swap(content, a)
    assert [x.card.motto for x in b.state.player.mingtie_box] == ["新帖"]  # 同一個人只留最新的一張
    view = b.mingtie_view()
    assert view["box"][0]["name"] == "甲" and view["box"][0]["card"]["motto"] == "新帖"
    assert b.peer_card("甲")["mingtie"]["motto"] == "新帖"


def test_sends_a_day_are_capped(content):
    content.config.mingtie.send_per_day = 1
    a = _player(content, "甲")
    for name in ("乙", "丙"):
        _player(content, name)
    a.make_mingtie(DOT, [], "")
    a.peer_act("乙", "mingtie", {"arg": "send"})
    assert a.peer_act("丙", "mingtie", {"arg": "send"}) == [mingtie.SENT_FULL.format(n=1)]


def test_a_report_hides_it_for_you_and_enough_reports_hide_it_for_everyone(content):
    content.config.mingtie.report_hide = 2
    a = _player(content, "甲")
    a.make_mingtie(DOT, [], "壞話")
    _done(a)
    viewers = [_player(content, n) for n in ("乙", "丙", "丁")]
    b, c, d = viewers
    assert b.report_mingtie("甲", 1) == [mingtie.REPORTED]
    assert b.peer_card("甲")["mingtie"].get("hidden") is True and b.peer_card("甲")["mingtie"]["strokes"] == []
    assert c.peer_card("甲")["mingtie"]["strokes"] == DOT  # 一個人檢舉：只有他看不到
    assert c.report_mingtie("甲", 1) == [mingtie.REPORTED]
    assert d.peer_card("甲")["mingtie"].get("hidden") is True  # 兩個人：大家都看不到
    assert b.report_mingtie("甲", 7) == ["（找不到這張名帖。）"]


def test_admin_removes_or_restores_a_reported_card(content, monkeypatch):
    content.config.mingtie.report_hide = 1
    a = _player(content, "甲")
    a.make_mingtie(DOT, [], "壞話")
    _done(a)
    b = _player(content, "乙")
    b.report_mingtie("甲", 1)
    admin = _player(content, "管")
    monkeypatch.setattr(Game, "is_admin", lambda self: True)
    [row] = admin.admin_mingtie_reports()
    assert (row["name"], row["version"], row["count"], row["card"]["motto"]) == ("甲", 1, 1, "壞話")
    admin.admin_mingtie_restore("甲", 1)
    assert admin.admin_mingtie_reports() == []
    c = _player(content, "丙")
    assert c.peer_card("甲")["mingtie"]["motto"] == "壞話"  # 放回：檢舉再多也照畫
    admin.admin_mingtie_remove("甲", 1)
    a = _as(content, a.world, "甲", NOW + 5)
    card = a.state.player.mingtie
    assert (card.strokes, card.motto, card.version) == ([], "", 2)
    assert mingtie.REMOVED_LINE in [line for e in a.state.journal for line in e.lines]


def test_card_and_box_survive_a_new_season(content):
    a = _player(content, "甲")
    a.make_mingtie(DOT, [], "跨季")
    a.state.player.top_merits = 1
    a._reset_player_for_new_season(a.state.player.season_number + 1)
    p = a.state.player
    assert p.mingtie.motto == "跨季" and any(t.endswith("決戰首功一次") and t.startswith("第") for t in p.title_book)


def test_a_bot_makes_a_card_from_presets(content):
    from tianxia import bot_policy
    from tianxia.models import MingtieArt

    content.mingtie.arts = [MingtieArt(id="x", name="遠山", strokes=DOT)]
    content.mingtie.mottos = ["山高水長"]
    b = _player(content, "乙", bot=True)
    bot_policy.look_after(b, random.Random(0))
    card = b.state.player.mingtie
    assert card is not None and card.strokes[:1] == DOT and card.motto in ("", "山高水長")


def test_real_mottos_and_presets_pass_their_own_checks():
    from tianxia.content import load_content

    real = load_content("content")
    assert real.mingtie.arts and real.mingtie.mottos
    for art in real.mingtie.arts:
        assert mingtie.parse_strokes(art.strokes, real) == art.strokes, art.id
    for line in real.mingtie.mottos:
        assert speech.word_problem(line, real, speech.MOTTO, real.config.mingtie.motto_max) is None, line


def test_speech_catches_spaced_out_words(content):
    content.banned_words = ["白癡"]
    assert speech.word_problem("白 ．癡", content, speech.TAUNT, 20) == speech.BLOCKED
    assert speech.word_problem("你這三腳貓", content, speech.TAUNT, 20) is None
    assert speech.word_problem("電話0912345678", content, speech.MOTTO, 16) == speech.BLOCKED
    assert speech.word_problem("電話0912345678", content, speech.TAUNT, 20) is None


def test_speech_judge_reads_the_model_and_falls_back_to_the_word_list():
    class Fake:
        def __init__(self, ok):
            self.ok = ok

        def chat_structured(self, messages, schema, **kw):
            if self.ok is None:
                raise RuntimeError("down")
            return schema(ok=self.ok)

    assert speech.judge(Fake(True), "嗨", speech.TAUNT) == "ok"
    assert speech.judge(Fake(False), "嗨", speech.TAUNT) == "bad"
    assert speech.judge(Fake(None), "嗨", speech.TAUNT) == ""
    assert speech.judge(None, "嗨", speech.TAUNT) == ""
