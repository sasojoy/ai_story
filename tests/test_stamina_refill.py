"""測試期間一鍵補滿體力（企劃者 2026-10-07，緊急）：
「體力在這個遊戲是很重要的資源，現在的回復以及消耗完全不成正比，探索偶爾還順便扣一堆體力，新人玩家體驗不到樂趣。
另外現在還在測試版，請直接讓玩家能直接補滿體力。」

做法：掛在 joy 的回體丹（PR #32）上，同一個入口（Game.take_stamina_pill）、同一顆鈕（狀態列體力條上那顆，路由 pill）；
Config.beta_free_refill 打開時按下去直接補滿、不花丹、不花銀兩、不限次數；關著時 joy 的丹一個字不變（test_stamina_pill.py 照舊）。
假人與整季機器人不吃這個：bot.take_pill 走 pill_only=True。"""
from __future__ import annotations

import copy
import random

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_prologue_web import run

import server
import webharness
from conftest import real_content
from tianxia import bot, bot_policy, engine, journal, skillview
from tianxia.content import load_content
from tianxia.engine import Game
from tianxia.models import Config
from tianxia.state import BotProfile

needs_node = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
LABEL = "補滿"  # 鈕上的字（Config.beta_free_refill_label 的預設，待 joy 潤）


def refill_on(game: Game) -> Game:
    game.content.config.beta_free_refill = True
    return game


def cap(game: Game) -> int:
    return game.content.config.stamina_max


# ── 開關 ──────────────────────────────────────────────


def test_the_switch_is_off_by_default_and_only_the_weekend_profile_turns_it_on():
    assert Config().beta_free_refill is False and Config().beta_free_refill_label == LABEL
    assert real_content().config.beta_free_refill is False  # content/config.json 不寫它
    assert real_content("weekend").config.beta_free_refill is True


def test_the_button_label_cannot_be_empty():
    """空字串的話網頁會退回畫「丹 N」（label 是假值），引擎卻照樣補滿：鈕上寫的跟按下去的對不上。載入時就擋。"""
    with pytest.raises(ValidationError, match="at least 1 character"):
        Config(beta_free_refill_label="")
    assert Config(beta_free_refill_label="滿").beta_free_refill_label == "滿"


# ── 開關打開：補滿 ──────────────────────────────────────


def test_a_press_fills_stamina_to_the_top_for_free(game):
    refill_on(game)
    p = game.state.player
    p.stamina = 37.0
    silver = p.stats["silver"]
    msgs = game.take_stamina_pill()
    assert p.stamina == cap(game) == game.status_data()["stamina_max"]
    assert p.stamina_pills == 20  # 丹的數量不動
    assert p.stats["silver"] == silver  # 不花銀兩
    assert msgs[0] == engine.REFILL_LINE
    assert msgs[-1] == f"體力 +{cap(game) - 37}"


def test_a_press_writes_one_journal_line(game):
    refill_on(game)
    game.state.player.stamina = 37.0
    game.state.world.time = 4321.0  # 不是 0：紀錄的時間要是世界時間（引擎不讀電腦時鐘），讀牆上時鐘或寫死 0 都會露餡
    before = len(game.state.journal)
    game.take_stamina_pill()
    assert len(game.state.journal) == before + 1
    entry = game.state.journal[0]  # 新的在最前面
    assert (entry.title, entry.lines, entry.changes) == (
        engine.REFILL_TITLE, [engine.REFILL_LINE], [f"體力 +{cap(game) - 37}"],
    )
    assert entry.time == game.state.world.time == 4321.0


def test_the_gain_matches_what_the_bar_moves(game):
    """「體力 +N」照狀態列的算法（int，不進位）：體力有小數是常態（每 3 分鐘回 1 點、一路累積），不能寫 +0 而條子明明動了，
    也不能寫 +112 而條子從 37 走到頂是 +113。"""
    refill_on(game)
    p = game.state.player
    for stamina in (149.97, 37.6, 0.4):
        p.stamina = stamina
        bar_before = game.status_data()["stamina"]
        msgs = game.take_stamina_pill()
        moved = game.status_data()["stamina"] - bar_before
        assert moved == cap(game) - int(stamina) >= 1, stamina
        assert msgs[-1] == f"體力 +{moved}" and game.state.journal[0].changes == [f"體力 +{moved}"], stamina


