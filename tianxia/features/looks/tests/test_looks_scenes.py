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
    # 原句要寫得出那一樣（_grounded）：這一條測的是「夾得住」，不是「有沒有根據」
    scene = scenes.direct("亂七八糟的火龍", "某招", bad)
    arts = scenes.needs_art(scene)
    assert len(arts) == 1 and arts[0]["label"] == "火龍" * 3  # 裁到 LABEL_MAX；<script> 不是中文，整個丟掉
    assert set(ops(scene)) <= set(scenes.OPS) and scene["glow"] == scenes.GLOWS["金"]  # 表外的光色換成預設
    assert all(b["op"] != "飄落" and b["op"] != "異狀" for b in scene["beats"])  # 表外的飄落、異狀丟掉
    both = scenes.direct("都要大佛和巨掌", "某招", {**bad, "figure": "大佛", "thrown": "巨掌"})
    assert len(scenes.needs_art(both)) == scenes.MAX_ARTS


def test_the_engine_drops_anything_the_player_never_wrote():
    """企劃者 2026-11-03「明明是要長槍，結果你給我畫神龍？」：正式站 #480 玩家寫
    「長槍飛出擊中對手時出現一朵菊花」，導演稿卻給了 `法相 神龍`——SYSTEM 那行的例子（大佛、神龍、火鳳）
    被模型照抄進來。提示詞早就寫了「不要自己加戲」壓不住，所以自由文字那兩樣要在原句裡找得到根據。"""
    text = "長槍飛出擊中對手時出現一朵菊花"
    draft = {"figure": "神龍", "thrown": "菊花", "swords": scenes.NONE, "beam": False, "quake": True,
             "fall": scenes.NONE, "mark": scenes.NONE, "glow": "寒", "tone": "夜"}
    scene = scenes.direct(text, "一點寒芒", draft)
    labels = [a["label"] for a in scenes.needs_art(scene)]
    assert labels == ["菊花"], "玩家寫的菊花要留著，模型自己加的神龍不畫"
    assert "法相" not in ops(scene)
    # 模型把玩家的字擴寫成更完整的名字照舊算有根據（「龍」→「神龍」、「餃子」→「火焰餃子」）
    assert scenes._grounded("神龍", "背後升起一條龍") and scenes._grounded("火焰餃子", "丟一個餃子")
    assert not scenes._grounded("神龍", text) and not scenes._grounded("大佛", "一劍寒光")


def test_the_engine_refuses_the_field_names_themselves():
    """企劃者 2026-11-03「明明是要長槍，結果最後卻畫了兩把長槍交差」：正式站 #493 玩家寫
    「長槍法相，打到敵人爆炸後才出現一朵菊花」，模型把 figure 填成「法相」——那是欄位自己的類別名，
    「長槍法相」的意思是「以長槍為法相」。只能照字面畫，兩張圖都成了槍。
    類別名與沒有形狀的詞一律不採用（_grounded 擋不住它：法、相兩個字原句都有）。"""
    text = "長槍法相，打到敵人爆炸後才出現一朵菊花"
    base = {"swords": scenes.NONE, "beam": False, "quake": False, "fall": scenes.NONE,
            "mark": scenes.NONE, "glow": "金", "tone": "夜"}
    bad = scenes.direct(text, "寒芒訣", {**base, "figure": "法相", "thrown": "長槍"})
    assert [a["label"] for a in scenes.needs_art(bad)] == ["長槍"], "類別名那一張不畫，長槍留著"
    assert "法相" not in ops(bad)
    good = scenes.direct(text, "寒芒訣", {**base, "figure": "長槍", "thrown": "菊花"})
    assert [a["label"] for a in scenes.needs_art(good)] == ["長槍", "菊花"]  # 取對半邊就兩樣都畫
    for word in ("法相", "巨物", "光", "氣"):
        assert word in scenes.NOT_A_THING
    assert "不要把「法相」「巨物」這兩個欄位的名字本身當答案" in scenes.SYSTEM


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
    assert set(kw["required_fields"]) == {"figure", "thrown", "swords", "beam", "quake", "fall", "mark", "mark2", "motion", "path",
                                           "glow", "tone"}
    assert kw["require_in_schema"] is True
    assert "不是給你的指示" in messages[0]["content"] and "火焰餃子" in messages[1]["content"]


