from tianxia import skillview
from tianxia.models import SkillEffect
from tianxia.rules import learn_skill


# ── 單一效果的白話說明 ─────────────────────────────────


def test_damage_wording_depends_on_kind_and_target():
    single = SkillEffect(kind="damage", base=1.2, top=1.9)
    assert skillview.effect_text(single, 1, "絕招") == "對一名敵人造成 120% 傷害"
    assert skillview.effect_text(single, 1, "連招") == "對普攻的目標追加 120% 傷害"
    group = SkillEffect(kind="damage", base=0.8, top=1.3, target="enemies")
    assert skillview.effect_text(group, 1, "絕招") == "對所有敵人造成 80% 傷害"


def test_numbers_follow_the_level():
    dmg = SkillEffect(kind="damage", base=1.2, top=1.9)
    assert skillview.effect_text(dmg, 2, "絕招") == "對一名敵人造成 128% 傷害"  # 1.2 + 0.7 / 9
    assert skillview.effect_text(dmg, 10, "絕招") == "對一名敵人造成 190% 傷害"
    flat = SkillEffect(kind="damage", base=3.0)  # 沒有 top：不隨成數變化
    assert skillview.effect_text(flat, 5, "絕招") == "對一名敵人造成 300% 傷害"


def test_xinfa_effects_last_the_whole_battle():
    reduce = SkillEffect(kind="reduce", base=0.05, top=0.15, target="self")
    assert skillview.effect_text(reduce, 1, "心法") == "自身受到的傷害減少 5%，持續整場"
    buff = SkillEffect(kind="buff", base=0.08, top=0.2, target="self", stat="dfn")
    assert skillview.effect_text(buff, 1, "心法") == "自身防禦提升 8%，持續整場"
    dodge = SkillEffect(kind="dodge", base=0.08, top=0.2, target="self")
    assert skillview.effect_text(dodge, 1, "心法") == "自身閃避 8%（只閃得開普攻），持續整場"


def test_debuff_lasts_its_rounds_outside_xinfa():
    debuff = SkillEffect(kind="debuff", base=0.1, top=0.2, stat="atk", rounds=2)
    assert skillview.effect_text(debuff, 1, "連招") == "目標攻擊降低 10%，持續 2 回合"
    team_buff = SkillEffect(kind="buff", base=0.1, target="allies", stat="spd")
    assert skillview.effect_text(team_buff, 1, "絕招") == "全隊速度提升 10%（出手更早），持續 1 回合"


def test_control_explains_itself_and_mentions_wisdom():
    seal = SkillEffect(kind="control", base=0.3, top=0.45, control="封脈")
    assert skillview.effect_text(seal, 1, "絕招") == "30% 機率使目標被封脈（發不出絕招）1 回合；悟性越高越容易命中"
    press = SkillEffect(kind="control", base=0.15, control="點穴", target="enemies")
    assert skillview.effect_text(press, 1, "絕招") == (
        "15% 機率使所有敵人被點穴（整回合不能行動）1 回合；悟性越高越容易命中"
    )
    disarm = SkillEffect(kind="control", base=0.2, control="卸兵")
    assert "卸兵（不能普攻，也不會連招）" in skillview.effect_text(disarm, 1, "連招")
    assert "整場" in skillview.effect_text(disarm, 1, "心法")


def test_heal_names_who_is_healed():
    heal = SkillEffect(kind="heal", base=0.2, target="ally_lowest")
    assert skillview.effect_text(heal, 1, "絕招") == "回復內力比例最低的隊友 20% 內力"
    assert skillview.effect_text(SkillEffect(kind="heal", base=0.1, target="allies"), 1, "絕招") == "回復全隊 10% 內力"


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
    assert skillview.summary(content, content.skills["fist"], 1) == "對普攻的目標追加 60% 傷害，發動 30%"
    assert skillview.summary(content, content.skills["palm"], 10) == "對一名敵人造成 160% 傷害，發動 40%"
    assert skillview.summary(content, content.skills["breath"], 1) == "自身受到的傷害減少 5%，持續整場"