def test_the_refill_goes_into_the_action_log(game):
    """成功、體力已滿、序章的拒絕都要經過 _log（GameState.log：工具列與「剛剛」讀它，戰況變化的換字也在那裡）。"""
    refill_on(game)
    p = game.state.player
    p.stamina = 37.0
    game.take_stamina_pill()
    assert game.state.log[-3:] == [engine.REFILL_LINE, f"體力 +{cap(game) - 37}", journal.LOG_BREAK]
    game.take_stamina_pill()
    assert game.state.log[-2:] == [engine.REFILL_FULL, journal.LOG_BREAK]


def test_it_works_with_no_pills_at_all(game):
    refill_on(game)
    p = game.state.player
    p.stamina, p.stamina_pills = 0.0, 0
    game.take_stamina_pill()
    assert p.stamina == cap(game) and p.stamina_pills == 0


def test_it_fills_to_the_same_top_the_status_bar_shows(game):
    """上限一律是設定的 stamina_max（狀態列顯示的那個），不是寫死的 150。"""
    refill_on(game)
    game.content.config.stamina_max = 120
    p = game.state.player
    p.stamina = 10.0
    game.take_stamina_pill()
    status = game.status_data()
    assert p.stamina == 120 and (status["stamina"], status["stamina_max"]) == (120, 120)


def test_a_second_press_at_the_top_is_refused_and_costs_nothing(game):
    refill_on(game)
    p = game.state.player
    p.stamina = 20.0
    game.take_stamina_pill()
    journal_len = len(game.state.journal)
    assert game.take_stamina_pill() == [engine.REFILL_FULL]  # 跟丹一樣：滿的就拒絕，只回一句話
    assert p.stamina == cap(game) and p.stamina_pills == 20
    assert len(game.state.journal) == journal_len  # 拒絕不寫紀錄


def test_there_is_no_limit_on_how_many_times_it_can_be_pressed(game):
    refill_on(game)
    p = game.state.player
    for _ in range(30):  # 比開局送的 20 顆丹還多
        p.stamina = 5.0
        game.take_stamina_pill()
        assert p.stamina == cap(game)
    assert p.stamina_pills == 20
    assert sum(e.title == engine.REFILL_TITLE for e in game.state.journal) == 30


def test_the_hut_keeps_its_own_stamina_plan_with_the_switch_on_too(prologue_content):
    """序章的體力是照步驟算好的：跟丹一樣，序章裡不能補、狀態列不畫鈕。"""
    prologue_content.config.beta_free_refill = True
    game = Game.new(prologue_content, "沈浪", rng=random.Random(0), prologue=True)
    p = game.state.player
    p.stamina = 0.0
    before = len(game.state.journal)
    msgs = game.take_stamina_pill()
    assert msgs == [engine.REFILL_HUT] and p.stamina == 0 and len(game.state.journal) == before
    assert game.state.log[-2:] == [engine.REFILL_HUT, journal.LOG_BREAK]
    assert game.status_data()["pills"] is None


def test_nothing_is_refilled_while_the_season_is_preparing(content, world):
    content.config.auto_open_first_season = False
    content.config.beta_free_refill = True
    game = Game.new(content, "甲", rng=random.Random(1), world=world)
    game.state.player.stamina = 5.0
    assert game.take_stamina_pill() == [engine.PREPARING_REFUSAL]
    assert game.state.player.stamina == 5


# ── 打坐、閉關、在路上：跟丹一模一樣 ──────────────────────

SITUATIONS = {
    "resting": lambda g: g.choose("act:rest"),
    "seclusion": lambda g: g.seclude(2),
    "on the road": lambda g: g.choose("move:lake"),
}


def marks(game: Game) -> tuple[bool, bool, bool]:
    p = game.state.player
    return p.resting_since is not None, p.busy_until is not None, p.journey is not None


def press_in(content, situation: str, free: bool):
    content = copy.deepcopy(content)
    content.config.beta_free_refill = free
    game = Game.new(content, f"甲{int(free)}", rng=random.Random(0))
    SITUATIONS[situation](game)
    game.state.player.stamina = 20.0
    before = marks(game)
    assert any(before), situation  # 真的進了那個狀態
    msgs = game.take_stamina_pill()
    return game, before, msgs


@pytest.mark.parametrize("situation", list(SITUATIONS))
def test_the_refill_allows_and_refuses_exactly_what_the_pill_does(content, situation):
    """丹在打坐、閉關、在路上都吃得了、只加體力、不動那個狀態；補滿一樣：照做、不動狀態（不多拒絕、也不多放行）。"""
    pill_game, pill_before, _ = press_in(content, situation, free=False)
    free_game, free_before, _ = press_in(content, situation, free=True)
    restore = pill_game.content.config.stamina_pill_restore
    assert pill_game.state.player.stamina == min(cap(pill_game), 20 + restore)  # 丹：+restore，吃得了
    assert free_game.state.player.stamina == cap(free_game)  # 補滿：照做
    assert marks(pill_game) == pill_before and marks(free_game) == free_before == pill_before  # 狀態都沒被動
    assert pill_game.state.player.stamina_pills == 19 and free_game.state.player.stamina_pills == 20


