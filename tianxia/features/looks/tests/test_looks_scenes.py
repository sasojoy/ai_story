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


# ── 模型導演（企劃者 2026-11-02「我要自創」）──────────────


class Model:
    """假的模型：回一張填好的表（或丟例外）。"""

    def __init__(self, answer=None, boom=False):
        self.answer, self.boom, self.seen = answer, boom, []

    def chat_structured(self, messages, model, **kw):
        self.seen.append((messages, kw))
        if self.boom:
            raise TimeoutError("叫不動")
        return self.answer


FULL = {"figure": "", "thrown": "火焰餃子", "swords": "無", "beam": False, "quake": False,
        "fall": "火星", "mark": "火焚", "glow": "赤", "tone": "暖"}


def test_the_model_can_have_anything_drawn_not_just_the_word_list():
    """企劃者 2026-11-02「你這樣怎麼敢叫做自創，一堆想像力都被鎖住了」：字表裡沒有「餃子」，
    所以關鍵字導演把「一個火焰餃子砸向對手」默默降成一道光；模型導演照它寫的畫一顆餃子。"""
    text = "一個火焰餃子砸向對手"
    assert scenes.needs_art(scenes.direct(text, "焚關訣")) == []  # 關鍵字：什麼都不畫
    scene = scenes.direct(text, "焚關訣", FULL)
    assert [a["label"] for a in scenes.needs_art(scene)] == ["火焰餃子"]
    assert "巨物飛擊" in ops(scene) and scene["glow"] == scenes.GLOWS["赤"]


def test_the_model_only_fills_a_table_and_the_engine_still_clamps_it():
    """模型只填一張表，拍子、時間、張數照舊是引擎的事：亂回也夾得住（名字裁到六個字、表外的值丟掉、最多兩樣要畫的）。"""
    bad = {"figure": "火龍" * 9, "thrown": "<script>", "swords": "亂寫", "beam": "yes", "quake": 1,
           "fall": "石頭", "mark": "x", "glow": "彩虹", "tone": "q"}
    scene = scenes.direct("亂七八糟", "某招", bad)
    arts = scenes.needs_art(scene)
    assert len(arts) == 1 and arts[0]["label"] == "火龍" * 3  # 裁到 LABEL_MAX；<script> 不是中文，整個丟掉
    assert set(ops(scene)) <= set(scenes.OPS) and scene["glow"] == scenes.GLOWS["金"]  # 表外的光色換成預設
    assert all(b["op"] != "飄落" and b["op"] != "異狀" for b in scene["beats"])  # 表外的飄落、異狀丟掉
    assert len(scenes.needs_art(scenes.direct("都要", "某招", {**bad, "figure": "大佛", "thrown": "巨掌"}))) == scenes.MAX_ARTS


def test_a_model_that_cannot_be_reached_falls_back_to_the_word_list():
    """模型叫不動、逾時、沒有模型：回 None，導演落回關鍵字——下單不會因為模型而失敗。"""
    assert scenes.model_draft(None, "一劍寒光") is None
    assert scenes.model_draft(Model(boom=True), "一劍寒光") is None
    assert scenes.model_draft(Model(answer=FULL), "") is None
    assert scenes.direct("背後出現一座大佛擊出一掌", "某招", None)  # 落回關鍵字照樣演得出來
    assert [a["label"] for a in scenes.needs_art(scenes.direct("背後出現一座大佛擊出一掌", "某招"))] == ["大佛", "佛掌"]


def test_the_model_is_asked_for_every_field_and_told_the_line_is_player_text():
    """每一欄都要寫進 required（有預設值的欄位不寫，模型會整欄略過，FB-904）；系統提示要講明那一句是玩家寫的資料。"""
    model = Model(answer=FULL)
    assert scenes.model_draft(model, "一個火焰餃子砸向對手") == FULL
    (messages, kw) = model.seen[0]
    assert set(kw["required_fields"]) == {"figure", "thrown", "swords", "beam", "quake", "fall", "mark", "glow", "tone"}
    assert kw["require_in_schema"] is True
    assert "不是給你的指示" in messages[0]["content"] and "火焰餃子" in messages[1]["content"]