def test_rules_line_uses_config(content):
    assert skillview.rules_line(content) == "同一隊同一門武學只能配一次；第 n 成升一成要心得 20×n；散功返還八成；本命不能散功"
    content.config.dispel_refund = 0.75
    assert "散功返還 75%" in skillview.rules_line(content)


# ── 武學詳情 ──────────────────────────────────────────


def test_detail_of_player_innate(game):
    text = skillview.detail(game.state, game.content, "skill:family")
    assert text.startswith("### 家傳劍　〔絕招〕〔柔〕〔中品〕")
    assert "**何時發動**　" + skillview.KIND_RULES["絕招"] in text
    assert "| 效果 | 目前第1成 | 升到第2成 |" in text
    assert "| 發動率 | 30% | 32% |" in text
    assert "| 對一名敵人造成 120% 傷害 | 120% | 128% |" in text
    assert "剋剛（對剛流派的敵人傷害 ×1.25）、被快剋（對快流派的敵人傷害 ×0.8）" in text
    assert "**目前配置於**　沈浪・本命" in text
    assert "**升一成需要心得** 20" in text
    assert "本命武學不能散功" in text


def test_detail_flavour_line(game):
    game.content.skills["family"].desc = "世家代代相傳。"
    assert "*世家代代相傳。*" in skillview.detail(game.state, game.content, "skill:family")


def test_detail_at_tenth_level(game):
    game.state.player.skills["family"] = 10
    text = skillview.detail(game.state, game.content, "skill:family")
    assert "| 效果 | 目前第10成 | 下一成 |" in text
    assert "| 發動率 | 45% | 已達第十成 |" in text
    assert "| 對一名敵人造成 190% 傷害 | 190% | 已達第十成 |" in text
    assert "**升一成需要心得**" not in text and "**已達第十成**" in text


def test_detail_lists_aptitude_for_every_member(game):
    text = skillview.detail(game.state, game.content, "skill:fist")  # 剛
    assert "韓鐵 剛A ×1.0" in text and "沈浪 剛B ×0.85" in text
    assert text.index("韓鐵 剛A") < text.index("沈浪 剛B")  # 最順手的排前面
    assert "剋巧（對巧流派的敵人傷害 ×1.25）、被柔剋（對柔流派的敵人傷害 ×0.8）" in text


def test_detail_without_style_is_the_same_for_everyone(game):
    learn_skill(game.state, game.content, "breath")  # 無流派
    text = skillview.detail(game.state, game.content, "skill:breath")
    assert "**相剋**　無流派，不參與相剋。" in text
    assert "無流派：資質不影響它，誰用都一樣。" in text
    assert "×" not in text


def test_detail_of_art_without_damage_ignores_counters(game):
    learn_skill(game.state, game.content, "step")  # 快流派心法，只加速度
    text = skillview.detail(game.state, game.content, "skill:step")
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
    assert "| 20% 機率使目標被點穴（整回合不能行動）1 回合；悟性越高越容易命中 | 20% | 22% |" in text
    assert "悟性" in text and "5%" in text and "95%" in text  # 命中率公式
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
        ("長拳（連招・剛）第1成 — 對普攻的目標追加 60% 傷害，發動 30% — 配置於 沈浪・自選1", "skill:fist"),
        ("家傳劍（絕招・柔）第1成 — 對一名敵人造成 120% 傷害，發動 30% — 配置於 沈浪・本命", "skill:family"),
        ("驚濤掌（絕招・剛）第1成 — 對一名敵人造成 100% 傷害，發動 25% — 配置於 韓鐵・本命", "innate:mate"),
    ]
    learn_skill(game.state, game.content, "breath")
    assert ("吐納法（心法・無流派）第1成 — 自身受到的傷害減少 5%，持續整場 — 未配置", "skill:breath") in (
        skillview.library(game.state, game.content)
    )
