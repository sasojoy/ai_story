"""正式季整合第 7 批：江湖頁最上面那一排小標多一個「簽到」（設計 9.1 第 4 組丙）。還沒簽亮紅點，簽了寫「簽到 ✔」；攤開是這一週
七格、今天的份與領的鈕，四階的日子是四顆挑屬性的鈕。把 app.js 的 checkinPeek 與 peekHtml 切出來交給 node 跑；沒有 node 就略過。"""
from __future__ import annotations

import random
from pathlib import Path

import pytest

import webharness
from conftest import real_content
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
ROOT = Path(__file__).parent.parent

DRIVER = r"""
const S = { peekOpen: input.open ? { id: "checkin", week: 1 } : null };
const H = new Function("S", [
  ...["esc", "CK_ATTR", "CK_LAST"].map(konst),
  ...["ckGift", "checkinPeek", "peekHtml"].map(fn),
  "return { checkinPeek, peekHtml };",
].join("\n"))(S);
const part = H.checkinPeek(input.m);
finish({ part, html: part ? H.peekHtml([part], 1) : "" });
"""

HOUR, DAY = 3600, 86400
MON = 1792339200  # 2026-10-19 週一 00:00（台灣）


def run(m, *, open_=True):
    return webharness.run(DRIVER, {"m": m, "open": open_})


def _week(today, claimed=(), last=7, first=1):
    labels = {1: "30 兩", 2: "一階", 3: "丹 2", 4: "30 兩", 5: "一階", 6: "丹2＋四階", 7: "30 兩"}
    return [{"day": d, "label": labels.get(d, "30 兩"), "got": d in claimed, "four": d == 6,
             "state": "today" if d == today else "future" if d > today else "got" if d in claimed else "miss"}
            for d in range(first, last + 1)]


def _m(**checkin):
    card = {"day": 3, "done": False, "week": _week(3, (1,)), "gift": "回體丹 2 顆", "step": "今天的份：回體丹 2 顆",
            "next": "明日 30 兩", "pick": None}
    card.update(checkin)
    return {"status": {"checkin": card}}


def test_chip_has_a_dot_until_claimed():
    out = run(_m(), open_=False)
    assert "peek-dot" in out["html"] and "簽到" in out["html"] and "✔" not in out["html"]
    assert 'aria-label="簽到：第 3 天還沒簽"' in out["html"]  # 亮點不另加「有還沒看過的」
    out = run(_m(done=True, step="今天的份領過了：回體丹 2 顆。"), open_=False)
    assert "peek-dot" not in out["html"] and "簽到 ✔" in out["html"]


def test_panel_lists_the_week_and_claim_button():
    html = run(_m())["html"]
    assert "第 3 天" in html and "下一份：明日 30 兩" in html
    assert html.count('class="ck-day') == 7
    assert 'ck-day miss' in html and 'ck-day got got' in html and 'ck-day today' in html
    assert html.count('data-act="checkin"') == 1 and "data-attr" not in html


def test_done_has_no_button():
    html = run(_m(done=True, step="今天的份領過了：回體丹 2 顆。"))["html"]
    assert 'data-act="checkin"' not in html and "今天的份領過了" in html


def test_tier4_day_shows_four_picks():
    pick = [{"attribute": a, "id": i, "name": n, "held": h} for a, i, n, h in
            (("剛", "gang_4", "熔星髓", 1), ("柔", "rou_4", "天池露", 0), ("快", "kuai_4", "奔雷角", 2), ("慢", "man_4", "歸墟壤", 0))]
    html = run(_m(day=6, week=_week(6), pick=pick, step="回體丹 2 顆，再挑一種四階料（點一種就領）："))["html"]
    assert html.count('data-act="checkin"') == 4
    for attr in "剛柔快慢":
        assert f'data-attr="{attr}"' in html
    assert "熔星髓" in html and "有 2" in html and "ck-go" not in html


def test_short_last_week_and_no_next():
    html = run(_m(day=19, week=_week(19, last=19, first=15), next=None))["html"]
    assert html.count('class="ck-day') == 5 and "下一份" not in html and "這一季最後一天" in html


def test_two_gift_label_splits_into_two_lines():
    """FB-436：第 6 天「丹2＋四階」字寬 48px、375／360 寬的格子只有 37／35px，被切成「丹2＋四」：兩樣的短字拆兩行（「丹2」／「＋四階」），
    一樣的照舊一行。"""
    html = run(_m(day=6, week=_week(6)))["html"]
    assert '<span class="g"><span class="gl">丹2</span><span class="gl">＋四階</span></span>' in html
    assert '<span class="g">30 兩</span>' in html and '<span class="g">丹 2</span>' in html
    css = (ROOT / "web" / "style.css").read_text(encoding="utf-8")
    assert ".ck-day .g .gl { display: block; }" in css


def test_the_signed_stamp_sits_on_the_top_corner():
    """FB-437：「簽」朱印貼在右下角，375 寬蓋掉「30 兩」的「兩」、「丹 2」的「2」、「一階」的「階」：改蓋在右上角、半壓在格子外框上，
    不碰底下那一行獎勵字（天數置中，兩位數也不到右邊那一截）。"""
    import re

    css = (ROOT / "web" / "style.css").read_text(encoding="utf-8")
    rule = re.search(r"\.ck-day\.got::after \{([^}]*)\}", css).group(1)
    assert re.search(r"(?<![-\w])top: -\d+px", rule) and "bottom" not in rule
    size = int(re.search(r"(?<![-\w])width: (\d+)px", rule).group(1))
    assert size <= 14


def test_no_chip_without_checkin():
    assert run({"status": {}})["part"] is None


def test_real_status_renders():
    c = real_content("season21")
    store = open_world()
    store.seed_first_season(c)
    store.open_season(c, MON + 10 * HOUR)
    game = Game.new(c, "沈浪", rng=random.Random(0), world=store)
    game.state.player.tutorial_step = len(c.tutorial.steps)
    store.catch_up_season(c, MON + 5 * DAY + 10 * HOUR, random.Random(0))
    game.sync(MON + 5 * DAY + 10 * HOUR)  # 第 6 天：挑四階
    html = run({"status": game.status_data()})["html"]
    assert "第 6 天" in html and html.count("data-attr") == 4
