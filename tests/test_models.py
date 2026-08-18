import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.models import NPCProfile
from src.rules import get_intimacy_stage, get_intimacy_stage_number


class TestIntimacyStageSSOT(unittest.TestCase):
    """Stage 4 安全網：config/npc_stages.json 成為親密度分級的唯一真實來源，
    這裡驗證邊界值 24/25/49/50/74/75 的分級正確，以及查無資料的 NPC 會 fallback
    回舊版寫死的 25/50/75 門檻，確保向後相容。"""

    def test_known_npc_boundary_values(self):
        # 邊界值對照 config/npc_stages.json 的 intimacy_range: [0,24]/[25,49]/[50,74]/[75,100]
        self.assertEqual(get_intimacy_stage_number("風騷老闆娘", 0), 1)
        self.assertEqual(get_intimacy_stage_number("風騷老闆娘", 24), 1)
        self.assertEqual(get_intimacy_stage_number("風騷老闆娘", 25), 2)
        self.assertEqual(get_intimacy_stage_number("風騷老闆娘", 49), 2)
        self.assertEqual(get_intimacy_stage_number("風騷老闆娘", 50), 3)
        self.assertEqual(get_intimacy_stage_number("風騷老闆娘", 74), 3)
        self.assertEqual(get_intimacy_stage_number("風騷老闆娘", 75), 4)
        self.assertEqual(get_intimacy_stage_number("風騷老闆娘", 100), 4)

    def test_known_npc_stage_detail_fields(self):
        stage_info = get_intimacy_stage("殺手阿福", 60)
        self.assertIsNotNone(stage_info)
        self.assertEqual(stage_info["stage"], 3)
        self.assertIn("stage_title", stage_info)
        self.assertIn("behavior", stage_info)
        self.assertIn("unlocked_topics", stage_info)

    def test_unknown_npc_falls_back_to_hardcoded_thresholds(self):
        # 查無 npc_stages.json 資料的 NPC，維持舊版 25/50/75 寫死門檻
        self.assertIsNone(get_intimacy_stage("路人乙", 60))
        self.assertEqual(get_intimacy_stage_number("路人乙", 24), 1)
        self.assertEqual(get_intimacy_stage_number("路人乙", 25), 2)
        self.assertEqual(get_intimacy_stage_number("路人乙", 49), 2)
        self.assertEqual(get_intimacy_stage_number("路人乙", 50), 3)
        self.assertEqual(get_intimacy_stage_number("路人乙", 74), 3)
        self.assertEqual(get_intimacy_stage_number("路人乙", 75), 4)


class TestNPCProfileIntimacyUnlocks(unittest.TestCase):
    """驗證 NPCProfile.get_unlocked_biography/get_unlocked_stats 透過 rules.py 查表後，
    對已知 NPC (資料驅動) 與未知 NPC (fallback) 都給出跟重構前一致的解鎖結果。"""

    def _make_profile(self, name: str, intimacy: int) -> NPCProfile:
        return NPCProfile(
            name=name, identity="測試身份", personality="測試性格",
            hp=100, location="測試地點", intimacy=intimacy,
            stats={"attack": 80, "realm": "先天境"},
            biography=["初見傳聞", "解鎖故事1", "解鎖故事2", "解鎖故事3"]
        )

    def test_known_npc_biography_unlock_uses_config_stage(self):
        profile = self._make_profile("風騷老闆娘", 60)  # stage 3
        self.assertEqual(len(profile.get_unlocked_biography()), 3)

    def test_known_npc_stats_unlock_uses_config_stage(self):
        profile = self._make_profile("風騷老闆娘", 30)  # stage 2 -> 部分解鎖
        stats = profile.get_unlocked_stats()
        self.assertEqual(stats["attack"], 80)
        self.assertEqual(stats["defense"], "???")

    def test_unknown_npc_still_uses_hardcoded_fallback(self):
        profile = self._make_profile("路人乙", 10)
        stats_low = profile.get_unlocked_stats()
        self.assertEqual(stats_low["attack"], "???")
        self.assertEqual(len(profile.get_unlocked_biography()), 1)

        profile.intimacy = 30
        stats_mid = profile.get_unlocked_stats()
        self.assertEqual(stats_mid["attack"], 80)
        self.assertEqual(len(profile.get_unlocked_biography()), 2)

        profile.intimacy = 80
        stats_high = profile.get_unlocked_stats()
        self.assertEqual(stats_high["realm"], "先天境")
        self.assertEqual(len(profile.get_unlocked_biography()), 4)


if __name__ == "__main__":
    unittest.main()
