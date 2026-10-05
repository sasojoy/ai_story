"""江湖頁最上面的態勢卡（正式版辛；PM 2026-10-06 改成收起的一行）：web/app.js 沒有建置步驟、也沒有前端測試框架，
這裡把畫態勢卡的 stanceBars／stanceCardHtml 從原始碼切出來交給 node 跑，檢查出來的 HTML 結構：
收起時那一行寫了三方的名稱與數字，規則與怎麼算的兩行在摺疊裡面；另外檢查卡排在哪（只有平常閒著時排最上面，
在路上與事件、對話、決戰等一疊按鈕的選單排在選項底下）。沒有 node 就略過。"""
from __future__ import annotations

import json
import random
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tianxia.content import load_content
from tianxia.engine import Game

ROOT = Path(__file__).parent.parent
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="沒有 node，前端畫面測試略過")

DRIVER = r"""
const fs = require("fs");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const src = fs.readFileSync(input.app, "utf8");
const grab = (re) => { const m = src.match(re); if (!m) throw new Error("app.js 裡找不到 " + re); return m[0]; };
const a = src.indexOf("function stanceBars"), b = src.indexOf("function resultHtml");
if (a < 0 || b < a) throw new Error("app.js 裡找不到 stanceBars／stanceCardHtml");
// 存不了瀏覽器的儲存空間（隱私模式、被封鎖）時，卡也要照樣畫出來
for (const name of ["localStorage", "sessionStorage"]) {
  Object.defineProperty(globalThis, name, { get() { throw new Error("storage denied"); }, configurable: true });
}
const prelude = [grab(/const esc = .*;/), grab(/const pct = .*;/), grab(/const STANCE_NAMES = .*;/)].join("\n");
const make = new Function("S", prelude + "\n" + src.slice(a, b) + "\nreturn stanceCardHtml;");
process.stdout.write(JSON.stringify(make(input.S)(input.status)));
"""


PLACE_DRIVER = r"""
const fs = require("fs");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const src = fs.readFileSync(input.app, "utf8");
const grab = (re) => { const m = src.match(re); if (!m) throw new Error("app.js 裡找不到 " + re); return m[0]; };
const below = new Function(grab(/const idleMenu = .*;/) + "\n" + grab(/const stanceBelowMenu = .*;/) + "\nreturn stanceBelowMenu;")();
process.stdout.write(JSON.stringify(input.menus.map((m) => below(m))));
"""


