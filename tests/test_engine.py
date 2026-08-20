import sys
import os
import json
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.models import NPCProfile, PlayerState, GameStateDelta
from src.npc_agent import NPCAgent, build_schema_example, load_lorebook
from src.game_engine import GameEngine


class TestEngine(unittest.TestCase):

    def setUp(self):
        # 測試用的通用 NPC，刻意不用 config/npcs.json 裡的真實角色名稱，
        # 讓這裡的測試獨立於實際角色資料內容之外，只驗證 NPCAgent 本身的行為。
        self.profile = NPCProfile(
            name="無名劍客",
            identity="來歷不明的江湖客",
            personality="沉默寡言，深藏不露。",
            hp=120,
            location="棲霜山莊演武場"
        )
        self.player_state = PlayerState(
            hp=100,
            max_hp=100,
            gold=50,
            inventory=["鏽蝕鐵劍"]
        )

    def test_npc_agent_prompt(self):
        agent = NPCAgent(self.profile)
        prompt = agent.build_system_prompt(self.player_state)

        self.assertIn("無名劍客", prompt)
        self.assertIn("來歷不明的江湖客", prompt)
        self.assertIn("HP=100", prompt)
        self.assertIn("金幣=50", prompt)
        self.assertIn("鏽蝕鐵劍", prompt)
        self.assertIn("好感度: 0 (範圍 -50~80)", prompt)
        self.assertIn("options 欄位中生成 3 個具體動態選項", prompt)

    def test_build_system_prompt_includes_resolved_intimacy_result_when_known(self):
        """五.1 節設計：查表得到的好感度變化要明確告知 LLM「已知結果」，不要求它自己判斷。"""
        agent = NPCAgent(self.profile)
        prompt_without = agent.build_system_prompt(self.player_state)
        self.assertNotIn("本回合好感度已知結果", prompt_without)

        prompt_with = agent.build_system_prompt(self.player_state, resolved_tag="真誠切磋", resolved_delta=6)
        self.assertIn("本回合好感度已知結果", prompt_with)
        self.assertIn("真誠切磋", prompt_with)
        self.assertIn("+6", prompt_with)

    def test_build_schema_example_matches_model_fields(self):
        """Stage 5 安全網：JSON 範例改成從 GameStateDelta.model_fields 動態產生，
        這裡確保範例的欄位集合永遠等於實際 schema，防止新增/改動欄位卻忘記同步 prompt。"""
        example_dict = json.loads(build_schema_example("測試角色"))
        self.assertEqual(set(example_dict.keys()), set(GameStateDelta.model_fields.keys()))
        self.assertIn("測試角色", example_dict["narrative"])
        self.assertIn("測試角色", example_dict["npc_status_tag"])
        self.assertEqual(len(example_dict["options"]), 3)
        self.assertEqual(len(example_dict["option_tags"]), 3)
        # 動態產生的欄位範例本身也要通過 model 驗證
        GameStateDelta.model_validate(example_dict)

    def test_load_lorebook_is_cached_across_calls(self):
        """Stage 5：load_lorebook 加上 lru_cache，同一個 process 內同一個路徑只應該讀一次檔"""
        load_lorebook.cache_clear()
        first = load_lorebook("config/lorebook.json")
        with patch("builtins.open", side_effect=AssertionError("不應該再次讀檔")):
            second = load_lorebook("config/lorebook.json")
        self.assertIs(first, second)

    def test_game_engine_apply_delta(self):
        engine = GameEngine()
        engine.player_state.hp = 50
        engine.player_state.gold = 20
        engine.player_state.inventory = ["鏽蝕鐵劍"]

        delta = GameStateDelta(
            narrative="測試獲得寶物與受傷",
            player_hp_change=-10,
            player_gold_change=100,
            inventory_added=["秘笈"],
            inventory_removed=["鏽蝕鐵劍"],
            npc_status_tag="驚訝",
            world_flag_set={"met_afu": True}
        )

        engine.apply_delta(delta)

        self.assertEqual(engine.player_state.hp, 40)
        self.assertEqual(engine.player_state.gold, 120)
        self.assertIn("秘笈", engine.player_state.inventory)
        self.assertNotIn("鏽蝕鐵劍", engine.player_state.inventory)
        self.assertTrue(engine.world_flags.get("met_afu"))

    def test_apply_delta_intimacy_clamped_to_new_range(self):
        """五.1 節設計：好感度區間從 0~100 改成 -50~80，apply_delta 的 clamp 要同步更新。"""
        engine = GameEngine()
        engine.current_agent.profile.intimacy = -45

        delta = GameStateDelta(narrative="測試好感度下限", intimacy_change=-20)
        engine.apply_delta(delta)
        self.assertEqual(engine.current_agent.profile.intimacy, -50)

        engine.current_agent.profile.intimacy = 75
        delta2 = GameStateDelta(narrative="測試好感度上限", intimacy_change=20)
        engine.apply_delta(delta2)
        self.assertEqual(engine.current_agent.profile.intimacy, 80)

    def test_apply_delta_milestone_and_faction_paths(self):
        """Stage 0 安全網：apply_delta 原本只測過 HP/金幣/背包/world_flags，
        補上里程碑去重與勢力聲望疊加這兩條路徑，供後續重構比對行為。"""
        engine = GameEngine()
        engine.factions["血罌宗"] = 10
        start_yijian = engine.factions.get("一劍宗", 0)

        delta = GameStateDelta(
            narrative="測試里程碑與勢力聲望",
            milestone_unlocked="初探群芳會秘辛",
            faction_reputation_changes={"血罌宗": 20, "一劍宗": -5}
        )
        engine.apply_delta(delta)

        self.assertIn("初探群芳會秘辛", engine.story_milestones)
        self.assertEqual(engine.factions["血罌宗"], 30)
        self.assertEqual(engine.factions["一劍宗"], start_yijian - 5)

        # 同一個里程碑不應該被重複加入第二次
        delta2 = GameStateDelta(
            narrative="再次觸發同一個里程碑",
            milestone_unlocked="初探群芳會秘辛",
            faction_reputation_changes={"血罌宗": 5}
        )
        engine.apply_delta(delta2)

        self.assertEqual(engine.story_milestones.count("初探群芳會秘辛"), 1)
        self.assertEqual(engine.factions["血罌宗"], 35)
        self.assertEqual(engine.factions["一劍宗"], start_yijian - 5)

    def test_switch_npc(self):
        engine = GameEngine()
        self.assertIsNotNone(engine.current_agent)

        if "慕容茵" in engine.agents:
            success = engine.switch_npc("慕容茵")
            self.assertTrue(success)
            self.assertEqual(engine.current_agent.profile.name, "慕容茵")

    @patch("src.ollama_client.OllamaClient.chat_structured")
    def test_engine_interact(self, mock_chat):
        mock_delta = GameStateDelta(
            narrative="慕容茵眼波流轉，笑意盈盈",
            player_hp_change=0,
            player_gold_change=50,
            inventory_added=["密函"],
            inventory_removed=[],
            npc_status_tag="興味",
            world_flag_set={"met_muronyin": True}
        )
        mock_chat.return_value = mock_delta

        engine = GameEngine()
        engine.switch_npc("慕容茵")
        delta = engine.interact("我要與你交換情報")

        self.assertEqual(delta.narrative, "慕容茵眼波流轉，笑意盈盈")
        self.assertEqual(engine.player_state.gold, 100)  # 50 + 50
        self.assertIn("密函", engine.player_state.inventory)

    @patch("src.game_engine.npc_autonomy.simulate_npc_autonomous_actions")
    @patch("src.ollama_client.OllamaClient.chat_structured")
    def test_interact_with_location_change_triggers_npc_autonomy_exactly_once(self, mock_chat, mock_autonomy):
        """Stage 7 bug 修正回歸測試：move_to_location 本身不再觸發 NPC 自主行動，
        所以就算這回合的 delta 帶有地點轉移 (apply_delta 內部會呼叫 move_to_location)，
        interact() 結尾也應該只觸發一次自主行動，而不是過去那樣觸發兩次。"""
        mock_delta = GameStateDelta(
            narrative="測試地點轉移是否只觸發一次自主行動",
            current_location="棲霜山莊後山"
        )
        mock_chat.return_value = mock_delta

        engine = GameEngine()
        engine.switch_npc("卓芷若")
        engine.interact("移動去棲霜山莊後山")

        self.assertEqual(engine.current_location, "棲霜山莊後山")
        self.assertEqual(mock_autonomy.call_count, 1)

    @patch("src.save_manager.save_account_game")
    @patch("src.game_engine.npc_autonomy.simulate_npc_autonomous_actions")
    def test_on_select_location_triggers_npc_autonomy_exactly_once(self, mock_autonomy, mock_save):
        """web_ui.on_select_location 是唯一不經過 interact() 的直接地點移動入口；
        move_to_location 不再自己觸發自主行動後，這裡要驗證它有自己補觸發恰好一次。"""
        from web_ui import on_select_location, get_engine_for_user
        eng = get_engine_for_user("_stage7_move_test")

        on_select_location("_stage7_move_test", "棲霜山莊後山", [])

        self.assertEqual(eng.current_location, "棲霜山莊後山")
        self.assertEqual(mock_autonomy.call_count, 1)

    def test_npc_stats_and_biography_unlock(self):
        profile = NPCProfile(
            name="測試NPC",
            identity="神祕客",
            personality="寡言",
            hp=100,
            location="客棧",
            intimacy=10,
            stats={"attack": 80, "realm": "先天境"},
            biography=["初見傳聞", "解鎖故事1", "解鎖故事2", "解鎖故事3"]
        )
        stats_low = profile.get_unlocked_stats()
        self.assertEqual(stats_low["attack"], "???")
        self.assertEqual(len(profile.get_unlocked_biography()), 1)

        profile.intimacy = 30
        stats_mid = profile.get_unlocked_stats()
        self.assertEqual(stats_mid["attack"], 80)
        self.assertEqual(len(profile.get_unlocked_biography()), 2)

        profile.intimacy = 80
        stats_high = profile.get_unlocked_stats()
        self.assertEqual(stats_high["attack"], 80)
        self.assertEqual(stats_high["realm"], "先天境")
        self.assertEqual(len(profile.get_unlocked_biography()), 4)

    def test_npc_autonomous_actions_and_world_news(self):
        engine = GameEngine()
        initial_news_count = len(engine.world_news)
        self.assertGreater(initial_news_count, 0)

        # 模擬一輪自主推演
        engine.simulate_npc_autonomous_actions()
        self.assertGreaterEqual(len(engine.world_news), initial_news_count)
        self.assertIn("【江湖動態", engine.world_news[0])

    def test_normalize_llm_dict_robustness(self):
        raw_dict = {
            "narrative": "她笑了笑",
            "player_hp_change": "-10",
            "inventory_added": "銀兩",
            "npc_status_tag": "靜默",
            "options": {
                "A": "選項A測試",
                "B": "選項B測試",
                "C": "選項C測試"
            }
        }
        delta = GameStateDelta.model_validate(raw_dict)
        self.assertEqual(delta.player_hp_change, -10)
        self.assertEqual(delta.inventory_added, ["銀兩"])
        self.assertEqual(delta.npc_status_tag, "凝視")  # 轉置靜默標籤
        self.assertEqual(len(delta.options), 3)
        self.assertEqual(len(delta.option_tags), 3)

    def test_normalize_llm_dict_strips_leaked_options_from_narrative(self):
        """小型模型有時會把選項清單誤附加在 narrative 尾端 (例如 qwen2.5:1.5b 的實測案例)，
        驗證這種情況會被自動截斷，不會讓選項清單重複出現在劇情文字裡。"""
        raw_dict = {
            "narrative": (
                "楚留香在這時開始有了新的行動：\n\n"
                "**選項 A) '這話說得倒是挺自信的'，楚留香心中暗笑。\n"
                "选项 B) '那話說起來可是蠻有道理的'，楚留香心中暗道。**"
            ),
            "options": [
                "A) 抱拳向對方詢問真實來歷",
                "B) 分析局勢向對方提出籌碼交換",
                "C) 上前施展強硬手段逼問"
            ]
        }
        delta = GameStateDelta.model_validate(raw_dict)
        self.assertNotIn("選項", delta.narrative)
        self.assertNotIn("选项", delta.narrative)
        self.assertTrue(delta.narrative.startswith("楚留香在這時開始有了新的行動"))

    def test_normalize_llm_dict_options_key_value_shape(self):
        """實測案例：qwen2.5:1.5b 有時把 options 內每個項目寫成 {"key": "C", "value": "完整選項文字"}，
        跟程式原本假設的 {"value": "A", "text": "內容"}（value 放字母、text 放內容）欄位語意剛好相反。
        修復前會把 value 誤當成字母前綴、把整個 dict 的 repr 字串塞進畫面，
        變成「C) 完整選項文字...) {'key': 'C', 'value': '完整選項文字...'}」這種可見的畫面污染。"""
        raw_dict = {
            "narrative": "她雙眸微眯",
            "options": [
                {"key": "A", "value": "A) 亮出兵器靜觀其變，開口詢問對方的意圖"},
                {"key": "B", "value": "B) 分析眼前局勢利害，冷靜提出籌碼條件進行談判"},
                {"key": "C", "value": "C) 上前進行身體接觸與耳邊輕語試探"},
            ],
        }
        delta = GameStateDelta.model_validate(raw_dict)
        for opt in delta.options:
            self.assertNotIn("{'key'", opt)
            self.assertNotIn("'value':", opt)
        self.assertIn("C) 上前進行身體接觸與耳邊輕語試探", delta.options)

    def test_normalize_llm_dict_keeps_narrative_mentioning_option_midsentence(self):
        """只有「選項/选项」緊接著 A) 這種清單開頭標記才截斷，一般提及「選項」兩字的敘述不受影響。"""
        raw_dict = {"narrative": "她笑道：『大俠這選項未免太多了些，不如挑一個吧。』"}
        delta = GameStateDelta.model_validate(raw_dict)
        self.assertEqual(delta.narrative, "她笑道：『大俠這選項未免太多了些，不如挑一個吧。』")

    @patch("src.ollama_client.OllamaClient.chat_structured")
    def test_npc_fallback_on_exception(self, mock_chat):
        mock_chat.side_effect = Exception("Ollama service timeout")
        agent = NPCAgent(self.profile)
        mock_client = MagicMock()
        mock_client.chat_structured.side_effect = Exception("Ollama service timeout")

        delta = agent.process_action(
            client=mock_client,
            player_action="你好",
            player_state=self.player_state
        )

        self.assertIsNotNone(delta)
        self.assertNotEqual(delta.npc_status_tag, "靜默")
        self.assertIn("無名劍客", delta.narrative)
        self.assertEqual(len(delta.options), 3)

    # ---- 好感度查表機制 (五.1 節設計，取代舊版主題線鎖定 + LLM 自報好感度) ----

    def test_process_action_overrides_llm_reported_intimacy_with_tag_lookup(self):
        """核心行為：即使 LLM 自己回報了一個 intimacy_change 數字，引擎也要無視它，
        改用玩家這次選擇的選項分類查表覆寫，且分類要能命中上一回合顯示過的選項。"""
        profile = NPCProfile(
            name="無名劍客", identity="來歷不明", personality="沉默寡言",
            hp=100, location="棲霜山莊演武場",
            intimacy_tags={"真誠切磋": 7, "中性互動": 2, "強攻鋪墊": -8}
        )
        agent = NPCAgent(profile)
        agent.last_offered_options = ["A) 真誠切磋選項", "B) 中性選項", "C) 強攻選項"]
        agent.last_offered_tags = ["真誠切磋", "中性互動", "強攻鋪墊"]

        mock_client = MagicMock()
        mock_client.chat_structured.return_value = GameStateDelta(
            narrative="測試",
            intimacy_change=999,  # LLM 亂填的數字，應該被忽略
            options=["A) 下一輪選項1", "B) 下一輪選項2", "C) 下一輪選項3"],
            option_tags=["真誠切磋", "中性互動", "強攻鋪墊"],
        )

        delta = agent.process_action(
            client=mock_client,
            player_action="A) 真誠切磋選項",
            player_state=self.player_state,
        )
        self.assertEqual(delta.intimacy_change, 7)

    def test_process_action_unmatched_action_results_in_zero_delta(self):
        """玩家輸入的行動沒有命中上一回合顯示過的任何選項 (例如自由輸入文字、或第一回合)，
        好感度變化視為 0，而不是信任 LLM 自報的數字。"""
        agent = NPCAgent(self.profile)
        mock_client = MagicMock()
        mock_client.chat_structured.return_value = GameStateDelta(
            narrative="測試", intimacy_change=50
        )
        delta = agent.process_action(
            client=mock_client,
            player_action="這是一段自由輸入、沒有對應任何選項的文字",
            player_state=self.player_state,
        )
        self.assertEqual(delta.intimacy_change, 0)

    def test_process_action_updates_last_offered_options_for_next_turn(self):
        agent = NPCAgent(self.profile)
        mock_client = MagicMock()
        mock_client.chat_structured.return_value = GameStateDelta(
            narrative="測試",
            options=["A) opt1", "B) opt2", "C) opt3"],
            option_tags=["真誠切磋", "中性互動", "強攻鋪墊"],
        )
        agent.process_action(client=mock_client, player_action="任意行動", player_state=self.player_state)
        self.assertEqual(agent.last_offered_options, ["A) opt1", "B) opt2", "C) opt3"])
        self.assertEqual(agent.last_offered_tags, ["真誠切磋", "中性互動", "強攻鋪墊"])

    def test_reset_history_clears_last_offered_options(self):
        agent = NPCAgent(self.profile)
        agent.last_offered_options = ["A) x", "B) y", "C) z"]
        agent.last_offered_tags = ["真誠切磋", "中性互動", "強攻鋪墊"]
        agent.reset_history()
        self.assertEqual(agent.last_offered_options, [])
        self.assertEqual(agent.last_offered_tags, [])

    def test_history_deduplication_and_repeat_penalty(self):
        agent = NPCAgent(self.profile)
        # 故意加入重複的 assistant 歷史紀錄
        agent.history = [
            {"role": "user", "content": "行動 1"},
            {"role": "assistant", "content": "她與你相擁，雙方的心意彼此對話。"},
            {"role": "user", "content": "行動 2"},
            {"role": "assistant", "content": "她與你相擁，雙方的心意彼此對話。"},
            {"role": "user", "content": "行動 3"},
            {"role": "assistant", "content": "她與你相擁，雙方的心意彼此對話。"}
        ]

        dedup = agent.get_deduplicated_history()
        # 驗證重複的 assistant 紀錄已被自動清洗，只保留 1 筆
        assistant_msgs = [m for m in dedup if m.get("role") == "assistant"]
        self.assertEqual(len(assistant_msgs), 1)

        # 驗證 System Prompt 簡化且不含僵化硬性模板詞「瞳孔微震」
        sys_prompt = agent.build_system_prompt(player_state=self.player_state)
        self.assertNotIn("瞳孔微震", sys_prompt)
        self.assertNotIn("雙頰酡紅", sys_prompt)


if __name__ == "__main__":
    unittest.main()
