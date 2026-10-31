"""FB-695：起用過碎片的獨門行動之後，退回舊程式（main 54802f52、1d12fa6c）一啟動就讀不進 world 那一列——起用記在全服登記的
history、kind 是 "use"，舊程式的 SealEvent.kind 是 Literal、不認得它（pydantic 驗證錯，伺服器與假人程式都起不來）。

修法（PM 2026-10-22）：起用另記在 SealRegistry.uses（舊程式的登記模型沒有這一欄，pydantic 預設略過不認得的欄位）；讀檔時把舊資料
history 裡 kind "use" 的搬過去，搬完 history 不留 use；沒人起用過時 JSON 不多 uses 這個鍵（存檔一個位元組都不變）。

OLD_* 是舊程式（54802f52 與 1d12fa6c 兩版一樣）tianxia/world_state.py 的登記模型原樣抄下來的：新程式寫進資料庫的登記，舊程式那一版的
模型要讀得進來。舊程式的伺服器與假人程式真的開同一份資料庫，實測寫在試玩回饋 FB-695 那一列。"""
from __future__ import annotations

import json
import sqlite3
from typing import Literal, get_args

import pytest
from pydantic import BaseModel, Field, ValidationError

from tianxia import seal
from tianxia.world_state import SealEvent, SealRegistry

# ── 舊程式的登記模型（54802f52／1d12fa6c 的 world_state.py，原樣；不要跟著新程式改）──


class OldSealEvent(BaseModel):
    seq: int
    season: int
    kind: Literal["emerge", "stir", "keep", "take", "sink", "unsettled", "assign", "recall", "scatter", "mandate"]
    shard: str | None = None
    holder: str | None = None
    other: str | None = None
    record: int | None = None
    where: str = ""
    result: str | None = None
    fresh: bool = False
    proxied: list[str] = Field(default_factory=list)
    absent: list[str] = Field(default_factory=list)
    at: float | None = None
    lines: list[str] = Field(default_factory=list)
    edge: float | None = None
    round: int | None = None
    holders: dict[str, str] = Field(default_factory=dict)
    text: str = ""


class OldSealShard(BaseModel):
    id: str
    state: Literal["hidden", "held", "sunk"] = "hidden"
    holder: str | None = None
    since_season: int | None = None
    stirred_season: int | None = None
    emerged_round: int | None = None
    former: str | None = None
    absent: int = 0


class OldSealCache(BaseModel):
    season: int
    shard: str
    loc: str


class OldSealRegistry(BaseModel):
    shards: dict[str, OldSealShard] = Field(default_factory=dict)
    round: int = 1
    seq: int = 0
    opened_real: float | None = None
    salt: str = ""
    emerge_season: int | None = None
    force_emerge: str | None = None
    force_stir: str | None = None
    last_showdown: int | None = None
    last_showdown_dueled: bool = False
    last_showdown_where: str = ""
    mandate_season: int | None = None
    mandate_pending: bool = False
    cache: OldSealCache | None = None
    history: list[OldSealEvent] = Field(default_factory=list)


def _old_use(seq: int, holder: str, act: str, what: str, at: float, *, shard: str = "yunzhuan", season: int = 1) -> dict:
    """FB-695 以前的新程式（main 3e69e094）寫進 history 的那一筆，欄位與順序照 SealEvent.model_dump_json。"""
    return {"seq": seq, "season": season, "kind": "use", "shard": shard, "holder": holder, "other": None, "record": None,
            "where": what, "result": act, "fresh": False, "proxied": [], "absent": [], "at": at, "lines": [], "edge": None,
            "round": 1, "holders": {}, "text": ""}


def _event(seq: int, kind: str, **fields) -> dict:
    return json.loads(SealEvent(seq=seq, season=1, kind=kind, round=1, **fields).model_dump_json())


# ── 純模型 ──

