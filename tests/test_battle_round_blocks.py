"""決戰的戰況一回合一段（Joy 2026-10-14「現在大決戰，因為很多人，戰況文字沒有分回合，擠在一起玩家很難閱讀」）。

引擎（Game._round_blocks）把場景上最近五段戰況寫成「##### 第 N 回合」加一行一條的清單、新的在上；網頁（app.js 的 roundBlocks）把最新
那一回合整段攤開，舊的幾回合各收成一行（回合數＋誰佔上風那一句），點了攤開，攤開了哪幾回合記在 S.roundsOpen、輪詢重畫照樣開著。"""
from __future__ import annotations

import re

from test_fb120_battle_fold import _fight_round, battle, node, run  # noqa: F401（battle 是 fixture）

import server
from tianxia import engine


def _many_lines(fighter):
    """把最近兩回合換成人多時的樣子：一回合好幾個人放手一搏，各一行（照 _advance_battle_round 的寫法用換行接起來）。"""
    def put(b):
        b.narrative_log[-1] = "\n".join(["這一回合官軍佔了上風（戰局 50→58）：甲帶頭強攻。", "甲放手一搏：「火燒連營」（評估成功率 30%）",
                                         "甲這一搏成功了！官軍推進一小截，自己氣血 -12。", "", "乙這一搏失敗了，付出了慘痛代價：自己氣血 -40。"])
    fighter.world.mutate_battle(put)


def test_each_round_is_its_own_block_newest_first(battle):
    _, fighter = battle
    _fight_round(fighter)
    _many_lines(fighter)
    text = fighter.scene_text()
    assert text.index("##### 第 2 回合") < text.index("##### 第 1 回合")  # 新的在上
    block = text.split("##### 第 2 回合", 1)[1].split("##### 第 1 回合", 1)[0]
    rows = [line for line in block.strip().split("\n") if line]
    assert rows == ["- 這一回合官軍佔了上風（戰局 50→58）：甲帶頭強攻。", "- 甲放手一搏：「火燒連營」（評估成功率 30%）",
                    "  甲這一搏成功了！官軍推進一小截，自己氣血 -12。", "- 乙這一搏失敗了，付出了慘痛代價：自己氣血 -40。"]
    # 一行一條、空行拿掉；誰寫了什麼跟接著的成敗併成同一條（Markdown 清單裡縮排的下一行，網頁上換行）
    assert text.index("##### 第 1 回合") < text.index("集結完畢，戰鬥開始")  # 開打那一句照舊一段話、在最後
    assert "##### 第 0 回合" not in text


def test_only_the_last_few_entries_are_shown(battle):
    _, fighter = battle
    for _ in range(engine.ROUND_BLOCKS):
        _fight_round(fighter)
    text = fighter.scene_text()
    n = fighter.world.get_battle().round_number
    heads = [int(x) for x in re.findall(r"##### 第 (\d+) 回合", text)]
    assert heads == list(range(n, n - engine.ROUND_BLOCKS, -1)) and "集結完畢，戰鬥開始" not in text


@node
def test_the_newest_round_is_open_and_older_ones_fold_to_a_line(battle):
    _, fighter = battle
    _fight_round(fighter)
    _fight_round(fighter)
    m = server.main_view(fighter)
    out = run(m, 'H.S.tab = "jianghu"; H.renderPage(); return T.els.page.innerHTML;', S={"roundsOpen": None})
    newest = re.search(r'<div class="b-round latest"><p class="b-rhead">第 3 回合</p><ul class="b-lines">', out)
    folded = re.findall(r'<details class="b-round" data-round="(\d+)"><summary><b>第 \d+ 回合</b><span>這一回合', out)
    assert newest and folded == ["2", "1"] and out.index("第 3 回合") < out.index('data-round="2"')
    assert "<h5>" not in out


@node
def test_an_opened_old_round_stays_open_when_the_page_redraws(battle):
    _, fighter = battle
    _fight_round(fighter)
    m = server.main_view(fighter)
    script = """
      H.S.tab = "jianghu"; H.S.roundsOpen = new Set(["1"]); H.renderPage();
      return T.els.page.innerHTML;"""
    out = run(m, script)
    assert '<details class="b-round" data-round="1" open>' in out
