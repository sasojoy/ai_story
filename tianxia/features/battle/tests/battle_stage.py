"""契約測試（tests/core/test_contract_features.py）把全服決戰擺進「有選項」的局面：每擺好一種 yield 一個名字。

只擺「平常」：決戰的選項由 Game._battle_menu 的委派給、不經 options／menu 掛鉤（全部拆包第 7 批計畫 1.4），擺出集結的局面的話，契約測試的
「關著的包不給選項」不成立（原位不問 enabled），跟前綴有關的三條對這一包是空的（README 寫著）。選單接上掛鉤的那一批一起改成擺出集結。"""


def stages(game):
    yield "平常"
