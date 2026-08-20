import sys
import os
import json
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.models import NPCProfile, PlayerState, GameStateDelta
from src.npc_agent import NPCAgent, build_schema_example, load_lorebook
from src.game_engine import GameEngine
from src.thread_state import update_thread_state, THREAD_INTENSITY_THRESHOLD, THREAD_INTENSITY_BASE_STEP


class TestEngine(unittest.TestCase):

    def setUp(self):
        self.profile = NPCProfile(
            name="殺手阿福",
            identity="血衣樓高級殺手",
            personality="下午六點準時下班，絕不加班。",
            hp=120,
            location="龍門客棧旁暗巷"
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

        self.assertIn("殺手阿福", prompt)
        self.assertIn("血衣樓高級殺手", prompt)
        self.assertIn("HP=100", prompt)
        self.assertIn("金幣=50", prompt)
        self.assertIn("鏽蝕鐵劍", prompt)
        self.assertIn("允許玩家進行任何正邪抉擇", prompt)

    def test_build_schema_example_matches_model_fields(self):
        """Stage 5 安全網：JSON 範例改成從 GameStateDelta.model_fields 動態產生，
        這裡確保範例的欄位集合永遠等於實際 schema，防止新增/改動欄位卻忘記同步 prompt。"""
        example_dict = json.loads(build_schema_example("測試角色"))
        self.assertEqual(set(example_dict.keys()), set(GameStateDelta.model_fields.keys()))
        self.assertIn("測試角色", example_dict["narrative"])
        self.assertIn("測試角色", example_dict["npc_status_tag"])
        self.assertEqual(len(example_dict["options"]), 5)
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

    def test_apply_delta_milestone_and_faction_paths(self):
        """Stage 0 安全網：apply_delta 原本只測過 HP/金幣/背包/world_flags，
        補上里程碑去重與勢力聲望疊加這兩條路徑，供後續重構比對行為。"""
        engine = GameEngine()
        engine.factions["血衣樓"] = 10
        start_zhengpai = engine.factions.get("正派武林盟", 0)

        delta = GameStateDelta(
            narrative="測試里程碑與勢力聲望",
            milestone_unlocked="初探龍門秘辛",
            faction_reputation_changes={"血衣樓": 20, "正派武林盟": -5}
        )
        engine.apply_delta(delta)

        self.assertIn("初探龍門秘辛", engine.story_milestones)
        self.assertEqual(engine.factions["血衣樓"], 30)
        self.assertEqual(engine.factions["正派武林盟"], start_zhengpai - 5)

        # 同一個里程碑不應該被重複加入第二次
        delta2 = GameStateDelta(
            narrative="再次觸發同一個里程碑",
            milestone_unlocked="初探龍門秘辛",
            faction_reputation_changes={"血衣樓": 5}
        )
        engine.apply_delta(delta2)

        self.assertEqual(engine.story_milestones.count("初探龍門秘辛"), 1)
        self.assertEqual(engine.factions["血衣樓"], 35)
        self.assertEqual(engine.factions["正派武林盟"], start_zhengpai - 5)

    def test_switch_npc(self):
        engine = GameEngine()
        self.assertIsNotNone(engine.current_agent)
        
        if "錢莊老王" in engine.agents:
            success = engine.switch_npc("錢莊老王")
            self.assertTrue(success)
            self.assertEqual(engine.current_agent.profile.name, "錢莊老王")

    @patch("src.ollama_client.OllamaClient.chat_structured")
    def test_engine_interact(self, mock_chat):
        mock_delta = GameStateDelta(
            narrative="老王算盤打得飛快",
            player_hp_change=0,
            player_gold_change=50,
            inventory_added=["銀票"],
            inventory_removed=[],
            npc_status_tag="興奮",
            world_flag_set={"invested": True}
        )
        mock_chat.return_value = mock_delta

        engine = GameEngine()
        engine.switch_npc("錢莊老王")
        delta = engine.interact("我要買 IPO 股票")

        self.assertEqual(delta.narrative, "老王算盤打得飛快")
        self.assertEqual(engine.player_state.gold, 100)  # 50 + 50
        self.assertIn("銀票", engine.player_state.inventory)

    @patch("src.game_engine.npc_autonomy.simulate_npc_autonomous_actions")
    @patch("src.ollama_client.OllamaClient.chat_structured")
    def test_interact_with_location_change_triggers_npc_autonomy_exactly_once(self, mock_chat, mock_autonomy):
        """Stage 7 bug 修正回歸測試：move_to_location 本身不再觸發 NPC 自主行動，
        所以就算這回合的 delta 帶有地點轉移 (apply_delta 內部會呼叫 move_to_location)，
        interact() 結尾也應該只觸發一次自主行動，而不是過去那樣觸發兩次。"""
        mock_delta = GameStateDelta(
            narrative="測試地點轉移是否只觸發一次自主行動",
            current_location="黑風寨山腳"
        )
        mock_chat.return_value = mock_delta

        engine = GameEngine()
        engine.switch_npc("風騷老闆娘")
        engine.interact("移動去黑風寨山腳")

        self.assertEqual(engine.current_location, "黑風寨山腳")
        self.assertEqual(mock_autonomy.call_count, 1)

    @patch("src.save_manager.save_account_game")
    @patch("src.game_engine.npc_autonomy.simulate_npc_autonomous_actions")
    def test_on_select_location_triggers_npc_autonomy_exactly_once(self, mock_autonomy, mock_save):
        """web_ui.on_select_location 是唯一不經過 interact() 的直接地點移動入口；
        move_to_location 不再自己觸發自主行動後，這裡要驗證它有自己補觸發恰好一次。"""
        from web_ui import on_select_location, get_engine_for_user
        eng = get_engine_for_user("_stage7_move_test")

        on_select_location("_stage7_move_test", "黑風寨山腳", [])

        self.assertEqual(eng.current_location, "黑風寨山腳")
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
            "narrative": "老闆娘笑了笑",
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
        self.assertGreaterEqual(len(delta.options), 3)

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
                "A) 抱拳向賽金花詢問真實來歷",
                "B) 分析局勢向賽金花提出籌碼交換",
                "C) 上前攬住賽金花腰肢進行情慾交換",
                "D) 眼神一冷搜刮賽金花隨身密卷",
                "E) 移動前往黑風寨山腳避開風頭"
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
            "narrative": "柳如煙雙眸微眯",
            "options": [
                {"key": "A", "value": "A) 亮出兵器靜觀其變，開口詢問對方的意圖"},
                {"key": "B", "value": "B) 分析眼前局勢利害，冷靜提出籌碼條件進行談判"},
                {"key": "C", "value": "C) 上前進行身體接觸與耳邊輕語試探"},
                {"key": "D", "value": "D) 眼神一冷出其不意搜刮對方的隨身密卷"},
                {"key": "E", "value": "E) 移動前往周邊安全區域避開風頭"},
            ],
        }
        delta = GameStateDelta.model_validate(raw_dict)
        for opt in delta.options:
            self.assertNotIn("{'key'", opt)
            self.assertNotIn("'value':", opt)
        self.assertIn("C) 上前進行身體接觸與耳邊輕語試探", delta.options)

    def test_normalize_llm_dict_keeps_narrative_mentioning_option_midsentence(self):
        """只有「選項/选项」緊接著 A) 這種清單開頭標記才截斷，一般提及「選項」兩字的敘述不受影響。"""
        raw_dict = {"narrative": "賽金花笑道：『大俠這選項未免太多了些，不如挑一個吧。』"}
        delta = GameStateDelta.model_validate(raw_dict)
        self.assertEqual(delta.narrative, "賽金花笑道：『大俠這選項未免太多了些，不如挑一個吧。』")

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
        self.assertIn("阿福", delta.narrative)
        self.assertGreaterEqual(len(delta.options), 3)

    @patch("src.ollama_client.OllamaClient.chat_structured_stream")
    def test_option_deduplication_and_progression(self, mock_stream):
        """Stage 6：process_player_choice 改成串流 generator，這裡改為 mock chat_structured_stream
        並取 generator 的最後一個 yield（等同 Gradio 消費到最後一次更新後的畫面狀態）。"""
        mock_delta = GameStateDelta(
            narrative="賽金花眼波盈盈地看了你一眼",
            options=[
                "A) 詢問老闆娘賽金花龍門客棧密道與各方勢力的核心情報",
                "B) 提議將龍門客棧打包上市進行資本股權劃轉",
                "C) 湊近賽金花耳畔輕吟調情話語並撫摸其手背",  # 故意包含上一輪的選項 C 測試去重
                "D) 冷聲逼問賽金花龍門客棧地下庫房位置",
                "E) 移動前往黑風寨山腳避開風頭"
            ]
        )
        mock_stream.return_value = iter([(mock_delta.narrative, mock_delta)])

        from web_ui import process_player_choice, get_engine_for_user
        eng = get_engine_for_user("測試玩家_OptionDedup")
        eng.switch_npc("風騷老闆娘")

        # 第一回合選擇選項 C
        res1 = list(process_player_choice(
            custom_name="測試玩家_OptionDedup",
            user_input="C) 湊近賽金花耳畔輕吟調情話語並撫摸其手背",
            history=[],
            prev_opt_a="A) 點一壺上等竹葉青向老闆娘賽金花打聽龍門關最新消息",
            prev_opt_b="B) 拿出客棧餐飲評鑑表要求賽金花打八折",
            prev_opt_c="C) 湊近賽金花耳畔輕吟調情話語並撫摸其手背",
            prev_opt_d="D) 亮出血滴子逼問賽金花關於血衣樓黑榜的幕後主使",
            prev_opt_e="E) 移動前往龍門錢莊查詢存款行情"
        ))[-1]

        opt_c_turn2 = res1[12]  # opt_c is at index 12
        self.assertNotEqual(opt_c_turn2, "C) 湊近賽金花耳畔輕吟調情話語並撫摸其手背")

        # 第二回合再選選項 C (使用第二回合獲得的 opt_c_turn2)
        mock_stream.return_value = iter([(mock_delta.narrative, mock_delta)])
        res2 = list(process_player_choice(
            custom_name="測試玩家_OptionDedup",
            user_input=opt_c_turn2,
            history=res1[0],
            prev_opt_a=res1[10],
            prev_opt_b=res1[11],
            prev_opt_c=res1[12],
            prev_opt_d=res1[13],
            prev_opt_e=res1[14]
        ))[-1]

        opt_c_turn3 = res2[12]  # opt_c is at index 12
        self.assertNotEqual(opt_c_turn3, opt_c_turn2)
        self.assertNotEqual(opt_c_turn3, "C) 湊近賽金花耳畔輕吟調情話語並撫摸其手背")

    @patch("src.ollama_client.OllamaClient.chat_structured_stream")
    def test_partial_llm_options_are_preserved_not_fully_discarded(self, mock_stream):
        """實測回報：模型只生出 4 個有效選項時（第 5 個被判定重複/佔位而濾掉），
        以前的邏輯會把這 4 個貼合當下劇情的選項整批丟棄、換成完全通用的罐頭選項，
        玩家因此覺得「選項不連貫」。驗證修復後：這 4 個真實選項會被保留，只有缺的
        那一格才會用單格保底補上。"""
        # 清掉這個帳號可能殘留的存檔：process_player_choice 結尾一定會 auto_save，
        # 殘留的存檔會讓 used_options_history 帶著上一次執行的痕跡，導致保底選項
        # 挑到不同候選字串，使這個測試在不同次執行結果不一致（CLAUDE.md 已記錄過這個坑）。
        from src.save_manager import get_account_save_path
        save_path = get_account_save_path("測試玩家_PartialOptions")
        if os.path.exists(save_path):
            os.remove(save_path)

        mock_delta = GameStateDelta(
            narrative="賽金花眼波盈盈地看了你一眼",
            options=[
                "A) 詢問賽金花關於今晚黑風寨夜襲的傳聞",
                "B) 提議與賽金花聯手對付血衣樓的追兵",
                "C) 邀請賽金花共飲一杯壓驚酒拉近距離",
                "D) 冷聲逼問賽金花今晚客棧異狀的真相",
            ]
        )
        mock_stream.return_value = iter([(mock_delta.narrative, mock_delta)])

        from web_ui import process_player_choice, get_engine_for_user
        eng = get_engine_for_user("測試玩家_PartialOptions")
        eng.switch_npc("風騷老闆娘")

        result = list(process_player_choice(
            custom_name="測試玩家_PartialOptions",
            user_input="向老闆娘打聽消息",
            history=[],
        ))[-1]

        opt_a, opt_b, opt_c, opt_d, opt_e = result[10], result[11], result[12], result[13], result[14]
        self.assertEqual(opt_a, "A) 詢問賽金花關於今晚黑風寨夜襲的傳聞")
        self.assertEqual(opt_b, "B) 提議與賽金花聯手對付血衣樓的追兵")
        self.assertEqual(opt_c, "C) 邀請賽金花共飲一杯壓驚酒拉近距離")
        self.assertEqual(opt_d, "D) 冷聲逼問賽金花今晚客棧異狀的真相")
        self.assertTrue(opt_e.startswith("E)"))  # 缺的那一格由單格保底補上

    def test_history_deduplication_and_repeat_penalty(self):
        agent = NPCAgent(self.profile)
        # 故意加入重複的 assistant 歷史紀錄
        agent.history = [
            {"role": "user", "content": "行動 1"},
            {"role": "assistant", "content": "楚留香與柳如煙相擁，雙方的心意彼此對話。"},
            {"role": "user", "content": "行動 2"},
            {"role": "assistant", "content": "楚留香與柳如煙相擁，雙方的心意彼此對話。"},
            {"role": "user", "content": "行動 3"},
            {"role": "assistant", "content": "楚留香與柳如煙相擁，雙方的心意彼此對話。"}
        ]

        dedup = agent.get_deduplicated_history()
        # 驗證重複的 assistant 紀錄已被自動清洗，只保留 1 筆
        assistant_msgs = [m for m in dedup if m.get("role") == "assistant"]
        self.assertEqual(len(assistant_msgs), 1)

        # 驗證 System Prompt 簡化且不含僵化硬性模板詞「瞳孔微震」
        sys_prompt = agent.build_system_prompt(player_state=self.player_state)
        self.assertNotIn("瞳孔微震", sys_prompt)
        self.assertNotIn("雙頰酡紅", sys_prompt)

    # ---- 主題線鎖定狀態機 (src/thread_state.py::update_thread_state) ----
    # 設計討論見對話紀錄：玩家選了 B(謀略)/C(情慾)/D(混亂) 其中一類後，接下來幾回合的
    # 選項應該延續同一主題，而不是每回合都重新開放五種不相關的類型；E(地圖探索/轉移)
    # 永遠是逃生口，主題強度累積到門檻後下一回合先收尾再重置回中立狀態。

    def test_thread_lock_stays_neutral_on_a_or_e_from_neutral_state(self):
        agent = NPCAgent(self.profile)
        delta = GameStateDelta(narrative="測試")
        update_thread_state(agent, "A", delta)
        self.assertIsNone(agent.active_thread)
        update_thread_state(agent, "E", delta)
        self.assertIsNone(agent.active_thread)

    def test_thread_lock_enters_on_bcd_category_from_neutral_state(self):
        agent = NPCAgent(self.profile)
        delta = GameStateDelta(narrative="測試")
        update_thread_state(agent, "C", delta)
        self.assertEqual(agent.active_thread, "C")
        self.assertEqual(agent.thread_intensity, THREAD_INTENSITY_BASE_STEP)
        self.assertFalse(agent.thread_climax_pending)

    def test_thread_lock_e_breaks_active_thread_immediately(self):
        agent = NPCAgent(self.profile)
        agent.active_thread = "C"
        agent.thread_intensity = 50
        delta = GameStateDelta(narrative="測試")
        update_thread_state(agent, "E", delta)
        self.assertIsNone(agent.active_thread)
        self.assertEqual(agent.thread_intensity, 0)
        self.assertFalse(agent.thread_climax_pending)

    def test_thread_lock_c_accumulates_via_intimacy_change_magnitude(self):
        agent = NPCAgent(self.profile)
        agent.active_thread = "C"
        agent.thread_intensity = 20
        delta = GameStateDelta(narrative="測試", intimacy_change=15)
        update_thread_state(agent, "C", delta)
        self.assertEqual(agent.thread_intensity, 20 + THREAD_INTENSITY_BASE_STEP + 15)
        self.assertFalse(agent.thread_climax_pending)

    def test_thread_lock_d_accumulates_via_faction_reputation_magnitude(self):
        agent = NPCAgent(self.profile)
        agent.active_thread = "D"
        agent.thread_intensity = 20
        delta = GameStateDelta(narrative="測試", faction_reputation_changes={"血衣樓": -30, "正派武林盟": 10})
        update_thread_state(agent, "D", delta)
        self.assertEqual(agent.thread_intensity, 20 + THREAD_INTENSITY_BASE_STEP + 40)

    def test_thread_lock_b_accumulates_fixed_bonus_on_quest_or_milestone_update(self):
        agent_with_update = NPCAgent(self.profile)
        agent_with_update.active_thread = "B"
        agent_with_update.thread_intensity = 20
        delta_with_milestone = GameStateDelta(narrative="測試", milestone_unlocked="第一層毒詛解開")
        update_thread_state(agent_with_update, "B", delta_with_milestone)
        self.assertEqual(agent_with_update.thread_intensity, 20 + THREAD_INTENSITY_BASE_STEP * 2)

        agent_without_update = NPCAgent(self.profile)
        agent_without_update.active_thread = "B"
        agent_without_update.thread_intensity = 20
        delta_without_update = GameStateDelta(narrative="測試")
        update_thread_state(agent_without_update, "B", delta_without_update)
        self.assertEqual(agent_without_update.thread_intensity, 20 + THREAD_INTENSITY_BASE_STEP)

    def test_thread_lock_reaches_climax_pending_when_threshold_crossed(self):
        agent = NPCAgent(self.profile)
        agent.active_thread = "C"
        agent.thread_intensity = THREAD_INTENSITY_THRESHOLD - 10
        delta = GameStateDelta(narrative="測試", intimacy_change=20)
        update_thread_state(agent, "C", delta)
        self.assertGreaterEqual(agent.thread_intensity, THREAD_INTENSITY_THRESHOLD)
        self.assertTrue(agent.thread_climax_pending)
        # 跨過門檻的當下還不會立刻重置，要等收尾回合結束才重置
        self.assertEqual(agent.active_thread, "C")

    def test_thread_lock_resolves_to_neutral_after_climax_round(self):
        agent = NPCAgent(self.profile)
        agent.active_thread = "C"
        agent.thread_intensity = 120
        agent.thread_climax_pending = True
        delta = GameStateDelta(narrative="測試")
        update_thread_state(agent, "C", delta)
        self.assertIsNone(agent.active_thread)
        self.assertEqual(agent.thread_intensity, 0)
        self.assertFalse(agent.thread_climax_pending)

    def test_build_system_prompt_reflects_thread_lock_state(self):
        agent = NPCAgent(self.profile)
        neutral_prompt = agent.build_system_prompt(player_state=self.player_state)
        self.assertIn("選項 C (情慾/色誘/雙修)", neutral_prompt)

        agent.active_thread = "C"
        agent.thread_intensity = 40
        locked_prompt = agent.build_system_prompt(player_state=self.player_state)
        self.assertIn("情慾/色誘/雙修", locked_prompt)
        self.assertIn("A~D 四個選項請全部延續這個主題方向", locked_prompt)
        self.assertNotIn("選項 C (情慾/色誘/雙修): 利用美色", locked_prompt)

        agent.thread_climax_pending = True
        climax_prompt = agent.build_system_prompt(player_state=self.player_state)
        self.assertIn("收尾回合", climax_prompt)

    @patch("src.ollama_client.OllamaClient.chat_structured_stream")
    def test_chosen_category_wiring_from_engine_locks_thread(self, mock_stream):
        """驗證 web_ui 按鈕 -> GameEngine.interact_stream(chosen_category=...) -> NPCAgent
        -> update_thread_state 整條路徑真的有接上，不是只有單元測試裡直接呼叫函式而已"""
        engine = GameEngine()
        engine.switch_npc("風騷老闆娘")
        mock_delta = GameStateDelta(narrative="測試劇情", intimacy_change=10)
        mock_stream.return_value = iter([(mock_delta.narrative, mock_delta)])

        list(engine.interact_stream("C) 上前進行身體接觸試探", chosen_category="C"))

        self.assertEqual(engine.current_agent.active_thread, "C")
        # 這是「從中立進入主題線」的第一回合，只會拿到固定的起始強度；
        # delta 訊號 (intimacy_change 等) 只在已經鎖定後的後續回合才會疊加進去
        self.assertEqual(engine.current_agent.thread_intensity, THREAD_INTENSITY_BASE_STEP)


if __name__ == "__main__":
    unittest.main()
