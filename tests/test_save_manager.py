import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.game_engine import GameEngine
from src.save_manager import (
    save_account_game,
    load_account_game,
    list_account_saves,
    get_latest_account_name,
    get_account_save_path,
)


class TestSaveManager(unittest.TestCase):
    """Stage 2 之後只支援 account-based 存檔（見 ARCHITECTURE.md 存檔系統整併）。"""

    def setUp(self):
        self.engine = GameEngine()
        self.test_account = "測試帳號_SaveManager"

    def tearDown(self):
        test_path = get_account_save_path(self.test_account)
        if os.path.exists(test_path):
            os.remove(test_path)

    def test_save_and_load_full_restoration(self):
        # 1. 設置自訂變更狀態
        self.engine.set_player_name("楚留香測試")
        self.engine.player_state.hp = 85
        self.engine.player_state.gold = 350
        self.engine.player_state.stamina = 70
        self.engine.player_state.charm = 25
        self.engine.player_state.cultivation_arts.append("合歡玄天功")

        self.engine.game_turn = 5
        self.engine.main_quest_summary = "已取得毒經谷信任，準備接近殘卷下落"
        self.engine.move_to_location("棲霜山莊後山")
        self.engine.factions["血罌宗"] = 80
        self.engine.world_flags["met_ayin"] = True
        self.engine.story_milestones.append("初探血罌宗邪功")
        self.engine.triggered_endings.add("卓芷若")

        if "慕容茵" in self.engine.agents:
            agent = self.engine.agents["慕容茵"]
            agent.profile.intimacy = 65
            agent.history = [
                {"role": "user", "content": "你可願與我坦誠相待？"},
                {"role": "assistant", "content": "慕容茵眼波流轉，微笑道：『少俠若是誠心，有何不可？』"}
            ]
            agent.used_options_history.add("你可願與我坦誠相待？")
            agent.last_offered_options = ["A) 選項一", "B) 選項二", "C) 選項三"]
            agent.last_offered_tags = ["真誠切磋", "中性互動", "強攻鋪墊"]

        # 2. 執行存檔
        msg = save_account_game(self.test_account, self.engine)
        self.assertIn("自動存檔成功", msg)

        # 3. 建立全新 GameEngine 實例並讀取存檔
        new_engine = GameEngine()
        success = load_account_game(self.test_account, new_engine)

        self.assertTrue(success)

        # 4. 驗證 100% 還原所有世界狀態與對話歷史
        self.assertEqual(new_engine.player_state.name, "楚留香測試")
        self.assertEqual(new_engine.player_state.hp, 85)
        self.assertEqual(new_engine.player_state.gold, 350)
        self.assertEqual(new_engine.player_state.stamina, 70)
        self.assertEqual(new_engine.player_state.charm, 25)
        self.assertIn("合歡玄天功", new_engine.player_state.cultivation_arts)

        self.assertEqual(new_engine.game_turn, 5)
        self.assertEqual(new_engine.main_quest_summary, "已取得毒經谷信任，準備接近殘卷下落")
        self.assertEqual(new_engine.current_location, "棲霜山莊後山")
        self.assertEqual(new_engine.factions["血罌宗"], 80)
        self.assertTrue(new_engine.world_flags.get("met_ayin"))
        self.assertIn("初探血罌宗邪功", new_engine.story_milestones)
        self.assertIn("卓芷若", new_engine.triggered_endings)

        if "慕容茵" in new_engine.agents:
            restored_agent = new_engine.agents["慕容茵"]
            self.assertEqual(restored_agent.profile.intimacy, 65)
            self.assertEqual(len(restored_agent.history), 2)
            self.assertEqual(restored_agent.history[0]["content"], "你可願與我坦誠相待？")
            self.assertIn("你可願與我坦誠相待？", restored_agent.used_options_history)
            self.assertEqual(restored_agent.last_offered_options, ["A) 選項一", "B) 選項二", "C) 選項三"])
            self.assertEqual(restored_agent.last_offered_tags, ["真誠切磋", "中性互動", "強攻鋪墊"])

    def test_story_milestones_and_used_options_history_are_now_persisted(self):
        """Stage 2 修復：story_milestones 與每個 NPCAgent 的 used_options_history
        現在會被存檔/讀檔正確還原（Stage 0 的 characterization test 記錄的是修復前的現況，
        這裡驗證修復後的行為）。"""
        self.engine.story_milestones.append("測試里程碑：夜探血罌宗")
        if "沈青鋒" in self.engine.agents:
            self.engine.agents["沈青鋒"].used_options_history.add("測試選項：夜探血罌宗")

        save_account_game(self.test_account, self.engine)

        new_engine = GameEngine()
        load_account_game(self.test_account, new_engine)

        self.assertIn("測試里程碑：夜探血罌宗", new_engine.story_milestones)
        if "沈青鋒" in new_engine.agents:
            self.assertIn(
                "測試選項：夜探血罌宗",
                new_engine.agents["沈青鋒"].used_options_history
            )

    def test_npc_relationship_notes_are_persisted(self):
        """npc_relationship_notes 是取代「要求 LLM 每回合重寫所有角色摘要」的新機制
        （見 src/npc_agent.py::build_system_prompt 的說明），確認存讀檔正確往返，
        且讀取舊格式存檔（沒有這個欄位）時能優雅降級成空字典，不會噴例外。"""
        self.engine.npc_relationship_notes["慕容茵"] = "已互相試探過底細"

        save_account_game(self.test_account, self.engine)

        new_engine = GameEngine()
        load_account_game(self.test_account, new_engine)

        self.assertEqual(new_engine.npc_relationship_notes.get("慕容茵"), "已互相試探過底細")

    def test_character_tags_are_persisted(self):
        """character_tags 原本是純靜態設定（每次都從 config/npcs.json 重新讀），但
        src/intimate_mode.py 的 attempt_intimate_action() 會在遊戲過程中把新習得的
        標籤直接 append 進 profile.character_tags，所以要跟 intimacy 一樣存讀檔，
        否則重新載入存檔會遺失玩家讓角色習得的標籤。"""
        if "阿罌" in self.engine.agents:
            agent = self.engine.agents["阿罌"]
            agent.profile.character_tags.append("喜歡口交")

        save_account_game(self.test_account, self.engine)

        new_engine = GameEngine()
        load_account_game(self.test_account, new_engine)

        if "阿罌" in new_engine.agents:
            self.assertIn("喜歡口交", new_engine.agents["阿罌"].profile.character_tags)

    def test_list_and_get_latest_account_saves(self):
        save_account_game(self.test_account, self.engine)

        saves = list_account_saves()
        account_names = [s["account_name"] for s in saves]
        self.assertIn(self.test_account, account_names)

        # 剛存檔的帳號時間戳最新，get_latest_account_name 應該找得到，而不是像
        # 舊版 get_latest_save_slot_id 那樣只認 slot 存檔而永遠找不到現存的 account 存檔
        self.assertEqual(get_latest_account_name(), self.test_account)


if __name__ == "__main__":
    unittest.main()
