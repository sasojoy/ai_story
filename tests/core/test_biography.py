"""玩家傳第二批：季末把行狀寫成《某某傳》（tianxia/biography.py、Game.biography_*）、背景寫傳與公開分享（server.py、zhuan_html.py）、
網頁的傳（web/app.js 的 zhuanHtml）。"""
from __future__ import annotations

import random
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server
import webharness
import zhuan_html
from conftest import next_season
from tianxia import annals, biography, epiphany, gender
from tianxia.engine import Game

ROOT = Path(__file__).parents[2]


@pytest.fixture
def on(content):
    content.config.biography.enabled = True
    content.config.admins = ["管理者"]
    return content


def _game(content, world, name="沈浪"):
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.client = None
    game.sync(0.0)
    return game


def _close(content, world, *players):
    admin = Game.new(content, "管理者", rng=random.Random(1), world=world)
    admin.admin_end_season(now=200.0)
    for p in players:
        p.sync(210.0)


def _request(**kw) -> biography.BiographyRequest:
    base = dict(
        season=1, name="沈浪", scenario="黃巾之亂", era_note="", profile={"level": 12, "faction": "官軍", "good": 9, "evil": 1},
        annals=(
            {"kind": "deed", "when": "第 1 週・週一 08:00", "text": "投靠官軍。", "weight": 4},
            {"kind": "showdown", "when": "第 6 週・週三 20:00", "text": "長社火攻，你站在官軍以先鋒出陣，出手 4 回合，在 12／30 人中排第 3／12。",
             "quote": "點火燒糧", "reply": "沈浪一把火燒了糧車", "weight": 5},
            {"kind": "figure", "when": "第2天 09:00", "text": "跟皇甫嵩的情誼到了 40。", "quote": "久仰", "reply": "好說。", "weight": 3},
        ),
    )
    base.update(kw)
    return biography.BiographyRequest(**base)


# ── 規則版、清理、數字 ──


@pytest.mark.smoke
def test_chinese_numbers():
    assert [biography._cn(n) for n in (0, 7, 10, 15, 20, 21, 105, 1200, 30000)] == [
        "〇", "七", "十", "十五", "二十", "二十一", "一百零五", "一千二百", "三〇〇〇〇"]


def test_the_rule_text_reads_like_a_biography_with_no_arabic_digits_and_no_you():
    text = biography.rule_text(_request())
    paras = text.split("\n\n")
    assert paras[0].startswith("沈浪者，") and paras[-1].startswith("評曰：")
    assert "第一週，投靠官軍。" in paras[0]
    assert "出手四回合" in text and "在十二人中排第三" in text and "沈浪曰：「點火燒糧」" in text
    assert not any(ch.isdigit() for ch in text if ch.isascii()) and "你" not in text
    assert "行事近俠" in text and "至第十二級" in text
    assert "沈浪問曰：「久仰」對曰：「好說。」" in text and "？。" not in text and "。。" not in text
    assert biography._end("贈「踏霜駒」") == "贈「踏霜駒」。" and biography._end("曰：「好。」") == "曰：「好。」"
    assert biography.clean(text, _request()) == text  # 規則版自己也過得了清理的檢查


def test_a_quiet_season_still_gets_a_biography():
    text = biography.rule_text(_request(annals=({"kind": "deed", "text": "拜入流雲派門下。", "weight": 4},), profile={}))
    assert "未嘗與於天下大戰" in text and "生逢黃巾之亂，" in text and text.count("\n\n") == 3


def test_clean_keeps_good_model_text_and_rejects_the_bad():
    req = _request()
    good = "# 沈浪傳\n\n**沈浪者**，潁川人也。" + "少負奇氣，" * 40 + "\n\n評曰：沈浪雖起於草莽，亦一時之選。"
    out = biography.clean(good, req)
    assert out.startswith("沈浪者，潁川人也。") and out.endswith("亦一時之選。") and "#" not in out and "*" not in out
    assert out.count("\n\n") == 1  # 標題那一行拿掉，剩兩段
    assert biography.clean("沈浪者，" + "简体字很多，" * 40, req).find("簡體") >= 0  # 轉成繁體
    assert biography.clean("太短了。沈浪", req) is None
    assert biography.clean("某人者，" + "無名，" * 100, req) is None  # 沒寫到名號
    assert biography.clean("沈浪者，" + "戰了3回合，" * 40, req) is None
    assert biography.clean("沈浪者，" + "ござる，" * 60, req) is None
    assert biography.clean(None, req) is None


