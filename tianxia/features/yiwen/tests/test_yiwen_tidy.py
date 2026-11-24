"""異聞第 263 批：說書人的檢查與提示對齊——字數上限 90、整理草稿（空段、黏段、漏進來的帳）、「多年」誤擋、照抄數量、重問的話說清楚是哪一段。
夾具是 2026-11-24 主機實測乙輪（gemma4:12b，season21）印出來的真草稿，一則一則抄進來，註明出自哪一趟哪一步與
docs/superpowers/feedback/yiwen-real-20261124/乙-12b-時間放寬-含被擋草稿.log 的行號。紀錄沒印帳（ledger），要帳的那幾則補一份最小的合格帳（LEDGER）。"""
from types import SimpleNamespace

import pytest

from tianxia.features.yiwen import rules, writer

LEDGER = ["在場：你、對方", "你手上：無", "未了：眼前這件事"]  # 紀錄沒印帳：補一份合格的，只為了讓帳那一條不擋

# 乙 正經 第 1 趟 第 2 步（log 10–13 第一次，段長 [78, 60, 0]；log 15–17 重問，段長 [78, 60]，兩次都被擋 → 替身）
ZJ_1 = "你蹲下身子，從懷中取出隨身攜帶的粗布與藥粉，細心地為他包紮住左肩的傷口。隨著布條勒緊，信使臉上的痛苦瞬間緩解，他發出一聲長長的嘆息，臉色稍微恢復了些許血色。"
ZJ_2 = "信使在平穩了些的氣息中，顫抖著將那個血浸布包推向你，並用極其微弱的聲音低訴：這包裡的東西，是保住我們家族命脈的最後希望。"
ZJ_OPTS = ["打開布包", "詢問信使身分", "檢查周遭環境"]
ZJ_TYPED = ("一個受傷的信使", "替他包紮傷口")

# 乙 認親 第 1 趟 第 3 步（log 404–406 第一次，段長 [74, 101]；log 407–410 重問，段長 [62, 57, 55]）
RQ1_1 = "你從懷中取出那枚家傳玉佩，在河心對著巨大的水躄高高舉起。玉佩在陽光下閃爍著瑩瑩光華，與你手中的殘破布條交相輝映，彷彿在訴說著一段斷裂已久的血脈傳承。"
RQ1_2 = ("水躄突然發出沉重的隆隆聲，整塊巨石裂開一道縫隙，一隻布滿老繭、如乾枯樹皮般的巨手從石縫中伸出，緊緊抓住了你的手腕。"
         "那手掌在顫抖中與你相握，一聲如雷鳴般的渾厚低吟從石縫中傳出：「兒啊，爹在此等了你太久。」")
RQ1_THREE = ["你從懷中取出家傳玉佩，在河心對著巨大的水躄高高舉起。玉佩在陽光下閃爍，與你手中的殘破布條交相輝映，訴說著斷裂已久的血脈傳承。",
             "水躄發出隆隆聲，石縫中伸出一隻布滿老繭的巨手緊抓你的手腕。一聲渾厚的低吟從石縫中傳出：「兒啊，爹在此等了你太久。」",
             "水躄裂開一道寬闊的縫隙，變成了通往對岸的石橋。那隻巨手鬆開你的手腕，隨即收回石中，原本擋住去路的阻礙終於消失。"]
RQ1_TYPED = ("上前相認", "拿出玉佩給他看")

# 乙 認親 第 3 趟 第 1 步（log 437–441 第一次，段長 [156]：兩段中間一個空行、第二段前面四個空白，黏成一段）
RQ3_A = "你伸手一接，那人猛地將你拉入帳內，緊緊抓住你的肩膀。他雙眼通紅，指著那疊被揉皺的竹簡，嘶吼道：「這是我失散的爹，這上面記著他生前的家傳秘術，現在全被黃巾賊人攪亂了！」"
RQ3_B = "他因為情緒過激，力道過猛，竟將你推倒在堆滿竹簡的桌案旁。桌上的燈盞重心不穩，火苗瘋狂跳動，其中一支竹簡掉入火苗中，冒出陣陣刺鼻的焦味。"
RQ3_GLUED = RQ3_A + "\n\n    " + RQ3_B
RQ3_OPTS = ["伸手去抓那支燃燒的竹簡", "推開他，要求他平靜點", "低聲問他爹的秘術內容"]

