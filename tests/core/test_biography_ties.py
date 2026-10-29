"""減法季 7e：列傳讀三類新行狀——人物心意（annals.STANCE）、託付辦成（annals.ERRAND，批 6）、出陣約戰（annals.DUEL，批 3b）。

這三類早就靠 annals.GROUPS 歸段（STANCE、ERRAND 在「與英雄交往」，DUEL 在「單打獨鬥」），事實清單（outline）與備援文字（rule_text）
照一般的事讀得到；7e 多的是兩件：
- 提示詞（biography.SYSTEM）：清單裡有這三類的那一篇多一條 TIES_RULE（眾人合力的心意不寫成一人說動、約戰勝負只用清單裡的字）；
- 備援文字：人物交談多、單挑多的人，備援文字只取前幾則、這三類被擠掉——替它們留一半位子，補主詞與時刻（TIES_LINE，待 joy 潤）。
這兩件只在列傳為終點（zhuan_end）開著時（身家有 contrib）才有；關著的季、存起來的舊身家、沒有這三類的篇，提示詞、事實清單、備援文字
一個字不變。痕跡（MARK，批 4）有記、列傳早就讀（行事那一段，備援文字接在行事後面），7e 沒有動它。"""
from __future__ import annotations

import random

import pytest

from wins_kit import save, wins_content, wins_game
from tianxia import annals, biography, gender, sortie_duel
from tianxia.characters import CharacterStore
from tianxia.engine import Game

NOW = 1_800_000_000.0
ADMIN = "論功官"

STANCE_TEXT = "眾人勸盧植速戰，你也是其中之一：盧植聽了眾人之勸，決意速攻廣宗。"  # annals.STANCE 的原句（stances.ANNAL＋內容）
ERRAND_TEXT = "替盧植把一封軍書送到長社，親手交給皇甫嵩，辦成了。"  # annals.ERRAND 的原句（engine._errand_reward＋內容）
DUEL_TEXT = "在長社約戰衛重，大勝。"  # annals.DUEL 的原句（sortie_duel.ANNAL_LINE）
ZHUAN = {"level": 12, "faction": "官軍", "contrib": 40}  # 列傳為終點開著：身家有 contrib（沒有階的人也有）
CLOSED = {"level": 12, "faction": "官軍"}  # 關著的季、7b 以前存起來的舊身家：沒有 contrib


def _e(kind: str, text: str, week: int = 2, weight: int = 2, **kw) -> dict:
    return {"kind": kind, "when": f"第 {week} 週・週二 10:00", "text": text, "weight": weight, **kw}


def _request(*rows: dict, profile: dict | None = None, **kw) -> biography.BiographyRequest:
    base = dict(season=1, name="沈浪", scenario="黃巾之亂", era_note="", profile=ZHUAN if profile is None else profile,
                annals=(_e("deed", "投靠官軍。", 1, 4), *rows))
    base.update(kw)
    return biography.BiographyRequest(**base)


def _system(sex: str = "男") -> str:
    return biography.SYSTEM.format(name="沈浪", him=gender.pronoun(sex), word=gender.word(sex))


def _section(outline: str, label: str) -> str:
    return outline.split(f"【{label}】")[1].split("\n\n")[0]


THREE = (_e("fight", "截殺了黃巾散兵。"), _e(annals.STANCE, STANCE_TEXT, figure="luzhi"), _e(annals.ERRAND, ERRAND_TEXT, 3, 3, figure="luzhi"),
         _e(annals.DUEL, DUEL_TEXT, 3, place="長社"), _e(annals.MARK, "潁川郊野的散兵退了。這裡頭有你出的一分力。"))


# ── 事實清單：各歸哪一段 ──


