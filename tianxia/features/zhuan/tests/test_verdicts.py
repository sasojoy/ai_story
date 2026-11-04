"""減法季批 7b-2：人物評曰（整合設計第九章、3.3；主機側計畫 Task 7b-2）。假模型，不打 Ollama。

- 誰寫：第一階由自己那一方的主將（FactionDef.verdict_by：官軍皇甫嵩或盧植、黃巾張角或波才，跟你情誼最高的那一位）、第二階由豪強的家主
  （曹操）、情誼到 signature_affinity（70）以上的人物各一位、買了親筆評曰請的那一位；同一位只寫一條；情誼 69 沒有。
- 怎麼寫：三段式同書信——A 開單（zhuan_end.verdict_request）、B 鎖外請模型（write_verdict：四十字以內、繁體、沒有數字與假名，
  寫壞或叫不動回空字串）、C 每一條接一段「評曰：某某云：「…」」（apply_verdict；空的照固定句 content/verdicts.json）。
- 伺服器：server.write_zhuan 寫完正文再逐條寫評曰（verdict_text，排在真人後面）。關著的季單子上沒有評曰，傳一個字不變。"""
from __future__ import annotations

import random
import time

import pytest

import server
from wins_kit import save, wins_content, wins_game
from tianxia import zhuan_end
from tianxia.characters import CharacterStore
from tianxia.engine import Game

NOW = 1_800_000_000.0
ADMIN = "論功官"


class FakeModel:
    """假模型：正文（chat_text）回一段夠長的傳，評曰（chat_structured）照順序回 replies 裡的句子；例外照丟。"""

    timeout, retry = 30, True

    def __init__(self, *replies, body: str | None = None):
        self.replies, self.body, self.asked = list(replies), body, []

    def chat_text(self, messages, **kw):
        if self.body is None:
            raise RuntimeError("down")
        return self.body

    def chat_structured(self, messages, response_model, **kw):
        self.asked.append(messages)
        reply = self.replies.pop(0) if self.replies else RuntimeError("down")
        if isinstance(reply, Exception):
            raise reply
        return response_model(verdict=reply)


# ── 純規則 ──


def _job(**kw) -> zhuan_end.VerdictJob:
    base = dict(fid="luzhi", reason=zhuan_end.TIER, name="盧植", persona="剛直", hero="少俠", player="沈浪", about="投靠官軍",
                fixed="沈浪此季之功，吾親書以表之。")
    base.update(kw)
    return zhuan_end.VerdictJob(**base)


def test_the_model_writes_one_short_clean_line_or_nothing():
    job = _job()
    fake = FakeModel("沈浪臨陣不亂，可託大事。")
    assert zhuan_end.write_verdict(fake, job, 40) == "沈浪臨陣不亂，可託大事。"
    system = fake.asked[0][0]["content"]
    assert "盧植" in system and "四十" not in system and "40字以內" in system and "不要寫任何數字" in system
    assert zhuan_end.write_verdict(FakeModel("沈浪这人可交。"), job, 40) == "沈浪這人可交。"  # 簡體轉繁體
    assert zhuan_end.write_verdict(FakeModel("沈浪立功三次，共3回。"), job, 40) == ""  # 有數字
    assert zhuan_end.write_verdict(FakeModel("沈浪はよい。"), job, 40) == ""  # 有假名
    assert zhuan_end.write_verdict(FakeModel("好" * 41), job, 40) == ""  # 太長
    assert zhuan_end.write_verdict(FakeModel(RuntimeError("down")), job, 40) == ""
    assert zhuan_end.write_verdict(None, job, 40) == ""
    assert zhuan_end.apply_verdict(job, "") == "評曰：盧植云：「沈浪此季之功，吾親書以表之。」"
    assert zhuan_end.apply_verdict(job, "可託大事。") == "評曰：盧植云：「可託大事。」"


@pytest.mark.slow
def test_the_fixed_lines_are_checked():
    content = wins_content()
    assert zhuan_end.check_verdicts(content) == []
    assert set(content.verdicts) == {zhuan_end.AFFINITY, zhuan_end.TIER, zhuan_end.BOUGHT}
    content.verdicts = {"tier": ["{name}" + "功" * 41], "other": ["好"]}
    problems = zhuan_end.check_verdicts(content)
    assert any("other" in p for p in problems) and any("四十" in p or "40" in p for p in problems)
    assert [f.verdict_by for f in content.scenario.factions] == [["huangfusong", "luzhi"], ["zhangjiao", "bocai"], ["caocao"]]


# ── 接線（正式內容、整季的流程，slow）──


def _season(off: bool = False):
    content = wins_content()
    content.config.admins = [ADMIN]
    if off:
        content.config.jianfa.zhuan_end = False
    admin = wins_game(content, name=ADMIN)
    w = admin.world
    people = {"官甲": ("guan", None, 200), "官乙": ("guan", None, 90), "豪甲": ("haoqiang", "guan", 100), "巾甲": ("huang", None, 50)}
    games = {}
    for name, (faction, ally, contrib) in people.items():
        game = wins_game(content, name=name, faction=faction, ally=ally, at="changshe", world=w)
        game.state.player.contrib = contrib
        if faction == "haoqiang":
            game.state.player.ledgers = {"guan": contrib}
        games[name] = game
    games["官甲"].state.player.affinities.update({"huangfusong": 30, "luzhi": 50, "caocao": 75, "zhangjiao": 69})
    games["官乙"].state.player.affinities.update({"caocao": 69})
    for game in games.values():
        save(game)
    admin.admin_end_season(NOW)
    return content, w


