"""決戰的戰況一回合一段（Joy 2026-10-14「現在大決戰，因為很多人，戰況文字沒有分回合，擠在一起玩家很難閱讀」）。

引擎（Game._round_blocks）把場景上最近五段戰況寫成「##### 第 N 回合」加一行一條的清單、新的在上；網頁（app.js 的 roundBlocks）把最新
那一回合整段攤開，舊的幾回合各收成一行（回合數＋誰佔上風那一句），點了攤開，攤開了哪幾回合記在 S.roundsOpen、輪詢重畫照樣開著。"""
from __future__ import annotations

import re

from test_jianghu_page_web import _fight_round, battle, node, run_prologue_web as run  # noqa: F401（battle 是 fixture）

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


def _sided(fighter):
    def put(b):
        b.narrative_log[-1] = "\n".join(["這一回合官軍佔了上風（戰局 50→58）：參戰乙帶頭強攻。", "參戰乙放手一搏：「火燒連營」（評估成功率 30%）",
                                         "參戰乙這一搏成功了！官軍推進一小截，自己氣血 -12。", "黃巾軍的強攻盯著顯眼的人打：參戰乙氣血 -8。",
                                         "各路奇招互相牽扯，官軍這一回合的放手一搏合起來只把戰線推前了一截。"])
    fighter.world.mutate_battle(put)


def test_each_line_says_which_side_it_is(battle):
    """Joy 2026-10-14「看不出誰是官軍誰是黃巾」：開頭是參戰者（照他站的那一邊）或交戰一方的名字，前面加那一軍；不分邊的句子不加。"""
    _, fighter = battle
    _sided(fighter)
    block = fighter.scene_text().split("##### 第 1 回合", 1)[1]
    rows = [line for line in block.split("\n\n", 2)[1].split("\n")]
    assert rows == ["- 這一回合官軍佔了上風（戰局 50→58）：參戰乙帶頭強攻。",
                    "- 〔官軍〕參戰乙放手一搏：「火燒連營」（評估成功率 30%）", "  參戰乙這一搏成功了！官軍推進一小截，自己氣血 -12。",
                    "- 〔黃巾軍〕黃巾軍的強攻盯著顯眼的人打：參戰乙氣血 -8。",
                    "- 各路奇招互相牽扯，官軍這一回合的放手一搏合起來只把戰線推前了一截。"]


@node
def test_the_side_shows_as_a_coloured_tag(battle):
    _, fighter = battle
    _sided(fighter)
    m = server.main_view(fighter)
    out = run(m, 'H.S.tab = "jianghu"; H.renderPage(); return T.els.page.innerHTML;')
    assert '<li class="b-side side-guan mine"><span class="b-tag">官軍・我方</span>參戰乙放手一搏' in out
    assert '<li class="b-side side-huang"><span class="b-tag">黃巾軍</span>黃巾軍的強攻' in out
    assert "〔" not in out.split('class="b-round latest"', 1)[1].split("</div>", 1)[0]


def _war_moves(fighter, kinds=True):
    """官軍另外三個人（丙、丁、戊）這一回合各發動了武學，黃巾那邊一個人一句、自己（參戰乙）一句（Joy 2026-10-30）。"""
    def put(b):
        me = b.participants["參戰乙"]
        for name, side in (("參戰丙", "guan"), ("參戰丁", "guan"), ("參戰戊", "guan"), ("參戰己", "huang")):
            b.participants[name] = me.model_copy(update={"faction": side})
        b.narrative_log[-1] = "\n".join(["這一回合官軍佔了上風（戰局 50→58）：參戰乙帶頭強攻。",
                                         "〔吐故納新〕參戰丙一吐一納，氣血一回合一回合慢慢回了過來",
                                         "〔沉勁〕參戰丁勁力沉到了底，這一回合出手極重",
                                         "〔吐故納新〕參戰戊一吐一納，氣血一回合一回合慢慢回了過來",
                                         "〔掠影〕參戰丙身形一掠，這一回合化影",
                                         "〔沉勁〕參戰乙勁力沉到了底，這一回合出手極重",
                                         "〔掠影〕參戰己身形一掠，這一回合化影"])
        b.tactic_kinds = {"吐故納新": "mend", "沉勁": "waver", "掠影": "shadow"} if kinds else {}
    fighter.world.mutate_battle(put)