# ── 別的玩家的名號（FB-9020）：行狀記下這一則要原樣保留的名號（AnnalEntry.keep），備援文字與清理都照它 ──
# 對手是玩家，名號只擋控制字元與長度：帶「你」、帶阿拉伯數字、帶正負號都有可能。_strip 整句把「你」換成傳主、把數字換成中文，原句同時有代詞
# 「你」與對手名號時光看字串分不出哪個「你」是代詞，所以由寫行狀的那一刻（engine 的 _raid_record 等）把名號記在 keep 裡。

RIVALS = ("你好嗎", "Rival2", "你好嗎2", "A-1", "+3號")
# （種類、原句、傳裡的樣子）：原句是 engine 與各規則檔實際格式出來的，{r} 是對手的名號
KEEP_CASES = {
    "raid（攔人的）": ("fight", "你攔下{r}動手，{r}不敵，丟下銀兩走了。", "沈浪攔下{r}動手，{r}不敵，丟下銀兩走了。"),
    "raid（被攔的）": ("fight", "{r}半路截殺你，反被你打退，丟下銀兩走了。", "{r}半路截殺沈浪，反被沈浪打退，丟下銀兩走了。"),
    "ambush（設伏的）": ("fight", "{r}走進你的埋伏，被你打得丟下財物逃了。", "{r}走進沈浪的埋伏，被沈浪打得丟下財物逃了。"),
    "ambush（路過的）": ("fight", "路上殺出伏兵{r}，你把他打退，搶下他的財物。", "路上殺出伏兵{r}，沈浪把他打退，搶下他的財物。"),
    "melee（出陣的）": ("fight", "{r}正在長社替官軍出力，兩人撞個正著，當場動起手來。你逼退了{r}，這一下推得更多。",
                    "{r}正在長社替官軍出力，兩人撞個正著，當場動起手來。沈浪逼退了{r}，這一下推得更多。"),
    "melee（被撞的）": ("fight", "{r}在長社出陣，撞上了你；你逼退了他，他那一下白跑了。", "{r}在長社出陣，撞上了沈浪；沈浪逼退了他，他那一下白跑了。"),
    "擂台": ("fight", "上擂台挑{r}，大勝。", "上擂台挑{r}，大勝。"),
    "奪璽": ("deed", "你從{r}懷中奪得了『螭首』。", "沈浪從{r}懷中奪得了『螭首』。"),
    "奪璽（守住的）": ("deed", "你擋下了{r}，『螭首』還在你懷中。", "沈浪擋下了{r}，『螭首』還在沈浪懷中。"),
    "約戰（攻方）": ("duel", "在長社約戰{r}，大勝。", "在長社約戰{r}，大勝。"),
    "約戰（守方）": ("duel", "應下{r}在汝南荒野的約戰，落敗。", "應下{r}在汝南荒野的約戰，落敗。"),
}


def _kept_request(kind: str, text: str, keep: list[str] | None, **kw) -> biography.BiographyRequest:
    row = {"kind": kind, "when": "第 3 週・週二 10:00", "text": text, "weight": 5}
    if keep is not None:
        row["keep"] = keep
    return _request(annals=(row,), **kw)


@pytest.mark.parametrize("rival", RIVALS)
@pytest.mark.parametrize("case", sorted(KEEP_CASES))
def test_a_rival_name_stays_as_written_while_the_pronoun_still_becomes_the_subject(case, rival):
    kind, said, wanted = KEEP_CASES[case]
    text = biography.rule_text(_kept_request(kind, said.format(r=rival), [rival]))
    assert wanted.format(r=rival) in text, text
    assert "你" not in text.replace(rival, "")  # 對手名號以外沒有「你」：代詞都換成了傳主
    assert not any(ch.isascii() and ch.isdigit() for ch in text.replace(rival, ""))  # 名號以外沒有阿拉伯數字
    assert "。。" not in text