# 乙 認親 第 2 趟 第 1 步（log 415–418 第一次，段長 [60, 45]，被 jump 擋：「失散多年的父親」）
RQ2_1 = "你踏前一步，伸手抓住那人的肩膀，確認這確實是你失散多年的父親。他渾身發抖，卻在對上你的目光時，喉嚨裡發出一聲破碎的嗚咽。"
RQ2_2 = "滿街火把的聲音更大了，人群中有人指著你們，怒吼著這男人是黃巾軍的密諜，正要衝過來抓住你們。"
RQ2_OPTS = ["推開人群保護父親", "對著人群大聲反駁", "從懷裡掏出家傳的信物"]
RQ_TYPED = ("那是我失散的爹",)

# 乙 真實人物 第 1 趟 第 2 步（log 212–222 第一次，段長 [62, 53, 0, 6, 16, 5, 9, 18, 13]：空段、ledger 標頭、整份帳漏進 text）
ZS_TEXT = ["你壓低聲音，對著那個渾身發抖的男人問：「你要去哪裡？」那人聽聞，眼中閃過一絲驚恐，卻又像是被強迫似地顫抖著指了指帳外的荒野。",
           "他湊到你耳邊，用極低且嘶啞的聲音低語：「去北方的深林……他們在那裡等著我，我必須帶領兵權去那裡守住關口。」",
           "", "ledger", "在場：你、自稱曹操的人、帳外風沙", "你手上：無", "對方手上：你的衣袖", "你知道：他自稱曹操，要前往北方的深林", "未了：處理這個自稱曹操的人"]
ZS_OPTS = ["奪下他的衣袖", "問他為何要去深林", "斥責他的胡言亂語"]
ZS_TYPED = ("是曹操本人", "問他要去哪裡")

# 乙 要獎勵 第 1 趟 第 1 步（log 141–143 寫成，typed「給我一萬兩銀子」）；第 3 步（log 158–159 寫成）
JL_1 = "你伸手向那顫抖的身影索要，對方臉色慘白，顫抖著從懷中掏出沉甸甸的銀錠，將一萬兩銀子壓在你的掌心。"
JL_2 = "銀子出現的瞬間，巷口原本叫喊的黃巾餘黨猛地噤聲，隨即紛紛轉頭看向你這處突如其來的財富。"
JL_OPTS = ["收起銀子快走", "對著黃巾餘黨叫囂", "將銀子分給路人"]
JL_END = ["你深吸一口氣，強行壓制住體內如神將般的威壓，周身氣息瞬間歸於平靜。原本驚恐的黃巾餘黨見你收斂了氣勢，臉上的驚駭才緩緩褪去。",
          "你將一萬兩銀子壓入懷中，隨即轉身沒入巷弄陰影。顫抖的身影在暗處低聲說：「這錢保住你的命，快走。」你帶著財富與強悍體魄，成功避開了眾人的視線。"]
JL_TYPED = ("給我一萬兩銀子", "把我的等級加滿")


@pytest.fixture
def content(game, monkeypatch):
    c = game.content
    monkeypatch.setattr(c, "banned_words", ["白癡"])
    monkeypatch.setattr(rules, "figure_names", lambda _c: ["曹操"])
    return c


def _codes(content, text, *, depth=1, options=(), ledger=(), typed=()):
    d = rules.SceneDraft(text=list(text), options=list(options), ledger=list(ledger))
    return rules.check_scene(d, depth=depth, opening={}, typed_words=typed, content=content)