def _reload(content, world, name: str) -> Game:
    game = Game(content, CharacterStore(world.db).load(name), random.Random(0), world)
    game.client = None
    game.sync(NOW + 10)
    return game


@pytest.mark.slow
def test_who_writes_the_verdicts():
    content, w = _season()
    top = _reload(content, w, "官甲")
    req = top.biography_request(1)
    assert [(j.fid, j.reason) for j in req.verdicts] == [("luzhi", "tier"), ("caocao", "affinity")]  # 主將挑情誼高的；69 的沒有
    assert req.verdicts[0].name == "盧植" and req.verdicts[0].player == "官甲" and "第一階" in req.verdicts[0].about
    assert req.verdicts[0].fixed in [line.replace("{name}", "官甲") for line in content.verdicts["tier"]]
    gentry = _reload(content, w, "豪甲")
    assert [(j.fid, j.reason) for j in gentry.biography_request(1).verdicts] == [("caocao", "tier")]  # 第二階：豪強的家主
    third = _reload(content, w, "官乙")  # 第三階、情誼 69：沒有人寫
    assert third.biography_request(1).verdicts == ()
    assert top.biography_entry()["verdicts"] == [{"figure": "luzhi", "name": "盧植", "reason": "tier"},
                                                 {"figure": "caocao", "name": "曹操", "reason": "affinity"}]


@pytest.mark.slow
def test_each_verdict_is_its_own_paragraph_and_falls_back_to_the_fixed_line():
    content, w = _season()
    top = _reload(content, w, "官甲")
    req = top.biography_request(1)
    assert top.write_biography(req, None, NOW + 20, verdicts={"luzhi": "官甲臨陣不亂，可託大事。"}) is True
    paras = w.biography(1, "官甲")["text"].split("\n\n")
    assert paras[-2] == "評曰：盧植云：「官甲臨陣不亂，可託大事。」"
    assert paras[-1].startswith("評曰：曹操云：「") and paras[-1][len("評曰：曹操云：「"):-1] in [
        line.replace("{name}", "官甲") for line in content.verdicts["affinity"]]
    assert paras[-3].startswith("評曰：") and not paras[-3].startswith("評曰：盧植")  # 史官自己的評曰照舊在前
    assert [p.startswith("評曰") for p in top.biography_view(1)["paragraphs"]].count(True) == 3


@pytest.mark.slow
def test_a_bought_quote_adds_a_writer_and_a_rewrite_picks_it_up():
    from tianxia.characters import name_key
    from tianxia.wallet import Wallet

    content, w = _season()
    low = _reload(content, w, "官乙")
    low.state.player.affinities["zhujun"] = 45
    CharacterStore(w.db).save(low.state)
    Wallet(w.db).post(name_key("官乙"), 1000, "grant", "test:quote", time=NOW)
    assert low.mall_buy("zhuan_quote", "q1")[0].startswith("買下")
    assert "zhuan:quote:caocao" in {o.id for o in low.options()} and "zhuan:quote:zhujun" in {o.id for o in low.options()}
    low.choose("zhuan:quote:zhujun")
    req = low.biography_request(1)
    assert [(j.fid, j.reason) for j in req.verdicts] == [("zhujun", "bought")]
    low.write_biography(req, None, NOW + 30)
    assert w.biography(1, "官乙")["text"].split("\n\n")[-1].startswith("評曰：朱儁云：「")


@pytest.mark.slow
def test_off_has_no_verdicts_and_the_text_is_unchanged():
    content, w = _season(off=True)
    top = _reload(content, w, "官甲")
    req = top.biography_request(1)
    assert req.verdicts == () and "verdicts" not in top.biography_entry()
    top.write_biography(req, None, NOW + 20)
    from tianxia import biography

    assert w.biography(1, "官甲")["text"] == biography.rule_text(req)


@pytest.mark.slow
def test_the_server_writes_the_body_then_each_verdict_in_the_background(monkeypatch):
    content, w = _season()
    top = _reload(content, w, "官甲")
    CharacterStore(w.db).save(top.state)  # 伺服器每一下從資料庫重讀（同步記下的季末論功要先存）
    fake = FakeModel("官甲臨陣不亂，可託大事。", RuntimeError("down"), body="官甲者，" + "起於潁川，" * 60)
    top.client = fake
    monkeypatch.setattr(server, "QUEUE", None)
    assert server.write_zhuan(top, 1, False) is True
    deadline = time.monotonic() + 20
    while server._zhuan_key(top, 1) in server.ZHUAN_JOBS and time.monotonic() < deadline:
        time.sleep(0.05)
    row = w.biography(1, "官甲")
    assert row is not None and row["written_by"] == "model"
    paras = row["text"].split("\n\n")
    assert paras[0].startswith("官甲者，")
    assert paras[-2] == "評曰：盧植云：「官甲臨陣不亂，可託大事。」"  # 第一條模型寫成
    assert paras[-1].startswith("評曰：曹操云：「")  # 第二條叫不動：固定句
    assert len(fake.asked) == 2
