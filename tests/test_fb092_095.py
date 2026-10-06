"""FB-092～095 與 h_lose（QA 走 joy 版序章與入伍段，main 8d4d470，2026-10-06；規劃者決定，專職開發做）。

用真實內容（conftest 的 real、on：這個測試自己的一份複本）。每一條是一個 commit，先寫測試。
新寫的句子都在待 joy 潤的清單上（見 fb-report.md）：這裡的測試只認事實（講了什麼、對不對得上規則），不鎖死字句。"""
from __future__ import annotations

from tianxia import team
from tianxia.martial_arts import content_art


def _step(content, step_id):
    return next(step for step in content.tutorial.steps if step.id == step_id)


def _art(skill_id, kind, attribute):
    return content_art(skill_id, skill_id, kind, attribute, "下品")


# ── FB-092：序章選「火」，新武學跟吐納相剋 ─────────────────────────────


def test_fb092_the_fire_method_says_the_fire_does_not_suit_the_breath(real):
    """四景的「灶裡那盆火」是屬剛的做法，師門配方給的是屬剛的【烈爐拳】，跟身上柔的基礎吐納相剋：選之前先說一句。"""
    scene = real.insight_scenes["prologue_hut"]
    fire = next(m for m in scene.methods if m.attribute == "剛")
    assert "灶裡那盆火" in fire.text and "火性剛烈" in fire.text and "吐納" in fire.text
    breath = real.skills[real.config.starter_skills[0]]
    assert (breath.kind, breath.attribute) == ("內功", "柔") and breath.name == "基礎吐納"  # 句子說的是真的：吐納屬柔
    others = [m.text for m in scene.methods if m.attribute != "剛"]
    assert not any("吐納" in text for text in others)  # 另外三個做法不相剋，不多說


def test_fb092_step_five_says_how_pairing_works_to_everyone(real):
    """第 5 步（改練）的話對每個人都多兩句：同一路加兩成、相剋的冤家少兩成，扯了後腿先練上去，之後內功也能融意境換路數。"""
    step = _step(real, "p5_level")
    text = step.text
    assert "講緣分" in text and "同一路" in text and "兩成" in text and "冤家" in text and "內功" in text and "融意境" in text
    assert "改練" in text and "功法庫" in text and "練到第三成" in text  # 原本的指示還在
    assert step.glow == ["tab:practice", "switch", "practice"]  # 發光不動


def test_fb092_what_the_master_says_about_pairing_is_what_the_rules_do(real):
    """師父說的三件事都是真的：同屬性 +20%、相剋的一對 −20%（team.pairing，照 Config）；內功能當合成的底、融了意境還是內功
    （tests/test_fusion.py::test_a_neigong_base_stays_a_neigong 釘住）。"""
    breath = _art("jichu_tuna", "內功", "柔")
    assert real.config.pairing_bonus == 0.2 and real.config.pairing_penalty == 0.2
    assert team.pairing(real, _art("a", "武學", "柔"), breath) == 1.2  # 同一路
    assert team.pairing(real, _art("b", "武學", "剛"), breath) == 0.8  # 剛配柔：冤家
    assert team.pairing(real, _art("c", "武學", "快"), breath) == 1.0  # 不相干的不加不減
