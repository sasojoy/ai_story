import requests
import json

sys_prompt = """你是一款暗黑搞笑武俠 RPG 的 GM。你正扮演 NPC [合歡宗聖女柳如煙]。
必須且僅能輸出合法 JSON 物件，格式規範如下：
{
  "narrative": "故事劇情與NPC反應描述",
  "npc_status_tag": "NPC情緒標籤",
  "player_hp_change": 0,
  "player_gold_change": 0,
  "inventory_added": [],
  "inventory_removed": [],
  "options": [
    "A) 正派應對選項",
    "B) 搞笑/現代套路選項",
    "C) 18+ 情慾色誘選項"
  ]
}"""

res = requests.post(
    'http://localhost:11434/api/chat',
    json={
        'model': 'qwen2.5:1.5b',
        'messages': [
            {'role': 'system', 'content': sys_prompt},
            {'role': 'user', 'content': '聖女殿下，可否借一步說話？'}
        ],
        'format': 'json',
        'stream': False
    }
)

raw_content = res.json()['message']['content']
print("Raw Output:\n", raw_content)
