import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.models import NPCProfile, PlayerState
from src.npc_agent import NPCAgent
from src.options import (
    load_npc_fallbacks,
    generate_fallback_narrative,
    generate_fallback_options,
    generate_single_fallback_option,
    generate_fallback_delta,
    inject_critical_option,
    FALLBACK_TAG_SLOTS,
)


class TestOptions(unittest.TestCase):
    """src/options.py 是 npc_agent.py 與 web_ui.py 共用的唯一 fallback 內容來源，
    這裡驗證共用行為在兩端保持一致。征服路線重構後選項改成每回合固定 3 個 (A~C)，
    保底池改成依分類 (tag: 真誠切磋/中性互動/強攻鋪墊) 而非舊版 A~E 位置類別查詢。"""

    def setUp(self):
        self.player_state = PlayerState(name="楚留香", hp=100, max_hp=100, gold=50)

    def test_config_has_all_current_npcs(self):
        data = load_npc_fallbacks()
        for npc_name in ["沈青鋒", "慕容茵", "卓芷若", "阿罌"]:
            self.assertIn(npc_name, data)
            self.assertIn("narrative", data[npc_name])
            self.assertIn("option_pools", data[npc_name])
            for tag in FALLBACK_TAG_SLOTS:
                self.assertIn(tag, data[npc_name]["option_pools"])
                self.assertGreaterEqual(len(data[npc_name]["option_pools"][tag]), 1)

    def test_generate_fallback_narrative_known_npc_uses_display_name(self):
        narrative, tag = generate_fallback_narrative(
            npc_name="沈青鋒", player_name="楚留香", location="棲霜山莊演武場", disp_name="青鋒"
        )
        self.assertIn("青鋒", narrative)
        self.assertIn("楚留香", narrative)
        self.assertEqual(tag, "戒備")

    def test_generate_fallback_narrative_unknown_npc_uses_identity(self):
        narrative, tag = generate_fallback_narrative(
            npc_name="神秘刀客", player_name="楚留香", location="棲霜山莊正廳",
            disp_name="無名", identity="遊蕩的獨行刀客"
        )
        self.assertIn("無名", narrative)
        self.assertIn("遊蕩的獨行刀客", narrative)
        self.assertEqual(tag, "思索")

    def test_generate_fallback_options_returns_three_prefixed_unique_options_with_tags(self):
        options, tags = generate_fallback_options("卓芷若", "棲霜山莊藥廬", turn=1, disp_name="芷若")
        self.assertEqual(len(options), 3)
        self.assertEqual(len(tags), 3)
        for prefix, opt in zip("ABC", options):
            self.assertTrue(opt.startswith(f"{prefix}) "))
        self.assertEqual(len(set(options)), 3)
        self.assertEqual(tags, FALLBACK_TAG_SLOTS)

    def test_generate_fallback_options_excludes_used_and_falls_back_to_dynamic(self):
        data = load_npc_fallbacks()
        # 排除掉沈青鋒「真誠切磋」的所有候選，逼函式退回動態帶回合數的選項
        exclude = {
            f"A) {tpl.format(disp_name='青鋒', location='棲霜山莊演武場')}"
            for tpl in data["沈青鋒"]["option_pools"]["真誠切磋"]
        }
        opt_a, tag_a = generate_single_fallback_option(
            0, "沈青鋒", "棲霜山莊演武場", turn=7, exclude_opts=exclude, disp_name="青鋒"
        )
        self.assertTrue(opt_a.startswith("A) "))
        self.assertIn("第7回合", opt_a)
        self.assertNotIn(opt_a, exclude)
        self.assertEqual(tag_a, "真誠切磋")

    def test_generate_fallback_delta_shape(self):
        delta = generate_fallback_delta(
            npc_name="慕容茵", player_state=self.player_state, location="棲霜山莊廂房",
            turn=2, disp_name="茵兒", identity="毒經谷谷主之女"
        )
        self.assertIn("茵兒", delta.narrative)
        self.assertEqual(delta.npc_status_tag, "算計")
        self.assertEqual(len(delta.options), 3)
        self.assertEqual(len(delta.option_tags), 3)
        # fallback 的 intimacy_change 固定為 0：好感度變化交由呼叫端 (NPCAgent) 依玩家
        # 這次選擇的選項分類查表覆寫，不是 generate_fallback_delta 的責任
        self.assertEqual(delta.intimacy_change, 0)
        self.assertEqual(delta.cultivation_exp_gained, 5)

    def test_npc_agent_fallback_delegates_to_shared_options_module(self):
        profile = NPCProfile(
            name="沈青鋒", identity="一劍宗宗主", personality="孤傲清冷",
            hp=130, location="棲霜山莊演武場", display_name="青鋒"
        )
        agent = NPCAgent(profile)
        delta = agent._generate_fallback_delta(
            player_action="出招試探", player_state=self.player_state, current_location="棲霜山莊演武場"
        )
        expected_delta = generate_fallback_delta(
            npc_name="沈青鋒", player_state=self.player_state, location="棲霜山莊演武場",
            disp_name="青鋒", identity="一劍宗宗主"
        )
        self.assertEqual(delta.narrative, expected_delta.narrative)
        self.assertEqual(delta.npc_status_tag, expected_delta.npc_status_tag)

    def test_unknown_npc_option_pools_are_generic_but_well_formed(self):
        options, tags = generate_fallback_options("路人乙", "亂葬崗", turn=1)
        self.assertEqual(len(options), 3)
        for prefix, opt in zip("ABC", options):
            self.assertTrue(opt.startswith(f"{prefix}) "))
        for opt in options:
            self.assertIn("路人乙", opt)
        self.assertEqual(tags, FALLBACK_TAG_SLOTS)


class TestInjectCriticalOption(unittest.TestCase):
    """好感度接近門檻時，系統決定性地把最後一格選項換成關鍵臨界選項，不靠 LLM 自己想到要放。"""

    def _make_delta(self):
        from src.models import GameStateDelta
        return GameStateDelta(
            narrative="測試",
            options=["A) 選項一", "B) 選項二", "C) 選項三"],
            option_tags=["真誠切磋", "中性互動", "強攻鋪墊"],
        )

    def test_injects_ultimate_slot_near_good_threshold(self):
        delta = self._make_delta()
        inject_critical_option(delta, predicted_intimacy=75, disp_name="青鋒")
        self.assertEqual(delta.option_tags[2], "終極臨界")
        self.assertIn("青鋒", delta.options[2])

    def test_injects_dark_slot_near_bad_threshold(self):
        delta = self._make_delta()
        inject_critical_option(delta, predicted_intimacy=-45, disp_name="青鋒", bad_ending_flow=["下迷藥"])
        self.assertEqual(delta.option_tags[2], "黑化臨界")
        self.assertIn("下迷藥", delta.options[2])

    def test_no_injection_when_intimacy_not_near_threshold(self):
        delta = self._make_delta()
        original_tags = list(delta.option_tags)
        inject_critical_option(delta, predicted_intimacy=20, disp_name="青鋒")
        self.assertEqual(delta.option_tags, original_tags)


if __name__ == "__main__":
    unittest.main()