def test_the_gamble_names_its_target_and_the_reply_keeps_the_name_too():
    rival = "你好嗎2"
    row = {"kind": "showdown", "when": "第 6 週・週三 20:00", "text": f"在長社火攻陣上放手一搏，成了，點名{rival}。", "weight": 4,
           "quote": "點火燒糧", "reply": f"沈浪一把火燒了{rival}的 2 輛糧車", "keep": [rival]}
    text = biography.rule_text(_request(annals=(row,)))
    assert f"在長社火攻陣上放手一搏，成了，點名{rival}。沈浪曰：「點火燒糧」於是沈浪一把火燒了{rival}的二輛糧車。" in text  # 別的數字照舊換中文
    legacy = biography.rule_text(_request(annals=({k: v for k, v in row.items() if k != "keep"},)))
    assert rival not in legacy and "點名沈浪好嗎二" in legacy  # 沒有 keep（舊存檔）：照舊被改


def test_without_keep_the_fallback_reads_exactly_as_before():
    """沒有 keep（存在玩家存檔裡的舊行狀、或這一則沒有別人的名號）：_strip 跟修之前一字不差；keep 裡的名號不在這一句裡也一樣。"""
    def before(text: str, name: str = "") -> str:
        text = biography._plain(text).rstrip("。")
        return text.replace("你", name) if name else text

    samples = ["你攔下你好嗎動手，兩人鬥了半天不分高下，各自退開。", "出手 4 回合，在 12／30 人中排第 3／12，情誼 +6", "你從Rival2懷中奪得了『螭首』。", "", "你"]
    for sample in samples:
        for name in ("沈浪", "", "你好嗎2"):
            assert biography._strip(sample, name) == before(sample, name)
            assert biography._strip(sample, name, None) == biography._strip(sample, name, ()) == biography._strip(sample, name, ["", "不在這一句裡"]) == before(sample, name)


def test_an_all_digit_subject_name_is_not_masked_so_the_same_numbers_still_read_in_chinese():
    """FB-9021：傳主名號整個是數字時不遮，行狀裡湊巧一樣的數目照舊換中文、不漏阿拉伯數字（跟 FB-9020 以前一樣）；代詞照舊換成名號。"""
    assert biography._strip("你到了第 10 級，出手 10 回合", "10") == "10到了第十級，出手十回合"
    assert biography._strip("戰功排第 2／88", "88") == "戰功在八十八人中排第二"
    assert biography._strip("你攔下Rival2動手，出手 4 回合", "4", ["Rival2"]) == "4攔下Rival2動手，出手四回合"  # 對手照舊護著
    assert biography._strip("Zed12打了 12 場", "Zed12") == "Zed12打了十二場"  # 有字母的照護
    model = "10者，" + "天下大亂，" * 60 + "出手 10 回合。"
    assert biography.clean(model, _request(name="10")) is None  # 模型版：整個是數字的傳主名號不遮，有阿拉伯數字照擋


def test_the_placeholders_cannot_be_confused_with_the_text_or_the_names():
    """遮名號用私用區的字元：挑文字、傳主名號、保留名號裡都沒有的；長的名號先遮，免得一個名號是另一個的一部分。"""
    assert biography._strip("你攔下Rival2動手", "沈浪", ["Rival2"]) == "沈浪攔下Rival2動手"
    assert biography._strip("你攔下\ue000動手", "沈浪", ["\ue000"]) == "沈浪攔下\ue000動手"  # 對手名號裡就有私用區的字
    assert biography._strip("你攔下Rival2動手", "\ue000傳主", ["Rival2"]) == "\ue000傳主攔下Rival2動手"  # 傳主名號裡有
    assert biography._strip("你攔下\ue000\ue001動手", "沈浪", ["\ue000", "\ue001"]) == "沈浪攔下\ue000\ue001動手"
    assert biography._strip("你攔下你好嗎2動手，你好也來", "沈浪", ["你好", "你好嗎2"]) == "沈浪攔下你好嗎2動手，你好也來"  # 兩個名號一個包著另一個
    assert biography._strip("你攔下Rival22動手，你攔下Rival2動手", "沈浪", ["Rival2", "Rival22"]) == "沈浪攔下Rival22動手，沈浪攔下Rival2動手"
    assert biography._strip("你攔下A-1動手", "沈浪", ["A-1"]) == "沈浪攔下A-1動手"  # 正負號也不被當成「增減」