def test_resting_ends_at_the_next_sync_once_stamina_is_full(content):
    """打坐中補滿：跟丹把體力補到頂一樣，不當場起身；下一次同步（輪詢每 10 秒一次）看到體力滿了才收功起身。"""
    content = copy.deepcopy(content)
    content.config.beta_free_refill = True
    game = Game.new(content, "甲", rng=random.Random(0))
    game.sync(1000.0)
    game.choose("act:rest")
    game.state.player.stamina = 20.0
    game.take_stamina_pill()
    assert game.state.player.resting_since is not None
    game.sync(1001.0)
    assert game.state.player.resting_since is None and game.state.player.stamina == cap(game)


# ── 開關關著：joy 的丹一個字不變 ────────────────────────


def test_with_the_switch_off_a_press_still_eats_a_pill_and_restores_a_hundred(game):
    assert game.content.config.beta_free_refill is False
    p = game.state.player
    p.stamina = 37.0
    restore = game.content.config.stamina_pill_restore
    msgs = game.take_stamina_pill()
    assert p.stamina == min(cap(game), 37 + restore) and p.stamina_pills == 19
    assert msgs == [
        "你服下一顆回體丹，一股暖意自丹田散開，精神為之一振。", f"體力 +{round(p.stamina - 37)}（回體丹還剩 19 顆）",
    ]
    assert game.state.journal[0].title == "服下回體丹"


def test_with_the_switch_off_and_no_pills_there_is_nothing_to_press(game):
    p = game.state.player
    p.stamina, p.stamina_pills = 5.0, 0
    assert game.status_data()["pills"] is None
    assert game.take_stamina_pill() == ["你身上沒有回體丹了。"] and p.stamina == 5


def test_the_status_payload_is_unchanged_with_the_switch_off(game):
    """關著時 status 的 pills 一個鍵都沒多：跟 joy 的測試寫的同一份。"""
    game.state.player.stamina = 40.0
    restore = game.content.config.stamina_pill_restore
    assert game.status_data()["pills"] == {"name": "回體丹", "count": 20, "restore": restore, "full": False}


# ── 狀態列與背包 ──────────────────────────────────────


def test_the_status_bar_offers_the_refill_even_with_no_pills(game):
    refill_on(game)
    p = game.state.player
    p.stamina, p.stamina_pills = 40.0, 0
    assert game.status_data()["pills"] == {
        "name": "回體丹", "count": 0, "restore": game.content.config.stamina_pill_restore, "full": False, "refill": LABEL,
    }
    p.stamina = float(cap(game))
    assert game.status_data()["pills"]["full"] is True


def test_the_bag_still_lists_the_pills_but_stops_calling_them_the_button(game):
    """背包照列丹（數量沒動）；開關打開時狀態列那顆鈕叫「補滿」、不花丹，背包不能還叫人按「服丹」。"""
    assert "服丹" in skillview.bag_text(game.state, game.content)  # 關著：照舊
    refill_on(game)
    text = skillview.bag_text(game.state, game.content)
    assert "回體丹 ×20" in text and "服丹" not in text and f"「{LABEL}」" in text


# ── 假人與整季機器人：照舊吃丹 ──────────────────────────


def test_the_bot_takes_a_pill_not_the_free_refill(game):
    refill_on(game)
    p = game.state.player
    p.stamina = 0.0
    bot.take_pill(game)
    restore = game.content.config.stamina_pill_restore
    assert p.stamina == restore < cap(game) and p.stamina_pills == 19  # 丹：+restore、少一顆；不是補滿


def test_the_bot_with_no_pills_does_not_get_the_refill(game):
    refill_on(game)
    p = game.state.player
    p.stamina, p.stamina_pills = 0.0, 0
    bot.take_pill(game)
    assert p.stamina == 0


def test_a_server_bot_turn_takes_a_pill_not_the_free_refill(content, game):
    refill_on(game)
    p = game.state.player
    p.stamina = 0.0
    bot_policy.take_turn(game, BotProfile(personality="普通", seed=1, faction=None, season_number=1), random.Random(0))
    assert p.stamina_pills == 19  # 吃了一顆
    assert p.stamina < cap(game)  # 沒有補滿