def test_each_kind_sits_in_its_section_of_the_outline():
    outline = biography.outline(_request(*THREE))
    figures, fights, deeds = _section(outline, "與英雄交往"), _section(outline, "單打獨鬥"), _section(outline, "出身與行事")
    assert "眾人勸盧植速戰" in figures and "替盧植把一封軍書送到長社" in figures  # 心意、託付：人物那一段
    assert "約戰衛重，大勝" in fights and "截殺了黃巾散兵" in fights  # 約戰：跟其他單挑一段
    assert "散兵退了" in deeds  # 痕跡：行事那一段
    for text, home in (("眾人勸盧植", figures), ("替盧植把", figures), ("約戰衛重", fights), ("散兵退了", deeds)):
        assert outline.count(text) == 1 and text in home  # 每一則只出現一次、不在別段
    assert annals.GROUPS[annals.STANCE] == annals.GROUPS[annals.ERRAND] == annals.FIGURE and annals.GROUPS[annals.DUEL] == annals.FIGHT


def test_the_outline_is_the_same_with_the_switch_closed():
    """事實清單不分開不開：7e 沒有動它，關著的身家照樣把這幾類放在同一段。"""
    assert biography.outline(_request(*THREE, profile=CLOSED)) == biography.outline(_request(*THREE))


# ── 提示詞 ──


def test_the_prompt_gets_one_more_rule_only_with_the_three_kinds_and_the_switch():
    ties = biography.messages(_request(*THREE))[0]["content"]
    assert ties == _system() + biography.TIES_RULE.format(n=7, name="沈浪", him="他")
    assert "眾人合力" in ties and "只能寫沈浪也在其中" in ties and "一人改了人物的主意" in ties
    assert not any(ch.isascii() and ch.isdigit() for ch in biography.TIES_RULE) and "你" not in biography.TIES_RULE  # 不用阿拉伯數字
    assert biography.messages(_request(*THREE[1:2]))[0]["content"].endswith(biography.TIES_RULE.format(n=7, name="沈浪", him="他"))  # 只有一類也要
    only_one = biography.messages(_request(_e(annals.DUEL, DUEL_TEXT)))[0]["content"]
    assert only_one == ties  # 三類只要有一類，同一條
    assert biography.messages(_request(*THREE, sex="女"))[0]["content"] == _system("女") + biography.TIES_RULE.format(n=7, name="沈浪", him="她")
    # 沒有這三類（只有痕跡、一般的事）：一個字不變
    assert biography.messages(_request(THREE[0], THREE[4]))[0]["content"] == _system()
    # 關著的季或舊身家：有這三類也一個字不變
    assert biography.messages(_request(*THREE, profile=CLOSED))[0]["content"] == _system()
    assert biography.messages(_request(*THREE, profile={}))[0]["content"] == _system()


def test_the_ties_rule_only_names_a_section_the_prompt_asks_for():
    """FB-896：規矩 2 要的四段是出身與投靠、大戰、與英雄交往、結局，沒有「單打獨鬥」（那只是事實清單的標題，備援文字把約戰放在結局那一段）。
    第 7（8）條說約戰放哪一段，只能是這四段裡的。"""
    assert "分四段：出身與投靠、大戰、與英雄交往、結局" in biography.SYSTEM
    assert "放進與英雄交往或結局那一段" in biography.TIES_RULE
    assert "單打獨鬥" not in biography.TIES_RULE
    assert "放進與英雄交往或結局那一段" in biography.messages(_request(*THREE))[0]["content"]


def test_the_rule_number_follows_the_tier_rule():
    tiered = dict(ZHUAN, tier=1, tier_side="官軍", tier_title="漢室忠良", contrib=180, final_rank=3, final_of=20)
    got = biography.messages(_request(*THREE, profile=tiered))[0]["content"]
    assert got == _system() + biography.TIER_RULE + biography.TIES_RULE.format(n=8, name="沈浪", him="他")
    assert got.count("\n7. ") == 1 and got.count("\n8. ") == 1
    only_tier = biography.messages(_request(THREE[0], profile=tiered))[0]["content"]
    assert only_tier == _system() + biography.TIER_RULE  # 沒有這三類：只有論功那一條，跟 7b 一樣