def test_the_subjects_own_name_takes_the_pronoun_whole_and_is_never_changed_itself():
    """傳主自己的名號不存在 keep 裡（存檔不重複），_strip 固定把它加進去一起遮：代詞「你」換成他的名號，名號帶「你」或數字也是整個放進去，
    原句照字寫出的傳主名號也不被改（以前會寫成「你好嗎2好嗎二」「Zed二」）。"""
    assert biography._strip("你贏了", "你好嗎2") == "你好嗎2贏了"
    assert biography._strip("你贏了，出手 3 回合", "Rival2") == "Rival2贏了，出手三回合"
    assert biography._strip("你好嗎2頓悟，悟出神品意境「天」。", "你好嗎2") == "你好嗎2頓悟，悟出神品意境「天」"
    assert biography._strip("名號上了〈天下形勢〉第 5 篇：「Zed2下戰書攻荒丘」", "Zed2") == "名號上了〈天下形勢〉第五篇：「Zed2下戰書攻荒丘」"
    assert biography._strip("你攔下Rival2動手，你好嗎2也受了傷", "你好嗎2", ["Rival2"]) == "你好嗎2攔下Rival2動手，你好嗎2也受了傷"  # 對手與傳主各護各的
    assert biography._strip("Zed2一把火燒了糧車 2 輛", "", None, own="Zed2") == "Zed2一把火燒了糧車二輛"  # 不換代詞的那一句（放手一搏的 reply）照樣護傳主名號


@pytest.mark.parametrize("me", ("你好嗎", "Zed2", "你好嗎2", "A-1", "+3號"))
def test_a_sentence_that_writes_the_subjects_own_name_keeps_it_as_written(me):
    """行狀原句照字寫出傳主名號的幾類（〈天下形勢〉那一句、神品意境的首創、奇事收尾；放手一搏播出的那一版也常寫到他）：傳主叫「你好嗎2」「Zed2」
    也原樣；同一句的代詞「你」照舊換成他的名號。"""
    rows = (
        {"kind": "xingshi", "when": "第 3 週・週二 10:00", "text": f"名號上了〈天下形勢〉第 5 篇：「{me}下戰書攻荒丘」", "weight": 3},
        {"kind": "story", "when": "第 4 週・週二 10:00", "text": epiphany.FIRST_ANNAL.format(name=me, insight="天人"), "weight": 5},
        {"kind": "story", "when": "第 5 週・週二 10:00", "text": f"{me}替人傳了一封信，你也在場。", "weight": 4},
        {"kind": "showdown", "when": "第 6 週・週三 20:00", "text": "在長社火攻陣上放手一搏，成了。", "weight": 4, "quote": "點火燒糧",
         "reply": f"{me}一把火燒了糧車 2 輛"},
    )
    text = biography.rule_text(_request(name=me, annals=rows))
    assert f"第三週，名號上了〈天下形勢〉第五篇：「{me}下戰書攻荒丘」" in text
    assert f"第四週，{me}頓悟，悟出神品意境「天人」" in text
    assert f"第五週，{me}替人傳了一封信，{me}也在場" in text
    assert f"{me}曰：「點火燒糧」於是{me}一把火燒了糧車二輛" in text
    assert biography.clean(text.replace("\n\n", "\n\n" + "起於潁川，" * 40, 1), _request(name=me, annals=rows)) is not None  # 傳主名號帶數字也過得了清理


def _sys(name: str = "沈浪", sex: str = "男", note: bool = False) -> str:
    """系統提示的樣子：note 是規矩 4 後面多一句名號的（先改範本再填名號）。"""
    template = biography.SYSTEM.replace(biography.RULE4_END, biography.RULE4_END + biography.NAME_NOTE, 1) if note else biography.SYSTEM
    return template.format(name=name, him=gender.pronoun(sex), word=gender.word(sex))


