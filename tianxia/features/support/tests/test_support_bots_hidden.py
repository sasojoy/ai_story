"""看不出誰是假人（帳號與客服第 211 批）：單裡寫到假人的名號、真人的名號、不存在的名號，回話逐字一樣（名號一律不收、不查）；
假人沒有帳號，/api/main 那一格的樣子跟沒有回覆的真人一樣（只有 support_unread: 0），不出錯也不多鍵。"""
from __future__ import annotations

import pytest
import server
from server_kit import (  # noqa: F401
    _no_landing, _no_preset_recipes, cheap_password_hashing, fresh_server_memory, model_breaker_closed, save_dir, scheduler_off,
    season_already_open,
)
from support_kit import player, staffer, support_isolated, support_on, ticket  # noqa: F401

from tianxia.characters import open_characters
from tianxia.engine import Game
from tianxia.features.support import notes
from tianxia.state import BotProfile

pytestmark = [pytest.mark.whole_content, pytest.mark.usefixtures("support_on")]

BOT = "莫問天"


def _bot() -> Game:
    game = Game.new(server.CONTENT, BOT)
    game.state.player.bot = BotProfile(personality="普通", seed=7)
    open_characters().save(game.state)
    return game


def _shape(reply) -> tuple:
    data = reply.json()
    data.pop("id", None)
    for t in data.get("mine", {}).get("tickets", []):
        for k in ("id", "body", "created", "updated"):
            t.pop(k, None)
    return reply.status_code, data


def test_tickets_naming_a_bot_a_player_or_nobody_read_the_same():
    _bot()
    player("li_02", "李白衣")
    shapes = []
    for i, name in enumerate((BOT, "李白衣", "無此人")):
        c = player(f"p_{i:02d}", f"路人{i}")
        shapes.append(_shape(ticket(c, body=f"{name}搶了我的東西")))
    assert shapes[0] == shapes[1] == shapes[2]
    assert shapes[0][0] == 200


def test_staff_view_of_a_ticket_has_no_bot_marks(monkeypatch):
    _bot()
    c = player()
    s = staffer(monkeypatch)
    tid = ticket(c, body=f"{BOT}是不是假的").json()["id"]
    text = s.get(f"/api/support/ticket/{tid}").text + s.get("/api/support/queue").text
    for word in ("假人", "機器人", '"bot"', "bot_"):
        assert word not in text


def test_main_slot_for_a_bot_is_the_same_as_a_fresh_player():
    bot = _bot()
    player()
    real = Game(server.CONTENT, open_characters().load("沈青衫"))
    assert notes.main_slot(bot) == notes.main_slot(real) == {"support_unread": 0}