# ── 備援文字：各一句 ──


def test_the_fallback_has_a_sentence_for_each_kind():
    req = _request(*THREE)
    text = biography.rule_text(req)
    paras = text.split("\n\n")
    assert "第二週，眾人勸盧植速戰，沈浪也是其中之一：盧植聽了眾人之勸，決意速攻廣宗。" in paras[2]
    assert "第三週，沈浪替盧植把一封軍書送到長社，親手交給皇甫嵩，辦成了。" in paras[2]
    assert paras[2].startswith("其與當世英雄交也，")
    assert "第三週，沈浪在長社約戰衛重，大勝。" in paras[3] and "截殺了黃巾散兵。" in paras[3]  # 約戰在結局那一段（單打獨鬥）
    assert "這裡頭有沈浪出的一分力" in paras[0]  # 痕跡照舊接在行事後面
    assert "。。" not in text and "。」。" not in text
    assert not any(ch.isascii() and ch.isdigit() for ch in text) and "你" not in text
    assert biography.clean(text, req) == text  # 規則版自己也過得了清理的檢查


def test_a_garrison_duel_and_an_errand_read_clean():
    req = _request(_e(annals.DUEL, "在宛城約戰守軍，落敗。"), _e(annals.ERRAND, "替波才到宛城探一探官軍的營，辦成了。", 3, 3))
    text = biography.rule_text(req)
    assert "第二週，沈浪在宛城約戰守軍，落敗。" in text
    assert "第三週，沈浪替波才到宛城探一探官軍的營，辦成了。" in text
    assert not any(ch.isascii() and ch.isdigit() for ch in text)


def test_a_rival_name_is_never_touched_by_the_fallback():
    """FB-895：對手是玩家，名號只擋控制字元與長度，帶「你」、帶阿拉伯數字都有可能。備援文字別人的名號一個字都不動：
    不能把「你好嗎」寫成「沈浪好嗎」、把「Rival2」寫成「Rival二」。「你」換成傳主名號只對心意那一句（原句寫給你看的「你也是其中之一」）。"""
    req = _request(_e(annals.DUEL, "在長社約戰你好嗎，大勝。", 3), _e(annals.DUEL, "在宛城約戰Rival2，落敗。", 4),
                   _e(annals.DUEL, "應下你好嗎2在汝南荒野的約戰，險勝。", 5), _e(annals.STANCE, STANCE_TEXT, figure="luzhi"))
    text = biography.rule_text(req)
    assert "第三週，沈浪在長社約戰你好嗎，大勝。" in text
    assert "第四週，沈浪在宛城約戰Rival2，落敗。" in text
    assert "第五週，沈浪應下你好嗎2在汝南荒野的約戰，險勝。" in text
    assert "沈浪好嗎" not in text and "Rival二" not in text and "好嗎二" not in text
    assert "沈浪也是其中之一" in text  # 心意那一句照舊：「你」換成名號


def test_a_rival_name_is_kept_in_the_duel_lines_with_the_switch_open_or_closed():
    """FB-9020：列傳為終點關著的季，約戰那一句走一般的 _strip（7f 照「關著一個字不變」沒動），對手叫「你好嗎2」「Rival2」就被改成
    「沈浪好嗎二」「Rival二」；行狀記了 keep，關著的季也原樣（開著的季走 _tie_line，原句整句不動，跟 keep 無關）。攻方、守方兩種句子都是。"""
    rows = {"在長社約戰你好嗎2，大勝。": "你好嗎2", "在宛城約戰Rival2，落敗。": "Rival2",
            "應下你好嗎2在汝南荒野的約戰，險勝。": "你好嗎2", "應下Rival2在汝南荒野的約戰，險勝。": "Rival2"}
    for profile, lead in ((CLOSED, ""), (ZHUAN, "第三週，沈浪")):  # 開著的季補時刻與主詞（7e）；關著的季是原句
        for said, rival in rows.items():
            text = biography.rule_text(_request(_e(annals.DUEL, said, 3, keep=[rival]), profile=profile))
            assert lead + said in text, text
            assert "好嗎二" not in text and "Rival二" not in text and "沈浪好嗎" not in text
    legacy = biography.rule_text(_request(_e(annals.DUEL, "在宛城約戰Rival2，落敗。", 3), profile=CLOSED))  # 舊行狀沒有 keep：照舊
    assert "Rival二" in legacy