def test_a_sides_war_moves_fold_into_one_summary_row(battle):
    """一軍這一回合發動武學的那幾句摺成一列「官軍本回合 3 人發動武學：回氣血 2、加重 1、化影 1」，逐人那幾句縮在底下；
    自己那一句不摺；另一軍只有一句也不摺。"""
    _, fighter = battle
    _war_moves(fighter)
    block = fighter.scene_text().split("##### 第 1 回合", 1)[1]
    rows = block.split("\n\n", 2)[1].split("\n")
    assert rows == ["- 這一回合官軍佔了上風（戰局 50→58）：參戰乙帶頭強攻。",
                    "- 〔官軍〕官軍本回合 3 人發動武學：回氣血 2、加重 1、化影 1",
                    "    - 〔吐故納新〕參戰丙一吐一納，氣血一回合一回合慢慢回了過來",
                    "    - 〔沉勁〕參戰丁勁力沉到了底，這一回合出手極重",
                    "    - 〔吐故納新〕參戰戊一吐一納，氣血一回合一回合慢慢回了過來",
                    "    - 〔掠影〕參戰丙身形一掠，這一回合化影",
                    "- 〔官軍〕〔沉勁〕參戰乙勁力沉到了底，這一回合出手極重",
                    "- 〔黃巾軍〕〔掠影〕參戰己身形一掠，這一回合化影"]


def test_an_old_battle_without_kinds_reads_them_from_the_content(battle):
    """這一版以前打的場沒記 kind：照內容的武學戰法與功效補（吐故納新是內容武學的、掠影與沉勁是功效）；一句都認不出來就只寫幾個人。"""
    _, fighter = battle
    _war_moves(fighter, kinds=False)
    assert "- 〔官軍〕官軍本回合 3 人發動武學：回氣血 2、加重 1、化影 1\n" in fighter.scene_text()

    def rename(b):
        b.narrative_log[-1] = b.narrative_log[-1].replace("吐故納新", "某甲").replace("沉勁", "某乙").replace("掠影", "某丙")
    fighter.world.mutate_battle(rename)
    assert "- 〔官軍〕官軍本回合 3 人發動武學\n    - 〔某甲〕" in fighter.scene_text()


@node
def test_the_fold_opens_on_tap_and_stays_open_on_redraw(battle):
    """網頁：摘要一列（帶那一軍的小標籤），逐人那幾句收在 <details class="b-fold"> 裡（招名照舊移到句尾）；開過的輪詢重畫照樣開著；
    回合結尾的 </ul> 認得對（自己那一句、黃巾那一句還在同一回合的清單裡）。"""
    _, fighter = battle
    _war_moves(fighter)
    m = server.main_view(fighter)
    out = run(m, 'H.S.tab = "jianghu"; H.renderPage(); return T.els.page.innerHTML;')
    latest = out.split('class="b-round latest"', 1)[1].split("</div>", 1)[0]
    assert ('<li class="b-side side-guan mine"><span class="b-tag">官軍・我方</span><details class="b-fold" data-fold="1:〔官軍〕">'
            '<summary>官軍本回合 3 人發動武學：回氣血 2、加重 1、化影 1</summary><ol class="b-fold-lines">') in latest
    assert '<li>參戰丙一吐一納，氣血一回合一回合慢慢回了過來<span class="t-move">〔吐故納新〕</span></li>' in latest
    assert latest.index("</ol></details></li>") < latest.index("參戰乙勁力沉到了底") < latest.index("參戰己身形一掠")
    assert "<h5>" not in out and "<ul>" not in latest
    again = run(m, 'H.S.tab = "jianghu"; H.S.foldOpen = new Set(["1:〔官軍〕"]); H.renderPage(); return T.els.page.innerHTML;')
    assert '<details class="b-fold" data-fold="1:〔官軍〕" open>' in again