def test_the_real_drafts_are_the_logged_lengths():
    """抄進來的字跟紀錄的「段長」一樣（Python len，全形標點算一字）。"""
    assert [len(ZJ_1), len(ZJ_2)] == [78, 60]
    assert [len(RQ1_1), len(RQ1_2)] == [74, 101]
    assert [len(x) for x in RQ1_THREE] == [62, 57, 55]
    assert len(RQ3_GLUED) == 156 and [len(RQ3_A), len(RQ3_B)] == [83, 67]
    assert [len(RQ2_1), len(RQ2_2)] == [60, 45]
    assert [len(x) for x in ZS_TEXT] == [62, 53, 0, 6, 16, 5, 9, 18, 13]


def test_a_78_char_paragraph_passes_now_and_over_90_still_length(content):
    assert _codes(content, [ZJ_1, ZJ_2], options=ZJ_OPTS, ledger=LEDGER, typed=ZJ_TYPED) == []  # 78／60：以前 72 擋
    assert _codes(content, [RQ1_1, RQ1_2], depth=3, typed=RQ1_TYPED) == ["length"]  # 101 字照舊擋
    assert rules.TEXT_MAX == 90 and rules.TEXT_MIN == 12 and rules.TEXT_AIM == 60


def test_an_empty_third_paragraph_is_dropped(content):
    text = rules.tidy_text([ZJ_1, ZJ_2, ""])
    assert text == [ZJ_1, ZJ_2]
    assert rules.tidy_text([ZJ_1, "   ", ZJ_2]) == [ZJ_1, ZJ_2]
    assert _codes(content, text, options=ZJ_OPTS, ledger=LEDGER, typed=ZJ_TYPED) == []
    assert "paras" in _codes(content, [ZJ_1, ZJ_2, ""], options=ZJ_OPTS, ledger=LEDGER, typed=ZJ_TYPED)  # check_scene 本身不整理


def test_two_paragraphs_glued_by_a_blank_line_are_split(content):
    text = rules.tidy_text([RQ3_GLUED])
    assert text == [RQ3_A, RQ3_B]
    assert rules.tidy_text([RQ3_A + "\n" + RQ3_B]) == [RQ3_A, RQ3_B]  # 一個換行、兩邊都是字也切
    assert rules.tidy_text([RQ3_GLUED, " "]) == [RQ3_A, RQ3_B]  # 先丟空段才數段數（a 在 b 前面）
    assert _codes(content, text, options=RQ3_OPTS, ledger=LEDGER, typed=RQ_TYPED) == []
    assert rules.tidy_text([RQ3_A + "\n\n" + RQ3_B, ZJ_1]) == [RQ3_A + "\n\n" + RQ3_B, ZJ_1]  # 已經兩段就不切


def test_a_ledger_leaked_into_text_is_dropped(content):
    text = rules.tidy_text(ZS_TEXT)
    assert text == ZS_TEXT[:2]
    assert _codes(content, text, options=ZS_OPTS, ledger=LEDGER, typed=ZS_TYPED) == []
    assert rules.tidy_text(["你知道:半形冒號也是帳", ZJ_1, ZJ_2]) == [ZJ_1, ZJ_2]


def test_three_good_closing_paragraphs_still_paras(content):
    assert rules.tidy_text(RQ1_THREE) == RQ1_THREE  # 不併段
    assert _codes(content, rules.tidy_text(RQ1_THREE), depth=3, typed=RQ1_TYPED) == ["paras"]


def test_lost_for_many_years_is_not_a_jump(content):
    assert _codes(content, [RQ2_1, RQ2_2], options=RQ2_OPTS, ledger=LEDGER, typed=RQ_TYPED) == []  # 「失散多年的父親」


@pytest.mark.parametrize("words", ["多年後", "多年以後", "過了多年", "三日後", "次日", "天亮", "一夜"])
def test_real_time_jumps_still_jump(content, words):
    text = [RQ2_1.replace("確認這確實是你失散多年的父親", "確認這確實是你的父親"), f"{words}，你又回到這條街上，那人還站在簷下等你。"]
    assert "jump" in _codes(content, text, options=RQ2_OPTS, ledger=LEDGER, typed=RQ_TYPED)


