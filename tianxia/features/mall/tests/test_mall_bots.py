"""商城第三批：假人這一版不買（設計 4.8），而且別人看得到的地方都沒有元寶、購買的字樣，看不出誰是假人。

- 假人照樣拿封測發放（第一批 test_mall.py 的 test_bots_get_the_same_grant），但從不叫 Game.mall_buy：帳上只有發放、沒有購買紀錄。
- 一個真人買了月卡與回體丹、一個假人只拿了發放：第三個人看到的「此地還有」、兩張玩家卡、傳聞、江湖史、大事、榜單，與兩人的戰報、
  行狀（會寫進公開的傳）都沒有元寶、商城、月卡、購買這類字，兩張玩家卡的鍵一樣。
- 假人程式的主控台輸出（run_bots）不寫元寶、商城。"""
from __future__ import annotations

import json
import random

import pytest
from test_bot_runner import START, _install
from test_social import NOW, _done, _player

import run_bots
from tianxia import leaderboard, server_bots
from tianxia.bot_runner import BotRunner
from tianxia.characters import name_key, open_characters
from tianxia.engine import Game
from tianxia.models import MallItem
from tianxia.sqlite_world import open_world
from tianxia.wallet import Wallet

WORDS = ("元寶", "商城", "萬寶閣", "月卡", "購買", "買下", "儲值", "封測發放")


@pytest.fixture
def on(content):
    m = content.config.mall
    m.enabled, m.beta_grant = True, 5000
    content.mall = {i.id: i for i in (
        MallItem(id="pills_5", name="回體丹五顆", price=100, kind="consumable", effects={"pills": 5}),
        MallItem(id="card_30", name="月卡", price=600, kind="card", effects={"card_days": 30}),
    )}
    content.config.stamina_pills_per_day = 2
    content.config.newbie_pills_per_day = 5
    return content


def _no_mall_words(seen: object) -> list[str]:
    text = json.dumps(seen, ensure_ascii=False, default=str)
    return [word for word in WORDS if word in text]


def test_online_bots_take_the_grant_but_never_buy(on, monkeypatch):
    """假人在線、每一輪都動：每個假人照樣拿到封測發放，一次都沒叫 mall_buy，帳上只有發放、沒有購買紀錄。"""
    world = open_world()
    world.seed_first_season(on)
    _install(on)
    clock = [START]
    runner = BotRunner(on, world, open_characters(), random.Random(1), clock=lambda: clock[0])
    monkeypatch.setattr(server_bots, "is_online", lambda profile, now: True)
    on.config.bots_min_per_faction = 1
    on.config.bot_tick_seconds = 1000  # 在線就一定做一個動作
    calls: list[str] = []
    real_buy = Game.mall_buy

    def watched(self, item_id, ref):
        calls.append(self.state.player.name)
        return real_buy(self, item_id, ref)

    monkeypatch.setattr(Game, "mall_buy", watched)
    acted = 0
    for _ in range(25):
        report = runner.tick()
        assert report.failed == 0
        acted += report.acted
        clock[0] += 120
    bots = open_characters().all(bots_only=True)
    assert len(bots) == 2 and acted >= 40
    assert calls == []
    with world.db.snapshot() as conn:
        assert conn.execute("SELECT COUNT(*) FROM mall_purchases").fetchone()[0] == 0
        rows = sorted(tuple(r) for r in conn.execute("SELECT owner, reason, delta FROM mall_ledger"))
    assert rows == sorted((name_key(s.player.name), "grant", 5000) for s in bots)


@pytest.mark.smoke
def test_what_others_see_says_nothing_about_the_mall(on):
    """真人買了月卡與回體丹、假人只拿了發放：第三個人看得到的東西都沒有商城的字樣，兩張玩家卡長得一樣。"""
    buyer = _player(on, "沈浪", save=False)
    buyer.mark_seen(NOW)
    assert buyer.mall_buy("card_30", "card-ref-0001") and buyer.mall_bought == "card_30"
    assert buyer.mall_buy("pills_5", "pill-ref-0001") and buyer.mall_bought == "pills_5"
    _done(buyer)
    bot = _player(on, "某假人", bot=True, save=False)
    bot.own_turn_checks()
    _done(bot)
    wallet = Wallet(buyer.world.db)
    assert len(wallet.purchases("沈浪")) == 2 and wallet.purchases("某假人") == []
    assert wallet.balance("某假人") == 5000
    viewer = _player(on, "旁人")
    here = viewer.peers_here()
    assert {p["name"] for p in here} == {"沈浪", "某假人"}
    real_card, bot_card = viewer.peer_card("沈浪"), viewer.peer_card("某假人")
    assert real_card is not None and bot_card is not None
    assert set(real_card) == set(bot_card)
    seen = {
        "here": here, "cards": [real_card, bot_card],
        "rumors": viewer.rumors_text(), "chronicle": viewer.chronicle_text(), "bulletin": viewer.bulletin(),
        "trends": viewer.trends_text(), "boards": leaderboard.compute_boards(on, viewer.world, top=None),
        "battles": [r.model_dump() for g in (buyer, bot) for r in g.state.battles],
        "annals": [a.model_dump() for g in (buyer, bot) for a in g.state.player.annals],
    }
    assert _no_mall_words(seen) == []


def test_the_bot_console_never_mentions_the_mall(monkeypatch, capsys):
    """假人程式的主控台輸出（啟動與每一輪那一行）只寫數字，商城開著的設定（week7）也不寫元寶、商城。"""
    monkeypatch.setattr(run_bots.time, "sleep", lambda seconds: None)
    monkeypatch.setenv("TIANXIA_PROFILE", "week7")
    run_bots.main(ticks=2)
    out = capsys.readouterr().out
    assert "設定：week7" in out
    assert _no_mall_words(out) == []
