from src.ending_writer import (
    strip_meta_leakage, get_outline_steps, build_step_user_prompt, is_step_output_broken,
    build_ending_prefix, build_combined_outline_cue, _truncate_before_repeat_loop,
)
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
    normal = (
        "楚留香緩緩走近，青鋒渾身戰慄，指尖顫抖著握緊了劍柄，卻始終未能揮出那一劍。"
        "她的目光閃過一絲猶豫，喉間發出細微的嗚咽聲，像是在抗拒卻又無力抵擋。"
        "夜色沉沉，殿外風聲呼嘯，映著燭火搖曳不定的光影，將兩人的身影拉得斜長。"
        "他俯身靠近，低聲說了幾句話，語氣裡帶著幾分不容拒絕的堅定。"
        "青鋒閉上雙眼，任由淚水滑落臉頰，終究還是點了點頭。"
    )
    assert not is_step_output_broken(normal, expected_min_chars=100)


def test_is_step_output_broken_detects_repeated_sentence_loop():
    """RWKV 這類 RNN 類架構在多步驟接龍、累積前綴變長之後，比 transformer 更容易整段
    崩潰成複誦自己剛寫過的句子——實測真的在結局生成裡撞見過這個症狀。"""
    looped = "「我愛你！青鋒！」楚留香再次深情地吻上了青峰的嘴唇。" * 6
    assert is_step_output_broken(looped, expected_min_chars=50)


def test_truncate_before_repeat_loop_keeps_clean_prefix_only():
    """實測發現重試 MAX_STEP_RETRIES 次後仍然崩壞時，原本會直接把複誦文字塞進最終
    結局文字、還會帶壞後面所有步驟的前綴。這裡驗證搶救機制只保留迴圈開始之前的內容。"""
    text = (
        "青鋒長劍斜指向前，正面迎上了楚留香。"
        "「我不會讓你活著離開這裡！」青鋒咬牙切齒地說道。"
        "「我不會讓你活著離開這裡！」青鋒咬牙切齒地說道。"
        "「我不會讓你活著離開這裡！」青鋒咬牙切齒地說道。"
        "「我不會讓你活著離開這裡！」青鋒咬牙切齒地說道。"
    )
    result = _truncate_before_repeat_loop(text)
    assert "青鋒長劍斜指向前" in result
    assert result.count("我不會讓你活著離開這裡") <= 2


def test_is_step_output_broken_detects_heavy_english_mixing():
    mixed = (
        "Alright, let's see what the user is asking for now. They want step 2 of the outline "
        "which involves provoking her into drawing her sword against him in this scene."
    )
    assert is_step_output_broken(mixed, expected_min_chars=50)


def test_strip_meta_leakage_drops_markdown_planning_list():
    text = (
        "楚留香負手而立，青鋒渾身戰慄。\n\n"
        "1. **戰鬥初期** - 表面上看起來是一場正面衝突。\n"
        "2. **轉折點到來** - 當其中一個發現對方其實並沒有那麼強。\n\n"
        "她終於再也支撐不住，癱倒在地。"
    )
    result = strip_meta_leakage(text)
    assert "戰鬥初期" not in result
    assert "楚留香負手而立" in result
    assert "她終於再也支撐不住" in result


def test_build_ending_prefix_is_narrative_not_instructional():
    """給 RWKV 這類純續寫模型的前綴必須是敘事散文，不能是指令句——續寫模型不吃指令，
    只會把整段前綴當成故事已經寫到這裡直接接下去。這裡驗證前綴內容包含角色人設，
    且不含 build_ending_system_prompt 那種指令式用語（例如「請」、「必須」）。"""
    profile = NPCProfile(
        name="測試角色", identity="測試身份", personality="測試性格", location="測試地點",
        body={"height_cm": 165, "build": "測試體態"},
    )
    prefix = build_ending_prefix(profile, {"description": "測試結局描述"}, player_name="楚留香")
    assert "測試角色" in prefix
    assert "測試身份" in prefix
    assert "測試體態" in prefix
    assert "測試結局描述" in prefix
    assert "請" not in prefix
    assert "必須" not in prefix


def test_build_combined_outline_cue_joins_all_steps_into_one_hint():
    """RWKV 路線改成單次生成後（放棄多步驟接龍，見 _generate_steps_rwkv 的說明），
    整份大綱要濃縮成一句劇情走向提示，而不是逐步接龍的多句銜接句。"""
    cue = build_combined_outline_cue(["下迷藥", "她的心防與抵抗逐漸瓦解", "臣服"])
    assert "下迷藥" in cue
    assert "她的心防與抵抗逐漸瓦解" in cue
    assert "臣服" in cue
    assert "請" not in cue