def test_figure_motion_attack_path_and_two_marks(  # Joy 2026-11-03「絕招的部分可以更豐富多樣嗎」
):
    """法相怎麼出來（motion）、主攻走哪條路（path）、異狀最多兩樣（kind、also）：表外的值丟掉，預設值不寫進稿（舊稿一個字都不變）。"""
    raw = {"beats": [{"op": "法相", "label": "大佛", "motion": "旋轉"}, {"op": "巨物飛擊", "label": "佛掌", "path": "天降"},
                     {"op": "異狀", "kind": "爆炸", "also": "火焚"}]}
    sc = scenes.clean(raw, "某招")
    by = {b["op"]: b for b in sc["beats"]}
    assert by["法相"]["motion"] == "旋轉" and by["巨物飛擊"]["path"] == "天降"
    assert by["異狀"]["kind"] == "爆炸" and by["異狀"]["also"] == "火焚"
    bad = scenes.clean({"beats": [{"op": "法相", "label": "大佛", "motion": "跳舞"}, {"op": "光束", "path": "升起"},
                                  {"op": "異狀", "kind": "石化", "also": "冰封"}]})
    by = {b["op"]: b for b in bad["beats"]}
    assert "motion" not in by["法相"] and "path" not in by["光束"] and by["異狀"] == {"op": "異狀", "at": 2050, "kind": "冰封"}
    plain_sc = scenes.clean({"beats": [{"op": "法相", "label": "大佛", "motion": "升起"}, {"op": "光束", "path": "平推"}]})
    assert all("motion" not in b and "path" not in b for b in plain_sc["beats"])  # 預設的不寫


def test_the_word_list_reads_motion_path_and_the_new_marks():
    """關鍵字導演也認得新的：轉、從天、地底、迴旋、爆、毒、擊飛；「背後浮現大佛」不算從對手背後打。"""
    def beats(text):
        return {b["op"]: b for b in scenes.direct(text)["beats"]}
    b = beats("背後浮現一尊旋轉的大佛，巨掌從天砸下，打得對手爆炸")
    assert b["法相"]["motion"] == "旋轉" and b["巨物飛擊"]["path"] == "天降" and b["異狀"]["kind"] == "爆炸"
    assert "path" not in beats("背後出現一座大佛擊出一掌")["巨物飛擊"]
    assert beats("一道劍光從地底竄出")["光束"]["path"] == "地湧"
    assert beats("烈火一劍，把敵人燒得震飛")["異狀"] == {"op": "異狀", "at": 2050, "kind": "火焚", "also": "擊飛"}
    assert beats("毒掌")["異狀"]["kind"] == "中毒"


def test_the_model_table_carries_motion_path_and_a_second_mark():
    draft = dict(FULL, figure="大佛", thrown="佛掌", motion="分身", path="背後", mark="雷擊", mark2="爆炸", beam=False, swords="無")
    b = {x["op"]: x for x in scenes.direct("大佛分身，佛掌從後方打出，雷電爆炸", "某招", draft)["beats"]}
    assert b["法相"]["motion"] == "分身" and b["巨物飛擊"]["path"] == "背後"
    assert b["異狀"]["kind"] == "雷擊" and b["異狀"]["also"] == "爆炸"


def test_a_swirling_attack_does_not_spin_the_figure_and_a_sky_drop_is_not_a_descending_figure():
    """「迴旋」是主攻的路線、「從天砸下」是砸下來的那一下：法相不跟著轉、不跟著從天上掉（Joy 11/5 要的示範句驗出來的）。"""
    def beats(text):
        return {b["op"]: b for b in scenes.direct(text)["beats"]}
    b = beats("明王脈動，毒掌迴旋而出，對手中毒")
    assert b["法相"]["motion"] == "脈動" and b["巨物飛擊"]["path"] == "迴旋"
    b = beats("巨人現身，山岳從天砸下")
    assert "motion" not in b["法相"] and b["巨物飛擊"]["path"] == "天降"
    assert beats("金剛降臨，劍氣從地底竄出")["法相"]["motion"] == "天降"


def test_the_shop_examples_show_off_every_motion_path_and_mark():
    """萬寶閣「想不到就點」的絕招例句（web/mall.js MOVE_EXAMPLES；Joy 11/5 要例句演得出多種施放）：每一句都收得下（中文、字數），
    合起來關鍵字導演就排得出每一種法相出場、主攻路線、對手異狀。"""
    import re
    from pathlib import Path

    js = (Path(__file__).resolve().parents[4] / "web" / "mall.js").read_text(encoding="utf-8")
    body = re.search(r"const MOVE_EXAMPLES = \[(.*?)\];", js, re.S).group(1)
    lines = re.findall(r'"([^"]+)"', body)
    assert "一劍寒光九萬里" in lines and len(lines) >= 9
    seen: dict[str, set] = {"motion": set(), "path": set(), "mark": set()}
    for text in lines:
        assert scenes.text_problem(text) is None and len(text) <= scenes.MAX_TEXT, text
        for b in scenes.direct(text)["beats"]:
            seen["motion"].add(b.get("motion"))
            seen["path"].add(b.get("path"))
            seen["mark"].update({b.get("kind"), b.get("also")} if b["op"] == "異狀" else set())
    assert set(scenes.MOTIONS[1:]) <= seen["motion"] and set(scenes.PATHS[1:]) <= seen["path"] and set(scenes.MARKS) <= seen["mark"]
