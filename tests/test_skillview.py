from tianxia import skillview
from tianxia.models import SkillEffect
from tianxia.rules import learn_skill


# ── 效果表的列名（不含數字）──────────────────────────────


def test_damage_labels_name_the_target():
    single = SkillEffect(kind="damage", base=1.2, top=1.9)
    assert skillview.effect_label(single, "絕招") == "傷害・一名敵人"
    assert skillview.effect_label(single, "連招") == "追加傷害・普攻的目標"
    group = SkillEffect(kind="damage", base=0.8, top=1.3, target="enemies")
    assert skillview.effect_label(group, "絕招") == "傷害・所有敵人"
    assert skillview.effect_label(group, "連招") == "追加傷害・所有敵人"


def test_xinfa_labels_last_the_whole_battle():
    reduce = SkillEffect(kind="reduce", base=0.05, top=0.15, target="self")
    assert skillview.effect_label(reduce, "心法") == "減傷・自身・整場"
    buff = SkillEffect(kind="buff", base=0.08, top=0.2, target="self", stat="dfn")
    assert skillview.effect_label(buff, "心法") == "防禦提升・自身・整場"
    dodge = SkillEffect(kind="dodge", base=0.08, top=0.2, target="self")
    assert skillview.effect_label(dodge, "心法") == "閃避・自身・整場（只閃得開普攻）"


def test_labels_outside_xinfa_show_rounds():
    debuff = SkillEffect(kind="debuff", base=0.1, top=0.2, stat="atk", rounds=2)
    assert skillview.effect_label(debuff, "連招") == "攻擊降低・目標・2 回合"
    team_buff = SkillEffect(kind="buff", base=0.1, target="allies", stat="spd")
    assert skillview.effect_label(team_buff, "絕招") == "速度提升・全隊・1 回合（出手更早）"


def test_control_labels_explain_the_control():
    seal = SkillEffect(kind="control", base=0.3, top=0.45, control="封脈")
    assert skillview.effect_label(seal, "絕招") == "封脈命中率・1 回合（發不出絕招）"
    press = SkillEffect(kind="control", base=0.15, control="點穴", target="enemies")
    assert skillview.effect_label(press, "絕招") == "點穴命中率・所有敵人・1 回合（整回合不能行動）"
    disarm = SkillEffect(kind="control", base=0.2, control="卸兵")
    assert skillview.effect_label(disarm, "連招") == "卸兵命中率・1 回合（不能普攻，也不會連招）"
    assert skillview.effect_label(disarm, "心法") == "卸兵命中率・一名敵人・整場（不能普攻，也不會連招）"


def test_heal_labels_name_who_is_healed():
    heal = SkillEffect(kind="heal", base=0.2, target="ally_lowest")
    assert skillview.effect_label(heal, "絕招") == "回復內力・內力比例最低的隊友"
    assert skillview.effect_label(SkillEffect(kind="heal", base=0.1, target="allies"), "絕招") == "回復內力・全隊"


# ── 武學庫用的短句（含數字）──────────────────────────────


def test_short_text_follows_the_level():
    dmg = SkillEffect(kind="damage", base=1.2, top=1.9)
    assert skillview.effect_short(dmg, 1, "絕招") == "傷害 120%"
    assert skillview.effect_short(dmg, 2, "絕招") == "傷害 128%"  # 1.2 + 0.7 / 9
    assert skillview.effect_short(dmg, 10, "絕招") == "傷害 190%"
    assert skillview.effect_short(SkillEffect(kind="damage", base=3.0), 5, "絕招") == "傷害 300%"  # 沒有 top


def test_short_text_wording():
    group = SkillEffect(kind="damage", base=0.4, top=0.7, target="enemies")
    assert skillview.effect_short(group, 1, "連招") == "全體追加傷害 40%"
    reduce = SkillEffect(kind="reduce", base=0.05, top=0.15, target="self")
    assert skillview.effect_short(reduce, 1, "心法") == "減傷 5%"
    seal = SkillEffect(kind="control", base=0.3, top=0.45, control="封脈")
    assert skillview.effect_short(seal, 1, "絕招") == "封脈 30%"
    debuff = SkillEffect(kind="debuff", base=0.1, top=0.2, stat="atk", rounds=2)
    assert skillview.effect_short(debuff, 1, "連招") == "攻擊降低 10%"
    assert skillview.effect_short(SkillEffect(kind="heal", base=0.1, target="allies"), 1, "絕招") == "全隊回復內力 10%"


# ── 何時發動、一行摘要、規則 ─────────────────────────────