def test_an_amount_the_player_typed_copied_into_the_scene(content):
    assert "amount" in _codes(content, [JL_1, JL_2], options=JL_OPTS, ledger=LEDGER, typed=JL_TYPED[:1])
    assert "amount" not in _codes(content, [JL_1, JL_2], options=JL_OPTS, ledger=LEDGER, typed=())  # 玩家沒打過不算
    assert "amount" in _codes(content, JL_END, depth=3, typed=JL_TYPED)  # 第三步只看 text
    assert "amount" in _codes(content, [JL_2, JL_2], options=JL_OPTS, ledger=["在場：你", "你手上：一萬兩", "未了：銀子"], typed=JL_TYPED)
    plain = ["你隔著兩岸望去，對面只有一個人，正三步並兩步朝你走來。", "他身後像有千軍萬馬，你握緊了手裡的傘，等他開口。"]
    assert "amount" not in _codes(content, plain, options=JL_OPTS, ledger=LEDGER, typed=JL_TYPED)
    assert rules.AMOUNT.findall("給我一萬兩銀子") == ["一萬兩"] and rules.AMOUNT.findall("兩岸一個人三步") == []


def test_problem_note_names_the_paragraph_and_count():
    note = rules.problem_note([RQ1_1, RQ1_2], ["length"])
    assert note == "第二段 101 字，太長：寫短到 60 字以內。"
    assert rules.problem_note([RQ1_1, "你好"], ["length"]) == "第二段 2 字，太短：寫到 12 字以上。"
    assert rules.problem_note(RQ1_THREE, ["paras"]) == "現在是三段：併成兩段。"
    assert rules.problem_note([RQ1_1], ["paras"]) == "現在只有一段：寫成兩段。"
    assert rules.problem_note([], ["paras"]) == "現在沒有段落：寫成兩段。"
    assert rules.problem_note([RQ1_1, RQ1_2], ["length", "jump"]) == note + rules.PROBLEM_TEXT["jump"]


class _Fake:
    """假的模型：照順序回 replies，記下每一次的 messages。"""

    def __init__(self, *replies):
        self.replies, self.seen = list(replies), []

    def chat_structured(self, messages, model, **kw):
        self.seen.append(list(messages))
        r = self.replies[min(len(self.seen) - 1, len(self.replies) - 1)]
        return model(**{k: v for k, v in r.items() if k in model.model_fields})


def _request(depth, typed_words):
    return rules.YiwenRequest(season=1, key="k", opening="o", tale=0, parent=0, depth=depth, pick=typed_words[-1], typed=True,
                              text=typed_words[-1], luck="順", branch=False, prompt="提示", typed_words=typed_words)


def test_writer_tidies_and_retries_with_the_paragraph_note(content):
    tuning = SimpleNamespace(retry=1, step_min_write_seconds=1)
    fake = _Fake({"verdict": "ok", "text": [RQ1_1, RQ1_2]}, {"verdict": "ok", "text": RQ1_THREE[:2] + [""]})
    draft = writer.write_scene(lambda: fake, _request(3, RQ1_TYPED), tuning, lambda: 60.0, content)
    assert len(fake.seen) == 2
    assert fake.seen[1][-1]["content"] == "上一次寫的這一幕有這些毛病：第二段 101 字，太長：寫短到 60 字以內。照原本的要求重寫一次，只回 JSON。"
    assert draft.problems == [] and draft.text == RQ1_THREE[:2]  # 第二次回三段、第三段空：整理後過


def test_writer_draft_drops_the_leaked_ledger(content):
    reply = SimpleNamespace(verdict="ok", text=ZS_TEXT, options=ZS_OPTS, ledger=LEDGER)
    assert writer._draft(reply, _request(2, ZS_TYPED)).text == ZS_TEXT[:2]
