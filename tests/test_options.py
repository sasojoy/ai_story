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
)


class TestOptions(unittest.TestCase):
    """Stage 3 安全網：src/options.py 是 npc_agent.py 與 web_ui.py 共用的唯一 fallback 內容來源
    (取代原本兩份各自寫死的 if/elif 與選項池)，這裡驗證共用行為在兩端保持一致。"""

    def setUp(self):
        self.player_state = PlayerState(name="楚留香", hp=100, max_hp=100, gold=50)

    def test_config_has_all_current_npcs(self):
        data = load_npc_fallbacks()
        for npc_name in ["殺手阿福", "錢莊老王", "合歡宗聖女", "風騷老闆娘"]:
            self.assertIn(npc_name, data)
            self.assertIn("narrative", data[npc_name])
            self.assertIn("option_pools", data[npc_name])
            for category in ["A", "B", "C", "D", "E"]:
                self.assertIn(category, data[npc_name]["option_pools"])
                self.assertGreaterEqual(len(data[npc_name]["option_pools"][category]), 1)

    def test_generate_fallback_narrative_known_npc_uses_display_name(self):
        narrative, tag = generate_fallback_narrative(
            npc_name="殺手阿福", player_name="楚留香", location="龍門客棧旁暗巷", disp_name="阿福"
        )
        self.assertIn("阿福", narrative)
        self.assertIn("楚留香", narrative)
        self.assertEqual(tag, "算計工時")

    def test_generate_fallback_narrative_unknown_npc_uses_identity(self):
        narrative, tag = generate_fallback_narrative(
            npc_name="神秘刀客", player_name="楚留香", location="龍門客棧",
            disp_name="無名", identity="遊蕩的獨行刀客"
        )
        self.assertIn("無名", narrative)
        self.assertIn("遊蕩的獨行刀客", narrative)
        self.assertEqual(tag, "思索")

    def test_generate_fallback_options_returns_five_prefixed_unique_options(self):
        opts = generate_fallback_options("風騷老闆娘", "龍門客棧", turn=1, disp_name="賽金花")
        self.assertEqual(len(opts), 5)
        for prefix, opt in zip("ABCDE", opts):
            self.assertTrue(opt.startswith(f"{prefix}) "))
        self.assertEqual(len(set(opts)), 5)

    def test_generate_fallback_options_excludes_used_and_falls_back_to_dynamic(self):
        data = load_npc_fallbacks()
        # 排除掉阿福 A 類別的所有候選，逼函式退回動態帶回合數的選項
        exclude = {
            f"A) {tpl.format(disp_name='阿福', location='龍門客棧旁暗巷')}"
            for tpl in data["殺手阿福"]["option_pools"]["A"]
        }
        opt_a = generate_single_fallback_option(
            0, "殺手阿福", "龍門客棧旁暗巷", turn=7, exclude_opts=exclude, disp_name="阿福"
        )
        self.assertTrue(opt_a.startswith("A) "))
        self.assertIn("第7回合", opt_a)
        self.assertNotIn(opt_a, exclude)

    def test_generate_fallback_delta_shape(self):
        delta = generate_fallback_delta(
            npc_name="錢莊老王", player_state=self.player_state, location="龍門錢莊",
            turn=2, disp_name="老王", identity="龍門錢莊掌櫃"
        )
        self.assertIn("老王", delta.narrative)
        self.assertEqual(delta.npc_status_tag, "精算")
        self.assertEqual(len(delta.options), 5)
        self.assertEqual(delta.intimacy_change, 2)
        self.assertEqual(delta.cultivation_exp_gained, 5)

    def test_npc_agent_fallback_delegates_to_shared_options_module(self):
        profile = NPCProfile(
            name="殺手阿福", identity="血衣樓高級殺手", personality="冷酷嚴謹",
            hp=120, location="龍門客棧旁暗巷", display_name="阿福"
        )
        agent = NPCAgent(profile)
        delta = agent._generate_fallback_delta(
            player_action="出招試探", player_state=self.player_state, current_location="龍門客棧旁暗巷"
        )
        expected_delta = generate_fallback_delta(
            npc_name="殺手阿福", player_state=self.player_state, location="龍門客棧旁暗巷",
            disp_name="阿福", identity="血衣樓高級殺手"
        )
        self.assertEqual(delta.narrative, expected_delta.narrative)
        self.assertEqual(delta.npc_status_tag, expected_delta.npc_status_tag)

    def test_unknown_npc_option_pools_are_generic_but_well_formed(self):
        opts = generate_fallback_options("路人乙", "亂葬崗", turn=1)
        self.assertEqual(len(opts), 5)
        for prefix, opt in zip("ABCDE", opts):
            self.assertTrue(opt.startswith(f"{prefix}) "))
        # A~D 類別會提及對象名稱，E 類別 (地圖探索) 則不需要
        for opt in opts[:4]:
            self.assertIn("路人乙", opt)


if __name__ == "__main__":
    unittest.main()
