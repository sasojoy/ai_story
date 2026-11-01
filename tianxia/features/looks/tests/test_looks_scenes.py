"""一句話自創絕招的導演稿（scenes.py；Joy 2026-11-01「可以讓玩家『自創』，不是拼接組合」）：關鍵字導演怎麼拆一句話、
夾稿的規矩（動作只認表上的、參數只認表上的值、主攻只留一種、要畫的最多兩樣、時間照表排）。"""
from __future__ import annotations

from tianxia.features.looks import scenes


def ops(scene):
    return [b["op"] for b in scene["beats"]]


def test_a_sword_of_cold_light():
    s = scenes.direct("一劍寒光九萬里", "寒光九萬里")
    assert ops(s) == ["暗場", "蓄勢", "落款", "飄落", "光束", "異狀", "白光"]
    assert s["glow"] == scenes.GLOWS["寒"] and s["arts"] == [] and s["name"] == "寒光九萬里"
    assert next(b for b in s["beats"] if b["op"] == "異狀")["kind"] == "冰封"


def test_a_great_buddha_strikes_a_palm():
    s = scenes.direct("背後出現一座大佛擊出一掌")
    assert ops(s) == ["暗場", "震地", "蓄勢", "法相", "落款", "巨物飛擊", "白光"]
    assert [a["label"] for a in s["arts"]] == ["大佛", "佛掌"] and [a["slot"] for a in s["arts"]] == ["art1", "art2"]
    assert next(b for b in s["beats"] if b["op"] == "落款")["at"] == scenes.TITLE_AFTER_FIGURE  # 等法相升起來才落款
    assert s["glow"] == scenes.GLOWS["金"]


def test_ten_thousand_swords_rain_down():
    s = scenes.direct("萬劍如雨落下")
    swords = next(b for b in s["beats"] if b["op"] == "飛劍")
    assert (swords["count"], swords["form"]) == (scenes.COUNT_MAX, "雨") and "光束" not in ops(s)  # 主攻只留一種


def test_anything_unknown_is_still_a_strike():
    s = scenes.direct("無名")
    assert ops(s) == ["暗場", "蓄勢", "落款", "光束", "白光"]


def test_clean_keeps_only_what_the_table_allows():
    raw = {"glow": "#123456", "beats": [
        {"op": "核爆"}, {"op": "飛劍", "count": 999, "form": "螺旋"}, {"op": "光束"}, {"op": "飄落", "kind": "血"},
        {"op": "法相", "label": "Dragon龍王"}, {"op": "巨物飛擊", "label": "龍爪"}, {"op": "異狀", "kind": "冰封"}, {"op": "暗場", "tone": "粉"},
    ]}
    s = scenes.clean(raw, "名字太長了的招名")
    assert ops(s) == ["暗場", "蓄勢", "法相", "落款", "巨物飛擊", "異狀", "白光"]  # 主攻留巨物飛擊；核爆、血雨丟掉
    assert s["glow"] == scenes.GLOWS["金"] and s["name"] == "名字太長了的"
    assert [a["label"] for a in s["arts"]] == ["龍王", "龍爪"]
    assert next(b for b in s["beats"] if b["op"] == "暗場")["tone"] == "冷"
    assert [b["at"] for b in s["beats"]] == sorted(b["at"] for b in s["beats"])
    swords = scenes.clean({"beats": [{"op": "飛劍", "count": 1}]})["beats"]
    assert next(b for b in swords if b["op"] == "飛劍")["count"] == scenes.COUNT_MIN


def test_a_giant_without_a_name_becomes_light():
    s = scenes.clean({"beats": [{"op": "巨物飛擊", "label": ""}]})
    assert "巨物飛擊" not in ops(s) and "光束" in ops(s) and s["arts"] == []


def test_only_chinese_and_not_empty():
    assert scenes.text_problem("") == scenes.NO_TEXT
    assert scenes.text_problem("sword 劍") == scenes.ONLY_ZH
    assert scenes.text_problem("一劍寒光，九萬里！") is None