def test_when_text_covers_every_kind_and_prep(content):
    assert set(skillview.KIND_RULES) == {"心法", "絕招", "連招"}
    assert "整場" in skillview.KIND_RULES["心法"]
    assert "封脈" in skillview.KIND_RULES["絕招"] and "普攻" in skillview.KIND_RULES["絕招"]
    assert "卸兵" in skillview.KIND_RULES["連招"]
    assert "蓄勢" not in skillview.when_text(content.skills["palm"])
    heavy = skillview.when_text(content.skills["heavy"])  # prep 1
    assert heavy.startswith(skillview.KIND_RULES["絕招"]) and "蓄勢" in heavy and "1 個自己的回合" in heavy


def test_summary_is_first_effect_plus_chance(content):
    assert skillview.summary(content.skills["fist"], 1) == "追加傷害 60%，發動 30%"
    assert skillview.summary(content.skills["palm"], 10) == "傷害 160%，發動 40%"
    assert skillview.summary(content.skills["breath"], 1) == "減傷 5%"


def test_rules_line_uses_config(content):
    assert skillview.rules_line(content) == (
        "一門武學同時只能配給一個人，某人的本命不能配給同隊的人；第 n 成升一成要心得 20×n；散功返還八成；本命不能散功"
    )
    content.config.dispel_refund = 0.75
    assert "散功返還 75%" in skillview.rules_line(content)


# ── 武學詳情 ──────────────────────────────────────────


def test_detail_of_player_innate(game):
    text = skillview.detail(game.state, game.content, "skill:family")
    assert text.startswith("### 家傳劍　〔絕招〕〔柔〕〔中品〕")
    assert "**何時發動**　" + skillview.KIND_RULES["絕招"] in text
    assert "| 效果 | 目前第1成 | 升到第2成 |" in text
    assert "| 發動率 | 30% | 32% |" in text
    assert "| 傷害・一名敵人 | 120% | 128% |" in text
    assert "剋剛（對剛流派的敵人傷害 ×1.25）、被快剋（對快流派的敵人傷害 ×0.8）" in text
    assert "**目前配置於**　沈浪・本命" in text
    assert "**升一成需要心得** 20" in text
    assert "本命武學不能散功" in text


def test_detail_table_labels_carry_no_percentages(game):
    for target in ("skill:family", "skill:fist", "innate:mate"):
        text = skillview.detail(game.state, game.content, target)
        rows = [line for line in text.splitlines() if line.startswith("| ") and not line.startswith("| 效果")]
        labels = [row.split(" | ")[0].removeprefix("| ") for row in rows]
        assert labels and all("%" not in label for label in labels)


def test_detail_flavour_line(game):
    game.content.skills["family"].desc = "世家代代相傳。"
    assert "*世家代代相傳。*" in skillview.detail(game.state, game.content, "skill:family")


def test_detail_at_tenth_level(game):
    game.state.player.skills["family"] = 10
    text = skillview.detail(game.state, game.content, "skill:family")
    assert "| 效果 | 目前第10成 | 下一成 |" in text
    assert "| 發動率 | 45% | 已達第十成 |" in text
    assert "| 傷害・一名敵人 | 190% | 已達第十成 |" in text
    assert "**升一成需要心得**" not in text and "**已達第十成**" in text


def test_detail_lists_aptitude_for_every_member(game):
    text = skillview.detail(game.state, game.content, "skill:fist")  # 剛，可以配給任何人
    assert "韓鐵 剛A ×1.0" in text and "沈浪 剛B ×0.85" in text
    assert text.index("韓鐵 剛A") < text.index("沈浪 剛B")  # 最順手的排前面
    assert "本命只有本人能用" not in text
    assert "剋巧（對巧流派的敵人傷害 ×1.25）、被柔剋（對柔流派的敵人傷害 ×0.8）" in text


def test_innate_aptitude_shows_only_the_holder(game):
    text = skillview.detail(game.state, game.content, "skill:family")  # 本人的本命，柔
    assert "- 沈浪 柔A ×1.0（本命只有本人能用）" in text
    assert "韓鐵 柔" not in text
    text = skillview.detail(game.state, game.content, "innate:mate")  # 韓鐵的本命，剛
    assert "- 韓鐵 剛A ×1.0（本命只有本人能用）" in text
    assert "沈浪 剛" not in text


def test_innate_without_damage_is_still_only_for_its_holder(game):
    game.content.characters["mate"].innate = "step"  # 快流派心法，只加速度
    text = skillview.detail(game.state, game.content, "innate:mate")
    assert "**誰用最順手**　本命只有本人能用；這門武學不造成傷害，資質不影響它。" in text
    assert "誰用都一樣" not in text


def test_detail_without_style_is_the_same_for_everyone(game):
    learn_skill(game.state, game.content, "breath")  # 無流派
    text = skillview.detail(game.state, game.content, "skill:breath")
    assert "**相剋**　無流派，不參與相剋。" in text
    assert "**誰用最順手**　無流派，資質不影響它，誰用都一樣。" in text
    assert "×" not in text


