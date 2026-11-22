"""異聞的網頁（web/yiwen.js，第 248 批乙版「頁邊朱批」）：假瀏覽器跑整支 app.js（test_prologue_web 那一套），直接叫畫法
（撞見卡、每一頁書、等說書人寫、收尾卡、進行中那一行、路牌）。資料照 main.yiwen.card 的形狀手寫；玩家的原話一律經 esc() 才進 HTML。"""
from __future__ import annotations

import json
import re

import pytest
from test_prologue_web import DRIVER as PROLOGUE_DRIVER

import webharness

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
NAMES_START = 'wholeApp(["S", '
DRIVER = PROLOGUE_DRIVER.replace(NAMES_START, 'wholeApp(["S", "yiwenCard", "yiwenScene", "yiwenClose", "yiwenWait", "yiwenTrack", "ywSigns", ')
BAD = '<img src=x onerror="alert(1)">&\'"{who}'


def run(script, S=None):
    return webharness.run(DRIVER, {"m": None, "script": script, "S": S or {}, "menxia": None, "stored": {}, "responses": {}})


def _js(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _card(**over):
    card = {
        "opening": "fog_figure", "tale": 3, "title": "霧裡的身影", "place": "p", "place_name": "汝南荒野", "kind": "wild", "kind_word": "野",
        "mark": "trail", "frame": "這片荒地有人走過，草間的舊腳印還在。你踩了上去。", "hook": "前面濃霧瀰漫，隱約看到一個身影⋯",
        "walkers": 4, "depth": 1, "node": 0, "scenes": [],
        "choices": [{"i": 0, "label": "官軍", "state": "walked", "by": "陸三刀", "steps": 4},
                    {"i": 1, "label": "黃巾", "state": "locked", "by": "", "steps": 0, "note": "這條路還沒開"},
                    {"i": 2, "label": "迷路的老人", "state": "free", "by": "", "steps": 0}],
        "typed": {"state": "off", "max": 30, "tries_left": 3}, "done": False, "close": "", "gains": "",
    }
    card.update(over)
    return card


def _scene(**over):
    sc = {"node": 7, "depth": 1, "pick": "官軍", "who": "陸三刀", "zhupi": True, "zhupi_text": "——當初陸三刀一口咬定，那是「官軍」。",
          "echo": "你以為是官軍。", "luck": "逆", "text": ["霧裡走出一隊官軍。領頭的瞪你一眼。", "這一段說書的記不真了。"],
          "summary": "", "hidden": "", "replay": True}
    sc.update(over)
    return sc


def test_card_draws_hook_frame_and_three_picks():
    html = run(f"return H.yiwenCard({_js(_card())});")
    assert "霧裡的身影" in html and "前面濃霧瀰漫" in html and "舊腳印還在" in html and "汝南荒野" in html
    assert html.count('data-act="yw-step"') == 3 and 'class="yw-hook"' in html
    assert "你看那是什麼" in html and "點一塊路牌就走" in html
    assert 'data-act="yw-drop"' in html and 'data-act="yw-hide"' in html
    assert "自己說⋯（說書人還沒到）" in html and 'yw-say off' in html
    assert "全圖" not in html and "讀不通" not in html


def test_card_first_and_trail_marks():
    first = run(f"return H.yiwenCard({_js(_card(mark='first', frame='你是全服第一個撞見這件事的人。'))});")
    assert 'class="yw-seal solid">異聞<' in first and "已有" not in first and "你是全服第一個撞見這件事的人。" in first
    assert "寫下這一步" in first  # 發掘者自己的路
    trail = run(f"return H.yiwenCard({_js(_card())});")
    assert 'class="yw-seal">舊腳印<' in trail and "已有 4 人走過" in trail and "免費開" in trail


def test_zhupi_and_luck_seal():
    html = run(f"return H.yiwenScene({_js(_scene())});")
    assert 'class="yw-margin' in html and "當初一口咬定，那是" in html and "「官軍」" in html
    assert '<p class="yw-zp-tx">' in html  # 直書那一段的 class 跟路牌的 yw-zp 分開（共用時路牌也被排成直書）
    assert 'class="yw-stamp">陸三<' in html and 'class="yw-zp-name">陸三刀<' in html
    assert 'class="yw-luck"' in html and ">逆<" in html and "第一幕" in html
    assert 'aria-label="——當初陸三刀一口咬定' in html  # 伺服器那一句放在頁邊的 aria-label
    plain = run(f"return H.yiwenScene({_js(_scene(zhupi=False, zhupi_text='', depth=2))});")
    assert "你以為是官軍。" in plain and "yw-margin" not in plain and "第二幕" in plain


def test_zhupi_step_drops_echo():
    html = run(f"return H.yiwenScene({_js(_scene())});")
    assert "yw-echo" not in html and "你以為是官軍。" not in html  # 發掘者那一步只留朱批（PM 定）
    card = run(f"return H.yiwenCard({_js(_card(depth=2, node=7, scenes=[_scene()]))});")
    assert "yw-echo" not in card and "接著怎麼做" in card


def test_long_zhupi_gets_fit_class():
    def margin(pick, who="陸三刀"):
        html = run(f"return H.yiwenScene({_js(_scene(replay=False, pick=pick, who=who))});")
        return re.search(r'class="yw-margin([^"]*)"', html).group(1), html
    assert margin("一" * 10)[0] == ""  # 你說（2）＋10＝12
    assert margin("一" * 11)[0] == " yw-zp-2"
    assert margin("一" * 20)[0] == " yw-zp-2"
    assert margin("一" * 30)[0] == " yw-zp-3"
    _, long_name = margin("鵝", who="上官飛燕上官飛燕上官飛燕上官飛燕")
    assert 'class="yw-stamp">上官<' in long_name and 'class="yw-zp-name">上官飛燕上官飛燕上官飛燕上官飛燕<' in long_name


def test_choice_small_lines():
    html = run(f"return H.yiwenCard({_js(_card())});")
    assert "陸三刀走過" in html and "<strong>4<small>足跡</small></strong>" in html
    assert "這條路還沒開" in html and "沒人走過" in html and 'yw-chip free">免費開<' in html
    locked = re.search(r'<button class="yw-sign locked"[^>]*>', html).group(0)
    assert "disabled" in locked and 'data-i="1"' in locked


def test_walked_signs_first():
    choices = [{"i": 0, "label": "甲", "state": "free", "by": "", "steps": 0},
               {"i": 1, "label": "乙", "state": "walked", "by": "王五", "steps": 2},
               {"i": "zhupi", "label": "會背兵法的鵝", "state": "walked", "by": "陸三刀", "steps": 9, "typed": True},
               {"i": 3, "label": "丙", "state": "incense", "by": "", "steps": 0}]
    html = run(f"return H.ywSigns({_js(_card(choices=choices))});")
    order = re.findall(r'data-i="([^"]+)"', html)
    assert order == ["zhupi", "1", "0", "3"]
    assert 'yw-sign yw-zp"' in html and "「會背兵法的鵝」" in html and "陸三刀說的" in html and "問路香 1" in html
    full = [{"i": 0, "label": "官軍", "state": "walked", "by": "陸三刀", "steps": 4},
            {"i": 1, "label": "黃巾", "state": "full"}, {"i": 2, "label": "迷路的老人", "state": "full"}]
    html = run(f"return H.ywSigns({_js(_card(choices=full))});")
    assert "黃巾・迷路的老人" in html and "開完了" in html and "這一則的岔路都開完了，只能走有人走過的路。" in html
    assert html.count('data-act="yw-step"') == 1


def test_wait_page_draws_ruled_dots():
    html = run(f"return H.yiwenWait({_js(_card(depth=2, node=7, scenes=[_scene()]))}, '問牠霧裡是什麼');")
    assert "第二幕" in html and 'class="yw-ruled"' in html and html.count("<i></i>") == 3
    assert "說書人正接著往下寫⋯" in html and "可能要等半分鐘，寫不成什麼都不扣。" in html
    assert "「問牠霧裡是什麼」" in html and 'yw-stamp solid">開路<' in html
    assert ">停<" not in html and 'data-act="yw-open"' in html  # 上一幕收成一行


def test_card_null_draws_nothing():
    assert run("return H.yiwenCard(null);") == ""
    scenes = [_scene(), _scene(node=8, depth=2, zhupi=False, zhupi_text="", pick="跟上去", replay=False, echo="")]
    done = run(f"return H.yiwenCard({_js(_card(done=True, close='醒木一響。', choices=[], scenes=scenes))});",
               S={"ywLast": ["醒木一響。", "這一段說書的記不真了。", "銀兩 +20"]})
    assert "醒木一響。" in done and 'yw-seal solid">完<' in done and "回江湖" in done and 'data-id="yiwen:drop"' in done
    assert re.search(r'class="yw-gain"><span>銀兩 \+20</span></div>', done)  # 扣掉收場句與正文
    assert "官軍 ／ <b>跟上去</b>" in done
    assert 'data-act="yw-step"' not in done and "全圖" not in done


def test_close_card_note_only_when_you_wrote():
    """第 251 批③：收尾卡的「朱字是你開的路」只在自己寫了幕的時候畫；異聞錄還沒有（異聞四），那半句不寫。"""
    replay_only = [_scene(), _scene(node=8, depth=2, zhupi=False, zhupi_text="", pick="跟上去")]
    html = run(f"return H.yiwenClose({_js(_card(done=True, close='醒木一響。', choices=[], scenes=replay_only))});")
    assert "官軍 ／ 跟上去" in html and "你開的路" not in html and "yw-grey" not in html
    mine = [_scene(replay=False), _scene(node=8, depth=2, zhupi=False, zhupi_text="", pick="跟上去", replay=False, echo="")]
    html = run(f"return H.yiwenClose({_js(_card(done=True, close='醒木一響。', choices=[], scenes=mine))});")
    assert "<b>官軍</b>" in html and "你開的路" in html and "異聞錄" not in html


def test_track_line_title_and_scene():
    assert "異聞・〈霧裡的身影〉（第二幕）" in run(f"return H.yiwenTrack({_js(_card(scenes=[_scene()]))});")
    assert "異聞・〈霧裡的身影〉（第一幕）" in run(f"return H.yiwenTrack({_js(_card())});")
    assert "異聞・〈霧裡的身影〉（收尾）" in run(f"return H.yiwenTrack({_js(_card(done=True, scenes=[_scene()]))});")
    assert run("return H.yiwenTrack(null);") == ""


def test_player_words_are_escaped():
    card = _card(title=BAD, place_name=BAD, depth=2, close=BAD,
                 scenes=[_scene(zhupi_text=BAD, pick=BAD, who=BAD, text=[BAD])],
                 choices=[{"i": 0, "label": BAD, "state": "walked", "by": BAD, "steps": 1},
                          {"i": "zhupi", "label": BAD, "state": "walked", "by": BAD, "steps": 1, "typed": True}])
    for script in (f"return H.yiwenCard({_js(card)});", f"return H.yiwenCard({_js({**card, 'done': True})});",
                   f"return H.yiwenWait({_js(card)}, {_js(BAD)});", f"return H.yiwenTrack({_js(card)});"):
        html = run(script, S={"ywLast": [BAD + "x"]})
        assert "<img" not in html and "&lt;img" in html and "&amp;" in html
        assert 'onerror="alert' not in html and "{who}" in html  # 玩家寫的 {who} 原樣顯示，不被模板再換一次