def test_the_prompt_gains_one_sentence_only_when_a_name_carries_an_ascii_digit():
    """PM 2026-10-29：這一篇有名號帶阿拉伯數字（傳主名號或任何一則 keep）時，規矩 4 後面接「名號照事實清單原樣寫，…」，免得模型把 Rival2 寫成
    Rival二；沒有這種名號的篇系統提示一個字不變（名號帶「你」、沒有數字的也不變）。"""
    row = {"kind": "fight", "when": "第 3 週・週二 10:00", "text": "你攔下你好嗎動手。", "weight": 3}
    assert biography.messages(_request())[0]["content"] == _sys()
    assert biography.messages(_request(annals=({**row, "keep": ["你好嗎"]},)))[0]["content"] == _sys()
    assert biography.messages(_request(annals=({**row, "text": "你攔下Rival2動手。"},)))[0]["content"] == _sys()  # 沒有 keep 的舊行狀：不算
    for req in (_request(name="沈浪2"), _request(annals=({**row, "keep": ["Rival2"]},)), _request(annals=(row, {**row, "keep": ["甲２"]})),
                _request(name="Ｘ１", annals=({**row, "keep": []},)), _request(annals=({**row, "keep": ["A-1"]},), sex="女")):
        got = biography.messages(req)[0]["content"]
        assert got == _sys(req.name, req.sex, note=True)
        assert got.count(biography.NAME_NOTE) == 1
        assert f"清單裡沒有的數目不寫。{biography.NAME_NOTE}\n5. " in got  # 接在規矩 4 後面、5 之前
    assert not any(ch.isascii() and ch.isdigit() for ch in biography.NAME_NOTE) and "你" not in biography.NAME_NOTE
    # 名號不是範本：名號剛好叫「清單裡沒有的數目不寫。」也只在規矩 4 後面多那一句
    odd = biography.RULE4_END
    assert biography.messages(_request(name=odd + "2"))[0]["content"] == _sys(odd + "2", note=True)
    assert f"{odd}{biography.NAME_NOTE}\n5. " in biography.messages(_request(name=odd + "2"))[0]["content"]  # 名號裡的那一段沒被當成範本
    # 事實清單的格式不動：名號本來就原樣
    kept, plain = _request(annals=({**row, "text": "你攔下Rival2動手。", "keep": ["Rival2"]},)), _request(annals=({**row, "text": "你攔下Rival2動手。"},))
    assert biography.outline(kept) == biography.outline(plain) and "你攔下Rival2動手" in biography.outline(kept)
    assert biography.messages(kept)[1] == biography.messages(plain)[1]  # 給模型的第二則（事實清單）一樣


def test_clean_lets_a_name_with_digits_through_but_nothing_else():
    """模型照事實清單把對手的名號（Rival2）原樣寫進傳：名號是行狀的 keep，檢查阿拉伯數字之前先遮掉；傳主自己的名號也一樣。其他數字照擋。"""
    row = {"kind": "fight", "when": "第 3 週・週二 10:00", "text": "你攔下Rival2動手。", "weight": 3, "keep": ["Rival2"]}
    req = _request(annals=(row,))
    body = "沈浪者，" + "起於潁川，" * 40 + "曾攔下Rival2動手，不分高下。"
    assert biography.clean(body, req) == body
    assert biography.clean(body, _request(annals=({k: v for k, v in row.items() if k != "keep"},))) is None  # 沒有 keep：照舊擋
    assert biography.clean(body + "前後戰了3回合。", req) is None  # 別的數字照擋
    assert biography.clean(body.replace("Rival2", "Rival22"), req) is None  # 名號後面多一個數字：不是那個名號
    assert biography.clean(body.replace("Rival2", "Rival2０"), req) is None  # 全形數字也一樣
    own = _request(name="沈浪2", annals=({**row, "keep": []},))
    assert biography.clean("沈浪2者，" + "起於潁川，" * 40 + "與Rival二周旋。", own) is not None  # 傳主名號帶數字
    assert biography.clean("沈浪2者，" + "起於潁川，" * 40 + "戰了3回合。", own) is None


def test_the_model_is_asked_with_the_facts_and_failures_fall_back_to_none():
    class Fake:
        timeout, retry = 99, True

        def __init__(self, reply):
            self.reply, self.asked = reply, None

        def chat_text(self, messages, **kw):
            self.asked = (messages, self.timeout, self.retry)
            if isinstance(self.reply, Exception):
                raise self.reply
            return self.reply

    req = _request(rewrite=True)
    fake = Fake("沈浪者，" + "起於潁川，" * 50)
    assert biography.write(fake, req, 30).startswith("沈浪者")
    assert fake.asked is None and fake.timeout == 99  # 原本那一份不動：叫的是複本
    msgs = biography.messages(req)
    assert "沈浪者，" in msgs[0]["content"] and "長社火攻" in msgs[1]["content"] and "【大戰】" in msgs[1]["content"]
    assert "換一種起筆" in msgs[1]["content"]
    assert biography.write(Fake(RuntimeError("down")), req, 30) is None
    assert biography.write(Fake("太短"), req, 30) is None
    assert biography.write(None, req, 30) is None and biography.write(fake, req, 0) is None


