"""帖友書信（tianxia/features/mail/；設計稿 https://claude.ai/artifact/FhMZSwH6aqNsrnNAwHBznn，Joy 2026-11-07）：
交換過名帖才寫得了、一天幾封與連寫幾封、不收他的信（他不知道）、檢舉與管理者、假人照樣收、易名帖、兩季以前的封存、沒有已讀。"""
from __future__ import annotations

import random

import pytest

from tianxia.characters import CharacterStore
from tianxia.engine import Game
from tianxia.features.mail import actions, store as mail_store
from tianxia.state import BotProfile, Mingtie, MingtieCopy

NOW = 1_000_000.0


def _player(content, name, *, bot=False):
    game = Game.new(content, name, rng=random.Random(0))
    game.sync(NOW)
    if bot:
        game.state.player.bot = BotProfile(personality="普通", seed=1)
    game.state.player.mingtie = Mingtie(titles=[], motto="", version=1)
    CharacterStore(game.world.db).save(game.state)
    return game


def _swap(a, b):
    """兩人互換名帖（名帖匣各收一張；規則在 peers 包，這裡直接擺）。"""
    for me, them in ((a, b), (b, a)):
        me.state.player.mingtie_box.append(MingtieCopy(name=them.state.player.name, card=them.state.player.mingtie, when="", place="", season=1))
        CharacterStore(me.world.db).save(me.state)


@pytest.fixture
def mail(content):
    content.config.mail.enabled = True
    return content


def _pair(content, b_bot=False):
    a, b = _player(content, "甲"), _player(content, "乙", bot=b_bot)
    _swap(a, b)
    return a, b


@pytest.mark.smoke
def test_friends_write_and_the_other_sees_it_unread_then_read(mail):
    a, b = _pair(mail)
    ok, line = actions.send(a, "乙", "那天在宛城換帖，\n\n\n還沒謝你。")
    assert ok and line == actions.SENT.format(name="乙")
    assert actions.status(b) == {"mail": {"unread": 1}} and actions.status(a) == {"mail": {"unread": 0}}
    rows = actions.inbox(b)["threads"]
    assert [(r["name"], r["unread"], r["mine"]) for r in rows] == [("甲", 1, False)]
    t = actions.thread(b, "甲")
    assert [x["text"] for x in t["letters"]] == ["那天在宛城換帖，\n\n還沒謝你。"] and not t["letters"][0]["mine"]
    assert actions.status(b) == {"mail": {"unread": 0}}  # 打開就算看過
    mine = actions.thread(a, "乙")["letters"][0]
    assert mine["mine"] and "read" not in mine  # 沒有已讀


def test_only_people_who_swapped_cards_can_write(mail):
    a, b = _player(mail, "甲"), _player(mail, "乙")
    assert actions.send(a, "乙", "你好")[1] == actions.NOT_FRIENDS.format(name="乙")
    a.state.player.mingtie_box.append(MingtieCopy(name="乙", card=b.state.player.mingtie, when="", place="", season=1))
    assert actions.send(a, "乙", "你好")[1] == actions.NOT_FRIENDS.format(name="乙")  # 只有你收著他的：他那邊也要收著你的
    assert actions.send(a, "甲", "你好")[1] == actions.SELF
    assert actions.inbox(a)["friends"] == ["乙"]  # 名帖匣裡的人列成帖友


def test_a_day_cap_and_waiting_for_a_reply(mail):
    mail.config.mail.unanswered = 2
    mail.config.mail.per_day = 3
    a, b = _pair(mail)
    c = _player(mail, "丙")
    _swap(a, c)
    assert actions.send(a, "乙", "一")[0] and actions.send(a, "乙", "二")[0]
    assert actions.send(a, "乙", "三")[1] == actions.WAIT_REPLY.format(n=2, name="乙")
    assert actions.send(b, "甲", "回")[0]  # 他回了一封：重算
    assert actions.send(a, "乙", "三")[0]
    assert actions.send(a, "丙", "四")[1] == actions.DAY_FULL.format(n=3)
    assert actions.inbox(a)["left"] == 0


def test_blocking_drops_his_letters_silently(mail):
    a, b = _pair(mail)
    actions.set_block(b, "甲", True)
    ok, line = actions.send(a, "乙", "收得到嗎")
    assert ok and line == actions.SENT.format(name="乙")  # 他照常看到寄出去了
    assert [x["text"] for x in actions.thread(a, "乙")["letters"]] == ["收得到嗎"]
    assert actions.status(b)["mail"]["unread"] == 0 and actions.thread(b, "甲")["letters"] == []
    assert actions.inbox(b)["blocked"] == ["甲"]
    actions.set_block(b, "甲", False)
    assert actions.thread(b, "甲")["letters"] == []  # 不補
    assert actions.send(a, "乙", "這封呢")[0] and actions.status(b)["mail"]["unread"] == 1


