from src.ending_writer import strip_meta_leakage, get_outline_steps, build_step_user_prompt, is_step_output_broken
from src.models import NPCProfile


def test_strip_meta_leakage_removes_markdown_headers_and_code_fences():
    text = "正常的第一段小說內容。\n\n## 「下迷藥」\n\n```\n[注意]\n以上文本係\n```\n\n正常的第二段內容。"
    result = strip_meta_leakage(text)
    assert "##" not in result
    assert "```" not in result
    assert "[注意]" not in result
    assert "正常的第一段小說內容" in result
    assert "正常的第二段內容" in result


def test_strip_meta_leakage_drops_paragraph_mentioning_user():
    text = (
        "楚留香緩緩走近，青鋒渾身戰慄。\n\n"
        "好啊！用户現在讓我寫大綱第三步驟的部分呢！首先我要回顧之前的劇情發展。\n\n"
        "她終於再也支撐不住，癱倒在地。"
    )
    result = strip_meta_leakage(text)
    assert "用户" not in result
    assert "楚留香緩緩走近" in result
    assert "她終於再也支撐不住" in result


def test_strip_meta_leakage_keeps_clean_text_untouched():
    text = "第一段正常內容。\n\n第二段也是正常內容。"
    assert strip_meta_leakage(text) == text


def test_get_outline_steps_uses_bad_ending_flow_when_present():
    profile = NPCProfile(
        name="測試",
        identity="測試身份",
        personality="測試性格",
        location="測試地點",
        bad_ending_flow=["步驟一", "步驟二", "步驟三"],
    )
    assert get_outline_steps(profile, "bad") == ["步驟一", "步驟二", "步驟三"]


def test_get_outline_steps_falls_back_when_bad_ending_flow_missing():
    profile = NPCProfile(name="測試", identity="測試身份", personality="測試性格", location="測試地點")
    steps = get_outline_steps(profile, "bad")
    assert len(steps) == 3

    good_steps = get_outline_steps(profile, "good")
    assert len(good_steps) == 3


def test_build_step_user_prompt_marks_climax_and_last_step():
    normal = build_step_user_prompt(0, "鋪陳步驟", 3, is_climax_step=False)
    assert "直接進入身體接觸" not in normal
    assert "這是大綱的最後一步" not in normal

    climax_last = build_step_user_prompt(2, "收尾步驟", 3, is_climax_step=True)
    assert "直接進入身體接觸" in climax_last
    assert "這是大綱的最後一步" in climax_last


def test_is_step_output_broken_detects_emoji_symbol_collapse():
    garbage = "所以必須得好好把握住節奏！加油啦！😊✨💡🎉🎊💖💞💘💝🎀💫🌌🌠🌇🌅🌄🌆🌃🌉🟦🟢🟠🟡🟤⚪₹₩₫₽₺"
    assert is_step_output_broken(garbage, expected_min_chars=300)


def test_is_step_output_broken_detects_too_short_output():
    assert is_step_output_broken("很短。", expected_min_chars=300)


def test_is_step_output_broken_accepts_normal_prose():
    normal = "楚留香緩緩走近，青鋒渾身戰慄，指尖顫抖著握緊了劍柄，卻始終未能揮出那一劍。" * 5
    assert not is_step_output_broken(normal, expected_min_chars=100)