def test_lead_is_the_first_paragraph_clipped():
    assert biography.lead("甲乙。\n\n丙丁。") == "甲乙。"
    assert biography.lead("長" * 150, 100) == "長" * 99 + "…"


# ── 引擎：開單、寫、看、分享 ──


def test_nothing_can_be_written_while_the_season_runs_or_the_switch_is_off(on, world):
    game = _game(on, world)
    annals.note(game.state, on, annals.DEED, "投靠官軍。", 4)
    assert game.biography_request(1) is None and game.biography_entry() is None and game.biography_view(1) is None
    on.config.biography.enabled = False
    _close(on, world, game)
    assert game.biography_request(1) is None and game.biography_entry() is None


def test_a_closed_season_is_written_once_and_rewritten_once(on, world):
    game = _game(on, world)
    annals.note(game.state, on, annals.DEED, "投靠官軍。", 4)
    _close(on, world, game)
    assert game.biography_entry() == {"season": 1, "title": "沈浪傳"}
    assert game.annals_view()["books"] == [{"season": 1, "title": "沈浪傳", "written": False, "public": False}]
    view = game.biography_view(1)
    assert view["written"] is False and view["can_write"] is True
    assert game.biography_request(1, rewrite=True) is None  # 還沒寫過，不能重寫
    req = game.biography_request(1)
    assert req.annals[0]["text"] == "投靠官軍。" and req.profile["name"] == "沈浪"
    assert game.write_biography(req, None, 5.0) is True  # 模型寫不出來：照規則拼
    view = game.biography_view(1)
    assert view["written"] and view["by"] == biography.RULE and view["paragraphs"][0].startswith("沈浪者，")
    assert view["can_rewrite"] is True and view["public"] is False and view["code"] is None
    assert game.biography_request(1) is None  # 寫過了，不能再「寫」
    again = game.biography_request(1, rewrite=True)
    model_text = "沈浪者，" + "起於潁川，" * 50
    assert game.write_biography(again, model_text, 6.0) is True
    view = game.biography_view(1)
    assert view["by"] == biography.MODEL and view["paragraphs"] == [model_text] and view["can_rewrite"] is False
    assert game.biography_request(1, rewrite=True) is None and game.write_biography(again, model_text, 7.0) is False


def test_a_stale_request_is_dropped(on, world):
    game = _game(on, world)
    annals.note(game.state, on, annals.DEED, "投靠官軍。", 4)
    _close(on, world, game)
    req = game.biography_request(1)
    annals.note(game.state, on, annals.DEED, "又多了一件。", 4)  # 季收了之後才補進來的決戰
    assert game.write_biography(req, None, 5.0) is False and game.biography_view(1)["written"] is False


def test_sharing_hands_out_one_code_and_can_be_taken_back(on, world):
    game = _game(on, world)
    annals.note(game.state, on, annals.DEED, "投靠官軍。", 4)
    _close(on, world, game)
    assert game.share_biography(1, True, "abc") is None  # 還沒寫成
    game.write_biography(game.biography_request(1), None, 5.0)
    assert game.share_biography(1, True, "abc") == "abc"
    assert world.biography_by_code("abc")["name"] == "沈浪" and game.biography_view(1)["code"] == "abc"
    assert game.share_biography(1, False, "zzz") == "abc" and world.biography_by_code("abc") is None
    assert game.biography_view(1)["code"] is None
    assert game.share_biography(1, True, "zzz") == "abc"  # 再公開沿用同一個代碼，舊網址又能用
    assert world.biography_by_code("zzz") is None and world.biography_by_code("abc") is not None


def test_last_seasons_biography_can_still_be_written_after_the_new_season_starts(on, world):
    game = _game(on, world)
    annals.note(game.state, on, annals.DEED, "上一季的事。", 4)
    next_season(on, world, game)
    assert game.biography_entry() is None  # 新的一季在跑
    assert [b["season"] for b in game.annals_view()["books"]] == [1]
    req = game.biography_request(1)
    assert req is not None and req.annals[0]["text"] == "上一季的事。"
    assert game.write_biography(req, None, 500.0) is True and game.biography_view(1)["written"]


