"""減法季批 7b-1：行狀補齊（主機側計畫 Task 7b-1；整合設計第九章「玩家做的每一件事都要能變成列傳裡的一句」）。

- 季末論功（annals.TIER）：收季之後自己同步那一下記一則，換季時沒回來過的人在 _reset_player_for_new_season 補；身家（annals.profile）
  多 contrib、ledger_used、final_rank、final_of、tier、tier_title。
- 〈天下形勢〉寫到你的名號（annals.XINGSHI）：自己同步那一下，上一次看到的那一篇之後的每一篇各記一則，不重複。
- 列傳的提示詞與備援文字：季末論功自己一段、寫在最後一段；痕跡（MARK）與〈天下形勢〉照行事寫。
- 關著（zhuan_end 關掉）什麼都不記、身家一個鍵都不多、提示詞與備援文字一個字不變。
約戰（DUEL，批 3b）、心意與託付（STANCE／ERRAND，批 6）還沒合進來，不在這一份。"""
from __future__ import annotations

import json
import random

import pytest

from jianfa_kit import jianfa_game
from wins_kit import save, wins_content, wins_game
from tianxia import annals, biography, gender
from tianxia.characters import CharacterStore
from tianxia.engine import Game
from tianxia.state import AnnalEntry, PlayerState, XingshiEssay

NOW = 1_800_000_000.0
ADMIN = "論功官"
BASE_PROFILE_KEYS = {"name", "faction", "sect", "rank", "level", "fame", "good", "evil", "ranger", "team", "showdowns", "top_merits",
                     "bounties", "start", "place"}


def _system(name: str = "沈浪", sex: str = "男") -> str:
    return biography.SYSTEM.format(name=name, him=gender.pronoun(sex), word=gender.word(sex))


def _request(**kw) -> biography.BiographyRequest:
    base = dict(season=1, name="沈浪", scenario="黃巾之亂", era_note="", profile={"level": 12, "faction": "官軍"},
                annals=({"kind": "deed", "when": "第 1 週・週一 08:00", "text": "投靠官軍。", "weight": 4},))
    base.update(kw)
    return biography.BiographyRequest(**base)


# ── 純規則：種類、歸段、提示詞與備援文字 ──


def test_the_new_kinds_have_labels_and_groups():
    assert annals.KINDS[annals.TIER] == "論功" and annals.KINDS[annals.XINGSHI] == "行事"
    assert annals.GROUPS[annals.XINGSHI] == annals.DEED and annals.TIER not in annals.GROUPS  # 論功自己一段
    assert annals.heard(AnnalEntry(kind=annals.XINGSHI, time=0, when="", text="x"))  # 文章是公開的，酒肆打聽得到
    assert annals.heard(AnnalEntry(kind=annals.TIER, time=0, when="", text="x"))


def test_without_the_new_things_the_prompt_and_the_fallback_are_word_for_word_the_old_ones():
    """關著的季身家沒有 tier、行狀沒有新種類：系統提示照原本的 SYSTEM、事實清單沒有【季末論功】、備援文字照原本四段加評曰。"""
    req = _request()
    assert biography.messages(req)[0]["content"] == _system()
    assert "季末論功" not in biography.outline(req) and "季末論功" not in biography.rule_text(req)
    assert biography.rule_text(req).count("\n\n") == 3  # 沒有人物交往那一段：出身、大戰、結局、評曰


def test_the_tier_goes_last_and_marks_and_xingshi_read_as_deeds():
    req = _request(
        profile={"level": 20, "faction": "官軍", "contrib": 180, "ledger_used": "guan", "tier_side": "官軍", "final_rank": 3,
                 "final_of": 20, "tier": 1, "tier_title": "漢室忠良"},
        annals=(
            {"kind": "deed", "when": "第 1 週・週一 08:00", "text": "投靠官軍。", "weight": 4},
            {"kind": annals.MARK, "when": "第 2 週・週二 10:00", "text": "潁川郊野的散兵退了。這裡頭有你出的一分力。", "weight": 2},
            {"kind": annals.XINGSHI, "when": "第 2 週・週三 22:00", "text": "名號上了〈天下形勢〉第 3 篇：「沈浪下戰書攻荒丘」", "weight": 3},
            {"kind": annals.TIER, "when": "第 3 週・週日 23:00", "text": "季末論功，官軍出力排第 3（共 20 人），得第一階「漢室忠良」。", "weight": 5},
        ),
    )
    system = biography.messages(req)[0]["content"]
    assert system == _system() + biography.TIER_RULE  # 只多一條「名次與第幾階寫在結局那一段的最後」
    outline = biography.outline(req)
    assert outline.split("\n\n")[-1].startswith("【季末論功】") and "得第一階「漢室忠良」" in outline.split("\n\n")[-1]
    assert "季末論功：官軍第一階「漢室忠良」，貢獻 180，在 20 人中排第 3" in outline  # 身家那一段
    deeds = outline.split("【出身與行事】")[1].split("【")[0]
    assert "散兵退了" in deeds and "〈天下形勢〉第 3 篇" in deeds
    text = biography.rule_text(req)
    paras = text.split("\n\n")
    assert paras[-1].startswith("評曰：")
    assert paras[-2].endswith("季末論功，官軍出力排第三（共二十人），得第一階「漢室忠良」。")  # 結局那一段的最後
    assert "這裡頭有沈浪出的一分力" in paras[0] and "名號上了〈天下形勢〉第三篇：「沈浪下戰書攻荒丘」。" in paras[0]
    assert "。。" not in text and "。」。" not in text
    assert not any(ch.isascii() and ch.isdigit() for ch in text) and "你" not in text


