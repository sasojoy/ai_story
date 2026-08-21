"""
用本機已經架好的 RWKV 續寫模型（見 CLAUDE.md「結局劇情生成管線的後續：RWKV 續寫模型」
一節），針對幾個常見的角色屬性標籤 (character_tags) 各生成一份基礎模板草稿，寫進
config/scene_templates.json（gitignored，不進版本控制）。

這是「起手式」草稿，不是最終模板庫——使用者本來就打算另外從大量參考作品整理正式的
模板庫，這個腳本只是先用同一套本來就在用的無審查模型生成幾份堪用的初稿，省去從零
手打的力氣，之後使用者可以直接在 config/scene_templates.json 裡逐條修改替換。

用法（需先用 scripts/start_rwkv_server.ps1 啟動 RWKV backend-python）：
    python scripts/bootstrap_scene_templates.py

刻意寫成幕後腳本、不透過 Claude Code 直接產文：餵給 RWKV 的前綴只用泛用代詞
（「她」/「你」），不夾帶任何角色姓名或版權角色設定，生成結果本身也不含任何具體真實
人物設定，純粹是空白場景的續寫草稿；真正露骨的文字內容完全來自本機模型的輸出，
不是這支腳本自己寫的。
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.ending_writer import (
    MAX_STEP_RETRIES,
    is_step_output_broken,
    load_ending_writer_config,
    strip_meta_leakage,
    _truncate_before_repeat_loop,
)
from src.rwkv_client import RWKVClient

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "scene_templates.json")

# 每個 act 的前綴刻意只用「她」/「你」這種泛用代詞起頭，不帶任何具體角色姓名或設定，
# 讓生成結果保持角色中立，之後才能安全地在文字裡插入 {name}/{beat:xxx} 佔位符、
# 給多個共用同一 character_tag 的角色重複使用。
ACTS = [
    {
        "act_name": "貼近試探",
        "required_tags": [],
        "label": "溫柔地貼近她",
        "prefix": "燭火搖曳，她終於卸下了慣常的防備，任由對方的氣息一寸寸貼近，",
    },
    {
        "act_name": "敏感反應",
        "required_tags": ["敏感體質"],
        "label": "撫過她的敏感之處",
        "prefix": "指尖不過是輕輕一劃，她整個人便如遭雷擊般繃緊了脊背，連呼吸都亂了節奏，",
    },
    {
        "act_name": "野性反撲",
        "required_tags": ["野性"],
        "label": "與她纏鬥角力",
        "prefix": "她反手扣住對方的手腕，眼底翻湧著毫不掩飾的挑釁與興味，",
    },
    {
        "act_name": "豐盈起伏",
        "required_tags": ["巨乳"],
        "label": "撫弄她的胸乳",
        "prefix": "她微微側身，隨著漸急的呼吸，衣衫下的曲線也跟著輕輕顫動，",
    },
]

# 收尾動作刻意不透過 RWKV 生成——這是一句很短的通用收場白，不需要長篇續寫，手寫
# 反而比較穩定；而且性愛模式至少要有一個 is_finisher=True 的動作，玩家才有辦法
# 結束這個模式（見 src/intimate_mode.py::list_intimate_actions），所以每次跑這個
# 腳本都確保這個 act 存在，不管 ACTS 生成得順不順利。
_FINISHER_ACT_NAME = "圓滿收場"
_FINISHER_ACT = {
    "required_tags": [],
    "label": "射入花心",
    "applicable_endings": [],
    "is_finisher": True,
    "variants": [
        {"text": "{beat:opening}{name}輕輕靠進{player_name}懷裡，讓這一夜的糾纏，在彼此交疊的呼吸聲中緩緩落下帷幕。{beat:reaction}"}
    ],
}

_SENTENCE_SPLIT = re.compile(r"(?<=[。！？])")


def _generate_raw(client: RWKVClient, prefix: str, config, max_tokens: int) -> str:
    """呼叫 RWKV 續寫，套用跟 ending_writer.py 同一套破格過濾/崩壞重試邏輯。"""
    text = ""
    for _attempt in range(MAX_STEP_RETRIES):
        text = strip_meta_leakage(
            client.complete(
                prefix, max_tokens=max_tokens,
                temperature=config.temperature, top_p=config.rwkv_top_p,
            )
        )
        if not is_step_output_broken(text, expected_min_chars=max_tokens // 2):
            break
    else:
        text = _truncate_before_repeat_loop(text)
    return text


def _insert_placeholders(prefix: str, generated: str) -> str:
    """把「前綴 + 生成內容」組成完整文字，做兩件事：
    1. 把第一次出現的「她」換成 {name}（只換第一次，後面沿用代詞才符合中文行文習慣，
       跟 config/scene_templates.example.json 手寫範例的慣例一致）。
    2. 在文字前三成、後兩成的句界各插入一個 {beat:opening}/{beat:reaction}，
       之後使用者可以自行調整插入點或替換成不同的插槽數量。"""
    full_text = prefix + generated
    full_text = full_text.replace("她", "{name}", 1)

    sentences = [s for s in _SENTENCE_SPLIT.split(full_text) if s.strip()]
    n = len(sentences)
    if n < 3:
        return full_text

    opening_idx = max(1, n // 3)
    reaction_idx = max(opening_idx + 1, n - max(1, n // 5))
    reaction_idx = min(reaction_idx, n - 1)

    sentences.insert(reaction_idx, "{beat:reaction}")
    sentences.insert(opening_idx, "{beat:opening}")
    return "".join(sentences)


def main():
    config = load_ending_writer_config()
    client = RWKVClient(base_url=config.rwkv_url, timeout=config.timeout)
    if not client.check_health():
        print(f"連不上 RWKV backend ({config.rwkv_url})，請先執行 scripts/start_rwkv_server.ps1")
        sys.exit(1)

    existing = {}
    if os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
            existing = json.load(f)
        print(f"{OUTPUT_PATH} 已存在，將只新增缺少的 act，不覆蓋既有內容。")

    for spec in ACTS:
        act_name = spec["act_name"]
        if act_name in existing:
            print(f"[跳過] {act_name} 已存在")
            continue

        print(f"[生成中] {act_name} ...")
        raw = _generate_raw(client, spec["prefix"], config, max_tokens=500)
        text = _insert_placeholders(spec["prefix"], raw)

        existing[act_name] = {
            "required_tags": spec["required_tags"],
            "label": spec["label"],
            "variants": [{"text": text}],
        }
        print(f"[完成] {act_name}（{len(text)} 字）")

    if _FINISHER_ACT_NAME not in existing:
        existing[_FINISHER_ACT_NAME] = _FINISHER_ACT
        print(f"[補上] {_FINISHER_ACT_NAME}（手寫收尾動作，確保性愛模式至少有一個能結束的選項）")

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    print(f"已寫入 {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