def test_bots_never_get_a_biography(on, world):
    from tianxia.state import BotProfile

    game = _game(on, world)
    game.state.player.bot = BotProfile(personality="普通", seed=1)
    annals.note(game.state, on, annals.DEED, "投靠官軍。", 4)
    _close(on, world, game)
    assert game.biography_entry() is None and game.biography_request(1) is None and game.share_biography(1, True, "x") is None


# ── 伺服器：背景寫傳、分享、公開頁 ──


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server.CONTENT.config, "auto_open_first_season", True)
    monkeypatch.setattr(server.CONTENT.config, "admins", list(server.CONTENT.config.admins))
    for store in (server.LOGIN_FAILURES, server.SESSIONS, server.GAMES):
        store.clear()
    server.WORLD_GAME = None
    server.QUEUE = None
    server.ZHUAN_JOBS.clear()
    yield TestClient(server.app)
    for store in (server.LOGIN_FAILURES, server.SESSIONS, server.GAMES):
        store.clear()
    server.WORLD_GAME = None


def _closed_player(client):
    client.post("/api/register", json={"login": "shen_01", "password": "secret-pw", "again": "secret-pw"})
    client.post("/api/character", json={"name": "沈青衫"})
    client.post("/api/do/skip_tutorial", json={})
    game = server.game_for("沈青衫")
    game.client = None
    server.act(game, lambda g: annals.note(g.state, server.CONTENT, annals.DEED, "投靠官軍。", 4))
    server.CONTENT.config.admins = ["沈青衫"]  # 名號建好之後才當管理者（玩家不能取管理者的名號）；client 那一份 fixture 收回
    server.act(game, lambda g: g.admin_end_season(now=g.now), paused_ok=True)
    assert game.world.season_phase() == "resting"
    return game


def _wait_written(client):
    for _ in range(200):
        view = client.get("/api/zhuan?season=1").json()
        if view["written"] and not view["writing"]:
            return view
        time.sleep(0.02)
    raise AssertionError("寫不完")


def test_the_server_writes_in_the_background_shares_and_serves_the_public_page(client, monkeypatch):
    from tianxia import accounts

    monkeypatch.setattr(accounts, "SCRYPT_PARAMS", {"n": 2, "r": 1, "p": 1, "dklen": 32})
    monkeypatch.delenv(server.PUBLIC_URL_ENV, raising=False)
    _closed_player(client)
    main = client.get("/api/main").json()
    assert main["zhuan"] == {"season": 1, "title": "沈青衫傳"}
    assert client.post("/api/zhuan/share", json={"season": 1, "public": True}).status_code == 400  # 還沒寫成
    out = client.post("/api/zhuan/write", json={"season": 1})
    assert out.status_code == 200
    view = _wait_written(client)
    assert view["paragraphs"][0].startswith("沈青衫者，") and view["by"] == "rule" and view["can_rewrite"]
    assert client.post("/api/zhuan/write", json={"season": 1}).status_code == 400  # 寫過了
    shared = client.post("/api/zhuan/share", json={"season": 1, "public": True}).json()
    code = shared["code"]
    assert shared["public"] and shared["url"] == f"http://testserver/zhuan/{code}"
    page = TestClient(server.app).get(f"/zhuan/{code}", headers={"x-forwarded-proto": "https"})  # 不用登入
    assert page.status_code == 200
    html = page.text
    assert '<meta property="og:title" content="沈青衫傳">' in html
    assert f'<meta property="og:url" content="https://testserver/zhuan/{code}">' in html
    assert 'content="https://testserver/static/zhuan-og.png"' in html and "沈青衫者，" in html
    monkeypatch.setenv(server.PUBLIC_URL_ENV, "https://tianxia.example/")
    assert client.get("/api/zhuan?season=1").json()["url"] == f"https://tianxia.example/zhuan/{code}"
    taken = client.post("/api/zhuan/share", json={"season": 1, "public": False}).json()
    assert taken["public"] is False and "url" not in taken
    gone = TestClient(server.app).get(f"/zhuan/{code}")
    assert gone.status_code == 404 and "查無此傳" in gone.text
    assert TestClient(server.app).get("/zhuan/nope").status_code == 404