def test_the_garrison_line_needs_no_keep_and_reads_as_before():
    for profile in (CLOSED, ZHUAN):
        text = biography.rule_text(_request(_e(annals.DUEL, "在宛城約戰守軍，落敗。", 3), profile=profile))
        assert "在宛城約戰守軍，落敗。" in text


def test_the_one_who_answered_is_not_written_as_the_one_who_posted():
    """FB-897：守方的行狀是「應下某某在某地的約戰」（sortie_duel.ANNAL_ANSWER_LINE），補了主詞與時刻之後讀起來是他應戰、不是他下戰書。"""
    answered = sortie_duel.ANNAL_ANSWER_LINE.format(place="汝南荒野", rival="沈浪", tier="落敗")
    posted = sortie_duel.ANNAL_LINE.format(place="汝南荒野", rival="乙守", tier="大勝")
    req = _request(_e(annals.DUEL, answered, 1), name="乙守")
    assert "第一週，乙守應下沈浪在汝南荒野的約戰，落敗。" in biography.rule_text(req)
    assert "第一週，沈浪在汝南荒野約戰乙守，大勝。" in biography.rule_text(_request(_e(annals.DUEL, posted, 1)))  # 攻方照舊


def test_the_stance_line_still_turns_you_into_the_name_and_digits_into_chinese():
    req = _request(_e(annals.STANCE, "眾人勸盧植速戰，你也是其中之一：盧植決意 3 日內速攻廣宗。", figure="luzhi"))
    assert "第二週，眾人勸盧植速戰，沈浪也是其中之一：盧植決意三日內速攻廣宗。" in biography.rule_text(req)


def test_an_errand_and_a_duel_line_only_lose_the_closing_stop():
    """託付、約戰的原句整句原樣接進備援文字（只去掉句尾句號再補回）：人物的名字、地名、「你」「數字」都不經過 _strip。"""
    for kind, text in ((annals.ERRAND, "替盧植把一封軍書送到長社，親手交給皇甫嵩，辦成了。"), (annals.DUEL, "在長社約戰Rival2你好，險勝。")):
        line = biography._tie_line({"kind": kind, "when": "第 3 週・週二 10:00", "text": text}, "沈浪")
        assert line == f"第三週，沈浪{text}"
    assert biography._tie_line({"kind": annals.DUEL, "when": "", "text": "在長社約戰你好嗎，大勝"}, "沈浪") == "沈浪在長社約戰你好嗎，大勝。"  # 沒有句號也補得上


# ── 擠位子：備援文字每一段只取前幾則 ──


def _crowd(*tail: dict, profile: dict | None = None) -> biography.BiographyRequest:
    talks = [_e("figure", f"跟盧植談了第{i}回話。", 1, 1) for i in range(12)]
    fights = [_e("fight", f"截殺了黃巾散兵第{i}波。", 1, 2) for i in range(6)]
    return _request(*talks, *fights, *tail, profile=profile)