def test_report_hides_it_and_the_admin_removes_or_mutes(mail, monkeypatch):
    a, b = _pair(mail)
    actions.send(a, "乙", "不好聽的話")
    lid = actions.thread(b, "甲")["letters"][0]["id"]
    assert actions.report(a, lid) == actions.NO_LETTER  # 只能檢舉寄給你的
    assert actions.report(b, lid) == actions.REPORTED
    assert actions.thread(b, "甲")["letters"] == []
    admin = _player(mail, "管")
    monkeypatch.setattr(Game, "is_admin", lambda self: self.state.player.name == "管")
    [row] = actions.admin_reports(admin)
    assert (row["sender"], row["recipient"], row["text"], row["count"]) == ("甲", "乙", "不好聽的話", 1)
    assert actions.admin_reports(a) == []  # 不是管理者看不到
    actions.admin_settle(admin, lid, True)
    assert actions.admin_reports(admin) == [] and actions.thread(a, "乙")["letters"] == []  # 撤下：兩邊都看不到
    assert actions.admin_mute(admin, "甲", 2)[0].startswith("（停寄只能挑")
    actions.admin_mute(admin, "甲", 3)
    a.now = admin.now
    assert actions.send(a, "乙", "再寫")[1] == actions.MUTED.format(h=72)
    actions.admin_mute(admin, "甲", 0)
    assert actions.send(a, "乙", "再寫")[0]


def test_a_bot_receives_letters_exactly_like_a_person(mail):
    a, b = _pair(mail, b_bot=True)
    c = _player(mail, "丙")
    _swap(a, c)
    assert actions.send(a, "乙", "在嗎") == (True, actions.SENT.format(name="乙"))
    assert actions.send(a, "丙", "在嗎") == (True, actions.SENT.format(name="丙"))
    assert actions.thread(a, "乙").keys() == actions.thread(a, "丙").keys()
    assert actions.status(b) == {"mail": {"unread": 1}}


def test_words_are_screened_but_contact_details_are_fine(mail):
    mail.banned_words = ["王八"]
    a, b = _pair(mail)
    assert not actions.send(a, "乙", "你這王八")[0]
    assert actions.send(a, "乙", "加我 line：tianxia123，電話 0912345678，www.example.com")[0]  # Joy 11/7「不擋」
    assert not actions.send(a, "乙", "好話", verdict="bad")[0]  # 模型說擋就擋
    assert actions.send(a, "乙", "字" * (mail.config.mail.max_chars + 1))[1] == "最多 200 個字。"
    assert actions.send(a, "乙", "   ")[1] == actions.EMPTY


def test_a_rename_keeps_the_letters(mail):
    a, b = _pair(mail)
    actions.send(a, "乙", "老友")
    a.world.rename_character("甲", "甲二")
    b.state = CharacterStore(b.world.db).load("乙")
    rows = actions.inbox(b)["threads"]
    assert [r["name"] for r in rows] == ["甲二"]


def test_letters_two_seasons_old_move_to_the_archive_and_still_read(tmp_path):
    box = mail_store.MailStore(tmp_path / "x-mail.sqlite")
    put = lambda season, text: box.add(season=season, at=0.0, day=1, stamp="", place="", sender="甲", recipient="乙", text=text, dropped=False, keep=200)
    for i in range(3):
        put(1, f"第一季{i}")
    put(3, "第三季")
    assert box.archive_path.is_file()
    rows, more = box.page("乙", "甲", limit=2)
    assert [r["text"] for r in rows] == ["第三季", "第一季2"] and more
    rows, more = box.page("乙", "甲", before=rows[-1]["id"], limit=5)
    assert [r["text"] for r in rows] == ["第一季1", "第一季0"] and not more


def test_a_pair_keeps_only_the_latest_letters(tmp_path):
    box = mail_store.MailStore(tmp_path / "y-mail.sqlite")
    for i in range(5):
        box.add(season=1, at=0.0, day=1, stamp="", place="", sender="甲" if i % 2 else "乙", recipient="乙" if i % 2 else "甲",
                text=str(i), dropped=False, keep=3)
    assert [r["text"] for r in box.page("甲", "乙")[0]] == ["4", "3", "2"]