def test_the_rewrite_uses_the_model_when_it_answers(client, monkeypatch):
    from tianxia import accounts

    monkeypatch.setattr(accounts, "SCRYPT_PARAMS", {"n": 2, "r": 1, "p": 1, "dklen": 32})
    game = _closed_player(client)
    client.post("/api/zhuan/write", json={"season": 1})
    _wait_written(client)
    text = "沈青衫者，" + "起於潁川，" * 50

    class Fake:
        timeout, retry = 10, True

        def chat_text(self, messages, **kw):
            return text

    game.client = Fake()
    assert client.post("/api/zhuan/write", json={"season": 1, "rewrite": True}).status_code == 200
    for _ in range(200):
        view = client.get("/api/zhuan?season=1").json()
        if view["by"] == "model":
            break
        time.sleep(0.02)
    assert view["paragraphs"] == [text] and view["can_rewrite"] is False
    assert client.post("/api/zhuan/write", json={"season": 1, "rewrite": True}).status_code == 400


def test_the_public_page_escapes_and_marks_the_verdict():
    row = {"name": "<b>沈</b>", "season": 2, "text": "<b>沈</b>者，<script>x</script>。\n\n評曰：好。"}
    html = zhuan_html.page(row, "黃巾之亂", "https://x/zhuan/a", "https://x/static/zhuan-og.png")
    assert "<script>x</script>" not in html and "&lt;script&gt;" in html
    assert '<p class="ping">評曰：好。</p>' in html and "第 2 季・黃巾之亂" in html
    assert '<meta name="robots" content="noindex">' in html


def test_the_share_image_is_a_1200_by_630_png():
    data = (ROOT / "web" / "zhuan-og.png").read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert int.from_bytes(data[16:20], "big") == 1200 and int.from_bytes(data[20:24], "big") == 630


# ── 網頁：江湖頁的入口、傳的書頁 ──

DRIVER = r"""
const S = { zhuanVertical: !!input.vertical };
const parts = [konst("esc"), konst("ZHUAN_VERTICAL"), konst("slipSize"), fn("zhuanIcon"), fn("zhuanVertical"), fn("zhuanHead"), fn("zhuanSeal"), fn("zhuanHtml"), fn("zhuanEntry"),
  "return { zhuanHtml, zhuanEntry };"];
const H = new Function("S", parts.join("\n"))(S);
finish(input.entry ? H.zhuanEntry(input.entry, "副題") : H.zhuanHtml(input.z));
"""


def _web(**inp):
    return webharness.run(DRIVER, inp)


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_the_reader_draws_each_state():
    written = {"season": 1, "title": "沈<浪>傳", "written": True, "paragraphs": ["沈浪者，<i>x</i>。", "評曰：好。"],
               "public": False, "can_rewrite": True, "scenario": "黃巾之亂"}
    html = _web(z={"season": 1, "view": written})
    assert "沈&lt;浪&gt;傳" in html and "&lt;i&gt;x" in html and '<p class="ping">評曰：好。</p>' in html
    assert 'data-act="zhuan-share" data-public="1"' in html and 'data-act="zhuan-rewrite"' in html and "第 1 季・黃巾之亂" in html
    assert 'aria-pressed="false"' in html and "zh-text vertical" not in html
    shared = _web(z={"season": 1, "view": {**written, "public": True, "url": "https://x/zhuan/<a>", "can_rewrite": False}}, vertical=True)
    assert "https://x/zhuan/&lt;a&gt;" in shared and 'data-act="zhuan-send"' in shared and 'data-public="0"' in shared
    assert 'data-act="zhuan-rewrite"' not in shared and "zh-text vertical" in shared
    waiting = _web(z={"season": 1, "view": {"season": 1, "title": "沈浪傳", "written": False, "can_write": True, "writing": True}})
    assert "史官正在落筆" in waiting and 'data-act="zhuan-write"' not in waiting
    ready = _web(z={"season": 1, "view": {"season": 1, "title": "沈浪傳", "written": False, "can_write": True}})
    assert 'data-act="zhuan-write"' in ready
    assert "翻開史冊" in _web(z={"season": 1, "view": None})
    entry = _web(entry={"season": 3, "title": "沈浪傳", "written": False})
    assert 'data-act="zhuan-open" data-season="3"' in entry and "立傳 ›" in entry


def test_the_page_wires_the_entries_and_the_handlers():
    src = webharness.app_source()
    for needle in ('case "zhuan-open"', 'case "zhuan-write"', 'case "zhuan-share"', 'case "zhuan-send"', 'case "zhuan-rewrite"',
                   "m.zhuan ? zhuanEntry(", "歷季列傳", 'api(`/api/zhuan?season='):
        assert needle in src, needle