def test_detail_of_art_without_damage_ignores_counters(game):
    learn_skill(game.state, game.content, "step")  # 快流派心法，只加速度
    text = skillview.detail(game.state, game.content, "skill:step")
    assert "| 速度提升・自身・整場（出手更早） | 10% | 11% |" in text
    assert "**相剋**　快流派，但這門武學不造成傷害，相剋不影響它。" in text
    assert "這門武學不造成傷害，資質不影響它，誰用都一樣。" in text
    assert "×" not in text


def test_detail_placement(game):
    learn_skill(game.state, game.content, "step")
    assert "**目前配置於**　未配置" in skillview.detail(game.state, game.content, "skill:step")
    assert "**目前配置於**　沈浪・自選1" in skillview.detail(game.state, game.content, "skill:fist")
    game.set_loadout("mate", 1, "fist")
    assert "**目前配置於**　韓鐵・自選2" in skillview.detail(game.state, game.content, "skill:fist")
    assert "本命武學不能散功" not in skillview.detail(game.state, game.content, "skill:fist")


def test_detail_of_companion_innate_explains_control(game):
    text = skillview.detail(game.state, game.content, "innate:mate")
    assert text.startswith("### 驚濤掌")
    assert "| 傷害・一名敵人 | 100% | 107% |" in text
    assert "| 點穴命中率・1 回合（整回合不能行動） | 20% | 22% |" in text
    assert "控制命中率＝表中機率 ×（1 +（自己悟性 − 對方悟性）× 5%），最低 5%、最高 95%。" in text
    assert "回合數以承受者自己的回合計（被點穴而沒出手也算一回合）。" in text
    assert "**目前配置於**　韓鐵・本命" in text
    assert "本命武學不能散功" in text


def test_detail_of_unknown_target_is_a_hint(game):
    assert "點選" in skillview.detail(game.state, game.content, "skill:nothing")
    assert "點選" in skillview.detail(game.state, game.content, None)


# ── 人物卡、武學欄、武學庫 ──────────────────────────────


def test_member_card_for_player(game):
    card = skillview.member_card(game.state, game.content, "player")
    assert card.startswith("### 沈浪（隊長）")
    assert "第 1 級（經驗 0/100）" in card
    assert "流派 柔" in card
    assert "內力 520 / 520" in card  # 300 + 根骨 5 × 40 + 第 1 級 × 20
    assert "臂力 5　身法 5　根骨 5　悟性 5" in card
    assert "資質　剛B　柔A　快B　巧B" in card


def test_member_card_grows_with_level(game):
    member = game.state.player.members["mate"]
    member.level, member.exp, member.neili = 3, 50, 100.0
    card = skillview.member_card(game.state, game.content, "mate")
    assert card.startswith("### 韓鐵\n") and "隊長" not in card
    assert "第 3 級（經驗 50/300）" in card
    assert "流派 剛" in card
    assert "內力 100 / 624" in card  # 300 + 6.6 × 40 + 3 × 20
    assert "臂力 6.6　身法 5.4　根骨 6.6　悟性 4.2" in card
    assert "資質　剛A　柔B　快B　巧B" in card


def test_slot_labels(game):
    s, c = game.state, game.content
    assert skillview.slot_label(s, c, "player", None) == "本命　家傳劍（絕招）第1成"
    assert skillview.slot_label(s, c, "player", 0) == "自選1　長拳（連招）第1成"
    assert skillview.slot_label(s, c, "player", 1) == "自選2　（空）"
    assert skillview.slot_label(s, c, "mate", None) == "本命　驚濤掌（絕招）第1成"


def test_library_follows_upgrade_options(game):
    assert skillview.library(game.state, game.content) == [
        ("長拳（連招・剛）第1成　追加傷害 60%，發動 30%〔沈浪・自選1〕", "skill:fist"),
        ("家傳劍（絕招・柔）第1成　傷害 120%，發動 30%〔沈浪・本命〕", "skill:family"),
        ("驚濤掌（絕招・剛）第1成　傷害 100%，發動 25%〔韓鐵・本命〕", "innate:mate"),
    ]
    learn_skill(game.state, game.content, "breath")
    assert ("吐納法（心法・無流派）第1成　減傷 5%〔未配置〕", "skill:breath") in (
        skillview.library(game.state, game.content)
    )


def test_library_labels_stay_short(game):
    for skill_id in game.content.skills:
        learn_skill(game.state, game.content, skill_id)
        game.state.player.skills[skill_id] = 10
    labels = [label for label, _ in skillview.library(game.state, game.content)]
    assert labels and all(len(label) <= 40 for label in labels), max(labels, key=len)
