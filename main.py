import sys
import os
import json
from typing import List

# 確保可 import src 模組
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 避免 Windows 主機 CP950 終端機印出特殊 unicode 字元拋出 UnicodeEncodeError
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.game_engine import GameEngine
from src.save_manager import has_account_save


def print_banner():
    print("=" * 65)
    print("         Local Blade RPG Engine - 本地刀鋒暗黑武俠 (v1.0.0)")
    print("=" * 65)


def print_prologue(engine: GameEngine):
    intro = engine.world_intro
    print("\n" + "=" * 65)
    print(f"【序幕故事】 {intro.get('title', '血夜龍門')}")
    print("=" * 65)
    print(f"{intro.get('opening_narrative', '')}\n")
    print(f"【大背景局勢衝突】\n{intro.get('background_conflict', '')}\n")
    print(f"【初始主線任務】\n{engine.main_quest_summary}\n")
    print(f"【初始勢力聲望】 {engine.factions}")
    print("=" * 65)


def print_status(engine: GameEngine):
    p = engine.player_state
    factions_str = ", ".join([f"{k}:{v}" for k, v in engine.factions.items()])
    print("\n" + "-" * 55)
    print(f"【回合: 第 {engine.game_turn} 回合】 | 【主線摘要】: {engine.main_quest_summary}")
    print(f"【勢力聲望】: {factions_str}")
    print(f"【玩家狀態】 HP: {p.hp}/{p.max_hp} | 金幣: {p.gold} | 背包: {', '.join(p.inventory) if p.inventory else '空'}")
    if engine.current_agent:
        npc = engine.current_agent.profile
        tag = engine.current_agent.current_status_tag
        print(f"【當前對象】 {npc.name} ({npc.identity}) | 位置: {npc.location} | 狀態: {tag}")
    print("-" * 55)


def switch_npc_menu(engine: GameEngine):
    print("\n可互動 NPC 列表：")
    npc_names = list(engine.agents.keys())
    for idx, name in enumerate(npc_names, 1):
        npc = engine.agents[name].profile
        print(f"  {idx}. {npc.name} - {npc.identity} (地點: {npc.location})")

    choice = input("\n請選擇要切換的 NPC 編號或名稱 (輸入 Enter 取消): ").strip()
    if not choice:
        return

    selected_name = None
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(npc_names):
            selected_name = npc_names[idx]
    elif choice in engine.agents:
        selected_name = choice

    if selected_name and engine.switch_npc(selected_name):
        print(f"\n>>> 已成功切換至 [{selected_name}]！")
    else:
        print("\n>>> 切換失敗，找不到該 NPC。")


