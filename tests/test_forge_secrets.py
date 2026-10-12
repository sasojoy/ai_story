"""打造的隱藏配方、名器、線索與鑄譜（docs/superpowers/specs/2026-10-12-打造隱藏配方-design.md；
計畫 docs/superpowers/plans/2026-10-12-打造-1-隱藏配方與防具.md Task 6～9）。"""
from __future__ import annotations

from collections import Counter

import pytest

from conftest import real_content
from tianxia import forge_secrets, naming, secret_recipes, weapons
from tianxia.content import ContentError, validate
from tianxia.models import ForgeSecret, ForgeSide

# 測試內容的素材只有精鐵砂（剛一）、玄鋼骨（剛二）、隕鐵膽（剛三）、驚羽（快一）
BLADE = ForgeSecret(
    id="t_blade", slot="weapon", kind="劍", main=ForgeSide(attribute="剛", tier=1), aux=ForgeSide(attribute="快", tier=1),
    name="穿霞劍", note="劍光像一道穿過晚霞的電。", clues=["說書一句。", "鐵匠一句。", "殘譜一句。"],
)
CLEAVER = ForgeSecret(
    id="t_cleaver", slot="weapon", kind="刀", main=ForgeSide(attribute="剛", tier=2), aux=ForgeSide(attribute="剛", min_tier=1),
    name="斷嶂刀", clues=["刀一句。", "刀二句。", "刀三句。"],
)
JACKET = ForgeSecret(
    id="t_jacket", slot="armor", main=ForgeSide(attribute="剛", tier=1), aux=ForgeSide(attribute="快", tier=1),
    name="赤霞鎧", note="甲片紅得像晚霞。", clues=["甲一句。", "甲二句。", "甲三句。"],
)


@pytest.fixture
def forge_content(content):
    # 深複本：test_a_bad_forge_pool_is_refused_at_load 會直接改 c.forge_secrets 裡的那一條（setattr），放模組層的原件進去
    # 就會漏到後面的測試（xdist 分到同一個 worker 時，BLADE 的 kind 被改成 None 之後 test_match 等都會紅）
    content.forge_secrets = {r.id: r.model_copy(deep=True) for r in (BLADE, CLEAVER, JACKET)}
    content.config.forge_secrets.per_season = {"weapon:1": 1, "weapon:2": 1, "armor:1": 1}
    content.config.weapons.enabled = content.config.armor.enabled = True
    return content


# ── Task 6：隱藏配方的內容、比對與命名過濾 ──

def test_each_season_picks_its_own_batch_per_group(forge_content):
    pool = {f"w{i}": BLADE.model_copy(update={"id": f"w{i}", "name": f"鋒{i}劍"}) for i in range(10)}
    forge_content.forge_secrets = {**pool, JACKET.id: JACKET}
    forge_content.config.forge_secrets.per_season = {"weapon:1": 2, "armor:1": 1}
    first = forge_secrets.active(forge_content, 0)
    assert [r.slot for r in first] == ["weapon", "weapon", "armor"] and first == forge_secrets.active(forge_content, 0)  # 全服同一批
    assert any(forge_secrets.active(forge_content, t) != first for t in range(1, 6))  # 換季換一批
    assert forge_secrets._rank(0, "w1") != secret_recipes._rank(0, "w1")  # 尾巴跟武學秘方分開，兩邊的排序互不牽動
    forge_content.config.armor.enabled = False
    assert all(r.slot == "weapon" for r in forge_secrets.active(forge_content, 0))  # 防具關著：不挑（也就不給摸不到的線索）
    forge_content.config.forge_secrets.per_season = {}
    assert forge_secrets.active(forge_content, 0) == []  # 預設全關（測試內容）


def test_match_reads_the_shape_kind_slot_and_main_aux_order(forge_content):
    m = lambda slot, kind, main, aux: forge_secrets.match(forge_content, 0, slot, kind, main, aux)  # noqa: E731
    assert m("weapon", "劍", "gang_1", "kuai_1") == BLADE  # forge_content 放的是深複本：比內容，不比是不是同一個物件
    assert m("weapon", "劍", "kuai_1", "gang_1") is None  # 主輔不交換
    assert m("weapon", "刀", "gang_1", "kuai_1") is None  # 種類對不上
    assert m("armor", "防具", "gang_1", "kuai_1") == JACKET  # 防具不看種類
    assert m("weapon", "刀", "gang_2", "gang_1") == CLEAVER and m("weapon", "刀", "gang_2", "gang_3") == CLEAVER  # 輔料不低於一階
    assert m("weapon", "刀", "gang_1", "gang_1") is None  # 主料寫死二階
    assert forge_secrets.key(BLADE) == "鑄|t_blade"
    forge_content.config.forge_secrets.per_season = {"armor:1": 1}
    assert m("weapon", "劍", "gang_1", "kuai_1") is None  # 這一季沒挑到的不算