def test_a_crowded_season_still_tells_the_three_kinds():
    tail = (_e(annals.STANCE, STANCE_TEXT, 4), _e(annals.ERRAND, ERRAND_TEXT, 5, 3), _e(annals.DUEL, DUEL_TEXT, 6),
            _e(annals.DUEL, "在宛城約戰守軍，落敗。", 6), _e(annals.DUEL, "在長社約戰甲，大勝。", 7))
    text = biography.rule_text(_crowd(*tail))
    paras = text.split("\n\n")
    assert "決意速攻廣宗" in paras[2] and "辦成了" in paras[2]  # 排在十二次交談之後也沒被擠掉
    assert paras[2].count("談了") == 6  # 一段八則：心意、託付兩則（最多留四則位子），其餘六個位子照時間先後給交談
    assert paras[3].count("約戰") == 2 and "第六週，沈浪在宛城約戰守軍，落敗。" in paras[3] and "第七週，沈浪在長社約戰甲，大勝。" in paras[3]  # 兩個位子、同份量取近的
    assert paras[3].count("截殺了") == 2  # 其餘兩個位子照時間先後
    assert text.index("決意速攻廣宗") > text.index("談了第") and text.index("辦成了") > text.index("決意速攻廣宗")  # 仍照時間先後


def test_more_than_the_reserved_places_heavier_goes_first_then_the_later_one():
    """留給心意與託付的位子最多一段的一半（八則裡的四則）：五則爭四個位子，份量重的（託付三）先，同份量取近的（心意二：丙、乙，甲落選）。"""
    stances = [_e(annals.STANCE, f"眾人勸盧植速戰，你也是其中之一：{w}。", week) for week, w in ((3, "甲"), (4, "乙"), (5, "丙"))]
    errands = [_e(annals.ERRAND, f"替盧植辦了{w}事，辦成了。", week, 3) for week, w in ((6, "丁"), (7, "戊"))]
    text = biography.rule_text(_crowd(*stances, *errands))
    figures = text.split("\n\n")[2]
    assert [w in figures for w in "甲乙丙丁戊"] == [False, True, True, True, True]
    assert figures.count("談了") == 4  # 其餘四個位子照時間先後給交談
    assert figures.index("乙") < figures.index("丙") < figures.index("丁") < figures.index("戊")


def test_the_same_crowd_with_the_switch_closed_reads_the_old_way():
    """關著：照原本只取前八則交談、前四則單挑，心意、託付、約戰被擠掉（行狀本身還在、清單也有）；備援文字一個字不變。"""
    tail = (_e(annals.STANCE, STANCE_TEXT, 4), _e(annals.ERRAND, ERRAND_TEXT, 5, 3), _e(annals.DUEL, DUEL_TEXT, 6))
    req, closed = _crowd(*tail), _crowd(*tail, profile=CLOSED)
    text = biography.rule_text(closed)
    assert "決意速攻廣宗" not in text and "辦成了" not in text and "約戰" not in text
    assert text.split("\n\n")[2].count("談了") == 8 and text.split("\n\n")[3].count("截殺了") == 4
    assert "決意速攻廣宗" in biography.outline(closed) and biography.outline(closed) == biography.outline(req)
    assert biography.rule_text(req) != text  # 開著就多了


def test_nothing_to_tell_nothing_changes():
    """列傳為終點開著、行狀裡沒有這三類（舊存檔、沒勸沒託付沒約戰）：備援文字、事實清單、提示詞跟身家沒有 contrib 時一字不差。"""
    rows = [_e("figure", f"跟盧植談了第{i}回話。", 1, 1) for i in range(12)] + [_e("fight", f"截殺了黃巾散兵第{i}波。") for i in range(6)]
    rows += [_e(annals.MARK, "潁川郊野的散兵退了。這裡頭有你出的一分力。"), _e(annals.XINGSHI, "名號上了〈天下形勢〉第 3 篇：「沈浪下戰書攻荒丘」", 3, 3)]
    on, off = _request(*rows), _request(*rows, profile=CLOSED)
    assert biography.rule_text(on) == biography.rule_text(off)
    assert biography.outline(on) == biography.outline(off)
    assert biography.messages(on) == biography.messages(off)
    assert biography.messages(on)[0]["content"] == _system()


