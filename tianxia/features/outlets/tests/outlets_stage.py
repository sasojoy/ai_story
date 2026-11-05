"""契約測試（tests/core/test_contract_features.py）把銀兩出口與捐軍備擺進「有選項」的局面：每擺好一種 yield 一個名字。
真實內容 week7 的 Game：坐在軍需官那一串前（店面登記的選單：donate:room、donate:back……）。「打點」那一間店不擺：它的選單是銀兩出口那幾樣
（act:mentor、act:furnace……，核心 act: 前綴的 id）加 dadian:back，契約測試要求這一包給的選項都帶自己的前綴。兩間店的入口（act:donate、
act:dadian）是核心的前綴、排在療傷之後，由 Game._everyday_options 原位叫委派，不在這一包的選單裡，不擺。"""


def stages(game):
    p = game.state.player
    p.picking_donate = True
    yield "坐在軍需官那一串前"