def test_a_gentry_or_a_draw_says_which_book():
    req = _request(profile={"faction": "地方豪強", "contrib": 90, "ledger_used": "both", "tier_side": "替兩軍", "final_rank": 2,
                            "final_of": 5, "tier": 3, "tier_title": "鄉里之望"})
    assert "季末論功：替兩軍第三階「鄉里之望」，貢獻 90，在 5 人中排第 2" in biography.outline(req)
    none = _request(profile={"faction": "官軍", "contrib": 12, "ledger_used": "guan", "tier_side": "官軍", "final_rank": 0, "final_of": 0,
                             "tier": 0, "tier_title": ""})
    assert "季末論功：貢獻 12，未入階" in biography.outline(none)


# ── 接線：收季、換季、〈天下形勢〉（正式內容、整季的流程，slow）──


def _season(off: bool = False):
    content = wins_content()
    content.config.admins = [ADMIN]
    if off:
        content.config.jianfa.zhuan_end = False
    admin = wins_game(content, name=ADMIN)
    w = admin.world
    people = {"官甲": ("guan", None, 200), "官乙": ("guan", None, 90), "巾甲": ("huang", None, 150), "巾乙": ("huang", None, 60),
              "豪甲": ("haoqiang", "guan", 100), "散人": (None, None, 0)}
    games = {}
    for name, (faction, ally, contrib) in people.items():
        game = wins_game(content, name=name, faction=faction, ally=ally, at="changshe", world=w)
        game.state.player.contrib = contrib
        if faction == "haoqiang":
            game.state.player.ledgers = {"guan": contrib}
        games[name] = save(game)
    return content, admin, games


def _reload(content, world, name: str) -> Game:
    game = Game(content, CharacterStore(world.db).load(name), random.Random(0), world)
    game.client = None
    return game


def _tiers(game: Game) -> list[AnnalEntry]:
    return [e for e in game.state.player.annals if e.kind == annals.TIER]


@pytest.mark.slow
def test_season_end_notes_the_tier_once_and_the_profile_carries_it():
    content, admin, _ = _season()
    w = admin.world
    admin.admin_end_season(NOW)
    season = w.get_season()
    top = _reload(content, w, "官甲")
    top.sync(NOW + 10)
    result = season.final_tiers["官甲"]
    assert [e.text for e in _tiers(top)] == [f"季末論功，官軍出力排第 1（共 {result.of} 人），得第一階「漢室忠良」。"]
    assert _tiers(top)[0].weight == 5 and _tiers(top)[0].time == season.time
    top.sync(NOW + 20)
    assert len(_tiers(top)) == 1  # 只記一次
    profile = annals.profile(top.state, content, season=top.state.world)
    assert set(profile) == BASE_PROFILE_KEYS | {"contrib", "ledger_used", "tier_side", "final_rank", "final_of", "tier", "tier_title",
                                                "illustration",  # 列傳插畫的圖庫鍵（批 7b-3）
                                                "verdicts"}  # 第一階：主將替他寫評曰（批 7b-2）
    assert (profile["contrib"], profile["tier"], profile["final_rank"], profile["ledger_used"], profile["tier_title"]) == (
        200, 1, 1, "guan", "漢室忠良")
    req = top.biography_request(1)
    assert req is not None and "【季末論功】" in biography.outline(req) and biography.TIER_RULE in biography.messages(req)[0]["content"]

    gentry = _reload(content, w, "豪甲")
    gentry.sync(NOW + 10)
    assert "替官軍出力排第" in _tiers(gentry)[0].text
    drifter = _reload(content, w, "散人")
    drifter.sync(NOW + 10)
    assert _tiers(drifter) == []
    assert set(annals.profile(drifter.state, content, season=drifter.state.world)) == BASE_PROFILE_KEYS | {"contrib"}
    low = _reload(content, w, "巾乙")  # 到了門檻但沒有階的不記（貢獻與第幾名照樣在身家裡）
    low.sync(NOW + 10)
    if season.final_tiers["巾乙"].tier == 0:
        assert _tiers(low) == [] and annals.profile(low.state, content, season=low.state.world)["tier"] == 0