def test_history_only_has_kinds_the_old_program_knows():
    """history 的 kind 跟舊程式一樣：多一種，退回舊程式整列 world 就讀不進來（FB-695）。要加新的紀錄另開欄位（空的時候不寫）。"""
    assert set(get_args(SealEvent.model_fields["kind"].annotation)) == set(get_args(OldSealEvent.model_fields["kind"].annotation))
    with pytest.raises(ValidationError):
        seal.log(SealRegistry(), 1, "use", shard="yunzhuan", holder="懷璽")


@pytest.mark.smoke
def test_no_uses_writes_the_same_bytes_as_before():
    """沒人起用過：登記的 JSON 不多 uses 這個鍵，跟舊程式的模型寫出來的一個位元組都不差。"""
    reg = SealRegistry.model_validate({"seq": 2, "salt": "鹽", "shards": {"yunzhuan": {"id": "yunzhuan", "state": "held", "holder": "甲"}},
                                       "history": [_event(1, "emerge", shard="yunzhuan", holder="甲", text="現世"), _event(2, "stir", shard="yunzhuan")]})
    raw = reg.model_dump_json()
    assert "uses" not in json.loads(raw)
    # 舊模型照同一份資料寫出來的（新程式多的 act_* 三欄是舊程式不認得的，拿掉再比）
    shards = {k: {f: v for f, v in s.items() if not f.startswith("act_")} for k, s in json.loads(raw)["shards"].items()}
    assert OldSealRegistry.model_validate_json(raw).model_dump_json() == json.dumps(
        {**json.loads(raw), "shards": shards}, ensure_ascii=False, separators=(",", ":"))
    assert SealRegistry().model_dump_json() == OldSealRegistry().model_dump_json()