def below_menu(*menus) -> list[bool]:
    """app.js 的 stanceBelowMenu(m)：每一個選單（{on_road, options}）的態勢卡是不是排在選項底下。"""
    done = subprocess.run(
        [NODE, "-e", PLACE_DRIVER],
        input=json.dumps({"app": str(ROOT / "web" / "app.js"), "menus": list(menus)}),
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def render(status, state=None) -> str:
    """跑 app.js 的 stanceCardHtml(status)；state 是 S 裡頭態勢卡讀的那幾欄（stanceOpen）。"""
    done = subprocess.run(
        [NODE, "-e", DRIVER],
        input=json.dumps({"app": str(ROOT / "web" / "app.js"), "status": status, "S": state or {}}),
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@pytest.fixture
def on():
    c = load_content(ROOT / "content")
    c.config.auto_open_first_season = True
    c.config.season_one, c.config.season_days, c.config.server_max_players = True, 2.5, 2
    return c


def _status(content):
    return Game.new(content, "甲", rng=random.Random(0)).status_data()


def _parts(html: str) -> tuple[str, str, str]:
    """（開頭的 <details …> 標籤，summary 裡的字，摺疊本體的 HTML）。"""
    head = re.match(r"<details[^>]*>", html)
    summary = re.search(r"<summary>(.*?)</summary>", html, re.S)
    body = re.search(r'<div class="fold-body">(.*)</div></details>\s*$', html, re.S)
    assert head and summary and body, html
    return head.group(0), re.sub(r"<[^>]+>", "", summary.group(1)), body.group(1)


def test_the_collapsed_row_names_the_three_sides_with_their_numbers(on):
    status = _status(on)
    _tag, summary, _body = _parts(render(status))
    assert "三方態勢" in summary
    seen = [(name, status["stances"][side]) for side, name in (("guan", "官軍"), ("huang", "黃巾"), ("haoqiang", "豪強"))]
    positions = [summary.index(f"{name} {value}") for name, value in seen]
    assert positions == sorted(positions)  # 官軍、黃巾、豪強，照這個順序


def test_the_numbers_follow_the_status_not_a_fixed_text(on):
    status = _status(on)
    status["stances"] = {"guan": 12, "huang": 88, "haoqiang": 7}
    _tag, summary, _body = _parts(render(status))
    assert "官軍 12" in summary and "黃巾 88" in summary and "豪強 7" in summary


def test_the_rule_and_the_how_line_sit_inside_the_fold_body(on):
    status = _status(on)
    html = render(status)
    _tag, summary, body = _parts(html)
    assert 'class="stance-rule"' in body and status["stance_rule"] in body
    assert 'class="stance-how"' in body and status["stance_notes"]["sum"] in body
    assert "stance-rule" not in html.split("</summary>")[0] and "stance-how" not in html.split("</summary>")[0]
    assert "收場" not in summary  # 收起的一行只有名稱與數字
    for side in ("guan", "huang", "haoqiang"):
        assert f"front-bar stance side-{side}" in body  # 展開才有三條（跟結算卡共用的 stanceBars）


def test_the_rule_line_follows_the_content(on):
    for ending in on.scenario.endings:
        if ending.stance_min:
            ending.stance_min = {side: 80 for side in ending.stance_min}
        if ending.stance_max:
            ending.stance_max = {side: 20 for side in ending.stance_max}
    on.config.decisive_from_week = 9
    status = _status(on)
    _tag, _summary, body = _parts(render(status))
    assert "第 9 週起，哪一方的態勢一到 80" in body


def test_collapsed_by_default_and_open_only_for_the_remembered_week(on):
    status = _status(on)
    week = status["calendar"]["week"]
    assert " open" not in _parts(render(status))[0]
    assert " open" not in _parts(render(status, {"stanceOpen": None}))[0]
    assert " open" not in _parts(render(status, {"stanceOpen": week + 1}))[0]  # 換週就收回
    tag = _parts(render(status, {"stanceOpen": week}))[0]
    assert " open" in tag and f'data-week="{week}"' in tag


def test_no_card_without_stances_and_no_rule_paragraph_without_a_rule(on):
    status = _status(on)
    assert render({k: v for k, v in status.items() if k != "stances"}) == ""
    assert render(None) == ""
    status["stance_rule"] = ""
    assert "stance-rule" not in _parts(render(status))[2]


def test_names_in_the_notes_are_escaped(on):
    status = _status(on)
    status["stance_notes"] = {"sum": "<b>x</b>", "haoqiang": ""}
    _tag, _summary, body = _parts(render(status))
    assert "<b>x</b>" not in body and "&lt;b&gt;x&lt;/b&gt;" in body


# ── 排在哪：平常閒著（行動列）排最上面，其他的選單（一疊按鈕）排在選項底下 ──────────


def _menu(*ids, on_road=False):
    return {"on_road": on_road, "options": [{"id": i, "label": i, "enabled": True} for i in ids]}


def test_the_card_tops_the_page_only_for_the_idle_menu():
    idle = _menu("act:explore", "act:train", "act:rest", "act:call", "move:luoyang")
    event = _menu("choice:0", "choice:1", "choice:free")
    dialogue = _menu("talk:0", "talk:1", "talk:leave")
    battle = _menu("battle:guan", "battle:huang")
    audience = _menu("call:luzhi", "call:cancel")
    faction = _menu("faction:confirm", "faction:cancel")
    assert below_menu(idle, event, dialogue, battle, audience, faction) == [False, True, True, True, True, True]


def test_the_card_is_below_the_options_on_the_road():
    assert below_menu(_menu("road:back", "road:wait", on_road=True)) == [True]
    assert below_menu(_menu("act:rest", on_road=True)) == [True]  # 就算選單上剛好有打坐，在路上照舊排在底下


def test_page_jianghu_orders_the_card_by_that_rule():
    """版面順序的標記檢查：pageJianghu 兩個 return 用同一條 stanceBelowMenu(m) 決定卡排哪裡。"""
    src = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    page = src[src.index("function pageJianghu"): src.index("// ── 修練 ──")]
    assert "stanceBelowMenu(m)" in page
    road = re.search(r"if \(m\.on_road\) return `([^`]*)`;", page).group(1)
    idle = re.search(r"\n\s*return `(\$\{resultCard\}[^`]*)`;", page).group(1)
    assert "${topCard}" not in road and road.index("${menu}") < road.index("${lowCard}")
    assert idle.index("${topCard}") < idle.index("${now}") and idle.index("${menu}") < idle.index("${lowCard}")