@pytest.mark.slow
def test_the_next_season_saves_the_tier_for_someone_who_never_came_back():
    content, admin, _ = _season()
    w = admin.world
    admin.admin_end_season(NOW)
    tier = w.get_season().final_tiers["巾甲"].tier
    admin.admin_next_season(NOW + 60)
    back = _reload(content, w, "巾甲")
    back.sync(NOW + 70)  # 換季：上一季的行狀與身家存起來（先補季末論功）
    row = w.biography(1, "巾甲")
    assert row is not None and [e["kind"] for e in row["annals"]].count(annals.TIER) == 1
    assert row["profile"]["tier"] == tier and row["profile"]["contrib"] == 150
    assert back.state.player.annals == [] or all(e.kind != annals.TIER for e in back.state.player.annals)


@pytest.mark.slow
def test_off_notes_nothing_and_the_profile_and_prompt_stay_the_same():
    content, admin, _ = _season(off=True)
    w = admin.world
    admin.admin_end_season(NOW)
    top = _reload(content, w, "官甲")
    top.sync(NOW + 10)
    assert _tiers(top) == []
    assert set(annals.profile(top.state, content, season=top.state.world)) == BASE_PROFILE_KEYS
    req = top.biography_request(1)
    assert req is not None and biography.messages(req)[0]["content"] == _system("官甲", gender.of(top.state.player))
    assert "【季末論功】" not in biography.outline(req) and "季末論功：" not in biography.outline(req)  # 大事那一段的江湖史是 3c 寫的
    assert "xingshi_seen" not in json.loads(top.state.player.model_dump_json())


def _essay(n: int, text: str, time: float) -> XingshiEssay:
    return XingshiEssay(key=n, time=time, n=n, essay=text, line="是日：兩軍相持。")


@pytest.mark.slow
@pytest.mark.parametrize("off", [False, True])
def test_xingshi_mentions_are_noted_once_each(off):
    game = jianfa_game(zhuan_end=not off)
    game.sync(game.now)
    w = game.state.world
    w.xingshi = [_essay(1, "是日風起。沈浪下戰書攻荒丘，眾皆側目。兩軍相持。", w.time), _essay(2, "兩軍相持，無事可記。", w.time)]
    game._save_season()
    game.sync(game.now)
    noted = [e for e in game.state.player.annals if e.kind == annals.XINGSHI]
    if off:
        assert noted == [] and "xingshi_seen" not in json.loads(game.state.player.model_dump_json())
        return
    assert [e.text for e in noted] == ["名號上了〈天下形勢〉第 1 篇：「沈浪下戰書攻荒丘，眾皆側目」"]
    assert game.state.player.xingshi_seen == 2
    game.sync(game.now)
    assert len([e for e in game.state.player.annals if e.kind == annals.XINGSHI]) == 1  # 不重複
    w = game.state.world
    w.xingshi = w.xingshi + [_essay(3, "黃巾漸盛。", w.time)]
    w.xingshi[-1].line = "是日：沈浪守住荒丘。"  # 「是日」那一句寫到也算（同網頁推送）
    game._save_season()
    game.sync(game.now)
    assert [e.text for e in game.state.player.annals if e.kind == annals.XINGSHI][-1] == "名號上了〈天下形勢〉第 3 篇：「是日：沈浪守住荒丘」"


def test_old_saves_without_the_new_field_load_and_the_field_is_quiet():
    p = PlayerState(name="沈浪", location="yingchuan", stats={}, stamina=0)
    assert "xingshi_seen" not in json.loads(p.model_dump_json())
    p.xingshi_seen = 4
    again = PlayerState.model_validate_json(p.model_dump_json())
    assert again.xingshi_seen == 4
    data = json.loads(p.model_dump_json())
    data.pop("xingshi_seen")
    assert PlayerState.model_validate(data).xingshi_seen == 0