def test_the_real_pool_has_twenty_two_named_recipes_and_validates():
    rc = real_content()  # 載入時已經跑過 _validate_forge_secrets
    assert len(rc.forge_secrets) == 22 and not any(r.divine for r in rc.forge_secrets.values())  # 神器那 9 條等第二批（3.4）
    groups = Counter(forge_secrets.group_of(r) for r in rc.forge_secrets.values())
    assert groups == {"weapon:1": 8, "weapon:2": 8, "armor:1": 3, "armor:2": 3}
    assert rc.config.forge_secrets.per_season == {"weapon:1": 2, "weapon:2": 2, "armor:1": 1, "armor:2": 1}
    cfg = rc.config.forge_secrets
    assert (cfg.tale_chance, cfg.smith_chance, cfg.scrap_chance) == (0.5, 0.25, 0.04)  # 設計 6.2（PM 決定第 6 條照預設）
    assert {"柳影劍", "纏絲護手", "負山袍", "霧隱袍"} <= {r.name for r in rc.forge_secrets.values()}
    for tianji in range(5):
        assert len(forge_secrets.active(rc, tianji)) == 6  # 第一批一季 6 條（兵器 4、防具 2，3.2）
    for r in rc.forge_secrets.values():
        assert naming.name_problem(r.name, rc) == naming.FORGE_CLASH  # 撞到自己：表示別人（模型、玩家）取不到這個名字


def test_forge_names_and_gear_names_are_kept_off_other_names(forge_content):
    assert naming.name_problem("穿霞劍", forge_content) == naming.FORGE_CLASH  # 模型替武學取名、玩家替絕學定名都取不到
    rc = real_content()
    for item in [*rc.gear.treasures.values(), *rc.gear.steeds.values()]:
        assert naming.name_problem(item.name, rc) == naming.GEAR_CLASH  # 寶物、名駒的名字也擋（防具打造計畫 PM 決定第 4 條留下的）


@pytest.mark.parametrize("change, message", [
    (lambda c: setattr(c.forge_secrets["t_blade"], "kind", None), "兵器要寫種類"),
    (lambda c: setattr(c.forge_secrets["t_jacket"], "kind", "劍"), "防具不寫種類"),
    (lambda c: setattr(c.forge_secrets["t_blade"].main, "tier", None), "主料要寫死階"),
    (lambda c: setattr(c.forge_secrets["t_cleaver"].aux, "tier", 2), "輔料寫 tier 或 min_tier 其中一個"),
    (lambda c: setattr(c.forge_secrets["t_blade"].aux, "attribute", "柔"), "剛柔、快慢合出來的屬性每季不同"),
    (lambda c: setattr(c.forge_secrets["t_blade"], "name", "寒星刀"), f"名字 寒星刀 過不了（{weapons.KIND_MISSING}）"),
    (lambda c: setattr(c.forge_secrets["t_jacket"], "name", "赤霞刀甲"), "名字 赤霞刀甲 過不了（名字像是兵器）"),
    (lambda c: setattr(c.forge_secrets["t_jacket"], "name", "穿霞劍"), "名字 穿霞劍 重複"),
    (lambda c: c.forge_secrets["t_blade"].clues.__setitem__(0, "一二三四五六七八九十一二三四五六七八九十多"), "第 1 句口訣要 1～20 字"),
    (lambda c: c.forge_secrets["t_blade"].clues.__setitem__(1, "照這個配方打。"), "口訣不寫「配方」「秘方」"),
    (lambda c: c.forge_secrets.__setitem__("t_dup", c.forge_secrets["t_blade"].model_copy(update={"id": "t_dup", "name": "穿雲劍"})),
     "跟隱藏配方 t_blade 認同一個組合"),
    (lambda c: c.config.forge_secrets.per_season.__setitem__("weapon:1", 3), "weapon:1 只有 1 條，不夠挑 3 條"),
    (lambda c: c.config.forge_secrets.per_season.__setitem__("weapon:divine", 1), "要等打造第二批"),
    (lambda c: c.config.forge_secrets.per_season.__setitem__("shield:1", 1), "per_season 只能有"),
])
def test_a_bad_forge_pool_is_refused_at_load(forge_content, change, message):
    validate(forge_content)  # 改之前是好的
    change(forge_content)
    with pytest.raises(ContentError, match=message):
        validate(forge_content)
