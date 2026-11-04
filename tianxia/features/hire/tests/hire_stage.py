"""契約測試（tests/core/test_contract_features.py）把招募同伴擺進「有選項」的局面：每擺好一種 yield 一個名字。
測試內容沒有一般 NPC（content/hirelings.json 只在正式內容），擺不出來就只有平常那一種。"""


def stages(game):
    yield "平常"
