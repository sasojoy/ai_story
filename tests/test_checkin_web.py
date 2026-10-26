"""正式季整合第 7 批：每日簽到（設計 9.1 第 4 組丙）。減法季批 1 乙案（Joy 2026-10-24）起簽到不放鈕：每天第一次同步引擎自動領，
本週卡上沒有簽到的字；要挑四階的日子本週卡底下冒一張小卡、四顆挑屬性的鈕。這一週七格（每天給什麼）收在「為什麼」裡（checkinPeek 的 panel）。
把 main.js 的 checkinPeek、checkinPickHtml 與 weekCardHtml 切出來交給 node 跑；沒有 node 就略過。"""
from __future__ import annotations

import random
import re
from pathlib import Path

import pytest

import webharness
from conftest import real_content
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
ROOT = Path(__file__).parent.parent

DRIVER = r"""
const S = { wkOpen: null };
const H = new Function("S", [
  ...["esc", "CK_ATTR", "CK_LAST", "WK_STEP", "WK_WHY", "WK_NEXT", "WK_GO", "WK_MAP", "WK_IDLE", "CK_PICK_TITLE", "CK_PICK_NOTE", "WK_HIDE", "WK_HIDE_STORE", "wkKey", "wkDay"].map(konst),
  "const shown = () => true, STANCE_NAMES = [], whyHtml = () => '';",
  ...["ckGift", "checkinPeek", "wkStepOf", "wkSidesHtml", "wkSplit", "wkHidden", "checkinPickHtml", "weekCardHtml"].map(fn),
  "return { checkinPeek, weekCardHtml };",
].join("\n"))(S);
const part = H.checkinPeek(input.m);
const m = { ...input.m, week_card: { label: "本週", when: "第 1 週", theme: "", sides: null, steps: [], next: null } };
finish({ part, html: H.weekCardHtml(m) });
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


def test_the_week_card_has_no_sign_in_button_on_an_ordinary_day():
    """乙案：不必挑的日子引擎自動領，本週卡上一個簽到的字、一顆鈕都沒有（還沒領到、領過了都一樣）。"""
    for m in (_m(), _m(done=True, step="今天的份領過了：回體丹 2 顆。")):
        html = run(m, open_=False)["html"]
        assert "簽到" not in html and 'data-act="checkin"' not in html and "ck-card" not in html


def test_the_why_panel_part_lists_the_week():
    """這一週七格（每天給什麼）收在「為什麼」裡（whyHtml 接 checkinPeek 的 panel）。"""
    panel = run(_m())["part"]["panel"]
    assert "第 3 天" in panel and "下一份：明日 30 兩" in panel
    assert panel.count('class="ck-day') == 7
    assert 'ck-day miss' in panel and 'ck-day got got' in panel and 'ck-day today' in panel


def test_done_has_no_button():
    panel = run(_m(done=True, step="今天的份領過了：回體丹 2 顆。"))["part"]["panel"]
    assert 'data-act="checkin"' not in panel and "今天的份領過了" in panel


def test_tier4_day_shows_four_picks():
    pick = [{"attribute": a, "id": i, "name": n, "held": h} for a, i, n, h in
            (("剛", "gang_4", "熔星髓", 1), ("柔", "rou_4", "天池露", 0), ("快", "kuai_4", "奔雷角", 2), ("慢", "man_4", "歸墟壤", 0))]
    html = run(_m(day=6, week=_week(6), pick=pick, step="回體丹 2 顆，再挑一種四階料（點一種就領）："))["html"]
    card = re.search(r'<section data-wk class="card ck-card".*?</section>', html, re.S).group(0)  # 本週卡底下那一張小卡
    assert "簽到第 6 天" in card and card.count('data-act="checkin"') == 4
    for attr in "剛柔快慢":
        assert f'data-attr="{attr}"' in card
    assert "熔星髓" in card and "有 2" in card and "ck-go" not in html


def test_short_last_week_and_no_next():
    panel = run(_m(day=19, week=_week(19, last=19, first=15), next=None))["part"]["panel"]
    assert panel.count('class="ck-day') == 5 and "下一份" not in panel and "這一季最後一天" in panel


def test_two_gift_label_splits_into_two_lines():
    """FB-436：第 6 天「丹2＋四階」字寬 48px、375／360 寬的格子只有 37／35px，被切成「丹2＋四」：兩樣的短字拆兩行（「丹2」／「＋四階」），
    一樣的照舊一行。"""
    html = run(_m(day=6, week=_week(6)))["part"]["panel"]
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