def test_empty_uses_leave_no_key_on_any_pydantic_2():
    """uses 空的時候不寫這個鍵，不靠 Pydantic 的版本：Field(exclude_if=…) 是 2.11 才有的，requirements.txt 寫 pydantic>=2.6，舊版把它當多餘的
    參數略過、`"uses":[]` 照寫，存檔就跟以前不一樣。所以靠的是 SealRegistry 自己的 wrap serializer（_drop_empty_uses，同
    BattleInstance._drop_empty_front_note）：這一欄沒掛 exclude_if、tianxia 裡沒有任何呼叫帶 exclude_if，JSON 與 Python 兩種寫法、
    包在 SharedWorldState 裡（world 那一列的寫法）都沒有 uses；有一筆才寫。"""
    import ast
    from pathlib import Path

    from tianxia.world_state import SharedWorldState

    assert getattr(SealRegistry.model_fields["uses"], "exclude_if", None) is None
    used = []
    for path in sorted(Path(seal.__file__).resolve().parent.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and any(k.arg == "exclude_if" for k in node.keywords):
                used.append(f"{path.name}:{node.lineno}")
    assert used == []
    reg = SealRegistry(seq=1, history=[SealEvent(seq=1, season=1, kind="emerge", shard="yunzhuan")])
    assert "uses" not in json.loads(reg.model_dump_json()) and "uses" not in reg.model_dump()
    row = json.loads(SharedWorldState(seal=reg).model_dump_json(exclude={"season", "active_battle", "sieges"}))
    assert "uses" not in row["seal"] and "uses" not in SharedWorldState(seal=reg).model_dump()["seal"]
    seal.log_use(reg, 1, shard="yunzhuan", holder="甲", act="banzhao", what="", at=5.0)
    assert [u["holder"] for u in json.loads(reg.model_dump_json())["uses"]] == ["甲"] and len(reg.model_dump()["uses"]) == 1


def test_a_use_goes_to_its_own_list_that_the_old_model_skips():
    reg = SealRegistry(seq=1, history=[SealEvent(seq=1, season=1, kind="emerge", shard="yunzhuan", holder="甲")])
    used = seal.log_use(reg, 1, shard="yunzhuan", holder="甲", act="banzhao", what="", at=50.0)
    assert (used.seq, reg.seq) == (2, 2) and [e.kind for e in reg.history] == ["emerge"]
    assert [(u.seq, u.season, u.shard, u.holder, u.act, u.what, u.at) for u in reg.uses] == [(2, 1, "yunzhuan", "甲", "banzhao", "", 50.0)]
    raw = reg.model_dump_json()
    assert json.loads(raw)["uses"][0]["holder"] == "甲"
    old = OldSealRegistry.model_validate_json(raw)  # 舊程式略過 uses
    assert [e.kind for e in old.history] == ["emerge"] and old.seq == 2
    assert SealRegistry.model_validate_json(raw).uses == reg.uses  # 新程式讀回來一樣


def test_old_use_records_in_history_move_to_uses_on_read():
    """FB-695 以前的新程式寫的：history 裡的 use 讀進來搬到 uses（照流水號、欄位照原本的意思換），history 只剩舊程式認得的。"""
    raw = json.dumps({"seq": 4, "history": [
        _event(1, "emerge", shard="yunzhuan", holder="甲"), _old_use(2, "甲", "banzhao", "", 30.0),
        _event(3, "assign", shard="xuanniu", holder="乙"), _old_use(4, "乙", "yinjiang", "波才", 40.0, shard="xuanniu"),
    ]}, ensure_ascii=False)
    with pytest.raises(ValidationError):
        OldSealRegistry.model_validate_json(raw)  # 修之前的資料：舊程式讀不進來（QA 重現的那一個錯）
    reg = SealRegistry.model_validate_json(raw)
    assert [(e.seq, e.kind) for e in reg.history] == [(1, "emerge"), (3, "assign")]
    assert [(u.seq, u.holder, u.shard, u.act, u.what, u.at) for u in reg.uses] == [
        (2, "甲", "yunzhuan", "banzhao", "", 30.0), (4, "乙", "xuanniu", "yinjiang", "波才", 40.0)]
    assert reg.seq == 4
    again = reg.model_dump_json()
    assert '"use"' not in json.dumps(json.loads(again)["history"])
    assert len(OldSealRegistry.model_validate_json(again).history) == 2  # 搬完之後舊程式讀得進來
    assert SealRegistry.model_validate_json(again) == reg  # 再讀一次不變


def test_a_half_moved_registry_keeps_one_copy_per_number():
    """兩邊都有（uses 已經有、history 又出現同一號）：同一號只留一筆；不同號照流水號排。"""
    raw = json.dumps({"seq": 3, "uses": [{"seq": 2, "season": 1, "shard": "yunzhuan", "holder": "甲", "act": "banzhao", "what": "", "at": 30.0}],
                      "history": [_old_use(2, "甲", "banzhao", "", 30.0), _old_use(3, "甲", "banzhao", "", 90.0)]}, ensure_ascii=False)
    reg = SealRegistry.model_validate_json(raw)
    assert [u.seq for u in reg.uses] == [2, 3] and reg.history == []


# ── 正式內容：七種行動都起用過，舊程式的模型讀得進資料庫裡那一列（標 slow） ──

def _raw_seal(w) -> str:
    con = sqlite3.connect(str(w.db.path))
    try:
        return con.execute("SELECT json_extract(data, '$.seal') FROM world WHERE id = 1").fetchone()[0]
    finally:
        con.close()


@pytest.mark.slow
def test_after_all_seven_acts_the_old_model_still_reads_the_world_row():
    from test_seal_acts import _do, _give, _person
    from test_seal_acts3 import _season, _world

    from conftest import no_plans

    from tianxia import conquest

    c, w = _world()  # 21 天季＋領地爭奪打開：鎮地、補缺才起用得了
    no_plans(c)  # 引將要引的波才，行程開著時一開季就先被帶到長社（盤算公告）：「已經在這裡」，起用不成
    c.config.admins = ["管理"]
    cases = [  # 碎片、持有者、站哪、目標
        ("xuanniu", "甲客", "changshe", "bocai"), ("yunzhuan", "乙客", "yingchuan_wilds", ""),
        ("chenglu", "丙客", "yingchuan_wilds", ""), ("chizhang", "丁客", "yingchuan_wilds", "yingru"),
        ("guixin", "戊客", "yingchuan_wilds", "caocao"), ("jinjiao", "己客", "runan", "runan"),
        ("chishou", "庚客", "runan_academy", "runan_academy"),
    ]
    for shard, name, at, _ in cases:
        _give(c, w, shard, name)
        _person(c, w, name, side="huang", at=at)
    admin = _person(c, w, "管理", side=None)
    _season(c, w, lambda wd: conquest.push(wd, c, "runan", "guan", "官甲", 100, "attack"), now=100.0, name="己客")  # 汝南被官軍翻走
    for i, (shard, name, _, target) in enumerate(cases):
        msgs = _do(c, w, name, lambda g, t=target: g.seal_use(t), now=3800.0 + i)
        assert msgs and "還能再起用 1 次" in msgs[0], (shard, msgs)
    raw = _raw_seal(w)
    old = OldSealRegistry.model_validate_json(raw)  # 修之前這裡是 ValidationError（seal.history.N.kind）
    assert "use" not in {e.kind for e in old.history}
    reg = w.seal_state().registry
    assert [(u.holder, u.shard, u.act) for u in reg.uses] == [(name, shard, c.seal[shard].act) for shard, name, _, _ in cases]
    assert {sid: reg.shards[sid].act_uses for sid, *_ in cases} == {sid: 1 for sid, *_ in cases}
    rows = _do(c, w, "管理", lambda g: g.admin_seal_choices()["uses"], now=4000.0)
    assert [r["who"] for r in rows] == [name for _, name, _, _ in cases] and all(r["when"] for r in rows)
    assert admin is not None


@pytest.mark.slow
def test_a_database_with_old_use_records_reads_and_behaves_the_same():
    """內測資料庫有 FB-695 以前寫的 history use：讀進來搬過去，管理者看到的、次數、間隔都跟搬之前一樣；寫回時 history 不留 use。"""
    from test_seal_acts import _do, _holder, _person, _use

    from tianxia.calendar import DAY

    c, w, g = _holder("yunzhuan")
    c.config.admins = ["管理"]
    _person(c, w, "管理")
    _use(c, w, now=10.0)
    before = _do(c, w, "管理", lambda game: game.admin_seal_choices()["uses"], now=20.0)
    # 把資料庫改回 FB-695 以前的樣子：uses 拿掉、同一筆照舊的寫法插回 history
    data = json.loads(_raw_seal(w))
    [u] = data.pop("uses")
    data["history"] = sorted([*data["history"], _old_use(u["seq"], u["holder"], u["act"], u["what"], u["at"], season=u["season"])],
                             key=lambda e: e["seq"])
    con = sqlite3.connect(str(w.db.path))
    with con:
        con.execute("UPDATE world SET data = json_set(data, '$.seal', json(?)) WHERE id = 1", (json.dumps(data, ensure_ascii=False),))
    con.close()
    with pytest.raises(ValidationError):
        OldSealRegistry.model_validate_json(_raw_seal(w))  # 改回去的樣子舊程式確實讀不進來
    assert [x.seq for x in w.seal_state().registry.uses] == [u["seq"]] and not any(e.kind == "use" for e in w.seal_state().registry.history)
    assert _do(c, w, "管理", lambda game: game.admin_seal_choices()["uses"], now=20.0) == before
    assert "之後才能再起用" in _use(c, w, now=10.0 + DAY)[0]  # 間隔照舊
    w.mutate(lambda st: None)  # 任何一次寫回（伺服器、假人程式啟動時的 ensure_salt 也是）就存成新的樣子
    assert [e.kind for e in OldSealRegistry.model_validate_json(_raw_seal(w)).history] == [
        e["kind"] for e in data["history"] if e["kind"] != "use"]
    assert "還能再起用 0 次" in _use(c, w, now=10.0 + 3 * DAY + 1)[0]  # 第二次照常，次數照舊算
    assert [x.holder for x in w.seal_state().registry.uses] == ["懷璽", "懷璽"]