def main():
    print_banner()

    # 初始化遊戲引擎
    try:
        engine = GameEngine()
    except Exception as e:
        print(f"初始化遊戲失敗: {e}")
        return

    # 顯示序幕與世界大背景
    print_prologue(engine)

    # 詢問玩家名稱，作為帳號存檔的識別依據
    player_name = input("\n請輸入你的俠客名號 (直接 Enter 使用預設名稱): ").strip()
    if player_name:
        engine.set_player_name(player_name)

    if has_account_save(engine.player_state.name):
        resume = input(f"\n偵測到帳號 [{engine.player_state.name}] 的歷史存檔，要讀取嗎？ (Y/n): ").strip().lower()
        if resume != "n":
            if engine.load_account(engine.player_state.name):
                print(f"\n>>> 已讀取帳號 [{engine.player_state.name}] 的歷史進度！")

    input("\n按下 [Enter] 鍵 踏入江湖，開啟冒險...")

    # 檢查 Ollama 連線狀態
    print("\n正在檢查 Ollama 本地服務連線...")
    if engine.client.check_health():
        print(f"[OK] 已成功連線至 Ollama ({engine.game_config.ollama_url}), 模型: {engine.game_config.model_name}")
    else:
        print(f"[!] 警告: 無法連線至 Ollama ({engine.game_config.ollama_url})！")
        print("請確認 Ollama 服務已啟動 (例如: ollama run qwen2.5:1.5b)")

    print("\n提示指令: [/switch 切換NPC] [/dossier 查看NPC生平檔案] [/save 存檔] [/load 讀取存檔] [/status 玩家狀態] [/reset 重置對話] [/exit 退出遊戲]")

    last_options: List[str] = []

    while True:
        try:
            print_status(engine)
            option_letters = ["A", "B", "C", "D", "E"]
            if last_options:
                print("\n【動態劇情選項】")
                for letter, opt in zip(option_letters, last_options):
                    print(f"  [{letter}] {opt}")
                print("  (輸入字母選擇，或直接打字輸入任意行動/對話)")

            user_input = input("\n請選擇 (A/B/C/D/E) 或輸入行動 > ").strip()

            if not user_input:
                continue

            if user_input.upper() in option_letters:
                idx = option_letters.index(user_input.upper())
                if idx < len(last_options):
                    user_input = last_options[idx]

            if user_input.lower() in ["/save", "save"]:
                msg = engine.auto_save(engine.player_state.name)
                print(f"\n>>> {msg}")
                continue

            elif user_input.lower() in ["/load", "load"]:
                success = engine.load_account(engine.player_state.name)
                if success:
                    print(f"\n>>> 成功讀取帳號 [{engine.player_state.name}] 的存檔！")
                    last_options = []
                else:
                    print(f"\n>>> 讀取帳號 [{engine.player_state.name}] 失敗 (找不到存檔)")
                continue

            elif user_input.lower() in ["/status", "status"]:
                # print_status 已在每輪迴圈開頭執行，這裡僅確保 /status 是可被辨識的指令，
                # 不會被誤當成玩家行動送給 LLM
                continue

            elif user_input.lower() in ["/exit", "exit", "quit", "q"]:
                print("感謝遊玩，遊戲結束！")
                break

            elif user_input.lower() in ["/switch", "switch"]:
                switch_npc_menu(engine)
                continue

            elif user_input.lower() in ["/dossier", "dossier", "/npc", "npc"]:
                if engine.current_agent:
                    profile = engine.current_agent.profile
                    print(f"\n【NPC 詳細檔案與生平解鎖】: {profile.name} ({profile.identity})")
                    print(f"親密度: {profile.intimacy}/100 (提示: 提升親密度至 25/50/75 可逐步解鎖數值與生平)")
                    print(f"數值情報: {profile.get_unlocked_stats()}")
                    print("生平故事:")
                    for b in profile.get_unlocked_biography():
                        print(f"  - {b}")
                else:
                    print("\n>>> 當前未選定互動 NPC。")
                continue

            elif user_input.lower() in ["/reset", "reset"]:
                if engine.current_agent:
                    engine.current_agent.reset_history()
                    print(f"\n>>> 已重置與 {engine.current_agent.profile.name} 的對話歷史。")
                continue

            # 與 NPC 互動
            print("\nGM 算牌中/推演劇情演變...")
            delta = engine.interact(user_input)
            if delta.options and len(delta.options) >= 3:
                last_options = delta.options

            # 印出結果
            print("\n" + "=" * 55)
            print(f"【劇情發展 (第 {engine.game_turn} 回合)】\n{delta.narrative}")
            print("=" * 55)

            # 顯示數值變更
            changes = []
            if delta.player_hp_change != 0:
                sign = "+" if delta.player_hp_change > 0 else ""
                changes.append(f"HP {sign}{delta.player_hp_change}")
            if delta.player_gold_change != 0:
                sign = "+" if delta.player_gold_change > 0 else ""
                changes.append(f"金幣 {sign}{delta.player_gold_change}")
            if delta.inventory_added:
                changes.append(f"獲得: {', '.join(delta.inventory_added)}")
            if delta.inventory_removed:
                changes.append(f"失去: {', '.join(delta.inventory_removed)}")

            if changes:
                print(f"[*] 數值變更: {' | '.join(changes)}")
            if delta.main_quest_summary_update:
                print(f"📖 主線自動改寫: [{delta.main_quest_summary_update}]")
            if delta.faction_reputation_changes:
                print(f"🏛️ 勢力聲望變更: {delta.faction_reputation_changes}")
            if delta.npc_status_tag:
                print(f"[NPC] 狀態變更: [{delta.npc_status_tag}]")

        except KeyboardInterrupt:
            print("\n遊戲終止。")
            break
        except Exception as e:
            print(f"\n[ERROR] 發生錯誤: {e}")


if __name__ == "__main__":
    main()