def test_a_server_bot_with_no_pills_stays_dry(game):
    refill_on(game)
    p = game.state.player
    p.stamina, p.stamina_pills = 0.0, 0
    bot_policy.take_turn(game, BotProfile(personality="普通", seed=1, faction=None, season_number=1), random.Random(0))
    assert p.stamina < 10  # 沒有補滿（走路不花體力，頂多自然回一點）


# ── 網頁（node 假瀏覽器） ──────────────────────────────


@needs_node
def test_the_page_shows_the_refill_button_with_no_pills(game):
    refill_on(game)
    game.state.player.stamina, game.state.player.stamina_pills = 40.0, 0
    top = run(server.main_view(game), "return H.topHtml();")
    assert 'data-act="pill"' in top and f">{LABEL}</button>" in top
    assert "丹0" not in top and "disabled" not in top.split('data-act="pill"')[1].split(">")[0]
    # 給輔助科技讀的那句也走補滿的那一支：寫補滿、寫免費，不是 joy 的「服下回體丹（剩 N 顆…）」
    assert f'aria-label="{LABEL}體力（測試期間免費，不花回體丹）"' in top and "服下回體丹（剩" not in top


@needs_node
def test_the_button_is_grey_when_stamina_is_full_and_says_refill_not_a_count(game):
    refill_on(game)
    game.state.player.stamina = float(cap(game))
    top = run(server.main_view(game), "return H.topHtml();")
    button = top[top.index('<button class="pill-btn"'):top.index("</button>", top.index('<button class="pill-btn"'))]
    assert "disabled" in button and f">{LABEL}" in button and "丹20" not in button


@needs_node
def test_with_the_switch_off_the_button_is_joys_pill_button_and_vanishes_at_zero(game):
    game.state.player.stamina = 40.0
    top = run(server.main_view(game), "return H.topHtml();")
    assert 'data-act="pill"' in top and ">丹20</button>" in top and LABEL not in top
    restore = game.content.config.stamina_pill_restore
    assert f'aria-label="服下回體丹（剩 20 顆，回 {restore} 點體力）"' in top  # joy 的那一句，一個字不差
    game.state.player.stamina_pills = 0
    top = run(server.main_view(game), "return H.topHtml();")
    assert "pill-btn" not in top and 'data-act="pill"' not in top


@needs_node
def test_clicking_the_refill_button_posts_to_the_same_route_as_the_pill(game):
    refill_on(game)
    game.state.player.stamina = 40.0
    before = server.main_view(game)
    game.take_stamina_pill()
    after = server.main_view(game)
    script = """return (async () => {
      const el = { dataset: { act: "pill" }, classList: { contains: () => false } };
      await T.docListeners.click[0]({ target: { closest: () => el } });
      return { calls: T.calls.map((c) => c[0]), stamina: H.S.main.status.stamina };
    })();"""
    out = run(before, script, responses={"/api/do/pill": {"main": after, "message": ""}})
    assert out == {"calls": ["/api/do/pill"], "stamina": cap(game)}


# ── 伺服器：週末設定 ──────────────────────────────────


def test_the_pill_route_refills_to_the_top_under_the_weekend_profile(monkeypatch):
    from tianxia.characters import open_characters  # noqa: PLC0415

    weekend = load_content(server.ROOT / "content", profile="weekend")
    weekend.config.auto_open_first_season = True
    monkeypatch.setattr(server, "CONTENT", weekend)
    assert weekend.config.beta_free_refill is True
    client = TestClient(server.app)
    client.post("/api/register", json={"login": "refill_01", "password": "secret-pw", "again": "secret-pw"})
    client.post("/api/character", json={"name": "補滿人"})
    client.post("/api/do/skip_tutorial", json={})
    game = server.game_for("補滿人")
    game.state.player.stamina = 5.0
    game.state.player.stamina_pills = 0  # 沒有丹也補得滿
    open_characters().save(game.state)
    r = client.post("/api/do/pill", json={}).json()
    status = r["main"]["status"]
    top = weekend.config.stamina_max
    assert status["stamina"] == status["stamina_max"] == top, r["message"]
    assert status["pills"]["refill"] == LABEL and status["pills"]["count"] == 0
    saved = open_characters().load("補滿人").player
    assert saved.stamina >= top and saved.stamina_pills == 0
    again = client.post("/api/do/pill", json={}).json()  # 再按一次：滿的，只回一句話、不出錯
    assert engine.REFILL_FULL in again["message"]  # 伺服器把引擎的 Markdown 轉成 HTML