def test_the_closed_fallback_reads_them_as_plain_facts():
    """關著、人少：三類照一般的事讀（原句、沒有時刻、沒有補主詞），7e 之前就是這樣。"""
    text = biography.rule_text(_request(*THREE, profile=CLOSED))
    paras = text.split("\n\n")
    assert paras[2].startswith("其與當世英雄交也，眾人勸盧植速戰，沈浪也是其中之一：盧植聽了眾人之勸，決意速攻廣宗。替盧植把一封軍書送到長社")
    assert paras[3].startswith("截殺了黃巾散兵。在長社約戰衛重，大勝。季終")
    assert "第三週，沈浪在長社" not in text


# ── 接線：正式內容、收季之後真的寫一篇（slow）──


def _season(off: bool = False):
    content = wins_content()
    content.config.admins = [ADMIN]
    content.config.biography.enabled = True
    if off:
        content.config.jianfa.zhuan_end = False
    admin = wins_game(content, name=ADMIN)
    w = admin.world
    game = wins_game(content, name="官甲", faction="guan", at="changshe", world=w)
    game.state.player.contrib = 200
    save(game)
    admin.admin_end_season(NOW)
    return content, w


def _reload(content, world, name: str) -> Game:
    game = Game(content, CharacterStore(world.db).load(name), random.Random(0), world)
    game.client = None
    game.sync(NOW + 10)
    return game


def _note_three(game: Game) -> None:
    s, c = game.state, game.content
    annals.note(s, c, annals.STANCE, STANCE_TEXT, 2, figure="luzhi")
    annals.note(s, c, annals.ERRAND, ERRAND_TEXT, 3, figure="luzhi")
    annals.note(s, c, annals.DUEL, DUEL_TEXT, 2, place="長社")


@pytest.mark.slow
def test_a_closed_season_writes_a_biography_that_tells_the_three_kinds():
    content, w = _season()
    game = _reload(content, w, "官甲")
    _note_three(game)
    req = game.biography_request(1)
    assert req is not None and "contrib" in req.profile and {e["kind"] for e in req.annals} >= {annals.STANCE, annals.ERRAND, annals.DUEL}
    assert req.profile["tier"] == 1  # 論功第一名：提示已經有 7（TIER_RULE），這一條排 8
    assert biography.messages(req)[0]["content"].endswith(
        biography.TIER_RULE + biography.TIES_RULE.format(n=8, name="官甲", him=gender.pronoun(gender.of(game.state.player))))
    assert game.write_biography(req, None, NOW + 20) is True
    text = w.biography(1, "官甲")["text"]
    assert "決意速攻廣宗" in text and "官甲替盧植把一封軍書送到長社" in text and "官甲在長社約戰衛重，大勝" in text
    assert not any(ch.isascii() and ch.isdigit() for ch in text) and "你" not in text
    view = game.biography_view(1)
    assert any("決意速攻廣宗" in para for para in view["paragraphs"])  # 讀傳那一層看得到


@pytest.mark.slow
def test_with_the_switch_closed_the_same_season_writes_the_old_biography():
    content, w = _season(off=True)
    game = _reload(content, w, "官甲")
    _note_three(game)
    req = game.biography_request(1)
    assert req is not None and "contrib" not in req.profile
    assert biography.messages(req)[0]["content"] == _system_for(game)
    assert game.write_biography(req, None, NOW + 20) is True
    assert w.biography(1, "官甲")["text"] == biography.rule_text(req)
    assert "官甲替盧植" not in w.biography(1, "官甲")["text"] and "官甲在長社約戰" not in w.biography(1, "官甲")["text"]  # 沒補主詞、沒加時刻


def _system_for(game: Game) -> str:
    p = game.state.player
    return biography.SYSTEM.format(name=p.name, him=gender.pronoun(gender.of(p)), word=gender.word(gender.of(p)))
